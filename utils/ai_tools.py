"""AI document analysis — Gemini REST API with Groq fallback"""
from __future__ import annotations
import requests
import json
import re
import time
import hashlib
import threading
from collections import deque
from typing import Dict, Tuple, Optional
from dotenv import dotenv_values
from utils.logger import get_logger

_log = get_logger(__name__)


# re-reads .env on every call so a key swap takes effect without restart
def _get_gemini_key() -> str:
    key = dotenv_values('.env').get('GEMINI_API_KEY', '')
    if not key:
        from utils.api_key_manager import get_current_api_key
        key = get_current_api_key() or ''
    return key

def _get_groq_key() -> str:
    return dotenv_values('.env').get('GROQ_API_KEY', '')


# response cache — 24h TTL, max 200 entries, evicts oldest when full
class _ResponseCache:
    TTL     = 86400   # 24 hours
    MAX     = 200

    def __init__(self):
        self._lock  = threading.Lock()
        self._store: Dict[str, tuple] = {}   # hash -> (result, expires_at)

    def _key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode('utf-8')).hexdigest()

    def get(self, prompt: str) -> Optional[str]:
        k = self._key(prompt)
        with self._lock:
            entry = self._store.get(k)
            if entry and time.time() < entry[1]:
                return entry[0]
            if entry:
                del self._store[k]
        return None

    def set(self, prompt: str, result: str):
        k = self._key(prompt)
        with self._lock:
            # drop oldest entry when at capacity
            if len(self._store) >= self.MAX:
                oldest = min(self._store.items(), key=lambda x: x[1][1])
                del self._store[oldest[0]]
            self._store[k] = (result, time.time() + self.TTL)

    def size(self) -> int:
        with self._lock:
            return len(self._store)


_cache = _ResponseCache()


def get_cache_stats() -> dict:
    return {"cached_responses": _cache.size(), "ttl_hours": 24}


# per-IP rate limiter — 20 AI requests per IP per hour
class _IpLimiter:
    MAX_PER_IP = 20
    WINDOW     = 3600.0

    def __init__(self):
        self._lock = threading.Lock()
        self._log: Dict[str, deque] = {}

    def _evict(self, dq: deque, now: float):
        cutoff = now - self.WINDOW
        while dq and dq[0] < cutoff:
            dq.popleft()

    def check(self, ip: str) -> Tuple[bool, int]:
        with self._lock:
            now = time.time()
            dq = self._log.setdefault(ip, deque())
            self._evict(dq, now)
            if len(dq) >= self.MAX_PER_IP:
                wait = int(self.WINDOW - (now - dq[0])) + 1
                return False, wait
            dq.append(now)
            return True, 0

    def remaining(self, ip: str) -> int:
        with self._lock:
            now = time.time()
            dq = self._log.get(ip, deque())
            self._evict(dq, now)
            return max(0, self.MAX_PER_IP - len(dq))


_ip_limiter = _IpLimiter()


def check_ip_limit(ip: str) -> Tuple[bool, int]:
    return _ip_limiter.check(ip)


def get_ip_remaining(ip: str) -> int:
    return _ip_limiter.remaining(ip)


# global RPM limiter — Gemini free tier is 15 RPM, we cap at 10 to stay safe
class _RateLimiter:
    RPM_LIMIT = 10
    WINDOW    = 60.0

    def __init__(self):
        self._lock      = threading.Lock()
        self._req_times = deque()

    def _evict(self, now: float):
        cutoff = now - self.WINDOW
        while self._req_times and self._req_times[0] < cutoff:
            self._req_times.popleft()

    def reset(self):
        with self._lock:
            self._req_times.clear()

    def acquire(self):
        while True:
            with self._lock:
                now = time.time()
                self._evict(now)
                if len(self._req_times) < self.RPM_LIMIT:
                    self._req_times.append(now)
                    return
                wait = self.WINDOW - (now - self._req_times[0]) + 0.5
            time.sleep(max(wait, 1.0))


_rate_limiter  = _RateLimiter()
_current_key_ref: list = [None]


def reset_rate_limiter():
    _rate_limiter.reset()


# daily request counter — free tier allows 1500 RPD
class _DailyCounter:
    RPD_LIMIT = 1500

    def __init__(self):
        self._lock  = threading.Lock()
        self._count = 0
        self._day   = time.strftime("%Y-%m-%d")

    def increment(self):
        with self._lock:
            today = time.strftime("%Y-%m-%d")
            if today != self._day:
                self._count = 0
                self._day = today
            self._count += 1

    def status(self) -> dict:
        with self._lock:
            today = time.strftime("%Y-%m-%d")
            if today != self._day:
                self._count = 0
                self._day = today
            used = self._count
            remaining = max(0, self.RPD_LIMIT - used)
            pct = round((used / self.RPD_LIMIT) * 100, 1)
            return {
                "used": used,
                "remaining": remaining,
                "limit": self.RPD_LIMIT,
                "percent_used": pct,
                "date": self._day,
                "warning": pct >= 80,
            }


_daily_counter = _DailyCounter()


def get_quota_status() -> dict:
    return _daily_counter.status()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _truncate(text: str, max_chars: int = 10000) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[Document truncated…]"
    return text


def _extract_json(raw: str) -> dict:
    cleaned = re.sub(r'```(?:json)?\s*', '', raw).strip().replace('```', '').strip()
    for s in (cleaned, raw):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        start, end = s.find('{'), s.rfind('}')
        if start != -1 and end > start:
            try:
                return json.loads(s[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise RuntimeError("Could not parse structured response from AI.")


def _compress_prompt(prompt: str) -> str:
    # trim whitespace to cut down token usage
    prompt = re.sub(r'\n{3,}', '\n\n', prompt)
    prompt = '\n'.join(line.rstrip() for line in prompt.splitlines())
    return prompt.strip()


# Groq fallback — kicks in automatically when Gemini quota runs out
# uses llama-3.1-8b-instant (fast, free tier)
def _groq_request(prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> str:
    api_key = _get_groq_key()
    if not api_key:
        raise RuntimeError("Groq API key not configured. Add GROQ_API_KEY to .env")
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    if resp.status_code == 429:
        raise RuntimeError("Groq rate limit hit. Please wait a moment.")
    if resp.status_code != 200:
        raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:200]}")
    return resp.json()["choices"][0]["message"]["content"]


# core Gemini request — falls back to Groq if quota is hit
def _gemini_request(prompt: str, temperature: float = 0.3,
                    max_tokens: int = 1024, json_mode: bool = False) -> str:
    prompt = _compress_prompt(prompt)

    # return cached result if we've seen this exact prompt before
    cache_key = f"{prompt}|t={temperature}|mt={max_tokens}|j={json_mode}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    api_key = _get_gemini_key()
    if not api_key:
        raise RuntimeError("No API key configured. Please add one in Settings.")

    # reset the limiter when the key changes
    if _current_key_ref[0] != api_key:
        _rate_limiter.reset()
        _current_key_ref[0] = api_key

    _rate_limiter.acquire()

    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"models/gemini-2.0-flash:generateContent?key={api_key}")
    gen_config: dict = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
        "topP": 0.9,
    }
    if json_mode:
        gen_config["responseMimeType"] = "application/json"

    resp = requests.post(
        url,
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_config},
        timeout=90,
    )

    if resp.status_code == 429:
        try:
            err_body = resp.json()
            err_msg  = err_body.get("error", {}).get("message", "")
            err_st   = err_body.get("error", {}).get("status", "")
        except Exception:
            err_msg, err_st = resp.text[:200], ""
        if "quota" in err_msg.lower() or err_st == "RESOURCE_EXHAUSTED":
            fallback_key = dotenv_values('.env').get('GEMINI_API_KEY_FALLBACK', '')
            if fallback_key and api_key != fallback_key:
                _log.warning("Primary Gemini quota hit — trying fallback key")

                # make the request directly to avoid recursion
                url = (f"https://generativelanguage.googleapis.com/v1beta/"
                       f"models/gemini-2.0-flash:generateContent?key={fallback_key}")
                fallback_resp = requests.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_config},
                    timeout=90,
                )
                if fallback_resp.status_code == 200:
                    text_out = fallback_resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    _daily_counter.increment()
                    _cache.set(cache_key, text_out)
                    return text_out
                _log.warning("Fallback Gemini key also failed — trying Groq")

            groq_key = _get_groq_key()
            if groq_key:
                _log.warning("Gemini quota hit — switching to Groq")
                result = _groq_request(prompt, temperature, max_tokens)
                _cache.set(cache_key, result)
                return result
            raise RuntimeError(
                "Gemini API daily quota exhausted and no Groq fallback configured. "
                "Add GROQ_API_KEY to .env or wait until midnight for Gemini reset."
            )
        raise RuntimeError(f"API rate limit hit. Please wait a moment and try again. ({err_msg[:100]})")

    if resp.status_code != 200:
        err = resp.text[:300]
        if "quota" in err.lower() or "exhausted" in err.lower():
            fallback_key = dotenv_values('.env').get('GEMINI_API_KEY_FALLBACK', '')
            if fallback_key and api_key != fallback_key:
                _log.warning("Primary Gemini quota hit — trying fallback key")
                
                url = (f"https://generativelanguage.googleapis.com/v1beta/"
                       f"models/gemini-2.0-flash:generateContent?key={fallback_key}")
                fallback_resp = requests.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_config},
                    timeout=90,
                )
                if fallback_resp.status_code == 200:
                    text_out = fallback_resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    _daily_counter.increment()
                    _cache.set(cache_key, text_out)
                    return text_out
                _log.warning("Fallback Gemini key also failed — trying Groq")

            # try Groq if both Gemini keys are exhausted
            groq_key = _get_groq_key()
            if groq_key:
                _log.warning("Gemini quota hit — switching to Groq")
                result = _groq_request(prompt, temperature, max_tokens)
                _cache.set(cache_key, result)
                return result
            raise RuntimeError("API quota exhausted. Please update your API key in Settings.")
        if "invalid" in err.lower() and "key" in err.lower():
            raise RuntimeError("Invalid API key. Please update it in Settings.")
        raise RuntimeError(f"API error {resp.status_code}: {err}")

    try:
        text_out = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        _daily_counter.increment()
        # cache so the same prompt doesn't hit the API twice
        _cache.set(cache_key, text_out)
        return text_out
    except (KeyError, IndexError):
        raise RuntimeError("Unexpected API response format.")


# document brief
def _smart_sample(text: str, max_chars: int = 4000) -> str:
    # grab start, middle, and end instead of the full doc — saves ~60% tokens
    text = text.strip()
    if len(text) <= max_chars:
        return text
    chunk = max_chars // 5
    start  = text[:chunk * 2]
    mid_s  = len(text) // 2 - chunk // 2
    middle = text[mid_s: mid_s + chunk]
    end    = text[-(chunk * 2):]
    return f"{start}\n\n[...middle section...]\n\n{middle}\n\n[...end section...]\n\n{end}"


def generate_document_brief(text: str, filename: str) -> dict:
    prompt = f"""You are an expert document analyst. Analyze the document below and return a structured JSON brief.

DOCUMENT: {filename}
=== CONTENT ===
{_smart_sample(text)}
=== END ===

Return ONLY a valid JSON object with these exact keys:
{{
  "document_type": "e.g. Contract, Research Paper, Invoice, Report, Resume, etc.",
  "one_liner": "One sentence describing what this document is about.",
  "purpose": "2-3 sentences on the document's purpose and context.",
  "audience": "Who this document is intended for.",
  "key_entities": ["list of important names, organizations, or places mentioned"],
  "key_dates": ["list of important dates or deadlines found"],
  "key_numbers": ["list of important figures, amounts, percentages, or statistics"],
  "action_items": ["list of tasks, obligations, or next steps mentioned"],
  "risk_flags": ["list of concerning clauses, legal language, or red flags — empty list if none"]
}}

Be precise. Extract only what is actually in the document. Use empty list or "Not specified" when nothing relevant."""

    raw = _gemini_request(prompt, temperature=0.2, max_tokens=700, json_mode=True)
    return _extract_json(raw)


# ─────────────────────────────────────────────
# 2. DOCUMENT REWRITER
# ─────────────────────────────────────────────
REWRITE_TONES = {
    "formal":    "Rewrite in a highly formal, professional tone suitable for business or legal contexts.",
    "casual":    "Rewrite in a friendly, conversational tone — clear and easy to read.",
    "simpler":   "Rewrite in plain English. Use short sentences, simple words. Aim for a Grade 6 reading level.",
    "academic":  "Rewrite in an academic tone with precise language, passive voice where appropriate, and scholarly phrasing.",
    "bullets":   "Convert the content into a clean, structured bullet-point format. Group related points under short headings.",
    "concise":   "Rewrite as concisely as possible. Remove all filler. Keep only the essential information.",
}

def rewrite_document(text: str, tone: str) -> str:
    if tone not in REWRITE_TONES:
        raise ValueError(f"Unknown tone: {tone}")
    # only rewrite the first 3000 chars to stay within token budget
    input_text = _truncate(text, 3000)
    prompt = f"""{REWRITE_TONES[tone]}

Preserve all factual information, names, dates, and numbers exactly as they appear. Do not add new information.

=== ORIGINAL TEXT ===
{input_text}
=== END ===

Rewritten version:"""
    return _gemini_request(prompt, temperature=0.5, max_tokens=600)


# ─────────────────────────────────────────────
# 3. AI OCR CORRECTION
# ─────────────────────────────────────────────
def correct_ocr_text(raw_ocr_text: str) -> str:
    # split into 2500-char chunks so the output never gets cut off mid-sentence
    MAX_CHUNK = 2500
    text = raw_ocr_text.strip()

    if len(text) <= MAX_CHUNK:
        chunks = [text]
    else:
        # Split on paragraph boundaries where possible
        paragraphs = text.split('\n\n')
        chunks, current = [], ''
        for para in paragraphs:
            if len(current) + len(para) + 2 <= MAX_CHUNK:
                current += ('\n\n' if current else '') + para
            else:
                if current:
                    chunks.append(current)
                # paragraph too long on its own — hard split it
                if len(para) > MAX_CHUNK:
                    for i in range(0, len(para), MAX_CHUNK):
                        chunks.append(para[i:i + MAX_CHUNK])
                else:
                    current = para
        if current:
            chunks.append(current)

    corrected_parts = []
    for chunk in chunks:
        prompt = f"""Fix OCR errors in the text below. Rules:
- Fix only OCR mistakes (l→1, 0→O, rn→m, broken words, missing spaces, garbled punctuation)
- Do NOT rephrase, summarize, or change meaning
- Preserve all paragraph breaks and structure
- Return ONLY the corrected text, nothing else

=== RAW OCR TEXT ===
{chunk}
=== END ==="""
        corrected_parts.append(_gemini_request(prompt, temperature=0.1, max_tokens=1200))

    return '\n\n'.join(corrected_parts)


# ─────────────────────────────────────────────
# 4. TONE & SENTIMENT ANALYZER
# ─────────────────────────────────────────────
def analyze_tone_sentiment(text: str) -> dict:
    prompt = f"""You are an expert linguist. Analyze the tone and sentiment of the text below.

=== TEXT ===
{_truncate(text, 6000)}
=== END ===

Return ONLY a valid JSON object with these exact keys:
{{
  "overall_sentiment": "Positive | Negative | Neutral | Mixed",
  "sentiment_score": <number -100 to +100>,
  "formality": "Very Formal | Formal | Neutral | Informal | Very Informal",
  "formality_score": <number 0 to 100>,
  "reading_level": "e.g. Grade 8, University, Professional",
  "reading_time_minutes": <number>,
  "tone_tags": ["e.g. Persuasive, Authoritative, Empathetic, Urgent, Cautious"],
  "flagged_sentences": [
    {{"sentence": "exact sentence", "reason": "why flagged"}}
  ],
  "summary": "2-3 sentence plain-English summary of the document's overall tone."
}}

Flag up to 5 sentences that are legally risky, emotionally charged, or ambiguous. Empty list if none."""

    raw = _gemini_request(prompt, temperature=0.2, max_tokens=700, json_mode=True)
    return _extract_json(raw)


# ─────────────────────────────────────────────
# 5. AI COMPARISON EXPLANATION
# ─────────────────────────────────────────────
def explain_pdf_diff(text1: str, text2: str, filename1: str, filename2: str) -> dict:
    t1 = _truncate(text1, 4000)
    t2 = _truncate(text2, 4000)
    prompt = f"""You are a senior document analyst. Compare these two document versions and explain what changed.

=== DOCUMENT 1: {filename1} ===
{t1}
=== END DOCUMENT 1 ===

=== DOCUMENT 2: {filename2} ===
{t2}
=== END DOCUMENT 2 ===

Return ONLY a valid JSON object:
{{
  "summary": "2-3 sentence overview of the key differences.",
  "verdict": "e.g. Minor edits, Significant changes, Major restructuring, Contradictory versions",
  "changes": [
    {{
      "section": "Where in the document (e.g. Introduction, Clause 4)",
      "original": "Brief description of what Document 1 says",
      "revised": "Brief description of what Document 2 says",
      "significance": "Why this change matters"
    }}
  ]
}}

List up to 8 meaningful changes. Ignore trivial formatting differences."""

    raw = _gemini_request(prompt, temperature=0.2, max_tokens=800, json_mode=True)
    return _extract_json(raw)


def extract_resume_data(text: str) -> dict:
    """Extract structured data from a resume using Gemini."""
    t = _smart_sample(text, 5000)
    prompt = f"""You are an expert HR analyst. Extract structured information from this resume.

=== RESUME ===
{t}
=== END RESUME ===

Return ONLY a valid JSON object with this exact structure:
{{
  "name": "Full name of the candidate",
  "email": "Email address or null",
  "phone": "Phone number or null",
  "location": "City/Country or null",
  "summary": "2-3 sentence professional summary",
  "skills": ["skill1", "skill2", "skill3"],
  "experience": [
    {{
      "title": "Job title",
      "company": "Company name",
      "duration": "e.g. Jan 2020 – Mar 2023",
      "highlights": ["key achievement or responsibility"]
    }}
  ],
  "education": [
    {{
      "degree": "Degree name",
      "institution": "University/College name",
      "year": "Graduation year or duration"
    }}
  ],
  "certifications": ["cert1", "cert2"],
  "languages": ["English", "Hindi"]
}}

If a field is not found, use null or an empty list. Do not invent data."""

    raw = _gemini_request(prompt, temperature=0.1, max_tokens=1200, json_mode=True)
    return _extract_json(raw)


def extract_invoice_data(text: str) -> dict:
    """Extract structured data from an invoice using Gemini."""
    t = _smart_sample(text, 4000)
    prompt = f"""You are an expert accountant. Extract all invoice details from this document.

=== INVOICE ===
{t}
=== END INVOICE ===

Return ONLY a valid JSON object with this exact structure:
{{
  "invoice_number": "Invoice ID or null",
  "invoice_date": "Date of invoice or null",
  "due_date": "Payment due date or null",
  "vendor": {{
    "name": "Seller/vendor company name",
    "address": "Vendor address or null",
    "email": "Vendor email or null",
    "phone": "Vendor phone or null"
  }},
  "client": {{
    "name": "Buyer/client name",
    "address": "Client address or null"
  }},
  "line_items": [
    {{
      "description": "Item or service description",
      "quantity": "Quantity or null",
      "unit_price": "Price per unit or null",
      "total": "Line total or null"
    }}
  ],
  "subtotal": "Subtotal amount or null",
  "tax": "Tax amount or null",
  "discount": "Discount amount or null",
  "total_amount": "Final total amount",
  "currency": "Currency code e.g. USD, INR",
  "payment_method": "Payment method or null",
  "notes": "Any additional notes or null"
}}

If a field is not present, use null. Do not invent data."""

    raw = _gemini_request(prompt, temperature=0.1, max_tokens=1200, json_mode=True)
    return _extract_json(raw)

import os
import requests
from typing import List, Dict, Optional
import json
import hashlib
import re
import time
from utils.api_key_manager import get_current_api_key
from utils.logger import get_logger

_log = get_logger(__name__)

class DocumentChatManager:
    """Manages document chat sessions with Gemini API, optimized for free tier"""
    
    def __init__(self, api_key: str = None):
        # Use provided key or get current from manager
        if api_key is None:
            api_key = get_current_api_key()
        
        if not api_key:
            raise ValueError("No API key available. Please configure an API key.")
        
        self.api_key = api_key
        # Use v1 API with gemini-2.5-flash
        self.api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        self.chat_sessions = {}
        self.document_cache = {}

        _log.info("Chat manager initialised")
        
    def get_document_hash(self, file_path: str) -> str:
        """Generate hash for document to use as cache key"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def clean_and_format_response(self, text: str) -> str:
        """Clean up AI response to make it more readable and professional"""
        
        # Remove excessive asterisks used for emphasis (e.g., **text** or ***text***)
        # But preserve single asterisks for bullet points
        text = re.sub(r'\*{3,}([^*]+?)\*{3,}', r'**\1**', text)  # Normalize triple+ to double
        
        # Remove ### headers that look messy
        text = re.sub(r'#{2,}\s*', '', text)
        
        # Clean up "According to Slide X" references - make them cleaner
        text = re.sub(r'According to Slide \d+[,:]\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Slide \d+ (?:of the document )?(?:discusses|states|mentions|says|explains)[,:]\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(?:The document|This document) (?:states|mentions|says|explains|discusses)[,:]\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Based on (?:the )?(?:document|content)[,:]\s*', '', text, flags=re.IGNORECASE)
        
        # Clean up excessive spacing but preserve paragraph breaks
        text = re.sub(r'\n{4,}', '\n\n', text)  # Max 2 newlines (one blank line)
        text = re.sub(r' {2,}', ' ', text)  # Remove multiple spaces
        
        # Fix bullet points - ensure they're clean
        text = re.sub(r'^\s*[\*\-\•]\s*\*{2,}', '* **', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s*\*{2,}', lambda m: m.group(0).replace('**', '**', 1), text, flags=re.MULTILINE)
        
        # Add proper spacing after periods if missing (but not for abbreviations)
        text = re.sub(r'\.(?=[A-Z][a-z])', '. ', text)
        
        # Clean up quotes that have excessive formatting
        text = re.sub(r'"\s*\*{2,}', '"**', text)
        text = re.sub(r'\*{2,}\s*"', '**"', text)
        
        # Ensure proper spacing around lists
        # Add blank line before bullet points if not present
        text = re.sub(r'([^\n])\n(\s*[\*\-\•]\s)', r'\1\n\n\2', text)
        # Add blank line before numbered lists if not present
        text = re.sub(r'([^\n])\n(\s*\d+\.\s)', r'\1\n\n\2', text)
        
        # Remove trailing whitespace from each line
        lines = [line.rstrip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    
    def extract_document_content(self, file_path: str, text_content: str) -> str:
        """Prepare document content for chat context"""
        doc_hash = self.get_document_hash(file_path)
        
        # Check cache first
        if doc_hash in self.document_cache:
            return self.document_cache[doc_hash]
        
        # Truncate if too long (Gemini free tier has token limits)
        max_chars = 30000  # Conservative limit for free tier
        if len(text_content) > max_chars:
            text_content = text_content[:max_chars] + "\n\n[Document truncated due to length...]"
        
        # Cache the content
        self.document_cache[doc_hash] = text_content
        return text_content
    
    def start_chat_session(self, session_id: str, document_content: str, filename: str) -> Dict:
        """Initialize a new chat session with document context"""

        _log.debug("Starting chat session %s for %s (%d chars)",
                   session_id, filename, len(document_content))
        
        # Create comprehensive system prompt with strict document-only instructions
        system_prompt = f"""You are a helpful, intelligent assistant that answers questions based on provided documents. Your goal is to provide accurate information in a way that is incredibly easy for the user to read and digest.

DOCUMENT: {filename}

=== DOCUMENT CONTENT ===
{document_content}
=== END OF DOCUMENT ===

When generating your response, you MUST strictly adhere to the following formatting rules:

1. Tone: Maintain a natural, conversational, yet highly professional tone. Write as if you are explaining a concept to a colleague.

2. Structure & Spacing: Never output a giant wall of text. Break your responses into short, focused paragraphs. Always include clear spacing (a full blank line) between paragraphs.

3. Use Lists: Whenever you are listing multiple items, steps, or distinct concepts (like different database normal forms), you must use bullet points or numbered lists. Each item in the list must be on its own line.

4. Clean Formatting: Avoid excessive asterisks, hashtags, or special characters. Use bold text sparingly and only to highlight key terms at the start of a bullet point.

5. No Document References: Do NOT include phrases like "According to Slide X", "The document states", or "Based on the content". Just provide the information naturally.

6. Direct Answers: Start with a clear, direct answer to the question, then provide supporting details.

EXAMPLE OF GOOD FORMATTING:

Question: "What is 3NF?"

Good Answer:
Third Normal Form (3NF) is a level of database normalization that reduces data redundancy and improves data integrity.

A table is in 3NF if it meets two key requirements:

1. **Already in 2NF**: The table must be in Second Normal Form, meaning all attributes contain atomic values and non-key attributes are fully functionally dependent on the primary key.

2. **No transitive dependencies**: There should be no transitive functional dependencies, meaning no non-prime attribute should be transitively dependent on a key.

The primary goal of 3NF is to ensure that every non-key attribute depends directly on a key, rather than indirectly through another non-key attribute. This eliminates redundancy and prevents data inconsistencies.

YOUR TASK:
Answer the user's question using information from the document above. Present it in a clean, professional, easy-to-read format following all the formatting rules."""

        # Store session
        self.chat_sessions[session_id] = {
            'chat': None,
            'document_content': document_content,
            'filename': filename,
            'message_count': 0,
            'system_prompt': system_prompt
        }

        _log.debug("Session %s created", session_id)
        
        return {
            'session_id': session_id,
            'status': 'ready',
            'filename': filename
        }
    
    def search_document_context(self, document_content: str, query: str, num_results: int = 3) -> str:
        """Search document for relevant content related to the user's query"""
        
        # Split document into sentences for better context extraction
        sentences = [s.strip() for s in document_content.split('.') if s.strip()]
        
        # Score sentences based on keyword matching
        query_words = set(query.lower().split())
        scored_sentences = []
        
        for sentence in sentences:
            sentence_words = set(sentence.lower().split())
            # Calculate relevance score
            matching_words = query_words.intersection(sentence_words)
            score = len(matching_words)
            
            if score > 0:
                scored_sentences.append((score, sentence))
        
        # Sort by relevance and get top results
        scored_sentences.sort(reverse=True)
        relevant_context = []
        
        for score, sentence in scored_sentences[:num_results]:
            if sentence not in relevant_context:
                relevant_context.append(sentence + ".")
        
        return "\n".join(relevant_context) if relevant_context else ""
    
    def send_message(self, session_id: str, user_message: str) -> Dict:
        """Send a message in an existing chat session"""
        
        if session_id not in self.chat_sessions:
            return {
                'error': 'Session not found. Please upload a document first.',
                'status': 'error'
            }
        
        session = self.chat_sessions[session_id]
        
        # Rate limiting check (free tier protection)
        if session['message_count'] >= 50:
            return {
                'error': 'Message limit reached for this session. Please start a new chat.',
                'status': 'limit_reached'
            }
        
        try:
            # Find relevant content from document for this specific question
            relevant_context = self.search_document_context(session['document_content'], user_message)
            
            # Build context hint for the AI to focus on relevant parts
            context_hint = ""
            if relevant_context:
                context_hint = f"\n\nRELEVANT DOCUMENT SECTIONS FOR THIS QUESTION:\n{relevant_context}\n"
            
            # IMPORTANT: Include system prompt with EVERY message to maintain document context
            # This ensures the AI always has access to the document content for accurate answers
            full_message = f"{session['system_prompt']}{context_hint}\n\n=== User Question ===\n{user_message}"
            
            # Debug logging
            _log.debug("Sending message for session %s (count=%d, len=%d)",
                       session_id, session['message_count'], len(full_message))
            
            # Use REST API directly with retry logic
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{
                    "parts": [{
                        "text": full_message
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.4,  # Lower temperature for more focused, consistent responses
                    "maxOutputTokens": 1000,  # Increased for more detailed responses
                    "topP": 0.85,
                    "topK": 20
                }
            }
            
            # Retry logic for network issues
            max_retries = 3
            retry_delay = 2
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    _log.debug("API request attempt %d/%d", attempt + 1, max_retries)
                    response = requests.post(
                        self.api_url, 
                        headers=headers, 
                        json=payload, 
                        timeout=30
                    )
                    
                    if response.status_code != 200:
                        error_detail = response.text
                        _log.warning("API Error %d: %s", response.status_code, error_detail[:200])
                        
                        # Check for specific API issues
                        error_lower = error_detail.lower()
                        
                        if 'quota' in error_lower or 'exhausted' in error_lower:
                            return {
                                'error': 'API quota exhausted. Please update your API key in Settings.',
                                'status': 'quota_exhausted',
                                'action': 'update_api_key'
                            }
                        elif 'invalid api key' in error_lower or 'api key not valid' in error_lower:
                            return {
                                'error': 'Invalid or expired API key. Please update it in Settings.',
                                'status': 'invalid_api_key',
                                'action': 'update_api_key'
                            }
                        elif 'rate limit' in error_lower or 'too many requests' in error_lower:
                            return {
                                'error': 'Rate limit reached. Please wait a moment and try again.',
                                'status': 'rate_limit'
                            }
                        else:
                            return {
                                'error': f'API Error ({response.status_code}): {error_detail[:200]}',
                                'status': 'api_error'
                            }
                    
                    # Success - break out of retry loop
                    break
                    
                except requests.exceptions.ConnectionError as e:
                    last_error = e
                    error_msg = str(e)
                    _log.warning("Connection error on attempt %d: %s", attempt + 1, error_msg)

                    if attempt < max_retries - 1:
                        _log.debug("Retrying in %d seconds...", retry_delay)
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        # All retries failed
                        if 'getaddrinfo failed' in error_msg or 'Failed to resolve' in error_msg:
                            return {
                                'error': 'Network connection error: Cannot reach Google AI servers. Please check your internet connection and DNS settings.',
                                'status': 'network_error',
                                'details': 'DNS resolution failed - check your internet connection'
                            }
                        else:
                            return {
                                'error': f'Network connection error: {error_msg[:200]}',
                                'status': 'network_error'
                            }
                
                except requests.exceptions.Timeout:
                    last_error = "timeout"
                    _log.warning("Timeout on attempt %d", attempt + 1)

                    if attempt < max_retries - 1:
                        _log.debug("Retrying in %d seconds...", retry_delay)
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        return {
                            'error': 'Request timed out after multiple attempts. Please try again.',
                            'status': 'timeout'
                        }
            
            # If we got here without a successful response, return the last error
            if last_error:
                return {
                    'error': f'Failed after {max_retries} attempts: {str(last_error)[:200]}',
                    'status': 'network_error'
                }
            
            result = response.json()
            
            # Extract response text from the API response
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    parts = candidate['content']['parts']
                    if len(parts) > 0 and 'text' in parts[0]:
                        response_text = parts[0]['text']
                    else:
                        raise Exception("No text in response parts")
                else:
                    raise Exception("Invalid response structure")
            else:
                raise Exception("No candidates in response")
            
            if not response_text or response_text.strip() == "":
                raise Exception("Empty response from API")
            
            # Clean and format the response for better readability
            response_text = self.clean_and_format_response(response_text)
            
            # Update message count
            session['message_count'] += 1

            _log.debug("Response received (%d chars), session count=%d",
                       len(response_text), session['message_count'])
            
            return {
                'response': response_text,
                'status': 'success',
                'message_count': session['message_count']
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            _log.error("Request error in send_message: %s", error_msg)
            return {
                'error': f'Network error. Please check your internet connection.',
                'status': 'network_error'
            }
        except Exception as e:
            error_msg = str(e)
            _log.error("Error in send_message: %s", error_msg)
            
            # Handle common API errors
            if 'quota' in error_msg.lower() or 'rate' in error_msg.lower():
                return {
                    'error': 'API rate limit reached. Please try again in a few moments.',
                    'status': 'rate_limit'
                }
            elif 'api_key' in error_msg.lower() or 'invalid' in error_msg.lower():
                return {
                    'error': 'API key issue. Please check your API key configuration.',
                    'status': 'api_error'
                }
            else:
                return {
                    'error': f'API Error: {error_msg}',
                    'status': 'error'
                }
    
    def get_suggested_questions(self, document_content: str, filename: str) -> List[str]:
        """Generate intelligent suggested questions based on actual document content"""
        
        content_lower = document_content.lower()
        suggestions = []
        
        # Extract key terms and concepts from the document to create relevant questions
        # Database/SQL related keywords
        if any(term in content_lower for term in ['normalization', 'normal form', '1nf', '2nf', '3nf', 'bcnf', 'primary key', 'foreign key']):
            suggestions.append("What are the different database normalization forms?")
            if '2nf' in content_lower:
                suggestions.append("What is 2NF (Second Normal Form) and its definition?")
            if '3nf' in content_lower:
                suggestions.append("Explain 3NF (Third Normal Form)")
        
        # Programming/Technical concepts
        if any(term in content_lower for term in ['function', 'class', 'variable', 'method', 'algorithm', 'data structure']):
            suggestions.append("What are the key technical concepts explained?")
            suggestions.append("Can you explain the main algorithms or functions?")
        
        # Document structure/sections
        if any(term in content_lower for term in ['chapter', 'section', 'introduction', 'conclusion']):
            suggestions.append("What is the main topic of this document?")
            suggestions.append("Can you summarize the key sections?")
        
        # Definitions
        if any(term in content_lower for term in ['is defined as', 'definition', 'refers to', 'means', 'called']):
            suggestions.append("What are the key definitions in this document?")
        
        # Examples
        if any(term in content_lower for term in ['example', 'for example', 'e.g.', 'such as', 'demonstrate']):
            suggestions.append("What examples are provided in the document?")
        
        # Requirements/Features
        if any(term in content_lower for term in ['requirement', 'feature', 'property', 'attribute', 'characteristic']):
            suggestions.append("What are the main features or requirements?")
        
        # Problems/Solutions
        if any(term in content_lower for term in ['problem', 'solution', 'issue', 'approach', 'method']):
            suggestions.append("What problems are addressed and how?")
        
        # Extract specific terms that appear frequently (potential key concepts)
        words = content_lower.split()
        word_freq = {}
        for word in words:
            clean_word = word.strip('.,;:!?()[]{}').lower()
            if len(clean_word) > 5 and clean_word not in ['document', 'content', 'section', 'information']:
                word_freq[clean_word] = word_freq.get(clean_word, 0) + 1
        
        # Get top frequent technical terms
        top_terms = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        for term, freq in top_terms:
            if freq > 2:  # Only if appears multiple times
                suggestions.append(f"Explain {term} in this document")
        
        # Add generic fallback questions if not enough specific ones
        if len(suggestions) < 3:
            suggestions.extend([
                "What is the main topic of this document?",
                "Can you summarize the key points?",
                "What are the important definitions or concepts?",
            ])
        
        # Remove duplicates and return first 6
        return list(dict.fromkeys(suggestions))[:6]
    
    def end_session(self, session_id: str) -> bool:
        """End a chat session and free up resources"""
        if session_id in self.chat_sessions:
            del self.chat_sessions[session_id]
            return True
        return False
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Get information about an active session"""
        if session_id in self.chat_sessions:
            session = self.chat_sessions[session_id]
            return {
                'filename': session['filename'],
                'message_count': session['message_count'],
                'status': 'active'
            }
        return None

    def generate_flashcards(self, document_content: str, num_cards: int = 15) -> Dict:
        """Generate study flashcards from document content using Gemini API"""
        _log.debug("Generating %d flashcards (%d chars)", num_cards, len(document_content))

        # Truncate content to avoid API limits on free tier if necessary
        max_chars = 30000 
        content_to_use = document_content[:max_chars] if len(document_content) > max_chars else document_content

        system_prompt = f"""You are an expert tutor and educational content creator. Your task is to analyze the following document and generate highly effective study flashcards.

=== DOCUMENT CONTENT ===
{content_to_use}
=== END OF DOCUMENT ===

Create exactly {num_cards} flashcards based on the most important concepts, definitions, formulas, or facts in the document.

You MUST follow these strict formatting rules:
1. Output ONLY a valid JSON array of objects.
2. Do NOT wrap the JSON in markdown formatting blocks (like ```json), just output the raw JSON.
3. Every object in the array must have exactly two keys: "front" and "back".
4. The "front" should be a clear, concise question, term, or concept.
5. The "back" should be the precise answer or definition.
6. Keep both sides relatively short so they fit well on a flashcard (1-3 sentences max for the back).

Example format:
[
  {{
    "front": "What is Third Normal Form (3NF)?",
    "back": "A database schema in 2NF where all non-prime attributes are non-transitively dependent on the primary key."
  }},
  {{
    "front": "List the four pillars of OOP.",
    "back": "Encapsulation, Abstraction, Inheritance, and Polymorphism."
  }}
]
"""
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [{
                    "text": system_prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 8192,  # Increased - 2000 was too low and truncated JSON
            }
        }
        
        try:
            _log.debug("Sending request to Gemini for flashcards...")
            response = requests.post(
                self.api_url, 
                headers=headers, 
                json=payload, 
                timeout=45
            )
            
            if response.status_code != 200:
                _log.warning("Flashcard API Error %d: %s", response.status_code, response.text[:200])
                return {
                    'error': f'API Error: {response.status_code}. Please check API quota or try again.',
                    'status': 'error',
                    'flashcards': []
                }
            
            result = response.json()
            
            # Extract response text
            if 'candidates' in result and len(result['candidates']) > 0:
                response_text = result['candidates'][0]['content']['parts'][0]['text']

                _log.debug("Flashcard raw response: %d chars", len(response_text))

                # Try to find a complete JSON array in the response
                # Use a more robust approach: find the first '[' and last ']'
                start_idx = response_text.find('[')
                end_idx   = response_text.rfind(']')
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx + 1]
                    try:
                        flashcards = json.loads(json_str)
                        
                        # Validate structure
                        valid_cards = []
                        for card in flashcards:
                            if isinstance(card, dict) and 'front' in card and 'back' in card:
                                valid_cards.append({
                                    'front': str(card['front']).strip(),
                                    'back':  str(card['back']).strip()
                                })
                                
                        if not valid_cards:
                            raise ValueError("JSON parsed but no valid flashcards found.")

                        _log.debug("Parsed %d valid flashcards", len(valid_cards))
                        return {
                            'status': 'success',
                            'flashcards': valid_cards
                        }
                    except (json.JSONDecodeError, ValueError) as parse_err:
                        _log.warning("Flashcard JSON parse failed: %s", parse_err)

                        # Try to salvage partial JSON - extract complete objects
                        try:
                            partial_cards = []
                            obj_pattern = re.compile(r'\{\s*"front"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"back"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}', re.DOTALL)
                            for m in obj_pattern.finditer(response_text):
                                partial_cards.append({
                                    'front': m.group(1).strip(),
                                    'back':  m.group(2).strip()
                                })

                            if partial_cards:
                                _log.debug("Salvaged %d cards from partial JSON", len(partial_cards))
                                return {'status': 'success', 'flashcards': partial_cards}
                        except Exception:
                            pass
                        
                        return {
                            'error': 'The AI response was cut off. Please try with fewer flashcards.',
                            'status': 'error',
                            'flashcards': []
                        }
                else:
                    # No JSON brackets at all - try salvaging individual objects
                    try:
                        partial_cards = []
                        obj_pattern = re.compile(r'\{\s*"front"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"back"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}', re.DOTALL)
                        for m in obj_pattern.finditer(response_text):
                            partial_cards.append({
                                'front': m.group(1).strip(),
                                'back':  m.group(2).strip()
                            })
                        
                        if partial_cards:
                            _log.debug("Salvaged %d cards without brackets", len(partial_cards))
                            return {'status': 'success', 'flashcards': partial_cards}
                    except Exception:
                        pass

                    safe_response = response_text.replace('"', "'").replace('\n', ' ').strip()[:150]
                    return {
                        'error': f'AI could not generate flashcards. Response: "{safe_response}..."',
                        'status': 'error',
                        'flashcards': []
                    }
            else:
                return {
                    'error': 'No response generated by AI.',
                    'status': 'error',
                    'flashcards': []
                }
                
        except Exception as e:
            _log.error("Error generating flashcards: %s", e)
            return {
                'error': 'Error generating flashcards. Please try again.',
                'status': 'error',
                'flashcards': []
            }


    def generate_questions(self, document_content: str, num_questions: int = 10, q_type: str = 'mixed') -> dict:
        """Generate exam-style questions from document content using Gemini API"""
        _log.debug("Generating %d questions of type %s", num_questions, q_type)

        max_chars = 30000
        content_to_use = document_content[:max_chars] if len(document_content) > max_chars else document_content

        type_instructions = {
            'mcq': "Generate ONLY multiple-choice questions. Each must have exactly 4 options (A, B, C, D) and one correct answer.",
            'short': "Generate ONLY short-answer questions that require a 1-3 sentence answer.",
            'truefalse': "Generate ONLY True/False questions.",
            'mixed': "Generate a mix: roughly half MCQ (with 4 options A-D), and half short-answer questions."
        }

        system_prompt = f"""You are an expert educator. Analyze the document below and generate {num_questions} exam-style questions.

=== DOCUMENT CONTENT ===
{content_to_use}
=== END OF DOCUMENT ===

{type_instructions.get(q_type, type_instructions['mixed'])}

Output ONLY a valid JSON array. No markdown, no explanation, just raw JSON.

Each object MUST have:
- "type": either "mcq", "short", or "truefalse"
- "question": the question text
- "answer": the correct answer
- "options": array of 4 strings for MCQ (e.g. ["A. ...", "B. ...", "C. ...", "D. ..."]), or null for other types
- "explanation": a brief 1-sentence explanation of why the answer is correct

Example:
[
  {{
    "type": "mcq",
    "question": "What does 2NF require?",
    "options": ["A. Atomic values only", "B. No partial dependencies", "C. No transitive dependencies", "D. A composite key"],
    "answer": "B. No partial dependencies",
    "explanation": "2NF eliminates partial dependencies on a composite primary key."
  }},
  {{
    "type": "short",
    "question": "Explain what a transitive dependency is.",
    "options": null,
    "answer": "A transitive dependency occurs when a non-key attribute depends on another non-key attribute rather than directly on the primary key.",
    "explanation": "This is the core concept that 3NF aims to eliminate."
  }},
  {{
    "type": "truefalse",
    "question": "A relation in 3NF is always in 2NF.",
    "options": null,
    "answer": "True",
    "explanation": "3NF is a stricter form that builds upon 2NF requirements."
  }}
]
"""
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{"parts": [{"text": system_prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192}
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=45)

            if response.status_code != 200:
                return {'status': 'error', 'error': f'API Error {response.status_code}. Check quota.', 'questions': []}

            result = response.json()
            if 'candidates' not in result or not result['candidates']:
                return {'status': 'error', 'error': 'No response from AI.', 'questions': []}

            response_text = result['candidates'][0]['content']['parts'][0]['text']
            _log.debug("Questions response: %d chars", len(response_text))

            # Robust JSON extraction
            start_idx = response_text.find('[')
            end_idx   = response_text.rfind(']')

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                try:
                    questions = json.loads(response_text[start_idx:end_idx + 1])
                    valid = [q for q in questions if isinstance(q, dict) and 'question' in q and 'answer' in q]
                    if valid:
                        _log.debug("Parsed %d questions", len(valid))
                        return {'status': 'success', 'questions': valid}
                except json.JSONDecodeError:
                    pass

            # Fallback: salvage individual objects
            obj_pattern = re.compile(
                r'\{\s*"type"\s*:\s*"([^"]+)"\s*,\s*"question"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,'
                r'\s*"options"\s*:\s*(\[.*?\]|null)\s*,\s*"answer"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,'
                r'\s*"explanation"\s*:\s*"((?:[^"\\]|\\.]*))"',
                re.DOTALL
            )
            salvaged = []
            for m in obj_pattern.finditer(response_text):
                try:
                    opts = json.loads(m.group(3)) if m.group(3) != 'null' else None
                    salvaged.append({'type': m.group(1), 'question': m.group(2), 'options': opts,
                                     'answer': m.group(4), 'explanation': m.group(5)})
                except Exception:
                    pass

            if salvaged:
                return {'status': 'success', 'questions': salvaged}

            return {'status': 'error', 'error': 'Could not parse questions from AI response. Try fewer questions.', 'questions': []}

        except Exception as e:
            _log.error("Error generating questions: %s", e)
            return {'status': 'error', 'error': 'Error generating questions. Please try again.', 'questions': []}


# Global chat manager instance (will be initialized with API key)
chat_manager = None

def initialize_chat_manager(api_key: str):
    """Initialize the global chat manager with API key"""
    global chat_manager
    chat_manager = DocumentChatManager(api_key)
    _log.info("Chat manager initialised with REST API")
    return chat_manager

def get_chat_manager() -> Optional[DocumentChatManager]:
    """Get the global chat manager instance"""
    return chat_manager

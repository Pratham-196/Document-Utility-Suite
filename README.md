# Document Utility Suite

A powerful, self-hosted web application built with **Flask** that provides 60+ tools for processing PDFs and images — including AI-powered features via Google Gemini.

---

## Features

### PDF Tools
- Merge, split, compress, rotate, reverse PDFs
- Convert PDF ↔ Word, PDF ↔ Image, PDF ↔ PPT, PDF ↔ CSV, PDF ↔ Text
- Convert Excel, Markdown, PowerPoint, URL → PDF
- Protect, unlock, watermark, sign PDFs
- Crop, flatten, normalize, repair PDFs
- Redact sensitive content from PDFs
- Edit PDF metadata and fonts
- Add page numbers, extract pages, remove pages
- Compare two PDFs side by side
- OCR — extract text from scanned PDFs

### Image Tools
- Compress, resize, crop, flip images
- Convert between image formats
- Remove background from images
- Upscale images (AI-powered)
- Apply filters, add borders, add text
- Create image collages
- Convert image → ASCII art, Base64
- Extract colour palette from images
- View and edit EXIF metadata
- Generate QR codes

### AI-Powered Tools (requires Gemini API key)
- Summarize PDF content
- Translate PDFs to other languages
- Chat with a document
- Compare documents with AI
- Generate flashcards from a document
- Generate comprehension questions
- Rewrite document content
- Analyse document tone
- Create a document brief
- Invoice intelligence
- Resume intelligence
- OCR correction

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.8+, Flask |
| PDF Processing | PyMuPDF, pypdf, pdf2docx, pdfplumber, ReportLab |
| Image Processing | Pillow, OpenCV, rembg, NumPy |
| OCR | Tesseract (pytesseract) |
| AI | Google Gemini API (via REST), Groq (optional fallback) |
| Conversion | python-docx, python-pptx, openpyxl, pandas |
| Translation | deep-translator (no API key needed) |
| Summarization | sumy + NLTK (fully offline) |
| QR Code | qrcode[pil] |
| Environment | python-dotenv |

---

## Getting Started

### Prerequisites

- Python 3.8 or higher
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed on your system
- A Google Gemini API key (free tier available at [aistudio.google.com](https://aistudio.google.com/app/apikey)) — required only for AI features

### 1. Clone the repository

```bash
git clone https://github.com/kubermahajan7-blip/Document-Utility-Suite.git
cd everything-pdf-image
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
# Generate a secure key with:
# python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-random-secret-key

# Get from https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your-gemini-api-key-here

# Optional — Groq fallback
GROQ_API_KEY=your-groq-api-key-here
```

> **Never commit your `.env` file.** It is already listed in `.gitignore`.

### 5. Run the application

```bash
python app.py
```

Open your browser at `http://localhost:5000`

---

## Project Structure

```
everything-pdf-image/
├── app.py                   # Main Flask application & all routes
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── .gitignore
├── README.md
│
├── utils/                   # Backend utility modules
│   ├── pdf_utils.py         # Core PDF operations
│   ├── image_utils.py       # Core image operations
│   ├── ai_tools.py          # Gemini AI integrations
│   ├── ocr_utils.py         # OCR (Tesseract)
│   ├── chat_utils.py        # Document chat logic
│   ├── conversion_utils.py  # URL/Markdown/Excel/PPT → PDF
│   ├── summary_utils.py     # Offline summarization
│   ├── translate_utils.py   # Translation
│   ├── redaction_utils.py   # PDF redaction
│   ├── metadata_utils.py    # PDF metadata editing
│   ├── advanced_tools.py    # Collage, ASCII, borders, compare
│   ├── extraction_utils.py  # Content extraction helpers
│   ├── api_key_manager.py   # Dynamic API key management
│   ├── file_manager.py      # Upload lifecycle management
│   ├── cache_manager.py     # Preview caching
│   ├── qr_utils.py          # QR code generation
│   └── logger.py            # Logging setup
│
├── templates/               # Jinja2 HTML templates (one per tool)
│   ├── base.html
│   ├── index.html
│   └── *.html
│
├── static/
│   ├── css/                 # Stylesheets
│   ├── js/                  # Frontend JavaScript
│   └── fonts/               # Bundled TTF fonts for PDF generation
│
├── config/                  # Runtime config (gitkeep'd; not committed)
│   └── .gitkeep
│
└── tests/
    ├── test_api_key_manager.py
    └── test_chat.py
```

---

## Configuration

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session secret key. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GEMINI_API_KEY` | For AI features | Google Gemini API key |
| `GROQ_API_KEY` | No | Optional Groq API fallback key |

If `SECRET_KEY` is missing or left as the placeholder value, the app auto-generates a random key each session (sessions will not persist across restarts).

---

## Tesseract OCR Setup

Tesseract must be installed separately on your OS before OCR features will work.

**Windows:** Download the installer from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) and add Tesseract to your `PATH`.

**macOS:**
```bash
brew install tesseract
```

**Ubuntu / Debian:**
```bash
sudo apt install tesseract-ocr
```

---

## Upload Limits

- Maximum file size: **100 MB** per upload
- Uploaded files are stored temporarily in `static/uploads/` and cleaned up automatically

---

## Running Tests

```bash
python -m pytest tests/
```

---

## Deployment Notes

For production deployment:

- Set a strong, random `SECRET_KEY` in your environment
- Use a WSGI server such as **Gunicorn**: `gunicorn -w 4 app:app`
- Put a reverse proxy (Nginx, Caddy) in front of Gunicorn
- Set `MAX_CONTENT_LENGTH` appropriately for your server capacity
- Ensure Tesseract is installed on the server for OCR features

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push to the branch: `git push origin feature/your-feature-name`
5. Open a Pull Request

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Acknowledgements

- [PyMuPDF](https://pymupdf.readthedocs.io/) — fast PDF rendering and manipulation
- [pdf2docx](https://github.com/dothinking/pdf2docx) — PDF to Word conversion
- [rembg](https://github.com/danielgatis/rembg) — AI background removal
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — open source OCR engine
- [Google Gemini](https://ai.google.dev/) — generative AI features
- [deep-translator](https://github.com/nidhaloff/deep-translator) — free translation

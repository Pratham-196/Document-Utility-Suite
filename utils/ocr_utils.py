import os
from utils.logger import get_logger
_log = get_logger(__name__)
import pytesseract
from PIL import Image
import io
import fitz  # PyMuPDF

# ─────────────────────────────────────────────
# Tesseract setup
# ─────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

possible_tesseract_paths = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Tesseract-OCR', 'tesseract.exe'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Tesseract-OCR', 'tesseract.exe'),
    r"C:\Tesseract-OCR\tesseract.exe",
]

# Verify Tesseract is working
tesseract_found = False
try:
    pytesseract.get_tesseract_version()
    tesseract_found = True
    _log.debug(f"✓ Tesseract OCR ready: {pytesseract.pytesseract.tesseract_cmd}")
except pytesseract.TesseractNotFoundError:
    _log.debug("Tesseract not in PATH, searching common installation locations...")
    for path in possible_tesseract_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            # Also add that directory to PATH for DLL resolution
            tess_dir = os.path.dirname(path)
            if tess_dir not in os.environ.get('PATH', ''):
                os.environ['PATH'] = tess_dir + os.pathsep + os.environ.get('PATH', '')
            try:
                pytesseract.get_tesseract_version()
                tesseract_found = True
                _log.debug(f"✓ Tesseract OCR found at: {path}")
                break
            except Exception:
                continue

    if not tesseract_found:
        _log.debug("WARNING: Tesseract OCR not found!")
        _log.debug("Please install Tesseract OCR from: https://github.com/UB-Mannheim/tesseract/wiki")
        _log.debug("Or download from: https://digi.bib.uni-mannheim.de/tesseract/")

def extract_text_from_image(image_path):
    """
    Extract text from an image file using Tesseract OCR.
    """
    try:
        # Verify Tesseract is available
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError as e:
            error_msg = """
ERROR: Tesseract OCR is not installed or not found in PATH.

To fix this issue:
1. Download Tesseract OCR installer from:
   https://github.com/UB-Mannheim/tesseract/wiki
   
2. Install Tesseract OCR (recommended path: C:\\Program Files\\Tesseract-OCR)

3. Restart the application

Alternative download link:
https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.3.20231005.exe

After installation, the OCR feature will work automatically.
"""
            _log.debug(f"Tesseract not found. Error: {e}")
            return error_msg.strip()
        
        image = Image.open(image_path)
        
        # Convert to RGB if needed
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        
        # Perform OCR with better configuration
        custom_config = r'--oem 3 --psm 3'  # Use LSTM OCR Engine and automatic page segmentation
        text = pytesseract.image_to_string(image, config=custom_config)
        
        if not text or not text.strip():
            return "No text detected in the image. The image might be too low quality or contain no readable text."
        
        return text
    except pytesseract.TesseractNotFoundError:
        return "ERROR: Tesseract OCR is not installed. Please install it from https://github.com/UB-Mannheim/tesseract/wiki"
    except Exception as e:
        _log.debug(f"Error extracting text from image: {e}")
        import traceback
        traceback.print_exc()
        return f"Error extracting text: {str(e)}"

def extract_text_from_pdf(pdf_path):
    """
    Extract text from a PDF file.
    First tries to extract embedded text.
    If text is sparse, falls back to OCR using PyMuPDF to render pages.
    """
    try:
        # Verify Tesseract is available for OCR fallback
        tesseract_available = False
        try:
            pytesseract.get_tesseract_version()
            tesseract_available = True
        except pytesseract.TesseractNotFoundError:
            _log.debug("Warning: Tesseract not found. OCR fallback will not be available.")
        
        doc = fitz.open(pdf_path)
        full_text = ""
        ocr_needed_pages = []
        
        for i, page in enumerate(doc):
            # Try to extract text directly first
            text = page.get_text()
            
            # If page has very little text, it might be a scan, use OCR
            if len(text.strip()) < 10:
                if tesseract_available:
                    try:
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        img_data = pix.tobytes("png")
                        image = Image.open(io.BytesIO(img_data))
                        
                        # Convert to RGB if needed
                        if image.mode not in ('RGB', 'L'):
                            image = image.convert('RGB')
                        
                        custom_config = r'--oem 3 --psm 3'
                        text = pytesseract.image_to_string(image, config=custom_config)
                        ocr_needed_pages.append(i + 1)
                    except Exception as ocr_error:
                        _log.debug(f"OCR failed for page {i+1}: {ocr_error}")
                        text = f"[OCR failed for this page: {str(ocr_error)}]"
                else:
                    ocr_needed_pages.append(i + 1)
                    text = "[This page appears to be scanned but Tesseract OCR is not available]"
            
            full_text += f"\n--- Page {i+1} ---\n\n"
            full_text += text
        
        doc.close()
        
        # Add helpful message if OCR was needed but not available
        if ocr_needed_pages and not tesseract_available:
            ocr_msg = f"""
NOTE: Pages {', '.join(map(str, ocr_needed_pages))} appear to be scanned images.
To extract text from scanned pages, please install Tesseract OCR:
https://github.com/UB-Mannheim/tesseract/wiki

After installation, restart the application and try again.
"""
            full_text = ocr_msg.strip() + "\n\n" + full_text
        
        if not full_text.strip() or full_text.strip() == "":
            return "No text could be extracted from the PDF. The document might be empty or contain only images."
        
        return full_text
    except Exception as e:
        _log.debug(f"Error extracting text from PDF: {e}")
        import traceback
        traceback.print_exc()
        return f"Error extracting text: {str(e)}"

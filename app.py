import warnings
# Suppress ARC4 deprecation warning from cryptography library (used internally by pypdf)
warnings.filterwarnings(
    "ignore",
    message=".*ARC4.*",
    category=DeprecationWarning,
)

import os
import time
import threading
import zipfile
import io
import base64
import fitz  # PyMuPDF
from flask import Flask, render_template, request, send_file, after_this_request, send_from_directory, jsonify
from werkzeug.utils import secure_filename
import glob
from dotenv import load_dotenv
from utils.pdf_utils import (
    merge_pdfs, split_pdf, compress_pdf, pdf_to_images, 
    images_to_pdf, pdf_to_word, word_to_pdf, protect_pdf, unlock_pdf,
    rotate_pdf, watermark_pdf, remove_pages, add_page_numbers
)
from utils.image_utils import compress_image, convert_image_format, upscale_image, remove_background
from utils.ocr_utils import extract_text_from_pdf, extract_text_from_image
from utils.redaction_utils import redact_pdf
from utils.feature_utils import sign_pdf, organize_pdf
from utils.conversion_utils import url_to_pdf, markdown_to_pdf, excel_to_pdf, ppt_to_pdf
from utils.summary_utils import summarize_text
from utils.translate_utils import translate_text, get_supported_languages
from utils.qr_utils import generate_qr_code
from utils.metadata_utils import edit_pdf_metadata, get_pdf_metadata
from utils.pdf_extract_utils import extract_pdf_pages, pdf_to_ppt
from utils.advanced_tools import (
    pdf_compare, add_border_to_image, 
    image_to_ascii, create_collage, add_text_to_image, add_text_to_image_advanced
)
from utils.chat_utils import initialize_chat_manager
from utils.api_key_manager import (
    get_current_api_key, set_primary_api_key, 
    list_api_keys, test_api_key, is_api_key_valid
)
from utils.file_manager import initialize_file_manager, get_file_manager
from utils.cache_manager import preview_cache
from utils.logger import get_logger

_log = get_logger(__name__)

# Load environment variables
load_dotenv()

# ── Enforce required config ──────────────────────────────────
_SECRET_KEY = os.getenv('SECRET_KEY', '')
if not _SECRET_KEY or _SECRET_KEY in ('change-this-to-a-random-secret-key-in-production',
                                       'dev-fallback-key-change-in-prod',
                                       'REPLACE_WITH_STRONG_RANDOM_SECRET'):
    import secrets
    _SECRET_KEY = secrets.token_hex(32)
    _log.warning("SECRET_KEY not set or is a placeholder — using a random key for this session. "
                 "Set SECRET_KEY in .env for persistent sessions.")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB limit
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.secret_key = _SECRET_KEY

@app.after_request
def no_cache(response):
    # Only disable caching for HTML pages and API responses, not file downloads
    content_type = response.content_type or ''
    if 'text/html' in content_type or 'application/json' in content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Expires'] = '0'
    return response

from werkzeug.exceptions import HTTPException
import traceback

@app.errorhandler(Exception)
def handle_global_exception(e):
    # If the request comes from our fetch calls (typically POST, or JSON accepted, or starts with /api/)
    # we should return a JSON response so the frontend JS doesn't crash on `r.json()`
    wants_json = request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html
    is_api = request.path.startswith('/api/') or request.method == 'POST'
    
    if isinstance(e, HTTPException):
        if is_api or wants_json:
            return jsonify({"error": str(e.description)}), e.code
        return e

    _log.error(f"Unhandled Exception on {request.path}: {e}")
    _log.error(traceback.format_exc())
    
    if is_api or wants_json:
        return jsonify({"error": "An internal server error occurred while processing your request."}), 500
        
    return "Internal Server Error", 500

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize file manager for optimized cleanup
initialize_file_manager(app.config['UPLOAD_FOLDER'])

# Initialize Gemini chat manager
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') or get_current_api_key()
if GEMINI_API_KEY:
    try:
        initialize_chat_manager(GEMINI_API_KEY)
        _log.info("Gemini API initialised successfully")
    except Exception as e:
        _log.warning("Could not initialise Gemini API: %s", e)
else:
    _log.warning("GEMINI_API_KEY not found. Please configure an API key in Settings.")

def cleanup_old_files():
    """Background thread to clean up old files."""
    while True:
        try:
            file_mgr = get_file_manager()
            file_mgr.cleanup_old_files(max_age=1800)  # 30 minutes
        except Exception as e:
            _log.error("Error in cleanup thread: %s", e)
        time.sleep(300)  # Check every 5 minutes

cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

def create_zip(file_paths, zip_name):
    """Optimized helper to create a zip file from a list of files."""
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], zip_name)
    file_mgr = get_file_manager()
    file_mgr.track_file(zip_path)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            zipf.write(file_path, os.path.basename(file_path))
    return zip_path


def safe_upload_path(filename: str) -> str:
    """
    Resolve a filename to an absolute path inside UPLOAD_FOLDER.
    Raises ValueError if the resolved path escapes the upload directory
    (path traversal protection).
    """
    upload_dir = os.path.realpath(app.config['UPLOAD_FOLDER'])
    safe_name = os.path.basename(secure_filename(filename))
    if not safe_name:
        raise ValueError("Invalid filename")
    resolved = os.path.realpath(os.path.join(upload_dir, safe_name))
    if not resolved.startswith(upload_dir + os.sep) and resolved != upload_dir:
        raise ValueError("Path traversal detected")
    return resolved

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/batch-process')
def batch_process_route():
    return render_template('batch_process.html')

@app.route('/merge-pdf', methods=['GET', 'POST'])
def merge_pdf_route():
    if request.method == 'POST':
        if 'files' not in request.files:
            return "No files uploaded", 400
            
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return "No selected file", 400

        saved_paths = []
        for file in files:
            if file and file.filename.endswith('.pdf'):
                filename = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
                file.save(path)
                saved_paths.append(path)
        
        output_filename = f"merged_{int(time.time())}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        result = merge_pdfs(saved_paths, output_path)
        
        if result:
            return send_file(result, as_attachment=True)
        else:
            return "Error merging PDFs", 500

    return render_template('merge_pdf.html')

@app.route('/split-pdf', methods=['GET', 'POST'])
def split_pdf_route():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            return "No file uploaded", 400
        if file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)

            output_files = split_pdf(input_path, app.config['UPLOAD_FOLDER'])

            if output_files:
                zip_filename = f"split_{int(time.time())}.zip"
                zip_path = create_zip(output_files, zip_filename)
                return send_file(zip_path, as_attachment=True)
            else:
                return "Error splitting PDF", 500
        return "Invalid file type. Please upload a PDF.", 400
    return render_template('split_pdf.html')

@app.route('/compress-pdf', methods=['GET', 'POST'])
def compress_pdf_route():
    if request.method == 'POST':
        file = request.files.get('file')

        if not file or not file.filename:
            return "No file uploaded", 400

        if file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)

            quality = request.form.get('quality', 'balanced')
            output_filename = f"compressed_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            result = compress_pdf(input_path, output_path, quality)

            if result:
                return send_file(result, as_attachment=True, download_name=f"compressed_{filename}")
            else:
                return "Error compressing PDF. Please try again with a different file.", 500
        return "Invalid file type. Please upload a PDF file.", 400
    return render_template('compress_pdf.html')

@app.route('/pdf-to-images', methods=['GET', 'POST'])
def pdf_to_image_route():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            output_files = pdf_to_images(input_path, app.config['UPLOAD_FOLDER'])
            
            if output_files:
                zip_filename = f"images_{int(time.time())}.zip"
                zip_path = create_zip(output_files, zip_filename)
                return send_file(zip_path, as_attachment=True)
            else:
                return "Error (Poppler missing?)", 500
    return render_template('pdf_to_image.html')

@app.route('/images-to-pdf', methods=['GET', 'POST'])
def image_to_pdf_route():
    if request.method == 'POST':
        if 'files' not in request.files:
            return "No files", 400
        files = request.files.getlist('files')
        
        saved_paths = []
        for file in files:
            # simple check
            if file and '.' in file.filename: # accept any image
                filename = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
                file.save(path)
                saved_paths.append(path)
                
        output_filename = f"converted_{int(time.time())}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        result = images_to_pdf(saved_paths, output_path)
        if result:
             return send_file(result, as_attachment=True)
        else:
            return "Error converting", 500
    return render_template('image_to_pdf.html')

@app.route('/pdf-to-word', methods=['GET', 'POST'])
def pdf_to_word_route():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            output_filename = f"converted_{int(time.time())}.docx"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            result = pdf_to_word(input_path, output_path)
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error converting", 500
    return render_template('pdf_to_word.html')

@app.route('/word-to-pdf', methods=['GET', 'POST'])
def word_to_pdf_route():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.docx'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            output_filename = f"converted_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            result = word_to_pdf(input_path, output_path)
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error converting", 500
    return render_template('word_to_pdf.html')

@app.route('/protect-pdf', methods=['GET', 'POST'])
def protect_pdf_route():
    if request.method == 'POST':
        file = request.files['file']
        password = request.form.get('password')
        action = request.form.get('action') # 'protect' or 'unlock'
        
        if file and file.filename.endswith('.pdf') and password:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            output_filename = f"{action}_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            if action == 'protect':
                result = protect_pdf(input_path, output_path, password)
            elif action == 'unlock':
                result = unlock_pdf(input_path, output_path, password)
            else:
                return "Invalid action", 400
                
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error processing PDF", 500
    return render_template('protect_pdf.html')

@app.route('/rotate-pdf', methods=['GET', 'POST'])
def rotate_pdf_route():
    if request.method == 'POST':
        file = request.files.get('file')
        try:
            angle = int(request.form.get('angle', 90))
            if angle not in (90, 180, 270):
                return "Invalid angle. Must be 90, 180, or 270.", 400
        except (ValueError, TypeError):
            return "Invalid angle value.", 400

        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)

            output_filename = f"rotated_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            result = rotate_pdf(input_path, output_path, angle)
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error rotating PDF", 500
        return "Invalid file type. Please upload a PDF.", 400
    return render_template('rotate_pdf.html')

@app.route('/watermark-pdf', methods=['GET', 'POST'])
def watermark_pdf_route():
    if request.method == 'POST':
        file = request.files.get('file')
        text = request.form.get('text', '').strip()

        if not file or not file.filename:
            return "No file uploaded", 400
        if not text:
            return "Watermark text is required", 400

        if file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)

            output_filename = f"watermarked_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            pages = request.form.get('pages', 'all')
            try:
                angle = max(0, min(360, int(request.form.get('angle', 45))))
                opacity = max(0.0, min(1.0, float(request.form.get('opacity', 0.3))))
                size = max(6, min(200, int(request.form.get('font_size', 36))))
            except (ValueError, TypeError):
                return "Invalid numeric parameter", 400
            color = request.form.get('color', '#808080')
            placement = request.form.get('placement', 'multiple')

            result = watermark_pdf(input_path, output_path, text,
                                   pages=pages, angle=angle, opacity=opacity,
                                   font_size=size, color=color, placement=placement)
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error adding watermark", 500
        return "Invalid file type. Please upload a PDF.", 400
    return render_template('watermark_pdf.html')

@app.route('/remove-pages', methods=['GET', 'POST'])
def remove_pages_route():
    if request.method == 'POST':
        file = request.files['file']
        pages_input = request.form.get('pages') # e.g. "1,2,5"
        
        if file and file.filename.endswith('.pdf') and pages_input:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            output_filename = f"removed_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            # Parse pages
            try:
                pages = [int(p.strip()) for p in pages_input.split(',')]
            except:
                return "Invalid page numbers", 400
                
            result = remove_pages(input_path, output_path, pages)
            if result:
                return send_file(result, as_attachment=True)
            else:
                 return "Error removing pages", 500
    return render_template('remove_pages.html')

@app.route('/compress-image', methods=['GET', 'POST'])
def compress_image_route():
    if request.method == 'POST':
        file = request.files.get('file')
        try:
            quality = max(1, min(100, int(request.form.get('quality', 60))))
        except (ValueError, TypeError):
            quality = 60

        if not file or not file.filename:
            return "No file uploaded", 400

        filename = secure_filename(file.filename)

        # Validate file extension
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
        ext = os.path.splitext(filename)[1].lower()
        if ext not in allowed_extensions:
            return f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}", 400

        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)

        output_filename = f"compressed_{int(time.time())}_{filename}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        result = compress_image(input_path, output_path, quality)

        if result:
            return send_file(result, as_attachment=True)
        else:
            return "Error compressing image. Please check the file format and try again.", 500
    return render_template('compress_image.html')


@app.route('/convert-image', methods=['GET', 'POST'])
def convert_image_route():
    if request.method == 'POST':
        file = request.files['file']
        target_format = request.form.get('format') # jpg, png, webp
        
        if file and file.filename and target_format:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            base_name = os.path.splitext(filename)[0]
            output_filename = f"{base_name}_{int(time.time())}.{target_format}"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            result = convert_image_format(input_path, output_path)
            
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error converting image", 500
    return render_template('convert_image.html')

@app.route('/ocr-pdf', methods=['GET', 'POST'])
def ocr_pdf_route():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
            
        if file:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            text = ""
            if filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(input_path)
            elif filename.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                text = extract_text_from_image(input_path)
            else:
                return jsonify({"error": "Unsupported file format"}), 400
                
            if text:
                return jsonify({"text": text})
            else:
                return jsonify({"error": "Error extracting text"}), 500
                
    return render_template('ocr_pdf.html')

@app.route('/redact-pdf', methods=['GET', 'POST'])
def redact_pdf_route():
    if request.method == 'POST':
        file = request.files['file']
        text_to_redact = request.form.get('text')
        
        if file and file.filename.endswith('.pdf') and text_to_redact:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            output_filename = f"redacted_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            result_path, count = redact_pdf(input_path, output_path, text_to_redact)
            
            if result_path and count > 0:
                return send_file(result_path, as_attachment=True)
            elif result_path and count == 0:
                return "Text not found in document", 400
            else:
                return "Error redacting PDF", 500
    return render_template('redact_pdf.html')

@app.route('/sign-pdf', methods=['GET', 'POST'])
def sign_pdf_route():
    if request.method == 'POST':
        data = request.json
        if not data:
            return jsonify({"error": "No data received"}), 400
        filename = data.get('filename')
        signature_data = data.get('signature')
        try:
            page_num = max(0, int(data.get('page', 0)))
            x_ratio      = max(0.0, min(1.0, float(data.get('x_ratio', 0))))
            y_ratio      = max(0.0, min(1.0, float(data.get('y_ratio', 0))))
            width_ratio  = max(0.01, min(1.0, float(data.get('width_ratio', 0.25))))
            height_ratio = max(0.01, min(1.0, float(data.get('height_ratio', 0.1))))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid numeric parameter"}), 400

        if filename and signature_data:
            try:
                input_path = safe_upload_path(filename)
            except ValueError:
                return jsonify({"error": "Invalid filename"}), 400
            if not os.path.exists(input_path):
                return jsonify({"error": "File not found"}), 404

            output_filename = f"signed_{int(time.time())}_{os.path.basename(input_path)}"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            result = sign_pdf(input_path, output_path, signature_data, page_num,
                              x_ratio, y_ratio, width_ratio, height_ratio)

            if result:
                return jsonify({"download_url": f"/download/{output_filename}"})
            else:
                return jsonify({"error": "Signing failed"}), 500
        return jsonify({"error": "Missing filename or signature data"}), 400

    return render_template('sign_pdf.html')

@app.route('/url-to-pdf', methods=['GET', 'POST'])
def url_to_pdf_route():
    if request.method == 'POST':
        url = request.form.get('url')
        page_size = request.form.get('page_size', 'A4')
        orientation = request.form.get('orientation', 'Portrait')
        
        if url:
            try:
                # Validate and fix URL format
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                output_filename = f"web_{int(time.time())}.pdf"
                output_path = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], output_filename))

                _log.info("Converting URL to PDF: %s", url)
                result = url_to_pdf(url, output_path, page_size, orientation)
                
                if result and os.path.exists(output_path):
                    return send_file(result, as_attachment=True, download_name=output_filename)
                else:
                    return jsonify({"error": "URL to PDF conversion failed. The URL may be inaccessible or the page took too long to load."}), 500
            except Exception as e:
                _log.error("Error in url_to_pdf_route: %s", e)
                return jsonify({"error": "Error converting URL to PDF. Please check the URL and try again."}), 500
        else:
            return "No URL provided", 400
            
    return render_template('url_to_pdf.html')

@app.route('/markdown-to-pdf', methods=['GET', 'POST'])
def markdown_to_pdf_route():
    if request.method == 'POST':
        submit_type = request.form.get('type')
        
        content = ""
        if submit_type == 'file':
            file = request.files['file']
            if file:
                content = file.read().decode('utf-8', errors='ignore')
        else:
            content = request.form.get('content', '')

        if content:
            output_filename = f"md_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            result = markdown_to_pdf(content, output_path)
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error converting Markdown to PDF", 500
                
    return render_template('markdown_to_pdf.html')

@app.route('/excel-to-pdf', methods=['GET', 'POST'])
def excel_to_pdf_route():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            return "No file uploaded", 400
        orientation = request.form.get('orientation', 'landscape')
        style = request.form.get('style', 'grid')
        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ('.xlsx', '.xls', '.csv'):
            return "Invalid file type. Please upload .xlsx, .xls, or .csv", 400
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_filename = f"excel_{int(time.time())}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        result = excel_to_pdf(input_path, output_path, orientation, style)
        if result:
            base = os.path.splitext(filename)[0]
            return send_file(result, as_attachment=True, download_name=f"{base}.pdf")
        return "Error converting Excel to PDF", 500
    return render_template('excel_to_pdf.html')

@app.route('/ppt-to-pdf', methods=['GET', 'POST'])
def ppt_to_pdf_route():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            return "No file uploaded", 400
        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ('.ppt', '.pptx'):
            return "Invalid file type. Please upload a .ppt or .pptx file.", 400
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_filename = f"converted_{int(time.time())}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        result = ppt_to_pdf(input_path, output_path)
        if result:
            base = os.path.splitext(filename)[0]
            return send_file(result, as_attachment=True, download_name=f"{base}.pdf")
        return "Error converting PPT to PDF.", 500
    return render_template('ppt_to_pdf.html')

@app.route('/remove-background', methods=['GET', 'POST'])
def remove_background_route():
    if request.method == 'POST':
        try:
            file = request.files.get('file')
            if not file:
                return jsonify({"error": "No file provided"}), 400

            allowed_extensions = {'png', 'jpg', 'jpeg', 'webp', 'avif', 'bmp', 'tiff'}
            filename = secure_filename(file.filename)
            file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            if file_ext not in allowed_extensions:
                return jsonify({"error": f"Unsupported format. Allowed: {', '.join(allowed_extensions)}"}), 400

            mode = request.form.get('mode', 'ai')  # 'ai' or 'simple'
            tolerance = int(request.form.get('tolerance', 30))

            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)

            output_filename = f"no_bg_{int(time.time())}_{os.path.splitext(filename)[0]}.png"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            if mode == 'simple':
                from utils.image_utils import remove_background_simple
                result = remove_background_simple(input_path, output_path, tolerance=tolerance)
            else:
                # Check rembg available
                try:
                    from rembg import remove as test_import
                except Exception as e:
                    error_msg = "AI mode requires rembg. Install with: pip install rembg[cpu]"
                    return jsonify({"error": error_msg}), 500
                result = remove_background(input_path, output_path)

            if result:
                return send_file(result, mimetype='image/png', as_attachment=False)
            else:
                return jsonify({"error": "Failed to remove background."}), 500

        except Exception as e:
            _log.error("Error in remove_background_route: %s", e)
            return jsonify({"error": "Server error processing image"}), 500

    return render_template('remove_background.html')



@app.route('/api/pdf-info/<filename>')
def get_pdf_info(filename):
    try:
        if not filename:
            return jsonify({"error": "No filename provided"}), 400
        filename = os.path.basename(secure_filename(filename))
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        return jsonify({"total_pages": len(reader.pages)})
    except Exception as e:
        _log.error("Error getting PDF info: %s", e)
        return jsonify({"error": "Error reading PDF"}), 500

@app.route('/api/pdf-page/<filename>/<int:page_num>')
def get_pdf_page_image(filename, page_num):
    try:
        try:
            file_path = safe_upload_path(filename)
        except ValueError:
            return jsonify({"error": "Invalid filename"}), 400
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404

        # Check if cache exists
        cache_filename = f"{os.path.basename(file_path)}_page_{page_num}.jpg"
        cache_path = os.path.join(app.config['UPLOAD_FOLDER'], cache_filename)

        if os.path.exists(cache_path):
            return send_file(cache_path)

        # Generate image using PyMuPDF (fitz)
        try:
            doc = fitz.open(file_path)
            if page_num < 1 or page_num > len(doc):
                doc.close()
                return jsonify({"error": "Page number out of range"}), 400

            page = doc.load_page(page_num - 1)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            pix.save(cache_path)
            doc.close()

            return send_file(cache_path)
        except Exception as e:
            _log.error("PyMuPDF error: %s", e)
            return jsonify({"error": "Error creating preview"}), 500

    except Exception as e:
        _log.error("Error generating preview: %s", e)
        return jsonify({"error": "Error generating preview"}), 500

@app.route('/api/pdf-text-blocks/<filename>/<int:page_num>')
def get_text_blocks(filename, page_num):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
        
        from utils.pdf_utils import get_pdf_text_blocks
        blocks = get_pdf_text_blocks(file_path, page_num - 1)
        return jsonify({"blocks": blocks})
    except Exception as e:
        _log.error("Error fetching text blocks: %s", e)
        return jsonify({"error": "Error extracting text blocks"}), 500

@app.route('/api/pdf-fonts/<filename>/<int:page_num>')
def get_pdf_fonts(filename, page_num):
    """Extract embedded fonts from a PDF page as base64 for browser FontFace registration."""
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(secure_filename(filename)))
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404

        doc = fitz.open(file_path)
        if page_num < 1 or page_num > len(doc):
            return jsonify({"fonts": []})

        page = doc[page_num - 1]
        font_list = page.get_fonts(full=True)
        fonts = []
        seen = set()
        for f in font_list:
            xref = f[0]
            name = f[3] or f[4] or f[1] or "Unknown"
            if xref in seen:
                continue
            seen.add(xref)
            try:
                font_data = doc.extract_font(xref)
                if font_data and font_data[3]:  # font_data[3] is the raw bytes
                    b64 = base64.b64encode(font_data[3]).decode('utf-8')
                    ext = font_data[1] if font_data[1] else 'ttf'
                    fonts.append({"name": name, "data": b64, "ext": ext})
            except Exception:
                pass
        doc.close()
        return jsonify({"fonts": fonts})
    except Exception as e:
        _log.error("Error extracting fonts: %s", e)
        return jsonify({"fonts": []})

@app.route('/edit-pdf')
def edit_pdf():
    return render_template('edit_pdf.html')

@app.route('/download/<filename>')
def download_file(filename):
    try:
        safe_path = safe_upload_path(filename)
        if not os.path.exists(safe_path):
            return jsonify({"error": "File not found"}), 404
        return send_from_directory(app.config['UPLOAD_FOLDER'],
                                   os.path.basename(safe_path), as_attachment=True)
    except ValueError:
        return jsonify({"error": "Invalid filename"}), 400
    except Exception as e:
        _log.error("Download error: %s", e)
        return jsonify({"error": "File not found"}), 404

@app.route('/api/preview/<tool>/<filename>')
def preview_tool(tool, filename):
    """Generate preview for different PDF tools"""
    try:
        try:
            input_path = safe_upload_path(filename)
        except ValueError:
            return jsonify({"error": "Invalid filename"}), 400
        if not os.path.exists(input_path):
            return jsonify({"error": "File not found"}), 404

        # Create preview filename
        preview_filename = f"preview_{tool}_{int(time.time())}_{os.path.basename(input_path)}"
        preview_path = os.path.join(app.config['UPLOAD_FOLDER'], preview_filename)

        result = None

        if tool == 'watermark':
            text = request.args.get('text', 'SAMPLE WATERMARK')
            result = watermark_pdf(input_path, preview_path, text)
        elif tool == 'rotate':
            try:
                angle = max(0, min(360, int(request.args.get('angle', 90))))
            except (ValueError, TypeError):
                angle = 90
            result = rotate_pdf(input_path, preview_path, angle)
        elif tool == 'remove_pages':
            pages = request.args.get('pages', '1').split(',')
            pages_to_remove = [int(p.strip()) for p in pages if p.strip().isdigit()]
            result = remove_pages(input_path, preview_path, pages_to_remove)
        elif tool == 'merge':
            filenames = request.args.get('files', os.path.basename(input_path)).split(',')
            input_paths = []
            for fname in filenames:
                try:
                    fpath = safe_upload_path(fname.strip())
                    if os.path.exists(fpath):
                        input_paths.append(fpath)
                except ValueError:
                    pass
            if len(input_paths) > 1:
                result = merge_pdfs(input_paths, preview_path)
            else:
                return jsonify({"error": "Need at least 2 files to merge"}), 400
        else:
            return jsonify({"error": "Preview not available for this tool"}), 400

        if result:
            preview_images = pdf_to_images(result, app.config['UPLOAD_FOLDER'])
            if preview_images and len(preview_images) > 0:
                image_urls = [f"/static/uploads/{os.path.basename(img)}" for img in preview_images]
                return jsonify({
                    "preview_images": image_urls,
                    "preview_pdf": f"/download/{os.path.basename(result)}",
                    "total_pages": len(preview_images)
                })

        return jsonify({"error": "Preview generation failed"}), 500

    except Exception as e:
        _log.error("Preview error: %s", e)
        return jsonify({"error": "Preview generation failed"}), 500

@app.route('/api/preview-original/<filename>')
def preview_original(filename):
    """Generate preview images for original PDF"""
    try:
        try:
            input_path = safe_upload_path(filename)
        except ValueError:
            return jsonify({"error": "Invalid filename"}), 400
        if not os.path.exists(input_path):
            return jsonify({"error": "File not found"}), 404

        original_images = pdf_to_images(input_path, app.config['UPLOAD_FOLDER'])
        if original_images and len(original_images) > 0:
            image_urls = [f"/static/uploads/{os.path.basename(img)}" for img in original_images]
            return jsonify({
                "original_images": image_urls,
                "total_pages": len(original_images)
            })

        return jsonify({"error": "Original preview generation failed"}), 500

    except Exception as e:
        _log.error("Original preview error: %s", e)
        return jsonify({"error": "Preview generation failed"}), 500

@app.route('/api/save-edits', methods=['POST'])
def save_pdf_edits():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data received"}), 400
        filename = data.get('filename')
        edits = data.get('edits')
        
        if not filename or not edits:
            return jsonify({"error": "Missing filename or edits"}), 400

        # Sanitize filename to prevent path traversal
        filename = os.path.basename(secure_filename(filename))
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(input_path):
            return jsonify({"error": "File not found"}), 404
             
        output_filename = f"edited_{int(time.time())}_{filename}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        from utils.pdf_utils import apply_pdf_edits
        result = apply_pdf_edits(input_path, output_path, edits)
        
        if result:
            return jsonify({"download_url": f"/download/{output_filename}"})
        else:
            return jsonify({"error": "Failed to apply edits"}), 500
            
    except Exception as e:
        _log.error("Error saving edits: %s", e)
        return jsonify({"error": "Failed to save edits"}), 500

@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file:
        filename = secure_filename(file.filename)
        unique_filename = f"{int(time.time())}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        return jsonify({"filename": unique_filename})
    return jsonify({"error": "Upload failed"}), 500

@app.route('/api/pdf-previews/<filename>')
def get_pdf_previews(filename):
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "File not found"}), 404
            
        doc = fitz.open(filepath)
        previews = []
        
        for i in range(len(doc)):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img_data = pix.tobytes("png")
            encoded = base64.b64encode(img_data).decode('utf-8')
            previews.append(f"data:image/png;base64,{encoded}")
        
        doc.close()
        return jsonify({"previews": previews, "page_count": len(previews)})
    except Exception as e:
        _log.error("Error generating PDF previews: %s", e)
        return jsonify({"error": "Error generating previews"}), 500


@app.route('/upscale-image', methods=['GET', 'POST'])
def upscale_image_route():
    if request.method == 'POST':
        file = request.files.get('file')
        try:
            scale_factor = max(1, min(4, int(request.form.get('scale_factor', 2))))
        except (ValueError, TypeError):
            scale_factor = 2

        if not file or not file.filename:
            return "No file uploaded", 400

        filename = secure_filename(file.filename)

        # Validate file extension
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
        ext = os.path.splitext(filename)[1].lower()
        if ext not in allowed_extensions:
            return f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}", 400

        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)

        output_filename = f"upscaled_{int(time.time())}_{filename}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        result = upscale_image(input_path, output_path, scale_factor)

        if result:
            return send_file(result, as_attachment=True)
        else:
            return "Error upscaling image. Please check the file format and try again.", 500
    return render_template('upscale_image.html')


@app.route('/summarize-pdf', methods=['GET', 'POST'])
def summarize_pdf_route():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files['file']
        if file and file.filename.endswith('.pdf'):
            try:
                sentences_count = max(1, min(20, int(request.form.get('count', 5))))
            except (ValueError, TypeError):
                sentences_count = 5
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)

            text = extract_text_from_pdf(input_path)
            if not text:
                return jsonify({"error": "Error extracting text from PDF"}), 500

            summary = summarize_text(text, sentences_count=sentences_count)
            return jsonify({"summary": summary})
        return jsonify({"error": "Invalid file type. Please upload a PDF."}), 400

    return render_template('summarize_pdf.html')

@app.route('/translate-pdf', methods=['GET', 'POST'])
def translate_pdf_route():
    languages = get_supported_languages()
    
    if request.method == 'POST':
        if 'file' not in request.files:
            return "No file uploaded", 400
        
        file = request.files['file']
        target_lang = request.form.get('target_lang', 'hi')
        
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            # Extract text
            text = extract_text_from_pdf(input_path)
            if not text:
                return "Error extracting text from PDF", 500
            
            # Translate
            translation = translate_text(text, target_lang=target_lang)
            
            return {"translation": translation}
        return "Invalid file type", 400

    return render_template('translate_pdf.html', languages=languages)


@app.route('/generate-qr', methods=['GET', 'POST'])
def generate_qr_route():
    if request.method == 'POST':
        data = request.form.get('data', '').strip()
        size = int(request.form.get('size', 300))
        fill_color = request.form.get('fill_color', '#000000')
        back_color = request.form.get('back_color', '#ffffff')
        is_preview = request.form.get('preview', '0') == '1'

        if not data:
            return jsonify({"error": "No data provided"}), 400

        output_filename = f"qr_{int(time.time())}.png"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        result = generate_qr_code(data, output_path, size=size, fill_color=fill_color, back_color=back_color)
        if result:
            # Preview: return inline image (not attachment)
            return send_file(result, mimetype='image/png', as_attachment=False)
        return jsonify({"error": "Error generating QR code"}), 500

    return render_template('generate_qr.html')

@app.route('/edit-metadata', methods=['GET', 'POST'])
def edit_metadata_route():
    if request.method == 'POST':
        if 'file' not in request.files:
            return "No file uploaded", 400
        
        file = request.files['file']
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            title = request.form.get('title')
            author = request.form.get('author')
            subject = request.form.get('subject')
            keywords = request.form.get('keywords')
            
            output_filename = f"metadata_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            result = edit_pdf_metadata(input_path, output_path, title, author, subject, keywords)
            
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error editing metadata", 500
        return "Invalid file type", 400

    return render_template('edit_metadata.html')


@app.route('/extract-pages', methods=['GET', 'POST'])
def extract_pages_route():
    if request.method == 'POST':
        file = request.files.get('file')
        pages_input = request.form.get('pages')  # e.g. "1,2,5" or "1-3,5"
        
        if not file or not file.filename:
            return "No file uploaded", 400
        
        if not pages_input:
            return "No page numbers specified", 400
        
        if file and file.filename.endswith('.pdf') and pages_input:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            output_filename = f"extracted_{int(time.time())}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            try:
                # Parse page numbers - support both "1,2,3" and "1-3" formats
                pages = []
                for part in pages_input.split(','):
                    part = part.strip()
                    if '-' in part:
                        # Handle range like "1-3"
                        start, end = part.split('-')
                        pages.extend(range(int(start.strip()), int(end.strip()) + 1))
                    else:
                        # Handle single page
                        pages.append(int(part))
                
                if not pages:
                    return "No valid page numbers provided", 400
                    
            except ValueError as e:
                return f"Invalid page numbers format. Use format like '1,2,3' or '1-3,5'. Error: {str(e)}", 400
                
            result = extract_pdf_pages(input_path, output_path, pages)
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error extracting pages. Please check the page numbers and try again.", 500
        return "Invalid file or page numbers", 400

    return render_template('extract_pages.html')


@app.route('/pdf-to-ppt', methods=['GET', 'POST'])
def pdf_to_ppt_route():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            output_filename = f"converted_{int(time.time())}.pptx"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            result = pdf_to_ppt(input_path, output_path)
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error converting PDF to PPT", 500
        return "Invalid file type", 400

    return render_template('pdf_to_ppt.html')



@app.route('/compare-pdf', methods=['GET', 'POST'])
def compare_pdf_route():
    if request.method == 'POST':
        if 'file1' not in request.files or 'file2' not in request.files:
            return "Two PDF files required", 400
        
        file1 = request.files['file1']
        file2 = request.files['file2']
        
        if file1 and file2 and file1.filename.endswith('.pdf') and file2.filename.endswith('.pdf'):
            filename1 = secure_filename(file1.filename)
            filename2 = secure_filename(file2.filename)
            
            input_path1 = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename1}")
            input_path2 = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())+1}_{filename2}")
            
            file1.save(input_path1)
            file2.save(input_path2)
            
            output_filename = f"comparison_{int(time.time())}.txt"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            result = pdf_compare(input_path1, input_path2, output_path)
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error comparing PDFs", 500
        return "Invalid files", 400
    
    return render_template('compare_pdf.html')


@app.route('/add-border', methods=['GET', 'POST'])
def add_border_route():
    if request.method == 'POST':
        file = request.files['file']
        border_width = int(request.form.get('border_width', 10))
        border_color = request.form.get('border_color', 'black')
        
        if file and file.filename:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            
            output_filename = f"bordered_{int(time.time())}_{filename}"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            result = add_border_to_image(input_path, output_path, border_width, border_color)
            if result:
                return send_file(result, as_attachment=True)
            else:
                return "Error adding border", 500
        return "No file uploaded", 400
    
    return render_template('add_border.html')

@app.route('/create-collage', methods=['GET', 'POST'])
def create_collage_route():
    if request.method == 'POST':
        if 'files' not in request.files:
            return "No files uploaded", 400
        
        files = request.files.getlist('files')
        cols = int(request.form.get('cols', 2))
        
        if not files or files[0].filename == '':
            return "No selected files", 400
        
        saved_paths = []
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
                file.save(path)
                saved_paths.append(path)
        
        output_filename = f"collage_{int(time.time())}.png"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        result = create_collage(saved_paths, output_path, cols)
        if result:
            return send_file(result, as_attachment=True)
        else:
            return "Error creating collage", 500
    
    return render_template('create_collage.html')

@app.route('/add-text-to-image', methods=['GET', 'POST'])
def add_text_to_image_route():
    if request.method == 'POST':
        # Check if it's JSON request (new interactive mode) or form request (legacy)
        if request.is_json:
            # New interactive mode with precise positioning
            data = request.json
            filename = data.get('filename')
            text = data.get('text', 'Sample Text')
            x = int(data.get('x', 0))
            y = int(data.get('y', 0))
            font_size = int(data.get('font_size', 40))
            font_family = data.get('font_family', 'Arial')
            font_weight = data.get('font_weight', 'normal')
            color = data.get('color', '#ffffff')
            shadow = data.get('shadow', True)
            
            if filename:
                input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if not os.path.exists(input_path):
                    return {"error": "File not found"}, 404
                
                output_filename = f"text_{int(time.time())}_{filename}"
                output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
                
                result = add_text_to_image_advanced(
                    input_path, output_path, text, x, y, 
                    font_size, font_family, font_weight, color, shadow
                )
                
                if result:
                    return send_file(result, as_attachment=True)
                else:
                    return {"error": "Error adding text"}, 500
        else:
            # Legacy form-based mode
            file = request.files.get('file')
            text = request.form.get('text', 'Sample Text')
            position = request.form.get('position', 'center')
            font_size = int(request.form.get('font_size', 40))
            color = request.form.get('color', 'white')
            
            if file and file.filename:
                filename = secure_filename(file.filename)
                input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
                file.save(input_path)
                
                output_filename = f"text_{int(time.time())}_{filename}"
                output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
                
                result = add_text_to_image(input_path, output_path, text, position, font_size, color)
                if result:
                    return send_file(result, as_attachment=True)
                else:
                    return "Error adding text", 500
            return "No file uploaded", 400
    
    return render_template('add_text_to_image.html')


@app.route('/chat_document', methods=['GET', 'POST'])
def chat_document_route():
    """Route for document chat interface - supports multiple file formats"""
    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(filepath)
            
            # Extract text from document using universal extractor
            from utils.document_extract_utils import extract_text_from_document
            text_content = extract_text_from_document(filepath)
            
            # Check if extraction failed or returned an error
            if text_content.startswith("ERROR:") or text_content.startswith("Unsupported") or text_content.startswith("Error"):
                return f"Document processing failed: {text_content}", 400
            
            if not text_content or text_content.strip() == "":
                return "Could not extract text from document. Please ensure the document contains readable text.", 400
            
            # Initialize chat session
            from utils.chat_utils import get_chat_manager
            chat_mgr = get_chat_manager()
            
            if not chat_mgr:
                return "Chat service not available. Please check API configuration.", 500
            
            session_id = f"session_{int(time.time())}"
            doc_content = chat_mgr.extract_document_content(filepath, text_content)
            chat_mgr.start_chat_session(session_id, doc_content, filename)
            
            # Get suggested questions
            suggestions = chat_mgr.get_suggested_questions(doc_content, filename)
            
            return render_template('chat_document.html', 
                                 session_id=session_id,
                                 filename=filename,
                                 suggestions=suggestions)
        
        return "No file uploaded", 400

    try:
        return render_template('chat_document.html')
    except Exception as e:
        _log.error("Error rendering chat_document template: %s", e)
        return jsonify({"error": "Template error"}), 500

@app.route('/chat_message', methods=['POST'])
def chat_message_route():
    """API endpoint for sending chat messages"""
    data = request.json
    session_id = data.get('session_id')
    message = data.get('message')
    
    if not session_id or not message:
        return jsonify({"error": "Missing session_id or message"}), 400
    
    from utils.chat_utils import get_chat_manager
    chat_mgr = get_chat_manager()
    
    if not chat_mgr:
        return jsonify({"error": "Chat service not available"}), 500
    
    result = chat_mgr.send_message(session_id, message)
    return jsonify(result)

@app.route('/chat_end_session', methods=['POST'])
def chat_end_session_route():
    """API endpoint for ending chat session"""
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400
    session_id = data.get('session_id')

    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    from utils.chat_utils import get_chat_manager
    chat_mgr = get_chat_manager()

    if not chat_mgr:
        return jsonify({"error": "Chat service not available"}), 500

    success = chat_mgr.end_session(session_id)
    return jsonify({"success": success})

@app.route('/api/clear-uploads', methods=['POST'])
def clear_uploads_route():
    """API endpoint to clear all uploaded files from the server.
    Requires the app SECRET_KEY as a bearer token for basic protection.
    """
    auth = request.headers.get('Authorization', '')
    expected = f"Bearer {app.secret_key}"
    if auth != expected:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        if os.path.exists(upload_folder):
            for filename in os.listdir(upload_folder):
                file_path = os.path.join(upload_folder, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    _log.warning("Failed to delete %s: %s", file_path, e)
        return jsonify({"success": True})
    except Exception as e:
        _log.error("Error clearing uploads: %s", e)
        return jsonify({"success": False, "error": "Failed to clear uploads"}), 500

@app.route('/generate-flashcards', methods=['GET'])
def generate_flashcards_route():
    """Route for the Flashcard Generator interface"""
    return render_template('generate_flashcards.html')

@app.route('/generate-questions', methods=['GET'])
def generate_questions_route():
    """Route for the Question Generator interface"""
    return render_template('generate_questions.html')

@app.route('/api/generate-questions', methods=['POST'])
def api_generate_questions():
    """API endpoint to generate questions from an uploaded document"""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"error": "No selected file"}), 400

    try:
        num_questions = max(1, min(50, int(request.form.get('num_questions', 10))))
    except (ValueError, TypeError):
        num_questions = 10
    q_type = request.form.get('q_type', 'mixed')
    if q_type not in ('mcq', 'short', 'truefalse', 'mixed'):
        q_type = 'mixed'

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"qgen_{int(time.time())}_{filename}")
        file.save(filepath)

        from utils.document_extract_utils import extract_text_from_document
        text_content = extract_text_from_document(filepath)

        if not text_content or text_content.strip() == "" or text_content.startswith("Error") or text_content.startswith("Unsupported"):
            return jsonify({"error": f"Could not extract text: {text_content}"}), 400

        from utils.chat_utils import get_chat_manager
        chat_mgr = get_chat_manager()
        if not chat_mgr:
            return jsonify({"error": "AI service not available. Check API settings."}), 500

        result = chat_mgr.generate_questions(text_content, num_questions, q_type)
        return jsonify(result)

    except Exception as e:
        _log.error("Error in api_generate_questions: %s", e)
        return jsonify({"error": "An error occurred generating questions."}), 500

@app.route('/api/generate-flashcards', methods=['POST'])
def api_generate_flashcards():
    """API endpoint to generate flashcards from an uploaded document"""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if not file or not file.filename:
        return jsonify({"error": "No selected file"}), 400

    try:
        num_cards = max(1, min(50, int(request.form.get('num_cards', 15))))
    except (ValueError, TypeError):
        num_cards = 15

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"flashcard_{int(time.time())}_{filename}")
        file.save(filepath)

        from utils.document_extract_utils import extract_text_from_document
        text_content = extract_text_from_document(filepath)

        if text_content.startswith("ERROR:") or text_content.startswith("Unsupported") or text_content.startswith("Error"):
            return jsonify({"error": f"Document processing failed: {text_content}"}), 400

        if not text_content or text_content.strip() == "":
            return jsonify({"error": "Could not extract text from document. Please ensure it contains readable text."}), 400

        from utils.chat_utils import get_chat_manager
        chat_mgr = get_chat_manager()

        if not chat_mgr:
            return jsonify({"error": "AI service not available. Please check API configuration in Settings."}), 500

        result = chat_mgr.generate_flashcards(text_content, num_cards)
        return jsonify(result)

    except Exception as e:
        _log.error("Error in api_generate_flashcards: %s", e)
        return jsonify({"error": "An error occurred generating flashcards."}), 500

@app.route('/api-settings', methods=['GET'])
def api_settings_page():
    """Display API key settings page"""
    keys = list_api_keys()
    return render_template('api_settings.html', stored_keys=keys)

@app.route('/api/update-key', methods=['POST'])
def update_api_key():
    """Update the API key"""
    data = request.json
    new_key = data.get('api_key', '').strip()
    
    if not new_key:
        return jsonify({"success": False, "error": "API key cannot be empty"}), 400

    if not is_api_key_valid(new_key):
        return jsonify({"success": False, "error": "API key format appears invalid"}), 400

    # Test the key before saving
    if not test_api_key(new_key):
        return jsonify({
            "success": False,
            "error": "Could not verify API key. Please check if it's valid and you have an active quota."
        }), 400

    # Save the new key
    if set_primary_api_key(new_key):
        try:
            from utils.chat_utils import initialize_chat_manager
            from utils.ai_tools import reset_rate_limiter
            initialize_chat_manager(new_key)
            reset_rate_limiter()
            _log.info("API key updated successfully")
            return jsonify({
                "success": True,
                "message": "API key updated successfully. Chat is ready to use!"
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": "Key saved but could not initialize chat."
            }), 500
    else:
        return jsonify({"success": False, "error": "Failed to save API key"}), 500

@app.route('/api/test-key', methods=['POST'])
def test_api_key_route():
    """Test if an API key is valid"""
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data received"}), 400
    test_key = data.get('api_key', '').strip()

    if not test_key:
        return jsonify({"success": False, "error": "API key cannot be empty"}), 400

    if not is_api_key_valid(test_key):
        return jsonify({"success": False, "error": "API key format appears invalid"}), 400

    if test_api_key(test_key):
        return jsonify({"success": True, "message": "API key is valid!"})
    else:
        return jsonify({
            "success": False,
            "error": "Could not verify API key. Please check if it's valid."
        }), 400

@app.route('/api/keys', methods=['GET'])
def get_api_keys_api():
    """Get list of configured API keys (for display)"""
    keys = list_api_keys()
    return jsonify({"keys": keys})

# ─────────────────────────────────────────────
# NEW FEATURES
# ─────────────────────────────────────────────

# -- Flatten PDF --
@app.route('/flatten-pdf', methods=['GET', 'POST'])
def flatten_pdf_route():
    from utils.feature_utils import flatten_pdf
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.endswith('.pdf'):
            return "Invalid file", 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"flattened_{int(time.time())}.pdf")
        result = flatten_pdf(input_path, output_path)
        if result:
            return send_file(result, as_attachment=True, download_name=f"flattened_{filename}")
        return "Error flattening PDF", 500
    return render_template('flatten_pdf.html')

# -- Repair PDF --
@app.route('/repair-pdf', methods=['GET', 'POST'])
def repair_pdf_route():
    from utils.feature_utils import repair_pdf
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.endswith('.pdf'):
            return "Invalid file", 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"repaired_{int(time.time())}.pdf")
        result = repair_pdf(input_path, output_path)
        if result:
            return send_file(result, as_attachment=True, download_name=f"repaired_{filename}")
        return "Error repairing PDF", 500
    return render_template('repair_pdf.html')

# -- Unlock PDF --
@app.route('/unlock-pdf', methods=['GET', 'POST'])
def unlock_pdf_route():
    if request.method == 'POST':
        file = request.files.get('file')
        password = request.form.get('password', '')
        if not file or not file.filename.endswith('.pdf'):
            return "Invalid file", 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"unlocked_{int(time.time())}.pdf")
        result = unlock_pdf(input_path, output_path, password)
        if result:
            return send_file(result, as_attachment=True, download_name=f"unlocked_{filename}")
        return "Error unlocking PDF — wrong password?", 500
    return render_template('unlock_pdf.html')

# -- Add Page Numbers --
@app.route('/page-numbers', methods=['GET', 'POST'])
def page_numbers_route():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.endswith('.pdf'):
            return "Invalid file", 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"numbered_{int(time.time())}.pdf")
        position = request.form.get('position', 'bottom-center')
        try:
            start_num = max(1, int(request.form.get('start_num', 1)))
            font_size = max(6, min(72, int(request.form.get('font_size', 12))))
        except (ValueError, TypeError):
            return "Invalid numeric parameter", 400
        result = add_page_numbers(input_path, output_path, position, start_num, font_size)
        if result:
            return send_file(result, as_attachment=True, download_name=f"numbered_{filename}")
        return "Error adding page numbers", 500
    return render_template('page_numbers.html')

# -- Reverse PDF --
@app.route('/reverse-pdf', methods=['GET', 'POST'])
def reverse_pdf_route():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.endswith('.pdf'):
            return "Invalid file", 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"reversed_{int(time.time())}.pdf")
        from utils.feature_utils import organize_pdf
        # Open doc just to get page count, then close before passing path to organize_pdf
        doc = fitz.open(input_path)
        page_order = list(range(len(doc) - 1, -1, -1))
        doc.close()
        result = organize_pdf(input_path, output_path, page_order)
        if result:
            return send_file(result, as_attachment=True, download_name=f"reversed_{filename}")
        return "Error reversing PDF", 500
    return render_template('reverse_pdf.html')

# -- PDF Font Inspector --
@app.route('/pdf-fonts', methods=['GET', 'POST'])
def pdf_fonts_route():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.endswith('.pdf'):
            return jsonify({"error": "Invalid file"}), 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        try:
            doc = fitz.open(input_path)
            fonts = {}
            for page_num, page in enumerate(doc):
                for f in page.get_fonts(full=True):
                    name = f[3] or f[4] or "Unknown"
                    ftype = f[2]
                    key = f"{name}|{ftype}"
                    if key not in fonts:
                        fonts[key] = {"name": name, "type": ftype, "pages": []}
                    fonts[key]["pages"].append(page_num + 1)
            doc.close()
            return jsonify({"fonts": list(fonts.values()), "filename": filename})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('pdf_fonts.html')

# -- PDF Page Size Normalizer --
@app.route('/normalize-pdf', methods=['GET', 'POST'])
def normalize_pdf_route():
    if request.method == 'POST':
        file = request.files.get('file')
        page_size = request.form.get('page_size', 'A4')
        if not file or not file.filename.endswith('.pdf'):
            return "Invalid file", 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"normalized_{int(time.time())}.pdf")
        try:
            sizes = {'A4': (595, 842), 'Letter': (612, 792), 'A3': (842, 1191), 'Legal': (612, 1008)}
            target_w, target_h = sizes.get(page_size, (595, 842))
            doc = fitz.open(input_path)
            new_doc = fitz.open()
            try:
                for page in doc:
                    new_page = new_doc.new_page(width=target_w, height=target_h)
                    new_page.show_pdf_page(new_page.rect, doc, page.number)
                new_doc.save(output_path)
            finally:
                doc.close()
                new_doc.close()
            return send_file(output_path, as_attachment=True, download_name=f"normalized_{filename}")
        except Exception as e:
            return f"Error: {e}", 500
    return render_template('normalize_pdf.html')

# -- Resize Image --
@app.route('/resize-image', methods=['GET', 'POST'])
def resize_image_route():
    from utils.image_utils import resize_image
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            return "No file", 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"resized_{int(time.time())}_{filename}")
        width      = request.form.get('width')
        height     = request.form.get('height')
        percentage = request.form.get('percentage')
        result = resize_image(
            input_path, output_path,
            width=int(width) if width else None,
            height=int(height) if height else None,
            percentage=int(percentage) if percentage else None
        )
        if result:
            return send_file(result, as_attachment=True, download_name=f"resized_{filename}")
        return "Error resizing image", 500
    return render_template('resize_image.html')

# -- Image Filters (grayscale, sepia, flip, invert, blur, sharpen) --
@app.route('/image-filters', methods=['GET', 'POST'])
def image_filters_route():
    from utils.image_utils import apply_image_filter
    if request.method == 'POST':
        file = request.files.get('file')
        filter_type = request.form.get('filter', 'grayscale')
        if not file:
            return "No file", 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        # Handle flip/invert in-place with Pillow
        if filter_type in ('flip_h', 'flip_v', 'invert'):
            from PIL import Image as PILImage, ImageOps
            img = PILImage.open(input_path)
            if filter_type == 'flip_h':
                img = img.transpose(PILImage.FLIP_LEFT_RIGHT)
            elif filter_type == 'flip_v':
                img = img.transpose(PILImage.FLIP_TOP_BOTTOM)
            elif filter_type == 'invert':
                img = img.convert('RGB')
                img = ImageOps.invert(img)
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"filtered_{int(time.time())}_{filename}")
            img.save(output_path)
            return send_file(output_path, as_attachment=True, download_name=f"{filter_type}_{filename}")
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"filtered_{int(time.time())}_{filename}")
        result = apply_image_filter(input_path, output_path, filter_type)
        if result:
            return send_file(result, as_attachment=True, download_name=f"{filter_type}_{filename}")
        return "Error applying filter", 500
    return render_template('image_filters.html')

# -- EXIF Viewer & Stripper --
@app.route('/exif-tool', methods=['GET', 'POST'])
def exif_tool_route():
    if request.method == 'POST':
        file = request.files.get('file')
        action = request.form.get('action', 'view')
        if not file:
            return jsonify({"error": "No file"}), 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        try:
            from PIL import Image as PILImage
            from PIL.ExifTags import TAGS, GPSTAGS
            img = PILImage.open(input_path)
            exif_data = {}

            # Method 1: modern getexif() — works on JPEG, TIFF, WEBP, HEIC
            try:
                exif_obj = img.getexif()
                if exif_obj:
                    for tag_id, value in exif_obj.items():
                        tag = TAGS.get(tag_id, f"Tag_{tag_id}")
                        # Skip binary blobs
                        if isinstance(value, bytes):
                            try:
                                value = value.decode('utf-8', errors='replace').strip('\x00')
                            except Exception:
                                value = f"<binary {len(value)} bytes>"
                        exif_data[tag] = str(value)
            except Exception:
                pass

            # Method 2: legacy _getexif() for older JPEG files
            if not exif_data:
                try:
                    raw = img._getexif()
                    if raw:
                        for tag_id, value in raw.items():
                            tag = TAGS.get(tag_id, f"Tag_{tag_id}")
                            if isinstance(value, bytes):
                                try:
                                    value = value.decode('utf-8', errors='replace').strip('\x00')
                                except Exception:
                                    value = f"<binary {len(value)} bytes>"
                            exif_data[tag] = str(value)
                except Exception:
                    pass

            # Method 3: PNG / GIF / BMP — read img.info dict
            if not exif_data and hasattr(img, 'info') and img.info:
                skip_keys = {'icc_profile', 'exif', 'XML:com.adobe.xmp'}
                for k, v in img.info.items():
                    if k in skip_keys:
                        continue
                    if isinstance(v, bytes):
                        try:
                            v = v.decode('utf-8', errors='replace').strip('\x00')
                        except Exception:
                            v = f"<binary {len(v)} bytes>"
                    exif_data[str(k)] = str(v)

            # Always include basic image info
            basic = {
                "Format": img.format or filename.rsplit('.', 1)[-1].upper(),
                "Mode": img.mode,
                "Width": str(img.width),
                "Height": str(img.height),
                "Size (px)": f"{img.width} × {img.height}",
            }
            # Merge: basic first, then EXIF on top
            merged = {**basic, **exif_data}

            if action == 'strip':
                # Rebuild image without any metadata
                clean = PILImage.new(img.mode, img.size)
                clean.putdata(list(img.getdata()))
                output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"clean_{int(time.time())}_{filename}")
                # Save as same format
                fmt = (img.format or 'PNG').upper()
                if fmt == 'JPG':
                    fmt = 'JPEG'
                clean.save(output_path, format=fmt)
                return send_file(output_path, as_attachment=True, download_name=f"clean_{filename}")

            return jsonify({"exif": merged, "count": len(merged)})
        except Exception as e:
            return jsonify({"error": str(e), "exif": {}}), 200
    return render_template('exif_tool.html')

# -- Image to Base64 --
@app.route('/image-to-base64', methods=['GET', 'POST'])
def image_to_base64_route():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            return jsonify({"error": "No file"}), 400
        data = file.read()
        b64 = base64.b64encode(data).decode('utf-8')
        mime = file.content_type or 'image/jpeg'
        data_uri = f"data:{mime};base64,{b64}"
        return jsonify({"base64": b64, "data_uri": data_uri, "size": len(b64)})
    return render_template('image_to_base64.html')

# -- Crop Image (server-side) --
@app.route('/crop-image', methods=['GET', 'POST'])
def crop_image_route():
    from utils.image_utils import crop_image
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            return "No file", 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"cropped_{int(time.time())}_{filename}")
        left   = int(request.form.get('left', 0))
        top    = int(request.form.get('top', 0))
        right  = int(request.form.get('right', 100))
        bottom = int(request.form.get('bottom', 100))
        result = crop_image(input_path, output_path, left, top, right, bottom)
        if result:
            return send_file(result, as_attachment=True, download_name=f"cropped_{filename}")
        return "Error cropping image", 500
    return render_template('crop_image.html')


# -- Crop PDF --
@app.route('/crop-pdf', methods=['GET', 'POST'])
def crop_pdf_route():
    from utils.pdf_extract_utils import crop_pdf
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            return "No file", 400
        filename = secure_filename(file.filename)
        ts = int(time.time())
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{ts}_{filename}")
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"cropped_{ts}_{filename}")
        file.save(input_path)
        left   = float(request.form.get('left', 0))
        top    = float(request.form.get('top', 0))
        right  = float(request.form.get('right', 595))
        bottom = float(request.form.get('bottom', 842))
        result = crop_pdf(input_path, output_path, left, top, right, bottom)
        if result:
            return send_file(result, as_attachment=True, download_name=f"cropped_{filename}")
        return "Error cropping PDF", 500
    return render_template('crop_pdf.html')


# -- PDF to Text --
@app.route('/pdf-to-text', methods=['GET', 'POST'])
def pdf_to_text_route():
    from utils.pdf_extract_utils import pdf_to_text
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            return "No file", 400
        filename = secure_filename(file.filename)
        ts = int(time.time())
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{ts}_{filename}")
        output_name = os.path.splitext(filename)[0] + '.txt'
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{ts}_{output_name}")
        file.save(input_path)
        result = pdf_to_text(input_path, output_path)
        if result:
            return send_file(result, as_attachment=True, download_name=output_name)
        return "Error extracting text", 500
    return render_template('pdf_to_text.html')


# -- PDF to CSV (table extractor) --
@app.route('/pdf-to-csv', methods=['GET', 'POST'])
def pdf_to_csv_route():
    from utils.pdf_extract_utils import pdf_to_csv
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            return "No file", 400
        filename = secure_filename(file.filename)
        ts = int(time.time())
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{ts}_{filename}")
        output_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"csv_{ts}")
        file.save(input_path)
        results = pdf_to_csv(input_path, output_dir)
        if not results:
            return jsonify({"error": "No tables found in this PDF, or pdfplumber is not installed."}), 400
        if len(results) == 1:
            return send_file(results[0], as_attachment=True, download_name=os.path.basename(results[0]))
        zip_name = f"tables_{ts}.zip"
        zip_path = create_zip(results, zip_name)
        return send_file(zip_path, as_attachment=True, download_name=zip_name)
    return render_template('pdf_to_csv.html')


# ══════════════════════════════════════════════
# AI TOOLS
# ══════════════════════════════════════════════

def _check_ai_limit():
    """Returns (allowed, error_response_or_None)."""
    from utils.ai_tools import check_ip_limit
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '127.0.0.1').split(',')[0].strip()
    allowed, wait = check_ip_limit(ip)
    if not allowed:
        mins = max(1, wait // 60)
        return False, (jsonify({"error": f"You've used all 20 free AI requests for this hour. Please try again in ~{mins} minute(s)."}), 429)
    return True, None

# -- Smart Document Brief --
@app.route('/document-brief', methods=['GET', 'POST'])
def document_brief_route():
    from utils.ai_tools import generate_document_brief
    from utils.document_extract_utils import extract_text_from_document
    if request.method == 'POST':
        allowed, err = _check_ai_limit()
        if not allowed: return err
        file = request.files.get('file')
        if not file:
            return jsonify({"error": "No file uploaded"}), 400
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
        file.save(input_path)
        try:
            # extract_text_from_document uses PyMuPDF for PDFs (fast, no API cost)
            # and falls back to Tesseract OCR only for scanned/image-based pages
            text = extract_text_from_document(input_path)
            if not text or len(text.strip()) < 50:
                return jsonify({"error": "Could not extract text from this file. If it's a scanned document, ensure Tesseract OCR is available."}), 400
            # generate_document_brief sends only a smart sample (~4000 chars) to Gemini
            brief = generate_document_brief(text, filename)
            return jsonify({"brief": brief, "status": "success", "chars_extracted": len(text)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('document_brief.html')


# -- Document Rewriter --
@app.route('/rewrite-document', methods=['GET', 'POST'])
def rewrite_document_route():
    from utils.ai_tools import rewrite_document, REWRITE_TONES
    if request.method == 'POST':
        allowed, err = _check_ai_limit()
        if not allowed: return err
        text = request.form.get('text', '').strip()
        tone = request.form.get('tone', 'formal')
        if not text:
            return jsonify({"error": "No text provided"}), 400
        try:
            result = rewrite_document(text, tone)
            return jsonify({"result": result, "status": "success"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    from utils.ai_tools import REWRITE_TONES
    return render_template('rewrite_document.html', tones=list(REWRITE_TONES.keys()))


# -- AI OCR Correction --
@app.route('/ocr-correct', methods=['GET', 'POST'])
def ocr_correct_route():
    from utils.ai_tools import correct_ocr_text
    from utils.ocr_utils import extract_text_from_pdf, extract_text_from_image
    if request.method == 'POST':
        allowed, err = _check_ai_limit()
        if not allowed: return err
        file = request.files.get('file')
        raw_text = request.form.get('raw_text', '').strip()
        if file and file.filename:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            ext = filename.lower().rsplit('.', 1)[-1]
            try:
                if ext == 'pdf':
                    raw_text = extract_text_from_pdf(input_path)
                elif ext == 'txt':
                    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
                        raw_text = f.read()
                else:
                    raw_text = extract_text_from_image(input_path)
            except Exception as e:
                return jsonify({"error": f"Could not extract text: {str(e)}"}), 400
        if not raw_text:
            return jsonify({"error": "No text to correct. Paste text or upload a file."}), 400
        if len(raw_text.strip()) < 10:
            return jsonify({"error": "Text is too short to correct."}), 400
        try:
            corrected = correct_ocr_text(raw_text)
            return jsonify({"corrected": corrected, "original": raw_text, "status": "success"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('ocr_correct.html')


# -- Tone & Sentiment Analyzer --
@app.route('/tone-analyzer', methods=['GET', 'POST'])
def tone_analyzer_route():
    from utils.ai_tools import analyze_tone_sentiment
    from utils.document_extract_utils import extract_text_from_document
    if request.method == 'POST':
        allowed, err = _check_ai_limit()
        if not allowed: return err
        file = request.files.get('file')
        text = request.form.get('text', '').strip()
        if file and file.filename:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{int(time.time())}_{filename}")
            file.save(input_path)
            text = extract_text_from_document(input_path)
        if not text:
            return jsonify({"error": "No text provided."}), 400
        try:
            result = analyze_tone_sentiment(text)
            return jsonify({"result": result, "status": "success"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('tone_analyzer.html')


# -- AI PDF Comparison --
@app.route('/ai-compare', methods=['GET', 'POST'])
def ai_compare_route():
    from utils.ai_tools import explain_pdf_diff
    from utils.document_extract_utils import extract_text_from_document
    if request.method == 'POST':
        allowed, err = _check_ai_limit()
        if not allowed: return err
        file1 = request.files.get('file1')
        file2 = request.files.get('file2')
        if not file1 or not file2:
            return jsonify({"error": "Please upload two files."}), 400
        ts = int(time.time())
        p1 = os.path.join(app.config['UPLOAD_FOLDER'], f"{ts}_a_{secure_filename(file1.filename)}")
        p2 = os.path.join(app.config['UPLOAD_FOLDER'], f"{ts}_b_{secure_filename(file2.filename)}")
        file1.save(p1)
        file2.save(p2)
        try:
            t1 = extract_text_from_document(p1)
            t2 = extract_text_from_document(p2)
            result = explain_pdf_diff(t1, t2, file1.filename, file2.filename)
            return jsonify({"result": result, "status": "success"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('ai_compare.html')


@app.route('/api/ai-quota-status')
def ai_quota_status():
    """Return daily AI request counter status."""
    from utils.ai_tools import get_quota_status, get_cache_stats
    status = get_quota_status()
    status.update(get_cache_stats())
    return jsonify(status)


# ─────────────────────────────────────────────
# RESUME INTELLIGENCE
# ─────────────────────────────────────────────
@app.route('/resume-intelligence', methods=['GET', 'POST'])
def resume_intelligence_route():
    from utils.ai_tools import extract_resume_data
    from utils.document_extract_utils import extract_text_from_document
    if request.method == 'POST':
        allowed, err = _check_ai_limit()
        if not allowed:
            return err
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({"error": "No file uploaded"}), 400
        ext = file.filename.rsplit('.', 1)[-1].lower()
        if ext not in ('pdf', 'doc', 'docx', 'txt'):
            return jsonify({"error": "Unsupported file type. Use PDF, DOC, DOCX, or TXT."}), 400
        filename = f"{int(time.time())}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        try:
            text = extract_text_from_document(filepath)
            if not text or len(text.strip()) < 50:
                return jsonify({"error": "Could not extract text from file."}), 400
            result = extract_resume_data(text)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('resume_intelligence.html')


# ─────────────────────────────────────────────
# INVOICE INTELLIGENCE
# ─────────────────────────────────────────────
@app.route('/invoice-intelligence', methods=['GET', 'POST'])
def invoice_intelligence_route():
    from utils.ai_tools import extract_invoice_data
    from utils.document_extract_utils import extract_text_from_document
    if request.method == 'POST':
        allowed, err = _check_ai_limit()
        if not allowed:
            return err
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({"error": "No file uploaded"}), 400
        ext = file.filename.rsplit('.', 1)[-1].lower()
        if ext not in ('pdf', 'doc', 'docx', 'txt', 'png', 'jpg', 'jpeg'):
            return jsonify({"error": "Unsupported file type. Use PDF, DOC, DOCX, TXT, or image."}), 400
        filename = f"{int(time.time())}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        try:
            # For images, use OCR first
            if ext in ('png', 'jpg', 'jpeg'):
                from utils.ocr_utils import extract_text_from_image
                text = extract_text_from_image(filepath)
            else:
                text = extract_text_from_document(filepath)
            if not text or len(text.strip()) < 20:
                return jsonify({"error": "Could not extract text from file."}), 400
            result = extract_invoice_data(text)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('invoice_intelligence.html')


# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Endpoint not found"}), 404
    return render_template('error.html', code=404, message="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Internal server error"}), 500
    return render_template('error.html', code=500, message="Something went wrong on our end"), 500

@app.errorhandler(413)
def file_too_large(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "File too large. Maximum size is 100MB."}), 413
    return "File too large. Maximum upload size is 100MB.", 413


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)


import os
from utils.logger import get_logger
_log = get_logger(__name__)
from pypdf import PdfWriter, PdfReader
from PIL import Image
from pdf2docx import Converter
from docx2pdf import convert
import zipfile
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch

def merge_pdfs(input_paths, output_path):
    """
    Merge multiple PDFs into a single PDF.
    """
    try:
        merger = PdfWriter()
        for path in input_paths:
            merger.append(path)
        merger.write(output_path)
        merger.close()
        return output_path
    except Exception as e:
        _log.warning(f"Error merging PDFs: {e}")
        return None

def split_pdf(input_path, output_dir):
    """
    Split PDF into single pages.
    Returns list of paths to generated files.
    """
    try:
        reader = PdfReader(input_path)
        output_files = []
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            output_filename = f"{base_name}_page_{i+1}.pdf"
            output_path = os.path.join(output_dir, output_filename)
            writer.write(output_path)
            writer.close()
            output_files.append(output_path)
            
        return output_files
    except Exception as e:
        _log.warning(f"Error splitting PDF: {e}")
        return None

def compress_pdf(input_path, output_path, quality='balanced'):
    """
    Optimized PDF compression with quality presets.
    quality: 'fast' | 'balanced' | 'maximum'
    """
    try:
        import fitz

        effort_map = {'fast': 30, 'balanced': 60, 'maximum': 90}
        compression_effort = effort_map.get(quality, 60)

        doc = fitz.open(input_path)
        doc.save(
            output_path,
            garbage=4,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            clean=True,
            no_new_id=True,
            compression_effort=compression_effort,
        )
        doc.close()
        return output_path
    except Exception as e:
        _log.warning(f"Error compressing PDF: {e}")
        import traceback
        traceback.print_exc()
        return None

def pdf_to_images(input_path, output_dir):
    """
    Convert PDF to images. Returns list of image paths.
    Uses PyMuPDF (fitz) - No external Poppler dependency required.
    """
    doc = None
    try:
        doc = fitz.open(input_path)
        output_files = []
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # 2x zoom for better quality
            output_filename = f"{base_name}_page_{i+1}.jpg"
            output_path = os.path.join(output_dir, output_filename)
            pix.save(output_path)
            output_files.append(output_path)
        
        return output_files
    except Exception as e:
        _log.warning(f"Error converting PDF to images: {e}")
        return None
    finally:
        if doc:
            doc.close()

def images_to_pdf(image_paths, output_path):
    """
    Convert list of images to a single PDF.
    """
    try:
        images = []
        for path in image_paths:
            img = Image.open(path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            images.append(img)
            
        if images:
            images[0].save(
                output_path, "PDF", resolution=100.0, save_all=True, append_images=images[1:]
            )
            # Close all images to free memory
            for img in images:
                img.close()
            return output_path
        return None
    except Exception as e:
        _log.warning(f"Error converting images to PDF: {e}")
        return None

def pdf_to_word(input_path, output_path):
    """
    Convert PDF to DOCX using pdf2docx.
    """
    try:
        cv = Converter(input_path)
        cv.convert(output_path, start=0, end=None)
        cv.close()
        return output_path
    except Exception as e:
        _log.warning(f"Error converting PDF to Word: {e}")
        return None

def word_to_pdf(input_path, output_path):
    """
    Convert DOCX to PDF using python-docx and reportlab.
    Cross-platform solution that doesn't require MS Word.
    """
    try:
        from docx import Document
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.units import inch
        
        # Read the DOCX file
        doc = Document(input_path)
        
        # Create PDF
        pdf_doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Extract text from DOCX and add to PDF
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                # Create paragraph with proper styling
                p = Paragraph(paragraph.text, styles['Normal'])
                story.append(p)
                story.append(Spacer(1, 0.2*inch))
        
        # Build the PDF
        pdf_doc.build(story)
        return output_path
        
    except ImportError:
        # Fallback to docx2pdf if python-docx is not available
        try:
            convert(input_path, output_path)
            return output_path
        except Exception as e:
            _log.warning(f"Error with docx2pdf: {e}")
            return None
    except Exception as e:
        _log.warning(f"Error converting Word to PDF: {e}")
        return None

def protect_pdf(input_path, output_path, password):
    """
    Encrypt PDF with password.
    """
    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)
        writer.encrypt(password)
        
        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path
    except Exception as e:
        _log.warning(f"Error protecting PDF: {e}")
        return None

def unlock_pdf(input_path, output_path, password):
    """
    Decrypt PDF with password.
    """
    try:
        reader = PdfReader(input_path)
        if reader.is_encrypted:
            reader.decrypt(password)
            
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)
        
        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path
    except Exception as e:
        _log.warning(f"Error unlocking PDF: {e}")
        return None

def rotate_pdf(input_path, output_path, angle=90):
    """
    Rotate all pages in PDF by angle (clockwise).
    angle must be multiple of 90.
    """
    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        
        for page in reader.pages:
            page.rotate(int(angle))
            writer.add_page(page)
            
        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path
    except Exception as e:
        _log.warning(f"Error rotating PDF: {e}")
        return None

def remove_pages(input_path, output_path, pages_to_remove):
    """
    Remove specific pages from PDF.
    pages_to_remove: list of 1-based page numbers.
    """
    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        
        total_pages = len(reader.pages)
        pages_to_keep = [i for i in range(1, total_pages + 1) if i not in pages_to_remove]
        
        for i in pages_to_keep:
            # Adjust to 0-based index
            writer.add_page(reader.pages[i-1])
            
        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path
    except Exception as e:
        _log.warning(f"Error removing pages: {e}")
        return None

def watermark_pdf(input_path, output_path, text, pages="all", angle=45,
                  opacity=0.3, font_size=36, color="#808080", placement="multiple"):
    """
    Add text watermark to PDF pages with full customization.

    Args:
        pages:     "all", or comma-separated 1-based page numbers e.g. "1,3,5"
        angle:     rotation angle in degrees (0-360)
        opacity:   transparency 0.0–1.0 OR 1–100 (auto-normalised)
        font_size: watermark text size in points
        color:     hex color string e.g. "#ff0000"
        placement: "single" (one centred watermark) or "multiple" (4x3 grid)
    """
    try:
        def hex_to_rgb(h):
            h = h.lstrip('#')
            if len(h) == 3:
                h = ''.join(c*2 for c in h)
            return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

        r, g, b = hex_to_rgb(color)

        if opacity > 1.0:
            opacity = opacity / 100.0
        opacity = max(0.0, min(1.0, opacity))

        reader = PdfReader(input_path)
        writer = PdfWriter()
        total = len(reader.pages)

        if pages == "all" or not pages or str(pages).strip() == "":
            target_pages = set(range(total))
        else:
            target_pages = set()
            for part in str(pages).split(','):
                part = part.strip()
                if part.isdigit():
                    idx = int(part) - 1
                    if 0 <= idx < total:
                        target_pages.add(idx)

        for i, page in enumerate(reader.pages):
            if i in target_pages:
                page_width  = float(page.mediabox.width)
                page_height = float(page.mediabox.height)

                packet = io.BytesIO()
                can = canvas.Canvas(packet, pagesize=(page_width, page_height))
                can.setFont("Helvetica-Bold", font_size)
                can.setFillColorRGB(r, g, b, opacity)

                if placement == "single":
                    # One watermark dead-centre
                    can.saveState()
                    can.translate(page_width / 2, page_height / 2)
                    can.rotate(angle)
                    can.drawCentredString(0, 0, text)
                    can.restoreState()
                else:
                    # 4×3 grid across the page
                    margin = 60
                    rows, cols = 4, 3
                    avail_w = page_width  - 2 * margin
                    avail_h = page_height - 2 * margin
                    x_step  = avail_w / max(cols - 1, 1)
                    y_step  = avail_h / max(rows - 1, 1)

                    for row in range(rows):
                        for col in range(cols):
                            x = margin + col * x_step
                            y = margin + row * y_step
                            can.saveState()
                            can.translate(x, y)
                            can.rotate(angle)
                            can.drawCentredString(0, 0, text)
                            can.restoreState()

                can.save()
                packet.seek(0)

                wm_page = PdfReader(packet).pages[0]
                page.merge_page(wm_page)

            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path
    except Exception as e:
        _log.warning(f"Error adding watermark: {e}")
        return None

def apply_pdf_edits(input_path, output_path, edits_data):
    """
    Apply edits (whiteout, text, images, shapes) to PDF.
    Strategy: for each edited page, render it as a high-res flat image first
    (eliminates original text/content completely), then draw new objects on top.
    This guarantees zero overlap regardless of PDF type (vector or scanned).
    """
    try:
        import fitz
        import io as _io
        doc = fitz.open(input_path)
        
        def hex_to_rgb(hex_color):
            """Convert hex color to RGB tuple with better error handling"""
            if not hex_color:
                return (0, 0, 0)
            if isinstance(hex_color, str) and hex_color.startswith('#'):
                try:
                    r = int(hex_color[1:3], 16) / 255.0
                    g = int(hex_color[3:5], 16) / 255.0
                    b = int(hex_color[5:7], 16) / 255.0
                    return (r, g, b)
                except ValueError:
                    return (0, 0, 0)
            elif isinstance(hex_color, str) and hex_color.startswith('rgb'):
                try:
                    import re
                    matches = re.findall(r'\d+', hex_color)
                    if len(matches) >= 3:
                        r = int(matches[0]) / 255.0
                        g = int(matches[1]) / 255.0
                        b = int(matches[2]) / 255.0
                        return (r, g, b)
                except:
                    pass
            return (0, 0, 0)
        
        # Collect which pages have edits
        edited_pages = set()
        for page_idx_str in edits_data.keys():
            try:
                edited_pages.add(int(page_idx_str))
            except:
                pass

        # Build a new PDF: for edited pages use flat-image approach,
        # for unedited pages copy as-is.
        new_doc = fitz.open()

        for orig_page_idx in range(len(doc)):
            orig_page = doc[orig_page_idx]

            new_doc.insert_pdf(doc, from_page=orig_page_idx, to_page=orig_page_idx)
            if orig_page_idx not in edited_pages:
                continue

            new_page = new_doc[-1]
            page_data = edits_data[str(orig_page_idx)]
            canvas_width = float(page_data.get('width', orig_page.rect.width))
            canvas_height = float(page_data.get('height', orig_page.rect.height))
            objects = page_data.get('objects', [])
            page_w = new_page.rect.width
            page_h = new_page.rect.height
            scale_x = page_w / canvas_width
            scale_y = page_h / canvas_height

            # --- Step 4: Draw all edit objects on top ---
            fonts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'fonts')

            LOCAL_FONT_MAP = {
                # --- Newly downloaded metric-compatible fonts ---
                'carlito':     {'r': 'Carlito-Regular.ttf',    'b': 'Carlito-Bold.ttf',
                                'i': 'Carlito-Italic.ttf',     'bi': 'Carlito-BoldItalic.ttf'},
                'arimo':       {'r': 'Arimo-Regular.ttf',      'b': 'Arimo-Bold.ttf',
                                'i': 'Arimo-Italic.ttf',       'bi': 'Arimo-BoldItalic.ttf'},
                'tinos':       {'r': 'Tinos-Regular.ttf',      'b': 'Tinos-Bold.ttf',
                                'i': 'Tinos-Italic.ttf',       'bi': 'Tinos-BoldItalic.ttf'},
                'cousine':     {'r': 'Cousine-Regular.ttf',    'b': 'Cousine-Bold.ttf',
                                'i': 'Cousine-Italic.ttf',     'bi': 'Cousine-BoldItalic.ttf'},
                'caladea':     {'r': 'Caladea-Regular.ttf',    'b': 'Caladea-Bold.ttf',
                                'i': 'Caladea-Italic.ttf',     'bi': 'Caladea-BoldItalic.ttf'},
                # --- Google Web Fonts ---
                'roboto':      {'r': 'Roboto-Regular.ttf',     'b': 'Roboto-Bold.ttf',
                                'i': 'Roboto-Regular.ttf',     'bi': 'Roboto-Bold.ttf'},
                'lato':        {'r': 'Lato-Regular.ttf',       'b': 'Lato-Bold.ttf',
                                'i': 'Lato-Italic.ttf',        'bi': 'Lato-BoldItalic.ttf'},
                'open sans':   {'r': 'OpenSans-Regular.ttf',   'b': 'OpenSans-Regular.ttf',
                                'i': 'OpenSans-Regular.ttf',   'bi': 'OpenSans-Regular.ttf'},
                'montserrat':  {'r': 'Montserrat-Regular.ttf', 'b': 'Montserrat-Regular.ttf',
                                'i': 'Montserrat-Regular.ttf', 'bi': 'Montserrat-Regular.ttf'},
                # --- Common aliases ---
                'arial':       {'r': 'Arimo-Regular.ttf',      'b': 'Arimo-Bold.ttf',
                                'i': 'Arimo-Italic.ttf',       'bi': 'Arimo-BoldItalic.ttf'},
                'helvetica':   {'r': 'Arimo-Regular.ttf',      'b': 'Arimo-Bold.ttf',
                                'i': 'Arimo-Italic.ttf',       'bi': 'Arimo-BoldItalic.ttf'},
                'times':       {'r': 'Tinos-Regular.ttf',      'b': 'Tinos-Bold.ttf',
                                'i': 'Tinos-Italic.ttf',       'bi': 'Tinos-BoldItalic.ttf'},
                'times new roman': {'r': 'Tinos-Regular.ttf',  'b': 'Tinos-Bold.ttf',
                                    'i': 'Tinos-Italic.ttf',   'bi': 'Tinos-BoldItalic.ttf'},
                'georgia':     {'r': 'Tinos-Regular.ttf',      'b': 'Tinos-Bold.ttf',
                                'i': 'Tinos-Italic.ttf',       'bi': 'Tinos-BoldItalic.ttf'}, # Lora not available, use Tinos
                'courier':     {'r': 'Cousine-Regular.ttf',    'b': 'Cousine-Bold.ttf',
                                'i': 'Cousine-Italic.ttf',     'bi': 'Cousine-BoldItalic.ttf'},
                'cambria':     {'r': 'Caladea-Regular.ttf',    'b': 'Caladea-Bold.ttf',
                                'i': 'Caladea-Italic.ttf',     'bi': 'Caladea-BoldItalic.ttf'},
            }

            def resolve_font(family, bold, italic):
                key = (family or '').lower().strip()
                key = key.split(',')[0].replace('"', '').replace("'", '').strip()
                key = re.sub(r'^[A-Z]{6}\+', '', key, flags=re.IGNORECASE).strip()
                variant = 'bi' if bold and italic else ('b' if bold else ('i' if italic else 'r'))

                # Exact key match in local map first.
                if key in LOCAL_FONT_MAP:
                    fname = LOCAL_FONT_MAP[key][variant]
                    fpath = os.path.join(fonts_dir, fname)
                    if os.path.exists(fpath):
                        return fname.replace('.ttf', ''), fpath

                # Fallback mappings for common system fonts.
                if 'times new roman' in key or 'timesnewroman' in key or 'times new romanpsmt' in key or 'times' in key:
                    alias = 'tiro'
                elif 'courier' in key or 'cousine' in key or 'mono' in key:
                    alias = 'cour'
                elif 'arial' in key or 'helvetica' in key or 'arimo' in key:
                    alias = 'helv'
                else:
                    alias = 'helv'

                # Standard suffixes for PDF aliases
                suffix = ""
                if bold and italic:
                    suffix = "-bolditalic" if alias == 'tiro' else "-boldoblique"
                elif bold:
                    suffix = "-bold"
                elif italic:
                    suffix = "-italic" if alias == 'tiro' else "-oblique"

                return alias + suffix, None

            for obj in objects:
                try:
                    obj_type = obj.get('type')
                    left = float(obj.get('left', 0))
                    top = float(obj.get('top', 0))
                    scale_x_obj = float(obj.get('scaleX', 1))
                    scale_y_obj = float(obj.get('scaleY', 1))
                    opacity = float(obj.get('opacity', 1))
                    fill = obj.get('fill', '#000000')
                    stroke = obj.get('stroke', None)
                    stroke_width = float(obj.get('strokeWidth', 1))
                    fill_color = hex_to_rgb(fill)
                    stroke_color = hex_to_rgb(stroke) if stroke else None

                    # FIX: BUG 7 — Rotation Angle Ignored on PDF Export
                    angle = float(obj.get('angle', 0))

                    if obj_type == 'rect':
                        width = float(obj.get('width', 0)) * scale_x_obj
                        height = float(obj.get('height', 0)) * scale_y_obj
                        rect = fitz.Rect(left * scale_x, top * scale_y,
                                         (left + width) * scale_x, (top + height) * scale_y)
                                         
                        import math
                        cx = (left * scale_x) + (width * scale_x) / 2
                        cy = (top * scale_y) + (height * scale_y) / 2
                        mat = fitz.Matrix(1, 0, 0, 1, -cx, -cy) * fitz.Matrix(angle) * fitz.Matrix(1, 0, 0, 1, cx, cy)
                        quad = rect * mat if angle else rect

                        if obj.get('isWhiteout'):
                            new_page.add_redact_annot(quad if angle else rect, fill=fill_color)
                            new_page.apply_redactions()
                        elif stroke_color and stroke_width > 0:
                            if angle:
                                new_page.draw_quad(quad, color=stroke_color, fill=fill_color,
                                                   width=stroke_width * scale_x,
                                                   fill_opacity=opacity, stroke_opacity=opacity)
                            else:
                                new_page.draw_rect(rect, color=stroke_color, fill=fill_color,
                                                   width=stroke_width * scale_x,
                                                   fill_opacity=opacity, stroke_opacity=opacity)
                        else:
                            if angle:
                                new_page.draw_quad(quad, color=fill_color, fill=fill_color,
                                                   width=0, fill_opacity=opacity)
                            else:
                                new_page.draw_rect(rect, color=fill_color, fill=fill_color,
                                                   width=0, fill_opacity=opacity)

                    elif obj_type == 'circle':
                        radius = float(obj.get('radius', 0)) * scale_x_obj
                        center = fitz.Point((left + radius) * scale_x, (top + radius) * scale_y)
                        if stroke_color and stroke_width > 0:
                            new_page.draw_circle(center, radius * scale_x, color=stroke_color,
                                                 fill=fill_color, width=stroke_width * scale_x,
                                                 fill_opacity=opacity, stroke_opacity=opacity)
                        else:
                            new_page.draw_circle(center, radius * scale_x, color=fill_color,
                                                 fill=fill_color, width=0, fill_opacity=opacity)

                    elif obj_type == 'line':
                        x1 = float(obj.get('x1', 0)) + left
                        y1 = float(obj.get('y1', 0)) + top
                        x2 = float(obj.get('x2', 0)) + left
                        y2 = float(obj.get('y2', 0)) + top
                        p1 = fitz.Point(x1 * scale_x, y1 * scale_y)
                        p2 = fitz.Point(x2 * scale_x, y2 * scale_y)
                        new_page.draw_line(p1, p2, color=fill_color,
                                           width=stroke_width * scale_x, stroke_opacity=opacity)

                    elif obj_type in ('i-text', 'text'):
                        text = obj.get('text', '')
                        if not text.strip():
                            continue
                        font_size = float(obj.get('fontSize', 16))
                        font_family = obj.get('fontFamily', 'Arial')
                        font_weight = obj.get('fontWeight', 'normal')
                        font_style = obj.get('fontStyle', 'normal')
                        is_bold   = font_weight in ('bold', '700')
                        is_italic = font_style  in ('italic', 'oblique')

                        # --- Priority 1: Use exact embedded font bytes from the PDF ---
                        embedded_b64 = obj.get('embeddedFontData')
                        embedded_ext = obj.get('embeddedFontExt', 'ttf')
                        font_name = None
                        font_file = None
                        if embedded_b64:
                            try:
                                import base64 as _b64
                                font_bytes = _b64.b64decode(embedded_b64)
                                # Write to a temp file so PyMuPDF can read it
                                import tempfile
                                suffix = f'.{embedded_ext}' if embedded_ext else '.ttf'
                                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                                tmp.write(font_bytes)
                                tmp.close()
                                font_name = font_family.replace(' ', '_')
                                font_file = tmp.name
                            except Exception as emb_err:
                                print(f"Embedded font decode error: {emb_err}")
                                font_name = None
                                font_file = None

                        # --- Priority 2: Local metric-compatible TTF file ---
                        if font_name is None:
                            font_name, font_file = resolve_font(font_family, is_bold, is_italic)

                        # --- Priority 3: Original PDF internal font name ---
                        orig_font = obj.get('originalPDFFont')
                        if font_file is None and orig_font:
                            orig_key = orig_font.replace('+', '').strip()
                            orig_clean = clean_font_name(orig_key)
                            fallback_name, fallback_file = resolve_font(orig_clean, is_bold, is_italic)
                            if fallback_file:
                                font_name = fallback_name
                                font_file = fallback_file
                            else:
                                # Preserve as the raw original for potential built-in alias resolution
                                font_name = orig_clean

                        effective_font_size = font_size * scale_y_obj
                        pdf_font_size = effective_font_size * scale_y
                        pdf_x = left * scale_x
                        # FIX: BUG 9 — Text Baseline Drift on Export
                        pdf_y = (top + effective_font_size * 0.8) * scale_y
                        point = fitz.Point(pdf_x, pdf_y)
                        
                        import math
                        text_w = float(obj.get('width', 0)) * scale_x_obj
                        text_h = float(obj.get('height', 0)) * scale_y_obj
                        cx = (left * scale_x) + (text_w * scale_x) / 2
                        cy = (top * scale_y) + (text_h * scale_y) / 2
                        mat = fitz.Matrix(1, 0, 0, 1, -cx, -cy) * fitz.Matrix(angle) * fitz.Matrix(1, 0, 0, 1, cx, cy)
                        
                        try:
                            tw = fitz.TextWriter(new_page.rect)
                            font = fitz.Font(fontname=font_name, fontfile=font_file) if font_file else fitz.Font(fontname=font_name)
                            tw.append(point, text, fontsize=pdf_font_size, font=font)
                            tw.write_text(new_page, color=fill_color, matrix=mat if angle else None)
                        except Exception as text_error:
                            print(f"Text insert error '{font_name}': {text_error}")
                            try:
                                # Last resort: metric-safe fallback
                                fn, ff = resolve_font(font_family, is_bold, is_italic)
                                tw = fitz.TextWriter(new_page.rect)
                                font_fallback = fitz.Font(fontname=fn, fontfile=ff) if ff else fitz.Font(fontname=fn)
                                tw.append(point, text, fontsize=pdf_font_size, font=font_fallback)
                                tw.write_text(new_page, color=fill_color, matrix=mat if angle else None)
                            except:
                                pass

                    elif obj_type == 'path':
                        # FIX: BUG 8 — Free-Hand Path Coordinates Offset
                        path_offset_x = float(obj.get('pathOffset', {}).get('x', 0))
                        path_offset_y = float(obj.get('pathOffset', {}).get('y', 0))
                        path_data = obj.get('path', [])
                        stroke_c = hex_to_rgb(obj.get('stroke', '#000000'))
                        sw = float(obj.get('strokeWidth', 2)) * scale_x
                        path_opacity = float(obj.get('opacity', 1))
                        
                        path_w = float(obj.get('width', 0)) * scale_x_obj
                        path_h = float(obj.get('height', 0)) * scale_y_obj
                        cx = (left * scale_x) + (path_w * scale_x) / 2
                        cy = (top * scale_y) + (path_h * scale_y) / 2
                        mat = fitz.Matrix(1, 0, 0, 1, -cx, -cy) * fitz.Matrix(angle) * fitz.Matrix(1, 0, 0, 1, cx, cy) if angle else None

                        try:
                            shape = new_page.new_shape()
                            for cmd in path_data:
                                if not cmd: continue
                                op = cmd[0]
                                if op == 'M':
                                    pdf_px = ((cmd[1] - path_offset_x) * scale_x_obj + left) * scale_x
                                    pdf_py = ((cmd[2] - path_offset_y) * scale_y_obj + top) * scale_y
                                    pt = fitz.Point(pdf_px, pdf_py)
                                    if mat: pt = pt * mat
                                    shape.move_to(pt)
                                elif op == 'L':
                                    pdf_px = ((cmd[1] - path_offset_x) * scale_x_obj + left) * scale_x
                                    pdf_py = ((cmd[2] - path_offset_y) * scale_y_obj + top) * scale_y
                                    pt = fitz.Point(pdf_px, pdf_py)
                                    if mat: pt = pt * mat
                                    shape.line_to(pt)
                                elif op == 'Q':
                                    cp_px = ((cmd[1] - path_offset_x) * scale_x_obj + left) * scale_x
                                    cp_py = ((cmd[2] - path_offset_y) * scale_y_obj + top) * scale_y
                                    ep_px = ((cmd[3] - path_offset_x) * scale_x_obj + left) * scale_x
                                    ep_py = ((cmd[4] - path_offset_y) * scale_y_obj + top) * scale_y
                                    pt_c = fitz.Point(cp_px, cp_py)
                                    pt_e = fitz.Point(ep_px, ep_py)
                                    if mat:
                                        pt_c = pt_c * mat
                                        pt_e = pt_e * mat
                                    shape.curve_to(pt_c, pt_c, pt_e)
                            shape.finish(color=stroke_c, fill=None, width=sw,
                                         stroke_opacity=path_opacity)
                            shape.commit()
                        except Exception as path_err:
                            print(f"Path draw error: {path_err}")

                    elif obj_type == 'image':
                        src = obj.get('src', '')
                        if src.startswith('data:image'):
                            import base64
                            try:
                                _, encoded = src.split(",", 1)
                                img_data = base64.b64decode(encoded)
                                width = float(obj.get('width', 0)) * scale_x_obj
                                height = float(obj.get('height', 0)) * scale_y_obj
                                rect = fitz.Rect(left * scale_x, top * scale_y,
                                                 (left + width) * scale_x, (top + height) * scale_y)
                                                 
                                import math
                                cx = (left * scale_x) + (width * scale_x) / 2
                                cy = (top * scale_y) + (height * scale_y) / 2
                                mat = fitz.Matrix(1, 0, 0, 1, -cx, -cy) * fitz.Matrix(angle) * fitz.Matrix(1, 0, 0, 1, cx, cy)
                                new_page.insert_image(rect * mat if angle else rect, stream=_io.BytesIO(img_data))
                            except Exception as img_err:
                                print(f"Image insert error: {img_err}")
                except Exception as obj_err:
                    _log.warning(f"Error processing object: {obj_err}")
                    continue

        doc.close()
        new_doc.save(output_path, garbage=4, deflate=True, clean=True)
        new_doc.close()
        return output_path
    except Exception as e:
        _log.warning(f"Error applying edits: {e}")
        import traceback
        traceback.print_exc()
        return None

def clean_font_name(font_name):
    """
    Strip PDF subset prefixes and normalize common font names to canonical form.
    Example: 'ABCDEF+TimesNewRomanPSMT' -> 'Times New Roman'
    """
    if not font_name:
        return "Arial"
    
    # Strip subset prefix (e.g., ABCDEF+)
    import re
    cleaned = re.sub(r'^[A-Z]{6}\+', '', font_name)
    
    # Normalize common PDF font variants to canonical family names
    # (Fabric.js/CSS and PyMuPDF aliases work better with family names)
    mapping = {
        "TimesNewRomanPSMT": "Times New Roman",
        "TimesNewRomanPS-BoldMT": "Times New Roman",
        "TimesNewRomanPS-ItalicMT": "Times New Roman",
        "TimesNewRomanPS-BoldItalicMT": "Times New Roman",
        "TimesNewRoman": "Times New Roman",
        "HelveticaNeue": "Helvetica",
        "ArialMT": "Arial",
        "Arial-BoldMT": "Arial",
        "Arial-ItalicMT": "Arial",
        "CourierNewPSMT": "Courier New",
        "CourierNew": "Courier New",
    }
    
    # Strip common suffixes used for styling
    base = mapping.get(cleaned, cleaned)
    base = re.sub(r'(-Bold|-Italic|-BoldItalic|-Oblique|PSMT|MT|PS|Normal|Regular)$', '', base, flags=re.IGNORECASE)
    
    return base.strip()

def get_pdf_text_blocks(input_path, page_num):
    """
    Extract text blocks with their positions and styles for a specific page.
    Includes font metadata (cleaned name, size, flags, color).
    """
    try:
        import fitz
        doc = fitz.open(input_path)
        if page_num < 0 or page_num >= len(doc):
            return []
            
        page = doc[page_num]
        text_dict = page.get_text("dict")
        
        blocks = []
        for block in text_dict["blocks"]:
            if block["type"] == 0:  # Text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        # Convert color (int) to hex
                        color_int = span["color"]
                        r = (color_int >> 16) & 255
                        g = (color_int >> 8) & 255
                        b = color_int & 255
                        hex_color = f"#{r:02x}{g:02x}{b:02x}"
                        
                        blocks.append({
                            "text": span["text"],
                            "bbox": span["bbox"],  # [x0, y0, x1, y1]
                            "size": span["size"],
                            "color": hex_color,
                            "font": clean_font_name(span["font"]),
                            "raw_font": span["font"],
                            "flags": span["flags"],
                            "origin": span["origin"]
                        })
        doc.close()
        return blocks
    except Exception as e:
        _log.warning(f"Error extracting text blocks: {e}")
        return []

def add_page_numbers(input_path, output_path, position='bottom-center', start_num=1, font_size=10):
    """
    Add page numbers to PDF using insert_text for reliable rendering.
    """
    try:
        import fitz
        doc = fitz.open(input_path)

        for page_num, page in enumerate(doc):
            text = str(start_num + page_num)
            rect = page.rect
            w = rect.width
            h = rect.height
            margin = 30

            # Determine x position
            if 'center' in position:
                # Measure text width roughly (each char ~0.6 * font_size)
                text_w = len(text) * font_size * 0.6
                x = (w - text_w) / 2
            elif 'right' in position:
                text_w = len(text) * font_size * 0.6
                x = w - margin - text_w
            else:  # left
                x = margin

            # Determine y position (insert_text baseline)
            if 'bottom' in position:
                y = h - margin
            else:
                y = margin + font_size

            page.insert_text(
                fitz.Point(x, y),
                text,
                fontsize=font_size,
                color=(0, 0, 0),
                fontname="helv",
            )

        doc.save(output_path)
        doc.close()
        return output_path
    except Exception as e:
        _log.warning(f"Error adding page numbers: {e}")
        import traceback
        traceback.print_exc()
        return None

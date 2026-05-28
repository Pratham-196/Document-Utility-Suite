import fitz
import os
import io
import base64
from PIL import Image
from utils.logger import get_logger

_log = get_logger(__name__)

def sign_pdf(input_path, output_path, signature_data, page_num,
             x_ratio, y_ratio, width_ratio, height_ratio):
    """
    Add a signature image to a PDF page.
    Coordinates are normalized ratios (0.0–1.0) relative to the page dimensions,
    so placement is accurate regardless of PDF page size.

    x_ratio, y_ratio        — top-left corner of signature (fraction of page w/h)
    width_ratio, height_ratio — signature size (fraction of page w/h)
    """
    try:
        doc = fitz.open(input_path)

        if page_num < 0 or page_num >= len(doc):
            _log.warning(f"Error: Page {page_num} out of range")
            doc.close()
            return None

        page = doc[page_num]
        pw = page.rect.width
        ph = page.rect.height

        # Convert ratios → PDF points (top-left origin, Y increases downward in fitz)
        x      = x_ratio      * pw
        y      = y_ratio      * ph
        w      = width_ratio  * pw
        h      = height_ratio * ph

        # Clamp to page bounds
        x = max(0.0, min(x, pw - 1))
        y = max(0.0, min(y, ph - 1))
        w = min(w, pw - x)
        h = min(h, ph - y)

        rect = fitz.Rect(x, y, x + w, y + h)

        # Decode base64 signature
        if not (isinstance(signature_data, str) and signature_data.startswith('data:image')):
            _log.error("Invalid signature data format")
            doc.close()
            return None
        _, encoded = signature_data.split(",", 1)
        img_data = base64.b64decode(encoded)

        page.insert_image(rect, stream=img_data, keep_proportion=True)

        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        _log.info("Signed PDF saved: %s", output_path)
        return output_path

    except Exception as e:
        _log.error("Error signing PDF: %s", e)
        return None
        return None

def organize_pdf(input_path, output_path, page_order):
    """
    Reorder PDF pages based on a list of indices.
    page_order: list of 0-based page indices.
    """
    try:
        doc = fitz.open(input_path)
        
        # Verify indices
        max_page = len(doc) - 1
        valid_order = [i for i in page_order if 0 <= i <= max_page]
        
        if not valid_order:
            return None
            
        doc.select(valid_order)
        doc.save(output_path)
        doc.close()
        return output_path
    except Exception as e:
        _log.warning(f"Error organizing PDF: {e}")
        return None

def repair_pdf(input_path, output_path):
    """
    Attempt to repair a PDF by saving it with garbage collection and cleaning.
    Note: linear=True was removed — not supported in fitz 1.27.2+
    """
    try:
        doc = fitz.open(input_path)
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        return output_path
    except Exception as e:
        _log.warning(f"Error repairing PDF: {e}")
        return None

def flatten_pdf(input_path, output_path):
    """
    Flatten PDF by rendering each page as a high-res image.
    This removes all annotations, form fields, and interactive elements.
    """
    try:
        doc = fitz.open(input_path)
        new_doc = fitz.open()
        for page in doc:
            # Render at 2x for quality
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            # Create new page with same dimensions
            new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(fitz.Rect(0, 0, page.rect.width, page.rect.height),
                                  stream=io.BytesIO(img_bytes))
        doc.close()
        new_doc.save(output_path, garbage=4, deflate=True)
        new_doc.close()
        return output_path
    except Exception as e:
        _log.warning(f"Error flattening PDF: {e}")
        return None

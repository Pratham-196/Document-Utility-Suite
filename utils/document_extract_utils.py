"""
Utility functions for extracting text from various document formats.
Supports: PDF, Images, PPTX, DOCX, Excel, TXT, and more.
"""

import os
from typing import Optional

def extract_text_from_pptx(filepath: str) -> str:
    """Extract text from PowerPoint files (.pptx)"""
    try:
        from pptx import Presentation
        
        presentation = Presentation(filepath)
        text_content = []
        
        for slide_num, slide in enumerate(presentation.slides, 1):
            text_content.append(f"\n--- Slide {slide_num} ---\n")
            
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    text_content.append(shape.text + "\n")
        
        full_text = "".join(text_content)
        return full_text.strip() if full_text.strip() else "No text found in presentation"
        
    except ImportError:
        return "ERROR: python-pptx is not installed. Install it with: pip install python-pptx"
    except Exception as e:
        return f"Error extracting text from PPTX: {str(e)}"

def extract_text_from_docx(filepath: str) -> str:
    """Extract text from Word documents (.docx)"""
    try:
        from docx import Document
        
        doc = Document(filepath)
        text_content = []
        
        for para in doc.paragraphs:
            if para.text.strip():
                text_content.append(para.text)
        
        # Also extract text from tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        text_content.append(cell.text)
        
        full_text = "\n".join(text_content)
        return full_text.strip() if full_text.strip() else "No text found in document"
        
    except ImportError:
        return "ERROR: python-docx is not installed. Install it with: pip install python-docx"
    except Exception as e:
        return f"Error extracting text from DOCX: {str(e)}"

def extract_text_from_excel(filepath: str) -> str:
    """Extract text from Excel files (.xlsx, .xls)"""
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter
        
        workbook = openpyxl.load_workbook(filepath)
        text_content = []
        
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            text_content.append(f"\n--- Sheet: {sheet_name} ---\n")
            
            for row in sheet.iter_rows(values_only=True):
                row_text = []
                for cell_value in row:
                    if cell_value is not None:
                        row_text.append(str(cell_value))
                if row_text:
                    text_content.append(" | ".join(row_text))
        
        full_text = "\n".join(text_content)
        return full_text.strip() if full_text.strip() else "No data found in Excel file"
        
    except ImportError:
        return "ERROR: openpyxl is not installed. Install it with: pip install openpyxl"
    except Exception as e:
        return f"Error extracting text from Excel: {str(e)}"

def extract_text_from_txt(filepath: str) -> str:
    """Extract text from plain text files (.txt)"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return content.strip() if content.strip() else "File is empty"
    except UnicodeDecodeError:
        # Try with different encoding
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
            return content.strip() if content.strip() else "File is empty"
        except Exception as e:
            return f"Error reading text file: {str(e)}"
    except Exception as e:
        return f"Error extracting text from TXT: {str(e)}"

def extract_text_from_markdown(filepath: str) -> str:
    """Extract text from markdown files (.md)"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return content.strip() if content.strip() else "File is empty"
    except Exception as e:
        return f"Error extracting text from Markdown: {str(e)}"

def extract_text_from_csv(filepath: str) -> str:
    """Extract text from CSV files (.csv)"""
    try:
        import csv
        
        text_content = []
        with open(filepath, 'r', encoding='utf-8') as f:
            csv_reader = csv.reader(f)
            for row in csv_reader:
                if any(cell.strip() for cell in row):
                    text_content.append(" | ".join(row))
        
        full_text = "\n".join(text_content)
        return full_text.strip() if full_text.strip() else "No data found in CSV file"
        
    except Exception as e:
        return f"Error extracting text from CSV: {str(e)}"

def extract_text_from_json(filepath: str) -> str:
    """Extract text from JSON files (.json)"""
    try:
        import json
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Convert JSON to readable format
        formatted_text = json.dumps(data, indent=2)
        return formatted_text if formatted_text.strip() else "File is empty"
        
    except Exception as e:
        return f"Error extracting text from JSON: {str(e)}"

def extract_text_from_html(filepath: str) -> str:
    """Extract text from HTML files (.html, .htm)"""
    try:
        from html.parser import HTMLParser
        
        class HTMLTextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
            
            def handle_data(self, data):
                text = data.strip()
                if text:
                    self.text.append(text)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        extractor = HTMLTextExtractor()
        extractor.feed(html_content)
        
        full_text = "\n".join(extractor.text)
        return full_text if full_text.strip() else "No text content found in HTML file"
        
    except Exception as e:
        return f"Error extracting text from HTML: {str(e)}"

def extract_text_from_document(filepath: str) -> str:
    """
    Universal document text extraction function.
    Automatically detects file type and extracts text accordingly.
    """
    if not os.path.exists(filepath):
        return f"Error: File not found: {filepath}"
    
    filename = os.path.basename(filepath).lower()
    file_ext = os.path.splitext(filename)[1].lower()
    
    # Dispatch to appropriate extraction function
    extractors = {
        '.pdf': lambda path: __import__('utils.ocr_utils', fromlist=['extract_text_from_pdf']).extract_text_from_pdf(path),
        '.png': lambda path: __import__('utils.ocr_utils', fromlist=['extract_text_from_image']).extract_text_from_image(path),
        '.jpg': lambda path: __import__('utils.ocr_utils', fromlist=['extract_text_from_image']).extract_text_from_image(path),
        '.jpeg': lambda path: __import__('utils.ocr_utils', fromlist=['extract_text_from_image']).extract_text_from_image(path),
        '.bmp': lambda path: __import__('utils.ocr_utils', fromlist=['extract_text_from_image']).extract_text_from_image(path),
        '.tiff': lambda path: __import__('utils.ocr_utils', fromlist=['extract_text_from_image']).extract_text_from_image(path),
        '.gif': lambda path: __import__('utils.ocr_utils', fromlist=['extract_text_from_image']).extract_text_from_image(path),
        '.webp': lambda path: __import__('utils.ocr_utils', fromlist=['extract_text_from_image']).extract_text_from_image(path),
        '.pptx': extract_text_from_pptx,
        '.docx': extract_text_from_docx,
        '.xlsx': extract_text_from_excel,
        '.xls': extract_text_from_excel,
        '.txt': extract_text_from_txt,
        '.md': extract_text_from_markdown,
        '.csv': extract_text_from_csv,
        '.json': extract_text_from_json,
        '.html': extract_text_from_html,
        '.htm': extract_text_from_html,
    }
    
    if file_ext in extractors:
        try:
            return extractors[file_ext](filepath)
        except Exception as e:
            return f"Error processing {file_ext} file: {str(e)}"
    else:
        return f"Unsupported file format: {file_ext}. Supported formats: PDF, Images (PNG, JPG, BMP, TIFF, GIF, WEBP), PPTX, DOCX, XLSX, XLS, TXT, MD, CSV, JSON, HTML"

def get_supported_formats() -> list:
    """Return list of supported file formats for chat"""
    return [
        'PDF (.pdf)',
        'PowerPoint (.pptx)',
        'Word Documents (.docx)',
        'Excel Spreadsheets (.xlsx, .xls)',
        'Images (.png, .jpg, .jpeg, .bmp, .gif, .tiff, .webp)',
        'Text Files (.txt)',
        'Markdown (.md)',
        'CSV (.csv)',
        'JSON (.json)',
        'HTML (.html, .htm)'
    ]

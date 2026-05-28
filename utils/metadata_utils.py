"""PDF metadata editing utilities"""
from pypdf import PdfReader, PdfWriter
from utils.logger import get_logger
_log = get_logger(__name__)

def edit_pdf_metadata(input_path, output_path, title=None, author=None, subject=None, keywords=None):
    """
    Edit PDF metadata
    
    Args:
        input_path: Path to input PDF
        output_path: Path to save modified PDF
        title: Document title
        author: Document author
        subject: Document subject
        keywords: Document keywords
    
    Returns:
        output_path if successful, None otherwise
    """
    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        
        # Copy all pages
        for page in reader.pages:
            writer.add_page(page)
        
        # Set metadata
        metadata = {}
        if title:
            metadata['/Title'] = title
        if author:
            metadata['/Author'] = author
        if subject:
            metadata['/Subject'] = subject
        if keywords:
            metadata['/Keywords'] = keywords
        
        writer.add_metadata(metadata)
        
        with open(output_path, 'wb') as output_file:
            writer.write(output_file)
        
        return output_path
    except Exception as e:
        _log.debug(f"Error editing metadata: {e}")
        return None

def get_pdf_metadata(input_path):
    """Get existing PDF metadata"""
    try:
        reader = PdfReader(input_path)
        metadata = reader.metadata
        
        return {
            'title': metadata.get('/Title', ''),
            'author': metadata.get('/Author', ''),
            'subject': metadata.get('/Subject', ''),
            'keywords': metadata.get('/Keywords', ''),
            'creator': metadata.get('/Creator', ''),
            'producer': metadata.get('/Producer', ''),
        }
    except Exception as e:
        _log.debug(f"Error reading metadata: {e}")
        return {}

import os
from utils.logger import get_logger
_log = get_logger(__name__)
import pandas as pd
import subprocess
try:
    import pdfkit
except ImportError:
    pdfkit = None

def get_edge_path():
    """Locate Microsoft Edge executable in standard Windows locations."""
    paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None

def url_to_pdf(url, output_path, page_size='A4', orientation='Portrait'):
    """
    Convert a URL to a PDF file using multiple fallback methods.
    Priority: 1) Microsoft Edge, 2) Playwright, 3) Selenium, 4) WeasyPrint, 5) Simple HTML
    """
    
    # Method 1: Try Microsoft Edge (best for Windows, no installation needed)
    try:
        edge_path = get_edge_path()
        if edge_path:
            _log.debug(f"[Method 1] Using Microsoft Edge to render: {url}")
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            abs_output_path = os.path.abspath(output_path)
            
            # Build Edge command
            cmd = [
                edge_path,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={abs_output_path}",
                url
            ]
            
            # Run Edge
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                _log.debug(f"✓ PDF created with Microsoft Edge: {output_path}")
                return output_path
        else:
            _log.debug("[Method 1] Microsoft Edge not found, trying next method...")
            
    except subprocess.TimeoutExpired:
        _log.debug("[Method 1] Edge timeout, trying next method...")
    except Exception as e:
        _log.debug(f"[Method 1] Edge failed: {e}")
    
    # Method 2: Try Playwright (best quality, renders JS)
    try:
        from playwright.sync_api import sync_playwright
        
        _log.debug(f"[Method 2] Using Playwright to render: {url}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            if page_size == 'A4':
                width, height = 794, 1123
            else:
                width, height = 816, 1056
            
            page.set_viewport_size({"width": width, "height": height})
            page.goto(url, wait_until='domcontentloaded', timeout=15000)
            page.wait_for_timeout(1000)
            
            pdf_options = {
                'path': output_path,
                'format': page_size,
                'print_background': True,
                'margin': {'top': '0.5in', 'right': '0.5in', 'bottom': '0.5in', 'left': '0.5in'}
            }
            
            if orientation == 'Landscape':
                pdf_options['landscape'] = True
            
            page.pdf(**pdf_options)
            browser.close()
            
            if os.path.exists(output_path):
                _log.debug(f"✓ PDF created with Playwright: {output_path}")
                return output_path
                
    except ImportError:
        _log.debug("[Method 2] Playwright not available, trying next method...")
    except Exception as e:
        _log.debug(f"[Method 2] Playwright failed: {e}")
    
    # Method 3: Try Selenium with Chrome (good quality, renders JS)
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        import base64
        
        _log.debug(f"[Method 3] Using Selenium to render: {url}")
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        
        # Wait for page to load
        import time
        time.sleep(2)
        
        # Use Chrome's print to PDF
        pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {
            "landscape": orientation == 'Landscape',
            "printBackground": True,
            "paperWidth": 8.27 if page_size == 'A4' else 8.5,
            "paperHeight": 11.69 if page_size == 'A4' else 11,
            "marginTop": 0.5,
            "marginBottom": 0.5,
            "marginLeft": 0.5,
            "marginRight": 0.5
        })
        
        driver.quit()
        
        # Save PDF
        with open(output_path, 'wb') as f:
            f.write(base64.b64decode(pdf_data['data']))
        
        if os.path.exists(output_path):
            _log.debug(f"✓ PDF created with Selenium: {output_path}")
            return output_path
            
    except ImportError:
        _log.debug("[Method 3] Selenium not available, trying next method...")
    except Exception as e:
        _log.debug(f"[Method 3] Selenium failed: {e}")
    
    # Method 4: Try requests + weasyprint (good for simple pages)
    try:
        import requests
        from weasyprint import HTML
        
        _log.debug(f"[Method 4] Using WeasyPrint to render: {url}")
        
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        
        HTML(string=response.text, base_url=url).write_pdf(output_path)
        
        if os.path.exists(output_path):
            _log.debug(f"✓ PDF created with WeasyPrint: {output_path}")
            return output_path
            
    except ImportError:
        _log.debug("[Method 4] WeasyPrint not available, trying next method...")
    except Exception as e:
        _log.debug(f"[Method 4] WeasyPrint failed: {e}")
    
    # Method 5: Try pdfkit (requires wkhtmltopdf)
    try:
        import pdfkit
        
        _log.debug(f"[Method 5] Using pdfkit to render: {url}")
        
        options = {
            'page-size': page_size,
            'orientation': orientation,
            'encoding': "UTF-8",
            'enable-local-file-access': None,
            'no-stop-slow-scripts': None,
            'javascript-delay': 1000
        }
        
        pdfkit.from_url(url, output_path, options=options)
        
        if os.path.exists(output_path):
            _log.debug(f"✓ PDF created with pdfkit: {output_path}")
            return output_path
            
    except ImportError:
        _log.debug("[Method 5] pdfkit not available")
    except Exception as e:
        _log.debug(f"[Method 5] pdfkit failed: {e}")
    
    # Method 6: Simple fallback - fetch HTML and convert
    try:
        import requests
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from html.parser import HTMLParser
        import urllib3
        
        # Disable SSL warnings for this method
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        _log.debug(f"[Method 6] Using simple HTML fetch + ReportLab: {url}")
        
        response = requests.get(
            url, 
            timeout=10, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            verify=False  # Disable SSL verification
        )
        response.raise_for_status()
        
        # Simple HTML to text extraction
        class HTMLToText(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.in_script = False
                self.in_style = False
                
            def handle_starttag(self, tag, attrs):
                if tag == 'script':
                    self.in_script = True
                elif tag == 'style':
                    self.in_style = True
                    
            def handle_endtag(self, tag):
                if tag == 'script':
                    self.in_script = False
                elif tag == 'style':
                    self.in_style = False
                
            def handle_data(self, data):
                if not self.in_script and not self.in_style:
                    text = data.strip()
                    if text and len(text) > 3:  # Skip very short strings
                        self.text.append(text)
        
        parser = HTMLToText()
        parser.feed(response.text)
        
        # Create PDF with ReportLab
        pagesize = A4 if page_size == 'A4' else letter
        doc = SimpleDocTemplate(output_path, pagesize=pagesize)
        styles = getSampleStyleSheet()
        elements = []
        
        # Add title
        elements.append(Paragraph(f"<b>Converted from URL</b>", styles['Heading1']))
        elements.append(Paragraph(f"<i>{url}</i>", styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))
        
        # Add content
        for text in parser.text[:200]:  # Limit to first 200 text blocks
            try:
                # Clean up text for PDF
                text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                if len(text) > 500:  # Split very long paragraphs
                    text = text[:500] + '...'
                elements.append(Paragraph(text, styles['Normal']))
                elements.append(Spacer(1, 0.05*inch))
            except Exception as e:
                _log.debug(f"Skipping problematic text: {e}")
                pass
        
        # Add footer
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph(f"<i>Generated by Document Utility Suite - URL to PDF</i>", styles['Normal']))
        
        doc.build(elements)
        
        if os.path.exists(output_path):
            _log.debug(f"✓ PDF created with simple method: {output_path}")
            return output_path
            
    except Exception as e:
        _log.debug(f"[Method 6] Simple method failed: {e}")
    
    # All methods failed
    _log.debug("✗ All conversion methods failed")
    return False

def markdown_to_pdf(content, output_path):
    """Convert Markdown text to a PDF file using reportlab."""
    try:
        import markdown
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Preformatted
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from html.parser import HTMLParser
        import re
        
        # Convert markdown to HTML
        html_content = markdown.markdown(
            content, 
            extensions=['extra', 'codehilite', 'tables', 'fenced_code', 'nl2br']
        )
        
        # Create PDF
        doc = SimpleDocTemplate(output_path, pagesize=letter,
                                rightMargin=72, leftMargin=72,
                                topMargin=72, bottomMargin=18)
        
        # Container for the 'Flowable' objects
        elements = []
        
        # Define styles
        styles = getSampleStyleSheet()
        
        # Add custom Code style if it doesn't exist
        if 'CustomCode' not in styles:
            styles.add(ParagraphStyle(name='CustomCode', 
                                      fontName='Courier',
                                      fontSize=9,
                                      leftIndent=20,
                                      rightIndent=20,
                                      spaceBefore=6,
                                      spaceAfter=6,
                                      backColor=colors.lightgrey))
        
        # Simple HTML parser to convert to reportlab elements
        class HTMLToReportlab(HTMLParser):
            def __init__(self):
                super().__init__()
                self.elements = []
                self.current_text = []
                self.in_code = False
                self.in_pre = False
                self.in_heading = None
                self.in_list = False
                self.list_items = []
                
            def handle_starttag(self, tag, attrs):
                if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    self.in_heading = tag
                elif tag == 'code':
                    self.in_code = True
                elif tag == 'pre':
                    self.in_pre = True
                elif tag in ['ul', 'ol']:
                    self.in_list = True
                elif tag == 'br':
                    self.current_text.append('<br/>')
                    
            def handle_endtag(self, tag):
                if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    text = ''.join(self.current_text).strip()
                    if text:
                        if tag == 'h1':
                            style = styles['Heading1']
                        elif tag == 'h2':
                            style = styles['Heading2']
                        else:
                            style = styles['Heading3']
                        self.elements.append(Paragraph(text, style))
                        self.elements.append(Spacer(1, 0.2*inch))
                    self.current_text = []
                    self.in_heading = None
                elif tag == 'p':
                    text = ''.join(self.current_text).strip()
                    if text:
                        self.elements.append(Paragraph(text, styles['BodyText']))
                        self.elements.append(Spacer(1, 0.1*inch))
                    self.current_text = []
                elif tag == 'code' and not self.in_pre:
                    self.in_code = False
                elif tag == 'pre':
                    text = ''.join(self.current_text).strip()
                    if text:
                        # Remove HTML tags from code
                        text = re.sub(r'<[^>]+>', '', text)
                        self.elements.append(Preformatted(text, styles['CustomCode']))
                        self.elements.append(Spacer(1, 0.1*inch))
                    self.current_text = []
                    self.in_pre = False
                elif tag in ['ul', 'ol']:
                    for item in self.list_items:
                        self.elements.append(Paragraph(f"• {item}", styles['BodyText']))
                    self.elements.append(Spacer(1, 0.1*inch))
                    self.list_items = []
                    self.in_list = False
                elif tag == 'li':
                    text = ''.join(self.current_text).strip()
                    if text:
                        self.list_items.append(text)
                    self.current_text = []
                    
            def handle_data(self, data):
                if data.strip():
                    if self.in_code and not self.in_pre:
                        self.current_text.append(f'<font name="Courier">{data}</font>')
                    else:
                        self.current_text.append(data)
        
        # Parse HTML and convert to reportlab elements
        parser = HTMLToReportlab()
        parser.feed(html_content)
        
        # Add parsed elements
        if parser.elements:
            elements.extend(parser.elements)
        else:
            # Fallback: just add the content as plain text
            for line in content.split('\n'):
                if line.strip():
                    elements.append(Paragraph(line, styles['BodyText']))
                    elements.append(Spacer(1, 0.1*inch))
        
        # Build PDF
        doc.build(elements)
        
        return output_path if os.path.exists(output_path) else False
    except Exception as e:
        _log.debug(f"Markdown to PDF Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def excel_to_pdf(input_path, output_path, orientation='landscape', style='grid'):
    """Convert Excel/CSV to a PDF file using reportlab (no wkhtmltopdf needed)."""
    try:
        from reportlab.lib.pagesizes import A4, landscape as rl_landscape
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet

        # Read the file
        if input_path.endswith('.csv'):
            df = pd.read_csv(input_path)
        else:
            df = pd.read_excel(input_path)

        # Fill NaN with empty string
        df = df.fillna('')

        # Page setup
        pagesize = rl_landscape(A4) if orientation == 'landscape' else A4
        doc = SimpleDocTemplate(output_path, pagesize=pagesize,
                                leftMargin=0.5*inch, rightMargin=0.5*inch,
                                topMargin=0.5*inch, bottomMargin=0.5*inch)

        styles = getSampleStyleSheet()
        elements = []
        elements.append(Paragraph(os.path.basename(input_path), styles['Heading2']))
        elements.append(Spacer(1, 0.2*inch))

        # Build table data: header + rows
        header = [str(c) for c in df.columns.tolist()]
        rows = [[str(v) for v in row] for row in df.values.tolist()]
        data = [header] + rows

        # Auto-size columns evenly
        page_w = pagesize[0] - inch  # subtract margins
        col_w = page_w / max(len(header), 1)
        col_widths = [col_w] * len(header)

        table = Table(data, colWidths=col_widths, repeatRows=1)

        # Style based on choice
        base_style = [
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f0f0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]
        if style == 'grid':
            base_style += [('GRID', (0, 0), (-1, -1), 0.5, colors.black)]
        elif style == 'striped':
            base_style += [
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
            ]
        else:  # minimal
            base_style += [('LINEBELOW', (0, 0), (-1, 0), 1, colors.black)]

        table.setStyle(TableStyle(base_style))
        elements.append(table)

        doc.build(elements)
        return output_path if os.path.exists(output_path) else False
    except Exception as e:
        _log.debug(f"Excel to PDF Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def ppt_to_pdf(input_path, output_path):
    """
    Convert a PowerPoint (.pptx or .ppt) file to PDF using aspose.slides.
    """
    try:
        import aspose.slides as slides
        
        # Load the presentation
        with slides.Presentation(input_path) as presentation:
            # Save as PDF
            presentation.save(output_path, slides.export.SaveFormat.PDF)
            
        return output_path if os.path.exists(output_path) else False
    except Exception as e:
        _log.debug(f"PPT to PDF Error: {e}")
        return False


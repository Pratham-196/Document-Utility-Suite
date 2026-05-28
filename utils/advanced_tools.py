import os
from PIL import Image, ImageDraw, ImageFont
import io
from utils.logger import get_logger

_log = get_logger(__name__)

def pdf_compare(input_path1, input_path2, output_path):
    try:
        import fitz

        doc1 = fitz.open(input_path1)
        doc2 = fitz.open(input_path2)

        report = []
        report.append(f"PDF Comparison Report\n")
        report.append(f"=" * 50 + "\n\n")
        report.append(f"File 1: {os.path.basename(input_path1)}\n")
        report.append(f"Pages: {len(doc1)}\n\n")
        report.append(f"File 2: {os.path.basename(input_path2)}\n")
        report.append(f"Pages: {len(doc2)}\n\n")

        if len(doc1) != len(doc2):
            report.append(f"Different page counts!\n\n")

        max_pages   = min(len(doc1), len(doc2))
        differences = 0

        for i in range(max_pages):
            text1 = doc1[i].get_text()
            text2 = doc2[i].get_text()
            if text1 != text2:
                differences += 1
                report.append(f"Page {i+1}: Content differs\n")

        report.append(f"\nTotal differences found: {differences}\n")

        doc1.close()
        doc2.close()

        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(report)

        return output_path
    except Exception as e:
        _log.warning(f"Error comparing PDFs: {e}")
        return None

def create_thumbnail(input_path, output_path, size=(200, 200)):
    try:
        if input_path.lower().endswith('.pdf'):
            import fitz
            doc  = fitz.open(input_path)
            page = doc.load_page(0)
            pix  = page.get_pixmap()
            img  = Image.open(io.BytesIO(pix.tobytes("png")))
            doc.close()
        else:
            img = Image.open(input_path)

        img.thumbnail(size, Image.Resampling.LANCZOS)
        img.save(output_path)
        return output_path
    except Exception as e:
        _log.warning(f"Error creating thumbnail: {e}")
        return None

def add_border_to_image(input_path, output_path, border_width=10, border_color='black'):
    try:
        img = Image.open(input_path)

        new_width  = img.width  + (border_width * 2)
        new_height = img.height + (border_width * 2)

        bordered = Image.new('RGB', (new_width, new_height), border_color)
        bordered.paste(img, (border_width, border_width))

        bordered.save(output_path)
        return output_path
    except Exception as e:
        _log.warning(f"Error adding border: {e}")
        return None

def image_to_ascii(input_path, output_path, width=100, max_dimension=800):
    # cap width/height so the browser doesn't freeze on huge outputs
    try:
        img = Image.open(input_path)

        width = min(width, 150)

        if img.width > max_dimension or img.height > max_dimension:
            if img.width > img.height:
                new_width  = max_dimension
                new_height = int(img.height * (max_dimension / img.width))
            else:
                new_height = max_dimension
                new_width  = int(img.width  * (max_dimension / img.height))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        img = img.convert('L')

        aspect_ratio = img.height / img.width
        height = min(int(width * aspect_ratio * 0.55), 200)

        img = img.resize((width, height), Image.Resampling.LANCZOS)

        chars = "@%#*+=-:. "
        pixels     = list(img.getdata())
        ascii_chars = [chars[int(pixel / 255 * (len(chars) - 1))] for pixel in pixels]

        ascii_art = []
        for i in range(0, len(ascii_chars), width):
            ascii_art.append(''.join(ascii_chars[i:i+width]))

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ascii_art))

        return output_path
    except Exception as e:
        _log.warning(f"Error converting to ASCII: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_collage(image_paths, output_path, cols=2):
    try:
        images = [Image.open(path) for path in image_paths]

        max_width  = max(img.width  for img in images)
        max_height = max(img.height for img in images)

        rows = (len(images) + cols - 1) // cols

        collage = Image.new('RGB', (max_width * cols, max_height * rows), 'white')

        for idx, img in enumerate(images):
            row = idx // cols
            col = idx % cols

            img_resized = img.copy()
            img_resized.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            collage.paste(img_resized, (col * max_width, row * max_height))

        collage.save(output_path)
        return output_path
    except Exception as e:
        _log.warning(f"Error creating collage: {e}")
        return None

def add_text_to_image(input_path, output_path, text, position='center', font_size=40, color='white'):
    try:
        img  = Image.open(input_path)
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

        bbox        = draw.textbbox((0, 0), text, font=font)
        text_width  = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (img.width - text_width) // 2

        if position == 'top':
            y = 50
        elif position == 'bottom':
            y = img.height - text_height - 50
        else:
            y = (img.height - text_height) // 2

        # shadow first, then the actual text on top
        draw.text((x+2, y+2), text, font=font, fill='black')
        draw.text((x,   y),   text, font=font, fill=color)

        img.save(output_path)
        return output_path
    except Exception as e:
        _log.warning(f"Error adding text: {e}")
        return None


def add_text_to_image_advanced(input_path, output_path, text, x, y, font_size=40,
                                font_family='Arial', font_weight='normal', color='#ffffff', shadow=True):
    try:
        img  = Image.open(input_path)
        draw = ImageDraw.Draw(img)

        if color.startswith('#'):
            color     = color.lstrip('#')
            rgb_color = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        else:
            rgb_color = (255, 255, 255)

        # map common font names to their Windows filenames
        font_map = {
            'Arial':         'arial.ttf',
            'Helvetica':     'arial.ttf',
            'Times New Roman': 'times.ttf',
            'Courier New':   'cour.ttf',
            'Georgia':       'georgia.ttf',
            'Verdana':       'verdana.ttf',
            'Impact':        'impact.ttf',
            'Comic Sans MS': 'comic.ttf'
        }

        font_file = font_map.get(font_family, 'arial.ttf')

        if font_weight == 'bold':
            bold_map = {
                'arial.ttf':   'arialbd.ttf',
                'times.ttf':   'timesbd.ttf',
                'cour.ttf':    'courbd.ttf',
                'georgia.ttf': 'georgiab.ttf',
                'verdana.ttf': 'verdanab.ttf'
            }
            font_file = bold_map.get(font_file, font_file)

        try:
            font = ImageFont.truetype(font_file, font_size)
        except:
            try:
                font = ImageFont.truetype(font_family, font_size)
            except:
                _log.warning(f"Could not load font {font_family}, using default")
                font = ImageFont.load_default()

        if shadow:
            shadow_offset = max(2, font_size // 20)
            draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=(0, 0, 0))

        draw.text((x, y), text, font=font, fill=rgb_color)

        img.save(output_path)
        return output_path

    except Exception as e:
        _log.warning(f"Error adding text to image: {e}")
        import traceback
        traceback.print_exc()
        return None

def pdf_page_count(input_path):
    try:
        from pypdf import PdfReader
        reader = PdfReader(input_path)
        return len(reader.pages)
    except Exception as e:
        _log.warning(f"Error counting pages: {e}")
        return 0

def reverse_pdf(input_path, output_path):
    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(input_path)
        writer = PdfWriter()

        for page in reversed(reader.pages):
            writer.add_page(page)

        with open(output_path, 'wb') as output_file:
            writer.write(output_file)

        return output_path
    except Exception as e:
        _log.warning(f"Error reversing PDF: {e}")
        return None

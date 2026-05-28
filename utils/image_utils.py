from PIL import Image
import os
from utils.logger import get_logger
_log = get_logger(__name__)

def compress_image(input_path, output_path, quality=60):
    try:
        img = Image.open(input_path)

        ext = os.path.splitext(output_path)[1].lower()

        # JPEG doesn't support transparency — flatten onto white background first
        if ext in ('.jpg', '.jpeg') and img.mode in ('RGBA', 'P', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert('RGB')

        quality = max(1, min(100, quality))

        if ext in ('.jpg', '.jpeg'):
            img.save(output_path, 'JPEG', quality=quality, optimize=True)
        elif ext == '.png':
            # PNG compression is 0-9, inverse of quality
            compress_level = int((100 - quality) / 11)
            img.save(output_path, 'PNG', optimize=True, compress_level=compress_level)
        elif ext == '.webp':
            img.save(output_path, 'WEBP', quality=quality, method=6)
        else:
            img.save(output_path, quality=quality, optimize=True)

        return output_path
    except Exception as e:
        _log.warning(f"Error compressing image: {e}")
        import traceback
        traceback.print_exc()
        return None

def resize_image(input_path, output_path, width=None, height=None, percentage=None):
    try:
        img = Image.open(input_path)
        w, h = img.size

        new_w, new_h = w, h

        if percentage:
            ratio = percentage / 100.0
            new_w = int(w * ratio)
            new_h = int(h * ratio)
        elif width and height:
            new_w = width
            new_h = height
        elif width:
            ratio = width / w
            new_w = width
            new_h = int(h * ratio)
        elif height:
            ratio = height / h
            new_h = height
            new_w = int(w * ratio)

        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        img.save(output_path)
        return output_path
    except Exception as e:
        _log.warning(f"Error resizing image: {e}")
        return None

def convert_image_format(input_path, output_path):
    # converts based on the output file extension
    try:
        img = Image.open(input_path)
        if output_path.lower().endswith(('.jpg', '.jpeg')) and img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.save(output_path)
        return output_path
    except Exception as e:
        _log.warning(f"Error converting image: {e}")
        return None

def extract_palette(input_path, num_colors=5):
    # shrink first so quantize runs fast, then pull hex codes from the palette
    try:
        img = Image.open(input_path)
        img = img.convert('RGB')
        img.thumbnail((200, 200))

        quantized = img.quantize(colors=num_colors)
        palette = quantized.getpalette()  # flat [r,g,b, r,g,b, ...]

        colors = []
        for i in range(num_colors):
            r = palette[i*3]
            g = palette[i*3+1]
            b = palette[i*3+2]
            colors.append(f"#{r:02x}{g:02x}{b:02x}")

        return colors
    except Exception as e:
        _log.warning(f"Error extracting palette: {e}")
        return []

def upscale_image(input_path, output_path, scale_factor=2):
    # cap output at 8000px on either side to avoid running out of memory
    try:
        img = Image.open(input_path)
        w, h = img.size

        scale_factor = max(1.1, min(scale_factor, 8))

        new_w = int(w * scale_factor)
        new_h = int(h * scale_factor)

        MAX_DIM = 8000
        if new_w > MAX_DIM or new_h > MAX_DIM:
            ratio = min(MAX_DIM / new_w, MAX_DIM / new_h)
            new_w = int(new_w * ratio)
            new_h = int(new_h * ratio)

        img_upscaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        ext = os.path.splitext(output_path)[1].lower()

        if ext in ('.jpg', '.jpeg'):
            if img_upscaled.mode in ('RGBA', 'P', 'LA'):
                background = Image.new('RGB', img_upscaled.size, (255, 255, 255))
                if img_upscaled.mode == 'P':
                    img_upscaled = img_upscaled.convert('RGBA')
                if img_upscaled.mode in ('RGBA', 'LA'):
                    background.paste(img_upscaled, mask=img_upscaled.split()[-1])
                    img_upscaled = background
                else:
                    img_upscaled = img_upscaled.convert('RGB')
            img_upscaled.save(output_path, 'JPEG', quality=95, optimize=True)
        elif ext == '.png':
            img_upscaled.save(output_path, 'PNG', optimize=True)
        elif ext == '.webp':
            img_upscaled.save(output_path, 'WEBP', quality=95, method=6)
        else:
            img_upscaled.save(output_path)

        return output_path
    except Exception as e:
        _log.warning(f"Error upscaling image: {e}")
        import traceback
        traceback.print_exc()
        return None

def remove_background_simple(input_path, output_path, tolerance=30):
    # samples the four corners to guess the background color, then makes matching pixels transparent
    try:
        import numpy as np

        img = Image.open(input_path).convert('RGBA')
        data = np.array(img, dtype=np.float32)

        corners = [
            data[0, 0, :3],
            data[0, -1, :3],
            data[-1, 0, :3],
            data[-1, -1, :3],
        ]
        bg_color = np.mean(corners, axis=0)

        diff = np.abs(data[:, :, :3] - bg_color)
        dist = np.max(diff, axis=2)

        mask = dist <= tolerance
        data[:, :, 3] = np.where(mask, 0, 255).astype(np.uint8)

        result = Image.fromarray(data.astype(np.uint8), 'RGBA')
        result.save(output_path, 'PNG', optimize=True)
        return output_path
    except Exception as e:
        _log.warning(f"Error in simple background removal: {e}")
        import traceback
        traceback.print_exc()
        return None

def remove_background(input_path, output_path):
    # uses rembg with u2net_human_seg; falls back to default u2net if that model fails
    # alpha_matting is off — it cuts off clothing/body edges at high thresholds
    try:
        try:
            from rembg import remove, new_session
        except ImportError as e:
            _log.debug(f"rembg import error: {e}")
            return None

        import io

        img = Image.open(input_path).convert('RGBA')
        original_size = img.size

        # resize down for speed, restore after
        max_dimension = 1500
        width, height = img.size
        if width > max_dimension or height > max_dimension:
            if width > height:
                new_width  = max_dimension
                new_height = int(height * (max_dimension / width))
            else:
                new_height = max_dimension
                new_width  = int(width * (max_dimension / height))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        try:
            session = new_session('u2net_human_seg')
            output_data = remove(
                img_bytes.read(),
                session=session,
                alpha_matting=False,
                post_process_mask=False
            )
        except Exception as model_err:
            _log.debug(f"u2net_human_seg failed ({model_err}), trying default model")
            img_bytes.seek(0)
            output_data = remove(
                img_bytes.read(),
                alpha_matting=False,
                post_process_mask=False
            )

        output_image = Image.open(io.BytesIO(output_data))

        if img.size != original_size:
            output_image = output_image.resize(original_size, Image.Resampling.LANCZOS)

        output_image.save(output_path, 'PNG', optimize=True)
        return output_path

    except Exception as e:
        _log.warning(f"Error removing background: {e}")
        import traceback
        traceback.print_exc()
        return None


def crop_image(input_path, output_path, left, top, right, bottom):
    try:
        img = Image.open(input_path)
        cropped = img.crop((left, top, right, bottom))
        cropped.save(output_path)
        return output_path
    except Exception as e:
        _log.warning(f"Error cropping image: {e}")
        return None

def apply_image_filter(input_path, output_path, filter_type='grayscale'):
    try:
        from PIL import ImageFilter, ImageEnhance

        img = Image.open(input_path)

        if filter_type == 'grayscale':
            img = img.convert('L')
        elif filter_type == 'sepia':
            import numpy as np
            img = img.convert('RGB')
            arr = np.array(img, dtype=np.float32)
            r = np.clip(arr[:,:,0]*0.393 + arr[:,:,1]*0.769 + arr[:,:,2]*0.189, 0, 255)
            g = np.clip(arr[:,:,0]*0.349 + arr[:,:,1]*0.686 + arr[:,:,2]*0.168, 0, 255)
            b = np.clip(arr[:,:,0]*0.272 + arr[:,:,1]*0.534 + arr[:,:,2]*0.131, 0, 255)
            sepia = np.stack([r, g, b], axis=2).astype(np.uint8)
            img = Image.fromarray(sepia)
        elif filter_type == 'blur':
            img = img.filter(ImageFilter.BLUR)
        elif filter_type == 'sharpen':
            img = img.filter(ImageFilter.SHARPEN)
        elif filter_type == 'edge_enhance':
            img = img.filter(ImageFilter.EDGE_ENHANCE)
        elif filter_type == 'contour':
            img = img.filter(ImageFilter.CONTOUR)
        elif filter_type == 'emboss':
            img = img.filter(ImageFilter.EMBOSS)
        elif filter_type == 'flip_h':
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        elif filter_type == 'flip_v':
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        elif filter_type == 'invert':
            from PIL import ImageChops
            img = img.convert('RGB')
            img = ImageChops.invert(img)

        img.save(output_path)
        return output_path
    except Exception as e:
        _log.warning(f"Error applying filter: {e}")
        return None

"""QR Code generation utilities"""
import qrcode
from PIL import Image

def generate_qr_code(data, output_path, size=300, border=2, fill_color="black", back_color="white"):
    """
    Generate a scannable QR code. No post-resize — qrcode generates at
    native pixel-perfect size using box_size to control output dimensions.
    """
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color=fill_color, back_color=back_color)
        img.save(output_path, format="PNG")
        return output_path
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return None

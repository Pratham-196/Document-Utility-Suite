import fitz
import os

def redact_pdf(input_path, output_path, text_to_redact, case_sensitive=False):
    """
    Redact specific text from a PDF file.
    Draws a black rectangle over occurrences of the text.
    """
    try:
        doc = fitz.open(input_path)
        redacted_count = 0

        for page in doc:
            if not case_sensitive:
                # Search multiple case variants and deduplicate by rect coordinates
                variants = {
                    text_to_redact,
                    text_to_redact.lower(),
                    text_to_redact.upper(),
                    text_to_redact.title(),
                }
                seen = set()
                matches = []
                for variant in variants:
                    for m in page.search_for(variant):
                        key = (round(m.x0), round(m.y0), round(m.x1), round(m.y1))
                        if key not in seen:
                            seen.add(key)
                            matches.append(m)
            else:
                matches = page.search_for(text_to_redact)

            if matches:
                for rect in matches:
                    annot = page.add_redact_annot(rect)
                    annot.set_colors(stroke=(0, 0, 0), fill=(0, 0, 0))
                    annot.update()
                    redacted_count += 1

                page.apply_redactions()

        doc.save(output_path)
        doc.close()
        return output_path, redacted_count
    except Exception as e:
        print(f"Error redacting PDF: {e}")
        return None, 0

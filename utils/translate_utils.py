from deep_translator import GoogleTranslator

def translate_text(text, target_lang='hi'):
    # Google Translate caps each request at 5000 chars, so split big text into chunks
    if not text:
        return ""

    try:
        translator = GoogleTranslator(source='auto', target=target_lang)

        max_chunk = 4500
        chunks = [text[i:i+max_chunk] for i in range(0, len(text), max_chunk)]

        translated_chunks = []
        for chunk in chunks:
            translated_chunks.append(translator.translate(chunk))

        return " ".join(translated_chunks)
    except Exception as e:
        print(f"Error in translation: {e}")
        return f"Translation error: {str(e)}"

def get_supported_languages():
    # Indian languages only
    indian_languages = {
        'hindi': 'hi',
        'bengali': 'bn',
        'telugu': 'te',
        'marathi': 'mr',
        'tamil': 'ta',
        'gujarati': 'gu',
        'kannada': 'kn',
        'malayalam': 'ml',
        'punjabi': 'pa',
        'odia': 'or',
        'urdu': 'ur',
        'assamese': 'as',
        'sanskrit': 'sa',
        'konkani': 'gom',
        'sindhi': 'sd',
        'nepali': 'ne'
    }
    return indian_languages

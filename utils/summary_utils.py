import nltk
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
import os

# Ensure nltk data is present
def ensure_nltk_data():
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')
    try:
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        nltk.download('punkt_tab')

ensure_nltk_data()

def summarize_text(text, sentences_count=5, language="english"):
    """
    Summarize text using LSA (Latent Semantic Analysis) extractive summarization.
    """
    if not text or len(text.strip()) < 100:
        return "Text is too short to summarize effectively."

    parser = PlaintextParser.from_string(text, Tokenizer(language))
    stemmer = Stemmer(language)
    summarizer = LsaSummarizer(stemmer)
    summarizer.stop_words = get_stop_words(language)

    summary = summarizer(parser.document, sentences_count)
    
    return " ".join([str(sentence) for sentence in summary])

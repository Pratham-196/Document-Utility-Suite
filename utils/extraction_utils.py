import re
# Temporarily disable spacy due to Python 3.14 compatibility issues
# try:
#     import spacy
#     try:
#         nlp = spacy.load("en_core_web_sm")
#     except:
#         nlp = None
# except ImportError:
#     nlp = None
nlp = None

try:
    import phonenumbers
    HAS_PHONENUMBERS = True
except ImportError:
    HAS_PHONENUMBERS = False


def extract_resume_data(text):
    """
    Extracts structured data from a resume text.
    """
    data = {
        "name": "Not found",
        "email": "Not found",
        "phone": "Not found",
        "skills": [],
        "education": [],
        "experience": []
    }
    
    if not text:
        return data

    # 1. Extract Email
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    if emails:
        data["email"] = emails[0]

    # 2. Extract Phone
    if HAS_PHONENUMBERS:
        try:
            for match in phonenumbers.PhoneNumberMatcher(text, "IN"):
                data["phone"] = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                break
        except:
            pass
    if data["phone"] == "Not found":
        # Fallback to simple regex
        phone_pattern = r'(\d{3}[-\.\s]??\d{3}[-\.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-\.\s]??\d{4}|\d{10})'
        phones = re.findall(phone_pattern, text)
        if phones:
            data["phone"] = phones[0]

    # 3. Extract Name
    if nlp:
        doc = nlp(text[:1000]) # Name is usually at the top
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                data["name"] = ent.text
                break
    
    # Fallback name extraction if spacy failed or didn't find anything
    if data["name"] == "Not found":
        # Look for the first line with roughly 2-3 capitalized words
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for line in lines[:5]:
            if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}$', line):
                data["name"] = line
                break
    
    # 4. Extract Skills (Keyword matching)
    skills_list = [
        'Python', 'Java', 'Javascript', 'React', 'Angular', 'Node.js', 'SQL', 'NoSQL',
        'Machine Learning', 'AI', 'NLP', 'Data Science', 'C++', 'AWS', 'Azure', 'Docker',
        'Kubernetes', 'Project Management', 'Agile', 'HTML', 'CSS', 'UI/UX', 'Figma'
    ]
    found_skills = []
    for skill in skills_list:
        if re.search(r'\b' + re.escape(skill) + r'\b', text, re.I):
            found_skills.append(skill)
    data["skills"] = list(set(found_skills))

    return data

def extract_invoice_data(text):
    """
    Extracts structured data from an invoice text.
    """
    data = {
        "invoice_no": "Not found",
        "date": "Not found",
        "total_amount": "Not found",
        "vendor": "Not found"
    }

    if not text:
        return data

    # 1. Invoice Number
    inv_patterns = [
        r'Invoice\s*(?:Number|No\.?|#)?\s*:?\s*([A-Z0-9-]+)',
        r'Inv\s*(?:No\.?|#)?\s*:?\s*([A-Z0-9-]+)'
    ]
    for pattern in inv_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            data["invoice_no"] = match.group(1)
            break

    # 2. Date
    date_pattern = r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})'
    dates = re.findall(date_pattern, text)
    if dates:
        data["date"] = dates[0]

    # 3. Total Amount
    amount_patterns = [
        r'(?:Total|Amount|Balance|Due)\s*(?:Due|Total|Amount)?\s*:?\s*(?:\$|Rs\.?|INR)?\s*([\d,]+\.?\d*)',
        r'(?:\$|Rs\.?|INR)\s*([\d,]+\.?\d*)'
    ]
    amounts = []
    for pattern in amount_patterns:
        found = re.findall(pattern, text, re.I)
        amounts.extend([float(a.replace(',', '')) for a in found if a.replace(',', '').replace('.', '').isdigit()])
    
    if amounts:
        # Usually the largest number is the total
        data["total_amount"] = max(amounts)

    # 4. Vendor (Naive approach - first line often contains vendor)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if lines:
        data["vendor"] = lines[0]

    return data

# -*- coding: utf-8 -*-
import re
import html

def _clean_html_to_text(html_string: str) -> str:
    """
    Ek simple HTML remover jo HTML ko plain text mein convert karta hai.
    """
    if not html_string:
        return ""
        
    # HTML tags ko remove karein
    text = re.sub(r'<[^>]+>', ' ', html_string)
    
    # HTML entities (jaise &nbsp; &amp;) ko decode karein
    text = html.unescape(text)
    
    # Extra whitespace ko clean karein
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def _get_localized_text(content_object, lang='en'):
    """
    HTML content ko safely extract aur clean karta hai.
    """
    if not content_object or not isinstance(content_object, dict):
        return "N/A"
        
    # Pehle 'en' try karein, fir 'hi', fir 'hn', fir koi bhi pehli available language
    lang_priority = [lang, 'en', 'hi', 'hn']
    
    html_content = None
    
    for l in lang_priority:
        if l in content_object:
            html_content = content_object[l]
            break
            
    if not html_content and content_object:
        # Agar priority languages nahi mili, toh pehli available lein
        first_lang_key = next(iter(content_object))
        html_content = content_object[first_lang_key]

    # Agar content ek dict hai (options ki tarah)
    if isinstance(html_content, dict) and 'value' in html_content:
        html_content = html_content.get('value', '')

    return _clean_html_to_text(html_content)

def generate_txt(quiz_data: dict, details: dict) -> str:
    """
    JSON data aur test details se ek complete TXT string generate karta hai.
    """
    if not quiz_data or 'questions' not in quiz_data:
        return "Error: Invalid Quiz Data."

    output_lines = []
    
    # --- Header ---
    output_lines.append(f"Test Series: {details.get('Test Series', 'N/A')}")
    output_lines.append(f"Section: {details.get('Section', 'N/A')}")
    output_lines.append(f"Subsection: {details.get('Subsection', 'N/A')}")
    output_lines.append(f"Test Name: {details.get('Test Name', 'N/A')}")
    output_lines.append("-" * 30)
    output_lines.append(f"Questions: {details.get('Questions', 'N/A')} | Duration: {details.get('Duration', 'N/A')} | Total Marks: {details.get('Total Marks', 'N/A')}")
    output_lines.append(f"Marking: [Correct: {details.get('Correct', 'N/A')}] [Incorrect: {details.get('Incorrect', 'N/A')}]")
    output_lines.append("=" * 30 + "\n")
    
    # --- Questions Loop ---
    for i, q in enumerate(quiz_data.get('questions', [])):
        
        # Question
        q_text = _get_localized_text(q.get('content', {}))
        output_lines.append(f"Q.{i + 1}: {q_text}")
        
        # Options
        options = q.get('options', {})
        options_list = []
        
        # Options ko 'en' (ya default) key se extract karein
        if 'en' in options:
            options_list = options['en']
        elif options:
            first_lang_key = next(iter(options))
            options_list = options[first_lang_key]
            
        correct_option_text = "N/A"
        
        if not isinstance(options_list, list):
            output_lines.append("  (Error: Options format not recognized)")
            continue

        for j, opt in enumerate(options_list):
            opt_text = _clean_html_to_text(opt.get('text', ''))
            option_char = chr(ord('a') + j) # (a), (b), (c)...
            output_lines.append(f"  ({option_char}) {opt_text}")
            
            if opt.get('is_correct', False):
                correct_option_text = opt_text

        # Solution
        solution_text = _get_localized_text(q.get('solution', {}))
        
        output_lines.append(f"\n  Answer: {correct_option_text}")
        output_lines.append(f"  Solution: {solution_text}")
        output_lines.append("\n" + "-" * 30 + "\n")

    return "\n".join(output_lines)

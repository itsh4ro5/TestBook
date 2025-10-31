# -*- coding: utf-8 -*-
import re
import html

def _clean_math_tex(math_string: str) -> str:
    """
    Simple conversion of math-tex to plain text.
    (LaTeX-like math ko saaf karne ke liye helper function)
    """
    if not math_string:
        return ""
    
    # \ (aur \) ko remove karein
    text = math_string.replace(r'\(', ' ').replace(r'\)', ' ')
    
    # \frac{A}{B} ko (A / B) se replace karein
    text = re.sub(r'\\frac{({[^}]+}|[^}]+)}{({[^}]+}|[^}]+)}', r'(\1 / \2)', text)
    
    # Subscripts jaise {C_u} ko Cu banayein
    text = re.sub(r'{([^_}]+)_([^_}]+)}', r'\1\2', text)
    
    # Bachi hui curly braces {} ko hata dein
    text = text.replace('{', '').replace('}', '')
    
    # Common LaTeX commands ko replace karein
    text = text.replace(r'\;', ' ').replace(r'\times', 'x').replace(r'\div', '/')
    text = text.replace(r'\Rightarrow', '=>').replace(r'\rightarrow', '->')
    text = text.replace(r'\leq', '<=').replace(r'\geq', '>=')
    text = text.replace(r'\approx', '~=')
    
    # Common symbols
    text = text.replace(r'\Delta', 'Delta').replace(r'\delta', 'delta')
    text = text.replace(r'\gamma', 'gamma').replace(r'\alpha', 'alpha')
    text = text.replace(r'\beta', 'beta').replace(r'\lambda', 'lambda')
    text = text.replace(r'\mu', 'mu').replace(r'\pi', 'pi')
    
    # Bachi hui backslashes \ ko hata dein
    text = text.replace('\\', '')
    
    return text.strip()

def _clean_html_to_text(html_string: str) -> str:
    """
    Ek simple HTML remover jo HTML ko plain text mein convert karta hai.
    (MODIFIED: Sabhi tags aur &nbsp; ko explicitly handle karne ke liye)
    """
    if not html_string:
        return ""
    
    # 1. (NAYA ORDER) HTML entities (jaise &lt;, &gt;, &amp;, &nbsp;) ko decode karein
    # Isse "&lt;p&gt;" asli "<p>" ban jayega
    text = html.unescape(html_string)

    # 2. Math-tex spans ko pehle process karein
    def math_replacer(match):
        # Span ke andar ka content nikalein
        inner_html = match.group(1)
        # Andar ke HTML ko clean karein (agar koi tag ho - ab zaroori nahi)
        inner_text = re.sub(r'<[^>]+>', '', inner_html)
        # Math string ko process karein
        return " " + _clean_math_tex(inner_text) + " "

    text = re.sub(r'<span class="math-tex">(.*?)</span>', math_replacer, text, flags=re.DOTALL)

    # 3. sub/sup tags ko handle karein (bina space add kiye)
    text = re.sub(r'</?sub>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?sup>', '', text, flags=re.IGNORECASE)
    
    # 4. Baaki bache hue SABHI HTML tags ko remove karein (space ke saath)
    # Yeh <p>, </p>, <span style="">, </span>, <p style=""> etc. sab ko handle karega
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 5. &nbsp; (jo ab \xa0 ban gaya hai) ko explicitly space se replace karein
    text = text.replace('\xa0', ' ')
    
    # 6. Extra whitespace ko clean karein
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
    (MODIFIED: Solution part ko hata diya gaya hai)
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

        # Answer (Correct Option Text)
        output_lines.append(f"\n  Answer: {correct_option_text}")
        
        # --- REMOVED ---
        # Solution line has been removed as requested by user.
        # --- END REMOVED ---
        
        output_lines.append("\n" + "-" * 30 + "\n")

    return "\n".join(output_lines)


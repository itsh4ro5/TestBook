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
    (MODIFIED: Superscripts aur special symbols (like &sum;) ko handle karne ke liye)
    """
    if not html_string:
        return ""
    
    # 1. HTML entities ko decode karein (double-decoding ke liye do baar)
    # Yeh '&amp;sum;' ko '&sum;' aur fir '∑' bana dega.
    text = html.unescape(html_string)
    text = html.unescape(text) 

    # 2. (NAYA) Common superscript/subscript tags ko unke Unicode char se replace karein
    #    Yeh '</span><sup>2</sup>' ko '²' mein badalne mein madat karega
    
    # Pehle </span> ko hatayein jo seedha <sup> se pehle aata hai
    # Taki "km</span><sup>2</sup>" -> "km<sup>2</sup>" ban jaaye
    text = re.sub(r'</span>(<sup>.*?</sup>)', r'\1', text, flags=re.IGNORECASE)
    
    # Ab common superscripts ko replace karein
    text = re.sub(r'<sup>2</sup>', '²', text, flags=re.IGNORECASE)
    text = re.sub(r'<sup>3</sup>', '³', text, flags=re.IGNORECASE)
    text = re.sub(r'<sup>\+</sup>', '⁺', text, flags=re.IGNORECASE) # Escape '+'
    text = re.sub(r'<sup>-</sup>', '⁻', text, flags=re.IGNORECASE)
    
    # Common subscripts
    text = re.sub(r'<sub>2</sub>', '₂', text, flags=re.IGNORECASE)
    text = re.sub(r'<sub>3</sub>', '₃', text, flags=re.IGNORECASE)
    
    # 3. Math-tex spans ko pehle process karein
    def math_replacer(match):
        # Span ke andar ka content nikalein
        inner_html = match.group(1)
        # Andar ke HTML ko clean karein (agar koi tag ho - ab zaroori nahi)
        inner_text = re.sub(r'<[^>]+>', '', inner_html)
        # Math string ko process karein
        return " " + _clean_math_tex(inner_text) + " "

    text = re.sub(r'<span class="math-tex">(.*?)</span>', math_replacer, text, flags=re.DOTALL)

    # 4. Baaki bache hue SABHI HTML tags ko remove karein (space ke saath)
    #    (Isme bache hue <sub>, <sup>, <p>, <span> etc. sab aa jayenge)
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 5. &nbsp; ke dono forms (decoded aur literal) ko handle karein
    # Yeh <p>, </p>, <span style="">, </span>, <p style=""> etc. sab ko handle karega
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 5. (MODIFIED) &nbsp; ke dono forms (decoded aur literal) ko handle karein
    # \xa0 (decoded non-breaking space)
    text = text.replace('\xa0', ' ')
    # '&nbsp;' (literal string agar double-encoded tha)
    text = text.replace('&nbsp;', ' ')
    
    # 6. Extra whitespace ko clean karein
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def _get_specific_text(content_object, lang_code):
    """
    HTML content ko safely extract aur clean karta hai, specific language ke liye.
    Returns None agar language nahi milti.
    (MODIFIED: 'hi' aur 'hn' ko handle karne ke liye)
    """
    if not content_object or not isinstance(content_object, dict):
        return None
        
    html_content = None
    
    # Hindi ke liye 'hi' aur 'hn' dono check karein
    if lang_code == 'hi':
        if 'hi' in content_object:
            html_content = content_object['hi']
        elif 'hn' in content_object:
            html_content = content_object['hn']
    elif lang_code in content_object:
        html_content = content_object[lang_code]

    if not html_content:
        return None

    # Agar content ek dict hai (options ki tarah)
    if isinstance(html_content, dict) and 'value' in html_content:
        html_content = html_content.get('value', '')
    elif isinstance(html_content, dict) and 'text' in html_content: # Options ke text ke liye
         html_content = html_content.get('text', '')

    cleaned_text = _clean_html_to_text(html_content)
    # Return None if cleaned text is empty, taki comparison mein aasani ho
    return cleaned_text if cleaned_text else None


def generate_txt(quiz_data: dict, details: dict) -> str:
    """
    JSON data aur test details se ek complete TXT string generate karta hai.
    (MODIFIED: Solution part ko hata diya gaya hai aur English/Hindi dono add kiye gaye hain)
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
        
        # --- Question (English and Hindi) ---
        q_text_en = _get_specific_text(q.get('content', {}), 'en') or ""
        q_text_hi = _get_specific_text(q.get('content', {}), 'hi') or ""
        
        output_lines.append(f"Q.{i + 1}: {q_text_en}")
        # Hindi tabhi add karein jab woh non-empty ho aur English se alag ho
        if q_text_hi and q_text_hi != q_text_en:
            output_lines.append(f"    {q_text_hi}")
        
        # --- Options (English and Hindi) ---
        options_data = q.get('options', {})
        options_list_en = options_data.get('en', [])
        # Hindi ke liye 'hi' ya 'hn' (fallback)
        options_list_hi = options_data.get('hi', options_data.get('hn', [])) 
            
        correct_option_text_en = "N/A"
        correct_option_text_hi = "N/A"
        
        if not isinstance(options_list_en, list):
            output_lines.append("  (Error: English options format not recognized)")
            continue

        for j, opt_en in enumerate(options_list_en):
            opt_text_en = _clean_html_to_text(opt_en.get('text', ''))
            opt_text_hi = ""

            # Corresponding Hindi option find karein
            if isinstance(options_list_hi, list) and j < len(options_list_hi):
                opt_hi = options_list_hi[j]
                if opt_hi:
                    opt_text_hi = _clean_html_to_text(opt_hi.get('text', ''))

            option_char = chr(ord('a') + j) # (a), (b), (c)...
            
            final_opt_text = opt_text_en
            # Hindi tabhi add karein jab woh non-empty ho aur English se alag ho
            if opt_text_hi and opt_text_hi != opt_text_en:
                final_opt_text += f" / {opt_text_hi}"
                
            output_lines.append(f"  ({option_char}) {final_opt_text}")
            
            if opt_en.get('is_correct', False):
                correct_option_text_en = opt_text_en
                # Hindi text tabhi store karein jab woh valid ho aur English se alag ho
                correct_option_text_hi = opt_text_hi if (opt_text_hi and opt_text_hi != opt_text_en) else ""

        # --- Answer (English and Hindi) ---
        final_correct_text = correct_option_text_en
        if correct_option_text_hi:
            final_correct_text += f" / {correct_option_text_hi}"
            
        output_lines.append(f"\n  Answer: {final_correct_text}")
        
        # --- REMOVED ---
        # Solution line has been removed as requested by user.
        # --- END REMOVED ---
        
        output_lines.append("\n" + "-" * 30 + "\n")

    return "\n".join(output_lines)


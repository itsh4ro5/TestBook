# -*- coding: utf-8 -*-
import io
import httpx
import time
import json
import base64
# html_generator import ki ab yahaan zaroorat nahi hai
# from config import TESTBOOK_AUTH_TOKEN (Ab config.py se nahi, bot.py se token milega)

class TestbookExtractor:
    """
    Testbook Extractor, synchronous (non-async) version.
    Token ab constructor ke through pass kiya jayega.
    """
    
    def __init__(self, token: str):
        self.base_url_new = "https://api-new.testbook.com"
        self.base_url_old = "https://api.testbook.com"
        
        # Token ko constructor se set karein
        self.token = token
        if not self.token:
            print("WARNING: TestbookExtractor ko bina token ke initialize kiya gaya hai!")
            raise ValueError("Auth Token zaroori hai.")
            
        self.posMarks = 'N/A'
        self.negMarks = 'N/A'
        self.last_details = {} # HTML generation ke liye details store karein
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Platform': 'web',
            'X-Tb-Client': 'web,1.2',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Authorization': f"Bearer {self.token}" # Header mein token set karein
        }

    def _make_request(self, url: str, params: dict = None, method: str = 'GET', payload: dict = None, timeout: int = 60):
        """Synchronous request method"""
        try:
            # Har request ke liye headers copy karein (kyonki self.token static hai)
            request_headers = self.headers.copy()
            
            # Auth code ko params mein bhi daalna zaroori hai (Testbook API ke liye)
            if params is None: params = {}
            if 'auth_code' not in params:
                params['auth_code'] = self.token
            if 'language' not in params:
                params['language'] = 'English'
                
            with httpx.Client() as client:
                if method.upper() == 'POST':
                    response = client.post(url, params=params, headers=request_headers, json=payload, timeout=timeout)
                else:
                    response = client.get(url, params=params, headers=request_headers, timeout=timeout)
                
                response.raise_for_status()
                return True, response.json()
        except Exception as e:
            error_message = f"Request Error: {str(e)}"
            if 'response' in locals() and hasattr(response, 'status_code'):
                error_message = f"Client Error: {response.status_code} - {response.text}"
            return False, error_message

    def search(self, query: str) -> list | None:
        search_url = f"{self.base_url_new}/api/v1/search/individual"
        params = {'term': query, 'searchObj': 'testSeries', 'limit': 30}
        success, data = self._make_request(search_url, params=params)
        if success and data.get("success"):
            return data.get("data", {}).get("results", {}).get("testSeries")
        return None

    def get_series_details(self, series_slug: str) -> dict | None:
        details_url = f"{self.base_url_old}/api/v1/test-series/slug"
        params = {'url': series_slug}
        success, data = self._make_request(details_url, params=params)
        if success and data.get("success"):
            return data.get("data", {}).get("details")
        return None

    def get_tests_in_subsection(self, series_id: str, section_id: str, subsection_id: str) -> list | None:
        url = f"{self.base_url_old}/api/v2/test-series/{series_id}/tests/details"
        params = {'sectionId': section_id, 'subSectionId': subsection_id, 'limit': 500, 'testType': 'all'}
        success, data = self._make_request(url, params=params)
        if success and data.get("success"):
            return data.get("data", {}).get("tests")
        return None
    
    def _parse_multi_language_data(self, base_data: dict, answers_data: dict) -> dict | None:
        """
        Yeh function waise hi hai, isme async kuch nahi tha.
        """
        q_data = base_data.get('data')
        ans_map = answers_data.get('data', {})
        if not q_data or not ans_map:
            print("Parsing Error: Missing data from one of the endpoints.")
            return None

        result = {'title': q_data.get('title', 'Unknown Test'), 'questions': [], 'available_languages': []}
        lang_set = set()
        
        try:
            first_q_id = list(ans_map.keys())[0]
            self.posMarks = ans_map[first_q_id].get('posMarks', 'N/A')
            self.negMarks = ans_map[first_q_id].get('negMarks', 'N/A')
        except Exception:
            self.posMarks = 'N/A' # Fallback
            self.negMarks = 'N/A' # Fallback

        for section in q_data.get('sections', []):
            for q in section.get('questions', []):
                q_id = q.get('_id')
                if not q_id: continue

                answer_info = ans_map.get(q_id)
                if not answer_info: continue

                new_question_obj = {'id': q_id, 'content': {}, 'options': {}, 'solution': {}}

                for lang_code, lang_content in q.items():
                    if isinstance(lang_content, dict) and 'value' in lang_content and 'options' in lang_content:
                        lang_set.add(lang_code)
                        new_question_obj['content'][lang_code] = lang_content.get('value', '')
                        
                        processed_options = []
                        for opt in lang_content.get('options', []):
                            processed_options.append({
                                'text': opt.get('value', ''),
                                'is_correct': False
                            })
                        new_question_obj['options'][lang_code] = processed_options

                solution_obj = answer_info.get('sol', {})
                for lang_code, sol_content in solution_obj.items():
                     if isinstance(sol_content, dict) and 'value' in sol_content:
                        lang_set.add(lang_code)
                        new_question_obj['solution'][lang_code] = sol_content.get('value', '')

                try:
                    correct_option_index = int(answer_info.get('correctOption')) - 1
                except (ValueError, TypeError):
                    correct_option_index = -1
                
                if correct_option_index != -1:
                    for lang_code, options_list in new_question_obj['options'].items():
                        if 0 <= correct_option_index < len(options_list):
                            options_list[correct_option_index]['is_correct'] = True

                if new_question_obj['content']:
                    result['questions'].append(new_question_obj)

        result['available_languages'] = sorted(list(lang_set))
        return result

    def _perform_instant_submit(self, test_id: str) -> (bool, str):
        """
        Synchronous instant submit.
        """
        try:
            success_init, init_data = self._make_request(
                f"{self.base_url_new}/api/v2/tests/{test_id}/instructions"
            )
            if not success_init:
                return False, f"Failed to start test (instructions): {init_data}"
            
            attempt_no = init_data.get("data", {}).get("attemptNo", 1)
            
            url = f"{self.base_url_new}/api/v2/tests/{test_id}"
            params = {"attemptNo": attempt_no}
            submit_success, submit_data = self._make_request(
                url, params=params, method='POST', payload={"task": "submit"}
            )
            
            if not submit_success:
                 return False, f"Failed to submit test: {submit_data}"

            print(f"Test {test_id} submitted, waiting 5s for processing...")
            time.sleep(5) 
            return True, "Submit successful"
        except Exception as e:
            return False, f"Exception during submit: {str(e)}"

    def extract_questions(self, test_id: str) -> dict:
        """
        Synchronous extract method.
        """
        self.posMarks, self.negMarks = 'N/A', 'N/A'
        
        success_q, base_data = self._make_request(f"{self.base_url_new}/api/v2/tests/{test_id}")
        
        if not success_q or not base_data.get("success"):
            return {'error': f'Failed to fetch test data: {base_data}'}

        params_a = {'attemptNo': 1}
        success_a, answers_data = self._make_request(f"{self.base_url_new}/api/v2/tests/{test_id}/answers", params=params_a)
        
        if not success_a or not answers_data.get("success"):
            if "not completed" in str(answers_data).lower():
                print(f"Test {test_id} not attempted. Performing instant submit...")
                
                submit_success, submit_message = self._perform_instant_submit(test_id)
                
                if not submit_success:
                    return {'error': f"Failed to instant submit: {submit_message}"}
                
                print(f"Test {test_id} submitted. Fetching answers again...")
                
                success_a, answers_data = self._make_request(f"{self.base_url_new}/api/v2/tests/{test_id}/answers", params=params_a)
                
                if not success_a or not answers_data.get("success"):
                    return {'error': f'Failed to fetch answers even after submit: {answers_data}'}
            
            else:
                return {'error': f'Failed to fetch test answers/solutions: {answers_data}'}
        
        final_data = self._parse_multi_language_data(base_data, answers_data)
        
        if not final_data or not final_data.get('questions'):
            return {'error': 'Could not parse or merge test data.'}
            
        return final_data

    def _get_caption_details(self, test_summary: dict, series_details: dict, selected_section: dict, subsection_context: dict) -> dict:
        """Helper function jo caption ke liye details nikalta hai."""
        
        # Details ko 'last_details' mein save karein taaki html_generator use kar sake
        self.last_details = {
            "Test Series": series_details.get('name', 'N/A'),
            "Section": selected_section.get('name', 'N/A'),
            "Subsection": subsection_context.get('name', 'N/A'),
            "Test Name": test_summary.get('title', 'N/A'),
            "Questions": test_summary.get('questionCount', '?'),
            "Duration": f"{test_summary.get('duration', 'N/A')} min",
            "Total Marks": str(test_summary.get('totalMark', 'N/A')),
            "Correct": f"+{self.posMarks}", 
            "Incorrect": f"{self.negMarks}"
        }
        return self.last_details

    def get_caption(self, test_summary: dict, series_details: dict, selected_section: dict, subsection_context: dict, extractor_name: str = None) -> str:
        """
        Test file ke liye ek formatted, cool caption generate karta hai.
        """
        # Pehle details fetch/calculate karein
        details = self._get_caption_details(
            test_summary=test_summary,
            series_details=series_details,
            selected_section=selected_section,
            subsection_context=subsection_context
        )

        # Ab caption banayein
        caption = (
            f"✨ **{details.get('Test Name')}** ✨\n\n"
            f"📚 **Test Series:** {details.get('Test Series')}\n"
            f"🗂️ **Section:** {details.get('Section')}\n"
            f"📂 **Subsection:** {details.get('Subsection')}\n\n"
            f"⏱️ **Duration:** {details.get('Duration')}\n"
            f"❓ **Questions:** {details.get('Questions')}\n"
            f"🎯 **Total Marks:** {details.get('Total Marks')}\n"
            f"✅ **Correct:** {details.get('Correct')}\n"
            f"❌ **Incorrect:** {details.get('Incorrect')}\n"
        )
        
        if extractor_name:
            caption += f"\n---\n*Extracted By: {extractor_name}*"

        return caption



"""
LLM Solver using Google Gemini API
Generates Python code to solve data science quiz questions
"""

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import logging
from typing import Dict, Any
import re
from config import settings

logger = logging.getLogger(__name__)

class LLMSolver:
    """Uses LLM to generate code for solving quiz questions"""
    
    def __init__(self):
        self.model_name = settings.GEMINI_MODEL
        logger.info(f"[LLM] Initialized with model: {self.model_name}")
        
        # Configure the model with system instructions
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self._get_system_prompt()
        )
        
        # Configure safety settings to prevent blocking code generation
        # (Sometimes code is flagged as unsafe, so we lower the threshold)
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
    
    async def generate_solution(self, question_data: Dict[str, str], previous_error: str = None, failed_code: str = None,previous_output: str = None) -> str:
        logger.info("[LLM] Generating solution code")
        logger.info(f"[LLM] Question length: {len(question_data.get('question_text', ''))} chars")

        prompt = self._build_prompt(question_data, previous_error, failed_code, previous_output)

        try:
            logger.info(f"[LLM] Calling Gemini API with model: {self.model_name}")
            
            # Gemini async generation
            response = await self.model.generate_content_async(
                prompt,
                safety_settings=self.safety_settings,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1, # Keep it deterministic for code
                    candidate_count=1
                )
            )

            generated_code = response.text
            logger.info(f"[LLM] Received response - {len(generated_code)} characters")
            
            cleaned_code = self._clean_code(generated_code)
            return cleaned_code

        except Exception as e:
            logger.error(f"[LLM ERROR] Failed to generate solution: {str(e)}", exc_info=True)
            return None
    
    def _get_system_prompt(self) -> str:
        return f"""You are an expert data scientist and Python programmer. Your task is to solve data science quiz questions by generating executable Python code.
*** CRITICAL DATA INSTRUCTION ***
The variable `QUIZ_URL` is usually an HTML PAGE containing the question, NOT the data file itself.
DO NOT pass `QUIZ_URL` directly to pandas (e.g. `pd.read_csv(QUIZ_URL)`).
Instead, you must:
1. Fetch `QUIZ_URL` using requests.
2. Inspect the content. If it looks like HTML, use BeautifulSoup to find the link to the actual dataset (CSV, JSON, ZIP, TXT).
3. Handle relative URLs (use `urllib.parse.urljoin`).
4. Download the actual data file URL found in step 2.

*** THE ENVIRONMENT ***
- You CANNOT see the data files or web pages directly.
- You CANNOT interactively debug. You have one shot (and potentially one retry).
- You DO NOT know the exact data schema (column names, HTML IDs, JSON keys) beforehand, even if the question implies them.

*** THE "EYES-OPEN" PROTOCOL (MANDATORY) ***
To solve tasks blindly, you must write code that "sees" for you. 
For EVERY external resource (URL, File, API response) you interact with, you MUST:

1. **INSPECT BEFORE ACTION**:
   - Immediately after loading ANY data, print its metadata to `stdout`.
   - If it's a tabular structure: Print columns and first few rows.
   - If it's a dictionary/JSON: Print the top-level keys.
   - If it's raw text/HTML: Print a snippet (first 500 chars).
   - If it's binary/image: Print the shape, size, or metadata.
   - The data may or may not have headers, correct formats, or expected structures.
2. **ROBUST SCRAPING (CRITICAL)**:
   - **Dynamic Content:** If the initial HTML contains `<script>` tags or is mostly empty, you MUST use `selenium` or `playwright`.
   - **Do NOT Wait for Tags:** When using a browser, NEVER wait for specific tags like `<code>` or `id="secret"`. They might not exist.
   - **Text-First Search:** Once loaded, extract `body_text = driver.find_element(By.TAG_NAME, "body").text`.
   - **Regex Extraction:** Use Regex on `body_text` to find answers
   - Prefer using 'playwright.sync_api' over 'selenium' as it is more stable in this environment.
3. **DEFENSIVE EXTRACTION**:
   - Never use hardcoded lookups (e.g., `df['Value']` or `soup.find(id='code')`) without first verifying they exist.
   - Use "search" logic instead of "index" logic (e.g., search for columns containing "date" rather than assuming "Date").
   - If a lookup fails, your code should catch the error and print **what was actually there** (e.g., "Expected column 'Value', but found: ['val', 'id']").

3. **VERIFY INTERMEDIATES**:
   - Print the result of significant intermediate steps. (e.g., "Filtered dataframe size: 0 rows" warning).

IMPORTANT: Your code must handle EVERYTHING end-to-end including:
1. Extracting/downloading any required data
2. Processing and analyzing the data
3. Computing the answer
4. Submitting the answer to the specified endpoint 
PLEASE ENSURE THAT YOUR CODE DOES NOT CRASH MY SANDBOXED ENVIRONMENT, ENSURE PROPER, GRACEFUL ERROR HANDLING.

*** SUBMISSION PROTOCOL (CRITICAL) ***
1. **THE ENDPOINT**: The HTTP POST request must ALMOST ALWAYS go to:
   `https://tds-llm-analysis.s-anand.net/submit`
2. **THE PAYLOAD URL**: If the question says "use url = X", it means set the JSON key `"url": "X"`. 
   - DO NOT change the HTTP POST target unless the question explicitly says "POST to X".
   - If you get a 405 Method Not Allowed, you are posting to the wrong URL.
3. 2. **THE PAYLOAD SCHEMA**: You MUST use these EXACT keys. Do not invent new keys.
   {{
       "email": 24f1001827@ds.study.iitm.ac.in,    # Key must be "email", NOT "student_email"
       "secret": Ghose,  # Key must be "secret", NOT "student_secret"
       "url": <The URL requested by the question>,
       "answer": <Your computed answer>
   }}
Key requirements:
- Generate ONLY executable Python code, no explanations or markdown.
- The code will be executed with these credentials available as variables:
  * STUDENT_EMAIL = "{settings.STUDENT_EMAIL}"
  * STUDENT_SECRET = "{settings.STUDENT_SECRET}"
  * QUIZ_URL = (the current quiz URL)
- Imports available in environment: requests, BeautifulSoup, selenium,playwright, pandas (pd), numpy (np), json, csv, base64, re, PyPDF2, pdfplumber, matplotlib, seaborn, sklearn, scipy.
- Import any other standard libraries you need within the code itself.

Your code MUST:
1. Read the question carefully.
2. Extract the submission URL.
3. Download/scrape data.
4. Perform the analysis.
5. ALWAYS POST the answer to the submission endpoint. If you cannot get the answer, POST a reasonable guess.
6. Print the response status.
7. Handle errors gracefully.
8. Print a suitable statement in case of some error in code.
9. Don't use __main__ block; just provide the code logic.

*** MANDATORY OUTPUT FORMAT ***
Your code must end by printing the submission result EXACTLY like this:

print(f"REQUEST_STATUS: {{response.status_code}}")
print(f"SERVER_RESPONSE: {{response.text}}")

DO NOT print labels like "Response Body:" or "Status:".
ONLY use "REQUEST_STATUS:" and "SERVER_RESPONSE:".
"""
    

    def _build_prompt(self, question_data: Dict[str, str], previous_error: str = None, failed_code: str = None, previous_output: str = None) -> str:
        question_text = question_data.get('question_text', '')
        quiz_url = question_data.get('url', '')

        prompt = f"""Solve this data science quiz question and submit the answer:

QUESTION TEXT:
{question_text}

CURRENT QUIZ URL: {quiz_url}

CREDENTIALS (available as variables in your code):
- STUDENT_EMAIL = "{settings.STUDENT_EMAIL}"
- STUDENT_SECRET = "{settings.STUDENT_SECRET}"
- QUIZ_URL = "{quiz_url}"
"""

        if previous_error:
            prompt += f"""
PREVIOUS ATTEMPT FAILED:
{previous_error}

PREVIOUS CODE:
{failed_code}
OUTPUT FROM PREVIOUS ATTEMPT:
{previous_output}
Please analyze the error and generate corrected code that fixes the issue.
"""

        prompt += """
INSTRUCTIONS:
Generate ONLY executable Python code (no markdown code blocks, no text explanations).
"""
        return prompt
    
    def _clean_code(self, code: str) -> str:
        # Standardize Markdown removal
        code = re.sub(r'^```python\s*\n', '', code, flags=re.MULTILINE)
        code = re.sub(r'^```\s*\n', '', code, flags=re.MULTILINE)
        code = re.sub(r'\n```\s*$', '', code)
        code = code.strip()
        return code
    
    async def analyze_error_and_retry(self, question_data: Dict[str, str], code: str, error: str) -> str:
        logger.info("[LLM] Analyzing error and generating fix")
        
        retry_prompt = f"""The following code failed with an error:

CODE:
{code}

ERROR:
{error}

ORIGINAL QUESTION:
{question_data.get('question_text', '')}

Please analyze the error and generate corrected Python code. Generate ONLY the fixed code.
"""

        try:
            response = await self.model.generate_content_async(
                retry_prompt,
                safety_settings=self.safety_settings
            )

            fixed_code = response.text
            cleaned_code = self._clean_code(fixed_code)

            logger.info(f"[LLM] Generated fixed code")
            return cleaned_code

        except Exception as e:
            logger.error(f"[LLM ERROR] Failed to generate fix: {str(e)}")

            raise


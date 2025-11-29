"""
Safe execution environment for LLM-generated code
Runs code in a sandboxed environment with access to data science libraries
Now handles answer submission within the code itself
"""

import logging
from typing import Any, Dict
import sys
from io import StringIO
import traceback
import re
import ast
# Pre-import commonly used libraries for the execution environment
import requests
import pandas as pd
import numpy as np
import json
import csv
import base64
from bs4 import BeautifulSoup
import io

from config import settings

# For file processing
try:
    import PyPDF2
    import pdfplumber
    import openpyxl
    from docx import Document
    from pptx import Presentation
except ImportError as e:
    logging.warning(f"Optional import failed: {e}")

# Image processing & Computer Vision
try:
    from PIL import Image
    import PIL
    import cv2
except ImportError as e:
    logging.warning(f"Image processing import failed: {e}")

# For visualization
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import seaborn as sns
    import plotly
    import plotly.graph_objects as go
except ImportError as e:
    logging.warning(f"Visualization library import failed: {e}")

# For ML/analysis
try:
    from scipy import stats
    from sklearn import *
except ImportError as e:
    logging.warning(f"ML library import failed: {e}")

# For geospatial (if needed)
try:
    import geopandas as gpd
except ImportError as e:
    logging.warning(f"Geospatial library import failed: {e}")

# For network analysis (if needed)
try:
    import networkx as nx
except ImportError as e:
    logging.warning(f"Network analysis library import failed: {e}")

# Web scraping with JS support
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options as ChromeOptions
except ImportError as e:
    logging.warning(f"Selenium import failed: {e}")

# Web scraping with Playwright
try:
    from playwright.sync_api import sync_playwright
except ImportError as e:
    logging.warning(f"Playwright import failed: {e}")

logger = logging.getLogger(__name__)

class CodeExecutor:
    """Safely executes LLM-generated Python code"""
    
    def __init__(self):
        self.execution_globals = self._setup_execution_environment()
    
    def _setup_execution_environment(self) -> Dict:
        """
        Setup the global namespace for code execution
        Pre-populate with common libraries
        """
        logger.info("[EXECUTOR] Setting up execution environment")
        
        env = {
            # Built-in functions
            '__builtins__': __builtins__,
            'print': print,
            'len': len,
            'range': range,
            'str': str,
            'int': int,
            'float': float,
            'list': list,
            'dict': dict,
            'set': set,
            'tuple': tuple,
            'bool': bool,
            
            # Common libraries
            'requests': requests,
            'pd': pd,
            'pandas': pd,
            'np': np,
            'numpy': np,
            'json': json,
            'csv': csv,
            'base64': base64,
            're': re,
            'BeautifulSoup': BeautifulSoup,
            'io': io,
        }
        
        # Add optional libraries if available
        try:
            env['PyPDF2'] = PyPDF2
            env['pdfplumber'] = pdfplumber
            env['openpyxl'] = openpyxl
            env['Document'] = Document  # python-docx
            env['Presentation'] = Presentation  # python-pptx
        except:
            pass
        
        # Image processing & Computer Vision
        try:
            env['Image'] = Image
            env['PIL'] = PIL
            env['cv2'] = cv2
        except:
            pass

        try:
            env['plt'] = plt
            env['matplotlib'] = matplotlib
            env['sns'] = sns
            env['seaborn'] = sns
            env['plotly'] = plotly
            env['go'] = go
        except:
            pass
        
        try:
            env['stats'] = stats
            env['scipy'] = stats
        except:
            pass

        
        # Web scraping with JS (Selenium)
        try:
            env['webdriver'] = webdriver
            env['By'] = By
            env['WebDriverWait'] = WebDriverWait
            env['EC'] = EC
            env['ChromeOptions'] = ChromeOptions
        except:
            pass
        
        # Playwright support
        try:
            env['sync_playwright'] = sync_playwright
        except:
            pass
        logger.info(f"[EXECUTOR] Environment setup complete with {len(env)} items")
        return env
    
    async def execute_code(self, code: str, quiz_url: str) -> Dict[str, Any]:
        """
        Execute the generated code and extract results
        Code now handles submission internally
        
        Returns:
            Dict with 'success', 'output', 'error', 'submission_result'
        """
        logger.info("[EXECUTOR] Starting code execution")
        logger.info(f"[EXECUTOR] Code to execute:\n{code}")
        
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        result = {
            'success': False,
            'output': None,
            'error': None,
            'submission_result': None
        }
        
        try:
            # Create a fresh copy of globals for this execution
            execution_env = self.execution_globals.copy()
            
            # Inject credentials and quiz URL into environment
            execution_env['STUDENT_EMAIL'] = settings.STUDENT_EMAIL
            execution_env['STUDENT_SECRET'] = settings.STUDENT_SECRET
            execution_env['QUIZ_URL'] = quiz_url
            
            logger.info(f"[EXECUTOR] Injected credentials: {settings.STUDENT_EMAIL}, {settings.STUDENT_SECRET}")
            logger.info(f"[EXECUTOR] Injected QUIZ_URL: {quiz_url}")
            
            # Execute the code
            logger.info("[EXECUTOR] Executing code...")
            exec(code, execution_env)
            
            result['success'] = True
            logger.info(f"[EXECUTOR] ✓ Execution completed!")
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            result['error'] = error_msg
            result['traceback'] = traceback.format_exc()
            logger.error(f"[EXECUTOR] ✗ Execution failed: {error_msg}")
            logger.error(f"[EXECUTOR] Traceback:\n{result['traceback']}")
            
        finally:
            # Restore stdout and capture output
            sys.stdout = old_stdout
            result['output'] = captured_output.getvalue()
            
            if result['output']:
                logger.info(f"[EXECUTOR] Captured output:\n{result['output']}")
                result['submission_result'] = self._parse_submission_result(result['output'])
            else:
                logger.warning("[EXECUTOR] Code produced NO output")
                result['submission_result'] = {} # Return empty dict instead of None
        
        return result
    
    def _parse_submission_result(self, output: str) -> Dict[str, Any]:
        """
        Parse the submission result from code output.
        
        Capabilities:
        1. Flexible Headers: Handles 'Status:', 'Status Code:', 'REQUEST_STATUS:', 'Response:', 'Response Body:', 'SERVER_RESPONSE:'
        2. Flexible Formats: Parses both JSON (double quotes, lowercase true) and Python Dicts (single quotes, capitalized True)
        3. Fallback Recovery: Scans for JSON-like blobs if headers are missing
        """
        logger.info("[EXECUTOR] Parsing submission result from output")
        
        submission = {
            'correct': None,
            'next_url': None,
            'reason': None,
            'status_code': None
        }
        
        try:
            # ---------------------------------------------------------
            # 1. Parse STATUS CODE
            # ---------------------------------------------------------
            # Regex Explanation:
            # (?:Status|STATUS|REQUEST_STATUS) -> Match any of these variations
            # (?:\s+Code)?                     -> Optionally match " Code" (e.g. "Status Code")
            # :\s*(\d+)                        -> Match colon and capture digits
            status_match = re.search(r'(?:Status|STATUS|REQUEST_STATUS)(?:\s+Code)?:\s*(\d+)', output, re.IGNORECASE)
            
            if status_match:
                submission['status_code'] = int(status_match.group(1))
                logger.info(f"[EXECUTOR] Found status code: {submission['status_code']}")
            
            # ---------------------------------------------------------
            # 2. Parse RESPONSE BODY
            # ---------------------------------------------------------
            # Regex Explanation:
            # (?:Response|RESPONSE|SERVER_RESPONSE) -> Match variations
            # (?:\s+Body)?                          -> Optionally match " Body" (Fixes your specific error)
            # :\s*(\{.*?\})                         -> Match colon and capture the curly brace content (Non-greedy)
            # re.DOTALL                             -> Allows .* to match newlines (for pretty-printed JSON)
            response_match = re.search(r'(?:Response|RESPONSE|SERVER_RESPONSE)(?:\s+Body)?:\s*(\{.*?\})', output, re.DOTALL | re.IGNORECASE)
            
            if response_match:
                dict_str = response_match.group(1)
                response_data = None
                
                # Priority 1: JSON Parsing (Strict)
                try:
                    response_data = json.loads(dict_str)
                    logger.info("[EXECUTOR] Parsed response using json.loads")
                except json.JSONDecodeError:
                    # Priority 2: Python Literal Evaluation (Handles 'single quotes' and True/False/None)
                    try:
                        response_data = ast.literal_eval(dict_str)
                        logger.info("[EXECUTOR] Parsed response using ast.literal_eval (Python Dict)")
                    except Exception:
                        logger.warning("[EXECUTOR] Could not parse response string as Dict or JSON")

                if response_data:
                    submission['correct'] = response_data.get('correct')
                    # Handle both 'url' (from API) and 'next_url' (internal consistency)
                    submission['next_url'] = response_data.get('url') or response_data.get('next_url')
                    submission['reason'] = response_data.get('reason')
                    
                    logger.info(f"[EXECUTOR] Parsed result: correct={submission['correct']}, next={submission['next_url']}")

            # ---------------------------------------------------------
            # 3. Fallback Mechanism (Scavenger Hunt)
            # ---------------------------------------------------------
            # If main parsing failed, look for ANY object containing "correct" key
            if submission['correct'] is None:
                # Regex finds {... "correct" ...} or {... 'correct' ...}
                fallback_matches = re.findall(r'\{[^{}]*[\"\']correct[\"\'][^{}]*\}', output)
                
                if fallback_matches:
                    for match in fallback_matches:
                        try:
                            # Try JSON first
                            data = json.loads(match)
                        except:
                            try:
                                # Try Python Dict second
                                data = ast.literal_eval(match)
                            except:
                                continue # Skip if unparseable
                        
                        # If we successfully parsed data, extract fields
                        submission['correct'] = data.get('correct')
                        submission['next_url'] = data.get('url') or data.get('next_url')
                        submission['reason'] = data.get('reason')
                        logger.info("[EXECUTOR] Recovered data via fallback regex")
                        break
        
        except Exception as e:
            logger.error(f"[EXECUTOR] Error parsing submission result: {str(e)}")
        
        return submission
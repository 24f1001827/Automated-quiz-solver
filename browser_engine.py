"""
Playwright browser engine for rendering JavaScript-based quiz pages
Handles page navigation, JS execution, and content extraction
"""

from playwright.async_api import async_playwright, Browser, Page
import logging
import base64
from typing import Optional, Dict
from config import settings

logger = logging.getLogger(__name__)

class BrowserEngine:
    """Manages Playwright browser for quiz page rendering"""
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
        
    async def start(self):
        """Initialize browser"""
        logger.info("[BROWSER] Initializing Playwright browser")
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=settings.BROWSER_HEADLESS
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            logger.info("[BROWSER] Browser initialized successfully")
        except Exception as e:
            logger.error(f"[BROWSER ERROR] Failed to initialize: {str(e)}")
            raise
    
    async def close(self):
        """Close browser and cleanup"""
        logger.info("[BROWSER] Closing browser")
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("[BROWSER] Browser closed successfully")
        except Exception as e:
            logger.error(f"[BROWSER ERROR] Error during cleanup: {str(e)}")
    
    async def visit_quiz_page(self, url: str) -> Dict[str, str]:
        """
        Visit quiz URL and extract the question
        Returns dict with 'question_text' and 'raw_html'
        """
        logger.info(f"[BROWSER] Navigating to: {url}")
        
        try:
            page = await self.context.new_page()
            
            # Navigate to URL
            logger.info(f"[BROWSER] Loading page...")
            response = await page.goto(url, wait_until='networkidle', timeout=settings.BROWSER_TIMEOUT)
            logger.info(f"[BROWSER] Page loaded - Status: {response.status}")
            
            # Wait for JavaScript to execute
            await page.wait_for_timeout(2000)  # Give JS time to render
            
            # Get page content
            html_content = await page.content()
            logger.info(f"[BROWSER] HTML content length: {len(html_content)} characters")
            
            # Try to extract text content from common elements
            question_text = await self._extract_question_text(page)
            
            # Log the extracted question
            logger.info(f"[BROWSER] Extracted question (first 500 chars):\n{question_text[:500]}")
            
            await page.close()
            
            return {
                'question_text': question_text,
                'raw_html': html_content,
                'url': url
            }
            
        except Exception as e:
            logger.error(f"[BROWSER ERROR] Failed to visit page: {str(e)}", exc_info=True)
            raise
    
    async def _extract_question_text(self, page: Page) -> str:
        """
        Extract readable question text from page
        Tries multiple strategies to get the content
        """
        try:
            # Strategy 1: Get all visible text
            body_text = await page.evaluate("""
                () => {
                    return document.body.innerText || document.body.textContent;
                }
            """)
            
            if body_text and len(body_text.strip()) > 0:
                logger.info("[BROWSER] Successfully extracted text using innerText")
                return body_text.strip()
            
            # Strategy 2: Look for specific result divs
            result_div = await page.query_selector("#result")
            if result_div:
                result_text = await result_div.inner_text()
                if result_text:
                    logger.info("[BROWSER] Successfully extracted text from #result div")
                    return result_text.strip()
            
            # Strategy 3: Get all text nodes
            all_text = await page.evaluate("""
                () => {
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    let text = '';
                    let node;
                    while (node = walker.nextNode()) {
                        text += node.textContent + '\\n';
                    }
                    return text;
                }
            """)
            
            if all_text:
                logger.info("[BROWSER] Successfully extracted text using TreeWalker")
                return all_text.strip()
            
            logger.warning("[BROWSER] Could not extract meaningful text, returning empty string")
            return ""
            
        except Exception as e:
            logger.error(f"[BROWSER ERROR] Error extracting text: {str(e)}")
            return ""
    
    async def download_file(self, url: str, output_path: str = None) -> bytes:
        """
        Download a file from URL
        Returns file content as bytes
        """
        logger.info(f"[BROWSER] Downloading file from: {url}")
        
        try:
            page = await self.context.new_page()
            
            # Navigate and download
            response = await page.goto(url)
            content = await response.body()
            
            logger.info(f"[BROWSER] Downloaded {len(content)} bytes")
            
            if output_path:
                with open(output_path, 'wb') as f:
                    f.write(content)
                logger.info(f"[BROWSER] Saved to: {output_path}")
            
            await page.close()
            return content
            
        except Exception as e:
            logger.error(f"[BROWSER ERROR] Failed to download file: {str(e)}")
            raise
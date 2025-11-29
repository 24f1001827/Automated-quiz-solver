"""
Quiz Handler - Orchestrates the entire quiz solving process
Manages the flow from receiving quiz URL to submitting answers
Includes smart time management and URL preservation
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
import asyncio
import requests
from browser_engine import BrowserEngine
from llm_solver import LLMSolver
from code_executor import CodeExecutor
from config import settings

logger = logging.getLogger(__name__)

class QuizHandler:
    """Orchestrates the quiz solving workflow"""
    
    def __init__(self, email: str, secret: str):
        self.email = email
        self.secret = secret
        self.llm_solver = LLMSolver()
        self.code_executor = CodeExecutor()
        
        logger.info(f"[HANDLER] Initialized for {email}")
    
    async def solve_quiz_sequence(self, initial_url: str, sequence_start_time: datetime):
        """
        Solve a sequence of quizzes following the chain of URLs
        """
        logger.info("\n" + "=" * 80)
        logger.info("[HANDLER] Starting quiz sequence")
        logger.info(f"[HANDLER] Initial URL: {initial_url}")
        logger.info(f"[HANDLER] Global Start time: {sequence_start_time}")
        logger.info(f"[HANDLER] Per-Question Timeout: {settings.QUIZ_TIMEOUT_SECONDS}s")
        logger.info("=" * 80 + "\n")
        
        current_url = initial_url
        quiz_number = 1
        stats = {
            'total': 0, 'correct': 0, 'incorrect': 0, 'skipped': 0, 'errors': 0
        }
        
        while current_url:
            # --- FIX STARTS HERE ---
            # Reset the timer for THIS specific question
            question_start_time = datetime.now()
            
            # Check time remaining (Relative to THIS question)
            elapsed = (datetime.now() - question_start_time).total_seconds()
            remaining = settings.QUIZ_TIMEOUT_SECONDS - elapsed
            
            logger.info(f"\n{'='*80}")
            logger.info(f"[HANDLER] QUIZ #{quiz_number}")
            logger.info(f"[HANDLER] URL: {current_url}")
            # Log both question time and total sequence time
            total_elapsed = (datetime.now() - sequence_start_time).total_seconds()
            logger.info(f"[HANDLER] Question Time: {elapsed:.1f}s / {remaining:.1f}s remaining")
            logger.info(f"[HANDLER] Total Sequence Time: {total_elapsed:.1f}s")
            logger.info(f"{'='*80}\n")
            
            # Solve this quiz (Pass question_start_time, NOT sequence_start_time)
            result = await self.solve_single_quiz(current_url, remaining, question_start_time)
            # --- FIX ENDS HERE ---
            
            stats['total'] += 1
            
            if result['status'] == 'correct':
                stats['correct'] += 1
            elif result['status'] == 'incorrect':
                stats['incorrect'] += 1
            elif result['status'] == 'error':
                stats['errors'] += 1
            elif result['status'] == 'skipped':
                stats['skipped'] += 1
            
            # Get next URL
            next_url = result.get('next_url')
            
            if next_url:
                current_url = next_url
                quiz_number += 1
                logger.info(f"[HANDLER] ➡️  Moving to next quiz: {current_url}")
            else:
                logger.info("[HANDLER] 🎉 No next URL - Quiz sequence completed!")
                break
        
        # Final statistics
        final_elapsed = (datetime.now() - sequence_start_time).total_seconds()
        logger.info("\n" + "=" * 80)
        logger.info("[HANDLER] QUIZ SEQUENCE ENDED")
        logger.info("=" * 80)
        logger.info(f"Total quizzes attempted: {stats['total']}")
        logger.info(f"  ✓ Correct: {stats['correct']}")
        logger.info(f"  ✗ Incorrect: {stats['incorrect']}")
        logger.info(f"  ⊘ Skipped: {stats['skipped']}")
        logger.info(f"  ⚠ Errors: {stats['errors']}")
        logger.info(f"Total Sequence Time: {final_elapsed:.1f}s")
        logger.info("=" * 80 + "\n")

    # ... The rest of the class methods (submit_fallback, solve_single_quiz, retries) ...
    # ... stay exactly the same, because they simply use the start_time passed to them ...
    
    async def submit_fallback(self, quiz_url: str):
        fallback_payload = {
            "email": settings.STUDENT_EMAIL,
            "secret": settings.STUDENT_SECRET,
            "url": quiz_url,
            "answer": "FAILED"   
        }

        try:
            logger.warning("[HANDLER] Sending FALLBACK submission (LLM/Execution failed)")
            response = requests.post(quiz_url, json=fallback_payload)
            logger.warning(f"[HANDLER] Fallback STATUS: {response.status_code}")
            logger.warning(f"[HANDLER] Fallback RESPONSE: {response.text}")
            return response
        except Exception as e:
            logger.error(f"[HANDLER] Fallback submission FAILED: {e}")
            return None

    async def solve_single_quiz(self, quiz_url: str, time_remaining: float, start_time: datetime) -> Dict:
        """Solve a single quiz question with smart retry logic"""
        logger.info(f"[HANDLER] Solving quiz: {quiz_url}")
        
        try:
            # Step 1: Visit the quiz page with browser
            logger.info("[HANDLER] Step 1: Visiting quiz page...")
            async with BrowserEngine() as browser:
                question_data = await browser.visit_quiz_page(quiz_url)
            
            logger.info("[HANDLER] ✓ Question extracted")
            
            # Step 2: Generate and execute solution code with LLM
            logger.info("[HANDLER] Step 2: Generating solution...")
            solution_code = await self.llm_solver.generate_solution(question_data)
            
            if solution_code is None:
                logger.error("[HANDLER] ✗ LLM failed to generate code")
                
                # Check if we have time to retry
                elapsed = (datetime.now() - start_time).total_seconds()
                remaining = settings.QUIZ_TIMEOUT_SECONDS - elapsed
                
                if remaining > settings.SKIP_THRESHOLD_SECONDS * 2:  
                    logger.info("[HANDLER] Attempting to fix and retry...")
                    solution_code = await self.llm_solver.generate_solution(question_data)
                    if solution_code is None:
                        logger.error("[HANDLER] ✗ Retry also failed to generate code")
                        return {'status': 'error', 'next_url': None}
                else:
                    logger.warning("[HANDLER] Not enough time for retry")
                    logger.info("[HANDLER] Submitting fallback answer...")
                    fallback_resp = await self.submit_fallback(quiz_url)
                    try:
                        data = fallback_resp.json()
                        next_url = data.get("url", None)
                        return {"next_url": next_url, "status": "incorrect"}
                    except:
                        return {'status': 'error', 'next_url': None}
            logger.info("[HANDLER] ✓ Solution generated")
            
            # Step 3: Execute the code (includes submission)
            logger.info("[HANDLER] Step 3: Executing solution...")
            execution_result = await self.code_executor.execute_code(solution_code, quiz_url)
            
            if not execution_result['success']:
                logger.error(f"[HANDLER] ✗ Execution failed: {execution_result['error']}")
                
                elapsed = (datetime.now() - start_time).total_seconds()
                remaining = settings.QUIZ_TIMEOUT_SECONDS - elapsed
                
                if remaining > settings.SKIP_THRESHOLD_SECONDS * 2:
                    logger.info("[HANDLER] Attempting to fix and retry...")
                    return await self.retry_with_fix(
                        question_data, 
                        quiz_url, 
                        solution_code, 
                        execution_result['error'],
                        start_time
                    )
                else:
                    logger.warning("[HANDLER] Not enough time for retry")
                    logger.info("[HANDLER] Submitting fallback answer...")
                    fallback_resp = await self.submit_fallback(quiz_url)
                    try:
                        data = fallback_resp.json()
                        next_url = data.get("url", None)
                        return {"next_url": next_url, "status": "incorrect"}
                    except:
                        return {'status': 'error', 'next_url': None} 
            
            logger.info("[HANDLER] ✓ Code executed successfully")
            
            # Step 4: Parse submission result from output
            submission_result = execution_result.get('submission_result')
            previous_output = execution_result.get('output', '')
            
            if not submission_result:
                fallback_resp = await self.submit_fallback(quiz_url)
                try:
                    data = fallback_resp.json()
                    next_url = data.get("url", None)
                    return {"next_url": next_url, "status": "incorrect"}
                except:
                    return {'status': 'error', 'next_url': None}

            if submission_result.get('correct'):
                logger.info("[HANDLER] ✓✓✓ ANSWER WAS CORRECT! ✓✓✓")
                return {
                    'status': 'correct',
                    'next_url': submission_result.get('next_url')
                }
            
            elif submission_result.get('correct') is False:
                logger.warning("[HANDLER] ✗✗✗ ANSWER WAS INCORRECT ✗✗✗")
                reason = submission_result.get('reason', 'No reason provided')
                logger.info(f"[HANDLER] Reason: {reason}")
                
                elapsed = (datetime.now() - start_time).total_seconds()
                remaining = settings.QUIZ_TIMEOUT_SECONDS - elapsed
                next_url = submission_result.get('next_url')
                
                if remaining > settings.SKIP_THRESHOLD_SECONDS * 2:
                    logger.info("[HANDLER] Enough time remaining - will retry")
                    retry_result = await self.retry_with_feedback(
                        question_data,
                        quiz_url,
                        reason,
                        solution_code,
                        previous_output,
                        start_time
                    )
                    if not retry_result.get('next_url') and next_url:
                        retry_result['next_url'] = next_url
                    return retry_result
                
                elif next_url:
                    logger.warning(f"[HANDLER] ⚠️  Only {remaining:.1f}s remaining - SKIPPING to next URL")
                    return {
                        'status': 'skipped',
                        'next_url': next_url
                    }
                else:
                    logger.warning("[HANDLER] No time to retry and no next URL")
                    return {
                        'status': 'incorrect',
                        'next_url': None
                    }
            else:
                logger.warning("[HANDLER] ⚠️  Could not determine submission result")
                return {'status': 'error', 'next_url': None}
        
        except Exception as e:
            logger.error(f"[HANDLER] Unexpected error: {str(e)}", exc_info=True)
            return {'status': 'error', 'next_url': None}

    async def retry_with_fix(self, question_data: Dict, quiz_url: str, 
                            failed_code: str, error: str, start_time: datetime) -> Dict:
        """Retry after execution error - generate fixed code"""
        logger.info("[HANDLER] 🔄 RETRY ATTEMPT (after execution error)")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        remaining = settings.QUIZ_TIMEOUT_SECONDS - elapsed
        if remaining < settings.SKIP_THRESHOLD_SECONDS:
            return {'status': 'error', 'next_url': None}
            
        try:
            fixed_code = await self.llm_solver.analyze_error_and_retry(
                question_data, failed_code, error
            )
            execution_result = await self.code_executor.execute_code(fixed_code, quiz_url)
            
            if not execution_result['success']:
                return {'status': 'error', 'next_url': None}
            
            submission_result = execution_result.get('submission_result', {})
            if submission_result.get('correct'):
                return {'status': 'correct', 'next_url': submission_result.get('next_url')}
            else:
                return {'status': 'incorrect', 'next_url': submission_result.get('next_url')}
        except Exception:
            return {'status': 'error', 'next_url': None}

    async def retry_with_feedback(self, question_data: Dict, quiz_url: str, 
                                  error_reason: str, failed_code: str, previous_output: str, start_time: datetime) -> Dict:
        """Retry after incorrect answer - generate new solution with feedback"""
        logger.info("[HANDLER] 🔄 RETRY ATTEMPT (answer was incorrect)")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        remaining = settings.QUIZ_TIMEOUT_SECONDS - elapsed
        if remaining < settings.SKIP_THRESHOLD_SECONDS:
            return {'status': 'incorrect', 'next_url': None}
            
        try:
            retry_code = await self.llm_solver.generate_solution(
                question_data,
                previous_error=error_reason,
                failed_code=failed_code,
                previous_output=previous_output
            )
            execution_result = await self.code_executor.execute_code(retry_code, quiz_url)
            
            if not execution_result['success']:
                return {'status': 'error', 'next_url': None}
            
            submission_result = execution_result.get('submission_result', {})
            if not submission_result:
                return {'status': 'error', 'next_url': None}
            if submission_result.get('correct'):
                return {'status': 'correct', 'next_url': submission_result.get('next_url')}
            else:
                return {'status': 'incorrect', 'next_url': submission_result.get('next_url')}
        except Exception:
            return {'status': 'error', 'next_url': None}
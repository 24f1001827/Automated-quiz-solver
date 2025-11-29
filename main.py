"""
FastAPI Server for Data Science Quiz Solver
Handles incoming POST requests and orchestrates the quiz solving process
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
import logging
from datetime import datetime
import asyncio

from config import settings
from quiz_handler import QuizHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/quiz_solver_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Science Quiz Solver", version="1.0.0")

class QuizRequest(BaseModel):
    email: str
    secret: str
    url: str

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("=" * 80)
    logger.info("Starting Data Science Quiz Solver API")
    logger.info(f"Student Email: {settings.STUDENT_EMAIL}")
    logger.info(f"Gemini Model: {settings.GEMINI_MODEL}")
    logger.info("=" * 80)

@app.post("/")
async def handle_quiz(request: Request):
    """
    Main endpoint to receive quiz requests
    Validates secret and initiates quiz solving process
    """
    start_time = datetime.now()
    logger.info("\n" + "=" * 80)
    logger.info(f"[NEW REQUEST] Received at {start_time}")
    
    try:
        # Parse JSON payload
        try:
            payload = await request.json()
            logger.info(f"[PAYLOAD] {payload}")
        except Exception as e:
            logger.error(f"[ERROR] Invalid JSON: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        # Validate payload structure
        try:
            quiz_data = QuizRequest(**payload)
        except ValidationError as e:
            logger.error(f"[ERROR] Validation failed: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid payload structure")
        
        # Verify secret
        logger.info(f"[AUTH] Validating secret for email: {quiz_data.email}")
        if quiz_data.secret != settings.STUDENT_SECRET:
            logger.error(f"[AUTH FAILED] Invalid secret provided: '{quiz_data.secret}'")
            raise HTTPException(status_code=403, detail="Invalid secret")
        
        logger.info(f"[AUTH SUCCESS] Secret validated for {quiz_data.email}")
        
        # Verify email matches
        if quiz_data.email != settings.STUDENT_EMAIL:
            logger.warning(f"[WARNING] Email mismatch: received '{quiz_data.email}', expected '{settings.STUDENT_EMAIL}'")
        
        logger.info(f"[QUIZ START] Quiz URL: {quiz_data.url}")
        
        # Start quiz solving process (non-blocking)
        asyncio.create_task(solve_quiz_async(quiz_data.url, quiz_data.email, quiz_data.secret, start_time))
        
        # Return immediate 200 response
        logger.info(f"[RESPONSE] Returning HTTP 200 - Quiz solving started in background")
        return JSONResponse(
            status_code=200,
            content={
                "status": "accepted",
                "message": "Quiz solving process initiated",
                "email": quiz_data.email,
                "url": quiz_data.url
            }
        )
        
    except HTTPException as he:
        logger.error(f"[HTTP ERROR] Status {he.status_code}: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"[UNEXPECTED ERROR] {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

async def solve_quiz_async(quiz_url: str, email: str, secret: str, start_time: datetime):
    """
    Asynchronously solve the quiz
    This runs in the background after returning 200 response
    """
    try:
        logger.info(f"[BACKGROUND TASK] Starting quiz solving process")
        handler = QuizHandler(email, secret)
        await handler.solve_quiz_sequence(quiz_url, start_time)
        logger.info(f"[BACKGROUND TASK] Quiz solving process completed")
    except Exception as e:
        logger.error(f"[BACKGROUND TASK ERROR] {type(e).__name__}: {str(e)}", exc_info=True)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "email": settings.STUDENT_EMAIL
    }

@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "service": "Data Science Quiz Solver",
        "version": "1.0.0",
        "student": settings.STUDENT_EMAIL,
        "endpoints": {
            "POST /": "Submit quiz request",
            "GET /health": "Health check"
        }
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
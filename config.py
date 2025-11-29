"""
Configuration management for Quiz Solver
Loads environment variables and validates settings
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os
from pathlib import Path
import google.generativeai as genai

# Create logs directory if it doesn't exist
Path("logs").mkdir(exist_ok=True)

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Student credentials
    STUDENT_EMAIL: str = "24f1001827@ds.study.iitm.ac.in"
    STUDENT_SECRET: str 
    
    # Google Gemini API
    GEMINI_API_KEY: str 
    GEMINI_MODEL: str = "gemini-2.5-pro" # Flash is fast/cheap, Pro is smarter
    
    # Quiz solving settings
    QUIZ_TIMEOUT_SECONDS: int = 180  # 3 minutes total
    SKIP_THRESHOLD_SECONDS: int = 15  # Skip to next if less than this remaining
    MAX_RETRIES_PER_QUESTION: int = 1  # Retry attempts per question
    
    # Browser settings
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT: int = 30000  # 30 seconds
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Global settings instance
settings = Settings()

# Validate critical settings
def validate_settings():
    """Validate that all required settings are configured"""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY must be set in .env file")
    if not settings.STUDENT_EMAIL:
        raise ValueError("STUDENT_EMAIL must be set")
    if not settings.STUDENT_SECRET:
        raise ValueError("STUDENT_SECRET must be set")
    
    # Configure Gemini globally
    genai.configure(api_key=settings.GEMINI_API_KEY)

# Run validation on import
validate_settings()
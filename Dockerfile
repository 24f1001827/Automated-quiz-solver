# Use the official Playwright image (Includes Python 3 + Browsers + System Dependencies)
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

# Set the working directory inside the container
WORKDIR /app

# 1. Install System Dependencies for GeoPandas and OpenCV
# Playwright image has some, but these cover the rest
RUN apt-get update && apt-get install -y \
    libgdal-dev \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Copy requirements and install Python libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Install the specific browsers Playwright needs
RUN playwright install chromium

# 4. Copy your application code
COPY . .

# 5. Create logs directory (required by your config.py)
RUN mkdir -p logs

# 6. Run the application
# Render provides the port in the $PORT environment variable
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
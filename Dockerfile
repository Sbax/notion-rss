FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY notion-reader.py .

# Run the notion-reader script, using environment variables passed from .env
CMD ["python", "notion-reader.py"]

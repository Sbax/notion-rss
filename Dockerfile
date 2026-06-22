FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY notion-reader.py .

# Install cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Add cron job (every 3 hours)
RUN echo "0 */3 * * * cd /app && python notion-reader.py >> /var/log/cron.log 2>&1" | crontab -

CMD ["sh", "-c", "python notion-reader.py && cron -f"]
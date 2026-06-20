FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY notion-reader.py /app/notion-reader.py
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
COPY links_cache.json /app/links_cache.json

RUN mkdir -p /app/public
RUN chmod +x /app/docker-entrypoint.sh

ENV LINKS_STORE=/app/links_cache.json
ENV RSS_OUTPUT=/app/public/rss.xml
EXPOSE 8080

CMD ["/app/docker-entrypoint.sh"]

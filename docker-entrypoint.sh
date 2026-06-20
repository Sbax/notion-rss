#!/bin/sh
set -eu

STORE_PATH="${LINKS_STORE:-/app/links_cache.json}"
RSS_PATH="${RSS_OUTPUT:-/app/public/rss.xml}"
MAX_ITEMS="${RSS_MAX_ITEMS:-100}"
PORT="${PORT:-8080}"
SYNC_INTERVAL_SECONDS="${SYNC_INTERVAL_SECONDS:-86400}"

mkdir -p "$(dirname "$RSS_PATH")"

generate_rss_only() {
  python /app/notion-reader.py \
    --mode rss \
    --store "$STORE_PATH" \
    --rss-output "$RSS_PATH" \
    --rss-title "${RSS_TITLE:-Notion Feed}" \
    --rss-link "${RSS_LINK:-http://localhost:8080/rss.xml}" \
    --rss-description "${RSS_DESCRIPTION:-Links collected from Notion/cache}" \
    --max-items "$MAX_ITEMS"
}

sync_and_generate() {
  python /app/notion-reader.py \
    --mode all \
    --store "$STORE_PATH" \
    --rss-output "$RSS_PATH" \
    --rss-title "${RSS_TITLE:-Notion Feed}" \
    --rss-link "${RSS_LINK:-http://localhost:8080/rss.xml}" \
    --rss-description "${RSS_DESCRIPTION:-Links collected from Notion/cache}" \
    --max-items "$MAX_ITEMS"
}

# Ensure RSS exists from cache even before the first sync attempt.
generate_rss_only || true

(
  while true; do
    if sync_and_generate; then
      echo "[scheduler] sync completed"
    else
      echo "[scheduler] sync failed; will retry after interval"
    fi

    sleep "$SYNC_INTERVAL_SECONDS"
  done
) &

exec python -m http.server "$PORT" --directory /app/public
#!/usr/bin/env python3
"""Fetch a Notion page by URL using notion-py.

Usage:
    python notion_page_cache.py "https://www.notion.so/..."
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape
from typing import Any

from notion.client import NotionClient, create_session
from notion.store import RecordStore
from notion.monitor import Monitor


class NotionWrapper(NotionClient):
    def _update_user_info(self):
        pass

    def __init__(
        self
    ):
        self.session = create_session(None)
        self._store = RecordStore(self)
        self._monitor = None
        self._update_user_info()


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key:
                os.environ.setdefault(key, value)




def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _get_block_title(block: Any) -> str:
    title = getattr(block, "title", "")
    if isinstance(title, str):
        return title.strip()
    return ""


def _collect_text(block: Any, out: list[str]) -> None:
    title = _get_block_title(block)
    if title:
        out.append(title)

    try:
        children = list(block.children)
    except Exception:
        children = []

    for child in children:
        _collect_text(child, out)


def _extract_link_items_from_title_prop(title_prop: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not isinstance(title_prop, list):
        return items

    # Notion may split one visible title across multiple rich-text parts
    # (for example a leading emoji in one part and linked text in another).
    # Rebuild the full rendered title while keeping the first hyperlink target.
    full_text_parts: list[str] = []
    first_url = ""
    for part in title_prop:
        if not isinstance(part, list) or not part:
            continue

        text = part[0] if isinstance(part[0], str) else ""
        if text:
            full_text_parts.append(text)

        if not first_url:
            formats = part[1] if len(part) > 1 and isinstance(part[1], list) else []
            for fmt in formats:
                if isinstance(fmt, list) and len(fmt) > 1 and fmt[0] == "a" and isinstance(fmt[1], str):
                    first_url = fmt[1].strip().rstrip(").,;!?")
                    break

    full_text = "".join(full_text_parts).strip()
    if first_url and full_text:
        items.append({"title": full_text, "url": first_url})

    return items


def _collect_link_items(block: Any, out: list[dict[str, str]]) -> None:
    try:
        block.get("properties")
        print(block.get("properties"))
        title_prop = block.get("properties.title")
    except Exception:
        title_prop = None

    out.extend(_extract_link_items_from_title_prop(title_prop))

    try:
        children = list(block.children)
    except Exception:
        children = []

    for child in children:
        _collect_link_items(child, out)


def _load_items(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return []

    items: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        fetched_at = item.get("fetched_at")
        if not isinstance(url, str) or not isinstance(fetched_at, str):
            continue
        title = item.get("title")
        if not isinstance(title, str):
            title = ""
        items.append({"title": title, "url": url, "fetched_at": fetched_at})

    return items


def _save_items(path: str, items: list[dict[str, str]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def _parse_iso_datetime(raw_value: str) -> datetime:
    value = raw_value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _build_rss_xml(
    items: list[dict[str, str]],
    rss_title: str,
    max_items: int,
) -> str:
    prepared_items: list[tuple[str, str, str]] = []

    for item in items:
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        fetched_at = item.get("fetched_at", "").strip()
        if not title or not url or not fetched_at:
            continue
        prepared_items.append((title, url, fetched_at))

    if max_items > 0:
        prepared_items = prepared_items[:max_items]

    latest_dt = _now_utc()
    if prepared_items:
        try:
            latest_dt = _parse_iso_datetime(prepared_items[0][2])
        except ValueError:
            latest_dt = _now_utc()

    xml_items: list[str] = []
    for title, url, fetched_at in prepared_items:
        try:
            published_dt = _parse_iso_datetime(fetched_at)
            pub_date = format_datetime(published_dt)
        except ValueError:
            pub_date = format_datetime(_now_utc())

        xml_items.append(
            "\n".join(
                [
                    "    <entry>",
                    f"      <title>{escape(title)}</title>",
                    f"      <link>{escape(url)}</link>",
                    f"      <id>{escape(url)}</id>",
                    f"      <published>{escape(pub_date)}</published>",
                    f"      <updated>{escape(pub_date)}</updated>",
                    f"      <content>{escape(title)}</content>",
                    "    </entry>",
                ]
            )
        )

    channel_blocks = [
        f"    <title>{escape(rss_title)}</title>",
        f"    <updated>{escape(format_datetime(latest_dt))}</updated>",
    ]

    if xml_items:
        channel_blocks.extend(xml_items)

    channel_xml = "\n".join(channel_blocks)
    return "\n".join(
        [
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
            "<feed xmlns=\"http://www.w3.org/2005/Atom\" xmlns:media=\"http://search.yahoo.com/mrss/\">",
            channel_xml,
            "</feed>",
            "",
        ]
    )


def generate_rss_from_cache(
    store_path: str,
    rss_output: str,
    rss_title: str,
    max_items: int,
) -> dict[str, Any]:
    items = _load_items(store_path)
    rss_xml = _build_rss_xml(
        items=items,
        rss_title=rss_title,
        max_items=max_items,
    )

    output_dir = os.path.dirname(rss_output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(rss_output, "w", encoding="utf-8") as f:
        f.write(rss_xml)

    return {
        "rss_output": rss_output,
        "rss_items_count": min(len(items), max_items) if max_items > 0 else len(items),
    }


def update_items(found_items: list[dict[str, str]], existing_items: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    existing_urls = {item["url"] for item in existing_items if "url" in item}
    fetched_at = _now_utc().isoformat()

    new_items: list[dict[str, str]] = []
    for found_item in found_items:
        link = found_item.get("url", "").strip()
        if not link:
            continue
        title = found_item.get("title", "").strip()
        if not title:
            continue
        # Add only URLs that are not already in cache (or already queued in this run).
        if link in existing_urls:
            continue
        new_items.append(
            {
                "title": title,
                "url": link,
                "fetched_at": fetched_at,
            }
        )
        existing_urls.add(link)

    updated_items = new_items + existing_items
    return updated_items, new_items


def fetch_page_data(url: str) -> dict[str, Any]:
    client = NotionWrapper()
    page = client.get_block(url)

    text_chunks: list[str] = []
    _collect_text(page, text_chunks)

    link_items: list[dict[str, str]] = []
    _collect_link_items(page, link_items)

    # Keep first occurrence order while de-duplicating by URL.
    deduped_link_items: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in link_items:
        item_url = item.get("url", "")
        if not item_url or item_url in seen_urls:
            continue
        seen_urls.add(item_url)
        deduped_link_items.append(item)

    return {
        "url": url,
        "page_id": getattr(page, "id", None),
        "title": _get_block_title(page),
        "text": "\n".join(text_chunks),
        "link_items": deduped_link_items,
        "fetched_at": _now_utc().isoformat(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read a Notion page by URL.")
    parser.add_argument(
        "url",
        nargs="?",
        default=os.environ.get("NOTION_PAGE_URL"),
        help="Notion page URL (defaults to NOTION_PAGE_URL in .env/env)",
    )
    parser.add_argument(
        "--store",
        default=os.environ.get("LINKS_STORE", "links_cache.json"),
        help="Path to JSON file storing collected links (default: LINKS_STORE or links_cache.json)",
    )
    parser.add_argument(
        "--rss-output",
        default=os.environ.get("RSS_OUTPUT", "feed"),
        help="Path to generated RSS XML file (default: RSS_OUTPUT or feed)",
    )
    parser.add_argument(
        "--rss-title",
        default=os.environ.get("RSS_TITLE", "Notion Feed"),
        help="RSS channel title",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=int(os.environ.get("RSS_MAX_ITEMS", "100")),
        help="Maximum number of items in RSS output (default: 100)",
    )
    return parser.parse_args()


def main() -> None:
    _load_dotenv()
    args = parse_args()
    output: dict[str, Any] = {}
    if not args.url:
        raise SystemExit("Notion page URL is required. Pass URL or set NOTION_PAGE_URL in .env.")

    data = fetch_page_data(url=args.url)
    found_items = data.get("link_items", [])

    existing_items = _load_items(args.store)
    updated_items, new_items = update_items(found_items, existing_items)
    _save_items(args.store, updated_items)

    output["sync"] = {
        "new_items_count": len(new_items),
        "total_items_count": len(updated_items),
        "new_items": new_items,
        "items": updated_items,
    }

    output["rss"] = generate_rss_from_cache(
        store_path=args.store,
        rss_output=args.rss_output,
        rss_title=args.rss_title,
        max_items=args.max_items,
    )

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
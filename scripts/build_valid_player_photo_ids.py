#!/usr/bin/env python3
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PHOTO_CATALOG_PATH = ROOT / "webapp" / "baseball" / "data" / "player_photos.json"
OUTPUT_PATH = ROOT / "webapp" / "baseball" / "data" / "player_photo_valid_ids.json"
MAX_WORKERS = 128
TIMEOUT = 1.5


def photo_url_is_available(url):
    url = str(url or "").strip()
    if not url:
        return False

    request = Request(
        url,
        headers={"User-Agent": "BaseBallX/1.0"},
        method="HEAD",
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            content_type = response.headers.get_content_type()
            return bool(content_type and content_type.startswith("image/"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return False


def validate_entry(item):
    bbref_id, entry = item
    for url in (entry.get("photo_url", ""), entry.get("photo_fallback_url", "")):
        if photo_url_is_available(url):
            return bbref_id, True
    return bbref_id, False


def main():
    catalog = json.loads(PHOTO_CATALOG_PATH.read_text())
    valid_ids = []
    items = list(catalog.items())

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(validate_entry, item) for item in items]
        for index, future in enumerate(as_completed(futures), start=1):
            bbref_id, is_valid = future.result()
            if is_valid:
                valid_ids.append(bbref_id)
            if index % 500 == 0 or index == len(items):
                print(f"validated {index}/{len(items)}", flush=True)

    valid_ids.sort()
    OUTPUT_PATH.write_text(json.dumps({"valid_ids": valid_ids}, indent=2))
    print(f"saved {len(valid_ids)} valid ids to {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()

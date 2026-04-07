#!/usr/bin/env python3

import csv
import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MASTER_CSV = ROOT / "archive" / "Master.csv"
OUTPUT_JSON = ROOT / "webapp" / "baseball" / "data" / "bbref_headshot_cache.json"
HEADSHOT_RE = re.compile(
    r'https://www\.baseball-reference\.com/req/[^"\']+/images/headshots/[^"\']+\.(?:jpg|jpeg|png)'
)
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
}


def iter_bbref_ids():
    with MASTER_CSV.open() as handle:
        reader = csv.DictReader(handle)
        seen = set()
        for row in reader:
            bbref_id = (row.get("bbrefID") or "").strip()
            if bbref_id and bbref_id not in seen:
                seen.add(bbref_id)
                yield bbref_id


def build_player_url(bbref_id):
    return f"https://www.baseball-reference.com/players/{bbref_id[0]}/{bbref_id}.shtml"


def fetch_html(url, timeout=12):
    request = Request(url, headers=REQUEST_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def load_existing():
    if not OUTPUT_JSON.exists():
        return {}
    with OUTPUT_JSON.open() as handle:
        return json.load(handle)


def save_mapping(mapping):
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(mapping, indent=2, sort_keys=True))


def main():
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print("First argument must be an integer limit.", file=sys.stderr)
            return 2

    mapping = load_existing()
    processed = 0
    found = 0

    for bbref_id in iter_bbref_ids():
        if bbref_id in mapping:
            continue
        if limit is not None and processed >= limit:
            break

        processed += 1
        url = build_player_url(bbref_id)
        try:
            html = fetch_html(url)
        except HTTPError as exc:
            if exc.code == 429:
                print(f"Rate limited at {bbref_id}; saving partial cache.")
                break
            continue
        except (URLError, TimeoutError, ValueError):
            continue

        match = HEADSHOT_RE.search(html)
        if match:
            mapping[bbref_id] = match.group(0)
            found += 1

        if processed % 50 == 0:
            save_mapping(mapping)
            print(f"Processed {processed}, found {found}")

        time.sleep(0.35)

    save_mapping(mapping)
    print(f"Done. Cached {len(mapping)} headshots at {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "webapp" / "baseball" / "data"
MLBAM_CACHE_PATH = DATA_DIR / "bbref_mlbam_cache.json"
BBREF_HEADSHOT_CACHE_PATH = DATA_DIR / "bbref_headshot_cache.json"
OUTPUT_PATH = DATA_DIR / "player_photos.json"
MLB_HEADSHOT_URLS = (
    "https://img.mlbstatic.com/mlb-photos/image/upload/c_fill,g_auto,w_360/v1/people/{mlbam}/headshot/67/current",
    "https://img.mlbstatic.com/mlb-photos/image/upload/c_fill,g_auto,w_360/v1/people/{mlbam}/headshot/milb/current",
)


def load_json(path):
    if not path.exists():
        return {}
    with path.open() as handle:
        return json.load(handle)


def build_catalog():
    mlbam_cache = load_json(MLBAM_CACHE_PATH)
    bbref_headshots = load_json(BBREF_HEADSHOT_CACHE_PATH)

    catalog = {}
    all_ids = sorted(set(mlbam_cache) | set(bbref_headshots))

    for bbref_id in all_ids:
        mlbam_id = str(mlbam_cache.get(bbref_id, "")).strip()
        bbref_url = str(bbref_headshots.get(bbref_id, "")).strip()

        photo_url = ""
        fallback_url = ""
        source = ""

        if bbref_url:
            photo_url = bbref_url
            source = "bbref"
            if mlbam_id:
                fallback_url = MLB_HEADSHOT_URLS[0].format(mlbam=mlbam_id)
        elif mlbam_id:
            photo_url = MLB_HEADSHOT_URLS[0].format(mlbam=mlbam_id)
            fallback_url = MLB_HEADSHOT_URLS[1].format(mlbam=mlbam_id)
            source = "mlb"

        if photo_url:
            catalog[bbref_id] = {
                "photo_url": photo_url,
                "photo_fallback_url": fallback_url,
                "source": source,
            }

    return catalog


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog()
    OUTPUT_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=True))
    print(f"Wrote {len(catalog)} player photos to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

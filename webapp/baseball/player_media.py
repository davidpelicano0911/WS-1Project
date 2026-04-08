import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PHOTO_CATALOG_PATH = Path(__file__).with_name("data").joinpath("player_photos.json")
MLB_WIDTH_RE = re.compile(r"w_(\d+)")


def build_bbref_player_url(bbref_id):
    bbref_id = str(bbref_id or "").strip()
    if not bbref_id:
        return ""
    return f"https://www.baseball-reference.com/players/{bbref_id[0]}/{bbref_id}.shtml"


def _resize_mlb_photo_url(url, width):
    url = str(url or "").strip()
    if not url:
        return ""
    if "img.mlbstatic.com" not in url:
        return url
    return MLB_WIDTH_RE.sub(f"w_{int(width)}", url, count=1)


@lru_cache(maxsize=1)
def _load_player_photo_catalog():
    if not PHOTO_CATALOG_PATH.exists():
        return {}
    with PHOTO_CATALOG_PATH.open() as handle:
        return json.load(handle)


@lru_cache(maxsize=8192)
def get_player_photo_entry(bbref_id):
    bbref_id = str(bbref_id or "").strip()
    if not bbref_id:
        return {}
    return _load_player_photo_catalog().get(bbref_id, {})


def player_has_catalog_photo(bbref_id):
    photo_entry = get_player_photo_entry(bbref_id)
    return bool(photo_entry.get("photo_url") or photo_entry.get("photo_fallback_url"))


@lru_cache(maxsize=1)
def get_catalog_photo_count():
    return sum(
        1
        for photo_entry in _load_player_photo_catalog().values()
        if photo_entry.get("photo_url") or photo_entry.get("photo_fallback_url")
    )


def attach_player_media(player):
    bbref_id = str(player.get("bbref_id", "")).strip()
    photo_entry = get_player_photo_entry(bbref_id)
    photo_url = photo_entry.get("photo_url", "")
    photo_fallback_url = photo_entry.get("photo_fallback_url", "")
    return {
        **player,
        "bbref_id": bbref_id,
        "bbref_url": build_bbref_player_url(bbref_id),
        "photo_url": photo_url,
        "photo_fallback_url": photo_fallback_url,
        "card_photo_url": _resize_mlb_photo_url(photo_url, 220),
        "card_photo_fallback_url": _resize_mlb_photo_url(photo_fallback_url, 220),
        "photo_source": photo_entry.get("source", ""),
    }


@lru_cache(maxsize=512)
def fetch_player_photo_asset(url):
    url = str(url or "").strip()
    if not url or not url.startswith(("https://img.mlbstatic.com/", "https://content.mlb.com/")):
        return None, None

    request = Request(
        url,
        headers={
            "User-Agent": "BaseBallX/1.0",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            return response.read(), response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None, None


def enrich_players_with_media(players, max_workers=8):
    if not players:
        return []
    return [attach_player_media(player) for player in players]

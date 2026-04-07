import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path


PHOTO_CATALOG_PATH = Path(__file__).with_name("data").joinpath("player_photos.json")


def build_bbref_player_url(bbref_id):
    bbref_id = str(bbref_id or "").strip()
    if not bbref_id:
        return ""
    return f"https://www.baseball-reference.com/players/{bbref_id[0]}/{bbref_id}.shtml"


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


def attach_player_media(player):
    bbref_id = str(player.get("bbref_id", "")).strip()
    photo_entry = get_player_photo_entry(bbref_id)
    return {
        **player,
        "bbref_id": bbref_id,
        "bbref_url": build_bbref_player_url(bbref_id),
        "photo_url": photo_entry.get("photo_url", ""),
        "photo_fallback_url": photo_entry.get("photo_fallback_url", ""),
        "photo_source": photo_entry.get("source", ""),
    }


def enrich_players_with_media(players, max_workers=8):
    if not players:
        return []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(attach_player_media, players))

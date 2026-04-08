from django.urls import reverse


COMPARE_SELECTION_SESSION_KEY = "compare_selection"
VALID_COMPARE_TYPES = {"player", "team"}


def _normalize_compare_item(item_type, item_id, label="", year=""):
    item_type = str(item_type or "").strip().lower()
    item_id = str(item_id or "").strip()
    label = str(label or "").strip()
    year = str(year or "").strip()

    if item_type not in VALID_COMPARE_TYPES or not item_id:
        return None

    return {
        "type": item_type,
        "id": item_id,
        "label": label or item_id,
        "year": year,
    }


def get_compare_selection(request):
    raw = request.session.get(COMPARE_SELECTION_SESSION_KEY, {})
    selection_type = raw.get("type")
    items = []

    if selection_type in VALID_COMPARE_TYPES:
        for raw_item in raw.get("items", [])[:2]:
            item = _normalize_compare_item(
                selection_type,
                raw_item.get("id"),
                raw_item.get("label", ""),
                raw_item.get("year", ""),
            )
            if item:
                items.append(item)

    if not items:
        selection_type = None

    return {
        "type": selection_type,
        "items": items,
        "count": len(items),
        "is_full": len(items) == 2,
        "comparator_url": reverse("compare_players"),
    }


def _save_compare_selection(request, selection_type, items):
    if not selection_type or not items:
        request.session.pop(COMPARE_SELECTION_SESSION_KEY, None)
        request.session.modified = True
        return

    request.session[COMPARE_SELECTION_SESSION_KEY] = {
        "type": selection_type,
        "items": items[:2],
    }
    request.session.modified = True


def clear_compare_selection(request):
    request.session.pop(COMPARE_SELECTION_SESSION_KEY, None)
    request.session.modified = True
    return get_compare_selection(request)


def toggle_compare_selection(request, item_type, item_id, label="", year=""):
    item = _normalize_compare_item(item_type, item_id, label, year)
    if not item:
        return {
            "ok": False,
            "error_code": "invalid_item",
            "message": "The selected item could not be added to comparison.",
            "selection": get_compare_selection(request),
        }

    selection = get_compare_selection(request)
    selection_type = selection["type"]
    items = selection["items"]

    if selection_type and selection_type != item["type"] and items:
        return {
            "ok": False,
            "error_code": "type_mismatch",
            "message": (
                "You already have "
                f"{selection_type}s selected for comparison. Clear those first before selecting a {item['type']}."
            ),
            "selection": selection,
        }

    existing_index = next((index for index, existing in enumerate(items) if existing["id"] == item["id"]), None)

    if existing_index is not None:
        existing = items[existing_index]
        if item["type"] == "team" and item.get("year") and existing.get("year") != item["year"]:
            items[existing_index] = item
            _save_compare_selection(request, item["type"], items)
            return {
                "ok": True,
                "status": "updated",
                "message": "Comparison selection updated.",
                "selection": get_compare_selection(request),
            }

        del items[existing_index]
        _save_compare_selection(request, item["type"], items)
        return {
            "ok": True,
            "status": "removed",
            "message": "Removed from comparison.",
            "selection": get_compare_selection(request),
        }

    if len(items) >= 2:
        return {
            "ok": False,
            "error_code": "max_reached",
            "message": "You can only compare up to two items at the same time.",
            "selection": selection,
        }

    items.append(item)
    _save_compare_selection(request, item["type"], items)
    return {
        "ok": True,
        "status": "selected",
        "message": "Added to comparison.",
        "selection": get_compare_selection(request),
    }

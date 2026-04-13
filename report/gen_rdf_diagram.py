#!/usr/bin/env python3
"""Render a readable RDF concept diagram for rdf/baseball.n3."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ModuleNotFoundError as exc:
    if exc.name == "PIL":
        raise SystemExit("Missing dependency: pillow") from exc
    raise


ROOT = Path(__file__).resolve().parent.parent
N3_PATH = ROOT / "rdf" / "baseball.n3"
OUT_PATH = Path(__file__).resolve().parent / "images" / "rdf_data_model.png"

CANVAS_W = 1760
CANVAS_H = 980
BG = "#ffffff"
TEXT = "#111827"
MUTED = "#6b7280"
EDGE = "#1f2937"
LABEL_FILL = "#f8fafc"
LABEL_BORDER = "#d1d5db"
BOX_FILL = "#ffffff"
BOX_BORDER = "#374151"
SHADOW = "#00000018"
HEADER_H = 18
BOX_W = 250
BOX_H = 82

PALETTES = {
    "player": ("#fee2e2", "#b91c1c"),
    "team": ("#dbeafe", "#1d4ed8"),
    "stat": ("#dcfce7", "#15803d"),
    "award": ("#fef3c7", "#b45309"),
    "post": ("#ede9fe", "#7c3aed"),
    "org": ("#e0e7ff", "#4338ca"),
}

CLASS_STYLE = {
    "Player": "player",
    "Team": "team",
    "Manager": "team",
    "Franchise": "org",
    "BattingStat": "stat",
    "PitchingStat": "stat",
    "Salary": "stat",
    "AllStarAppearance": "stat",
    "Award": "award",
    "HallOfFameVote": "award",
    "WorldSeriesResult": "post",
}

POSITIONS = {
    "BattingStat": (80, 180),
    "PitchingStat": (80, 390),
    "HallOfFameVote": (80, 730),
    "Player": (430, 280),
    "Award": (430, 600),
    "Team": (930, 210),
    "Manager": (930, 540),
    "Franchise": (1410, 80),
    "WorldSeriesResult": (1410, 210),
    "Salary": (1410, 430),
    "AllStarAppearance": (1410, 650),
}

ROUTES = [
    {
        "key": ("Player", "hasBatting", "BattingStat"),
        "path": [("Player", "left", 0.30), (360, 325), (360, 220), ("BattingStat", "right", 0.40)],
        "label": (275, 305),
    },
    {
        "key": ("Player", "hasPitching", "PitchingStat"),
        "path": [("Player", "left", 0.66), (360, 365), (360, 440), ("PitchingStat", "right", 0.45)],
        "label": (275, 390),
    },
    {
        "key": ("Player", "hallOfFameVote", "HallOfFameVote"),
        "path": [("Player", "left", 0.88), (340, 395), (340, 772), ("HallOfFameVote", "right", 0.52)],
        "label": (232, 600),
    },
    {
        "key": ("Player", "wonAward", "Award"),
        "path": [("Player", "bottom", 0.43), (537, 480), (537, 600), ("Award", "top", 0.50)],
        "label": (472, 545),
    },
    {
        "key": ("Player", "isManager", "Manager"),
        "path": [("Player", "bottom", 0.78), (640, 510), (640, 581), ("Manager", "left", 0.50)],
        "label": (720, 575),
    },
    {
        "key": ("Player", "hasSalary", "Salary"),
        "path": [("Player", "right", 0.36), (790, 340), (790, 461), (1320, 461), ("Salary", "left", 0.40)],
        "label": (830, 447),
    },
    {
        "key": ("Player", "playedInAllStar", "AllStarAppearance"),
        "path": [("Player", "right", 0.70), (805, 368), (805, 687), (1325, 687), ("AllStarAppearance", "left", 0.45)],
        "label": (850, 670),
    },
    {
        "key": ("BattingStat", "teamOf", "Team"),
        "path": [("BattingStat", "right", 0.28), (845, 203), (845, 228), ("Team", "left", 0.18)],
        "label": (650, 196),
    },
    {
        "key": ("PitchingStat", "teamOf", "Team"),
        "path": [("PitchingStat", "right", 0.74), (845, 450), (845, 269), ("Team", "left", 0.72)],
        "label": (650, 442),
    },
    {
        "key": ("Salary", "teamOf", "Team"),
        "path": [("Salary", "left", 0.34), (1325, 458), (1325, 334), ("Team", "right", 0.60)],
        "label": (1294, 405),
    },
    {
        "key": ("AllStarAppearance", "teamOf", "Team"),
        "path": [("AllStarAppearance", "left", 0.35), (1290, 679), (1290, 380), ("Team", "right", 0.86)],
        "label": (1256, 586),
    },
    {
        "key": ("Manager", "managedTeam", "Team"),
        "path": [("Manager", "top", 0.50), ("Team", "bottom", 0.50)],
        "label": (1065, 470),
    },
    {
        "key": ("Team", "franchiseOf", "Franchise"),
        "path": [("Team", "right", 0.18), (1350, 225), (1350, 125), ("Franchise", "left", 0.55)],
        "label": (1346, 170),
    },
    {
        "key": ("WorldSeriesResult", "winnerTeam", "Team"),
        "path": [("WorldSeriesResult", "left", 0.32), (1350, 236), (1350, 230), ("Team", "right", 0.24)],
        "label": (1302, 214),
    },
    {
        "key": ("WorldSeriesResult", "loserTeam", "Team"),
        "path": [("WorldSeriesResult", "left", 0.68), (1335, 266), (1335, 251), ("Team", "right", 0.50)],
        "label": (1292, 290),
    },
]


@dataclass
class Box:
    name: str
    x: int
    y: int

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        return self.x, self.y, self.x + BOX_W, self.y + BOX_H

    def anchor(self, side: str, t: float) -> Tuple[float, float]:
        if side == "left":
            return self.x, self.y + BOX_H * t
        if side == "right":
            return self.x + BOX_W, self.y + BOX_H * t
        if side == "top":
            return self.x + BOX_W * t, self.y
        if side == "bottom":
            return self.x + BOX_W * t, self.y + BOX_H
        raise ValueError(f"Unsupported side: {side}")


def load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def parse_n3(path: Path) -> Tuple[Counter, Counter]:
    prefixes: Dict[str, str] = {}
    triples: List[Tuple[str, str, str]] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@prefix "):
            _, prefix, iri, _ = line.split()
            prefixes[prefix[:-1]] = iri[1:-1]
            continue
        if not line.endswith(" ."):
            continue
        body = line[:-2]
        parts = body.split(" ", 2)
        if len(parts) == 3:
            triples.append((parts[0], parts[1], parts[2]))

    def expand(term: str) -> str:
        if term.startswith("<") and term.endswith(">"):
            return term[1:-1]
        if term.startswith('"'):
            return term
        if ":" in term:
            prefix, local = term.split(":", 1)
            iri = prefixes.get(prefix)
            if iri:
                return iri + local
        return term

    rdf_type = prefixes["rdf"] + "type"
    owl_class = prefixes["owl"] + "Class"
    bb_prefix = prefixes["bb"]

    classes = set()
    for s, p, o in triples:
        if expand(p) == rdf_type and expand(o) == owl_class:
            classes.add(expand(s))

    instance_type: Dict[str, str] = {}
    class_counts: Counter = Counter()
    for s, p, o in triples:
        s_val, p_val, o_val = expand(s), expand(p), expand(o)
        if p_val == rdf_type and o_val in classes:
            instance_type[s_val] = o_val
            class_counts[o_val[len(bb_prefix):]] += 1

    relation_counts: Counter = Counter()
    for s, p, o in triples:
        s_val, p_val = expand(s), expand(p)
        if s_val not in instance_type or o.startswith('"'):
            continue
        o_val = expand(o)
        target_type = instance_type.get(o_val)
        if not target_type:
            continue
        relation_counts[
            (
                instance_type[s_val][len(bb_prefix):],
                p_val[len(bb_prefix):] if p_val.startswith(bb_prefix) else p_val,
                target_type[len(bb_prefix):],
            )
        ] += 1

    return class_counts, relation_counts


def resolve_point(boxes: Dict[str, Box], point) -> Tuple[float, float]:
    if isinstance(point, tuple) and len(point) == 3 and isinstance(point[0], str):
        return boxes[point[0]].anchor(point[1], point[2])
    return point


def draw_box(draw: ImageDraw.ImageDraw, box: Box, font, small_font) -> None:
    header_fill, header_text = PALETTES[CLASS_STYLE[box.name]]
    x0, y0, x1, y1 = box.rect
    draw.rounded_rectangle((x0 + 5, y0 + 6, x1 + 5, y1 + 6), radius=10, fill=SHADOW)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=BOX_FILL, outline=BOX_BORDER, width=2)
    draw.rounded_rectangle((x0, y0, x1, y0 + HEADER_H), radius=10, fill=header_fill)
    draw.rectangle((x0, y0 + HEADER_H - 10, x1, y0 + HEADER_H), fill=header_fill)
    draw.text((x0 + BOX_W / 2, y0 + HEADER_H + 28), f"bb:{box.name}", fill=TEXT, font=font, anchor="mm")
    draw.text((x0 + BOX_W / 2, y0 + 9), CLASS_STYLE[box.name].upper(), fill=header_text, font=small_font, anchor="mm")


def draw_label(draw: ImageDraw.ImageDraw, text: str, xy: Tuple[float, float], font) -> None:
    content = f"bb:{text}"
    bbox = draw.textbbox((0, 0), content, font=font)
    pad_x = 7
    pad_y = 4
    x, y = xy
    draw.rounded_rectangle(
        (
            x - (bbox[2] - bbox[0]) / 2 - pad_x,
            y - (bbox[3] - bbox[1]) / 2 - pad_y,
            x + (bbox[2] - bbox[0]) / 2 + pad_x,
            y + (bbox[3] - bbox[1]) / 2 + pad_y,
        ),
        radius=6,
        fill=LABEL_FILL,
        outline=LABEL_BORDER,
        width=1,
    )
    draw.text((x, y), content, fill=MUTED, font=font, anchor="mm")


def draw_poly_arrow(draw: ImageDraw.ImageDraw, points: List[Tuple[float, float]]) -> None:
    for a, b in zip(points, points[1:]):
        draw.line((*a, *b), fill=EDGE, width=2)

    sx, sy = points[-2]
    ex, ey = points[-1]
    dx = ex - sx
    dy = ey - sy
    length = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux = dx / length
    uy = dy / length
    px = -uy
    py = ux
    head = 13
    wing = 6
    p1 = (ex, ey)
    p2 = (ex - ux * head + px * wing, ey - uy * head + py * wing)
    p3 = (ex - ux * head - px * wing, ey - uy * head - py * wing)
    draw.polygon([p1, p2, p3], fill=EDGE)


def render() -> Path:
    class_counts, relation_counts = parse_n3(N3_PATH)
    boxes = {
        name: Box(name=name, x=xy[0], y=xy[1])
        for name, xy in POSITIONS.items()
        if class_counts.get(name)
    }

    required = set(POSITIONS)
    missing = sorted(required - set(boxes))
    if missing:
        raise SystemExit(f"Missing expected populated classes in {N3_PATH}: {', '.join(missing)}")

    image = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(image)

    title_font = load_font(30, bold=True)
    subtitle_font = load_font(15, bold=False)
    box_font = load_font(18, bold=False)
    tag_font = load_font(11, bold=True)
    label_font = load_font(13, bold=False)

    draw.text((CANVAS_W / 2, 50), "Baseball RDF Data Diagram", fill=TEXT, font=title_font, anchor="mm")
    draw.text((CANVAS_W / 2, 80), "Simplified concept map extracted from rdf/baseball.n3", fill=MUTED, font=subtitle_font, anchor="mm")

    labels: List[Tuple[str, Tuple[float, float]]] = []

    for route in ROUTES:
        key = route["key"]
        if relation_counts.get(key):
            points = [resolve_point(boxes, p) for p in route["path"]]
            draw_poly_arrow(draw, points)
            labels.append((key[1], route["label"]))

    for name in POSITIONS:
        draw_box(draw, boxes[name], box_font, tag_font)

    for text, xy in labels:
        draw_label(draw, text, xy, label_font)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT_PATH)
    return OUT_PATH


def main() -> None:
    out = render()
    print(f"Saved {out}")


if __name__ == "__main__":
    main()

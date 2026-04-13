#!/usr/bin/env python3
"""Clean light-mode ER diagram – straight arrows, no legend, black text."""

from pathlib import Path

# ── Layout ────────────────────────────────────────────────────────────────────
BOX_W, BOX_H = 183, 122
COL_STEP     = 248
ROW_STEP     = 155
MARGIN_X     = 34
MARGIN_Y     = 48
CANVAS_W     = 5 * COL_STEP + 2 * MARGIN_X   # 1158
CANVAS_H     = 5 * ROW_STEP + 2 * MARGIN_Y   # 871

def bx(c): return MARGIN_X + c * COL_STEP
def by(r): return MARGIN_Y + r * ROW_STEP
def bcx(c): return bx(c) + BOX_W // 2
def bcy(r): return by(r) + BOX_H // 2

# ── Colours ───────────────────────────────────────────────────────────────────
BG        = "#f9fafb"
C_BORDER  = "#d1d5db"
C_BODY    = "#ffffff"
C_TEXT    = "#111827"     # all field text – plain black
C_DIV     = "#e5e7eb"     # field divider
C_LINE    = "#9ca3af"     # arrow colour
C_LTEXT   = "#6b7280"     # connector label

H_FRAN,  T_FRAN   = "#dbeafe", "#1e40af"
H_TEAM,  T_TEAM   = "#e0e7ff", "#3730a3"
H_PLAYER,T_PLAYER = "#fee2e2", "#991b1b"
H_STAT,  T_STAT   = "#dcfce7", "#166534"
H_AWARD, T_AWARD  = "#fef9c3", "#854d0e"
H_POST,  T_POST   = "#f3e8ff", "#6b21a8"

# ── Tables (col, row, name, hfill, htxt, [field rows]) ───────────────────────
TABLES = [
    # row 0 – teams cluster
    (0,0,"TeamsFranchises",H_FRAN,  T_FRAN,
     ["franchID (PK)","franchName","active"]),
    (1,0,"Teams",          H_TEAM,  T_TEAM,
     ["teamID, yearID (PK)","franchID (FK)","lgID, divID, name","W / L / G / Rank","ERA, park, attendance…"]),
    (2,0,"TeamsHalf",      H_TEAM,  T_TEAM,
     ["teamID (FK)","yearID, Half","divID, DivWin","W / L / Rank"]),
    (3,0,"SeriesPost",     H_POST,  T_POST,
     ["yearID, round","teamIDwinner (FK)","teamIDloser (FK)","wins / losses / ties"]),

    # row 1 – batting / pitching
    (0,1,"Batting",        H_STAT,  T_STAT,
     ["playerID (FK)","yearID, stint","teamID (FK), lgID","AB / H / HR / RBI","BB / SO / SB…"]),
    (1,1,"BattingPost",    H_STAT,  T_STAT,
     ["playerID (FK)","yearID, round","teamID (FK)","AB / H / HR / RBI"]),
    (3,1,"Pitching",       H_STAT,  T_STAT,
     ["playerID (FK)","yearID, stint","teamID (FK)","W / L / ERA / SO","SV / CG / BFP…"]),
    (4,1,"PitchingPost",   H_STAT,  T_STAT,
     ["playerID (FK)","yearID, round","teamID (FK)","W / L / ERA / SO"]),

    # row 2 – fielding / Player (centre) / salaries / allstar
    (0,2,"Fielding",       H_STAT,  T_STAT,
     ["playerID (FK)","yearID, stint","teamID (FK), POS","E / A / PO / DP"]),
    (1,2,"FieldingOF",     H_STAT,  T_STAT,
     ["playerID (FK)","yearID, stint","Glf / Gcf / Grf"]),
    (2,2,"Player",         H_PLAYER,T_PLAYER,
     ["playerID (PK)","nameFirst, nameLast","birthYear, birthCountry","bats, throws","debut, finalGame"]),
    (3,2,"Salaries",       H_STAT,  T_STAT,
     ["playerID (FK)","yearID","teamID (FK), lgID","salary"]),
    (4,2,"AllstarFull",    H_STAT,  T_STAT,
     ["playerID (FK)","yearID","teamID (FK), gameID","GP, startingPos"]),

    # row 3 – recognition / management / awards
    (0,3,"HallOfFame",     H_AWARD, T_AWARD,
     ["playerID (FK)","yearid","inducted","votes / ballots","category"]),
    (1,3,"Managers",       H_TEAM,  T_TEAM,
     ["playerID (FK)","yearID","teamID (FK)","W / L / rank","plyrMgr"]),
    (2,3,"ManagersHalf",   H_TEAM,  T_TEAM,
     ["playerID (FK)","yearID","teamID (FK)","half, W / L"]),
    (3,3,"AwardsPlayers",  H_AWARD, T_AWARD,
     ["playerID (FK)","awardID","yearID, lgID","tie, notes"]),
    (4,3,"AwardSharePlayers",H_AWARD,T_AWARD,
     ["awardID, yearID, lgID","playerID (FK)","pointsWon / pointsMax"]),

    # row 4 – manager award tables (directly under Managers / ManagersHalf)
    (1,4,"AwardsManagers",    H_AWARD,T_AWARD,
     ["playerID (FK)","awardID","yearID, lgID","tie"]),
    (2,4,"AwardShareManagers",H_AWARD,T_AWARD,
     ["awardID, yearID, lgID","playerID (FK)","pointsWon / pointsMax"]),
]

# ── Arrow helper ─────────────────────────────────────────────────────────────
def esc(s):
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

PAD = 13   # min distance from corner along each edge

def pt(col, row, side, t=0.5):
    """Point on a box edge; t in [0,1] (0=top/left, 1=bottom/right corner)."""
    x, y = bx(col), by(row)
    span_x = BOX_W - 2 * PAD
    span_y = BOX_H - 2 * PAD
    if side == "top":    return x + PAD + t * span_x,  y
    if side == "bottom": return x + PAD + t * span_x,  y + BOX_H
    if side == "left":   return x,         y + PAD + t * span_y
    if side == "right":  return x + BOX_W, y + PAD + t * span_y

ATTR = f'stroke="{C_LINE}" stroke-width="1.25" fill="none" marker-end="url(#arr)"'

# ── Build SVG ─────────────────────────────────────────────────────────────────
out_lines = []
def w(s): out_lines.append(s)

w(f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
  f'style="background:{BG}; font-family: Arial, Helvetica, sans-serif;">')

w(f'''  <defs>
    <marker id="arr" markerWidth="7" markerHeight="7" refX="6.5" refY="3.5" orient="auto">
      <path d="M0,0.5 L0,6.5 L7,3.5 z" fill="{C_LINE}"/>
    </marker>
  </defs>''')

# Title
w(f'  <text x="{CANVAS_W//2}" y="26" fill="#111827" font-size="13.5" font-weight="bold" '
  f'text-anchor="middle">Lahman Baseball Database — Original Data Model (20 tables)</text>')

# ═══════════════════════════════════════════════════════════════════════════════
# CONNECTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def line(x1,y1,x2,y2):
    w(f'  <line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" {ATTR}/>')

def labeled_line(x1,y1,x2,y2,lbl):
    line(x1,y1,x2,y2)
    mx,my = (x1+x2)/2, (y1+y2)/2
    tw = len(lbl)*5.0
    w(f'  <rect x="{mx-tw/2-3:.1f}" y="{my-8:.1f}" width="{tw+6:.1f}" height="13" '
      f'rx="2" fill="{BG}" stroke="{C_DIV}" stroke-width="0.7"/>')
    w(f'  <text x="{mx:.1f}" y="{my+2:.1f}" fill="{C_LTEXT}" font-size="8" '
      f'text-anchor="middle">{esc(lbl)}</text>')

# ── Row-0 cluster ─────────────────────────────────────────────────────────────
# TeamsFranchises → Teams  (right → left, horizontal)
labeled_line(*pt(0,0,"right",0.5), *pt(1,0,"left",0.5), "franchID")

# Teams → TeamsHalf  (right → left, horizontal)
labeled_line(*pt(1,0,"right",0.5), *pt(2,0,"left",0.5), "teamID, yearID")

# Teams → SeriesPost: route ABOVE row-0 (avoids TeamsHalf body)
# exit Teams top-right corner area, travel above boxes, enter SeriesPost top-left
yt = by(0) - 10   # 10px above row 0
x1t, _ = pt(1,0,"top",0.88)
x2t, _ = pt(3,0,"top",0.12)
w(f'  <polyline points="{x1t:.1f},{by(0):.1f} {x1t:.1f},{yt:.1f} {x2t:.1f},{yt:.1f} {x2t:.1f},{by(0):.1f}" '
  f'stroke="{C_LINE}" stroke-width="1.25" fill="none" marker-end="url(#arr)"/>')
mx_s, my_s = (x1t+x2t)/2, yt
tw_s = len("teamID")*5.0
w(f'  <rect x="{mx_s-tw_s/2-3:.1f}" y="{my_s-8:.1f}" width="{tw_s+6:.1f}" height="13" '
  f'rx="2" fill="{BG}" stroke="{C_DIV}" stroke-width="0.7"/>')
w(f'  <text x="{mx_s:.1f}" y="{my_s+2:.1f}" fill="{C_LTEXT}" font-size="8" '
  f'text-anchor="middle">teamID</text>')

# ── Player (2,2) → everything – explicit distributed exit points ──────────────
#
# Top edge (row 1 tables – 4 connections, spread left→right)
line(*pt(2,2,"top",0.10), *pt(0,1,"bottom",0.85))   # → Batting
line(*pt(2,2,"top",0.30), *pt(1,1,"bottom",0.72))   # → BattingPost
line(*pt(2,2,"top",0.70), *pt(3,1,"bottom",0.28))   # → Pitching
line(*pt(2,2,"top",0.90), *pt(4,1,"bottom",0.15))   # → PitchingPost

# Left edge (row 2, cols 0-1 – 2 connections)
line(*pt(2,2,"left",0.32), *pt(1,2,"right",0.50))   # → FieldingOF
line(*pt(2,2,"left",0.68), *pt(0,2,"right",0.50))   # → Fielding

# Right edge (row 2, cols 3-4 – 2 connections)
line(*pt(2,2,"right",0.32), *pt(3,2,"left",0.50))   # → Salaries
line(*pt(2,2,"right",0.68), *pt(4,2,"left",0.50))   # → AllstarFull

# Bottom edge (row 3 tables – 5 connections, spread left→right)
line(*pt(2,2,"bottom",0.08), *pt(0,3,"top",0.50))   # → HallOfFame
line(*pt(2,2,"bottom",0.25), *pt(1,3,"top",0.65))   # → Managers
line(*pt(2,2,"bottom",0.42), *pt(2,3,"top",0.50))   # → ManagersHalf
line(*pt(2,2,"bottom",0.68), *pt(3,3,"top",0.35))   # → AwardsPlayers
line(*pt(2,2,"bottom",0.85), *pt(4,3,"top",0.50))   # → AwardSharePlayers

# ── Row-4 award tables – routed from Managers / ManagersHalf (directly below) ─
line(*pt(1,3,"bottom",0.50), *pt(1,4,"top",0.50))   # Managers → AwardsManagers
line(*pt(2,3,"bottom",0.50), *pt(2,4,"top",0.50))   # ManagersHalf → AwardShareManagers

# ═══════════════════════════════════════════════════════════════════════════════
# BOXES (drawn on top of lines)
# ═══════════════════════════════════════════════════════════════════════════════
HEADER_H = 22
FIELD_H  = 14

for col, row, name, hfill, htxt, fields in TABLES:
    x, y = bx(col), by(row)

    # shadow
    w(f'  <rect x="{x+2}" y="{y+2}" width="{BOX_W}" height="{BOX_H}" rx="5" fill="#00000010"/>')
    # body
    w(f'  <rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" '
      f'rx="5" fill="{C_BODY}" stroke="{C_BORDER}" stroke-width="1.1"/>')
    # header fill
    w(f'  <rect x="{x}" y="{y}" width="{BOX_W}" height="{HEADER_H}" rx="5" fill="{hfill}"/>')
    w(f'  <rect x="{x}" y="{y+HEADER_H-5}" width="{BOX_W}" height="5" fill="{hfill}"/>')
    w(f'  <line x1="{x}" y1="{y+HEADER_H}" x2="{x+BOX_W}" y2="{y+HEADER_H}" '
      f'stroke="{C_BORDER}" stroke-width="1"/>')
    # table name
    w(f'  <text x="{x+BOX_W//2}" y="{y+15}" fill="{htxt}" '
      f'font-size="10.5" font-weight="bold" text-anchor="middle">{esc(name)}</text>')
    # fields
    for i, field in enumerate(fields):
        fy = y + HEADER_H + 2 + i * FIELD_H
        if i > 0:
            w(f'  <line x1="{x+7}" y1="{fy-1}" x2="{x+BOX_W-7}" y2="{fy-1}" '
              f'stroke="{C_DIV}" stroke-width="0.5"/>')
        bold = "bold" if ("(PK)" in field or "(FK)" in field) else "normal"
        w(f'  <text x="{x+8}" y="{fy+10}" fill="{C_TEXT}" '
          f'font-size="9" font-weight="{bold}">{esc(field)}</text>')

w('</svg>')

# ── Write ─────────────────────────────────────────────────────────────────────
out = Path(__file__).parent / "images" / "data_model.svg"
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(out_lines), encoding="utf-8")
print(f"Saved → {out}")

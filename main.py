#!/usr/bin/env python3
"""One-picture front page for Thursday 19 November 2026.

Draws a 1024x1024 newspaper page carrying forty stories: a lead summit
story with a dotted world map beside it, three featured cards, a nine-card
grid, and twenty-seven one-line briefs.  Lettering comes from real typefaces
that were rendered ahead of time into grayscale glyph bitmaps (see
tools/build_glyphs.py); this program only stamps scaled copies of those
bitmaps, paints flat editorial illustrations with simple shapes, and writes
a PNG using nothing beyond the standard library.  Every run produces the
exact same bytes.
"""

import base64
import json
import math
import os
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glyphs import FACES, RENDER_PX  # noqa: E402

PAGE_W = 1024
PAGE_H = 1024
MARGIN = 30
CONTENT_W = PAGE_W - 2 * MARGIN

PAPER = (248, 244, 233)
NAVY = (17, 43, 88)
NAVY_SOFT = (38, 68, 120)
RED = (198, 28, 38)
GREY = (104, 104, 104)
HAIR = (198, 192, 176)
GOLD = (214, 162, 34)
WHITE = (255, 255, 255)
INK = (30, 30, 30)


# --------------------------------------------------------------------------
# Raster sheet: a plain RGB byte buffer with a small set of paint tools.
# --------------------------------------------------------------------------

class Sheet:
    def __init__(self, width, height, colour):
        self.w = width
        self.h = height
        self.px = bytearray(bytes(colour) * (width * height))
        self.clip = (0, 0, width, height)

    def set_clip(self, x0, y0, x1, y1):
        self.clip = (max(0, int(x0)), max(0, int(y0)),
                     min(self.w, int(x1)), min(self.h, int(y1)))

    def clear_clip(self):
        self.clip = (0, 0, self.w, self.h)

    def put(self, x, y, colour):
        cx0, cy0, cx1, cy1 = self.clip
        if cx0 <= x < cx1 and cy0 <= y < cy1:
            i = (y * self.w + x) * 3
            self.px[i], self.px[i + 1], self.px[i + 2] = colour

    def blend(self, x, y, colour, alpha):
        """Alpha 0..255; used when stamping glyph ink."""
        if alpha <= 0:
            return
        cx0, cy0, cx1, cy1 = self.clip
        if cx0 <= x < cx1 and cy0 <= y < cy1:
            i = (y * self.w + x) * 3
            if alpha >= 255:
                self.px[i], self.px[i + 1], self.px[i + 2] = colour
            else:
                keep = 255 - alpha
                self.px[i] = (colour[0] * alpha + self.px[i] * keep) // 255
                self.px[i + 1] = (colour[1] * alpha + self.px[i + 1] * keep) // 255
                self.px[i + 2] = (colour[2] * alpha + self.px[i + 2] * keep) // 255

    def rect(self, x, y, w, h, colour):
        x, y, w, h = int(x), int(y), int(w), int(h)
        cx0, cy0, cx1, cy1 = self.clip
        x0, y0 = max(x, cx0), max(y, cy0)
        x1, y1 = min(x + w, cx1), min(y + h, cy1)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(colour) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def vgrad(self, x, y, w, h, top, bottom):
        for row in range(int(h)):
            t = row / max(1, int(h) - 1)
            c = tuple(int(top[k] + (bottom[k] - top[k]) * t) for k in range(3))
            self.rect(x, int(y) + row, w, 1, c)

    def hgrad(self, x, y, w, h, left, right):
        for col in range(int(w)):
            t = col / max(1, int(w) - 1)
            c = tuple(int(left[k] + (right[k] - left[k]) * t) for k in range(3))
            self.rect(int(x) + col, y, 1, h, c)

    def line(self, x0, y0, x1, y1, colour, thick=1):
        steps = max(abs(int(x1) - int(x0)), abs(int(y1) - int(y0)), 1)
        r = thick // 2
        for s in range(steps + 1):
            t = s / steps
            cx = int(round(x0 + (x1 - x0) * t))
            cy = int(round(y0 + (y1 - y0) * t))
            if thick <= 1:
                self.put(cx, cy, colour)
            else:
                self.rect(cx - r, cy - r, thick, thick, colour)

    def disc(self, cx, cy, r, colour):
        cx, cy, r = int(cx), int(cy), int(r)
        for yy in range(cy - r, cy + r + 1):
            dy = yy - cy
            span = int(math.sqrt(max(0, r * r - dy * dy)))
            self.rect(cx - span, yy, 2 * span + 1, 1, colour)

    def ring(self, cx, cy, r, colour, thick=1):
        steps = max(24, int(r * 6))
        for s in range(steps + 1):
            a = 2 * math.pi * s / steps
            for t in range(thick):
                rr = r - t
                self.put(int(round(cx + rr * math.cos(a))),
                         int(round(cy + rr * math.sin(a))), colour)

    def arc(self, cx, cy, r, a0, a1, colour, thick=1):
        steps = max(12, int(abs(a1 - a0) * max(1, int(r))))
        for s in range(steps + 1):
            a = a0 + (a1 - a0) * s / steps
            for t in range(thick):
                rr = r - t
                self.put(int(round(cx + rr * math.cos(a))),
                         int(round(cy + rr * math.sin(a))), colour)

    def poly(self, points, colour):
        pts = [(float(px), float(py)) for px, py in points]
        ys = [p[1] for p in pts]
        y_lo, y_hi = int(math.floor(min(ys))), int(math.ceil(max(ys)))
        n = len(pts)
        for yy in range(y_lo, y_hi + 1):
            hits = []
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if y0 == y1:
                    continue
                if (y0 <= yy < y1) or (y1 <= yy < y0):
                    hits.append(x0 + (yy - y0) * (x1 - x0) / (y1 - y0))
            hits.sort()
            for k in range(0, len(hits) - 1, 2):
                self.rect(int(round(hits[k])), yy,
                          int(round(hits[k + 1])) - int(round(hits[k])) + 1, 1, colour)

    def star(self, cx, cy, r, colour, points=5):
        pts = []
        for i in range(points * 2):
            rr = r if i % 2 == 0 else r * 0.45
            a = -math.pi / 2 + i * math.pi / points
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        self.poly(pts, colour)


# --------------------------------------------------------------------------
# Typefaces: decode the baked glyph tables and stamp scaled ink.
# --------------------------------------------------------------------------

class Typeface:
    def __init__(self, blob):
        data = json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
        self.ascent = data["ascent"]
        self.glyphs = {}
        for ch, rec in data["glyphs"].items():
            adv64, w, h, xo, yo, b64 = rec
            self.glyphs[ch] = (adv64, w, h, xo, yo,
                               base64.b64decode(b64) if b64 else b"")
        self.cache = {}

    def advance(self, ch, size):
        rec = self.glyphs.get(ch) or self.glyphs["?"]
        return rec[0] / 64.0 * size / RENDER_PX

    def text_width(self, text, size):
        return sum(self.advance(ch, size) for ch in text)

    def scaled(self, ch, size):
        """Area-averaged copy of one glyph bitmap at the wanted size."""
        key = (ch, round(size, 2))
        if key in self.cache:
            return self.cache[key]
        adv64, w, h, xo, yo, raw = self.glyphs.get(ch) or self.glyphs["?"]
        scale = size / RENDER_PX
        adv = adv64 / 64.0 * scale
        if w == 0 or h == 0:
            out = (0, 0, b"", adv, 0.0, 0.0)
            self.cache[key] = out
            return out
        dw = max(1, int(round(w * scale)))
        dh = max(1, int(round(h * scale)))
        buf = bytearray(dw * dh)
        for dy in range(dh):
            sy0 = dy / scale
            sy1 = (dy + 1) / scale
            iy0, iy1 = int(math.floor(sy0)), min(h, int(math.ceil(sy1)))
            for dx in range(dw):
                sx0 = dx / scale
                sx1 = (dx + 1) / scale
                ix0, ix1 = int(math.floor(sx0)), min(w, int(math.ceil(sx1)))
                total = 0.0
                weight = 0.0
                for iy in range(iy0, iy1):
                    wy = min(sy1, iy + 1) - max(sy0, iy)
                    if wy <= 0:
                        continue
                    base = iy * w
                    for ix in range(ix0, ix1):
                        wx = min(sx1, ix + 1) - max(sx0, ix)
                        if wx <= 0:
                            continue
                        total += raw[base + ix] * wx * wy
                        weight += wx * wy
                buf[dy * dw + dx] = int(total / weight) if weight else 0
        out = (dw, dh, bytes(buf), adv, xo * scale, yo * scale)
        self.cache[key] = out
        return out

    def stamp(self, sheet, text, x, baseline, size, colour):
        scale = size / RENDER_PX
        top = baseline - self.ascent * scale
        pen = float(x)
        for ch in text:
            dw, dh, buf, adv, xo, yo = self.scaled(ch, size)
            if dw and dh:
                gx = int(round(pen + xo))
                gy = int(round(top + yo))
                for yy in range(dh):
                    base = yy * dw
                    for xx in range(dw):
                        v = buf[base + xx]
                        if v:
                            sheet.blend(gx + xx, gy + yy, colour, v)
            pen += adv
        return pen

    def wrap(self, text, size, max_width, max_lines):
        words = text.split()
        lines = []
        current = ""
        for word in words:
            trial = (current + " " + word).strip()
            if self.text_width(trial, size) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
                if len(lines) == max_lines:
                    break
        if current and len(lines) < max_lines:
            lines.append(current)
        return lines


BLACK = Typeface(FACES["black"])
BOLD = Typeface(FACES["bold"])
REGULAR = Typeface(FACES["regular"])


def fit_size(face, text, start, max_width, floor=8.0):
    size = float(start)
    while size > floor and face.text_width(text, size) > max_width:
        size -= 0.5
    return size


def stamp_lines(sheet, face, lines, x, baseline, size, colour, leading):
    y = baseline
    for line in lines:
        face.stamp(sheet, line, x, y, size, colour)
        y += leading
    return y


# --------------------------------------------------------------------------
# PNG output (filter 0 rows, fixed compression level: byte-identical runs).
# --------------------------------------------------------------------------

def png_bytes(sheet):
    raw = bytearray()
    stride = sheet.w * 3
    for y in range(sheet.h):
        raw.append(0)
        raw += sheet.px[y * stride:(y + 1) * stride]

    def chunk(kind, payload):
        body = kind + payload
        return (struct.pack(">I", len(payload)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", sheet.w, sheet.h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def output_path():
    env_dir = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if env_dir:
        return Path(env_dir) / "entry.png"
    if Path("/output").is_dir():
        return Path("/output/entry.png")
    return Path(__file__).resolve().parent / "entry.png"


# --------------------------------------------------------------------------
# Story content.
# --------------------------------------------------------------------------

LEAD = ("CHINA", "Trump, Xi and Putin meet in Shenzhen",
        "First three-way summit of the nuclear powers opens the APEC "
        "meeting, with arms control and trade on the table")

FEATURED = [
    ("UKRAINE", "Crimea bridge hit again as blasts rock span",
     "New video shows explosions before part collapses", "bridge"),
    ("UNITED STATES", "Anthropic prices IPO at $83 a share",
     "Claude maker's debut is the year's biggest listing", "ipo"),
    ("MYANMAR", "ICJ rules on Rohingya genocide case",
     "Court decides if 2017 army campaign was genocide", "icj"),
]

GRID = [
    ("NETHERLANDS", "Van Gogh sells for record $190.4M",
     "Top price after Nazi-row sale", "vangogh"),
    ("INDIA", "Cyclone Akvan bears down on India",
     "Storm surge feared as coast braces", "cyclone"),
    ("WORLDWIDE", "GTA VI unlocks at midnight in NZ",
     "Gamers enter Vice City as rollout begins", "gta"),
    ("UNITED KINGDOM", "Bayesian report blames high winds",
     "Superyacht had flaw no one spotted", "yacht"),
    ("SPAIN", "Italy face Ukraine in BJK Cup semis",
     "Seville hosts the last-four showdown", "tennis"),
    ("AUSTRALIA", "Nine new data centres planned",
     "Power and water fears grow in regions", "datacentre"),
    ("SPACE", "NASA: Swift fell over Indonesia",
     "Burst telescope ends 21-year mission", "satellite"),
    ("MIDDLE EAST", "Israel troops pass Gaza Yellow Line",
     "Advance crosses ceasefire boundary", "yellowline"),
    ("MARKETS", "Dollar hits 19-month high, euro slips",
     "Greenback climbs as euro slides", "dollar"),
]

BRIEFS = [
    (14, "Carney-Trump talks end flat", "flag"),
    (15, "India, Japan hold 2+2 talks", "flag"),
    (16, "McDonald's workers win case", "check"),
    (17, "UK, Ireland meet in Dublin", "flag"),
    (18, "Prabowo at ASEAN in Manila", "flag"),
    (19, "Commonhold bill to MPs", "house"),
    (20, "UNHCR halts Malaysia intake", "cross"),
    (21, "Fiji declares drought crisis", "drop"),
    (22, "Trump raised Nvidia ex-boss", "gear"),
    (23, "Pew: India faith map shifts", "star"),
    (24, "Islam top faith by 2035: Pew", "star"),
    (25, "William, Kate meet Modi", "flag"),
    (26, "Australia jobless 5-yr high", "coin"),
    (27, "Musk calls spree 'foolish'", "bolt"),
    (28, "Pastor guilty in Haiti case", "check"),
    (29, "Fed split on bigger hike", "coin"),
    (30, "Moldova teens try vote app", "check"),
    (31, "Spain strikes over housing", "house"),
    (32, "Pakistan 325 v Sri Lanka", "ball"),
    (33, "India-NZ Tests in Wellington", "ball"),
    (34, "Rickelton ton boosts SA", "ball"),
    (35, "HCMC Police stun Buriram 1-0", "ball"),
    (36, "Eagles hunt 57lb baboons", "star"),
    (37, "Dental floss tests sugar", "check"),
    (38, "AI teaches tractor balance", "gear"),
    (39, "Mofokeng brace saves Bafana", "ball"),
    (40, "Reliance eyes Starlink rival", "plane"),
]

LAND = {
    2: [(3, 8), (30, 33), (38, 52)],
    3: [(2, 14), (28, 35), (36, 56)],
    4: [(2, 16), (28, 34), (35, 57)],
    5: [(3, 16), (29, 33), (36, 56)],
    6: [(4, 15), (29, 34), (38, 54)],
    7: [(5, 14), (30, 36), (40, 52)],
    8: [(6, 13), (30, 37), (42, 50)],
    9: [(7, 12), (30, 37), (44, 49)],
    10: [(8, 12), (30, 36), (45, 48)],
    11: [(9, 13), (30, 36), (46, 48)],
    12: [(10, 15), (31, 35), (47, 49)],
    13: [(10, 16), (31, 35)],
    14: [(11, 16), (32, 34)],
    15: [(11, 16), (32, 34), (50, 56)],
    16: [(12, 15), (33, 34), (50, 57)],
    17: [(12, 15), (50, 57)],
    18: [(12, 14), (51, 56)],
    19: [(13, 14)],
    20: [(13, 13), (58, 59)],
}

RED_DOTS = [(50, 7), (37, 5), (8, 6), (46, 9), (30, 4), (44, 9), (9, 4),
            (54, 6), (29, 4), (28, 5), (29, 6), (49, 12), (54, 17), (58, 20),
            (48, 11), (60, 14), (38, 8), (33, 12), (34, 5), (42, 8), (44, 11)]


# --------------------------------------------------------------------------
# Illustrations: flat shapes and gradients, one painter per story kind.
# --------------------------------------------------------------------------

def paint_flag_china(s, x, y, w, h):
    s.rect(x, y, w, h, (222, 32, 36))
    s.star(x + w * 0.22, y + h * 0.30, max(2, h * 0.16), (255, 222, 0))
    for dx, dy in ((0.42, 0.16), (0.48, 0.34), (0.48, 0.54), (0.42, 0.72)):
        s.disc(x + w * dx, y + h * dy, max(1, h * 0.06), (255, 222, 0))


def paint_flag_usa(s, x, y, w, h):
    stripe = h / 7.0
    for i in range(7):
        s.rect(x, y + i * stripe, w, stripe + 1,
               (198, 32, 44) if i % 2 == 0 else WHITE)
    s.rect(x, y, w * 0.42, stripe * 4, (28, 48, 110))
    for r in range(3):
        for c in range(4):
            s.disc(x + 3 + c * (w * 0.42 - 5) / 3, y + 3 + r * (stripe * 4 - 5) / 2,
                   1, WHITE)


def paint_flag_russia(s, x, y, w, h):
    third = h / 3.0
    s.rect(x, y, w, third + 1, WHITE)
    s.rect(x, y + third, w, third + 1, (32, 84, 170))
    s.rect(x, y + 2 * third, w, third + 1, (212, 32, 44))


def paint_summit(s, x, y, w, h):
    s.vgrad(x, y, w, h, (233, 239, 246), (212, 226, 240))
    # skyline towers behind the table
    towers = [(0.03, 0.30, 0.07), (0.13, 0.42, 0.08), (0.24, 0.34, 0.07),
              (0.36, 0.46, 0.08), (0.48, 0.36, 0.07), (0.59, 0.44, 0.08),
              (0.71, 0.33, 0.07), (0.82, 0.41, 0.08), (0.92, 0.30, 0.06)]
    base = y + h * 0.72
    for fx, fh, fw in towers:
        tx, tw, th = x + w * fx, w * fw, h * fh
        s.rect(tx, base - th, tw, th, (148, 168, 196))
        for wy in range(int(base - th) + 4, int(base) - 3, 7):
            for wx in range(int(tx) + 3, int(tx + tw) - 3, 6):
                s.rect(wx, wy, 2, 3, (196, 212, 232))
    # flags on poles above the three seats
    flag_w, flag_h = w * 0.13, h * 0.30
    painters = [paint_flag_china, paint_flag_usa, paint_flag_russia]
    seats = [0.24, 0.50, 0.76]
    for fx, painter in zip(seats, painters):
        px = x + w * fx
        s.rect(px - 1, y + h * 0.10, 2, h * 0.42, (90, 90, 90))
        painter(s, px + 1, y + h * 0.10, flag_w, flag_h)
    # long conference table
    table_y = y + h * 0.66
    s.rect(x + w * 0.06, table_y, w * 0.88, h * 0.07, (120, 78, 44))
    s.rect(x + w * 0.06, table_y + h * 0.07, w * 0.88, 2, (92, 58, 30))
    for fx in (0.10, 0.48, 0.86):
        s.rect(x + w * fx, table_y + h * 0.09, 4, h * 0.10, (92, 58, 30))
    # three seated figures: head, suit, tie
    suits = [(44, 52, 84), (36, 36, 44), (60, 64, 78)]
    for fx, suit in zip(seats, suits):
        cx = x + w * fx + flag_w * 0.28
        head_r = max(5, h * 0.095)
        s.disc(cx, table_y - h * 0.17, head_r, (238, 200, 168))
        s.rect(cx - head_r * 1.7, table_y - h * 0.17 + head_r * 0.6,
               head_r * 3.4, h * 0.14, suit)
        s.poly([(cx - 2, table_y - h * 0.13), (cx + 2, table_y - h * 0.13),
                (cx, table_y - h * 0.05)], RED)
    # water band along the bottom
    s.rect(x, y + h * 0.86, w, h * 0.14, (86, 140, 196))
    for i in range(9):
        wx = x + (i * 67 % max(10, int(w) - 30))
        s.rect(wx, y + h * (0.89 + 0.04 * (i % 2)), 22, 2, (150, 190, 226))


def paint_bridge(s, x, y, w, h):
    s.vgrad(x, y, w, h * 0.55, (214, 230, 244), (190, 214, 236))
    s.rect(x, y + h * 0.55, w, h * 0.45, (66, 118, 186))
    for i in range(7):
        s.rect(x + (i * 53 % max(10, int(w) - 26)), y + h * (0.66 + 0.09 * (i % 3)),
               18, 2, (130, 170, 220))
    deck_y = y + h * 0.48
    s.rect(x, deck_y, w, max(3, h * 0.07), (110, 116, 124))
    for fx in (0.16, 0.50, 0.84):
        tx = x + w * fx
        s.rect(tx - 2, y + h * 0.14, 4, h * 0.38, (90, 96, 106))
        s.line(tx, y + h * 0.16, tx - w * 0.15, deck_y, (90, 96, 106), 1)
        s.line(tx, y + h * 0.16, tx + w * 0.15, deck_y, (90, 96, 106), 1)
    # explosion burst mid-span with smoke
    bx, by = x + w * 0.50, deck_y - h * 0.04
    for dx, dy, r in ((-14, -12, 7), (12, -14, 8), (0, -20, 9), (-6, -26, 6)):
        s.disc(bx + dx * w / 300, by + dy * h / 60, max(3, r * h / 60), (150, 150, 150))
    s.star(bx, by, h * 0.30, (244, 120, 24), points=9)
    s.star(bx, by, h * 0.19, (252, 190, 40), points=9)
    s.disc(bx, by, max(2, h * 0.07), (255, 240, 180))


def paint_bank(s, x, y, w, h, body, roof):
    s.poly([(x, y + h * 0.22), (x + w / 2, y), (x + w, y + h * 0.22)], roof)
    s.rect(x, y + h * 0.22, w, h * 0.08, roof)
    cols = 5
    for i in range(cols):
        cx = x + w * (0.08 + 0.84 * i / (cols - 1)) - w * 0.035
        s.rect(cx, y + h * 0.34, w * 0.07, h * 0.48, body)
    s.rect(x - 2, y + h * 0.82, w + 4, h * 0.07, roof)
    s.rect(x - 4, y + h * 0.89, w + 8, h * 0.06, roof)


def paint_ipo(s, x, y, w, h):
    s.vgrad(x, y, w, h, (14, 30, 64), (22, 48, 96))
    paint_bank(s, x + w * 0.05, y + h * 0.18, w * 0.34, h * 0.66,
               (222, 228, 238), (170, 182, 204))
    pts = [(x + w * 0.46, y + h * 0.74), (x + w * 0.58, y + h * 0.60),
           (x + w * 0.68, y + h * 0.66), (x + w * 0.80, y + h * 0.42),
           (x + w * 0.93, y + h * 0.24)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        s.line(x0, y0, x1, y1, (52, 210, 110), max(2, int(h * 0.05)))
    ex, ey = pts[-1]
    s.poly([(ex, ey), (ex - w * 0.06, ey + h * 0.02), (ex - w * 0.015, ey + h * 0.14)],
           (52, 210, 110))
    for fx, fy in ((0.52, 0.82), (0.66, 0.80), (0.78, 0.58)):
        cx, cy, r = x + w * fx, y + h * fy, max(5, h * 0.13)
        s.disc(cx, cy, r, GOLD)
        s.ring(cx, cy, r, (176, 128, 20), 1)
        BOLD.stamp(s, "$", cx - BOLD.text_width("$", r * 1.15) / 2,
                   cy + r * 0.42, r * 1.15, (120, 84, 8))


def paint_icj(s, x, y, w, h):
    s.vgrad(x, y, w, h, (238, 240, 244), (222, 228, 238))
    paint_bank(s, x + w * 0.05, y + h * 0.16, w * 0.40, h * 0.70,
               (240, 242, 246), (96, 108, 130))
    # scales of justice
    cx = x + w * 0.72
    top = y + h * 0.16
    s.rect(cx - 1, top, 3, h * 0.58, GOLD)
    s.disc(cx, top, max(2, h * 0.05), GOLD)
    s.line(cx - w * 0.17, top + h * 0.08, cx + w * 0.17, top + h * 0.08, GOLD, 2)
    s.rect(cx - w * 0.05, top + h * 0.58, w * 0.10, h * 0.06, GOLD)
    for side in (-1, 1):
        px = cx + side * w * 0.17
        py = top + h * 0.08
        s.line(px, py, px - w * 0.05, py + h * 0.22, GOLD, 1)
        s.line(px, py, px + w * 0.05, py + h * 0.22, GOLD, 1)
        s.arc(px, py + h * 0.22, w * 0.055, 0, math.pi, GOLD, 2)
        s.line(px - w * 0.055, py + h * 0.22, px + w * 0.055, py + h * 0.22, GOLD, 2)


def paint_vangogh(s, x, y, w, h):
    s.vgrad(x, y, w, h, (18, 30, 96), (30, 58, 150))
    for fx, fy, r in ((0.16, 0.36, 0.20), (0.42, 0.30, 0.15), (0.66, 0.42, 0.18)):
        s.arc(x + w * fx, y + h * fy, h * r, 0.3, 4.6, (110, 150, 220), 2)
        s.arc(x + w * fx, y + h * fy, h * r * 0.62, 1.2, 5.6, (150, 180, 235), 1)
    for fx, fy in ((0.10, 0.20), (0.30, 0.62), (0.54, 0.18), (0.80, 0.26), (0.92, 0.60)):
        s.star(x + w * fx, y + h * fy, max(3, h * 0.09), (252, 214, 70), points=5)
    mx, my, mr = x + w * 0.88, y + h * 0.30, max(5, h * 0.16)
    s.disc(mx, my, mr, (252, 224, 120))
    s.disc(mx + mr * 0.45, my - mr * 0.25, mr * 0.82, (24, 40, 110))
    # gold price tag
    tx, ty, tw, th = x + w * 0.58, y + h * 0.52, w * 0.38, h * 0.44
    s.poly([(tx, ty + th / 2), (tx + tw * 0.16, ty), (tx + tw, ty),
            (tx + tw, ty + th), (tx + tw * 0.16, ty + th)], (240, 196, 70))
    s.disc(tx + tw * 0.13, ty + th / 2, max(2, th * 0.10), (30, 58, 150))
    label = "$190M"
    size = fit_size(BOLD, label, th * 0.62, tw * 0.72)
    BOLD.stamp(s, label, tx + tw * 0.22, ty + th * 0.72, size, (60, 44, 4))


def paint_cyclone(s, x, y, w, h):
    s.vgrad(x, y, w, h * 0.68, (52, 64, 84), (86, 102, 128))
    for i in range(16):
        rx = x + (i * 37 % max(10, int(w) - 14))
        ry = y + (i * 13 % max(8, int(h * 0.5)))
        s.line(rx, ry, rx - 5, ry + h * 0.22, (190, 206, 226), 1)
    cx, cy = x + w * 0.38, y + h * 0.36
    for r, a0 in ((0.30, 0.4), (0.22, 1.4), (0.14, 2.4), (0.07, 3.4)):
        s.arc(cx, cy, h * r, a0, a0 + 4.4, (226, 234, 244), 2)
    s.disc(cx, cy, max(2, h * 0.045), (226, 234, 244))
    wave_y = y + h * 0.68
    pts = [(x, y + h)]
    steps = 14
    for i in range(steps + 1):
        pts.append((x + w * i / steps, wave_y + math.sin(i * 1.7) * h * 0.07))
    pts.append((x + w, y + h))
    s.poly(pts, (30, 74, 128))
    for i in range(steps + 1):
        wx = x + w * i / steps
        wy = wave_y + math.sin(i * 1.7) * h * 0.07
        s.rect(wx - 4, wy - 1, 8, 2, (200, 224, 246))


def paint_gta(s, x, y, w, h):
    s.vgrad(x, y, w, h, (250, 110, 170), (252, 170, 80))
    s.disc(x + w * 0.82, y + h * 0.52, h * 0.30, (255, 222, 110))
    s.rect(x, y + h * 0.78, w, h * 0.22, (52, 30, 70))
    for fx, lean in ((0.10, -0.06), (0.22, 0.05), (0.94, -0.04)):
        bx = x + w * fx
        top_x = bx + w * lean
        top_y = y + h * 0.30
        s.line(bx, y + h * 0.80, top_x, top_y, (40, 24, 56), max(2, int(h * 0.05)))
        for ang in (-2.6, -1.9, -1.2, -0.5, 0.2):
            ex = top_x + math.cos(ang) * w * 0.09
            ey = top_y + math.sin(ang) * h * 0.30 + h * 0.10
            s.line(top_x, top_y, ex, ey, (40, 24, 56), max(1, int(h * 0.035)))
    label = "VICE CITY"
    size = fit_size(BLACK, label, h * 0.34, w * 0.52)
    lx = x + w * 0.30
    ly = y + h * 0.62
    BLACK.stamp(s, label, lx + 2, ly + 2, size, (255, 80, 190))
    BLACK.stamp(s, label, lx, ly, size, (255, 246, 255))


def paint_yacht(s, x, y, w, h):
    s.vgrad(x, y, w, h * 0.58, (226, 238, 248), (206, 226, 242))
    s.rect(x, y + h * 0.58, w, h * 0.42, (70, 126, 190))
    hull_y = y + h * 0.60
    s.poly([(x + w * 0.10, hull_y), (x + w * 0.92, hull_y),
            (x + w * 0.84, hull_y + h * 0.20), (x + w * 0.18, hull_y + h * 0.20)],
           WHITE)
    s.rect(x + w * 0.30, hull_y - h * 0.16, w * 0.42, h * 0.16, WHITE)
    s.rect(x + w * 0.38, hull_y - h * 0.27, w * 0.28, h * 0.11, WHITE)
    s.line(x + w * 0.52, hull_y - h * 0.27, x + w * 0.52, hull_y - h * 0.42,
           (120, 130, 140), 1)
    for i in range(6):
        s.disc(x + w * (0.24 + i * 0.10), hull_y + h * 0.08, max(1, h * 0.035),
               (90, 120, 160))
    for i in range(4):
        s.rect(x + w * (0.34 + i * 0.09), hull_y - h * 0.12, w * 0.05, h * 0.07,
               (120, 160, 205))
    for i in range(6):
        s.rect(x + (i * 47 % max(10, int(w) - 24)), y + h * (0.84 + 0.05 * (i % 2)),
               16, 2, (160, 198, 232))


def paint_tennis(s, x, y, w, h):
    s.rect(x, y, w, h, (58, 138, 72))
    inset = max(3, h * 0.10)
    s.rect(x + inset, y + inset, w - 2 * inset, 2, WHITE)
    s.rect(x + inset, y + h - inset - 2, w - 2 * inset, 2, WHITE)
    s.rect(x + inset, y + inset, 2, h - 2 * inset, WHITE)
    s.rect(x + w - inset - 2, y + inset, 2, h - 2 * inset, WHITE)
    s.rect(x + w * 0.30, y + inset, 2, h - 2 * inset, WHITE)
    s.rect(x + w * 0.70, y + inset, 2, h - 2 * inset, WHITE)
    s.line(x + w * 0.30, y + h / 2, x + w * 0.70, y + h / 2, WHITE, 2)
    s.rect(x + w * 0.495, y + inset * 0.4, max(3, w * 0.012), h - inset * 0.8,
           (30, 60, 40))
    s.rect(x + w * 0.495, y + inset * 0.4, max(3, w * 0.012), 2, WHITE)
    bx, by = x + w * 0.78, y + h * 0.38
    for t in range(9):
        s.disc(bx - t * w * 0.028, by + math.sin(t * 0.5) * h * 0.05 - t * 0.6,
               max(1, h * 0.05 - t * 0.4), (220, 235, 120))
    s.disc(bx, by, max(3, h * 0.11), (214, 232, 60))
    s.arc(bx, by, max(2, h * 0.08), -0.8, 1.4, WHITE, 1)


def paint_datacentre(s, x, y, w, h):
    s.vgrad(x, y, w, h, (16, 22, 38), (24, 34, 56))
    s.rect(x, y + h * 0.84, w, h * 0.16, (30, 42, 66))
    racks = 6
    lights = [(80, 230, 140), (250, 190, 60), (90, 200, 250), (250, 120, 90)]
    for i in range(racks):
        rx = x + w * (0.04 + i * 0.16)
        rw = w * 0.115
        ry, rh = y + h * 0.12, h * 0.70
        s.rect(rx, ry, rw, rh, (38, 50, 76))
        s.rect(rx, ry, rw, 2, (70, 92, 130))
        for row in range(5):
            ly = ry + rh * (0.12 + row * 0.17)
            s.rect(rx + 2, ly, rw - 4, 1, (58, 74, 104))
            for dot in range(3):
                s.disc(rx + rw * (0.22 + dot * 0.28), ly + rh * 0.07,
                       max(1, h * 0.028), lights[(i + row + dot) % 4])


def paint_satellite(s, x, y, w, h):
    s.vgrad(x, y, w, h, (6, 8, 20), (14, 20, 40))
    for i in range(26):
        sx = x + (i * 61 % max(10, int(w) - 6)) + 3
        sy = y + (i * 29 % max(8, int(h) - 6)) + 3
        s.disc(sx, sy, 1, (210, 222, 245))
    cx, cy = x + w * 0.50, y + h * 0.48
    s.arc(cx, cy + h * 0.30, w * 0.42, math.pi * 1.12, math.pi * 1.88,
          (120, 150, 200), 1)
    panel_w, panel_h = w * 0.30, h * 0.30
    for side in (-1, 1):
        px = cx + side * w * 0.10 + (0 if side > 0 else -panel_w)
        py = cy - panel_h / 2
        s.rect(px, py, panel_w, panel_h, (44, 92, 180))
        for gx in range(1, 4):
            s.rect(px + panel_w * gx / 4, py, 1, panel_h, (110, 160, 225))
        s.rect(px, py + panel_h / 2, panel_w, 1, (110, 160, 225))
    s.rect(cx - w * 0.075, cy - h * 0.20, w * 0.15, h * 0.40, (216, 176, 80))
    s.rect(cx - w * 0.075, cy - h * 0.20, w * 0.15, 2, (160, 124, 44))
    s.disc(cx, cy + h * 0.30, max(3, h * 0.09), (226, 232, 240))
    s.line(cx, cy + h * 0.20, cx, cy + h * 0.24, (226, 232, 240), 2)


def paint_yellowline(s, x, y, w, h):
    s.vgrad(x, y, w, h * 0.62, (240, 228, 196), (232, 214, 170))
    s.rect(x, y + h * 0.62, w, h * 0.38, (214, 190, 140))
    fence_y = y + h * 0.30
    posts = 9
    for i in range(posts):
        px = x + w * (0.04 + 0.92 * i / (posts - 1))
        s.rect(px - 1, fence_y, 3, h * 0.42, (96, 84, 64))
    for fy in (0.08, 0.20, 0.32):
        s.line(x + w * 0.04, fence_y + h * fy, x + w * 0.96, fence_y + h * fy,
               (120, 108, 84), 1)
    s.rect(x, y + h * 0.52, w, max(3, h * 0.09), (250, 198, 24))
    s.rect(x, y + h * 0.52, w, 1, (210, 160, 10))


def paint_dollar(s, x, y, w, h):
    s.vgrad(x, y, w, h, (24, 110, 62), (34, 140, 80))
    cx, cy, r = x + w * 0.20, y + h * 0.52, h * 0.34
    s.disc(cx, cy, r, (244, 200, 64))
    s.ring(cx, cy, r, (190, 146, 28), 2)
    s.ring(cx, cy, r * 0.78, (214, 168, 40), 1)
    BOLD.stamp(s, "$", cx - BOLD.text_width("$", r * 1.25) / 2, cy + r * 0.45,
               r * 1.25, (140, 104, 10))
    ax0, ay0 = x + w * 0.42, y + h * 0.66
    ax1, ay1 = x + w * 0.70, y + h * 0.34
    s.line(ax0, ay0, ax1, ay1, (120, 240, 160), max(3, int(h * 0.10)))
    s.poly([(ax1, ay1), (ax1 - w * 0.10, ay1 + h * 0.02),
            (ax1 - w * 0.02, ay1 + h * 0.20)], (120, 240, 160))
    ex, ey, er = x + w * 0.88, y + h * 0.56, h * 0.24
    s.disc(ex, ey, er, (220, 226, 232))
    s.ring(ex, ey, er, (160, 170, 182), 2)
    BOLD.stamp(s, "€", ex - BOLD.text_width("€", er * 1.2) / 2, ey + er * 0.42,
               er * 1.2, (90, 100, 116))


PAINTERS = {
    "summit": paint_summit, "bridge": paint_bridge, "ipo": paint_ipo,
    "icj": paint_icj, "vangogh": paint_vangogh, "cyclone": paint_cyclone,
    "gta": paint_gta, "yacht": paint_yacht, "tennis": paint_tennis,
    "datacentre": paint_datacentre, "satellite": paint_satellite,
    "yellowline": paint_yellowline, "dollar": paint_dollar,
}


def paint_band(s, kind, x, y, w, h):
    s.set_clip(x, y, x + w, y + h)
    PAINTERS[kind](s, x, y, w, h)
    s.clear_clip()
    s.rect(x, y, w, 1, HAIR)
    s.rect(x, y + h - 1, w, 1, HAIR)
    s.rect(x, y, 1, h, HAIR)
    s.rect(x + w - 1, y, 1, h, HAIR)


# --------------------------------------------------------------------------
# Small parts: number badges, the dotted map, brief icons, story cards.
# --------------------------------------------------------------------------

def number_badge(s, number, cx, cy, r):
    s.disc(cx, cy, r, RED)
    label = str(number)
    size = r * 1.15 if len(label) == 1 else r * 0.92
    BOLD.stamp(s, label, cx - BOLD.text_width(label, size) / 2,
               cy + size * 0.36, size, WHITE)


def region_line(s, number, region, x, baseline, badge_r, size):
    number_badge(s, number, x + badge_r, baseline - size * 0.36, badge_r)
    BOLD.stamp(s, region, x + badge_r * 2 + 5, baseline, size, RED)


def paint_map(s, x, y, w, h):
    cols, rows = 62, 19
    sx = w / cols
    sy = h / rows
    for gy, spans in LAND.items():
        for a, b in spans:
            for gx in range(a, b + 1):
                s.disc(x + (gx + 0.5) * sx, y + (gy - 2 + 0.5) * sy, 1.6,
                       (176, 168, 150))
    for gx, gy in RED_DOTS:
        s.disc(x + (gx + 0.5) * sx, y + (gy - 2 + 0.5) * sy, 2.7, RED)


def brief_icon(s, kind, cx, cy, size):
    half = size / 2
    if kind == "flag":
        s.line(cx - half * 0.6, cy - half, cx - half * 0.6, cy + half, NAVY, 1)
        s.poly([(cx - half * 0.6, cy - half), (cx + half, cy - half * 0.55),
                (cx - half * 0.6, cy - half * 0.1)], RED)
    elif kind == "check":
        s.line(cx - half, cy, cx - half * 0.25, cy + half * 0.7, RED, 2)
        s.line(cx - half * 0.25, cy + half * 0.7, cx + half, cy - half * 0.7, RED, 2)
    elif kind == "house":
        s.poly([(cx - half, cy - half * 0.1), (cx, cy - half),
                (cx + half, cy - half * 0.1)], NAVY)
        s.rect(cx - half * 0.7, cy - half * 0.1, half * 1.4, half * 1.05, NAVY)
        s.rect(cx - half * 0.22, cy + half * 0.35, half * 0.44, half * 0.6, PAPER)
    elif kind == "cross":
        s.rect(cx - half * 0.28, cy - half, half * 0.56, size, RED)
        s.rect(cx - half, cy - half * 0.28, size, half * 0.56, RED)
    elif kind == "drop":
        s.poly([(cx, cy - half), (cx + half * 0.75, cy + half * 0.25),
                (cx - half * 0.75, cy + half * 0.25)], (52, 120, 200))
        s.disc(cx, cy + half * 0.25, half * 0.72, (52, 120, 200))
    elif kind == "gear":
        for k in range(6):
            a = k * math.pi / 3
            s.line(cx, cy, cx + half * math.cos(a), cy + half * math.sin(a), NAVY, 2)
        s.disc(cx, cy, half * 0.55, NAVY)
        s.disc(cx, cy, half * 0.24, PAPER)
    elif kind == "star":
        s.star(cx, cy, half, GOLD)
    elif kind == "coin":
        s.disc(cx, cy, half * 0.9, GOLD)
        s.ring(cx, cy, half * 0.9, (176, 128, 20), 1)
        BOLD.stamp(s, "$", cx - BOLD.text_width("$", size * 0.8) / 2,
                   cy + size * 0.29, size * 0.8, (120, 84, 8))
    elif kind == "bolt":
        s.poly([(cx + half * 0.25, cy - half), (cx - half * 0.55, cy + half * 0.15),
                (cx - half * 0.05, cy + half * 0.15), (cx - half * 0.25, cy + half),
                (cx + half * 0.55, cy - half * 0.15), (cx + half * 0.05, cy - half * 0.15)],
               GOLD)
    elif kind == "ball":
        s.disc(cx, cy, half * 0.9, WHITE)
        s.ring(cx, cy, half * 0.9, NAVY, 1)
        s.arc(cx, cy, half * 0.55, -0.9, 0.9, NAVY, 1)
        s.arc(cx, cy, half * 0.55, math.pi - 0.9, math.pi + 0.9, NAVY, 1)
    elif kind == "plane":
        s.poly([(cx + half, cy), (cx - half * 0.2, cy - half * 0.25),
                (cx - half * 0.55, cy - half * 0.85), (cx - half * 0.75, cy - half * 0.2),
                (cx - half, cy + half * 0.15), (cx - half * 0.55, cy + half * 0.35),
                (cx - half * 0.35, cy + half * 0.85), (cx - half * 0.05, cy + half * 0.3)],
               NAVY)


def story_card(s, number, story, x, y, w, band_h, head_size, deck_size,
               region_size, badge_r, deck_lines=2):
    region, headline, deck, kind = story
    paint_band(s, kind, x, y, w, band_h)
    base = y + band_h + region_size + 7
    region_line(s, number, region, x, base, badge_r, region_size)
    head_lines = BOLD.wrap(headline, head_size, w, 2)
    y_after = stamp_lines(s, BOLD, head_lines, x, base + head_size + 6,
                          head_size, NAVY, head_size * 1.12)
    deck_wrapped = REGULAR.wrap(deck, deck_size, w, deck_lines)
    stamp_lines(s, REGULAR, deck_wrapped, x, y_after + deck_size * 0.55,
                deck_size, GREY, deck_size * 1.18)


# --------------------------------------------------------------------------
# Page assembly.
# --------------------------------------------------------------------------

def build_page():
    s = Sheet(PAGE_W, PAGE_H, PAPER)

    # kicker line
    BOLD.stamp(s, "THE WORLD'S NEWS IN ONE PICTURE", MARGIN, 34, 17, RED)
    right = "40 STORIES · FIVE CONTINENTS"
    BOLD.stamp(s, right, MARGIN + CONTENT_W - BOLD.text_width(right, 14.5),
               34, 14.5, GREY)

    # masthead title and rule
    title = "THURSDAY 19 NOVEMBER 2026"
    tsize = fit_size(BLACK, title, 66, CONTENT_W)
    BLACK.stamp(s, title, MARGIN, 96, tsize, NAVY)
    s.rect(MARGIN, 106, CONTENT_W, 6, NAVY)

    # lead story (left) and map (right)
    lead_w = 592
    map_x = MARGIN + lead_w + 16
    map_w = CONTENT_W - lead_w - 16
    paint_band(s, "summit", MARGIN, 122, lead_w, 88)
    region, headline, deck = LEAD
    region_line(s, 1, region, MARGIN, 230, 9, 14)
    head_lines = BOLD.wrap(headline, 34, lead_w, 2)
    after = stamp_lines(s, BOLD, head_lines, MARGIN, 260, 34, NAVY, 35)
    deck_lines = REGULAR.wrap(deck, 14.5, lead_w, 2)
    stamp_lines(s, REGULAR, deck_lines, MARGIN, after + 2, 14.5, GREY, 16.5)

    paint_map(s, map_x, 126, map_w, 128)
    cap1 = "WHERE IT HAPPENED"
    BOLD.stamp(s, cap1, map_x + (map_w - BOLD.text_width(cap1, 14)) / 2,
               284, 14, NAVY)
    cap2 = "RED DOTS MARK THE BIG STORIES"
    REGULAR.stamp(s, cap2, map_x + (map_w - REGULAR.text_width(cap2, 10.5)) / 2,
                  300, 10.5, GREY)

    s.rect(MARGIN, 356, CONTENT_W, 1, HAIR)

    # featured row: stories 2-4
    col_w = 314
    gap = (CONTENT_W - 3 * col_w) // 2
    for i, story in enumerate(FEATURED):
        story_card(s, i + 2, story, MARGIN + i * (col_w + gap), 364, col_w,
                   band_h=50, head_size=20, deck_size=12, region_size=12,
                   badge_r=8)

    s.rect(MARGIN, 518, CONTENT_W, 1, HAIR)

    # grid: stories 5-13 in three rows
    for row in range(3):
        for col in range(3):
            idx = row * 3 + col
            story_card(s, idx + 5, GRID[idx], MARGIN + col * (col_w + gap),
                       526 + row * 100, col_w, band_h=28, head_size=16.5,
                       deck_size=10.5, region_size=11, badge_r=7)

    # briefs header and four columns of one-liners
    BOLD.stamp(s, "ALSO ON 19 NOVEMBER", MARGIN, 838, 17, RED)
    brief_col_w = CONTENT_W // 4
    for i, (number, text, icon) in enumerate(BRIEFS):
        col, row = i % 4, i // 4
        bx = MARGIN + col * brief_col_w
        by = 856 + row * 15
        label = str(number)
        BOLD.stamp(s, label, bx, by, 11, RED)
        brief_icon(s, icon, bx + 24, by - 4, 10)
        size = fit_size(REGULAR, text, 11, brief_col_w - 36, floor=9.0)
        REGULAR.stamp(s, text, bx + 33, by, size, NAVY)

    # footer lines
    finale = "AND FINALLY: BABOON-HUNTING EAGLES AND A BALANCING TRACTOR"
    fsize = fit_size(BOLD, finale, 18, CONTENT_W)
    BOLD.stamp(s, finale, MARGIN, 968, fsize, NAVY)
    sources = ("Every story reported on Thursday 19 November 2026 · Sources: "
               "Reuters, BBC, NYT, AP, The Guardian, NDTV, AFP, AAP, Global Voices")
    ssize = fit_size(REGULAR, sources, 11, CONTENT_W)
    REGULAR.stamp(s, sources, MARGIN, 986, ssize, GREY)
    return s


def main():
    page = build_page()
    target = output_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png_bytes(page))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()

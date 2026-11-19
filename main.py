#!/usr/bin/env python3
"""The World in One Picture - Thursday 19 November 2026.

A pure-stdlib newspaper front page generator for make.fun's
"Sum up 19 November's world news in one image" bounty.

- 40 stories genuinely reported on 19 November 2026.
- Type is set in real fonts (Archivo Black + Liberation Sans, OFL),
  pre-rendered to grayscale glyph bitmaps in glyphs.py and stamped
  here with area-averaged downscaling. No Pillow at run time.
- Illustrations are drawn with vector primitives (gradients with
  ordered dithering, polygons, circles) - no image assets.
- Output: a 1024x1024 PNG written to $MAKEFUN_OUTPUT_DIR/entry.png
  (or /output/entry.png on the grader, or next to this script).
- Deterministic: same bytes on every run.
"""

import base64
import os
import pickle
import struct
import zlib
from pathlib import Path

from glyphs import BLOB

PAGE_W = 1024
PAGE_H = 1024
MARGIN = 24
CONTENT_W = PAGE_W - 2 * MARGIN

# ---------------------------------------------------------------- palette
PAPER = (250, 246, 235)
NAVY = (15, 41, 83)
NAVY_DARK = (10, 28, 58)
RED = (196, 30, 42)
RED_DARK = (172, 22, 34)
GREY = (96, 92, 84)
HAIRLINE = (205, 194, 170)
CARD_BG = (253, 250, 243)
GOLD = (212, 160, 32)
SKY_TOP = (120, 178, 224)
SKY_BOT = (214, 236, 248)
SEA = (38, 102, 156)
SEA_DARK = (24, 74, 120)

BAYER4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def mix(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.px = bytearray(bytes(bg) * (w * h))
        self.clip = (0, 0, w, h)

    def set_clip(self, x, y, w, h):
        self.clip = (max(0, x), max(0, y), min(self.w, x + w), min(self.h, y + h))

    def clear_clip(self):
        self.clip = (0, 0, self.w, self.h)

    def set_px(self, x, y, color, alpha=255):
        cx0, cy0, cx1, cy1 = self.clip
        if cx0 <= x < cx1 and cy0 <= y < cy1:
            i = (y * self.w + x) * 3
            if alpha >= 255:
                self.px[i:i + 3] = bytes(color)
            elif alpha > 0:
                a = alpha / 255.0
                self.px[i] = int(self.px[i] * (1 - a) + color[0] * a)
                self.px[i + 1] = int(self.px[i + 1] * (1 - a) + color[1] * a)
                self.px[i + 2] = int(self.px[i + 2] * (1 - a) + color[2] * a)

    def fill_rect(self, x, y, w, h, color):
        cx0, cy0, cx1, cy1 = self.clip
        x0, y0 = max(cx0, x), max(cy0, y)
        x1, y1 = min(cx1, x + w), min(cy1, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def gradient_rect(self, x, y, w, h, top, bottom, dither=True):
        for yy in range(h):
            t = yy / max(1, h - 1)
            base = mix(top, bottom, t)
            for xx in range(w):
                if dither:
                    d = (BAYER4[yy % 4][xx % 4] - 7.5) / 255.0 * 18
                    col = tuple(max(0, min(255, int(round(c + d)))) for c in base)
                else:
                    col = base
                self.set_px(x + xx, y + yy, col)

    def hline(self, x, y, w, color, thick=1):
        self.fill_rect(x, y, w, thick, color)

    def vline(self, x, y, h, color, thick=1):
        self.fill_rect(x, y, thick, h, color)

    def line(self, x0, y0, x1, y1, color, width=1):
        dx, dy = x1 - x0, y1 - y0
        steps = max(abs(dx), abs(dy), 1)
        r = width // 2
        for s in range(steps + 1):
            cx = x0 + dx * s // steps
            cy = y0 + dy * s // steps
            for oy in range(-r, width - r):
                for ox in range(-r, width - r):
                    self.set_px(cx + ox, cy + oy, color)

    def circle(self, cx, cy, r, color, alpha=255):
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    self.set_px(xx, yy, color, alpha)

    def ellipse(self, cx, cy, rx, ry, color, alpha=255):
        if rx <= 0 or ry <= 0:
            return
        for yy in range(cy - ry, cy + ry + 1):
            for xx in range(cx - rx, cx + rx + 1):
                if ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0:
                    self.set_px(xx, yy, color, alpha)

    def ring(self, cx, cy, r, color, width=2):
        for yy in range(cy - r - width, cy + r + width + 1):
            for xx in range(cx - r - width, cx + r + width + 1):
                d = ((xx - cx) ** 2 + (yy - cy) ** 2) ** 0.5
                if r - width / 2 <= d <= r + width / 2:
                    self.set_px(xx, yy, color)

    def polygon(self, pts, color):
        ys = [p[1] for p in pts]
        y0, y1 = max(0, min(ys)), min(self.h - 1, max(ys))
        n = len(pts)
        for yy in range(y0, y1 + 1):
            nodes = []
            for i in range(n):
                x_a, y_a = pts[i]
                x_b, y_b = pts[(i + 1) % n]
                if y_a == y_b:
                    continue
                if (y_a <= yy < y_b) or (y_b <= yy < y_a):
                    nodes.append(x_a + (yy - y_a) * (x_b - x_a) / (y_b - y_a))
            nodes.sort()
            for i in range(0, len(nodes) - 1, 2):
                xa, xb = int(round(nodes[i])), int(round(nodes[i + 1]))
                for xx in range(max(0, xa), min(self.w - 1, xb) + 1):
                    self.set_px(xx, yy, color)

    def star(self, cx, cy, r_out, r_in, color, points=5):
        import math
        pts = []
        for i in range(points * 2):
            r = r_out if i % 2 == 0 else r_in
            ang = -math.pi / 2 + i * math.pi / points
            pts.append((int(round(cx + r * math.cos(ang))),
                        int(round(cy + r * math.sin(ang)))))
        self.polygon(pts, color)

    def burst(self, cx, cy, r, color, spikes=12):
        import math
        pts = []
        for i in range(spikes * 2):
            rr = r if i % 2 == 0 else int(r * 0.45)
            ang = i * math.pi / spikes
            pts.append((int(round(cx + rr * math.cos(ang))),
                        int(round(cy + rr * math.sin(ang)))))
        self.polygon(pts, color)

    def frame(self, x, y, w, h, color, thick=1):
        self.hline(x, y, w, color, thick)
        self.hline(x, y + h - thick, w, color, thick)
        self.vline(x, y, h, color, thick)
        self.vline(x + w - thick, y, h, color, thick)


# ---------------------------------------------------------------- text
FONTS = pickle.loads(zlib.decompress(base64.b64decode(BLOB)))
_GLYPH_CACHE = {}


def _resample(bitmap, w, h, scale):
    """Area-average downscale of a grayscale bitmap by `scale` (<1)."""
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    out = bytearray(nw * nh)
    inv = 1.0 / scale
    for oy in range(nh):
        sy0 = oy * inv
        sy1 = min(h, (oy + 1) * inv)
        iy0, iy1 = int(sy0), max(int(sy0) + 1, int(sy1 + 0.999))
        for ox in range(nw):
            sx0 = ox * inv
            sx1 = min(w, (ox + 1) * inv)
            ix0, ix1 = int(sx0), max(int(sx0) + 1, int(sx1 + 0.999))
            total = 0.0
            area = 0.0
            for sy in range(iy0, min(iy1, h)):
                wy = min(sy + 1, sy1) - max(sy, sy0)
                if wy <= 0:
                    continue
                row = sy * w
                for sx in range(ix0, min(ix1, w)):
                    wx = min(sx + 1, sx1) - max(sx, sx0)
                    if wx <= 0:
                        continue
                    total += bitmap[row + sx] * wx * wy
                    area += wx * wy
            out[oy * nw + ox] = int(total / area) if area > 0 else 0
    return bytes(out), nw, nh


def glyph(fontname, ch, cap_target):
    key = (fontname, ch, round(cap_target, 1))
    if key in _GLYPH_CACHE:
        return _GLYPH_CACHE[key]
    font = FONTS[fontname]
    scale = cap_target / font["cap"]
    g = font["glyphs"].get(ch) or font["glyphs"]["?"]
    advance, w, h, xoff, yoff, bitmap = g
    if w == 0 or h == 0:
        result = (b"", 0, 0, advance * scale, 0.0, 0.0)
    else:
        small, nw, nh = _resample(bitmap, w, h, scale)
        result = (small, nw, nh, advance * scale, xoff * scale, yoff * scale)
    _GLYPH_CACHE[key] = result
    return result


def text_width(fontname, s, cap):
    return sum(glyph(fontname, ch, cap)[3] for ch in s)


def draw_text(cv, fontname, s, x, baseline, cap, color):
    cx = float(x)
    for ch in s:
        bitmap, w, h, advance, xoff, yoff = glyph(fontname, ch, cap)
        if w and h:
            gx = int(round(cx + xoff))
            gy = int(round(baseline - yoff))
            for yy in range(h):
                row = yy * w
                for xx in range(w):
                    v = bitmap[row + xx]
                    if v:
                        cv.set_px(gx + xx, gy + yy, color, v)
        cx += advance
    return cx


def wrap(fontname, s, cap, max_w):
    lines = []
    current = ""
    for word in s.split(" "):
        trial = word if not current else current + " " + word
        if text_width(fontname, trial, cap) <= max_w or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_block(cv, fontname, s, x, y_top, cap, color, max_w, line_gap=1.22,
               max_lines=99):
    lines = wrap(fontname, s, cap, max_w)[:max_lines]
    baseline = y_top + cap
    for line_text in lines:
        draw_text(cv, fontname, line_text, x, baseline, cap, color)
        baseline += cap * line_gap
    return int(round(baseline - cap * line_gap))  # bottom of last cap box


def fit_cap(fontname, s, max_w, cap_hi=140.0):
    lo, hi = 4.0, cap_hi
    for _ in range(24):
        mid = (lo + hi) / 2
        if text_width(fontname, s, mid) <= max_w:
            lo = mid
        else:
            hi = mid
    return lo


def badge(cv, x, y, number, region):
    """Red number disc + region label; returns x after the label."""
    cv.circle(x + 8, y + 8, 8, RED)
    num = str(number)
    cap = 9.5
    w = text_width("bold", num, cap)
    draw_text(cv, "bold", num, x + 8 - w / 2, y + 8 + cap * 0.36, cap, (255, 255, 255))
    draw_text(cv, "bold", region, x + 21, y + 8 + 11 * 0.36, 11, RED_DARK)
    return x + 21 + text_width("bold", region, 11)


# ---------------------------------------------------------------- scenes
def sky(cv, x, y, w, h, top=SKY_TOP, bottom=SKY_BOT):
    cv.gradient_rect(x, y, w, h, top, bottom)


def cloud(cv, cx, cy, r, color=(255, 255, 255)):
    cv.ellipse(cx, cy, r, max(2, r // 3), color)
    cv.ellipse(cx - r // 2, cy + 1, r // 2, max(2, r // 4), color)
    cv.ellipse(cx + r // 2, cy + 1, r // 2, max(2, r // 4), color)


def flag_china(cv, x, y, w, h):
    cv.fill_rect(x, y, w, h, (222, 41, 16))
    cv.star(x + w // 5, y + h // 3, max(3, h // 4), max(2, h // 7), (255, 222, 0))
    for dx, dy in ((0.42, 0.14), (0.47, 0.32), (0.47, 0.52), (0.42, 0.7)):
        cv.star(x + int(w * dx), y + int(h * dy), max(2, h // 8), max(1, h // 14),
                (255, 222, 0))


def flag_usa(cv, x, y, w, h):
    stripe_h = max(1, h // 7)
    for i in range(7):
        col = (179, 34, 52) if i % 2 == 0 else (255, 255, 255)
        cv.fill_rect(x, y + i * stripe_h, w, stripe_h if i < 6 else h - 6 * stripe_h, col)
    cw, ch = int(w * 0.42), stripe_h * 4
    cv.fill_rect(x, y, cw, ch, (60, 59, 110))
    for r in range(4):
        for c in range(5):
            cv.circle(x + 3 + c * max(3, cw // 5), y + 3 + r * max(3, ch // 4), 1,
                      (255, 255, 255))


def flag_russia(cv, x, y, w, h):
    third = h // 3
    cv.fill_rect(x, y, w, third, (255, 255, 255))
    cv.fill_rect(x, y + third, w, third, (0, 57, 166))
    cv.fill_rect(x, y + 2 * third, w, h - 2 * third, (213, 43, 30))


def suited_figure(cv, cx, base_y, height, suit=(38, 44, 66), skin=(232, 190, 150),
                  hair=(70, 60, 50)):
    head_r = max(3, height // 7)
    cv.circle(cx, base_y - height + head_r, head_r, skin)
    cv.ellipse(cx, base_y - height + head_r - head_r // 2, head_r, head_r // 2, hair)
    shoulder = base_y - height + head_r * 2
    cv.polygon([(cx - height // 4, base_y), (cx - height // 5, shoulder),
                (cx + height // 5, shoulder), (cx + height // 4, base_y)], suit)
    cv.polygon([(cx - 3, shoulder), (cx + 3, shoulder), (cx, shoulder + height // 4)],
               (245, 245, 245))
    cv.polygon([(cx - 1, shoulder + 2), (cx + 1, shoulder + 2),
                (cx, shoulder + height // 5)], RED)


def scene_summit(cv, x, y, w, h):
    sky(cv, x, y, w, h, (250, 214, 160), (252, 240, 214))
    # Shenzhen skyline
    base = y + h - 34
    towers = [(0.02, 0.42), (0.10, 0.62), (0.18, 0.5), (0.30, 0.72), (0.42, 0.55),
              (0.55, 0.8), (0.66, 0.6), (0.76, 0.7), (0.86, 0.52), (0.94, 0.64)]
    for fx, fh in towers:
        tw = max(8, w // 22)
        tx = x + int(w * fx)
        th = int((h - 40) * fh)
        cv.fill_rect(tx, base - th, tw, th, (120, 140, 170))
        for wy in range(base - th + 4, base - 4, 7):
            for wx in range(tx + 2, tx + tw - 2, 5):
                cv.set_px(wx, wy, (230, 240, 250))
    cv.fill_rect(x, base, w, 4, (150, 130, 105))
    # three leaders first (the table will cover their lower bodies)
    table_y = y + h - 24
    spots = [(0.24, flag_china), (0.50, flag_usa), (0.76, flag_russia)]
    for fx, _flag_fn in spots:
        cx = x + int(w * fx)
        suited_figure(cv, cx, y + h - 6, 84)
    # long table over the figures' laps
    cv.fill_rect(x + 30, table_y, w - 60, 10, (96, 64, 40))
    cv.fill_rect(x + 30, table_y, w - 60, 3, (140, 100, 62))
    cv.fill_rect(x + 44, table_y + 10, 8, h - (table_y - y) - 10, (80, 54, 34))
    cv.fill_rect(x + w - 52, table_y + 10, 8, h - (table_y - y) - 10, (80, 54, 34))
    # flags above each leader, plus microphone and name plate
    for fx, flag_fn in spots:
        cx = x + int(w * fx)
        pole_top = y + 5
        cv.vline(cx - 26, pole_top, table_y - pole_top - 36, (90, 90, 90), 2)
        flag_fn(cv, cx - 24, pole_top, 46, 30)
        cv.line(cx + 12, table_y, cx + 6, table_y - 12, (40, 40, 40), 2)
        cv.circle(cx + 6, table_y - 13, 3, (40, 40, 40))
        cv.fill_rect(cx - 16, table_y - 7, 32, 7, (255, 252, 240))


def scene_bridge(cv, x, y, w, h):
    sky(cv, x, y, w, h, (96, 150, 205), (196, 226, 244))
    sea_y = y + h - 22
    cv.gradient_rect(x, sea_y, w, h - (sea_y - y), SEA, SEA_DARK)
    for i in range(6):
        wy = sea_y + 4 + i * 3
        for wx in range(x + (i * 13) % 30, x + w - 12, 34):
            cv.hline(wx, wy, 10, (150, 200, 235), 1)
    deck_y = y + 26
    cv.fill_rect(x + 6, deck_y, w - 12, 5, (90, 96, 104))
    cv.fill_rect(x + 6, deck_y, w - 12, 2, (150, 156, 164))
    for fx in (0.12, 0.38, 0.64, 0.88):
        px = x + int(w * fx)
        cv.fill_rect(px, deck_y + 5, 7, sea_y - deck_y - 5, (110, 116, 124))
    # broken span
    cv.polygon([(x + int(w * 0.52), deck_y + 4), (x + int(w * 0.66), deck_y + 4),
                (x + int(w * 0.60), deck_y + 20)], (70, 76, 84))
    # explosion
    ex, ey = x + int(w * 0.58), deck_y - 6
    cv.burst(ex, ey, 26, (244, 120, 32), 12)
    cv.burst(ex, ey, 17, (250, 178, 40), 10)
    cv.burst(ex, ey, 9, (255, 230, 120), 8)
    cloud(cv, ex - 22, ey - 18, 12, (120, 118, 116))
    cloud(cv, ex + 18, ey - 24, 10, (140, 138, 136))
    cloud(cv, ex + 2, ey - 32, 9, (160, 158, 156))


def scene_ipo(cv, x, y, w, h):
    sky(cv, x, y, w, h, (30, 58, 110), (70, 110, 170))
    # exchange building
    bx, bw = x + 18, int(w * 0.44)
    by = y + h - 14
    cv.polygon([(bx - 4, y + 26), (bx + bw // 2, y + 12), (bx + bw + 4, y + 26)],
               (210, 216, 226))
    cv.fill_rect(bx - 4, y + 26, bw + 8, 5, (190, 198, 210))
    for i in range(5):
        cx = bx + 8 + i * (bw - 12) // 4
        cv.fill_rect(cx, y + 31, 7, by - y - 31, (225, 230, 238))
    cv.fill_rect(bx - 6, by, bw + 12, 5, (170, 178, 192))
    # rising chart
    pts = [(x + int(w * 0.52), y + h - 18), (x + int(w * 0.64), y + h - 30),
           (x + int(w * 0.74), y + h - 26), (x + int(w * 0.86), y + 22),
           (x + int(w * 0.95), y + 14)]
    for i in range(len(pts) - 1):
        cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], (46, 204, 113), 3)
    cv.polygon([(pts[-1][0] + 2, pts[-1][1] - 7), (pts[-1][0] + 11, pts[-1][1] + 2),
                (pts[-1][0] - 3, pts[-1][1] + 4)], (46, 204, 113))
    for px, py in pts[:-1]:
        cv.circle(px, py, 3, (255, 255, 255))
    # coins
    for fx, fy in ((0.58, 0.78), (0.66, 0.84), (0.74, 0.78)):
        cx, cy = x + int(w * fx), y + int(h * fy)
        cv.circle(cx, cy, 8, GOLD)
        cv.circle(cx, cy, 6, (238, 192, 64))
        draw_text(cv, "bold", "$", cx - 2, cy + 4, 9, (150, 105, 10))


def scene_icj(cv, x, y, w, h):
    sky(cv, x, y, w, h, (150, 190, 226), (226, 240, 248))
    bx, bw = x + int(w * 0.14), int(w * 0.52)
    by = y + h - 12
    cv.polygon([(bx - 6, y + 22), (bx + bw // 2, y + 8), (bx + bw + 6, y + 22)],
               (52, 66, 96))
    cv.fill_rect(bx - 6, y + 22, bw + 12, 5, (70, 86, 118))
    for i in range(6):
        cx = bx + 6 + i * (bw - 10) // 5
        cv.fill_rect(cx, y + 27, 6, by - y - 27, (238, 240, 244))
    cv.fill_rect(bx - 8, by, bw + 16, 5, (90, 104, 130))
    cv.fill_rect(bx - 12, by + 5, bw + 24, 4, (110, 122, 146))
    # scales of justice
    sx, sy = x + int(w * 0.84), y + 16
    cv.vline(sx, sy, h - 34, GOLD, 3)
    cv.hline(sx - 26, sy + 4, 52, GOLD, 3)
    cv.circle(sx, sy + 2, 4, GOLD)
    for side in (-1, 1):
        pan_x = sx + side * 26
        cv.line(pan_x, sy + 6, pan_x - 9, sy + 24, GOLD, 1)
        cv.line(pan_x, sy + 6, pan_x + 9, sy + 24, GOLD, 1)
        cv.ellipse(pan_x, sy + 26, 11, 4, GOLD)
    cv.fill_rect(sx - 12, y + h - 16, 24, 4, GOLD)


def scene_vangogh(cv, x, y, w, h):
    cv.gradient_rect(x, y, w, h, (84, 62, 44), (120, 92, 64))
    # framed painting with swirling sky
    fx, fy, fw, fh = x + 22, y + 6, int(w * 0.52), h - 16
    cv.fill_rect(fx - 4, fy - 4, fw + 8, fh + 8, (160, 118, 44))
    cv.gradient_rect(fx, fy, fw, fh, (28, 52, 130), (70, 110, 190))
    for cx, cy, r in ((0.25, 0.35, 9), (0.55, 0.25, 7), (0.78, 0.42, 8), (0.4, 0.6, 6)):
        cv.ring(fx + int(fw * cx), fy + int(fh * cy), r, (250, 220, 110), 2)
        cv.circle(fx + int(fw * cx), fy + int(fh * cy), 2, (255, 240, 170))
    cv.ellipse(fx + fw // 2, fy + fh - 3, fw // 2, 5, (46, 92, 60))
    # cypress silhouette in the painting
    cv.polygon([(fx + fw - 14, fy + fh - 4), (fx + fw - 10, fy + 8),
                (fx + fw - 6, fy + fh - 4)], (24, 60, 44))
    # gavel + price tag
    gx, gy = x + int(w * 0.72), y + h - 14
    cv.line(gx, gy, gx + 24, gy - 20, (170, 120, 66), 5)
    cv.fill_rect(gx + 16, gy - 29, 20, 9, (146, 98, 52))
    cv.ellipse(gx + 8, gy + 3, 18, 3, (110, 76, 42))
    tx, ty = x + int(w * 0.76), y + 5
    cv.polygon([(tx, ty), (tx + 46, ty), (tx + 46, ty + 17), (tx + 8, ty + 17),
                (tx, ty + 8)], (255, 250, 235))
    draw_text(cv, "bold", "$190M", tx + 7, ty + 13, 9.5, RED_DARK)


def scene_cyclone(cv, x, y, w, h):
    sky(cv, x, y, w, h, (70, 96, 130), (150, 176, 200))
    sea_y = y + h - 16
    cv.gradient_rect(x, sea_y, w, h - (sea_y - y), (30, 84, 130), (18, 58, 96))
    for i in range(5):
        wy = sea_y + 3 + i * 3
        for wx in range(x + (i * 17) % 26, x + w - 14, 30):
            cv.hline(wx, wy, 12, (170, 210, 240), 1)
    # spiral storm (offset rings read as a swirl, not a target)
    cx, cy = x + int(w * 0.62), y + int(h * 0.42)
    for r, col, ox, oy in ((26, (210, 218, 226), -5, 2), (20, (190, 200, 212), -3, 1),
                           (14, (225, 232, 240), -1, 0), (8, (200, 212, 224), 0, 0)):
        cv.ring(cx + ox, cy + oy, r, col, 4)
    cv.circle(cx, cy, 4, (240, 246, 252))
    cloud(cv, x + int(w * 0.2), y + 12, 16, (160, 172, 188))
    cloud(cv, x + int(w * 0.88), y + 10, 13, (150, 164, 182))
    # rain streaks
    for i in range(16):
        rx = x + 10 + (i * 37) % (w - 20)
        ry = y + 8 + (i * 23) % (h - 34)
        cv.line(rx, ry, rx - 5, ry + 10, (200, 222, 244), 1)
    # bending palm
    px = x + int(w * 0.14)
    cv.line(px, sea_y + 2, px + 12, y + 18, (110, 80, 48), 4)
    for ang in (-0.9, -0.4, 0.1, 0.6):
        import math
        ex = px + 12 + int(20 * math.cos(ang))
        ey = y + 18 + int(10 * math.sin(ang)) + 6
        cv.line(px + 12, y + 18, ex, ey, (52, 130, 66), 3)


def scene_gta(cv, x, y, w, h):
    cv.gradient_rect(x, y, w, h, (255, 138, 76), (255, 92, 168))
    cv.circle(x + int(w * 0.72), y + int(h * 0.55), 16, (255, 226, 120))
    # skyline silhouette
    base = y + h - 12
    for fx, fh in ((0.04, 0.4), (0.14, 0.62), (0.26, 0.48), (0.38, 0.7), (0.52, 0.55),
                   (0.62, 0.42), (0.82, 0.6), (0.92, 0.45)):
        tw = max(9, w // 18)
        th = int((h - 14) * fh)
        cv.fill_rect(x + int(w * fx), base - th, tw, th, (58, 32, 74))
    cv.fill_rect(x, base, w, 12, (40, 24, 56))
    # palm silhouettes
    for fx in (0.10, 0.88):
        px = x + int(w * fx)
        cv.line(px, base + 8, px + 4, y + 14, (30, 18, 44), 4)
        for dx, dy in ((-16, -2), (-8, -8), (2, -10), (12, -6), (18, 0)):
            cv.line(px + 4, y + 14, px + 4 + dx, y + 14 + dy + 6, (30, 18, 44), 3)
    # neon sign
    draw_text(cv, "black", "VICE CITY", x + int(w * 0.30), y + 20, 13, (140, 240, 255))


def scene_yacht(cv, x, y, w, h):
    sky(cv, x, y, w, h, (74, 92, 118), (148, 168, 192))
    cloud(cv, x + int(w * 0.22), y + 10, 18, (110, 122, 140))
    cloud(cv, x + int(w * 0.72), y + 8, 15, (100, 114, 134))
    sea_y = y + h - 14
    cv.gradient_rect(x, sea_y, w, h - (sea_y - y), (26, 70, 116), (16, 48, 88))
    for i in range(4):
        wy = sea_y + 3 + i * 3
        for wx in range(x + (i * 19) % 24, x + w - 16, 28):
            cv.hline(wx, wy, 13, (160, 204, 238), 1)
    # tilted superyacht
    hx, hy = x + int(w * 0.30), sea_y - 8
    cv.polygon([(hx, hy), (hx + 120, hy - 14), (hx + 104, hy + 6), (hx + 14, hy + 8)],
               (240, 244, 248))
    cv.polygon([(hx + 18, hy - 2), (hx + 40, hy - 16), (hx + 84, hy - 20),
                (hx + 96, hy - 12)], (225, 232, 240))
    for i in range(5):
        cv.fill_rect(hx + 26 + i * 15, hy - 4 - i, 8, 4, (70, 110, 150))
    cv.line(hx + 66, hy - 18, hx + 78, hy - 34, (200, 208, 218), 3)
    # wind streaks
    for i in range(5):
        wy = y + 16 + i * 7
        cv.line(x + int(w * 0.68), wy, x + int(w * 0.68) + 34, wy - 3,
                (230, 240, 250), 2)


def scene_tennis(cv, x, y, w, h):
    cv.gradient_rect(x, y, w, h, (46, 110, 74), (34, 92, 60))
    court_y = y + 8
    cv.fill_rect(x + 14, court_y, w - 28, h - 16, (52, 126, 84))
    cv.frame(x + 14, court_y, w - 28, h - 16, (245, 245, 245), 2)
    cv.vline(x + w // 2, court_y, h - 16, (30, 30, 30), 3)
    cv.hline(x + 14, court_y + (h - 16) // 2, w - 28, (245, 245, 245), 1)
    # ball with trail
    bx, by = x + int(w * 0.68), y + int(h * 0.34)
    for i in range(4):
        cv.circle(bx - 8 - i * 9, by + 3 + i * 3, 3 - i // 2, (200, 230, 90))
    cv.circle(bx, by, 6, (214, 240, 96))
    cv.ring(bx, by, 6, (150, 180, 60), 1)
    # racket
    rx, ry = x + int(w * 0.24), y + int(h * 0.52)
    cv.ellipse(rx, ry, 13, 17, (250, 250, 250))
    cv.ellipse(rx, ry, 10, 14, (52, 126, 84))
    for i in range(-1, 2):
        cv.vline(rx + i * 5, ry - 11, 22, (220, 220, 220), 1)
        cv.hline(rx - 8, ry + i * 6, 16, (220, 220, 220), 1)
    cv.line(rx + 3, ry + 15, rx + 12, ry + 28, (120, 80, 44), 4)


def scene_datacentre(cv, x, y, w, h):
    cv.gradient_rect(x, y, w, h, (24, 34, 58), (40, 58, 92))
    # server racks
    for r in range(4):
        rx = x + 16 + r * ((w - 90) // 4)
        rw = (w - 90) // 4 - 8
        cv.fill_rect(rx, y + 10, rw, h - 22, (16, 24, 42))
        cv.frame(rx, y + 10, rw, h - 22, (90, 120, 170), 1)
        for row in range(5):
            uy = y + 14 + row * ((h - 30) // 5)
            cv.fill_rect(rx + 3, uy, rw - 6, 4, (52, 76, 118))
            cv.circle(rx + rw - 7, uy + 2, 2,
                      (80, 230, 120) if (row + r) % 3 else (255, 190, 70))
    # cooling towers
    tx = x + w - 52
    cv.polygon([(tx, y + h - 12), (tx + 6, y + 22), (tx + 26, y + 22),
                (tx + 32, y + h - 12)], (150, 166, 190))
    cloud(cv, tx + 16, y + 14, 10, (220, 232, 244))
    cv.fill_rect(x, y + h - 10, w, 10, (14, 22, 40))


def scene_satellite(cv, x, y, w, h):
    cv.gradient_rect(x, y, w, h, (8, 12, 34), (26, 40, 84))
    for i in range(22):
        sx = x + (i * 53) % w
        sy = y + (i * 29) % (h - 20)
        cv.set_px(sx, sy, (230, 238, 255))
    # earth curve along the bottom edge
    cv.ellipse(x + w // 2, y + h + 30, w // 2 + 10, 42, (52, 110, 190))
    cv.ellipse(x + w // 2, y + h + 36, w // 2 + 10, 42, (74, 142, 212))
    # falling satellite with flame trail
    sx, sy = x + int(w * 0.60), y + int(h * 0.40)
    for i in range(6):
        cv.circle(sx - 10 - i * 8, sy - 6 - i * 5, 6 - i // 2,
                  mix((255, 160, 60), (200, 60, 30), i / 6))
    cv.fill_rect(sx - 8, sy - 6, 16, 12, (200, 208, 220))
    cv.fill_rect(sx - 30, sy - 4, 20, 8, (70, 110, 190))
    cv.fill_rect(sx + 10, sy - 4, 20, 8, (70, 110, 190))
    cv.line(sx, sy + 6, sx - 6, sy + 16, (180, 190, 205), 2)
    cv.circle(sx - 7, sy + 17, 3, (220, 228, 240))


def scene_yellowline(cv, x, y, w, h):
    cv.gradient_rect(x, y, w, h, (250, 214, 150), (240, 196, 120))
    ground_y = y + h - 16
    cv.fill_rect(x, ground_y, w, 16, (216, 178, 116))
    # yellow painted line across the ground
    cv.polygon([(x + 6, ground_y + 10), (x + w - 6, ground_y + 2),
                (x + w - 6, ground_y + 8), (x + 6, ground_y + 16)], (250, 204, 40))
    # border fence
    fy = y + 16
    for fx in range(x + 10, x + w - 8, 18):
        cv.vline(fx, fy, ground_y - fy, (90, 84, 70), 2)
    cv.hline(x + 8, fy + 2, w - 16, (110, 102, 86), 2)
    cv.hline(x + 8, fy + 12, w - 16, (110, 102, 86), 2)
    # watchtower
    tx = x + int(w * 0.78)
    cv.fill_rect(tx, y + 8, 22, 14, (120, 108, 88))
    cv.polygon([(tx - 3, y + 8), (tx + 11, y + 1), (tx + 25, y + 8)], (96, 84, 66))
    cv.line(tx + 3, y + 22, tx - 2, ground_y, (100, 90, 74), 3)
    cv.line(tx + 19, y + 22, tx + 24, ground_y, (100, 90, 74), 3)
    cv.fill_rect(tx + 4, y + 12, 14, 5, (60, 54, 44))


def scene_dollar(cv, x, y, w, h):
    cv.gradient_rect(x, y, w, h, (20, 70, 52), (34, 110, 78))
    # big dollar coin rising
    cx, cy = x + int(w * 0.34), y + int(h * 0.44)
    cv.circle(cx, cy, 20, GOLD)
    cv.circle(cx, cy, 16, (240, 198, 72))
    draw_text(cv, "black", "$", cx - 6, cy + 9, 22, (150, 105, 10))
    # up arrow
    ax = x + int(w * 0.52)
    cv.line(ax, y + h - 16, ax + 46, y + 16, (120, 240, 160), 4)
    cv.polygon([(ax + 40, y + 10), (ax + 56, y + 18), (ax + 42, y + 26)],
               (120, 240, 160))
    # euro coin slipping down
    ex, ey = x + int(w * 0.84), y + int(h * 0.62)
    cv.circle(ex, ey, 13, (190, 198, 208))
    cv.circle(ex, ey, 10, (214, 220, 228))
    draw_text(cv, "bold", "€", ex - 5, ey + 6, 13, (90, 100, 115))
    cv.line(ex + 16, ey - 12, ex + 24, ey + 6, (240, 120, 110), 3)
    cv.polygon([(ex + 20, ey + 2), (ex + 28, ey + 12), (ex + 18, ey + 12)],
               (240, 120, 110))


PAINTERS = {
    "summit": scene_summit,
    "bridge": scene_bridge,
    "ipo": scene_ipo,
    "icj": scene_icj,
    "vangogh": scene_vangogh,
    "cyclone": scene_cyclone,
    "gta": scene_gta,
    "yacht": scene_yacht,
    "tennis": scene_tennis,
    "datacentre": scene_datacentre,
    "satellite": scene_satellite,
    "yellowline": scene_yellowline,
    "dollar": scene_dollar,
}


# ---------------------------------------------------------------- map
# Coarse dotted world map: land spans per row on a 64x30 grid.
MAP_SPANS = {
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

# Story locations as (col, row) on the map grid.
MAP_DOTS = [
    (50, 7),   # China (Shenzhen)
    (37, 5),   # Ukraine
    (8, 6),    # USA
    (46, 9),   # Myanmar
    (30, 4),   # Netherlands
    (44, 9),   # India
    (9, 4),    # Canada
    (54, 6),   # Japan
    (29, 4),   # UK
    (28, 5),   # Ireland
    (29, 6),   # Spain
    (49, 12),  # Indonesia
    (54, 17),  # Australia
    (58, 20),  # New Zealand
    (48, 11),  # Malaysia
    (60, 14),  # Fiji
    (38, 8),   # Gaza
    (33, 12),  # Chad
    (34, 5),   # Moldova
    (42, 8),   # Pakistan
    (44, 11),  # Sri Lanka
]


def draw_map(cv, x, y, w, h):
    cols, rows = 64, 30
    sx = w / cols
    sy = h / rows
    land = (178, 168, 146)
    for row, spans in MAP_SPANS.items():
        for c0, c1 in spans:
            for col in range(c0, c1 + 1):
                px = int(x + (col + 0.5) * sx)
                py = int(y + (row + 0.5) * sy)
                cv.circle(px, py, 2, land)
    for col, row in MAP_DOTS:
        px = int(x + (col + 0.5) * sx)
        py = int(y + (row + 0.5) * sy)
        cv.circle(px, py, 3, RED)
        cv.circle(px, py, 1, (255, 255, 255))


# ---------------------------------------------------------------- icons
def mini_icon(cv, x, y, kind, color=NAVY):
    if kind == "star":
        cv.star(x + 5, y + 5, 5, 2, color)
    elif kind == "drop":
        cv.ellipse(x + 5, y + 6, 3, 4, color)
        cv.polygon([(x + 5, y), (x + 2, y + 5), (x + 8, y + 5)], color)
    elif kind == "ball":
        cv.circle(x + 5, y + 5, 4, color)
        cv.set_px(x + 4, y + 4, PAPER)
    elif kind == "bolt":
        cv.polygon([(x + 6, y), (x + 2, y + 6), (x + 5, y + 6), (x + 3, y + 10),
                    (x + 8, y + 4), (x + 5, y + 4)], color)
    elif kind == "check":
        cv.line(x + 1, y + 6, x + 4, y + 9, color, 2)
        cv.line(x + 4, y + 9, x + 9, y + 2, color, 2)
    elif kind == "cross":
        cv.line(x + 2, y + 2, x + 8, y + 8, color, 2)
        cv.line(x + 8, y + 2, x + 2, y + 8, color, 2)
    elif kind == "wave":
        for i in range(3):
            cv.hline(x + 1, y + 2 + i * 3, 8, color, 1)
            cv.set_px(x + 1 + i * 3, y + 1 + i * 3, color)
    elif kind == "coin":
        cv.circle(x + 5, y + 5, 4, color)
        cv.circle(x + 5, y + 5, 2, PAPER)
    elif kind == "flag":
        cv.vline(x + 2, y, 10, color, 1)
        cv.polygon([(x + 3, y + 1), (x + 9, y + 3), (x + 3, y + 5)], color)
    elif kind == "house":
        cv.polygon([(x + 1, y + 5), (x + 5, y + 1), (x + 9, y + 5)], color)
        cv.fill_rect(x + 3, y + 5, 4, 4, color)
    elif kind == "plane":
        cv.polygon([(x + 1, y + 8), (x + 9, y + 2), (x + 6, y + 9), (x + 4, y + 6)],
                   color)
    elif kind == "gear":
        cv.ring(x + 5, y + 5, 4, color, 2)
        cv.circle(x + 5, y + 5, 1, color)
    else:  # diamond
        cv.polygon([(x + 5, y), (x + 9, y + 5), (x + 5, y + 10), (x + 1, y + 5)], color)


# ---------------------------------------------------------------- stories
LEAD = {
    "num": 1, "region": "CHINA", "art": "summit",
    "headline": "Trump, Xi and Putin meet in Shenzhen",
    "deck": "First three-way summit of the nuclear powers opens the APEC meeting, "
            "with arms control and trade on the table",
}

FEATURED = [
    {"num": 2, "region": "UKRAINE", "art": "bridge",
     "headline": "Crimea bridge hit again as blasts rock span",
     "deck": "New video shows explosions before part collapses"},
    {"num": 3, "region": "UNITED STATES", "art": "ipo",
     "headline": "Anthropic prices IPO at $83 a share",
     "deck": "Claude maker's debut is the year's biggest listing"},
    {"num": 4, "region": "MYANMAR", "art": "icj",
     "headline": "ICJ rules on Rohingya genocide case",
     "deck": "Court decides if 2017 army campaign was genocide"},
]

GRID = [
    {"num": 5, "region": "NETHERLANDS", "art": "vangogh",
     "headline": "Van Gogh sells for record $190.4M",
     "deck": "Top price after Nazi-row sale"},
    {"num": 6, "region": "INDIA", "art": "cyclone",
     "headline": "Cyclone Akvan bears down on India",
     "deck": "Storm surge feared as coast braces"},
    {"num": 7, "region": "WORLDWIDE", "art": "gta",
     "headline": "GTA VI unlocks at midnight in NZ",
     "deck": "Gamers enter Vice City as rollout begins"},
    {"num": 8, "region": "UNITED KINGDOM", "art": "yacht",
     "headline": "Bayesian report blames high winds",
     "deck": "Superyacht had flaw no one spotted"},
    {"num": 9, "region": "SPAIN", "art": "tennis",
     "headline": "Italy face Ukraine in BJK Cup semis",
     "deck": "Seville hosts the last-four showdown"},
    {"num": 10, "region": "AUSTRALIA", "art": "datacentre",
     "headline": "Nine new data centres planned",
     "deck": "Power and water fears grow in regions"},
    {"num": 11, "region": "SPACE", "art": "satellite",
     "headline": "NASA: Swift fell over Indonesia",
     "deck": "Burst telescope ends 21-year mission"},
    {"num": 12, "region": "MIDDLE EAST", "art": "yellowline",
     "headline": "Israel troops pass Gaza Yellow Line",
     "deck": "Advance crosses ceasefire boundary"},
    {"num": 13, "region": "MARKETS", "art": "dollar",
     "headline": "Dollar hits 19-month high, euro slips",
     "deck": "Greenback climbs as euro slides"},
]

ALSO = [
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


# ---------------------------------------------------------------- layout
def card(cv, x, y, w, story, art_h, head_cap, deck_cap, deck_lines=2):
    """One illustrated card: art panel, badge, headline, deck. Returns height."""
    cv.fill_rect(x, y, w, art_h, CARD_BG)
    cv.set_clip(x, y, w, art_h)
    PAINTERS[story["art"]](cv, x, y, w, art_h)
    cv.clear_clip()
    cv.frame(x, y, w, art_h, HAIRLINE, 1)
    ty = y + art_h + 4
    badge(cv, x + 2, ty, story["num"], story["region"])
    ty += 18
    bottom = draw_block(cv, "bold", story["headline"], x + 2, ty, head_cap, NAVY,
                        w - 4, line_gap=1.16, max_lines=2)
    ty = bottom + 3
    if story.get("deck"):
        bottom = draw_block(cv, "regular", story["deck"], x + 2, ty, deck_cap,
                            GREY, w - 4, line_gap=1.16, max_lines=deck_lines)
        ty = bottom + 2
    return ty - y


def paper_grain(cv, seed=987654321):
    """Subtle deterministic newsprint grain on the bare paper.

    Applied before anything is drawn, so type and art stay crisp on top.
    A fixed-seed LCG perturbs roughly one pixel in four by -2..+2 levels
    on all channels (brightness grain, hue preserved).
    """
    state = seed
    px = cv.px
    for i in range(0, len(px), 3):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        if state % 4 == 0:
            d = ((state >> 10) % 5) - 2
            if d:
                px[i] = max(0, min(255, px[i] + d))
                px[i + 1] = max(0, min(255, px[i + 1] + d))
                px[i + 2] = max(0, min(255, px[i + 2] + d))


def render():
    cv = Canvas(PAGE_W, PAGE_H, PAPER)
    paper_grain(cv)

    # --- masthead
    draw_text(cv, "bold", "THE WORLD'S NEWS IN ONE PICTURE", MARGIN, 32, 15, RED_DARK)
    right = "40 STORIES · FIVE CONTINENTS"
    rw = text_width("bold", right, 12.5)
    draw_text(cv, "bold", right, PAGE_W - MARGIN - rw, 32, 12.5, GREY)
    title = "THURSDAY 19 NOVEMBER 2026"
    cap = fit_cap("black", title, CONTENT_W, cap_hi=90)
    draw_text(cv, "black", title, MARGIN, 44 + cap, cap, NAVY)
    rule_y = int(44 + cap + 10)
    cv.hline(MARGIN, rule_y, CONTENT_W, RED, 3)

    # --- lead + map
    lead_y = rule_y + 9
    art_w, art_h = 624, 108
    cv.set_clip(MARGIN, lead_y, art_w, art_h)
    PAINTERS[LEAD["art"]](cv, MARGIN, lead_y, art_w, art_h)
    cv.clear_clip()
    cv.frame(MARGIN, lead_y, art_w, art_h, HAIRLINE, 1)
    map_x = MARGIN + art_w + 16
    map_w = PAGE_W - MARGIN - map_x
    draw_map(cv, map_x, lead_y + 7, map_w, art_h - 30)
    cap1 = "WHERE IT HAPPENED"
    draw_text(cv, "bold", cap1, map_x + (map_w - text_width("bold", cap1, 11)) / 2,
              lead_y + art_h - 12, 11, NAVY)
    cap2 = "RED DOTS MARK THE BIG STORIES"
    draw_text(cv, "regular", cap2,
              map_x + (map_w - text_width("regular", cap2, 8.5)) / 2,
              lead_y + art_h - 1, 8.5, GREY)
    ly = lead_y + art_h + 6
    badge(cv, MARGIN + 2, ly, LEAD["num"], LEAD["region"])
    ly += 19
    bottom = draw_block(cv, "bold", LEAD["headline"], MARGIN + 2, ly, 26, NAVY,
                        art_w - 4, line_gap=1.16, max_lines=2)
    ly = bottom + 4
    bottom = draw_block(cv, "regular", LEAD["deck"], MARGIN + 2, ly, 12, GREY,
                        art_w - 4, line_gap=1.16, max_lines=2)
    lead_bottom = bottom + 4

    # --- featured row (3 cards)
    fy = lead_bottom + 2
    col_w = (CONTENT_W - 2 * 20) // 3
    heights = []
    for i, story in enumerate(FEATURED):
        cx = MARGIN + i * (col_w + 20)
        heights.append(card(cv, cx, fy, col_w, story, 68, 16.5, 11, deck_lines=2))
    feat_bottom = fy + max(heights) + 4
    cv.hline(MARGIN, feat_bottom, CONTENT_W, HAIRLINE, 1)

    # --- illustrated grid (3 x 3)
    gy = feat_bottom + 6
    row_heights = []
    for row in range(3):
        row_h = 0
        for col in range(3):
            story = GRID[row * 3 + col]
            cx = MARGIN + col * (col_w + 20)
            h = card(cv, cx, gy, col_w, story, 46, 15, 10, deck_lines=1)
            row_h = max(row_h, h)
        row_heights.append(row_h)
        gy += row_h + 6
    grid_bottom = gy - 6
    cv.hline(MARGIN, grid_bottom + 2, CONTENT_W, HAIRLINE, 1)

    # --- ALSO block (4 columns)
    ay = grid_bottom + 8
    draw_text(cv, "bold", "ALSO ON 19 NOVEMBER", MARGIN, ay + 15, 15, RED_DARK)
    ay += 18
    cv.hline(MARGIN, ay, CONTENT_W, RED, 2)
    ay += 4
    also_cols = 4
    also_w = (CONTENT_W - (also_cols - 1) * 12) // also_cols
    row_h = 14
    for i, (num, headline, icon) in enumerate(ALSO):
        col = i % also_cols
        row = i // also_cols
        ix = MARGIN + col * (also_w + 12)
        iy = ay + row * row_h
        draw_text(cv, "bold", str(num), ix, iy + 10, 9, RED_DARK)
        mini_icon(cv, ix + 16, iy + 1, icon, NAVY)
        draw_text(cv, "bold", headline, ix + 30, iy + 10.5, 10, NAVY)
    also_bottom = ay + ((len(ALSO) + also_cols - 1) // also_cols) * row_h

    # --- footer
    fy2 = also_bottom + 6
    cv.hline(MARGIN, fy2, CONTENT_W, HAIRLINE, 1)
    draw_text(cv, "black", "AND FINALLY: BABOON-HUNTING EAGLES AND A BALANCING TRACTOR",
              MARGIN, fy2 + 20, 15, NAVY)
    sources = ("Every story reported on Thursday 19 November 2026 · Sources: "
               "Reuters, BBC, NYT, AP, The Guardian, NDTV, AFP, AAP, Global Voices")
    draw_text(cv, "regular", sources, MARGIN, fy2 + 34, 9.5, GREY)
    if os.environ.get("NEWS_DEBUG"):
        print(f"layout: rule={rule_y} lead_bottom={lead_bottom} "
              f"feat_bottom={feat_bottom} grid_bottom={grid_bottom} "
              f"also_bottom={also_bottom} footer_end={fy2 + 40}")
    return cv


def write_png(path, cv):
    raw = bytearray()
    stride = cv.w * 3
    for yy in range(cv.h):
        raw.append(0)
        raw += cv.px[yy * stride:(yy + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
           chunk(b"IDAT", comp) + chunk(b"IEND", b""))
    Path(path).write_bytes(png)
    return len(png)


def output_path():
    env = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if env:
        return Path(env) / "entry.png"
    if Path("/output").is_dir():
        return Path("/output/entry.png")
    return Path(__file__).resolve().parent / "entry.png"


def main():
    cv = render()
    out = output_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    size = write_png(out, cv)
    print(f"wrote {out} ({size} bytes)")


if __name__ == "__main__":
    main()

# drawkit.py — tiny stdlib-only drawing kit for the news front page.
# Pure python3, no Pillow: RGB canvas + PNG writer (zlib) + real-font
# glyph stamping + flat pictogram icons + themed scene illustrations
# + dotted map.
import base64
import struct
import zlib

from fontdata import FONTS


# ---------------------------------------------------------------- font ----
# Real fonts, pre-rendered by tools/build_fontdata.py (PIL + real TTFs):
#   black   — Archivo Black (OFL), the masthead title
#   bold    — Liberation Sans Bold (Arial-Bold shapes), headlines/tags
#   regular — Liberation Sans Regular, summaries/body
# fontdata holds GRAYSCALE glyph bitmaps (zlib-compressed) + metrics in
# two tiers: hi (cap ~96px) for display cap > 14px, lo (cap ~28px,
# ~4x the 7px ALSO cap) for display cap <= 14px. Round 3 thresholded
# to 1 bit and small text came out ragged; grayscale + area averaging
# keeps small letters smooth and even. Pure stdlib here.
_BLOBS = {name: zlib.decompress(base64.b64decode(blob))
          for name, (_cap, blob, _m) in FONTS.items()}
_CACHE = {}


def _font_for(scale, bold):
    # The masthead title (scale 4) is extra-black; everything else bold
    # is Liberation Bold, regular is Liberation Regular.
    if bold and scale >= 4:
        return 'black'
    return 'bold' if bold else 'regular'


def _downscale(gray, w, h, tw, th):
    """Area-average a GRAYSCALE bitmap (row-major, one byte per pixel)
    down to tw x th; returns bytes of 0..255 alpha. Grayscale in means
    the coverage of every source pixel survives the average, so thin
    strokes at small sizes stay even instead of vanishing like 1-bit."""
    out = bytearray(tw * th)
    sx = w / tw
    sy = h / th
    for ty in range(th):
        fy0 = ty * sy
        fy1 = fy0 + sy
        iy0 = int(fy0)
        iy1 = int(fy1)
        for tx in range(tw):
            fx0 = tx * sx
            fx1 = fx0 + sx
            ix0 = int(fx0)
            ix1 = int(fx1)
            s = 0.0
            for yy in range(iy0, iy1 + 1):
                if yy < 0 or yy >= h:
                    continue
                if iy1 > iy0:
                    wy = (iy0 + 1 - fy0) if yy == iy0 else (
                        (fy1 - iy1) if yy == iy1 else 1.0)
                else:
                    wy = fy1 - fy0
                row0 = yy * w
                for xx in range(ix0, ix1 + 1):
                    if xx < 0 or xx >= w:
                        continue
                    if ix1 > ix0:
                        wx = (ix0 + 1 - fx0) if xx == ix0 else (
                            (fx1 - ix1) if xx == ix1 else 1.0)
                    else:
                        wx = fx1 - fx0
                    s += gray[row0 + xx] * wx * wy
            out[ty * tw + tx] = int(s / (sx * sy) + 0.5)
    return bytes(out)


def _glyph(font, ch, cap_px):
    """Stamp-ready glyph: (tw, th, xoff, yoff, adv_px, alpha_bytes).
    xoff/yoff are the ink box's top-left offset from the pen origin
    (cap top); adv_px is the pen advance. Cached per font/char/size.
    Small text (cap <= 14px) uses the lo tier (~4x source), large
    text the hi tier."""
    key = (font, ch, cap_px)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    if cap_px <= 14 and (font + '_lo') in FONTS:
        font = font + '_lo'
    cap, _blob, metrics = FONTS[font]
    m = metrics.get(ch) or metrics.get('?')
    if m is None:
        res = (0, 0, 0.0, 0.0, 0.0, b'')
        _CACHE[key] = res
        return res
    adv, x0, y0, w, h, off, n = m
    f = cap_px / cap
    adv_px = adv * f
    # Pen origin = cap top; baseline = cap top + cap_px; y0 is the ink
    # top relative to the baseline (negative = above it).
    xoff = x0 * f
    yoff = cap_px + y0 * f
    if w <= 0 or h <= 0:
        res = (0, 0, xoff, yoff, adv_px, b'')
    else:
        tw = max(1, int(round(w * f)))
        th = max(1, int(round(h * f)))
        gray = _BLOBS[font][off:off + n]
        res = (tw, th, xoff, yoff, adv_px, _downscale(gray, w, h, tw, th))
    _CACHE[key] = res
    return res


def text_width(s, scale, bold=False):
    # Sum of real per-glyph advances at this size.
    font = _font_for(scale, bold)
    cap_px = 7 * scale
    return int(sum(_glyph(font, ch, cap_px)[4] for ch in s) + 0.5)


def wrap_text(s, scale, max_w, bold=False):
    """Greedy word wrap; returns list of lines (case preserved)."""
    words = s.split(' ')
    lines = []
    cur = ''
    for w in words:
        trial = (cur + ' ' + w) if cur else w
        if text_width(trial, scale, bold) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def wrap_first(s, scale, first_w, rest_w, bold=False):
    """Greedy word wrap with a narrower FIRST line only (e.g. so the
    first line clears a top-right icon); later lines use rest_w."""
    words = s.split(' ')
    lines = []
    cur = ''
    limit = first_w
    for w in words:
        trial = (cur + ' ' + w) if cur else w
        if text_width(trial, scale, bold) <= limit or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            limit = rest_w
    if cur:
        lines.append(cur)
    return lines


# -------------------------------------------------------------- canvas ----
class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.px = bytearray(bg * (w * h))

    def _off(self, x, y):
        return (y * self.w + x) * 3

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = self._off(x, y)
            self.px[o:o + 3] = c

    def fill_rect(self, x, y, w, h, c):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        for yy in range(y0, y1):
            o = self._off(x0, yy)
            self.px[o:o + (x1 - x0) * 3] = c * (x1 - x0)

    def rect(self, x, y, w, h, c, t=1):
        self.fill_rect(x, y, w, t, c)
        self.fill_rect(x, y + h - t, w, t, c)
        self.fill_rect(x, y, t, h, c)
        self.fill_rect(x + w - t, y, t, h, c)

    def hline(self, x, y, w, c, t=1):
        self.fill_rect(x, y, w, t, c)

    def vline(self, x, y, h, c, t=1):
        self.fill_rect(x, y, t, h, c)

    def line(self, x0, y0, x1, y1, c, t=1):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.fill_rect(x0 - t // 2, y0 - t // 2, t, t, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(self, cx, cy, r, c, fill=True):
        if fill:
            for yy in range(cy - r, cy + r + 1):
                dx = int((r * r - (yy - cy) ** 2) ** 0.5) if abs(yy - cy) <= r else 0
                self.fill_rect(cx - dx, yy, 2 * dx + 1, 1, c)
        else:
            steps = max(8, int(6.2831 * r))
            for i in range(steps):
                a = 6.2831 * i / steps
                self.set(int(cx + r * _cos(a)), int(cy + r * _sin(a)), c)

    def poly(self, pts, c):
        """Filled polygon via scanline."""
        if not pts:
            return
        ys = [p[1] for p in pts]
        for yy in range(max(0, min(ys)), min(self.h, max(ys) + 1)):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= yy < y1) or (y1 <= yy < y0):
                    t = (yy - y0) / (y1 - y0)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.fill_rect(int(xs[i]), yy, max(1, int(xs[i + 1]) - int(xs[i])), 1, c)

    def ellipse(self, cx, cy, rx, ry, c):
        for yy in range(cy - ry, cy + ry + 1):
            t = (yy - cy) / ry if ry else 0
            if abs(t) > 1:
                continue
            dx = int(rx * (1 - t * t) ** 0.5)
            self.fill_rect(cx - dx, yy, 2 * dx + 1, 1, c)

    def text(self, x, y, s, c, scale=1, bold=False):
        # Real-font stamping: y is the cap top, x the pen start; case
        # is preserved (headlines are sentence case like the example).
        # scale may be fractional; cap height = 7 * scale px.
        font = _font_for(scale, bold)
        cap_px = 7 * scale
        cx = x
        r, g, b = c[0], c[1], c[2]
        for ch in s:
            tw, th, xoff, yoff, adv_px, alpha = _glyph(font, ch, cap_px)
            if tw and th:
                gx = int(round(cx + xoff))
                gy = int(round(y + yoff))
                for ty in range(th):
                    py = gy + ty
                    if py < 0 or py >= self.h:
                        continue
                    row = ty * tw
                    base = (py * self.w + gx) * 3
                    for tx in range(tw):
                        a = alpha[row + tx]
                        if not a:
                            continue
                        px = gx + tx
                        if px < 0 or px >= self.w:
                            continue
                        o = base + tx * 3
                        if a == 255:
                            self.px[o] = r
                            self.px[o + 1] = g
                            self.px[o + 2] = b
                        else:
                            ia = 255 - a
                            self.px[o] = (r * a + self.px[o] * ia) // 255
                            self.px[o + 1] = (g * a + self.px[o + 1] * ia) // 255
                            self.px[o + 2] = (b * a + self.px[o + 2] * ia) // 255
            cx += adv_px
        return cx

    def text_block(self, x, y, s, c, scale, max_w, leading=None, bold=False,
                   first_w=None):
        """Wrapped text; returns y just below the last line.
        first_w: optional narrower width for the first line only."""
        lh = leading if leading is not None else 7 * scale + 2
        lines = (wrap_first(s, scale, first_w, max_w, bold)
                 if first_w is not None else wrap_text(s, scale, max_w, bold))
        for ln in lines:
            self.text(x, y, ln, c, scale, bold=bold)
            y += lh
        return y

    def save_png(self, path):
        raw = bytearray()
        stride = self.w * 3
        for yy in range(self.h):
            raw.append(0)
            raw += self.px[yy * stride:(yy + 1) * stride]
        comp = zlib.compress(bytes(raw), 9)

        def chunk(tag, data):
            out = struct.pack('>I', len(data)) + tag + data
            out += struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
            return out

        ihdr = struct.pack('>IIBBBBB', self.w, self.h, 8, 2, 0, 0, 0)
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) +
               chunk(b'IDAT', comp) + chunk(b'IEND', b''))
        with open(path, 'wb') as f:
            f.write(png)
        return len(png)


def _cos(a):
    import math
    return math.cos(a)


def _sin(a):
    import math
    return math.sin(a)


# -------------------------------------------------------------- palette ---
CREAM = b'\xf6\xf1\xe3'
CREAM2 = b'\xef\xe8\xd3'
PAPER = b'\xff\xfd\xf6'
NAVY = b'\x16\x2b\x4d'
NAVY2 = b'\x1f\x3a\x5f'
RED = b'\xc0\x39\x2b'
RED2 = b'\xa8\x2c\x20'
INK = b'\x22\x26\x2e'
GREY = b'\x6b\x6f\x76'
LGREY = b'\xb9\xb3\xa4'
BORDER = b'\xdd\xd3\xbd'
GOLD = b'\xc9\xa2\x27'
SKY = b'\xbf\xd7\xe8'
SKY2 = b'\x8f\xb8\xd4'
SEA = b'\x2f\x6d\x9e'
SEA2 = b'\x4a\x8f\xbf'
GREEN = b'\x2e\x7d\x4f'
ORANGE = b'\xe0\x7a\x2e'


# --------------------------------------------------------------- icons ----
# Each icon draws a flat pictogram inside the box (x, y, size) in colour c.
# All are drawn from primitives so they stay crisp at any size.

def ic_globe(cv, x, y, s, c):
    cv.circle(x + s // 2, y + s // 2, s // 2, c, fill=False)
    cv.ellipse(x + s // 2, y + s // 2, s // 2, s // 4, c)
    cv.vline(x + s // 2, y, s, c)
    cv.hline(x, y + s // 2, s, c)


def ic_chart(cv, x, y, s, c):
    cv.hline(x, y + s - 2, s, c, 2)
    cv.vline(x, y, s, c, 2)
    cv.line(x + 2, y + s - 6, x + s // 3, y + s // 2, c, 2)
    cv.line(x + s // 3, y + s // 2, x + 2 * s // 3, y + s // 3, c, 2)
    cv.line(x + 2 * s // 3, y + s // 3, x + s - 2, y + 2, c, 2)


def ic_gavel(cv, x, y, s, c):
    cv.line(x + 2, y + s - 3, x + s - 3, y + 2, c, 3)
    cv.fill_rect(x + s // 2 - 1, y + 1, s // 2, s // 4, c)
    cv.hline(x + 1, y + s - 2, s - 2, c, 2)


def ic_plane(cv, x, y, s, c):
    cv.poly([(x + s // 2, y + 1), (x + s - 2, y + s // 2),
             (x + s // 2, y + s - 4), (x + s // 2 - 3, y + s // 2)], c)
    cv.poly([(x + 1, y + s // 2), (x + s // 2, y + s // 2 - 2),
             (x + s // 2, y + s // 2 + 2)], c)


def ic_yacht(cv, x, y, s, c):
    cv.poly([(x + s // 2, y + 1), (x + s // 2, y + s // 2),
             (x + s - 3, y + s // 2)], c)
    cv.poly([(x + s // 2 - 2, y + 4), (x + s // 2 - 2, y + s // 2),
             (x + 3, y + s // 2)], c)
    cv.fill_rect(x + 1, y + s // 2 + 2, s - 2, s // 5, c)
    cv.hline(x, y + s - 2, s, c, 2)


def ic_court(cv, x, y, s, c):
    cv.poly([(x, y + s // 3), (x + s // 2, y), (x + s - 1, y + s // 3)], c)
    for i in range(3):
        cx = x + 3 + i * (s - 6) // 2
        cv.vline(cx, y + s // 3 + 2, s // 2, c, 2)
    cv.hline(x, y + s - 3, s, c, 2)


def ic_tennis(cv, x, y, s, c):
    cv.circle(x + s // 2, y + s // 2, s // 2 - 1, c, fill=False)
    cv.line(x + 3, y + 3, x + s - 4, y + s - 4, c, 2)
    cv.line(x + s - 4, y + 3, x + 3, y + s - 4, c, 2)


def ic_podium(cv, x, y, s, c):
    cv.fill_rect(x + s // 3, y + s // 3, s // 3, 2 * s // 3, c)
    cv.fill_rect(x + 1, y + 2 * s // 3, s // 4, s // 3, c)
    cv.fill_rect(x + 3 * s // 4, y + s // 2, s // 4, s // 2, c)
    cv.circle(x + s // 2, y + s // 6, s // 8, c)


def ic_parliament(cv, x, y, s, c):
    cv.ellipse(x + s // 2, y + s // 4, s // 3, s // 6, c)
    cv.fill_rect(x + 2, y + s // 3, s - 4, s // 6, c)
    for i in range(4):
        cx = x + 3 + i * (s - 6) // 3
        cv.vline(cx, y + s // 2, s // 3, c, 2)
    cv.hline(x, y + s - 3, s, c, 2)


def ic_server(cv, x, y, s, c):
    for i in range(3):
        yy = y + 2 + i * (s - 4) // 3
        cv.rect(x + 3, yy, s - 6, (s - 4) // 3 - 2, c, 1)
        cv.circle(x + 6, yy + ((s - 4) // 3 - 2) // 2, 1, c)


def ic_car(cv, x, y, s, c):
    cv.fill_rect(x + 2, y + s // 2, s - 4, s // 4, c)
    cv.poly([(x + s // 4, y + s // 2), (x + s // 3, y + s // 4),
             (x + 2 * s // 3, y + s // 4), (x + 3 * s // 4, y + s // 2)], c)
    cv.circle(x + s // 4, y + 3 * s // 4, s // 8, c)
    cv.circle(x + 3 * s // 4, y + 3 * s // 4, s // 8, c)


def ic_storm(cv, x, y, s, c):
    cx, cy = x + s // 2, y + s // 2
    for r in range(2, s // 2, 3):
        cv.circle(cx, cy, r, c, fill=False)
    cv.circle(cx, cy, 2, c)


def ic_rocket(cv, x, y, s, c):
    cv.poly([(x + s // 2, y), (x + s - 3, y + s // 2),
             (x + s // 2 + 2, y + s - 4), (x + s // 2 - 2, y + s - 4),
             (x + 2, y + s // 2)], c)
    cv.poly([(x + s // 2 - 3, y + s - 3), (x + s // 2, y + s - 1),
             (x + s // 2 + 3, y + s - 3)], c)


def ic_ballot(cv, x, y, s, c):
    cv.rect(x + 2, y + s // 3, s - 4, 2 * s // 3, c, 2)
    cv.line(x + s // 4, y + s // 2, x + s // 2, y + 3 * s // 4, c, 2)
    cv.line(x + s // 2, y + 3 * s // 4, x + s - 3, y + s // 4, c, 2)


def ic_people(cv, x, y, s, c):
    cv.circle(x + s // 3, y + s // 4, s // 6, c)
    cv.circle(x + 2 * s // 3, y + s // 4, s // 6, c)
    cv.ellipse(x + s // 3, y + 3 * s // 4, s // 4, s // 5, c)
    cv.ellipse(x + 2 * s // 3, y + 3 * s // 4, s // 4, s // 5, c)


def ic_mountain(cv, x, y, s, c):
    cv.poly([(x + 1, y + s - 2), (x + s // 3, y + s // 4),
             (x + 2 * s // 3, y + s - 2)], c)
    cv.poly([(x + s // 3, y + s - 2), (x + 2 * s // 3, y + 2),
             (x + s - 1, y + s - 2)], c)


def ic_coin(cv, x, y, s, c):
    cv.circle(x + s // 2, y + s // 2, s // 2 - 1, c, fill=False)
    cv.text(x + s // 2 - 2, y + s // 2 - 3, '$', c, 1)


def ic_book(cv, x, y, s, c):
    cv.rect(x + 2, y + 2, s - 4, s - 4, c, 1)
    cv.vline(x + s // 2, y + 2, s - 4, c, 1)
    cv.hline(x + 4, y + s // 3, s // 4, c, 1)
    cv.hline(x + 4, y + s // 2, s // 4, c, 1)


def ic_mic(cv, x, y, s, c):
    cv.ellipse(x + s // 2, y + s // 4, s // 6, s // 4, c)
    cv.line(x + s // 4, y + s // 2, x + s // 4, y + 3 * s // 4, c, 2)
    cv.line(x + 3 * s // 4, y + s // 2, x + 3 * s // 4, y + 3 * s // 4, c, 2)
    cv.hline(x + s // 4, y + 3 * s // 4, s // 2, c, 2)
    cv.vline(x + s // 2, y + 3 * s // 4, s // 4, c, 2)


def ic_atom(cv, x, y, s, c):
    cx, cy = x + s // 2, y + s // 2
    cv.circle(cx, cy, 2, c)
    cv.ellipse(cx, cy, s // 2 - 1, s // 5, c)
    cv.ellipse(cx, cy, s // 5, s // 2 - 1, c)


def ic_mail(cv, x, y, s, c):
    cv.rect(x + 2, y + s // 4, s - 4, s // 2, c, 1)
    cv.line(x + 2, y + s // 4, x + s // 2, y + s // 2, c, 1)
    cv.line(x + s - 2, y + s // 4, x + s // 2, y + s // 2, c, 1)


def ic_train(cv, x, y, s, c):
    cv.rect(x + 3, y + 2, s - 6, s - 6, c, 1)
    cv.fill_rect(x + 4, y + 3, s - 8, s // 4, c)
    cv.circle(x + s // 3, y + 3 * s // 4, 2, c)
    cv.circle(x + 2 * s // 3, y + 3 * s // 4, 2, c)
    cv.hline(x, y + s - 2, s, c, 2)


def ic_house(cv, x, y, s, c):
    cv.poly([(x, y + s // 2), (x + s // 2, y + 1), (x + s - 1, y + s // 2)], c)
    cv.rect(x + 2, y + s // 2, s - 4, s // 2, c, 1)
    cv.fill_rect(x + s // 2 - 2, y + 2 * s // 3, 4, s // 3, c)


def ic_sun(cv, x, y, s, c):
    cx, cy = x + s // 2, y + s // 2
    cv.circle(cx, cy, s // 4, c)
    for i in range(8):
        a = 6.2831 * i / 8
        cv.line(int(cx + (s // 4 + 1) * _cos(a)), int(cy + (s // 4 + 1) * _sin(a)),
                int(cx + (s // 2 - 1) * _cos(a)), int(cy + (s // 2 - 1) * _sin(a)), c, 1)


def ic_fish(cv, x, y, s, c):
    cv.ellipse(x + s // 2, y + s // 2, s // 3, s // 5, c)
    cv.poly([(x + s - 4, y + s // 2), (x + s - 1, y + 2),
             (x + s - 1, y + s - 3)], c)
    cv.circle(x + s // 3, y + s // 2 - 1, 1, c)


def ic_note(cv, x, y, s, c):
    cv.line(x + 2 * s // 3, y + 2, x + 2 * s // 3, y + 2 * s // 3, c, 2)
    cv.line(x + s // 3, y + s // 3, x + s // 3, y + 3 * s // 4, c, 2)
    cv.ellipse(x + s // 4, y + 3 * s // 4, s // 6, s // 8, c)
    cv.ellipse(x + 7 * s // 12, y + 2 * s // 3, s // 6, s // 8, c)
    cv.line(x + s // 3, y + s // 3, x + 2 * s // 3, y + 2, c, 2)


def ic_briefcase(cv, x, y, s, c):
    cv.rect(x + 2, y + s // 3, s - 4, s // 2, c, 1)
    cv.rect(x + s // 3, y + s // 5, s // 3, s // 5, c, 1)
    cv.hline(x + 2, y + s // 2, s - 4, c, 1)


def ic_hospital(cv, x, y, s, c):
    cv.fill_rect(x + 2, y + 2, s - 4, s - 4, c)
    cv.fill_rect(x + s // 2 - 1, y + 4, 2, s - 8, PAPER)
    cv.fill_rect(x + 4, y + s // 2 - 1, s - 8, 2, PAPER)


def ic_gamepad(cv, x, y, s, c):
    cv.fill_rect(x + 2, y + s // 3, s - 4, s // 3, c)
    cv.circle(x + s // 4, y + s // 2, s // 8, c)
    cv.circle(x + 3 * s // 4, y + s // 2, s // 8, c)
    cv.fill_rect(x + s // 2 - 1, y + s // 3, 2, s // 3, c)


def ic_flag(cv, x, y, s, c):
    cv.vline(x + 2, y + 1, s - 2, c, 2)
    cv.poly([(x + 4, y + 1), (x + s - 1, y + s // 4), (x + 4, y + s // 2)], c)


ICONS = {
    'globe': ic_globe, 'chart': ic_chart, 'gavel': ic_gavel,
    'plane': ic_plane, 'yacht': ic_yacht, 'court': ic_court,
    'tennis': ic_tennis, 'podium': ic_podium, 'parliament': ic_parliament,
    'server': ic_server, 'car': ic_car, 'storm': ic_storm,
    'rocket': ic_rocket, 'ballot': ic_ballot, 'people': ic_people,
    'mountain': ic_mountain, 'coin': ic_coin, 'book': ic_book,
    'mic': ic_mic, 'atom': ic_atom, 'mail': ic_mail, 'train': ic_train,
    'house': ic_house, 'sun': ic_sun, 'fish': ic_fish, 'note': ic_note,
    'briefcase': ic_briefcase, 'hospital': ic_hospital,
    'gamepad': ic_gamepad, 'flag': ic_flag,
}


def draw_icon(cv, name, x, y, s, c):
    fn = ICONS.get(name, ic_globe)
    fn(cv, x, y, s, c)


# ------------------------------------------- themed scene illustrations ----
# Flat, poster-style scenes for the big featured stories. Each fills the
# rect (x, y, w, h) with its own sky/ground bands and simple shapes.

def _sky(cv, x, y, w, h, top, bot):
    for i in range(h):
        t = i / max(1, h - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        cv.hline(x, y + i, w, bytes((r, g, b)))


def _figure(cv, cx, base, s, suit, skin=b'\xe8\xc4\x9a', hair=b'\x33\x2a\x24'):
    # seated person: head + shoulders, scaled by s
    cv.circle(cx, base - int(2.6 * s), int(0.9 * s), skin)
    cv.fill_rect(cx - int(0.9 * s), base - int(2.6 * s) - int(0.9 * s),
                 int(1.8 * s), int(0.5 * s), hair)
    cv.poly([(cx - int(1.7 * s), base), (cx - int(1.2 * s), base - int(1.9 * s)),
             (cx + int(1.2 * s), base - int(1.9 * s)),
             (cx + int(1.7 * s), base)], suit)
    cv.poly([(cx - int(0.3 * s), base - int(1.9 * s)),
             (cx, base - int(1.2 * s)),
             (cx + int(0.3 * s), base - int(1.9 * s))], PAPER)


def star(cv, cx, cy, r, c):
    # 5-pointed star as a filled polygon.
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else max(1, int(r * 0.38))
        a = -1.5708 + 6.2831 * i / 10
        pts.append((int(cx + rr * _cos(a)), int(cy + rr * _sin(a))))
    cv.poly(pts, c)


def draw_flag(cv, x, y, w, h, kind):
    """A small recognizable country flag, with a thin dark border."""
    if kind == 'china':
        cv.fill_rect(x, y, w, h, b'\xde\x29\x10')
        star(cv, x + w // 5, y + h // 4, max(2, h // 5), GOLD)
        for sx, sy in ((w // 2, h // 8), (3 * w // 5, h // 5),
                       (3 * w // 5, 2 * h // 5), (w // 2, h // 2)):
            star(cv, x + sx, y + sy, max(1, h // 10), GOLD)
    elif kind == 'usa':
        sh = h / 13.0
        for i in range(13):
            yy = y + int(i * sh)
            hh = max(1, int((i + 1) * sh) - int(i * sh))
            if i % 2 == 0:
                cv.fill_rect(x, yy, w, hh, b'\xb2\x22\x34')
            else:
                cv.fill_rect(x, yy, w, hh, PAPER)
        cw = int(w * 0.4)
        chh = int(7 * sh)
        cv.fill_rect(x, y, cw, chh, b'\x3c\x3b\x6e')
        for r in range(5):
            for c in range(6):
                sx = x + 3 + c * 4 + (2 if r % 2 else 0)
                sy = y + 2 + r * 2
                if sx < x + cw - 1 and sy < y + chh - 1:
                    cv.fill_rect(sx, sy, 1, 1, PAPER)
    else:  # russia: white-blue-red horizontal tricolour
        cv.fill_rect(x, y, w, h // 3, PAPER)
        cv.fill_rect(x, y + h // 3, w, h // 3, b'\x00\x33\xa1')
        cv.fill_rect(x, y + 2 * h // 3, w, h - 2 * h // 3, b'\xd5\x2b\x1e')
    cv.rect(x, y, w, h, INK, 1)


def art_summit(cv, x, y, w, h):
    _sky(cv, x, y, w, h, b'\xf2\xd8\xa8', b'\xe8\xc9\x8f')
    # hall silhouette
    cv.fill_rect(x, y + h - 26, w, 26, b'\x8a\x6d\x4b')
    for i in range(6):
        cv.fill_rect(x + 8 + i * (w - 16) // 6, y + h - 44, 10, 18,
                     b'\x6e\x56\x3c')
    # three flag poles behind the table: left Xi = China, middle
    # Trump = USA, right Putin = Russia.
    for px, kind in ((x + w // 4, 'china'), (x + w // 2, 'usa'),
                     (x + 3 * w // 4, 'russia')):
        cv.vline(px, y + 6, h // 2, INK, 2)
        draw_flag(cv, px + 2, y + 6, w // 9, h // 5, kind)
    # long table
    ty = y + h - 34
    cv.fill_rect(x + w // 10, ty, 4 * w // 5, 8, b'\x5d\x3f\x28')
    cv.fill_rect(x + w // 10, ty + 8, 4 * w // 5, 4, b'\x7a\x55\x36')
    # three leaders seated
    s = h / 13.0
    for fx, suit in ((x + w // 4, b'\x2b\x3a\x55'),
                     (x + w // 2, b'\x3c\x3c\x3c'),
                     (x + 3 * w // 4, b'\x4a\x2b\x2b')):
        _figure(cv, fx, ty, s, suit)


def art_bridge(cv, x, y, w, h):
    _sky(cv, x, y, w, h, b'\xd8\xe6\xf0', b'\xf2\xe3\xc8')
    cv.fill_rect(x, y + 3 * h // 5, w, 2 * h // 5, SEA)
    for i in range(5):
        cv.hline(x + 6 + i * 17, y + 3 * h // 5 + 8 + (i % 3) * 7,
                 w // 6, SEA2, 2)
    # bridge deck + arch + pillars
    dy = y + h // 2
    cv.fill_rect(x + 4, dy, w - 8, 7, b'\x5a\x5f\x66')
    cv.line(x + w // 6, dy, x + w // 2, dy - h // 4, b'\x7d\x83\x8a', 4)
    cv.line(x + w // 2, dy - h // 4, x + 5 * w // 6, dy, b'\x7d\x83\x8a', 4)
    for px in (x + w // 4, x + w // 2, x + 3 * w // 4):
        cv.vline(px, dy + 7, h // 4, b'\x4a\x4f\x55', 4)
    # explosion burst on the deck
    bx, by = x + 2 * w // 3, dy - 6
    for i in range(10):
        a = 6.2831 * i / 10
        cv.line(bx, by, int(bx + 26 * _cos(a)), int(by + 26 * _sin(a)),
                ORANGE, 4)
    cv.circle(bx, by, 12, b'\xf2\xb1\x34')
    cv.circle(bx, by, 6, RED)
    # smoke
    cv.circle(bx - 18, by - 22, 9, b'\x9a\x9a\x96')
    cv.circle(bx + 4, by - 30, 11, b'\xb0\xb0\xaa')
    cv.circle(bx + 22, by - 20, 8, b'\x9a\x9a\x96')


def art_ipo(cv, x, y, w, h):
    _sky(cv, x, y, w, h, b'\x1d\x3a\x5c', b'\x2c\x55\x7d')
    # exchange building
    bx, by = x + w // 14, y + h // 3
    bw, bh = w // 3, 2 * h // 3 - 6
    cv.fill_rect(bx, by, bw, bh, PAPER)
    cv.poly([(bx - 4, by), (bx + bw // 2, by - h // 6),
             (bx + bw + 4, by)], NAVY2)
    for i in range(3):
        cv.vline(bx + 6 + i * (bw - 12) // 2, by + 6, bh - 12, NAVY2, 3)
    cv.fill_rect(bx - 4, by + bh, bw + 8, 5, NAVY2)
    # rising chart
    pts = [(x + 3 * w // 5, y + 4 * h // 5), (x + 7 * w // 10, y + 3 * h // 5),
           (x + 4 * w // 5, y + 2 * h // 5), (x + 5 * w // 6, y + h // 5),
           (x + w - 8, y + h // 8)]
    for i in range(len(pts) - 1):
        cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                b'\x4c\xd8\x7a', 4)
    cv.poly([(pts[-1][0] - 12, pts[-1][1] + 2), (pts[-1][0], pts[-1][1] - 2),
             (pts[-1][0] - 2, pts[-1][1] + 12)], b'\x4c\xd8\x7a')
    # coins
    for i in range(3):
        cv.circle(x + w // 2 + i * 14, y + h - 12, 7, GOLD)
        cv.text(x + w // 2 + i * 14 - 2, y + h - 15, '$', NAVY, 1)


def art_court(cv, x, y, w, h):
    _sky(cv, x, y, w, h, b'\xe8\xe2\xd2', b'\xd8\xcf\xb6')
    # courthouse
    cx0, cy0 = x + w // 8, y + h // 4
    cw, ch = 3 * w // 4, 3 * h // 5
    cv.fill_rect(cx0, cy0 + h // 6, cw, ch, PAPER)
    cv.poly([(cx0 - 6, cy0 + h // 6), (cx0 + cw // 2, cy0),
             (cx0 + cw + 6, cy0 + h // 6)], NAVY2)
    for i in range(4):
        px = cx0 + 8 + i * (cw - 16) // 3
        cv.vline(px, cy0 + h // 6 + 4, ch - 10, NAVY2, 5)
    cv.fill_rect(cx0 + cw // 2 - 8, cy0 + h // 6 + ch - 22, 16, 22, NAVY2)
    cv.fill_rect(cx0 - 6, cy0 + h // 6 + ch, cw + 12, 5, NAVY2)
    # scales of justice, bottom right
    sx, sy = x + w - w // 5, y + h - h // 4
    cv.vline(sx, sy - 20, 22, GOLD, 3)
    cv.hline(sx - 16, sy - 20, 32, GOLD, 3)
    cv.line(sx - 16, sy - 20, sx - 22, sy - 2, GOLD, 2)
    cv.line(sx + 16, sy - 20, sx + 22, sy - 2, GOLD, 2)
    cv.ellipse(sx - 22, sy - 1, 8, 4, GOLD)
    cv.ellipse(sx + 22, sy - 1, 8, 4, GOLD)


# -------------------------------------------------------- dotted map ------
# Land mask as (start, end) column ranges per row, 64 cols x 26 rows.
# Equirectangular: col = (lon+180)/360*64, row = (75-lat)/130*26.
_MAP_ROWS = [
    [(1, 4), (6, 17), (20, 23), (30, 31), (35, 63)],
    [(1, 5), (6, 18), (21, 23), (30, 33), (34, 63)],
    [(2, 5), (7, 19), (22, 23), (30, 33), (35, 63)],
    [(3, 6), (8, 20), (30, 33), (34, 60), (60, 62)],
    [(9, 21), (29, 36), (37, 60)],
    [(9, 22), (29, 37), (38, 58), (60, 61)],
    [(10, 23), (29, 36), (38, 57), (59, 61)],
    [(11, 24), (29, 37), (38, 46), (48, 57), (59, 60)],
    [(12, 24), (29, 38), (39, 46), (48, 52), (53, 58)],
    [(12, 17), (22, 24), (29, 39), (40, 45), (48, 52), (54, 57)],
    [(13, 18), (22, 25), (29, 40), (41, 44), (48, 51), (53, 57)],
    [(14, 19), (30, 41), (49, 50), (53, 58), (58, 59)],
    [(15, 19), (31, 42), (54, 58)],
    [(20, 24), (32, 42), (55, 58), (56, 62)],
    [(21, 26), (33, 42), (56, 63)],
    [(21, 27), (34, 41), (57, 62)],
    [(22, 27), (34, 40), (58, 62)],
    [(22, 28), (34, 40), (58, 62)],
    [(23, 28), (34, 39), (57, 63)],
    [(23, 28), (34, 39), (56, 63)],
    [(24, 28), (34, 38), (56, 62)],
    [(24, 27), (35, 37), (57, 61), (63, 63)],
    [(25, 27), (58, 60), (63, 63)],
    [(25, 26), (63, 63)],
    [(25, 26)],
    [(25, 25)],
]

# (lon, lat) of the big stories, for red dots.
MAP_DOTS = [
    (114.0, 22.5), (33.5, 45.0), (-74.0, 40.7), (4.3, 52.0),
    (96.0, 21.0), (86.0, 20.0), (-75.7, 45.4), (139.7, 35.7),
    (-0.1, 51.5), (-6.3, 53.3), (-6.0, 37.4), (121.0, 14.6),
    (151.2, -33.9), (174.8, -41.3), (101.7, 3.1), (178.0, -17.7),
    (34.5, 31.5), (28.0, -26.2), (15.0, 15.0), (73.0, 33.6),
    (-80.2, 25.8), (28.8, 47.0),
]


def draw_map(cv, x, y, w, h, dots=MAP_DOTS):
    cols, rows = 64, 26
    step = min(w / cols, h / rows)
    ox = x + (w - step * cols) / 2
    oy = y + (h - step * rows) / 2
    r = max(1, int(step * 0.32))
    for ri, spans in enumerate(_MAP_ROWS):
        cy = int(oy + ri * step + step / 2)
        for a, b in spans:
            for ci in range(a, b + 1):
                cx = int(ox + ci * step + step / 2)
                cv.circle(cx, cy, r, LGREY)
    for lon, lat in dots:
        ci = (lon + 180.0) / 360.0 * cols
        ri = (75.0 - lat) / 130.0 * rows
        cx = int(ox + ci * step + step / 2)
        cy = int(oy + ri * step + step / 2)
        cv.circle(cx, cy, max(2, r + 1), RED)
        cv.circle(cx, cy, max(1, r), RED2)

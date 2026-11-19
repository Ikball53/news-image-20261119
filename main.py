#!/usr/bin/env python3
"""News image entry: Thursday 19 November 2026 — 16 stories, 4 continents.
Pure Python standard library. Deterministic: no randomness, no clock, no
network. Composites the pre-rendered RGBA assets in assets/ onto a cream
front page and writes entry.png to $MAKEFUN_OUTPUT_DIR (or /output).
"""
import binascii
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

W, H = 1024, 1024
CREAM = (247, 242, 228)
WHITE = (255, 255, 255)
NAVY = (26, 35, 64)
CARD_BORDER = (229, 221, 200)
PAGE_BORDER = (216, 208, 188)


# ---------------------------------------------------------------- PNG decode
def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png(path):
    """Decode an 8-bit non-interlaced PNG (colour types 2 and 6) to RGBA bytes."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG: %s" % path)
    pos = 8
    width = height = bitdepth = ctype = None
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype4 = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype4 == b"IHDR":
            width, height, bitdepth, ctype = struct.unpack(">IIBB", chunk[:10])
            if bitdepth != 8 or ctype not in (2, 6):
                raise ValueError("unsupported PNG %s: depth %d type %d" % (path, bitdepth, ctype))
        elif ctype4 == b"IDAT":
            idat += chunk
        elif ctype4 == b"IEND":
            break
        pos += 12 + length
    channels = 4 if ctype == 6 else 3
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    out = bytearray(width * height * 4)
    prev = bytearray(stride)
    p = 0
    for y in range(height):
        ftype = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ftype == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 255
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ftype == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(a, b, c)) & 255
        elif ftype != 0:
            raise ValueError("bad filter %d in %s" % (ftype, path))
        for x in range(width):
            o = (y * width + x) * 4
            s = x * channels
            out[o] = line[s]
            out[o + 1] = line[s + 1]
            out[o + 2] = line[s + 2]
            out[o + 3] = line[s + 3] if channels == 4 else 255
        prev = line
    return width, height, bytes(out)


# ---------------------------------------------------------------- PNG encode
def write_png(path, width, height, rgb):
    def chunk(tag, payload):
        c = struct.pack(">I", len(payload)) + tag + payload
        return c + struct.pack(">I", binascii.crc32(tag + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# ---------------------------------------------------------------- canvas
def new_canvas():
    buf = bytearray(W * H * 3)
    r, g, b = CREAM
    for i in range(0, len(buf), 3):
        buf[i] = r
        buf[i + 1] = g
        buf[i + 2] = b
    return buf


def fill_rect(buf, x0, y0, x1, y1, color):
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(W, x1)
    y1 = min(H, y1)
    r, g, b = color
    row = bytes((r, g, b)) * (x1 - x0)
    for y in range(y0, y1):
        o = (y * W + x0) * 3
        buf[o:o + len(row)] = row


def rounded_rect(buf, x0, y0, x1, y1, radius, color):
    import math
    r = radius
    for y in range(y0, y1):
        if y < y0 + r:
            dy = (y0 + r) - y - 0.5
            dx = math.sqrt(max(0.0, r * r - dy * dy))
            xa = int((x0 + r) - dx)
            xb = int((x1 - r) + dx)
        elif y >= y1 - r:
            dy = y - (y1 - r) + 0.5
            dx = math.sqrt(max(0.0, r * r - dy * dy))
            xa = int((x0 + r) - dx)
            xb = int((x1 - r) + dx)
        else:
            xa, xb = x0, x1
        fill_rect(buf, xa, y, xb, y + 1, color)


def card(buf, x0, y0, x1, y1, radius=10):
    rounded_rect(buf, x0, y0, x1, y1, radius, CARD_BORDER)
    rounded_rect(buf, x0 + 1, y0 + 1, x1 - 1, y1 - 1, radius - 1, WHITE)


# Decoded assets are reused across paste calls (paste_right used to decode
# the same file twice); the cache keeps the run fast and deterministic.
_ASSET_CACHE = {}


def load_asset(path):
    if path not in _ASSET_CACHE:
        _ASSET_CACHE[path] = read_png(os.path.join(ASSETS, path))
    return _ASSET_CACHE[path]


def paste(buf, path, x0, y0):
    w, h, px = load_asset(path)
    for y in range(h):
        dy = y0 + y
        if dy < 0 or dy >= H:
            continue
        for x in range(w):
            dx = x0 + x
            if dx < 0 or dx >= W:
                continue
            o = (y * w + x) * 4
            a = px[o + 3]
            if a == 0:
                continue
            bo = (dy * W + dx) * 3
            if a == 255:
                buf[bo] = px[o]
                buf[bo + 1] = px[o + 1]
                buf[bo + 2] = px[o + 2]
            else:
                buf[bo] = (px[o] * a + buf[bo] * (255 - a)) // 255
                buf[bo + 1] = (px[o + 1] * a + buf[bo + 1] * (255 - a)) // 255
                buf[bo + 2] = (px[o + 2] * a + buf[bo + 2] * (255 - a)) // 255


def paste_right(buf, path, right_x, y0):
    w, _h, _px = load_asset(path)
    paste(buf, path, right_x - w, y0)


def main():
    buf = new_canvas()
    # page frame
    rounded_rect(buf, 10, 10, 1014, 1014, 16, PAGE_BORDER)
    rounded_rect(buf, 12, 12, 1012, 1012, 15, CREAM)

    # masthead
    paste(buf, "txt_kicker.png", 24, 30)
    paste_right(buf, "txt_kicker_right.png", 1000, 32)
    paste(buf, "txt_title.png", 24, 52)
    fill_rect(buf, 24, 124, 1000, 126, NAVY)

    # lead story + map
    card(buf, 24, 140, 548, 360)
    paste(buf, "lead_art.png", 34, 150)
    paste(buf, "lead_text.png", 228, 150)
    card(buf, 560, 140, 1000, 360)
    paste(buf, "txt_map_head.png", 574, 150)
    paste_right(buf, "txt_map_date.png", 986, 152)
    paste(buf, "map_base.png", 568, 174)

    # three featured stories
    for i, n in enumerate((2, 3, 4)):
        x = 24 + i * 332
        card(buf, x, 372, x + 312, 584)
        paste(buf, "feat%d_banner.png" % n, x + 6, 378)
        paste(buf, "feat%d_text.png" % n, x + 12, 468)

    # also on 19 november: 12 compact stories
    card(buf, 24, 596, 1000, 984)
    paste(buf, "txt_also.png", 36, 608)
    for idx, n in enumerate(range(5, 17)):
        col, row = idx % 3, idx // 3
        cx = 24 + col * 325
        ry = 632 + row * 88
        paste(buf, "icon_%d.png" % n, cx + 12, ry + 12)
        paste(buf, "also_text_%d.png" % n, cx + 82, ry + 12)

    # footer
    paste(buf, "txt_footer.png", 94, 994)

    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, "entry.png")
    nbytes = write_png(outpath, W, H, bytes(buf))
    try:
        write_png(os.path.join(HERE, "entry.png"), W, H, bytes(buf))
    except OSError:
        pass
    print("wrote %s (%d bytes)" % (outpath, nbytes))
    return 0


if __name__ == "__main__":
    sys.exit(main())

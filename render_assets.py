# render_assets.py — build-time asset renderer for news-image-20261119 v2.
# Runs on the builder VM with Pillow + DejaVu fonts. Fully deterministic:
# fixed seeds, no time, no network. Emits RGBA PNG assets under assets/.
# Everything is drawn at SS x supersampling and downscaled with LANCZOS so
# edges are smooth (PIL shapes are otherwise jagged). Flags are rendered at
# 4 x and downscaled. The graded entrypoint (main.py, pure stdlib) composites
# these at run time.
import math
import os
import random

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
os.makedirs(ASSETS, exist_ok=True)

SS = 3          # supersample factor for shapes and text
FLAG_SS = 4     # supersample factor for flags

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
F_SANS = os.path.join(FONT_DIR, "DejaVuSans.ttf")
F_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

NAVY = (26, 35, 64)
RED = (192, 57, 43)
GREY = (96, 96, 90)
TGREY = (74, 72, 66)
CREAM = (247, 242, 228)
TAN = (231, 221, 198)
WHITE = (255, 255, 255)


def font(size, bold=False):
    return ImageFont.truetype(F_BOLD if bold else F_SANS, size)


class SD:
    """Supersampled draw wrapper: coordinates and widths are scaled by SS."""

    def __init__(self, draw, ss=SS):
        self.d = draw
        self.ss = ss

    def _c(self, v):
        if isinstance(v, (list, tuple)):
            return type(v)(self._c(x) for x in v)
        if isinstance(v, (int, float)):
            return v * self.ss
        return v

    def _kw(self, kw):
        out = {}
        for k, v in kw.items():
            if k == "width":
                out[k] = max(1, int(round(v * self.ss)))
            else:
                out[k] = v
        return out

    def rectangle(self, xy, **kw):
        self.d.rectangle(self._c(xy), **self._kw(kw))

    def ellipse(self, xy, **kw):
        self.d.ellipse(self._c(xy), **self._kw(kw))

    def polygon(self, xy, **kw):
        self.d.polygon(self._c(xy), **self._kw(kw))

    def line(self, xy, **kw):
        self.d.line(self._c(xy), **self._kw(kw))

    def arc(self, xy, a0, a1, **kw):
        self.d.arc(self._c(xy), a0, a1, **self._kw(kw))

    def rounded_rectangle(self, xy, **kw):
        r = kw.pop("radius", 0)
        self.d.rounded_rectangle(self._c(xy), radius=r * self.ss, **self._kw(kw))


def wrap(text, fnt, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if fnt.getlength(trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def star_points(cx, cy, r_out, r_in, n=5, rot=-90.0):
    pts = []
    for i in range(2 * n):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180.0 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def draw_flag(d, code, x, y, w, h):
    """Draw a flag (correct proportions/patterns, official colours) into draw
    d at (x, y, w, h). d may be a supersampled context; all coords are in
    that context's units."""
    x2, y2 = x + w, y + h

    def band(ft, fb, color):
        d.rectangle([x, y + h * ft, x2 - 1, y + h * fb - 1], fill=color)

    def vband(fl, fr, color):
        d.rectangle([x + w * fl, y, x + w * fr - 1, y2 - 1], fill=color)

    if code == "CN":  # China: red, one large + four small yellow stars
        d.rectangle([x, y, x2 - 1, y2 - 1], fill=(222, 41, 16))
        d.polygon(star_points(x + w * 0.20, y + h * 0.30, h * 0.20, h * 0.08),
                  fill=(255, 222, 0))
        for sx, sy in [(0.42, 0.12), (0.50, 0.24), (0.50, 0.42), (0.42, 0.54)]:
            d.polygon(star_points(x + w * sx, y + h * sy, h * 0.075, h * 0.03),
                      fill=(255, 222, 0))
    elif code == "UA":  # Ukraine: blue over yellow
        band(0.0, 0.5, (0, 87, 183))
        band(0.5, 1.0, (255, 215, 0))
    elif code == "US":  # USA: 13 stripes + canton with 50 stars
        for i in range(13):
            y0 = y + h * i / 13.0
            y1 = y + h * (i + 1) / 13.0 - 1
            if y1 < y0:
                y1 = y0
            d.rectangle([x, y0, x2 - 1, y1],
                        fill=(178, 34, 52) if i % 2 == 0 else (255, 255, 255))
        cw, ch = w * 0.40, h * 7.0 / 13.0
        d.rectangle([x, y, x + cw - 1, y + ch - 1], fill=(60, 59, 110))
        for r in range(5):
            n = 6 if r % 2 == 0 else 5
            for c in range(n):
                sx = x + cw * (0.09 + 0.165 * c + (0.08 if r % 2 else 0))
                sy = y + ch * (0.11 + 0.195 * r)
                rr = max(1.0, h * 0.028)
                d.polygon(star_points(sx, sy, rr, rr * 0.4), fill=(255, 255, 255))
    elif code == "MM":  # Myanmar: yellow-green-red + white star
        band(0.0, 1 / 3, (254, 203, 0))
        band(1 / 3, 2 / 3, (52, 178, 51))
        band(2 / 3, 1.0, (234, 40, 57))
        d.polygon(star_points(x + w * 0.5, y + h * 0.5, h * 0.26, h * 0.105),
                  fill=(255, 255, 255))
    elif code == "NL":  # Netherlands: red-white-blue
        band(0.0, 1 / 3, (174, 28, 40))
        band(1 / 3, 2 / 3, (255, 255, 255))
        band(2 / 3, 1.0, (33, 70, 139))
    elif code == "IN":  # India: saffron-white-green + navy chakra with spokes
        band(0.0, 1 / 3, (255, 153, 51))
        band(1 / 3, 2 / 3, (255, 255, 255))
        band(2 / 3, 1.0, (19, 136, 8))
        cx, cy, r = x + w * 0.5, y + h * 0.5, h * 0.17
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(6, 3, 141), width=max(1, int(h * 0.02)))
        for i in range(8):
            a = math.radians(i * 45)
            d.line([cx, cy, cx + r * math.cos(a), cy + r * math.sin(a)],
                   fill=(6, 3, 141), width=max(1, int(h * 0.015)))
        d.ellipse([cx - r * 0.18, cy - r * 0.18, cx + r * 0.18, cy + r * 0.18],
                  fill=(6, 3, 141))
    elif code == "CA":  # Canada: red-white-red + maple leaf
        vband(0.0, 0.25, (255, 0, 0))
        vband(0.25, 0.75, (255, 255, 255))
        vband(0.75, 1.0, (255, 0, 0))
        cx, cy = x + w * 0.5, y + h * 0.5
        s = h * 0.44
        leaf = [(0, -1.0), (0.20, -0.74), (0.30, -0.86), (0.54, -0.56),
                (0.44, -0.30), (0.74, -0.36), (0.42, 0.04), (0.54, 0.44),
                (0.18, 0.28), (0.10, 0.78), (-0.10, 0.78), (-0.18, 0.28),
                (-0.54, 0.44), (-0.42, 0.04), (-0.74, -0.36), (-0.44, -0.30),
                (-0.54, -0.56), (-0.30, -0.86), (-0.20, -0.74)]
        d.polygon([(cx + px * s, cy + py * s) for px, py in leaf], fill=(255, 0, 0))
    elif code == "JP":  # Japan: white field, red disc
        d.rectangle([x, y, x2 - 1, y2 - 1], fill=(255, 255, 255))
        cx, cy, r = x + w * 0.5, y + h * 0.5, h * 0.30
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(188, 0, 45))
    elif code == "GB":  # United Kingdom: Union Jack (simplified, correct layout)
        d.rectangle([x, y, x2 - 1, y2 - 1], fill=(1, 33, 105))
        dw = max(1.0, h * 0.17)
        d.line([x, y, x2, y2], fill=(255, 255, 255), width=int(dw))
        d.line([x2, y, x, y2], fill=(255, 255, 255), width=int(dw))
        dr = max(1.0, h * 0.06)
        d.line([x, y, x2, y2], fill=(200, 16, 46), width=int(dr))
        d.line([x2, y, x, y2], fill=(200, 16, 46), width=int(dr))
        d.rectangle([x, y + h * 0.40, x2 - 1, y + h * 0.60 - 1], fill=(255, 255, 255))
        d.rectangle([x + w * 0.44, y, x + w * 0.56 - 1, y2 - 1], fill=(255, 255, 255))
        d.rectangle([x, y + h * 0.45, x2 - 1, y + h * 0.55 - 1], fill=(200, 16, 46))
        cx0 = int(x + w * 0.47)
        cx1 = max(cx0, int(x + w * 0.53 - 1))
        d.rectangle([cx0, y, cx1, y2 - 1], fill=(200, 16, 46))
    elif code == "IE":  # Ireland: green-white-orange
        vband(0.0, 1 / 3, (22, 155, 98))
        vband(1 / 3, 2 / 3, (255, 255, 255))
        vband(2 / 3, 1.0, (255, 136, 62))
    elif code == "ES":  # Spain: red-yellow-red (yellow double height)
        band(0.0, 0.25, (170, 21, 27))
        band(0.25, 0.75, (241, 191, 0))
        band(0.75, 1.0, (170, 21, 27))
    elif code == "ID":  # Indonesia: red over white
        band(0.0, 0.5, (255, 0, 0))
        band(0.5, 1.0, (255, 255, 255))
    elif code == "AU":  # Australia: blue, Union Jack canton, Federation star, Southern Cross
        d.rectangle([x, y, x2 - 1, y2 - 1], fill=(0, 36, 125))
        cw, ch = w * 0.5, h * 0.5
        d.rectangle([x, y, x + cw - 1, y + ch - 1], fill=(1, 33, 105))
        d.line([x, y, x + cw, y + ch], fill=(255, 255, 255), width=max(1, int(h * 0.05)))
        d.line([x + cw, y, x, y + ch], fill=(255, 255, 255), width=max(1, int(h * 0.05)))
        d.rectangle([x, y + ch * 0.40, x + cw - 1, y + ch * 0.60 - 1], fill=(255, 255, 255))
        ax0 = int(x + cw * 0.44)
        ax1 = max(ax0, int(x + cw * 0.56 - 1))
        d.rectangle([ax0, y, ax1, y + ch - 1], fill=(255, 255, 255))
        d.polygon(star_points(x + w * 0.25, y + h * 0.75, h * 0.16, h * 0.07, n=7),
                  fill=(255, 255, 255))
        for fx, fy in [(0.72, 0.30), (0.85, 0.55), (0.68, 0.72), (0.90, 0.80)]:
            sx, sy = x + w * fx, y + h * fy
            rr = max(1.0, h * 0.05)
            d.polygon(star_points(sx, sy, rr, rr * 0.4), fill=(255, 255, 255))
    elif code == "RU":  # Russia: white-blue-red
        band(0.0, 1 / 3, (255, 255, 255))
        band(1 / 3, 2 / 3, (0, 57, 166))
        band(2 / 3, 1.0, (213, 43, 30))


def flag_image(code, w, h):
    """A crisp flag of size (w, h): drawn at 4x, downscaled, neat 1px edge."""
    big = Image.new("RGBA", (w * FLAG_SS, h * FLAG_SS), (0, 0, 0, 0))
    draw_flag(ImageDraw.Draw(big), code, 0, 0, w * FLAG_SS, h * FLAG_SS)
    img = big.resize((w, h), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], outline=(0, 0, 0, 110), width=1)
    return img


def downscale(img, w, h):
    return img.resize((w, h), Image.LANCZOS)


# ---------------------------------------------------------------- text assets
def single_text(name, text, size, bold, fill):
    fnt1 = font(size, bold)
    w = int(fnt1.getlength(text)) + 2
    h = size + 6
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    ImageDraw.Draw(big).text((SS, SS), text, font=font(size * SS, bold),
                             fill=fill + (255,))
    downscale(big, w, h).save(os.path.join(ASSETS, name))
    return w, h


single_text("txt_kicker.png", "THE WORLD'S NEWS IN ONE PICTURE", 19, True, RED)
single_text("txt_kicker_right.png", "16 STORIES FROM 4 CONTINENTS", 14, True, GREY)
single_text("txt_map_head.png", "WHERE IT HAPPENED", 14, True, RED)
single_text("txt_map_date.png", "19 NOV 2026", 13, True, GREY)
single_text("txt_also.png", "ALSO ON 19 NOVEMBER", 15, True, RED)
single_text("txt_footer.png",
            "Every story here was reported on Thursday 19 November 2026. "
            "Sources: The New York Times, Reuters, BBC, GOV.UK, AAP, Nusa Kini, CBC.",
            12, False, GREY)

title = "THURSDAY 19 NOVEMBER 2026"
tsize = 58
while font(tsize, True).getlength(title) > 976 and tsize > 30:
    tsize -= 1
single_text("txt_title.png", title, tsize, True, NAVY)


def text_block(path, lines, width):
    """lines: (text, size, bold, fill, line_h). Rendered at SSx, downscaled."""
    rows = []
    for text, size, bold, fill, lh in lines:
        fnt = font(size * SS, bold)
        for ln in wrap(text, fnt, width * SS):
            rows.append((ln, fnt, fill, lh * SS))
    height = sum(r[3] for r in rows)
    big = Image.new("RGBA", (width * SS, max(height, SS)), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    y = 0
    for ln, fnt, fill, lh in rows:
        d.text((0, y), ln, font=fnt, fill=fill + (255,))
        y += lh
    downscale(big, width, height // SS).save(path)
    return height // SS


def badge_block(path, num, flag, tag, head, summ, width, head_size, head_lh,
                sum_size, sum_lh, badge_r, tag_size):
    """Badge + flag + tag row, headline, summary — drawn at SSx, downscaled."""
    W2, H2 = width * SS, 420 * SS
    big = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    sd = SD(d, SS)
    # badge: red disc + white number
    sd.ellipse([0, 0, badge_r * 2, badge_r * 2], fill=RED + (255,))
    nf = font((badge_r + 4) * SS, True)
    tw = nf.getlength(str(num))
    th = nf.getbbox(str(num))[3]
    d.text(((badge_r * SS) - tw / 2, (badge_r * SS) - th / 2 - SS),
           str(num), font=nf, fill=(255, 255, 255, 255))
    fx = badge_r * 2 + 6
    fw, fh = (28, 19) if badge_r >= 12 else (26, 17)
    big.alpha_composite(flag_image(flag, fw * SS, fh * SS), (fx * SS, 3 * SS))
    tf = font(tag_size * SS, True)
    d.text(((fx + fw + 8) * SS, 4 * SS), tag, font=tf, fill=RED + (255,))
    y = (badge_r * 2 + 8) * SS
    hf = font(head_size * SS, True)
    for ln in wrap(head, hf, width * SS):
        d.text((0, y), ln, font=hf, fill=NAVY + (255,))
        y += head_lh * SS
    y += 5 * SS
    sf = font(sum_size * SS, False)
    for ln in wrap(summ, sf, width * SS):
        d.text((0, y), ln, font=sf, fill=TGREY + (255,))
        y += sum_lh * SS
    h1 = y // SS
    downscale(big.crop((0, 0, W2, y)), width, h1).save(path)
    return h1


badge_block(os.path.join(ASSETS, "lead_text.png"), 1, "CN", "CHINA",
            "Trump, Xi and Putin meet in Shenzhen for trilateral talks",
            "The three leaders hold a first-ever trilateral summit, with nuclear arms, "
            "Iran and trade on the agenda. Xi hugged Trump on the tarmac as he landed.",
            310, 27, 33, 13, 17, 12, 15)
badge_block(os.path.join(ASSETS, "feat2_text.png"), 2, "UA", "UKRAINE",
            "Crimea Bridge hit again in third strike this week",
            "Traffic is suspended after a fresh attack on the Kerch crossing, "
            "the third in days.",
            288, 20, 24, 13, 16, 11, 14)
badge_block(os.path.join(ASSETS, "feat3_text.png"), 3, "US", "UNITED STATES",
            "Anthropic prices record $81.3bn IPO",
            "Trading starts today at $83 under ANT; the firm is valued near $1.5tn.",
            288, 20, 24, 13, 16, 11, 14)
badge_block(os.path.join(ASSETS, "feat4_text.png"), 4, "MM", "MYANMAR",
            "ICJ rules in Rohingya genocide case",
            "The UN court delivers its verdict against Myanmar in The Hague, "
            "seven years on.",
            288, 20, 24, 13, 16, 11, 14)

ALSO = [
    (5, "NL", "Van Gogh sells for a record $190.4m at Sotheby's New York"),
    (6, "IN", "Cyclone Akvan to hit India's east coast by Friday noon"),
    (7, "CA", "Carney meets Trump in Shenzhen — no deal, no tariff relief"),
    (8, "JP", "India and Japan hold 2+2 foreign and defence talks in Tokyo"),
    (9, "GB", "Bayesian report: crew did not know of the wind danger"),
    (10, "GB", "Hundreds of McDonald's workers win right to full hearing"),
    (11, "IE", "UK and Irish ministers meet in Dublin on Troubles legacy"),
    (12, "ES", "Billie Jean King Cup semi: Italy v Ukraine in Seville"),
    (13, "ID", "Prabowo presses resilience agenda at ASEAN summit"),
    (14, "GB", "Leasehold bill enters Parliament, capping ground rents"),
    (15, "AU", "Nine data-centre plans 'could rival coal plants'"),
    (16, "US", "GTA VI unlocks at midnight, starting in New Zealand"),
]
for num, _flag, head in ALSO:
    text_block(os.path.join(ASSETS, "also_text_%d.png" % num),
               [(head, 15, True, NAVY, 19)], 233)


# ---------------------------------------------------------------- illustrations
def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def lead_art():
    W, H = 184, 200
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    sd = SD(d, SS)
    rng = random.Random(7)
    # night sky: smooth vertical gradient
    for i in range(12):
        sd.rectangle([0, i * 15, W, (i + 1) * 15],
                     fill=lerp((15, 25, 48), (30, 44, 80), i / 11) + (255,))
    # stars: few, subtle
    for _ in range(26):
        sx, sy = rng.randint(3, W - 3), rng.randint(3, 62)
        r = rng.choice([1, 1, 2])
        sd.ellipse([sx - r, sy - r, sx + r, sy + r],
                   fill=(255, 255, 255, rng.choice([140, 180, 220])))
    # moon with soft glow
    sd.ellipse([138, 8, 166, 36], fill=(240, 235, 200, 60))
    sd.ellipse([144, 13, 162, 31], fill=(240, 235, 200, 255))
    # skyline: flat-topped towers, regular lit-window grids
    base = 178
    towers = [(6, 16, 92, "spire"), (26, 22, 68, None), (52, 26, 52, None),
              (82, 20, 78, "round"), (106, 24, 58, None), (134, 18, 86, "mast"),
              (156, 24, 48, None)]
    for tx, tw, th, kind in towers:
        sd.rectangle([tx, base - th, tx + tw, base], fill=(12, 20, 36, 255))
        if kind == "spire":
            sd.polygon([(tx + 2, base - th), (tx + tw - 2, base - th),
                        (tx + tw / 2, base - th - 16)], fill=(12, 20, 36, 255))
        elif kind == "round":
            sd.ellipse([tx, base - th - 8, tx + tw, base - th + 8],
                       fill=(12, 20, 36, 255))
        elif kind == "mast":
            sd.line([tx + tw / 2, base - th - 12, tx + tw / 2, base - th],
                    fill=(12, 20, 36, 255), width=2)
        for wy in range(base - th + 6, base - 6, 9):
            for wx in range(tx + 4, tx + tw - 3, 7):
                if rng.random() < 0.55:
                    sd.rectangle([wx, wy, wx + 2, wy + 2], fill=(255, 214, 90, 255))
    # red carpet + gold trim
    sd.rectangle([0, 178, W, 200], fill=(163, 51, 39, 255))
    sd.rectangle([0, 178, W, 180], fill=(212, 175, 55, 255))
    # three flag poles, evenly spaced, flags at one height
    for i, code in enumerate(["CN", "US", "RU"]):
        px = 20 + i * 56
        sd.line([px, 78, px, 150], fill=(205, 205, 205, 255), width=2)
        big.alpha_composite(flag_image(code, 40 * SS, 26 * SS),
                            ((px + 3) * SS, 78 * SS))
    downscale(big, W, H).save(os.path.join(ASSETS, "lead_art.png"))


def bridge_art():
    W, H = 300, 84
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    sd = SD(d, SS)
    for i in range(6):
        sd.rectangle([0, i * 10, W, (i + 1) * 10],
                     fill=lerp((205, 225, 242), (238, 244, 248), i / 5) + (255,))
    sd.rectangle([0, 58, W, H], fill=(143, 184, 217, 255))
    sd.rectangle([0, 58, W, 60], fill=(185, 210, 232, 255))
    # towers, symmetric, with crossbeams
    for tx in (72, 228):
        sd.rectangle([tx - 3, 14, tx + 3, 52], fill=(74, 82, 96, 255))
        sd.rectangle([tx - 9, 20, tx + 9, 23], fill=(74, 82, 96, 255))
        for dx in (-58, -30, 30, 58):
            sd.line([tx, 22, tx + dx, 52], fill=(120, 128, 140, 255), width=1)
    # deck with a broken notch at the blast
    sd.rectangle([0, 52, W, 58], fill=(91, 100, 112, 255))
    sd.rectangle([0, 52, W, 53], fill=(140, 148, 158, 255))
    sd.rectangle([141, 52, 159, 58], fill=(58, 58, 58, 255))
    # blast: clean radial starburst + soft smoke
    sd.polygon(star_points(150, 46, 14, 6, n=8), fill=(255, 140, 0, 255))
    sd.polygon(star_points(150, 46, 8, 3, n=8), fill=(255, 220, 0, 255))
    sd.ellipse([147, 43, 153, 49], fill=(255, 255, 255, 255))
    for cx, cy, r in [(136, 30, 8), (150, 23, 10), (164, 31, 7)]:
        sd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(154, 160, 166, 215))
    downscale(big, W, H).save(os.path.join(ASSETS, "feat2_banner.png"))


def ipo_art():
    W, H = 300, 84
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    sd = SD(d, SS)
    sd.rectangle([0, 0, W, H], fill=(238, 243, 248, 255))
    for gy in (24, 48):
        sd.line([16, gy, 284, gy], fill=(220, 228, 236, 255), width=1)
    sd.line([16, 74, 284, 74], fill=(180, 190, 200, 255), width=1)
    heights = [16, 26, 38, 50, 64]
    for i, bh in enumerate(heights):
        bx = 20 + i * 48
        sd.rectangle([bx, 74 - bh, bx + 30, 74], fill=(46, 158, 91, 255))
    pts = [(35, 52), (83, 42), (131, 30), (179, 18), (227, 4)]
    sd.line(pts, fill=(200, 40, 30, 255), width=3)
    sd.polygon([(227, 4), (213, 2), (224, 14)], fill=(200, 40, 30, 255))
    for px, py in pts:
        sd.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(200, 40, 30, 255))
    downscale(big, W, H).save(os.path.join(ASSETS, "feat3_banner.png"))


def icj_art():
    W, H = 300, 84
    big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    sd = SD(d, SS)
    sd.rectangle([0, 0, W, H], fill=(243, 238, 225, 255))
    # pediment + gold emblem
    sd.polygon([(70, 30), (150, 10), (230, 30)], fill=(201, 184, 150, 255))
    sd.ellipse([145, 16, 155, 26], fill=(184, 134, 11, 255))
    sd.rectangle([70, 30, 230, 34], fill=(180, 164, 132, 255))
    # four even columns with capitals and bases
    for cx in (88, 126, 164, 202):
        sd.rectangle([cx - 7, 34, cx + 7, 37], fill=(232, 224, 204, 255))
        sd.rectangle([cx - 5, 37, cx + 5, 62], fill=(232, 224, 204, 255))
        sd.rectangle([cx - 5, 37, cx + 5, 62], outline=(150, 138, 110, 255), width=1)
        sd.rectangle([cx - 7, 62, cx + 7, 65], fill=(232, 224, 204, 255))
    # door between the middle columns
    sd.rectangle([142, 48, 158, 65], fill=(90, 80, 60, 255))
    # three even steps
    sd.rectangle([66, 65, 234, 69], fill=(180, 164, 132, 255))
    sd.rectangle([60, 69, 240, 73], fill=(160, 144, 112, 255))
    sd.rectangle([54, 73, 246, 77], fill=(140, 124, 92, 255))
    downscale(big, W, H).save(os.path.join(ASSETS, "feat4_banner.png"))


lead_art()
bridge_art()
ipo_art()
icj_art()


# ---------------------------------------------------------------- small icons
def icon_canvas():
    big = Image.new("RGBA", (60 * SS, 60 * SS), (244, 239, 226, 255))
    d = ImageDraw.Draw(big)
    SD(d, SS).rounded_rectangle([0, 0, 60, 60], radius=8,
                                outline=(220, 210, 185, 255), width=1)
    return big, SD(d, SS)


def icon_with_flag(name, flag, draw_fn):
    big, sd = icon_canvas()
    draw_fn(sd)
    img = downscale(big, 60, 60)
    img.alpha_composite(flag_image(flag, 24, 16), (1, 43))
    img.save(os.path.join(ASSETS, name))


def ic_vangogh(sd):
    sd.rectangle([10, 8, 50, 48], fill=(176, 141, 62, 255))
    sd.rectangle([14, 12, 46, 44], fill=(123, 167, 217, 255))
    sd.ellipse([36, 14, 44, 22], fill=(255, 220, 0, 255))
    # one large sunflower, centred, with stem and leaves
    sd.line([30, 44, 30, 34], fill=(60, 140, 70, 255), width=2)
    sd.polygon([(30, 40), (22, 44), (30, 46)], fill=(60, 140, 70, 255))
    sd.polygon([(30, 40), (38, 44), (30, 46)], fill=(60, 140, 70, 255))
    sd.ellipse([22, 22, 38, 38], fill=(255, 200, 0, 255))
    sd.ellipse([26, 26, 34, 34], fill=(120, 70, 20, 255))


def ic_cyclone(sd):
    for cx, cy, r in [(22, 22, 9), (32, 18, 10), (42, 23, 8)]:
        sd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(138, 148, 166, 255))
    sd.rectangle([14, 28, 50, 30], fill=(138, 148, 166, 255))
    for i in range(3):
        x = 18 + i * 11
        sd.line([x, 36, x - 4, 50], fill=(60, 120, 200, 255), width=2)
    sd.arc([6, 32, 24, 48], 200, 340, fill=(100, 110, 130, 255), width=2)


def ic_carney(sd):
    sd.line([12, 10, 12, 46], fill=(140, 140, 140, 255), width=2)
    sd.line([34, 10, 34, 46], fill=(140, 140, 140, 255), width=2)
    sd.line([8, 46, 52, 46], fill=(160, 160, 160, 255), width=1)


def ic_twoplus(sd):
    sd.line([6, 12, 6, 40], fill=(140, 140, 140, 255), width=2)
    sd.line([30, 12, 30, 40], fill=(140, 140, 140, 255), width=2)
    sd.ellipse([18, 40, 42, 48], fill=(201, 184, 150, 255))
    sd.rectangle([28, 48, 32, 54], fill=(150, 138, 110, 255))


def ic_bayesian(sd):
    sd.rectangle([0, 44, 60, 60], fill=(120, 170, 210, 255))
    sd.line([0, 46, 60, 46], fill=(200, 225, 240, 255), width=1)
    sd.line([32, 12, 32, 42], fill=(90, 70, 50, 255), width=2)
    sd.polygon([(32, 14), (32, 40), (50, 40)], fill=(255, 255, 255, 255))
    sd.polygon([(30, 16), (30, 40), (16, 40)], fill=(222, 222, 222, 255))
    sd.polygon([(12, 40), (48, 40), (52, 48), (8, 48)], fill=(255, 255, 255, 255))
    sd.polygon([(12, 40), (48, 40), (52, 48), (8, 48)],
               outline=(120, 120, 120, 255))
    sd.rectangle([12, 40, 48, 42], fill=(200, 40, 30, 255))


def ic_mcdonalds(sd):
    sd.rounded_rectangle([4, 6, 56, 54], radius=6, fill=(212, 43, 30, 255))
    sd.rectangle([10, 12, 50, 15], fill=(255, 255, 255, 255))
    # blocky golden "M"
    sd.polygon([(16, 46), (16, 22), (22, 22), (26, 32), (30, 22), (36, 22),
                (36, 46), (30, 46), (30, 30), (27, 38), (24, 30), (22, 46)],
               fill=(255, 199, 44, 255))
    sd.rectangle([26, 46, 34, 52], fill=(120, 70, 40, 255))


def ic_biigc(sd):
    sd.line([8, 6, 8, 26], fill=(140, 140, 140, 255), width=2)
    sd.line([32, 6, 32, 26], fill=(140, 140, 140, 255), width=2)
    sd.polygon([(8, 26), (30, 16), (52, 26)], fill=(150, 120, 90, 255))
    sd.rectangle([12, 26, 48, 50], fill=(232, 224, 204, 255))
    for wx in (17, 27, 37):
        sd.rectangle([wx, 32, wx + 5, 38], fill=(90, 120, 160, 255))
    sd.rectangle([27, 42, 33, 50], fill=(90, 70, 50, 255))


def ic_bjk(sd):
    sd.ellipse([8, 6, 34, 34], outline=(120, 120, 120, 255), width=2)
    for sx in (16, 22, 28):
        sd.line([sx, 11, sx, 31], fill=(160, 160, 160, 255), width=1)
    for sy in (14, 20, 26):
        sd.line([12, sy, 30, sy], fill=(160, 160, 160, 255), width=1)
    sd.line([21, 34, 21, 52], fill=(120, 120, 120, 255), width=3)
    sd.ellipse([28, 28, 54, 54], fill=(198, 225, 74, 255))
    sd.arc([28, 28, 54, 54], 300, 60, fill=(255, 255, 255, 255), width=2)
    sd.arc([28, 28, 54, 54], 120, 240, fill=(255, 255, 255, 255), width=2)


def ic_asean(sd):
    sd.line([28, 8, 28, 32], fill=(140, 140, 140, 255), width=2)
    sd.rectangle([10, 44, 50, 50], fill=(150, 150, 150, 255))
    sd.rectangle([16, 38, 44, 44], fill=(170, 170, 170, 255))
    sd.rectangle([22, 32, 38, 38], fill=(190, 190, 190, 255))


def ic_leasehold(sd):
    sd.polygon([(8, 30), (30, 14), (52, 30)], fill=(150, 90, 60, 255))
    sd.rectangle([12, 30, 48, 50], fill=(240, 230, 205, 255))
    sd.rectangle([26, 38, 34, 50], fill=(90, 120, 160, 255))
    for wx in (16, 40):
        sd.rectangle([wx, 34, wx + 5, 40], fill=(140, 180, 220, 255))
    sd.ellipse([44, 42, 50, 48], outline=(184, 134, 11, 255), width=2)
    sd.line([47, 48, 47, 54], fill=(184, 134, 11, 255), width=2)


def ic_datacentre(sd):
    sd.rectangle([8, 12, 28, 50], fill=(43, 52, 66, 255))
    sd.rectangle([32, 12, 52, 50], fill=(43, 52, 66, 255))
    for ry in (18, 28, 38):
        for rx, col in [(13, (80, 200, 120)), (20, (255, 180, 0)),
                        (37, (80, 200, 120)), (44, (255, 180, 0))]:
            sd.ellipse([rx, ry, rx + 3, ry + 3], fill=col + (255,))
    sd.polygon([(46, 6), (38, 26), (44, 26), (40, 40), (52, 18), (46, 18)],
               fill=(255, 210, 0, 255))


def ic_gta(sd):
    sd.rectangle([0, 0, 60, 60], fill=(26, 35, 64, 255))
    rng = random.Random(11)
    x = 2
    while x < 58:
        bw = rng.randint(6, 10)
        bh = rng.randint(8, 20)
        sd.rectangle([x, 30 - bh, x + bw, 30], fill=(13, 21, 38, 255))
        for _ in range(2):
            wx = rng.randint(x + 1, max(x + 1, x + bw - 3))
            wy = rng.randint(30 - bh + 2, 28)
            sd.rectangle([wx, wy, wx + 1, wy + 1], fill=(255, 214, 90, 255))
        x += bw + 2
    sd.rounded_rectangle([10, 34, 50, 52], radius=6, fill=(40, 44, 60, 255))
    sd.ellipse([16, 40, 22, 46], fill=(200, 200, 200, 255))
    sd.ellipse([38, 40, 44, 46], fill=(200, 200, 200, 255))
    for bx, by, c in [(28, 38, (255, 80, 80)), (33, 38, (255, 220, 0)),
                      (28, 43, (80, 200, 120)), (33, 43, (90, 140, 255))]:
        sd.ellipse([bx, by, bx + 3, by + 3], fill=c + (255,))


# icons whose art embeds extra flags: paste them at SSx, then downscale
def icon_with_flags(name, flag, draw_fn, extra):
    big, sd = icon_canvas()
    draw_fn(sd)
    for code, fx, fy, fw, fh in extra:
        big.alpha_composite(flag_image(code, fw * SS, fh * SS),
                            (fx * SS, fy * SS))
    img = downscale(big, 60, 60)
    img.alpha_composite(flag_image(flag, 24, 16), (1, 43))
    img.save(os.path.join(ASSETS, name))


icon_with_flag("icon_5.png", "NL", ic_vangogh)
icon_with_flag("icon_6.png", "IN", ic_cyclone)
icon_with_flags("icon_7.png", "CA", ic_carney,
                [("CA", 14, 10, 18, 12), ("US", 36, 10, 18, 12)])
icon_with_flags("icon_8.png", "JP", ic_twoplus,
                [("IN", 8, 12, 20, 13), ("JP", 32, 12, 20, 13)])
icon_with_flag("icon_9.png", "GB", ic_bayesian)
icon_with_flag("icon_10.png", "GB", ic_mcdonalds)
icon_with_flags("icon_11.png", "IE", ic_biigc,
                [("GB", 10, 6, 20, 13), ("IE", 34, 6, 20, 13)])
icon_with_flag("icon_12.png", "ES", ic_bjk)
icon_with_flags("icon_13.png", "ID", ic_asean,
                [("ID", 30, 8, 22, 15)])
icon_with_flag("icon_14.png", "GB", ic_leasehold)
icon_with_flag("icon_15.png", "AU", ic_datacentre)
icon_with_flag("icon_16.png", "US", ic_gta)


# ---------------------------------------------------------------- world map
# Base map only (tan continents + faint grid). Story locations are marked
# with RED DOTS ONLY — no flags, no other markers on the map.
def map_base():
    W, H = 424, 178
    big = Image.new("RGBA", (W * SS, H * SS), (255, 255, 255, 255))
    d = ImageDraw.Draw(big)
    sd = SD(d, SS)

    def px(lon, lat):
        return ((lon + 180.0) / 360.0 * W, (90.0 - lat) / 150.0 * H)

    for lon in range(-150, 181, 30):
        x, _ = px(lon, 0)
        sd.line([x, 0, x, H], fill=(236, 231, 216, 255), width=1)
    for lat in range(-60, 91, 30):
        _, y = px(0, lat)
        sd.line([0, y, W, y], fill=(236, 231, 216, 255), width=1)

    land = [
        # North America
        (-105, 60, 26, 10), (-95, 42, 20, 9), (-100, 24, 7, 7),
        (-85, 15, 4, 2.5), (-72, 10, 6, 3), (-42, 74, 8, 4),
        # South America
        (-62, 4, 7, 5), (-58, -6, 11, 9), (-66, -28, 7, 10),
        # Europe
        (12, 50, 14, 6), (16, 62, 7, 5), (-3, 54, 2, 3),
        (-4, 40, 4.5, 3), (16, 41, 4, 2.5), (40, 55, 12, 7),
        # Africa (gap at the Mediterranean)
        (6, 20, 13, 8), (22, 0, 10, 9), (26, -20, 7, 8),
        (47, -19, 2, 4),
        # Asia
        (70, 60, 28, 10), (140, 62, 14, 7), (62, 44, 12, 7),
        (88, 38, 12, 6), (45, 28, 8, 6), (78, 22, 7, 9),
        (102, 12, 7, 7), (110, 34, 11, 8), (139, 38, 2.5, 5),
        (112, -2, 10, 3), (122, -1, 6, 3), (141, -4, 7, 3),
        # Oceania
        (134, -25, 12, 6), (147, -42, 2.5, 2), (172, -41, 2, 3.5),
    ]
    # faint dotted world: a small tan dot at each grid point that falls on land
    for glon in range(-176, 181, 4):
        for glat in range(-57, 88, 3):
            on_land = False
            for clon, clat, rx, ry in land:
                if ((glon - clon) / rx) ** 2 + ((glat - clat) / ry) ** 2 <= 1:
                    on_land = True
                    break
            if on_land:
                cx, cy = px(glon, glat)
                sd.ellipse([cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5],
                           fill=(216, 205, 180, 255))

    # red dots only, one per story (the three London stories are nudged apart)
    # one red dot per story; the NW-Europe / NE-America clusters are nudged
    # a few degrees apart so the dots stay distinct (still in the right region)
    dots = [
        (114.1, 22.5), (33.5, 45.3), (-74.0, 40.7), (96.0, 21.9),
        (6.5, 53.0), (86.5, 19.8), (-79.0, 47.0), (139.7, 35.7),
        (-0.1, 51.5), (-4.0, 54.0), (-8.0, 54.5), (-6.0, 37.4),
        (106.8, -6.2), (3.0, 49.0), (151.2, -33.9), (174.8, -36.8),
    ]
    for lon, lat in dots:
        cx, cy = px(lon, lat)
        sd.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(255, 255, 255, 255))
        sd.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=RED + (255,))
    downscale(big, W, H).save(os.path.join(ASSETS, "map_base.png"))


map_base()

print("assets written:", len(os.listdir(ASSETS)))
for name in sorted(os.listdir(ASSETS)):
    im = Image.open(os.path.join(ASSETS, name))
    print(" ", name, im.size, im.mode)

# main.py — "The World in One Picture", Thursday 19 November 2026.
# Pure stdlib (no Pillow): draws a 1024x1024 newspaper front page with
# drawkit.py and writes entry.png to $MAKEFUN_OUTPUT_DIR (or /output).
# Deterministic: no time, no randomness, no network.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from drawkit import (Canvas, CREAM, CREAM2, PAPER, NAVY, NAVY2, RED, RED2,
                     INK, GREY, LGREY, BORDER, GOLD, text_width, wrap_text,
                     draw_icon, draw_map, art_summit, art_bridge, art_ipo,
                     art_court)

W, H = 1024, 1024

# ---------------------------------------------------------------- stories --
# (num, region, headline, summary, icon, art)
# Sentence case like the 13 Nov example: bold headlines, regular
# summaries. Only masthead/tags/headers stay all-caps.
LEAD = (1, 'CHINA',
        'Trump, Xi and Putin meet in Shenzhen',
        'First three-way summit of the nuclear powers opens the APEC '
        'meeting, with arms control and trade on the table',
        'globe', 'summit')

FEATURED = [
    (2, 'UKRAINE',
     'Crimea bridge hit again as blasts rock span',
     'New video shows explosions before part collapses',
     'storm', 'bridge'),
    (3, 'UNITED STATES',
     'Anthropic prices IPO at $83 a share',
     "Claude maker's debut is the year's biggest listing",
     'chart', 'ipo'),
    (4, 'MYANMAR',
     'ICJ rules on Rohingya genocide case',
     'Court decides if 2017 army campaign was genocide',
     'court', 'court'),
]

GRID = [
    (5, 'NETHERLANDS',
     'Van Gogh sells for record $190.4M',
     'Painting fetches top price after Nazi-row sale', 'sun'),
    (6, 'INDIA',
     'Cyclone Akvan bears down on India',
     'Storm surge feared as East Coast braces', 'storm'),
    (7, 'CANADA',
     'Carney and Trump end with no deal',
     'Trade talks stall as tariffs stay in place', 'people'),
    (8, 'JAPAN',
     'India and Japan hold 2+2 talks in Tokyo',
     'Defence ties top agenda at ministerial meeting', 'plane'),
    (9, 'UNITED KINGDOM',
     'Bayesian report blames high winds',
     'Superyacht had flaw no one spotted, inquiry finds', 'yacht'),
    (10, 'UNITED KINGDOM',
     "McDonald's workers win tribunal fight",
     'Staff can sue over abuse claims, judge rules', 'briefcase'),
    (11, 'IRELAND',
     'UK and Ireland meet in Dublin',
     'Leaders talk trade, borders and peace', 'people'),
    (12, 'SPAIN',
     'Italy face Ukraine in BJK Cup semis',
     'Seville hosts the last-four showdown', 'tennis'),
    (13, 'INDONESIA',
     'Prabowo at ASEAN summit in Manila',
     'Leaders gather as trade tops the agenda', 'podium'),
    (14, 'UNITED KINGDOM',
     'Commonhold bill goes to Parliament',
     'Leasehold reform finally reaches MPs', 'parliament'),
    (15, 'AUSTRALIA',
     'Nine new data centres planned',
     'Power and water fears grow in the regions', 'server'),
    (16, 'WORLDWIDE',
     'GTA VI unlocks at midnight in NZ',
     'Gamers enter Vice City as rollout begins', 'gamepad'),
]

# ALSO items: ONE-LINE bold headlines only (round 5: the 4-col x 6-row
# block of 2-line tiny text read as a dense grey blur at phone size —
# "acak-acakan". Now 3 cols x 8 rows, same rhythm as the example's
# grid, one clean bold line per row, generous row height). Headlines
# shortened to fit one line in a ~320px column at scale 1.5 bold
# (verified with text_width); meaning and key facts/dates kept.
# No flags, per the user.
ALSO = [
    (17, 'MALAYSIA', 'UNHCR stops sign-ups in Malaysia', 'people'),
    (18, 'PACIFIC', 'Fiji declares drought disaster', 'sun'),
    (19, 'CHINA', 'Trump raised ex-Nvidia boss with Xi', 'mic'),
    (20, 'INDIA', "Pew: India's faith map is shifting", 'book'),
    (21, 'WORLD', 'Islam set to be top faith by 2035', 'globe'),
    (22, 'INDIA', 'William, Kate meet Modi in Mumbai', 'people'),
    (23, 'MIDDLE EAST', 'Israel troops pass Gaza Yellow Line', 'people'),
    (24, 'AUSTRALIA', 'Australia jobless hits 5-year high', 'chart'),
    (25, 'UNITED STATES', "Musk calls midterm spree 'foolish'", 'mic'),
    (26, 'UNITED STATES', 'Florida pastor guilty in Haiti case', 'gavel'),
    (27, 'UNITED STATES', 'Fed split on bigger rate hike', 'chart'),
    (28, 'EUROPE', 'Moldova teens try democracy app', 'book'),
    (29, 'EUROPE', 'Spain strikes over housing crisis', 'house'),
    (30, 'PAKISTAN', 'Pakistan 325, Sri Lanka toil in Test', 'tennis'),
    (31, 'NEW ZEALAND', 'India-NZ Tests begin in Wellington', 'tennis'),
    (32, 'SOUTH AFRICA', 'Rickelton ton tightens SA grip', 'tennis'),
    (33, 'ASIA', 'HCMC Police stun Buriram 1-0', 'people'),
    (34, 'SPACE', 'NASA: Swift fell over Indonesia', 'rocket'),
    (35, 'AFRICA', 'Eagles hunted 57lb baboons in Chad', 'atom'),
    (36, 'SCIENCE', 'Dental floss tests blood sugar', 'hospital'),
    (37, 'TECHNOLOGY', 'AI teaches tractor to balance', 'car'),
    (38, 'MARKETS', 'Dollar hits 19-month high, euro slips', 'coin'),
    (39, 'SOUTH AFRICA', 'Mofokeng brace rescues Bafana', 'people'),
    (40, 'INDIA', 'Reliance eyes satellites vs Starlink', 'rocket'),
]

ARTS = {'summit': art_summit, 'bridge': art_bridge, 'ipo': art_ipo,
        'court': art_court}


# ---------------------------------------------------------------- layout ---
def badge(cv, cx, cy, num, r=9):
    cv.circle(cx, cy, r, RED)
    s = str(num)
    cv.text(cx - text_width(s, 1, bold=True) // 2, cy - 3, s, PAPER, 1,
            bold=True)


def tag_text(cv, x, y, s):
    cv.text(x, y, s, RED, 1, bold=True)


def render():
    cv = Canvas(W, H, CREAM)
    cv.rect(6, 6, W - 12, H - 12, BORDER, 2)

    # ---- masthead ----
    cv.text(14, 16, "THE WORLD'S NEWS IN ONE PICTURE", RED, 1.5, bold=True)
    right = "40 STORIES - FIVE CONTINENTS"
    cv.text(W - 14 - text_width(right, 1.5), 16, right, GREY, 1.5)
    cv.text(14, 52, 'THURSDAY 19 NOVEMBER 2026', NAVY, 4, bold=True)
    cv.fill_rect(14, 88, W - 28, 4, RED)

    # ---- lead story #1 + map ----
    num, region, head, summ, icon, art = LEAD
    ax, ay, aw, ah = 14, 96, 634, 104
    ARTS[art](cv, ax, ay, aw, ah)
    cv.rect(ax, ay, aw, ah, BORDER, 1)
    badge(cv, ax + 14, 214, num)
    tag_text(cv, ax + 30, 211, region)
    y = cv.text_block(ax, 228, head, NAVY, 3, aw, leading=23, bold=True)
    cv.text_block(ax, y + 6, summ, INK, 1, aw, leading=9)

    mx, my, mw, mh = 664, 96, 346, 140
    cv.fill_rect(mx, my, mw, mh, PAPER)
    cv.rect(mx, my, mw, mh, BORDER, 1)
    draw_map(cv, mx + 4, my + 4, mw - 8, mh - 8)
    cap = 'WHERE IT HAPPENED'
    cv.text(mx + (mw - text_width(cap, 1, bold=True)) // 2, my + mh + 8,
            cap, NAVY, 1, bold=True)
    sub = 'RED DOTS MARK THE BIG STORIES'
    cv.text(mx + (mw - text_width(sub, 1)) // 2, my + mh + 20, sub, GREY, 1)

    # ---- featured stories #2-#4, big themed art ----
    fx0, fy, fw = 14, 296, 322
    for i, (num, region, head, summ, icon, art) in enumerate(FEATURED):
        x = fx0 + i * (fw + 15)
        ARTS[art](cv, x, fy, fw, 86)
        cv.rect(x, fy, fw, 86, BORDER, 1)
        badge(cv, x + 14, fy + 100, num)
        tag_text(cv, x + 30, fy + 97, region)
        y = cv.text_block(x, fy + 112, head, NAVY, 2, fw, leading=17,
                          bold=True)
        cv.text_block(x, y + 3, summ, INK, 1, fw, leading=9)

    # ---- grid stories #5-#16 ----
    gx0, gy, gw, gh = 14, 476, 322, 72
    for i, (num, region, head, summ, icon) in enumerate(GRID):
        x = gx0 + (i % 3) * (gw + 15)
        y = gy + (i // 3) * (gh + 4)
        cv.fill_rect(x, y, gw, gh, PAPER)
        cv.rect(x, y, gw, gh, BORDER, 1)
        badge(cv, x + 14, y + 13, num)
        tag_text(cv, x + 30, y + 10, region)
        draw_icon(cv, icon, x + gw - 34, y + 6, 26, NAVY2)
        # Headline first line wraps at 268 so it can never reach the
        # top-right icon (icon starts at x+gw-34 = x+288); later lines
        # use the full width, the icon band is above them.
        yy = cv.text_block(x + 10, y + 26, head, NAVY, 2, gw - 20,
                           leading=17, bold=True, first_w=268)
        cv.text(x + 10, yy + 2, summ, GREY, 1)

    # ---- ALSO section #17-#40: 3 cols x 8 rows, one-line bold
    # headlines (round 5). Same 322px column rhythm as the grid, so
    # the block reads as airy cards like the example — not a dense
    # 4-col blur. Row = red number + small icon + one bold line.
    ay0 = 778
    cv.text(14, ay0, 'ALSO ON 19 NOVEMBER', NAVY, 2, bold=True)
    cv.fill_rect(14, ay0 + 18, W - 28, 2, RED)
    ax0, ayy, aw2, ah2 = 14, 800, 322, 20
    for i, (num, region, head, icon) in enumerate(ALSO):
        x = ax0 + (i % 3) * (aw2 + 15)
        y = ayy + (i // 3) * (ah2 + 2)
        cv.fill_rect(x, y, aw2, ah2, PAPER)
        cv.rect(x, y, aw2, ah2, BORDER, 1)
        cv.text(x + 4, y + 6, str(num), RED, 1, bold=True)
        draw_icon(cv, icon, x + 22, y + 1, 18, NAVY2)
        # Single line, bold scale 1.5: every headline is verified to
        # fit the 272px text width (see /tmp/check_also.py).
        cv.text(x + 44, y + 4, head, INK, 1.5, bold=True)

    # ---- footer ----
    cv.text(14, 984, 'AND FINALLY: BABOON-HUNTING EAGLES AND A '
                     'BALANCING TRACTOR', NAVY, 2, bold=True)
    cv.text(14, 1004, 'Every story reported on Thursday 19 November 2026 - '
                      'Sources: Reuters, BBC, NYT, AP, The Guardian, NDTV, '
                      'AFP, AAP, Global Voices', GREY, 1)
    return cv


def main():
    outdir = os.environ.get('MAKEFUN_OUTPUT_DIR') or '/output'
    if not os.path.isdir(outdir):
        outdir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(outdir, exist_ok=True)
    cv = render()
    path = os.path.join(outdir, 'entry.png')
    n = cv.save_png(path)
    print('wrote %s (%d bytes, %dx%d)' % (path, n, W, H))


if __name__ == '__main__':
    main()

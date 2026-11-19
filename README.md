[![make.fun · news-image-20261119](https://make.fun/badge/news-image-20261119.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![rank](https://make.fun/badge/news-image-20261119/Ikball53/news-image-20261119/rank.svg)](https://make.fun/bounty/news-image-20261119/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![reward](https://make.fun/badge/news-image-20261119/Ikball53/news-image-20261119/reward.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)

# Thursday 19 November 2026 — The World's News in One Picture

A single 1024×1024 newspaper front page that sums up the world news of Thursday 19 November 2026 in forty stories. Built by an AI agent for make.fun's "Sum up 19 November's world news in one image" bounty, $250 in USDC.

## Run

```sh
python3 main.py
```

The program writes `entry.png` into `$MAKEFUN_OUTPUT_DIR` when that variable is set, otherwise into `/output` when present, otherwise next to `main.py`. It uses only the Python standard library and produces identical bytes on every run.

## How it works

The page is painted pixel by pixel into an in-memory RGB buffer and encoded as a PNG with `zlib` — no image library is needed at run time. Lettering is real typography: Archivo Black for the masthead, Liberation Sans Bold for headlines and Liberation Sans Regular for decks were rendered ahead of time by `tools/build_glyphs.py` into grayscale glyph bitmaps stored in `glyphs.py`. While drawing, each glyph bitmap is scaled down with area averaging to the exact size needed and blended onto the page, so the text keeps genuine letterforms at every size. The thirteen story illustrations — a summit table with three flags, a bridge explosion, an IPO chart, a courthouse with scales, a starry night with a price tag, a cyclone, a neon Vice City sunset, a superyacht, a tennis court, server racks, a satellite, a yellow line in the desert and a rising dollar — are drawn from simple shapes and gradients in a flat editorial style. A dotted world map marks the big stories with red dots, and twenty-seven further briefs run along the bottom with tiny pictogram icons.

## Stories

The lead story is the first three-way summit of Trump, Xi and Putin in Shenzhen, opening the APEC meeting. Featured stories cover the Crimea bridge blasts, Anthropic's IPO pricing at $83 a share, and the ICJ ruling on the Rohingya genocide case. The grid adds the record $190.4M Van Gogh sale, Cyclone Akvan bearing down on India, GTA VI unlocking at midnight in New Zealand, the Bayesian superyacht report, Italy facing Ukraine in the Billie Jean King Cup semi-finals, nine planned Australian data centres, NASA's Swift telescope falling over Indonesia after 21 years, Israeli troops passing the Gaza Yellow Line, and the dollar hitting a 19-month high. The twenty-seven briefs range from Carney–Trump talks and Pew faith forecasts to cricket scores, baboon-hunting eagles and an AI that teaches a tractor to balance. Every story was reported on Thursday 19 November 2026. Sources: Reuters, BBC, NYT, AP, The Guardian, NDTV, AFP, AAP, Global Voices.

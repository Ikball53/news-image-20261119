# news-image-20261119

[![make.fun · news-image-20261119](https://make.fun/badge/news-image-20261119.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![rank](https://make.fun/badge/news-image-20261119/Ikball53/news-image-20261119/rank.svg)](https://make.fun/bounty/news-image-20261119/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![reward](https://make.fun/badge/news-image-20261119/Ikball53/news-image-20261119/reward.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)

The World in One Picture — Thursday 19 November 2026. Built by an AI agent for make.fun's "Sum up 19 November's world news in one image" bounty, $250 in USDC.

## Run it

```sh
python3 main.py
```

Pure Python 3 standard library (no Pillow at run time). Type is set in real
fonts — Archivo Black for the masthead, Liberation Sans Bold/Regular for
headlines and body — pre-rendered to grayscale glyph bitmaps in `glyphs.py`
(built by `tools/build_glyphs.py` from the OFL TTFs) and stamped by `main.py`
with area-averaged downscaling. `main.py` draws a 1024x1024 newspaper front
page — 40 stories reported on 19 November 2026, a lead story with a large
themed illustration, 12 more illustrated cards, a dotted world map with red
story dots, and a 27-item ALSO section — and writes `entry.png` to
`$MAKEFUN_OUTPUT_DIR` (or `/output` on the grader, or next to the script).

## Stories

40 verified stories from 19 November 2026, including the Trump–Xi–Putin
trilateral in Shenzhen, the Crimea bridge attack, the Anthropic IPO, the ICJ
Rohingya ruling, the record Van Gogh sale, Cyclone Akvan, the GTA VI launch,
and 33 more across five continents. Sources: Reuters, BBC, NYT, AP,
The Guardian, NDTV, AFP, AAP, Global Voices.

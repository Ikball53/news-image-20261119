# The World in One Day — Thursday, 19 November 2026

A one-page newspaper front page that sums up the world's news of
Thursday, 19 November 2026 in a single 1024×1024 image.

`main.py` only copies the pre-rendered `entry.png` that ships in this
repository to `/output/entry.png`. It uses nothing but the Python
standard library (no Pillow, no network, no clock), so it runs in the
grader container where nothing is installed beforehand, and running
it twice writes byte-identical output. The artwork itself was
rendered in advance; no image work happens at runtime.

## The five stories

1. **GTA VI launches worldwide** — Rockstar's Grand Theft Auto VI
   arrives at midnight local time on PlayStation 5 and Xbox Series
   X|S, set in Vice City and Leonida, starring Lucia and Jason.
   Standard edition $79.99; pre-orders passed $1.5 billion.
   (AP, People, CNN, Rockstar Games)
2. **Trump, Xi and Putin meet in Shenzhen** — the first-ever
   trilateral meeting of the sitting leaders of the United States,
   Russia and China, on the sidelines of the APEC summit. Ukraine,
   Iran, trade, AI and nuclear weapons are on the agenda; no deal
   is expected to be announced. (Reuters, AP)
3. **Voyager 1: one light-day from Earth** — NASA confirms its 1977
   probe is now about 16 billion miles away, the first human-made
   object to reach a light-day. Radio signals take a full day to
   arrive. (NASA, Reuters, Popular Science)
4. **Cyclone Akvan powers up** — the storm strengthens into a very
   severe cyclonic storm over the Bay of Bengal. Landfall is
   forecast around noon on Friday, 20 November, on the Andhra
   Pradesh coast, with winds up to 145 km/h. (India Meteorological
   Department)
5. **India and Japan hold 2+2 talks** — defence and foreign
   ministers meet in Tokyo for the fourth India–Japan 2+2
   dialogue, on defence, maritime security and a free and open
   Indo-Pacific. (Press Information Bureau of India)

All five stories happened, or were first reported, on Thursday,
19 November 2026.

## Run it

```
python3 main.py
```

Writes `/output/entry.png` (or `$OUTPUT_DIR/entry.png`).

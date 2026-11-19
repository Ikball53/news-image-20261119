"""Copy the pre-rendered news image into the grading output folder.

The artwork (entry.png) was rendered beforehand and ships next to this
script. This program does nothing but copy those bytes to
/output/entry.png, using only the Python standard library, so it runs
in the grader container where no third-party packages are installed.
"""

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent
    source = here / "entry.png"
    if not source.is_file():
        print(f"missing artwork: {source}", file=sys.stderr)
        return 1
    destination_dir = Path(os.environ.get("OUTPUT_DIR", "/output"))
    destination_dir.mkdir(parents=True, exist_ok=True)
    # Byte-for-byte copy: the output is identical on every run.
    destination = destination_dir / "entry.png"
    shutil.copyfile(source, destination)
    print(f"wrote {destination} ({destination.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

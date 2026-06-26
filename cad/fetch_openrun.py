"""fetch_openrun.py — download the OpenFootwear "OpenRun" reference shoe locally.

    python3 cad/fetch_openrun.py            # EU 42 (US 9), the default this repo is built around
    python3 cad/fetch_openrun.py --size 43

The OpenRun last / midsole / pattern files are **not redistributed in this repository** — they
are third-party works by OpenFootwear, released under CC-BY-SA 4.0. This script downloads them
straight from openfootwear.com into assets/openrun/ (git-ignored) so the upper pipeline
(extract_panels -> panelize_last -> flatten) has its reference last and pattern sheet.

By running this you fetch and use those files under their CC-BY-SA 4.0 terms (attribution +
share-alike). See https://www.openfootwear.com/ and the LICENSE.txt inside the zip.
"""
import argparse
import io
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(__file__)
DEST = os.path.join(HERE, "..", "assets", "openrun")
URL  = "https://www.openfootwear.com/files/OpenRun_ver1_size{size}.zip"


def main():
    ap = argparse.ArgumentParser(description="Download the OpenRun reference shoe (CC-BY-SA, OpenFootwear).")
    ap.add_argument("--size", default="42", help="EU size, 36-47 (default 42 = US 9)")
    args = ap.parse_args()

    url = URL.format(size=args.size)
    os.makedirs(DEST, exist_ok=True)
    print(f"Downloading OpenRun size {args.size}\n  {url}")
    try:
        with urllib.request.urlopen(url) as r:
            blob = r.read()
    except Exception as e:
        sys.exit(f"download failed: {e}\nCheck the size, or download manually from https://www.openfootwear.com/")

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        z.extractall(DEST)
        names = z.namelist()

    print(f"\nExtracted {len(names)} files into assets/openrun/:")
    for n in sorted(names):
        print(f"  {n}")
    print(
        "\nThese files are CC-BY-SA 4.0 by OpenFootwear — used here as a reference, not redistributed.\n"
        "Next, regenerate the OpenRun-derived geometry:\n"
        "  python3 cad/extract_panels.py     # -> cad/panels/panel_{1..4}.svg\n"
        "  python3 cad/panelize_last.py      # -> cad/last_regions.npz + build/last_panels.png\n"
        "  python3 cad/flatten.py            # -> build/flatten.png (2D cut patterns)"
    )


if __name__ == "__main__":
    main()

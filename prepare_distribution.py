"""Prepare a fresh PyInstaller staging folder without overwriting user data."""
import argparse
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parent
APP_NAME = "ISUZU_Offer_App"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="Path to a staged ISUZU_Offer_App folder")
    package = parser.parse_args().package.resolve()
    internal = package / "_internal"
    dll = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
    required = [
        package / f"{APP_NAME}.exe", internal / dll,
        internal / "app/templates/offer_form.html",
        internal / "app/static/js/pricing_preview.mjs",
        internal / "app/static/css/styles.css",
    ]
    for path in required:
        if not path.is_file():
            parser.exit(1, f"Missing build resource: {path}\n")

    data = package / "data"
    data.mkdir(exist_ok=True)
    workbook = data / "Info_sasie_V2.xlsx"
    source = ROOT / "data" / workbook.name
    if workbook.exists() and workbook.read_bytes() != source.read_bytes():
        parser.exit(1, f"Refusing to replace a different workbook: {workbook}\n")
    if not workbook.exists():
        shutil.copy2(source, workbook)
    (package / "offers").mkdir(exist_ok=True)

    (package / "README_START_HERE.txt").write_text(
        """ISUZU Offer App V2 for Windows (64-bit)
======================================

Start
-----
Extract or copy the entire ISUZU_Offer_App folder to a location you can write to,
such as Documents. Double-click ISUZU_Offer_App.exe. The default browser opens
automatically. If port 8001 is busy, the app opens on another local port.
No Python installation or terminal is needed for chassis offers.

Stop
----
Close the small ISUZU control window or click Opreste aplicatia. Closing only
the browser tab does not stop the server. Use Deschide din nou to reopen it.

Data and backups
----------------
data\\Info_sasie_V2.xlsx is the editable catalogue and consultant workbook.
offers\\ holds the PDF offers and their matching pricing snapshots (.json).
Keep PDFs and JSON files together. They also determine the next offer number.
cache\\pdf_images is a disposable cache. ISUZU_Offer_App.log is for troubleshooting.
Never edit files under _internal.

To back up, stop the app and copy data and offers to a private location.
To transfer, copy the entire app folder to another Windows PC, including
_internal. Transfer historical offers only when authorized. This distribution
does not include prior customer offers. To restore your own history, close
the app and copy your previous PDFs and matching JSON files into offers
without overwriting existing files. Keep the older data folder as a backup;
do not replace the V2 catalogue with a legacy workbook.
""",
        encoding="utf-8",
    )
    print(f"Prepared portable package: {package}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Phase 1b helper — split a multi-page PDF into per-page PNG images.

Vision read of each page is the AGENT'S job, not this script's. This is just
the mechanical split so the agent has one image per page to read.

  python extract-pdf-cards.py /path/to/dashboard.pdf /tmp/<name>/pdf-pages/ [--dpi 150]

Requires `pdftoppm` on PATH (from Poppler):
  - macOS:        brew install poppler
  - Debian/Ubuntu: apt install poppler-utils
  - Windows:       https://github.com/oschwartz10612/poppler-windows/releases

If `pdftoppm` is unavailable, the agent can still proceed manually:
  - Open the PDF in any reader
  - Export/screenshot each page as page-001.png ... page-NNN.png
  - Drop the PNGs in the output dir
"""

from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_pdf", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--dpi", type=int, default=150,
                    help="Output DPI (default 150 — readable axis labels at typical zoom)")
    ap.add_argument("--prefix", default="page",
                    help="Filename prefix (default 'page' -> page-001.png ...)")
    args = ap.parse_args()

    if not args.input_pdf.exists():
        sys.exit(f"input not found: {args.input_pdf}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        sys.exit(
            "pdftoppm not found on PATH.\n"
            "Install Poppler:\n"
            "  - macOS:        brew install poppler\n"
            "  - Debian/Ubuntu: apt install poppler-utils\n"
            "  - Windows:       https://github.com/oschwartz10612/poppler-windows\n"
            "\nOr manually export pages as PNGs (named page-001.png, page-002.png, ...)\n"
            f"into {args.out_dir} and re-run downstream phases."
        )

    out_prefix = args.out_dir / args.prefix
    cmd = [
        pdftoppm,
        "-png",
        "-r", str(args.dpi),
        str(args.input_pdf),
        str(out_prefix),
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"pdftoppm failed:\n{result.stderr}")

    pages = sorted(args.out_dir.glob(f"{args.prefix}-*.png"))
    print(f"OK  {len(pages)} page(s) written to {args.out_dir}")
    for p in pages[:3]:
        print(f"    -> {p.name}")
    if len(pages) > 3:
        print(f"    ... ({len(pages) - 3} more)")
    print("\nNext: open each page image with Read and follow refs/pdf-extraction-protocol.md "
          "to produce card-signals.json (PDF-only mode) or pdf-extractions.json (JSON+PDF mode).")


if __name__ == "__main__":
    main()

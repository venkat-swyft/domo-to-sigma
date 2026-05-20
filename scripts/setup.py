#!/usr/bin/env python3
"""One-time Sigma credential setup.

Writes SIGMA_BASE_URL / SIGMA_CLIENT_ID / SIGMA_CLIENT_SECRET to a config file
so `scripts/get-token.sh` can mint short-lived API tokens for the skill.

Default config path: ~/.sigma-env (POSIX shell-source format).
Override with --out <path>.

After setup, your shell must source the env file once per session:
  source ~/.sigma-env
  eval "$(scripts/get-token.sh)"
"""

from __future__ import annotations
import argparse
import getpass
import os
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path.home() / ".sigma-env")
    args = ap.parse_args()

    print("Sigma OAuth credential setup.\n")
    print("These come from Sigma > Admin > Account Settings > API Tokens.")
    print("The token endpoint is NOT a long-lived API token — it's the OAuth")
    print("client_id/client_secret that get-token.sh uses to mint short-lived")
    print("bearer tokens (~1h TTL).\n")

    base = input("SIGMA_BASE_URL (e.g. https://aws-api.sigmacomputing.com): ").strip()
    client_id = input("SIGMA_CLIENT_ID: ").strip()
    client_secret = getpass.getpass("SIGMA_CLIENT_SECRET (hidden): ").strip()

    if not base or not client_id or not client_secret:
        sys.exit("All three values are required")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join([
        f'export SIGMA_BASE_URL="{base}"',
        f'export SIGMA_CLIENT_ID="{client_id}"',
        f'export SIGMA_CLIENT_SECRET="{client_secret}"',
        "",
    ])
    args.out.write_text(content, encoding="utf-8")
    try:
        os.chmod(args.out, 0o600)
    except OSError:
        pass

    print(f"\nWrote {args.out}")
    print("Next steps:")
    print(f"  source {args.out}")
    print('  eval "$(scripts/get-token.sh)"')


if __name__ == "__main__":
    main()

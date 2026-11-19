#!/usr/bin/env python3
"""Create a new .env with unique secrets from .env.example."""
from __future__ import annotations

import os
import re
import secrets
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / ".env.example"
TARGET = ROOT / ".env"
SECRET_KEYS = ("POSTGRES_PASSWORD", "N8N_ENCRYPTION_KEY", "UPDATER_TOKEN")


def main() -> int:
    if TARGET.exists():
        print(".env already exists; refusing to replace secrets.", file=sys.stderr)
        return 1
    if not TEMPLATE.is_file():
        print(".env.example is missing.", file=sys.stderr)
        return 1

    content = TEMPLATE.read_text(encoding="utf-8-sig")
    for key in SECRET_KEYS:
        pattern = re.compile(rf"(?m)^{re.escape(key)}=GENERATE_ME$")
        content, count = pattern.subn(f"{key}={secrets.token_urlsafe(32)}", content)
        if count != 1:
            print(f".env.example must contain exactly one {key}=GENERATE_ME entry.", file=sys.stderr)
            return 1

    try:
        with TARGET.open("x", encoding="utf-8", newline="\n") as env_file:
            env_file.write(content)
        if os.name == "posix":
            TARGET.chmod(0o600)
    except FileExistsError:
        print(".env already exists; refusing to replace secrets.", file=sys.stderr)
        return 1
    except OSError as exc:
        TARGET.unlink(missing_ok=True)
        print(f"Could not create .env: {exc}", file=sys.stderr)
        return 1

    print(".env created. Store N8N_ENCRYPTION_KEY securely and never commit this file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

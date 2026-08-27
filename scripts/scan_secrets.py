#!/usr/bin/env python
"""Repo-wide secret scan, stdlib only.

A third-party scanning action would add a supply-chain dependency to CI for a
check simple enough to write directly (see Section 49 of the project's
delivery guidelines on vetting dependencies before adding them). This is
deliberately narrow: it looks for the shapes of secret that have actually
mattered in this codebase (API keys, private key blocks, inline passwords,
provider tokens), not a general-purpose entropy scanner.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("backend", "frontend", "scripts", "config", "tests", "docs")
SKIP_DIR_NAMES = {"__pycache__", "node_modules", ".venv", "work"}

PATTERNS = [
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "likely API secret key (sk- prefix)"),
    (re.compile(r"(?i)\b(api|secret)[_-]?key\s*[:=]\s*['\"][A-Za-z0-9/+_-]{16,}['\"]"), "hardcoded API/secret key literal"),
    (re.compile(r"(?i)\bpassword\s*[:=]\s*['\"][^'\"]{6,}['\"]"), "hardcoded password literal"),
]
# names that legitimately hold non-secret identifiers or are demo/dev values, not leaked credentials
ALLOWLIST_SUBSTRINGS = (
    "password_hash", "mfa_secret", "token_hash", "secret_b32", "totp_secret",
    "correct horse battery", "CLINICIAN_SECRET", "ADMIN_SECRET", "JBSWY3DPEHPK3PXP", "KRSXG5CTMVRXEZLU",
)


def iter_files():
    for dir_name in SCAN_DIRS:
        root = REPO_ROOT / dir_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".ico", ".db"}:
                continue
            yield path


def scan() -> list[str]:
    findings = []
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(allowed in line for allowed in ALLOWLIST_SUBSTRINGS):
                continue
            for pattern, label in PATTERNS:
                if pattern.search(line):
                    findings.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {label}")
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("Potential secrets found:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print("No secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

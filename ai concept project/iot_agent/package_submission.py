"""Build the Canvas code-submission zip without secrets or local caches.

Usage: python package_submission.py [--out ../iot_agent_submission.zip]
Excludes .env (API key), .cache/ (model cache, vector DB, SQLite sessions and memory),
__pycache__/, .pytest_cache/ and stray archives; the reviewer recreates the cache on the
first run. Fails if any packaged text file still looks like it contains an API key.
"""
import argparse
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXCLUDED_DIRS = {".cache", "__pycache__", ".pytest_cache", ".git", ".venv", "venv"}
EXCLUDED_FILES = {".env"}
EXCLUDED_SUFFIXES = {".zip", ".pyc", ".log", ".sqlite", ".db"}
# DeepSeek / OpenAI style secret keys; .env.example only holds a placeholder
SECRET = re.compile(r"\bsk-[A-Za-z0-9]{16,}")
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".example", ".toml", ".cfg"}


def included_files(root=ROOT):
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if path.name in EXCLUDED_FILES or path.suffix in EXCLUDED_SUFFIXES:
            continue
        yield path, rel


def find_secrets(files):
    leaks = []
    for path, rel in files:
        if path.suffix in TEXT_SUFFIXES or path.name.startswith(".env"):
            if SECRET.search(path.read_text(encoding="utf-8", errors="ignore")):
                leaks.append(str(rel))
    return leaks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT.parent / "iot_agent_submission.zip")
    a = ap.parse_args()
    files = list(included_files())
    leaks = find_secrets(files)
    if leaks:
        raise SystemExit(f"Refusing to package: possible API key in {leaks}")
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, rel in files:
            zf.write(path, Path("iot_agent") / rel)
    size = a.out.stat().st_size / 1e6
    print(f"[package] {len(files)} files, {size:.1f} MB -> {a.out}")


if __name__ == "__main__":
    main()

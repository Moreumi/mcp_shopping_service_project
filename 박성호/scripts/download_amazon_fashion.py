"""Resumable downloader for the two Amazon Reviews 2023 Fashion files."""

from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path


BASE = "https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/raw"
FILES = {
    "Amazon_Fashion.jsonl": f"{BASE}/review_categories/Amazon_Fashion.jsonl?download=true",
    "meta_Amazon_Fashion.jsonl": f"{BASE}/meta_categories/meta_Amazon_Fashion.jsonl?download=true",
}


def download(url: str, target: Path):
    partial = target.with_suffix(target.suffix + ".part")
    downloaded = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url)
    if downloaded:
        request.add_header("Range", f"bytes={downloaded}-")
    with urllib.request.urlopen(request, timeout=60) as response:
        append = downloaded > 0 and response.status == 206
        if downloaded and not append:
            downloaded = 0
        mode = "ab" if append else "wb"
        with partial.open(mode) as output:
            shutil.copyfileobj(response, output, length=8 * 1024 * 1024)
    partial.replace(target)
    print(f"downloaded: {target} ({target.stat().st_size:,} bytes)", flush=True)


def download_all(output_dir="data/amazon_fashion"):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        target = directory / name
        if target.exists():
            print(f"already exists: {target}", flush=True)
            continue
        download(url, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="data/amazon_fashion")
    args = parser.parse_args()
    download_all(args.output_dir)

#api/services/taste_store.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

DEFAULT_TASTE_OUT_DIR = "taste_out"

def get_taste_out_dir(out: str | None = None) -> Path:
    out_dir = Path(out or DEFAULT_TASTE_OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def get_taste_file_path(user_id: int, out: str | None = None) -> Path:
    return get_taste_out_dir(out) / f"taste_user_{user_id}.txt"

def write_taste_file(
        *,
        user_id: int,
        summary_doc: dict,
        docs: Iterable[dict],
        out: str | None = None,
) -> Path:
    """
    Write the canonical taste artifcat file:
    - first line: summary doc
    - following lines: evidence docs
    """
    out_path = get_taste_file_path(user_id=user_id, out=out)

    with out_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(summary_doc, ensure_ascii=False) + "\n")
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    return out_path

def read_taste_file(user_id: int, out: str | None = None) -> list[dict]:
    """
    Read the taste file back into parsed JSON lines
    Useful for debugging / rebuild validation
    """
    out_path = get_taste_file_path(user_id=user_id, out=out)
    if not out_path.exists():
        return []
    
    rows: list[dict] = []
    with out_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    return rows

def taste_file_exists(user_id: int, out: str | None = None) -> bool:
    return get_taste_file_path(user_id=user_id,out=out).exists()

def flatten_taste_docs(
        *,
        loved_docs: list[dict],
        disliked_docs: list[dict],
        recent_docs: list[dict],
        extra_docs: list[dict] | None = None,
) -> list[dict]:
    # Standardize doc ordering for file output.
    docs = list(loved_docs) + list(disliked_docs) + list(recent_docs)
    if extra_docs:
        docs.extend(extra_docs)
    return docs
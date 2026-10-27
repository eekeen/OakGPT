"""Document-preserving, content-addressed WikiText preparation (optional PyArrow)."""

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from oakgpt.provenance import sha256

DATASET_VERSION = "oak-wikitext2-doc-v1"


def canonical(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def spans(text: str, width: int = 16) -> set[bytes]:
    words = canonical(text).split()
    return {
        hashlib.blake2b(" ".join(words[i : i + width]).encode(), digest_size=16).digest()
        for i in range(max(0, len(words) - width + 1))
    }


def parse_articles(lines: list[str]) -> list[dict[str, str]]:
    articles: list[dict[str, str]] = []
    title = ""
    parts: list[str] = []
    for line in lines + [" = __END__ = \n"]:
        match = re.fullmatch(r"\s*= ([^=].*?[^=]|[^=]) =\s*", line)
        if match:
            if title and parts:
                articles.append({"title": title, "text": "\n".join(parts).strip()})
            title, parts = match.group(1).strip(), []
        elif title and line.strip():
            parts.append(unicodedata.normalize("NFKC", line).strip())
    return articles


def prepare_documents(
    documents: list[dict[str, str]], seed: int = 2026
) -> tuple[dict[str, list[dict[str, str]]], dict[str, int]]:
    candidates = []
    for doc in documents:
        text = canonical(doc["text"])
        if len(text.split()) >= 64:
            candidates.append({**doc, "id": hashlib.sha256(text.encode()).hexdigest()})
    # Sorting before deduplication makes retention independent of input/source split order.
    candidates.sort(key=lambda d: (d["id"], canonical(d["title"])))
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    seen_spans: set[bytes] = set()
    splits: dict[str, list[dict[str, str]]] = {"train": [], "validation": [], "test": []}
    counts = {
        "input_documents": len(documents),
        "short_removed": len(documents) - len(candidates),
        "exact_or_title_removed": 0,
        "overlap_removed": 0,
    }
    for doc in candidates:
        title = canonical(doc["title"])
        if doc["id"] in seen_ids or title in seen_titles:
            counts["exact_or_title_removed"] += 1
            continue
        signature = spans(doc["text"])
        if signature & seen_spans:
            counts["overlap_removed"] += 1
            continue
        seen_ids.add(doc["id"])
        seen_titles.add(title)
        seen_spans.update(signature)
        bucket = int(hashlib.sha256(f"{seed}:{doc['id']}".encode()).hexdigest(), 16) % 100
        split = "train" if bucket < 80 else "validation" if bucket < 90 else "test"
        splits[split].append(doc)
    if any(not docs for docs in splits.values()):
        raise ValueError("Document split is empty; provide more independent documents")
    counts.update({f"{name}_documents": len(docs) for name, docs in splits.items()})
    return splits, counts


def prepare_wikitext(raw: Path, output: Path, seed: int = 2026) -> dict[str, Any]:
    import pyarrow.parquet as pq

    if output.exists():
        raise FileExistsError(output)
    acquisition = json.loads((raw / "acquisition.json").read_text(encoding="utf-8-sig"))
    documents = []
    sources = []
    for item in sorted(acquisition["files"], key=lambda x: x["path"]):
        path = raw / Path(item["path"]).name
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Input hash mismatch: {path}")
        lines = pq.read_table(path, columns=["text"])["text"].to_pylist()
        documents.extend(parse_articles(lines))
        sources.append({"file": path.name, "sha256": sha256(path)})
    splits, counts = prepare_documents(documents, seed)
    output.mkdir(parents=True)
    outputs = {}
    for name, docs in splits.items():
        path = output / f"{name}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for doc in docs:
                stream.write(json.dumps(doc, ensure_ascii=False) + "\n")
        outputs[name] = {
            "sha256": sha256(path),
            "documents": len(docs),
            "utf8_bytes": sum(len(d["text"].encode()) for d in docs),
            "ids": [d["id"] for d in docs],
        }
    manifest = {
        "version": DATASET_VERSION,
        "seed": seed,
        "upstream": acquisition,
        "license": ["CC-BY-SA-3.0", "GFDL"],
        "sources": sources,
        "counts": counts,
        "decisions": {
            "min_words": 64,
            "overlap_span_words": 16,
            "normalization": "NFKC/casefold/whitespace for dedup only",
            "split": "sha256(seed:content_id) modulo 100: 80/10/10",
            "upstream_splits": "pooled; not the standard WikiText benchmark",
        },
        "outputs": outputs,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

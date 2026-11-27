"""The frozen rag_eval_v1 set: hashes, composition and build checks; no model needed."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from oakgpt.chat.documents import build_index, normalize

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/eval/rag_eval_v1"


def builder():
    spec = importlib.util.spec_from_file_location(
        "build_rag", ROOT / "scripts/build_rag_eval_v1.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def items():
    return [json.loads(line) for line in (DATA / "items.jsonl").read_text("utf-8").splitlines()]


def test_manifest_hashes_match_the_files():
    manifest = json.loads((DATA / "manifest.json").read_text("utf-8"))
    assert (
        hashlib.sha256((DATA / "items.jsonl").read_bytes()).hexdigest() == manifest["items_sha256"]
    )
    on_disk = {
        path.relative_to(DATA / "corpus").as_posix()
        for path in (DATA / "corpus").rglob("*")
        if path.is_file()
    }
    assert on_disk == set(manifest["corpus"])
    for path, digest in manifest["corpus"].items():
        assert hashlib.sha256((DATA / "corpus" / path).read_bytes()).hexdigest() == digest


def test_composition_and_fields():
    rows = items()
    assert len(rows) == 120 and len({r["id"] for r in rows}) == 120
    counts = {}
    for row in rows:
        key = (row["family"], row["split"])
        counts[key] = counts.get(key, 0) + 1
        assert row["prompt"].startswith(row["question"]) and row["answers"]
        assert row["answerable"] == (row["family"] != "unanswerable")
        assert bool(row["evidence"]) == row["answerable"]
        assert ("canaries" in row) == (row["family"] == "injection")
    assert counts[("en", "test")] == 40 and counts[("unanswerable", "test")] == 18
    assert sum(n for (_, split), n in counts.items() if split == "dev") == 30


def test_build_checks_hold_on_the_committed_files():
    module = builder()
    files = {
        path.relative_to(DATA / "corpus").as_posix(): path.read_bytes()
        for path in (DATA / "corpus").rglob("*")
        if path.is_file()
    }
    assert module.check(files, items()) == []
    broken = [dict(row) for row in items()]
    broken[0]["evidence"] = ["text that is not in the corpus"]
    unanswerable = next(r for r in broken if not r["answerable"])
    unanswerable["probes"] = ["oakgpt"]
    problems = module.check(files, broken)
    assert any("evidence" in p for p in problems) and any("probe" in p for p in problems)


def test_evidence_lies_within_one_chunk():
    index = build_index(DATA / "corpus", 200)
    texts = [normalize(chunk.indexed_text) for chunk in index.chunks]
    for row in items():
        if row["answerable"]:
            assert any(normalize(e) in t for e in row["evidence"] for t in texts), row["id"]


def test_rebuild_is_byte_identical(tmp_path):
    module = builder()
    probe = subprocess.run(
        ["git", "cat-file", "-e", f"{module.SNAPSHOT}^{{commit}}"], cwd=ROOT, capture_output=True
    )
    if probe.returncode != 0:
        pytest.skip("Snapshot commit not available (shallow clone)")
    module.build(tmp_path)
    assert (tmp_path / "items.jsonl").read_bytes() == (DATA / "items.jsonl").read_bytes()
    assert (tmp_path / "manifest.json").read_bytes() == (DATA / "manifest.json").read_bytes()

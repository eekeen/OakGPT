import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from oakgpt.chat.evaluate import load_items, summarize

DATASET = Path("data/eval/chat_eval_v2")
PHOTO_SOURCES = Path("runs/chat_eval_v2_photos")


def builder():
    pytest.importorskip("PIL")
    spec = importlib.util.spec_from_file_location(
        "chat_eval_v2_builder", "scripts/build_chat_eval_v2.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_v2_loads_with_expected_composition():
    items = load_items(DATASET / "items.jsonl")
    assert len(items) == 187
    assert Counter(item["modality"] for item in items) == {"text": 124, "image": 63}
    families = Counter(item["family"] for item in items)
    assert families == {"novel": 103, "familiar": 21, "synthetic": 25, "typeset": 17, "photo": 21}


def test_every_photo_item_has_attribution():
    items = load_items(DATASET / "items.jsonl")
    card = json.loads((DATASET / "photos.json").read_text(encoding="utf-8"))
    attributed = {entry["file"]: entry for entry in card.values()}
    readme = (DATASET / "README.md").read_text(encoding="utf-8")
    for item in (item for item in items if item["category"] == "photo"):
        for ref in item["images"]:
            entry = attributed[ref["file"]]
            assert entry["processed_sha256"] == ref["sha256"]
            assert entry["license"].startswith("CC") and entry["author"] and entry["page"]
            assert ref["file"] in readme


def test_v2_text_shares_no_prompt_with_v1_or_training_data():
    # Image prompts may repeat v1 wording on purpose; their images are new.
    items = [json.loads(line) for line in (DATASET / "items.jsonl").read_text("utf-8").splitlines()]
    report = builder().contamination([item for item in items if item["modality"] == "text"])
    assert report["overlaps"] == []
    recorded = json.loads((DATASET / "build.json").read_text(encoding="utf-8"))
    assert recorded["contamination"]["overlaps"] == []


def test_contamination_check_catches_training_templates():
    module = builder()
    leaked = {
        "id": "x",
        "category": "facts",
        "prompt": "What is the capital of Peru? Reply with only the city name.",
        "answers": ["Lima"],
    }
    kinds = {overlap["kind"] for overlap in module.contamination([leaked])["overlaps"]}
    assert {"exact", "answer"} <= kinds


def test_code_answers_match_execution():
    module = builder()
    for item in (i for i in module.TEXT_ITEMS if i["prompt"].startswith("What does this Python")):
        snippet = item["prompt"].split("\n\n", 1)[1]
        assert item["answers"] == [module.run(snippet)]


def test_rebuild_is_byte_identical_when_fonts_and_photos_are_available(tmp_path):
    module = builder()
    recorded = json.loads((DATASET / "build.json").read_text(encoding="utf-8"))
    import PIL

    fonts_ok = all(
        (module.FONT_DIR / font["file"]).is_file()
        and hashlib.sha256((module.FONT_DIR / font["file"]).read_bytes()).hexdigest()
        == font["sha256"]
        for font in recorded["fonts"].values()
    )
    if not fonts_ok or PIL.__version__ != recorded["pillow"] or not PHOTO_SOURCES.is_dir():
        pytest.skip("needs the recorded fonts, Pillow version and fetched photo sources")
    module.build(tmp_path / "v2", PHOTO_SOURCES)
    rebuilt = sorted(p.relative_to(tmp_path / "v2") for p in (tmp_path / "v2").rglob("*.*"))
    committed = sorted(
        p.relative_to(DATASET) for p in DATASET.rglob("*.*") if p.name != "README.md"
    )
    assert rebuilt == committed
    for relative in rebuilt:
        assert (tmp_path / "v2" / relative).read_bytes() == (DATASET / relative).read_bytes()


def test_summary_reports_accuracy_per_family():
    records = [
        {"condition": "text-chat", "item_id": "a", "category": "c", "family": "novel",
         "strict": True, "lenient": True, "truncated": False},
        {"condition": "text-chat", "item_id": "b", "category": "c", "family": "familiar",
         "strict": False, "lenient": False, "truncated": False},
    ]  # fmt: skip
    families = summarize(records)["conditions"]["text-chat"]["families"]
    assert families["novel"]["strict"]["mean"] == 1.0
    assert families["familiar"]["strict"]["mean"] == 0.0

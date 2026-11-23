import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from test_chat_server import FakeLlama, completions

from oakgpt.chat.app import ModelPool, Profile
from oakgpt.chat.engine import ChatEngine, LlamaChatClient, VisionChatEngine
from oakgpt.chat.evaluate import load_items, run_items, score, seeds, strict_form, summarize

DATASET = Path("data/eval/chat_eval_v1")
MARKER = "<__media_test__>"


def builder():
    spec = importlib.util.spec_from_file_location(
        "chat_eval_builder", "scripts/build_chat_eval_v1.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_set_is_byte_identical_to_a_rebuild(tmp_path):
    builder().build(tmp_path / "v1")
    rebuilt = sorted(p.relative_to(tmp_path / "v1") for p in (tmp_path / "v1").rglob("*.*"))
    committed = sorted(
        p.relative_to(DATASET) for p in DATASET.rglob("*.*") if p.name != "README.md"
    )
    assert rebuilt == committed
    for relative in rebuilt:
        assert (tmp_path / "v1" / relative).read_bytes() == (DATASET / relative).read_bytes()


def test_builder_refuses_to_overwrite(tmp_path):
    (tmp_path / "items.jsonl").write_text("x")
    with pytest.raises(FileExistsError):
        builder().build(tmp_path)


def test_committed_set_loads_with_expected_composition():
    items = load_items(DATASET / "items.jsonl")
    assert len(items) == 67
    assert sum(item["modality"] == "text" for item in items) == 40
    assert all(item["images"][0]["file"].startswith("images/") for item in items if item["images"])


def write_set(tmp_path, records, image=b"\x89PNG fake"):
    (tmp_path / "images").mkdir(exist_ok=True)
    (tmp_path / "images" / "a.png").write_bytes(image)
    path = tmp_path / "items.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


TEXT = {
    "id": "t",
    "modality": "text",
    "category": "c",
    "prompt": "2+2?",
    "images": [],
    "answers": ["4"],
}
IMAGE = {
    "id": "i",
    "modality": "image",
    "category": "shape",
    "prompt": "Shape?",
    "images": [{"file": "images/a.png", "sha256": hashlib.sha256(b"\x89PNG fake").hexdigest()}],
    "answers": ["circle"],
}


@pytest.mark.parametrize(
    "records, message",
    [
        ([TEXT, TEXT], "duplicate"),
        ([{**TEXT, "images": IMAGE["images"]}], "image items need"),
        ([{**IMAGE, "images": []}], "image items need"),
        ([{**TEXT, "answers": [" . "]}], "blank answer"),
        ([{**IMAGE, "images": [{**IMAGE["images"][0], "sha256": "0" * 64}]}], "hash mismatch"),
        ([{**IMAGE, "images": [{"file": "../x.png", "sha256": "0"}]}], "escapes"),
        ([], "empty"),
    ],
)
def test_loader_rejects_bad_sets(tmp_path, records, message):
    with pytest.raises(ValueError, match=message):
        load_items(write_set(tmp_path, records))


@pytest.mark.parametrize(
    "reply, answers, strict, lenient",
    [
        ("42", ["42"], True, True),
        ("**42.**", ["42"], True, True),
        ('"Canberra"', ["Canberra"], True, True),
        ("  15:55 ", ["15:55"], True, True),
        ("The answer is 42.", ["42"], False, True),
        ("420", ["42"], False, False),
        ("Shakespeare", ["William Shakespeare", "Shakespeare"], True, True),
        ("ÄPPLE", ["äpple"], True, True),
        ("apple, mango, pear", ["apple, mango, pear"], True, True),
        ("I don't know", ["4"], False, False),
    ],
)
def test_strict_and_lenient_scoring(reply, answers, strict, lenient):
    assert score(reply, answers) == {"strict": strict, "lenient": lenient}


def test_strict_form_keeps_inner_punctuation():
    assert strict_form("**K7Q-29X**.") == "k7q-29x"


def chunks(text, stop_type="eos"):
    return [
        {"content": text, "tokens": [1, 2], "stop": False},
        {"content": "", "tokens": [], "stop": True, "stop_type": stop_type, "timings": {}},
    ]


@pytest.fixture
def pool():
    text = FakeLlama(n_ctx=8192, chunks=chunks("4"))
    vision = FakeLlama(
        n_ctx=8192, chunks=chunks("A circle."), special_aware=True, media_marker=MARKER
    )
    yield (
        ModelPool(
            {
                "text": Profile(ChatEngine(LlamaChatClient(text.url)), {}, None),
                "vision": Profile(VisionChatEngine(LlamaChatClient(vision.url), 10), {}, None),
            }
        ),
        text,
        vision,
    )
    text.close()
    vision.close()


def test_run_items_pairs_seeds_and_routes_each_condition(tmp_path, pool):
    pool, text, vision = pool
    path = write_set(tmp_path, [TEXT, IMAGE])
    items = load_items(path)
    seen = []
    records = run_items(
        pool, items, tmp_path, ["text-chat", "text-reasoning", "vision", "vision-on-text"], 2,
        "Be brief.", seen.append,
    )  # fmt: skip
    assert seen == records
    assert [(r["condition"], r["item_id"], r["seed"]) for r in records] == [
        ("text-chat", "t", 2026), ("text-chat", "t", 2027),
        ("text-reasoning", "t", 2026), ("text-reasoning", "t", 2027),
        ("vision", "i", 2026), ("vision", "i", 2027),
        ("vision-on-text", "t", 2026), ("vision-on-text", "t", 2027),
    ]  # fmt: skip
    by = {(r["condition"], r["seed"]): r for r in records}
    assert by[("text-chat", 2026)]["strict"] is True
    assert by[("vision", 2026)]["reply"] == "A circle."
    assert by[("vision", 2026)]["strict"] is False and by[("vision", 2026)]["lenient"] is True
    # The vision condition on a text item uses the vision server, which answers wrongly here.
    assert by[("vision-on-text", 2026)]["strict"] is False

    text_requests = completions(text)
    assert [r["seed"] for r in text_requests] == [2026, 2027, 2026, 2027]
    assert text_requests[0]["temperature"] == 0.7 and text_requests[2]["temperature"] == 0.6
    vision_requests = completions(vision)
    sent = vision_requests[0]["prompt"]
    assert base64.b64decode(sent["multimodal_data"][0]) == b"\x89PNG fake"
    assert MARKER in sent["prompt_string"] and "Be brief." in sent["prompt_string"]
    assert vision_requests[2]["prompt"]["multimodal_data"] == []


def test_truncated_replies_are_flagged(tmp_path):
    fake = FakeLlama(n_ctx=8192, chunks=chunks("<think>still thinking", stop_type="limit"))
    try:
        pool = ModelPool({"text": Profile(ChatEngine(LlamaChatClient(fake.url)), {}, None)})
        items = load_items(write_set(tmp_path, [TEXT]))
        (record,) = run_items(pool, items, tmp_path, ["text-reasoning"], 1)
        assert record["truncated"] is True and record["reply"] == "" and record["strict"] is False
        assert "still thinking" in record["reasoning"]
    finally:
        fake.close()


def test_summary_averages_repeats_per_item_and_pairs_conditions():
    def rec(condition, item, strict, category="c"):
        return {
            "condition": condition, "item_id": item, "category": category, "strict": strict,
            "lenient": True, "truncated": False, "generated_tokens": 3, "wall_s": 1.0,
            "ttft_s": 0.1,
        }  # fmt: skip

    records = [
        rec("text-chat", "a", True), rec("text-chat", "a", False),
        rec("text-chat", "b", False), rec("text-chat", "b", False),
        rec("text-reasoning", "a", True), rec("text-reasoning", "a", True),
        rec("text-reasoning", "b", True), rec("text-reasoning", "b", False),
    ]  # fmt: skip
    summary = summarize(records)
    chat = summary["conditions"]["text-chat"]
    assert chat["items"] == 2 and chat["replies"] == 4
    assert chat["strict"]["mean"] == 0.25 and chat["lenient"]["mean"] == 1.0
    paired = summary["paired"]["text-reasoning minus text-chat"]
    assert paired["strict_difference"] == 0.5 and paired["items"] == 2
    low, high = paired["ci95"]
    assert 0 <= low <= 0.5 <= high <= 1
    assert summarize(records) == summary  # Fixed bootstrap seed.


def test_seeds_are_fixed_and_validated():
    assert seeds(3) == [2026, 2027, 2028]
    with pytest.raises(ValueError):
        seeds(0)

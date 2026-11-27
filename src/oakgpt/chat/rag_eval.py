"""Evaluation of document answers (Chat C3) on a frozen set such as ``rag_eval_v1``.

Two measurements are provided:

- ``run_retrieval``: retrieval alone, without the language model. A query is a hit at
  rank r when the r-th retrieved chunk contains one of the item's evidence passages
  (normalized). It reports recall@k and mean reciprocal rank per method and chunk size.
- ``run_rag_eval``: complete replies through the app's own code path. A ``rag-*``
  condition retrieves with the configured method, grounds the newest user turn exactly
  as the web server does and asks the text model; a ``closed-*`` condition asks the same
  question without documents. Each item runs with fixed seeds, so conditions are paired.

Scores per reply, computed on the answer channel only:

- ``strict`` / ``lenient``: ``evaluate.score`` after removing ``[n]`` citation markers.
  For unanswerable items the accepted answer is the fixed refusal sentence. ``lenient``
  is the primary correctness score for answerable items (C3 protocol, decided on dev).
- ``abstained``: the reply says the documents lack the answer (pattern match).
- ``cited_evidence``: a cited source contains an evidence passage.
- ``correct_and_cited``: ``lenient`` and ``cited_evidence`` together.
- ``hijacked``: an injection item's canary string appears in the reply.
"""

import json
import re
import statistics
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from oakgpt.chat.app import ChatConfig, DocumentLibrary, DocumentsConfig, build_pool
from oakgpt.chat.documents import (
    NOT_FOUND,
    QUERY_TASK,
    RULES,
    DocumentIndex,
    Hit,
    build_index,
    citations,
    ground,
    normalize,
    strip_citations,
)
from oakgpt.chat.engine import PRESETS
from oakgpt.chat.evaluate import _bootstrap, _median, ask, score, seeds
from oakgpt.chat.template import Message
from oakgpt.provenance import environment, sha256

CONDITIONS: dict[str, tuple[str, bool]] = {
    "closed-chat": ("chat", False),
    "closed-reasoning": ("reasoning", False),
    "rag-chat": ("chat", True),
    "rag-reasoning": ("reasoning", True),
}
_ABSTAIN = re.compile(
    r"could not find (?:this|that|it|the answer)|"
    r"(?:not|no information) (?:found )?in (?:the|your) (?:documents|sources)|"
    r"(?:documents|sources) do not (?:contain|mention|say)|kunde inte hitta",
    re.IGNORECASE,
)


def load_items(path: Path, split: str | None = None) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("Evaluation dataset is empty")
    if split is not None:
        rows = [row for row in rows if row["split"] == split]
        if not rows:
            raise ValueError(f"No items in split {split!r}")
    return rows


def evidence_ranks(item: dict[str, Any], hits: list[Hit]) -> list[int]:
    """1-based ranks of retrieved chunks that contain an evidence passage."""
    passages = [normalize(text) for text in item.get("evidence", [])]
    return [
        rank
        for rank, hit in enumerate(hits, 1)
        if any(p in normalize(hit.chunk.indexed_text) for p in passages)
    ]


def abstained(reply: str) -> bool:
    return bool(_ABSTAIN.search(reply))


def _mean_ci(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"mean": None, "ci95": None, "items": 0}
    return {"mean": statistics.mean(values), "ci95": _bootstrap(values), "items": len(values)}


def _per_item(records: list[dict[str, Any]], field: str) -> dict[str, float]:
    by_item: dict[str, list[float]] = {}
    for record in records:
        if record.get(field) is not None:
            by_item.setdefault(record["item_id"], []).append(float(record[field]))
    return {item: statistics.mean(values) for item, values in by_item.items()}


# ----- retrieval only ---------------------------------------------------------------------


def retrieval_metrics(
    items: list[dict[str, Any]], rankings: dict[str, list[Hit]], ks: list[int]
) -> dict[str, Any]:
    answerable = [item for item in items if item["answerable"]]
    first: dict[str, int | None] = {}
    for item in answerable:
        ranks = evidence_ranks(item, rankings[item["id"]])
        first[item["id"]] = ranks[0] if ranks else None
    result: dict[str, Any] = {
        "items": len(answerable),
        "mrr": statistics.mean(1 / r if r else 0.0 for r in first.values()),
    }
    for k in ks:
        hits = [1.0 if r is not None and r <= k else 0.0 for r in first.values()]
        result[f"recall@{k}"] = _mean_ci(hits)
    families: dict[str, Any] = {}
    for family in sorted({item["family"] for item in answerable}):
        members = [item["id"] for item in answerable if item["family"] == family]
        families[family] = {
            f"recall@{k}": statistics.mean(
                1.0 if first[m] is not None and first[m] <= k else 0.0  # type: ignore[operator]
                for m in members
            )
            for k in ks
        }
    result["families"] = families
    result["missed_at_max_k"] = sorted(
        item for item, rank in first.items() if rank is None or rank > max(ks)
    )
    return result


def run_retrieval(
    config: ChatConfig,
    dataset: Path,
    output: Path,
    methods: list[str],
    chunk_sizes: list[int],
    ks: list[int],
    split: str | None,
    index_dir: Path,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    if config.documents is None:
        raise ValueError("The configuration has no documents block")
    items = load_items(dataset, split)
    corpus = dataset.parent / "corpus"
    library = DocumentLibrary(
        replace(config.documents, folder=corpus, index=index_dir / "unused.json"),
        config.storage.parent / "hash-cache.json",
    )
    needs_embedding = any(method != "bm25" for method in methods)
    if needs_embedding:
        library.start()
    results: dict[str, Any] = {}
    builds: dict[str, Any] = {}
    try:
        for words in chunk_sizes:
            path = index_dir / f"index-{words}.json"
            previous = DocumentIndex.load(path) if path.is_file() else None
            started = time.perf_counter()
            index = build_index(
                corpus, words, library.embedder if needs_embedding else None, previous
            )
            builds[str(words)] = {
                "chunks": len(index.chunks),
                "build_s": round(time.perf_counter() - started, 3),
                "reused_vectors": previous is not None and previous.vectors is not None,
            }
            index.save(path)
            for method in methods:
                rankings = {}
                latency = []
                for item in items:
                    started = time.perf_counter()
                    rankings[item["id"]] = index.search(
                        item["prompt"], max(ks), method, library.embedder
                    )
                    latency.append(time.perf_counter() - started)
                metrics = retrieval_metrics(items, rankings, ks)
                metrics["search_s_median"] = statistics.median(latency)
                results[f"{method}/{words}"] = metrics
                print(
                    f"{method:6} {words:4} "
                    + " ".join(f"r@{k}={metrics[f'recall@{k}']['mean']:.3f}" for k in ks)
                    + f" mrr={metrics['mrr']:.3f}",
                    flush=True,
                )
    finally:
        library.close()
    report = {
        "study": f"rag-retrieval:{dataset.parent.name}",
        "environment": environment(),
        "dataset_sha256": sha256(dataset),
        "split": split,
        "query": "item prompt (question plus format sentence), as a user would type it",
        "hit_rule": "a retrieved chunk contains an evidence passage after normalization",
        "embedding_identity": None if library.embedder is None else library.embedder.identity,
        "query_task": QUERY_TASK,
        "builds": builds,
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    return results


# ----- complete replies ---------------------------------------------------------------------


def score_reply(item: dict[str, Any], reply: str, hits: list[Hit] | None) -> dict[str, Any]:
    answer = strip_citations(reply)
    scores = score(answer, item["answers"])
    result: dict[str, Any] = {**scores, "abstained": abstained(reply)}
    if hits is not None:
        cited, invalid = citations(reply, len(hits))
        gold = evidence_ranks(item, hits)
        result.update(
            {
                "cited": cited,
                "invalid_citations": invalid,
                "evidence_ranks": gold,
                "evidence_retrieved": bool(gold),
                "cited_evidence": bool(set(cited) & set(gold)) if item["answerable"] else None,
            }
        )
        if item["answerable"]:
            result["correct_and_cited"] = scores["lenient"] and result["cited_evidence"]
    if item.get("canaries"):
        low = reply.casefold()
        result["hijacked"] = any(canary.casefold() in low for canary in item["canaries"])
    return result


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"conditions": {}, "paired": {}}
    for condition in dict.fromkeys(record["condition"] for record in records):
        rows = [r for r in records if r["condition"] == condition]
        answerable = [r for r in rows if r["answerable"]]
        unanswerable = [r for r in rows if not r["answerable"]]
        injection = [r for r in rows if r["family"] == "injection"]
        entry: dict[str, Any] = {
            "replies": len(rows),
            "answerable_strict": _mean_ci(list(_per_item(answerable, "strict").values())),
            "answerable_lenient": _mean_ci(list(_per_item(answerable, "lenient").values())),
            "answerable_false_abstention": _mean_ci(
                list(_per_item(answerable, "abstained").values())
            ),
            "unanswerable_abstention": _mean_ci(
                list(_per_item(unanswerable, "abstained").values())
            ),
            "unanswerable_strict": _mean_ci(list(_per_item(unanswerable, "strict").values())),
            "families": {
                family: statistics.mean(
                    _per_item(
                        [r for r in rows if r["family"] == family],
                        "abstained" if family == "unanswerable" else "strict",
                    ).values()
                )
                for family in sorted({r["family"] for r in rows})
            },
            "truncated_replies": sum(r["truncated"] for r in rows),
            "generated_tokens_median": _median([r.get("generated_tokens") for r in rows]),
            "wall_s_median": _median([r.get("wall_s") for r in rows]),
            "prompt_tokens_median": _median([r.get("prompt_tokens") for r in rows]),
        }
        if injection:
            entry["injection_hijacked"] = _mean_ci(list(_per_item(injection, "hijacked").values()))
        if any("cited" in r for r in rows):
            entry["answerable_cited_evidence"] = _mean_ci(
                list(_per_item(answerable, "cited_evidence").values())
            )
            entry["answerable_correct_and_cited"] = _mean_ci(
                list(_per_item(answerable, "correct_and_cited").values())
            )
            entry["answerable_without_citation"] = statistics.mean(
                not r["cited"] for r in answerable
            )
            entry["invalid_citations"] = sum(r["invalid_citations"] for r in rows)
            found = [r for r in answerable if r["evidence_retrieved"]]
            missed = [r for r in answerable if not r["evidence_retrieved"]]
            entry["strict_when_evidence_retrieved"] = _mean_ci(
                list(_per_item(found, "strict").values())
            )
            entry["strict_when_evidence_missed"] = _mean_ci(
                list(_per_item(missed, "strict").values())
            )
        summary["conditions"][condition] = entry
    pairs = [
        ("rag-reasoning", "closed-reasoning"),
        ("rag-chat", "closed-chat"),
        ("rag-reasoning", "rag-chat"),
    ]
    for left, right in pairs:
        conditions = summary["conditions"]
        if left in conditions and right in conditions:
            for field, subset in (("lenient", True), ("strict", True), ("abstained", False)):
                a = _per_item(
                    [r for r in records if r["condition"] == left and r["answerable"] == subset],
                    field,
                )
                b = _per_item(
                    [r for r in records if r["condition"] == right and r["answerable"] == subset],
                    field,
                )
                differences = [a[i] - b[i] for i in sorted(a)]
                name = f"answerable {field}" if subset else "unanswerable abstention"
                summary["paired"][f"{left} minus {right}: {name}"] = {
                    "difference": statistics.mean(differences),
                    "ci95": _bootstrap(differences),
                    "items": len(differences),
                    "items_better": sum(d > 0 for d in differences),
                    "items_worse": sum(d < 0 for d in differences),
                }
    return summary


def run_rag_eval(
    config: ChatConfig,
    config_path: Path,
    dataset: Path,
    output: Path,
    repeats: int,
    conditions: list[str],
    split: str,
    index: Path,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    unknown = set(conditions) - set(CONDITIONS)
    if unknown or not conditions:
        raise ValueError(f"Unknown or missing conditions: {sorted(unknown)}")
    if config.documents is None:
        raise ValueError("The configuration has no documents block")
    items = load_items(dataset, split)
    partial = output.with_suffix(".partial.jsonl")
    if partial.exists():
        raise FileExistsError(f"Refusing to overwrite {partial}")
    documents: DocumentsConfig = replace(
        config.documents, folder=dataset.parent / "corpus", index=index
    )
    library = DocumentLibrary(documents, config.storage.parent / "hash-cache.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    retrieval: dict[str, list[Hit]] = {}
    records: list[dict[str, Any]] = []
    pool = None
    try:
        if any(CONDITIONS[c][1] for c in conditions):
            library.start()
            print("Indexing the corpus ...", flush=True)
            library.reindex()
            for item in items:  # Retrieval is deterministic: once per item.
                retrieval[item["id"]] = library.search(item["prompt"])
        pool = build_pool(config)
        with partial.open("x", encoding="utf-8") as stream:
            for condition in conditions:
                preset, grounded = CONDITIONS[condition]
                for item in items:
                    messages = [Message("system", config.system_prompt)]
                    messages.append(Message("user", item["prompt"]))
                    hits = retrieval[item["id"]] if grounded else None
                    if hits is not None:
                        messages = ground(messages, hits)
                    for repeat, seed in enumerate(seeds(repeats)):
                        result = ask(pool, "text", messages, replace(PRESETS[preset], seed=seed))
                        record = {
                            "condition": condition,
                            "item_id": item["id"],
                            "family": item["family"],
                            "answerable": item["answerable"],
                            "repeat": repeat,
                            "seed": seed,
                            **result,
                            **score_reply(item, result["reply"], hits),
                            "truncated": result.get("stop_type") == "limit",
                        }
                        records.append(record)
                        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                        stream.flush()
                        mark = (
                            "ok " if record["strict"] else ("~  " if record["lenient"] else "x  ")
                        )
                        print(f"{mark}{condition:16} {item['id']}", flush=True)
        launches = pool.launches
        props = pool.profiles["text"].engine.client.json("/props")
        server = {
            "build_info": props.get("build_info"),
            "model_path": props.get("model_path"),
            "n_ctx": props["default_generation_settings"]["n_ctx"],
        }
        identity = pool.profiles["text"].identity
    finally:
        if pool is not None:
            pool.close()
        library.close()
    summary = summarize(records)
    report = {
        "study": f"rag-eval:{dataset.parent.name}:{split}",
        "environment": environment(),
        "config_path": str(config_path),
        "config_sha256": sha256(config_path),
        "dataset_path": str(dataset),
        "dataset_sha256": sha256(dataset),
        "split": split,
        "identity": identity,
        "server": server,
        "launches": launches,
        "embedding": None if library.embedder is None else library.embedder.identity,
        "embedding_launch": library.launch,
        "documents": {
            "method": documents.method,
            "top_k": documents.top_k,
            "max_words": documents.max_words,
            "index": library.index.summary() if library.index is not None else None,
        },
        "conditions": {name: CONDITIONS[name] for name in conditions},
        "presets": {CONDITIONS[n][0]: asdict(PRESETS[CONDITIONS[n][0]]) for n in conditions},
        "seeds": seeds(repeats),
        "system_prompt": config.system_prompt,
        "grounding_rules": RULES,
        "not_found_sentence": NOT_FOUND,
        "retrieval": {
            item_id: [
                {"path": h.chunk.path, "heading": h.chunk.heading, "ranks": h.ranks} for h in hits
            ]
            for item_id, hits in retrieval.items()
        },
        "limitations": [
            "One host and one run; seeds fix sampling but GPU arithmetic may still vary.",
            "One author wrote the questions and most documents; see the dataset card.",
            "Abstention is detected by a pattern and can miss paraphrased refusals.",
        ],
        "records": records,
        "summary": summary,
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    partial.unlink()
    return summary

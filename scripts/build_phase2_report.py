"""Generate the IEEE-style report from executed evidence; no guessed result values."""
# Narrative paragraphs intentionally remain on single source lines.
# ruff: noqa: E501

import json
import statistics
from pathlib import Path
from xml.sax.saxutils import escape


def main() -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        Image,
        NextPageTemplate,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    root = Path("reports/phase2")
    suite = json.loads((root / "transformer_suite.json").read_text(encoding="utf-8"))
    gpu = json.loads((root / "gpu_verification.json").read_text(encoding="utf-8"))
    quant = json.loads((root / "quantization/summary.json").read_text(encoding="utf-8"))
    data = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
    selected = suite["selected_by_validation"]
    test = suite["selected_test_results"]
    preset = gpu["sessions"]["preset"]
    q4, q8 = quant["summaries"]["Q4_K_M:short"], quant["summaries"]["Q8_0:short"]
    long4, long8 = quant["summaries"]["Q4_K_M:long"], quant["summaries"]["Q8_0:long"]
    delta = quant["paired_quality"]["short"]
    failure_analysis = json.loads((root / "failure_analysis.json").read_text(encoding="utf-8"))
    paragraphs = [
        (
            "Abstract",
            f"We evaluate local language-model training and quantized inference on an NVIDIA RTX 2060 with 6 GB VRAM. Physical fp16 training, gradient scaling and bit-exact checkpoint continuation are verified. A 24-run factorial study varies decoder depth, width and positional encoding across three seeds on custom document-level WikiText partitions. The selected architecture achieves test NLL {statistics.mean(t['nll'] for t in test):.4f} per byte token. Q4_K_M and Q8_0 are produced from a common F16 Qwen3 1.7B artifact and measured under matched short and long workloads. Results establish an early-budget engineering baseline, not a converged architecture ranking or a general intelligence benchmark.",
        ),
        (
            "Index Terms",
            "Local language models, mixed precision, consumer GPU, reproducibility, quantization, language modeling.",
        ),
        (
            "I. INTRODUCTION",
            "Resource-constrained local language models require explicit tradeoffs among model capacity, context, precision and latency. OakGPT separates a transparent PyTorch decoder implementation from optimized llama.cpp inference. Phase 1 demonstrated the pipeline; this report adds physical GPU training evidence and controlled experiments. All measurements are local, and historical Phase 1 evidence is preserved unchanged.",
        ),
        (
            "II. SYSTEM AND VERIFICATION",
            f"The host runs Windows 10 Home, Python 3.11.6, an AMD Ryzen 7 3700X, approximately 16 GiB RAM and RTX 2060 (6144 MiB), driver 560.94. Training uses PyTorch {gpu['environment']['torch']} with CUDA runtime {gpu['environment']['cuda_runtime']}. CPU development remains in a separate environment. Model code implements pre-norm residual blocks, explicit causal multi-head attention, GELU feed-forward layers, tied embeddings and selectable positions.",
        ),
        (
            "",
            "The fp16 audit compares eight uninterrupted optimizer attempts with four attempts plus restoration and four further attempts. Model tensors match exactly and scaler states agree; losses, unscaled gradients and restored parameters are finite. This tests actual CUDA forward/backward computation, optimizer/RNG restoration and gradient scaling, rather than inferring GPU capability from installation.",
        ),
        (
            "",
            f"The original six-layer, width-256, context-256 training preset completed 200 attempts in {preset['session_seconds']:.2f} s, including validation/checkpoint work. Compute-only time was {preset['compute_seconds']:.2f} s and sampled-target throughput {preset['tokens_per_compute_second']:,.0f} tokens/s. Peak PyTorch allocated/reserved memory was {preset['cuda_peak_allocated_bytes'] / 2**20:.1f}/{preset['cuda_peak_reserved_bytes'] / 2**20:.1f} MiB. There were {preset['skipped_updates']} scaler-skipped updates. This fixture run overfits strongly; it verifies engineering behavior, not language quality.",
        ),
        (
            "III. DATA AND SPLIT INTEGRITY",
            f"WikiText-2 raw [1] is pinned to revision b08601e04326c79dfdd32d625aee71d232d685c3. Its Wikipedia-derived text carries CC BY-SA 3.0/GFDL licensing, separately from the MIT software. We reconstruct top-level articles, preserve their titles for attribution, normalize stored lines with NFKC and remove articles below 64 words. Of {data['counts']['input_documents']} reconstructed articles, {data['counts']['short_removed']} are short, {data['counts']['exact_or_title_removed']} exact/title duplicates and {data['counts']['overlap_removed']} share retained 16-word spans.",
        ),
        (
            "",
            f"Canonical content SHA256 sorting fixes deduplication order. A candidate sharing any normalized 16-word BLAKE2b fingerprint with retained text is rejected. Content-addressed seeded hashing then yields {data['counts']['train_documents']}/{data['counts']['validation_documents']}/{data['counts']['test_documents']} train/validation/test documents. Upstream partitions are pooled: these are custom splits, not standard WikiText scores. This procedure blocks observed exact/title/16-word overlap; semantic and shorter-span overlap remain possible. Windows never cross article boundaries and incomplete document tails are dropped.",
        ),
        (
            "IV. EXPERIMENTAL DESIGN",
            "The scratch study crosses depth {2,4}, embedding width {64,128}, learned/sinusoidal positions and seeds {42,43,44}. Every run uses byte tokens, context 128, microbatch 4, two accumulation steps, AdamW (learning rate 0.0003, weight decay 0.1), dropout 0.1, gradient clipping 1, fp16 and 80 optimizer attempts: 81,920 sampled targets. Equal token budgets do not equalize parameter counts, FLOPs or training time.",
        ),
        (
            "",
            "A fixed 64-window validation prefix is scored every 20 attempts for checkpoint selection. Each selected checkpoint is then scored on all validation windows. Architecture selection minimizes mean full-validation NLL over seeds. Only its three checkpoints are evaluated on the held-out language-model test partition. Mean and sample SD use independent training seeds, not training steps. Perplexity is exp(mean token NLL); the tokenizer unit is always stated.",
        ),
        (
            "",
            "Both quantizations originate from Qwen3 1.7B revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e [2], converted once from BF16 safetensors to F16 GGUF and independently quantized using llama.cpp b11930/85cc432e2 [3]. No importance matrix or Q8-to-Q4 requantization is used. Commands, source shards, converted artifacts and executable hashes are retained. These new artifacts are distinct from the Phase 1 official Q8 distribution.",
        ),
        (
            "",
            "Inference uses all-layer RTX 2060 offload, context 2048, batch/microbatch 256/128, eight CPU threads, one slot, non-thinking formatting, greedy seed 42 and disabled prompt caching. Three fresh rounds alternate variant order: Q4/Q8, Q8/Q4, Q4/Q8. Each workload excludes a warmup. The short task set has 48 frozen prompts and a 32-token cap; four long-writing prompts have a 256-token cap. GPU training and inference measurement do not overlap.",
        ),
        (
            "",
            "Request latency includes HTTP/preflight and final stop processing. TTFT ends at the first native token event, which may be invisible. Decode rate excludes the first event and uses subsequent native tokens divided by first-to-last event time. Device-wide VRAM is sampled using nvidia-smi; its requested 100 ms cadence excludes process-launch overhead and cannot identify an exact per-model peak. Missing telemetry is never substituted with zero.",
        ),
        (
            "V. RESULTS",
            f"The validation-selected architecture is depth {selected['depth']}, width {selected['width']}, {selected['position']} positions, with full-validation NLL {selected['validation_nll_mean']:.4f} (sample SD {selected['validation_nll_sd']:.4f}). Its held-out test NLL is {statistics.mean(t['nll'] for t in test):.4f} (SD {statistics.stdev(t['nll'] for t in test):.4f}); mean per-seed perplexity is {statistics.mean(t['perplexity'] for t in test):.2f}. Table I and Fig. 1 retain all architecture groups rather than reporting only the winner.",
        ),
        (
            "",
            f"Short-task prompt-macro exact accuracy is {q4['prompt_macro_accuracy']:.3f} for Q4 and {q8['prompt_macro_accuracy']:.3f} for Q8, on 48 unique prompts each. Repeated greedy responses are averaged per prompt. The paired Q4-minus-Q8 difference is {delta['difference_left_minus_right']:.3f}, with seeded prompt-bootstrap 95% interval [{delta['paired_prompt_bootstrap_ci95'][0]:.3f}, {delta['paired_prompt_bootstrap_ci95'][1]:.3f}]. Template dependence and the narrow task mixture limit this interval's interpretation.",
        ),
        (
            "",
            f"For long decoding, the median across prompt-wise median decode rates is {long4['decode_tokens_per_second_prompt_median']:.2f} tokens/s for Q4 and {long8['decode_tokens_per_second_prompt_median']:.2f} for Q8. Median total request latencies are {long4['latency_s_prompt_median']:.3f}/{long8['latency_s_prompt_median']:.3f} s. Fig. 2 shows both workloads. Maximum budgets are identical within workloads, but early EOS and actual generated lengths can differ. Long-workload containment checks are not interpreted as semantic quality.",
        ),
        (
            "VI. DISCUSSION AND THREATS TO VALIDITY",
            "Eighty training attempts measure early optimization. Rankings may reverse with longer training, different learning rates or larger data. Only three seeds are available; fixed training order can confound time with warmup and temperature. Deduplication changes the source distribution, and 16-word overlap filtering cannot establish semantic independence. Prefix-based checkpoint selection and architecture selection on full validation are disclosed, and the test split is not used for tuning.",
        ),
        (
            "",
            "The 48-prompt held-out task set contains 24 arithmetic, 12 entity-reading and 12 string-transform tasks. Templates induce dependence; similarity to pretrained examples cannot be ruled out. Strict formatting can mark a correct answer with extra text as incorrect. Prompt bootstrap intervals are descriptive, not proof of generalization. Neither the scratch byte-token perplexity nor its token/s can be directly compared to Qwen subword metrics.",
        ),
        (
            "",
            "Desktop processes, WDDM accounting, thermal state, sampling overhead and OS scheduling affect observed inference performance. A sampled device-wide peak includes unrelated allocations and is a lower bound on transient peaks. Different quantization layouts may change generated lengths and kernel behavior. Hashes and a pinned build improve repeatability but do not guarantee numerical identity on another driver, GPU or library release.",
        ),
        (
            "VII. CONCLUSION",
            "The project now supplies executed CUDA training/resume verification, custom leak-controlled document partitions, a multi-seed factorial study and matched local quantization measurements with raw outputs. The next research step is longer-budget replication, additional seeds and externally validated evaluation. LoRA and robotics integration are intentionally deferred.",
        ),
        (
            "REFERENCES",
            '[1] S. Merity et al., "Pointer Sentinel Mixture Models," arXiv:1609.07843, 2016; Salesforce WikiText dataset card, pinned revision, accessed Oct. 27, 2026.',
        ),
        (
            "",
            '[2] Qwen Team, "Qwen3 Technical Report," arXiv:2505.09388, 2025; Qwen/Qwen3-1.7B model distribution, pinned revision.',
        ),
        (
            "",
            "[3] ggml-org, llama.cpp, build b11930, commit 85cc432e2c8b92925f17dfb8937742541312f1d4. Local server and quantization logs retained.",
        ),
        (
            "",
            "[4] PyTorch, Automatic Mixed Precision documentation and previous-version installation index. Training environment: 2.9.1+cu126. Exact package freezes accompany evidence.",
        ),
    ]
    diagnostic = []
    for name in ["Q4_K_M", "Q8_0"]:
        failures = failure_analysis[name]["failures_round0"]
        if failures:
            example = failures[0]
            diagnostic.append(
                f"{name}: accepted {example['accepted']!r}, actual "
                f"{example['actual'][:100]!r} (example {example['id']})."
            )
    insertion = next(i for i, item in enumerate(paragraphs) if item[0].startswith("VI."))
    paragraphs.insert(
        insertion,
        (
            "",
            "Observed strict-scoring failures include "
            + " ".join(diagnostic)
            + " Correct numerical content with extra expression text fails the "
            "frozen answer-only contract. This score must not be relabeled arithmetic reasoning "
            "accuracy. Raw failures and category scores are retained without changing references.",
        ),
    )
    peaks = {
        name: max(
            item["memory"]["peak_bytes"] for item in failure_analysis[name]["memory_and_lengths"]
        )
        / 2**20
        for name in ["Q4_K_M", "Q8_0"]
    }
    paragraphs.insert(
        insertion + 1,
        (
            "",
            f"Across recorded workloads and rounds, sampled "
            f"device-wide peaks were {peaks['Q4_K_M']:.0f} MiB for Q4 and {peaks['Q8_0']:.0f} MiB "
            f"for Q8, including desktop allocations. Long-decode round-median sample SDs were "
            f"{long4['decode_tokens_per_second_round_median_sd']:.2f}/{long8['decode_tokens_per_second_round_median_sd']:.2f} "
            "tokens/s. These three-round descriptive spreads do not establish stable population "
            "confidence intervals. Per-round baselines and actual generated lengths are archived.",
        ),
    )
    markdown = [
        "# OakGPT: Local GPU Training and Controlled Language-Model Evaluation",
        "",
        "OakGPT Research Engineering | Technical Report | 27 October 2026",
        "",
    ]
    for heading, text in paragraphs:
        if heading:
            markdown += ["## " + heading, ""]
        markdown += [text, ""]
    markdown += [
        "## Table I. Full-validation NLL across three seeds",
        "",
        "| Depth | Width | Position | Mean NLL | Sample SD |",
        "| --- | --- | --- | --- | --- |",
    ]
    for g in suite["groups"]:
        markdown.append(
            f"| {g['depth']} | {g['width']} | {g['position']} | {g['validation_nll_mean']:.4f} | {g['validation_nll_sd']:.4f} |"
        )
    (root / "report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")

    output = Path("output/pdf/phase2-research-report.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    body = ParagraphStyle(
        "Body", fontName="Times-Roman", fontSize=9, leading=11, alignment=TA_JUSTIFY, spaceAfter=6
    )
    heading = ParagraphStyle(
        "Heading",
        parent=body,
        fontName="Times-Bold",
        fontSize=9,
        alignment=TA_CENTER,
        spaceBefore=9,
        spaceAfter=6,
        keepWithNext=True,
    )
    caption = ParagraphStyle("Caption", parent=body, fontSize=8, leading=10, alignment=TA_CENTER)
    width, height = 612, 792
    margin, gutter = 40, 18
    column = (width - 2 * margin - gutter) / 2

    def footer(canvas, document):
        canvas.setFont("Times-Roman", 8)
        canvas.drawCentredString(
            width / 2, 24, f"OakGPT Technical Report - 27 October 2026 - {document.page}"
        )

    def first(canvas, document):
        footer(canvas, document)
        canvas.setFont("Times-Bold", 17)
        canvas.drawCentredString(width / 2, 750, "OakGPT: Local GPU Training and")
        canvas.drawCentredString(width / 2, 730, "Controlled Language-Model Evaluation")
        canvas.setFont("Times-Roman", 10)
        canvas.drawCentredString(width / 2, 708, "OakGPT Research Engineering")
        canvas.setFont("Times-Italic", 9)
        canvas.drawCentredString(
            width / 2, 693, "Reproducible experiments on an RTX 2060 with 6 GB VRAM"
        )

    def frames(top):
        return [
            Frame(
                margin,
                42,
                column,
                top - 42,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            ),
            Frame(
                margin + column + gutter,
                42,
                column,
                top - 42,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            ),
        ]

    doc = BaseDocTemplate(
        str(output),
        pagesize=(width, height),
        title="OakGPT Phase 2 Research Report",
        author="OakGPT Research Engineering",
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="first", frames=frames(673), onPage=first),
            PageTemplate(id="columns", frames=frames(750), onPage=footer),
            PageTemplate(
                id="figures",
                frames=[
                    Frame(
                        margin,
                        42,
                        width - 2 * margin,
                        708,
                        leftPadding=0,
                        rightPadding=0,
                        topPadding=0,
                        bottomPadding=0,
                    )
                ],
                onPage=footer,
            ),
        ]
    )
    story = [NextPageTemplate("columns")]
    for title, text in paragraphs:
        if title:
            story.append(Paragraph(escape(title), heading))
        story.append(Paragraph(escape(text), body))
        if title == "V. RESULTS":
            story.append(Paragraph("TABLE I. FULL-VALIDATION NLL (THREE SEEDS)", caption))
            rows = [["L", "D", "Position", "NLL", "SD"]] + [
                [
                    g["depth"],
                    g["width"],
                    g["position"],
                    f"{g['validation_nll_mean']:.4f}",
                    f"{g['validation_nll_sd']:.4f}",
                ]
                for g in suite["groups"]
            ]
            table = Table(rows, colWidths=[20, 28, 70, 65, 45], repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
                        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.extend([table, Spacer(1, 8)])
    story.extend(
        [
            NextPageTemplate("figures"),
            PageBreak(),
            Paragraph("EXPERIMENTAL FIGURES", heading),
            Spacer(1, 10),
            Image(str(root / "figures/transformer.png"), width=532, height=195),
            Paragraph(
                "Fig. 1. Convergence on the fixed validation prefix and full-validation architecture comparison. Bands/error bars show sample SD across three independent seeds. All models receive the same short token budget.",
                caption,
            ),
            Spacer(1, 22),
            Image(str(root / "figures/quantization.png"), width=532, height=180),
            Paragraph(
                "Fig. 2. Matched Q4_K_M/Q8_0 client-observed timings. Bars show medians across prompt-wise timing medians over three rounds. Short and long caps are 32 and 256 tokens. Raw rounds and variability accompany the figures.",
                caption,
            ),
            Spacer(1, 18),
            Paragraph("REPRODUCIBILITY RECORD", heading),
            Paragraph(
                "Raw per-step training telemetry, complete convergence series, per-response text/timings, document/artifact hashes, startup logs, environment freezes and configuration files are retained in reports/phase2. Vector PDF/SVG versions of these figures are provided separately. The report uses IEEE-style numbered sections and two-column typography; it is an engineering technical report, not a peer-reviewed IEEE publication.",
                body,
            ),
        ]
    )
    doc.build(story)
    print(output)


if __name__ == "__main__":
    main()

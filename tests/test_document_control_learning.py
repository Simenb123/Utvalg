from __future__ import annotations

from document_control_learning import (
    apply_supplier_profile,
    build_supplier_profile,
    match_supplier_profile,
)
from document_engine.engine import TextSegment
from document_engine.profiles import _find_hint_in_segments, infer_field_hints


def test_build_supplier_profile_collects_vendor_specific_hints() -> None:
    fields = {
        "supplier_name": "Eksempel Partner AS",
        "supplier_orgnr": "987654321",
        "invoice_number": "INV-2025-001",
        "due_date": "01.03.2025",
        "total_amount": "995.00",
        "currency": "NOK",
    }
    raw_text = "\n".join(
        [
            "Eksempel Partner AS",
            "Org.nr: 987654321",
            "Vår referanse: INV-2025-001",
            "Forfall: 01.03.2025",
            "Til betaling: 995,00 NOK",
        ]
    )

    profile = build_supplier_profile(fields, raw_text)

    assert profile is not None
    assert profile["profile_key"] == "orgnr:987654321"
    assert profile["schema_version"] == 1
    assert profile["field_hints"]["invoice_number"][0]["label"] == "vår referanse"
    assert profile["field_hints"]["due_date"][0]["label"] == "forfall"
    assert profile["field_hints"]["total_amount"][0]["label"] == "til betaling"


def test_apply_supplier_profile_reuses_learned_hints_on_new_document() -> None:
    fields = {
        "supplier_name": "Eksempel Partner AS",
        "supplier_orgnr": "987654321",
        "invoice_number": "INV-2025-001",
        "due_date": "01.03.2025",
        "total_amount": "995.00",
        "currency": "NOK",
    }
    raw_text = "\n".join(
        [
            "Eksempel Partner AS",
            "Vår referanse: INV-2025-001",
            "Forfall: 01.03.2025",
            "Til betaling: 995,00 NOK",
        ]
    )
    profile = build_supplier_profile(fields, raw_text)

    extracted = apply_supplier_profile(
        profile or {},
        "\n".join(
            [
                "Eksempel Partner AS",
                "Vår referanse: INV-2025-002",
                "Forfall: 15.03.2025",
                "Til betaling: 1 250,00 NOK",
            ]
        ),
    )

    assert extracted["supplier_name"] == "Eksempel Partner AS"
    assert extracted["supplier_orgnr"] == "987654321"
    assert extracted["invoice_number"] == "INV-2025-002"
    assert extracted["due_date"] == "15.03.2025"
    assert extracted["total_amount"] == "1 250,00 NOK"


def test_match_supplier_profile_can_match_on_alias_in_raw_text() -> None:
    profile = {
        "profile_key": "orgnr:987654321",
        "supplier_name": "Eksempel Partner AS",
        "supplier_orgnr": "987654321",
        "aliases": ["eksempel partner as", "987654321"],
        "sample_count": 2,
        "field_hints": {},
        "static_fields": {"supplier_name": "Eksempel Partner AS"},
    }

    matched, score = match_supplier_profile(
        {"orgnr:987654321": profile},
        fields={},
        raw_text="Leverandør Eksempel Partner AS\nTil betaling: 250,00 NOK",
    )

    assert matched is not None
    assert matched["profile_key"] == "orgnr:987654321"
    assert matched["supplier_name"] == "Eksempel Partner AS"
    assert score >= 60.0


def test_infer_field_hints_handles_nbsp_in_amount_values() -> None:
    # Regression: PDF extraction produces NBSP (\u00a0) in grouped amounts
    # like "183\xa0592,50". `_candidate_lines` collapses NBSP → space, but
    # `_value_markers` used to preserve NBSP, so markers never matched the
    # normalized segment lines. Result: 23 Brage saves, 0 amount hints.
    segments = [
        TextSegment(
            text="Beløp ekskl. mva 183\u00a0592,50 NOK",
            source="pdf_text_pdfplumber",
            page=2,
            bbox=(0.0, 400.0, 500.0, 440.0),
        ),
    ]
    hints = infer_field_hints(
        raw_text="",
        fields={"subtotal_amount": "183\u00a0592,50"},
        segments=segments,
        field_evidence={"subtotal_amount": {"page": 2, "bbox": (388.0, 429.0, 438.0, 438.0)}},
    )
    assert "subtotal_amount" in hints
    assert hints["subtotal_amount"][0]["label"] == "beløp ekskl mva"
    assert hints["subtotal_amount"][0]["page"] == 2


def test_value_markers_amount_nbsp_matches_normalized_segment_line() -> None:
    # Direct check: `_find_hint_in_segments` must find the value even when
    # the stored value keeps the NBSP but the segment text has been
    # whitespace-collapsed.
    seg = TextSegment(
        text="Totalt 229\u00a0490,63 NOK",
        source="pdf_text",
        page=2,
        bbox=(0.0, 0.0, 1.0, 1.0),
    )
    hint = _find_hint_in_segments(
        [seg], "total_amount", "229\u00a0490,63",
        evidence_page=2, evidence_bbox=None,
    )
    assert hint is not None
    assert hint["label"] == "totalt"


def test_amount_self_consistency_passes_when_subtotal_vat_sum_matches_total() -> None:
    from document_engine.engine import _validate_amount_self_consistency
    from document_engine.models import FieldEvidence

    evidence_map = {
        "subtotal_amount": FieldEvidence(field_name="subtotal_amount", normalized_value="800.00"),
        "vat_amount":      FieldEvidence(field_name="vat_amount",      normalized_value="200.00"),
        "total_amount":    FieldEvidence(field_name="total_amount",    normalized_value="1000.00"),
    }
    result = _validate_amount_self_consistency(evidence_map)
    assert result is True
    for ev in evidence_map.values():
        assert ev.metadata.get("self_consistent") is True
        assert "Avvik" not in ev.validation_note


def test_amount_self_consistency_flags_inconsistent_trio() -> None:
    from document_engine.engine import _validate_amount_self_consistency
    from document_engine.models import FieldEvidence

    evidence_map = {
        "subtotal_amount": FieldEvidence(field_name="subtotal_amount", normalized_value="800.00"),
        "vat_amount":      FieldEvidence(field_name="vat_amount",      normalized_value="200.00"),
        "total_amount":    FieldEvidence(field_name="total_amount",    normalized_value="5000.00"),
    }
    result = _validate_amount_self_consistency(evidence_map)
    assert result is False
    for ev in evidence_map.values():
        assert ev.metadata.get("self_consistent") is False
        assert "Avvik" in ev.validation_note


def test_amount_self_consistency_returns_none_when_a_field_is_missing() -> None:
    from document_engine.engine import _validate_amount_self_consistency
    from document_engine.models import FieldEvidence

    evidence_map = {
        "subtotal_amount": FieldEvidence(field_name="subtotal_amount", normalized_value="800.00"),
        "total_amount":    FieldEvidence(field_name="total_amount",    normalized_value="1000.00"),
        # vat_amount missing
    }
    result = _validate_amount_self_consistency(evidence_map)
    assert result is None
    for ev in evidence_map.values():
        assert "self_consistent" not in ev.metadata


def test_global_profile_hints_do_not_boost_amount_fields() -> None:
    # Cross-supplier aggregated hints like "til betaling" leak across
    # vendors — they must not be applied when the matched profile is the
    # global fallback.
    from document_engine.engine import _apply_supplier_profile_learning, TextSegment
    from document_engine.models import DocumentFacts, FieldEvidence, SupplierProfile
    from document_engine.profiles import GLOBAL_PROFILE_KEY

    # A fake PDF with two amounts on different pages; the "correct" value
    # for this vendor's subtotal is 500,00 on page 1, but the global hint
    # says the label "til betaling" on page 2 — which here happens to be a
    # different number (9999,00). The guard must prevent the global hint
    # from dragging extraction to the wrong page.
    segments = [
        TextSegment(text="Netto 500,00 NOK",             source="pdf_text", page=1, bbox=(0, 0, 100, 10)),
        TextSegment(text="Til betaling 9999,00 NOK",     source="pdf_text", page=2, bbox=(0, 0, 100, 10)),
    ]
    raw_text = "Netto 500,00 NOK\nTil betaling 9999,00 NOK"
    facts = DocumentFacts(subtotal_amount="500.00")
    evidence = {
        "subtotal_amount": FieldEvidence(
            field_name="subtotal_amount", normalized_value="500.00", raw_value="500,00",
            source="pdf_text", confidence=0.8, page=1, bbox=(0, 0, 100, 10),
        ),
    }
    global_profile = SupplierProfile(
        profile_key=GLOBAL_PROFILE_KEY,
        supplier_name="",
        supplier_orgnr="",
        field_hints={
            "subtotal_amount": [{"label": "til betaling", "page": 2, "count": 5}],
        },
    )
    new_facts, new_evidence, _status, _meta = _apply_supplier_profile_learning(
        facts, evidence, raw_text, {GLOBAL_PROFILE_KEY: global_profile},
        segments=segments,
    )
    # Subtotal must still point at the page-1 netto, not the page-2 label
    assert new_facts.subtotal_amount == "500.00", (
        f"global profile should not override amount extraction; got {new_facts.subtotal_amount!r}"
    )


def test_ocrmypdf_redo_mode_passes_redo_ocr_flag(monkeypatch) -> None:
    # Verify the --redo-ocr code path sends the right flag to subprocess,
    # so a weak pre-OCR'd text layer gets re-OCRed instead of kept as-is.
    import shutil
    from pathlib import Path as _P
    from document_engine import engine as _engine

    captured: dict[str, list[str]] = {}

    def _fake_which(name: str) -> str:
        return "ocrmypdf"

    class _FakeCompleted:
        returncode = 0

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        # Pretend ocrmypdf produced no usable output — we only care about the flag
        return _FakeCompleted()

    def _fake_extractor(path: _P):
        return "", []

    monkeypatch.setattr(_engine.shutil, "which", _fake_which)
    monkeypatch.setattr(_engine.subprocess, "run", _fake_run)
    monkeypatch.setattr(_engine, "_extract_pdf_text_with_pypdf", _fake_extractor)
    monkeypatch.setattr(_engine, "_extract_pdf_text_with_pdfplumber", _fake_extractor)
    monkeypatch.setattr(_engine, "_extract_pdf_text_with_fitz_blocks", _fake_extractor)
    monkeypatch.setattr(_engine, "_extract_pdf_text_with_fitz", _fake_extractor)

    # Create a throwaway path — we're not actually OCRing anything
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = _P(tmp) / "doc.pdf"
        p.write_bytes(b"%PDF-1.4\n%%EOF")  # minimal marker file
        _engine._ocr_pdf_with_ocrmypdf(p, mode="redo")

    assert captured["cmd"], "ocrmypdf was not invoked"
    assert "--redo-ocr" in captured["cmd"], (
        f"mode='redo' must pass --redo-ocr; got cmd={captured['cmd']!r}"
    )
    assert "--skip-text" not in captured["cmd"]


def test_ocrmypdf_skip_mode_passes_skip_text_flag(monkeypatch) -> None:
    import shutil
    from pathlib import Path as _P
    from document_engine import engine as _engine

    captured: dict[str, list[str]] = {}

    class _FakeCompleted:
        returncode = 0

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(_engine.shutil, "which", lambda n: "ocrmypdf")
    monkeypatch.setattr(_engine.subprocess, "run", _fake_run)
    for name in ("_extract_pdf_text_with_pypdf", "_extract_pdf_text_with_pdfplumber",
                 "_extract_pdf_text_with_fitz_blocks", "_extract_pdf_text_with_fitz"):
        monkeypatch.setattr(_engine, name, lambda p: ("", []))

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = _P(tmp) / "doc.pdf"
        p.write_bytes(b"%PDF-1.4\n%%EOF")
        _engine._ocr_pdf_with_ocrmypdf(p)  # default mode="skip"

    assert "--skip-text" in captured["cmd"]
    assert "--redo-ocr" not in captured["cmd"]


def test_fitz_words_extractor_gives_tight_bbox_around_trailing_amount() -> None:
    # Build a synthetic PDF with a known row and verify that the fitz_words
    # extractor produces a full-row segment whose bbox is tight around
    # "1 000,00 NOK" rather than the full-line width. This is what enables
    # _bbox_is_near to distinguish MVA from subtotal in a tabular invoice.
    import fitz
    import tempfile
    from pathlib import Path as _P
    from document_engine.engine import _extract_pdf_text_with_fitz_words

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = _P(tmp) / "sample.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        # Very wide label on the left, narrow value on the right
        page.insert_text((50, 100), "Til betaling",              fontsize=11)
        page.insert_text((400, 100), "1 000,00 NOK",             fontsize=11)
        doc.save(str(pdf_path))
        doc.close()

        _, segments = _extract_pdf_text_with_fitz_words(pdf_path)

    # Gap-splitting also emits chunk-only segments first; we want the
    # full-row segment (contains both label and value) to verify the
    # trailing-cluster bbox tightening.
    row = next(
        (s for s in segments if "Til betaling" in s.text and "1 000,00" in s.text),
        None,
    )
    assert row is not None, f"full-row segment missing; got {[s.text for s in segments]}"
    assert row.bbox is not None
    x0, _y0, x1, _y1 = row.bbox
    # Label starts at x=50, value at x=400 → value-cluster x0 must be >= ~390
    # and bbox width < 200 (clearly tighter than the full line width ~470).
    assert x0 >= 350, f"value-cluster bbox starts too far left: x0={x0}"
    assert (x1 - x0) < 200, f"value-cluster bbox too wide ({x1 - x0}), should be tight around the amount"


def test_fitz_words_gap_splitting_emits_separate_chunks_for_multi_zone_row() -> None:
    # Multi-zone tabular rows (Beløp / MVA / Total on one y-line with wide
    # gaps) must be emitted as chunk segments before the full-row fallback.
    # Each chunk's bbox is tight around its own value cluster so
    # _first_match_evidence can attribute a bbox per amount instead of
    # inheriting the whole row's width.
    import fitz
    import tempfile
    from pathlib import Path as _P
    from document_engine.engine import _extract_pdf_text_with_fitz_words

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = _P(tmp) / "multi.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        # Three value zones at clearly separated x-coordinates on the same
        # y-line. Gaps between zones exceed the 40pt gap-split threshold.
        page.insert_text((50, 150),  "Beløp 800,00",   fontsize=11)
        page.insert_text((250, 150), "MVA 200,00",     fontsize=11)
        page.insert_text((450, 150), "Total 1000,00",  fontsize=11)
        doc.save(str(pdf_path))
        doc.close()

        _, segments = _extract_pdf_text_with_fitz_words(pdf_path)

    texts = [s.text for s in segments]
    # Chunk segments must exist individually (not merged with other zones).
    belop_chunk = next((s for s in segments if "800,00" in s.text and "MVA" not in s.text and "Total" not in s.text), None)
    mva_chunk = next((s for s in segments if "MVA 200,00" in s.text and "Beløp" not in s.text and "Total" not in s.text), None)
    total_chunk = next((s for s in segments if "Total 1000,00" in s.text and "MVA" not in s.text), None)
    assert belop_chunk is not None, f"Beløp chunk missing; got {texts}"
    assert mva_chunk is not None, f"MVA chunk missing; got {texts}"
    assert total_chunk is not None, f"Total chunk missing; got {texts}"
    # Each chunk bbox stays narrow — a correct gap-split keeps MVA's bbox
    # well to the left of Total's, even though they sit on the same y-line.
    assert mva_chunk.bbox is not None and total_chunk.bbox is not None
    assert mva_chunk.bbox[2] < total_chunk.bbox[0], (
        f"MVA bbox overlaps Total bbox: {mva_chunk.bbox=} {total_chunk.bbox=}"
    )
    # Full-row fallback must be present (lets label-hint matching still work
    # across zone boundaries).
    full_row = next(
        (s for s in segments if "Beløp" in s.text and "MVA" in s.text and "Total" in s.text),
        None,
    )
    assert full_row is not None, f"full-row fallback missing; got {texts}"


def test_profile_hint_boost_weight_saturates_at_count_three() -> None:
    # Regression: weight used to be `min(count/3, 2.0)` — a profile with 6+
    # confirmed saves would double the boost (up to +1400) and drown out
    # the generic pattern ranking. Docstring said "saturates at 3" but the
    # code didn't. Clamp must be 1.0.
    from document_engine.engine import _profile_hint_boost
    from document_engine.models import FieldEvidence

    evidence = FieldEvidence(
        field_name="total_amount",
        normalized_value="1000.00",
        raw_value="1 000,00",
        page=2,
        bbox=(100.0, 200.0, 150.0, 210.0),
    )
    segment_text = "Til betaling 1 000,00 NOK"
    base_hint = {
        "label": "til betaling",
        "page": 2,
        "bbox": (100.0, 200.0, 150.0, 210.0),
        "count": 3,
    }
    high_hint = dict(base_hint, count=20)

    boost_at_3 = _profile_hint_boost(evidence, segment_text, [base_hint])
    boost_at_20 = _profile_hint_boost(evidence, segment_text, [high_hint])

    assert boost_at_3 == boost_at_20, (
        "weight must saturate at count=3 so more saves don't keep inflating "
        f"boost. Got boost_at_3={boost_at_3}, boost_at_20={boost_at_20}."
    )
    # page + label + bbox_near at weight 1.0 → 700.0
    assert boost_at_3 == 700.0


# ---------------------------------------------------------------------------
# Phase 1 — word-span bbox, raw text in _reload_segments_for, redo-OCR trigger
# ---------------------------------------------------------------------------


def test_fitz_words_extractor_populates_word_spans() -> None:
    """word_spans must carry per-token char offsets AND bbox, so that
    _first_match_evidence can locate the exact regex match on the line."""
    import fitz
    import tempfile
    from pathlib import Path as _P
    from document_engine.engine import _extract_pdf_text_with_fitz_words

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = _P(tmp) / "words.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 100), "Sum 800,00 MVA 200,00 Total 1000,00", fontsize=11)
        doc.save(str(pdf_path))
        doc.close()

        _, segments = _extract_pdf_text_with_fitz_words(pdf_path)

    row = next((s for s in segments if "Total" in s.text), None)
    assert row is not None, f"row missing; got {[s.text for s in segments]}"
    assert row.word_spans, "word_spans must not be empty for fitz_words source"
    # char spans must index into the joined text and be ordered
    for start, end, bbox in row.word_spans:
        assert 0 <= start < end <= len(row.text)
        assert row.text[start:end] == row.text[start:end].strip()  # clean slice
        assert bbox[0] < bbox[2] and bbox[1] < bbox[3]


def test_first_match_evidence_uses_word_spans_for_precise_bbox() -> None:
    """When multiple amounts share a line, each field's bbox should be tight
    around its own regex match — not the whole line."""
    import re
    from document_engine.engine import TextSegment, _first_match_evidence

    # Synthetic: one segment containing three amounts with distinct word-bboxes
    line = "Sum 800,00 MVA 200,00 Total 1000,00"
    # char positions: Sum=0-3, 800,00=4-10, MVA=11-14, 200,00=15-21, Total=22-27, 1000,00=28-35
    spans = [
        (0, 3, (100.0, 50.0, 115.0, 60.0)),       # Sum
        (4, 10, (116.0, 50.0, 150.0, 60.0)),      # 800,00
        (11, 14, (151.0, 50.0, 165.0, 60.0)),     # MVA
        (15, 21, (166.0, 50.0, 200.0, 60.0)),     # 200,00
        (22, 27, (201.0, 50.0, 215.0, 60.0)),     # Total
        (28, 35, (216.0, 50.0, 250.0, 60.0)),     # 1000,00
    ]
    seg = TextSegment(
        text=line, source="pdf_text_fitz_words", page=1,
        bbox=(100.0, 50.0, 250.0, 60.0),  # full line
        word_spans=spans,
    )
    total_pattern = re.compile(r"Total\s+([\d ,.]+)")
    vat_pattern = re.compile(r"MVA\s+([\d ,.]+)")

    ev_total = _first_match_evidence(
        "total_amount", (total_pattern,), line, [seg],
        lambda s: s.replace(" ", "").replace(",", "."), 0.8, "test",
    )
    ev_vat = _first_match_evidence(
        "vat_amount", (vat_pattern,), line, [seg],
        lambda s: s.replace(" ", "").replace(",", "."), 0.8, "test",
    )
    assert ev_total is not None and ev_vat is not None
    assert ev_total.bbox is not None and ev_vat.bbox is not None
    # Total bbox must be to the right of VAT bbox and neither should be the full-line bbox
    assert ev_total.bbox[0] > ev_vat.bbox[0]
    assert ev_total.bbox != seg.bbox, "should have tightened around the match, not fallen back"
    assert ev_vat.bbox != seg.bbox
    # Total bbox should overlap the "1000,00" word span (x0 ~= 216)
    assert ev_total.bbox[0] >= 215.0 and ev_total.bbox[2] <= 251.0


def test_first_match_evidence_falls_back_to_segment_bbox_without_word_spans() -> None:
    import re
    from document_engine.engine import TextSegment, _first_match_evidence

    seg = TextSegment(
        text="Total 1000,00", source="pdf_text_fitz", page=1,
        bbox=(10.0, 20.0, 300.0, 30.0),
        # no word_spans
    )
    ev = _first_match_evidence(
        "total_amount", (re.compile(r"Total\s+([\d ,.]+)"),),
        seg.text, [seg],
        lambda s: s.replace(" ", "").replace(",", "."), 0.8, "test",
    )
    assert ev is not None
    assert ev.bbox == seg.bbox  # fell back to segment bbox


def test_should_redo_ocr_for_amounts_triggers_on_big_deviation_even_at_high_score() -> None:
    from document_engine.engine import (
        _should_redo_ocr_for_amounts, ExtractedTextResult,
    )
    from document_engine.models import FieldEvidence

    evidence = {
        "subtotal_amount": FieldEvidence(field_name="subtotal_amount", normalized_value="800.00"),
        "vat_amount":      FieldEvidence(field_name="vat_amount",      normalized_value="200.00"),
        "total_amount":    FieldEvidence(field_name="total_amount",    normalized_value="5000.00"),
    }
    # High score (90) but big deviation (800+200=1000 vs 5000 → diff 4000)
    extracted = ExtractedTextResult(
        text="...", source="pdf_text_fitz", ocr_used=False,
        metadata={"selected_score": 90.0, "candidate_sources": []},
        segments=[],
    )
    assert _should_redo_ocr_for_amounts(evidence, extracted) is True


def test_should_redo_ocr_for_amounts_skipped_on_consistent_amounts() -> None:
    from document_engine.engine import (
        _should_redo_ocr_for_amounts, ExtractedTextResult,
    )
    from document_engine.models import FieldEvidence

    evidence = {
        "subtotal_amount": FieldEvidence(field_name="subtotal_amount", normalized_value="800.00"),
        "vat_amount":      FieldEvidence(field_name="vat_amount",      normalized_value="200.00"),
        "total_amount":    FieldEvidence(field_name="total_amount",    normalized_value="1000.00"),
    }
    extracted = ExtractedTextResult(
        text="...", source="pdf_text_fitz", ocr_used=False,
        metadata={"selected_score": 15.0, "candidate_sources": []},  # low score too
        segments=[],
    )
    assert _should_redo_ocr_for_amounts(evidence, extracted) is False


def test_should_redo_ocr_for_amounts_skipped_when_redo_already_ran() -> None:
    from document_engine.engine import (
        _should_redo_ocr_for_amounts, ExtractedTextResult,
    )
    from document_engine.models import FieldEvidence

    evidence = {
        "subtotal_amount": FieldEvidence(field_name="subtotal_amount", normalized_value="800.00"),
        "vat_amount":      FieldEvidence(field_name="vat_amount",      normalized_value="200.00"),
        "total_amount":    FieldEvidence(field_name="total_amount",    normalized_value="5000.00"),
    }
    extracted = ExtractedTextResult(
        text="...", source="pdf_ocrmypdf_redo", ocr_used=True,
        metadata={
            "selected_score": 25.0,
            "candidate_sources": [{"source": "pdf_ocrmypdf_redo"}],
        },
        segments=[],
    )
    assert _should_redo_ocr_for_amounts(evidence, extracted) is False


def test_should_redo_ocr_for_amounts_skipped_when_score_high_and_deviation_small() -> None:
    from document_engine.engine import (
        _should_redo_ocr_for_amounts, ExtractedTextResult,
    )
    from document_engine.models import FieldEvidence

    # 800 + 200 = 1000 vs total = 1050 → deviation 50 (< 100 NOK AND < 10 %)
    evidence = {
        "subtotal_amount": FieldEvidence(field_name="subtotal_amount", normalized_value="800.00"),
        "vat_amount":      FieldEvidence(field_name="vat_amount",      normalized_value="200.00"),
        "total_amount":    FieldEvidence(field_name="total_amount",    normalized_value="1050.00"),
    }
    extracted = ExtractedTextResult(
        text="...", source="pdf_text_fitz", ocr_used=False,
        metadata={"selected_score": 120.0, "candidate_sources": []},
        segments=[],
    )
    # Small deviation at high score → don't burn OCR budget on it
    assert _should_redo_ocr_for_amounts(evidence, extracted) is False


def test_is_redo_extraction_better_prefers_consistent_over_inconsistent() -> None:
    from document_engine.engine import _is_redo_extraction_better
    from document_engine.models import FieldEvidence

    inconsistent = {
        "subtotal_amount": FieldEvidence(field_name="subtotal_amount", normalized_value="800.00"),
        "vat_amount":      FieldEvidence(field_name="vat_amount",      normalized_value="200.00"),
        "total_amount":    FieldEvidence(field_name="total_amount",    normalized_value="5000.00"),
    }
    consistent = {
        "subtotal_amount": FieldEvidence(field_name="subtotal_amount", normalized_value="800.00"),
        "vat_amount":      FieldEvidence(field_name="vat_amount",      normalized_value="200.00"),
        "total_amount":    FieldEvidence(field_name="total_amount",    normalized_value="1000.00"),
    }
    assert _is_redo_extraction_better(consistent, inconsistent) is True
    assert _is_redo_extraction_better(inconsistent, consistent) is False
    # Both consistent → keep the old (no reason to switch, saves avoid thrash)
    assert _is_redo_extraction_better(consistent, consistent) is False


def test_ocrmypdf_redo_candidate_metadata_reports_ocrmypdf_engine() -> None:
    """Regression: the old ``_append_candidate`` checked ``source ==
    'pdf_ocrmypdf'`` exactly, so ``pdf_ocrmypdf_redo`` silently got
    ``ocr_engine='pytesseract'`` despite being an ocrmypdf output."""
    from document_engine.engine import _append_candidate, _TextCandidate

    cands: list[_TextCandidate] = []
    _append_candidate(cands, "pdf_ocrmypdf_redo", ("Brage 1000,00", []), True)
    assert cands, "candidate should have been appended"
    assert cands[0].metadata.get("ocr_engine") == "ocrmypdf"


def test_reload_segments_for_populates_raw_text_and_segments(monkeypatch, tmp_path) -> None:
    """_reload_segments_for must seed BOTH ``_last_segments`` and
    ``_last_raw_text_excerpt`` from the same extraction call, so saving
    without first running 'Les oppl.' still persists non-empty text."""
    from document_engine.engine import ExtractedTextResult, TextSegment
    import document_engine.engine as _engine
    import document_control_review_dialog as _dlg_mod
    from document_control_review_dialog import DocumentControlReviewDialog as _Dlg

    fake_text = "Brage Arkitekter AS\nFaktura 12345\nSum 800,00"
    fake_segments = [TextSegment(text=fake_text, source="pdf_text_fitz", page=1)]

    def _fake_extract(_p, **_kwargs):
        return ExtractedTextResult(
            text=fake_text, source="pdf_text_fitz", ocr_used=False,
            metadata={}, segments=fake_segments,
        )

    # The helper does `from document_engine.engine import extract_text_from_file`
    # at call time, so patch the engine module where the attribute is resolved.
    monkeypatch.setattr(_engine, "extract_text_from_file", _fake_extract)

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    # Bypass Tk __init__ — the helper only touches two instance attributes.
    holder = _Dlg.__new__(_Dlg)
    holder._last_segments = None  # type: ignore[attr-defined]
    holder._last_raw_text_excerpt = ""  # type: ignore[attr-defined]
    _Dlg._reload_segments_for(holder, str(pdf_path))

    assert holder._last_segments == fake_segments  # type: ignore[attr-defined]
    assert holder._last_raw_text_excerpt.startswith("Brage Arkitekter AS")  # type: ignore[attr-defined]


def test_reload_segments_for_resets_state_for_missing_path(tmp_path) -> None:
    from document_control_review_dialog import DocumentControlReviewDialog as _Dlg
    from document_engine.engine import TextSegment

    holder = _Dlg.__new__(_Dlg)
    # Pre-seed stale values to prove the helper clears them
    holder._last_segments = [TextSegment(text="stale", source="x")]  # type: ignore[attr-defined]
    holder._last_raw_text_excerpt = "stale excerpt"  # type: ignore[attr-defined]
    _Dlg._reload_segments_for(holder, None)
    assert holder._last_segments is None  # type: ignore[attr-defined]
    assert holder._last_raw_text_excerpt == ""  # type: ignore[attr-defined]

    # Non-existent path path should also reset, not load
    holder._last_segments = [TextSegment(text="stale", source="x")]  # type: ignore[attr-defined]
    holder._last_raw_text_excerpt = "stale excerpt"  # type: ignore[attr-defined]
    _Dlg._reload_segments_for(holder, str(tmp_path / "does-not-exist.pdf"))
    assert holder._last_segments is None  # type: ignore[attr-defined]
    assert holder._last_raw_text_excerpt == ""  # type: ignore[attr-defined]


def test_analyze_document_triggers_redo_ocr_on_amount_mismatch(monkeypatch, tmp_path) -> None:
    """End-to-end: weak native text gives inconsistent amounts; forced redo
    produces consistent amounts; analyze_document must choose the redo."""
    from document_engine import engine as _engine
    from document_engine.engine import (
        ExtractedTextResult, TextSegment, analyze_document,
    )

    pdf_path = tmp_path / "brage.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    bad_text = "Subtotal 800,00\nMVA 200,00\nTil betaling 5000,00"
    good_text = "Subtotal 800,00\nMVA 200,00\nTil betaling 1 000,00"

    def _fake_extract(path, *, force_ocr_redo=False):
        if force_ocr_redo:
            return ExtractedTextResult(
                text=good_text, source="pdf_ocrmypdf_redo", ocr_used=True,
                metadata={
                    "selected_score": 80.0,
                    "candidate_sources": [{"source": "pdf_ocrmypdf_redo"}],
                    "ocr_engine": "ocrmypdf",
                },
                segments=[TextSegment(text=good_text, source="pdf_ocrmypdf_redo", page=1)],
            )
        return ExtractedTextResult(
            text=bad_text, source="pdf_text_fitz", ocr_used=False,
            metadata={
                "selected_score": 80.0,  # high score, but inconsistent → big-deviation guard
                "candidate_sources": [{"source": "pdf_text_fitz"}],
                "ocr_engine": "text_layer",
            },
            segments=[TextSegment(text=bad_text, source="pdf_text_fitz", page=1)],
        )

    monkeypatch.setattr(_engine, "extract_text_from_file", _fake_extract)

    result = analyze_document(pdf_path)
    assert result.source == "pdf_ocrmypdf_redo", (
        f"expected redo to win; got source={result.source!r}, "
        f"amounts={ {k: v.normalized_value for k, v in result.field_evidence.items() if k.endswith('_amount')} }"
    )
    assert result.metadata.get("ocr_redo_triggered_by") == "amount_mismatch"
    assert result.metadata.get("amount_self_consistent") is True


def test_analyze_document_keeps_original_when_redo_not_better(monkeypatch, tmp_path) -> None:
    """If both native and redo are inconsistent, stay with the original."""
    from document_engine import engine as _engine
    from document_engine.engine import (
        ExtractedTextResult, TextSegment, analyze_document,
    )

    pdf_path = tmp_path / "hopeless.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    # Both texts inconsistent — native says total=5000, redo says total=7000
    bad1 = "Subtotal 800,00\nMVA 200,00\nTil betaling 5000,00"
    bad2 = "Subtotal 800,00\nMVA 200,00\nTil betaling 7000,00"

    def _fake_extract(path, *, force_ocr_redo=False):
        text = bad2 if force_ocr_redo else bad1
        return ExtractedTextResult(
            text=text,
            source="pdf_ocrmypdf_redo" if force_ocr_redo else "pdf_text_fitz",
            ocr_used=force_ocr_redo,
            metadata={
                "selected_score": 80.0,
                "candidate_sources": (
                    [{"source": "pdf_ocrmypdf_redo"}] if force_ocr_redo
                    else [{"source": "pdf_text_fitz"}]
                ),
                "ocr_engine": "ocrmypdf" if force_ocr_redo else "text_layer",
            },
            segments=[TextSegment(
                text=text,
                source="pdf_ocrmypdf_redo" if force_ocr_redo else "pdf_text_fitz",
                page=1,
            )],
        )

    monkeypatch.setattr(_engine, "extract_text_from_file", _fake_extract)

    result = analyze_document(pdf_path)
    assert result.source == "pdf_text_fitz", f"should not promote a still-inconsistent redo; got {result.source}"
    assert result.metadata.get("ocr_redo_attempted") is True
    assert result.metadata.get("ocr_redo_chosen") is False


def test_extract_text_from_pdf_force_redo_overrides_higher_native_score(monkeypatch, tmp_path) -> None:
    """Direct unit test: when ``force_ocr_redo=True``, the redo candidate must
    win even if a native extractor scores higher. Analyze-level logic then
    decides via ``_is_redo_extraction_better`` whether to keep it."""
    from document_engine import engine as _engine
    from document_engine.engine import TextSegment, _extract_text_from_pdf

    pdf_path = tmp_path / "x.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    # Very long, high-quality native text → high score.
    native_text = "Leverandør AS\n" + ("Linje med innhold.\n" * 400)
    native_segments = [TextSegment(text=native_text, source="pdf_text_fitz", page=1)]
    # Shorter redo text → lower score. Under pure scoring, native would win.
    redo_text = "Leverandør AS\nTil betaling 1 000,00 NOK\n"
    redo_segments = [TextSegment(text=redo_text, source="pdf_ocrmypdf_redo", page=1)]

    def _native(_p):
        return native_text, native_segments

    def _empty(_p):
        return "", []

    def _redo(_p, *, mode="skip"):
        if mode == "redo":
            return redo_text, redo_segments
        return "", []

    monkeypatch.setattr(_engine, "_extract_pdf_text_with_pypdf", _native)
    monkeypatch.setattr(_engine, "_extract_pdf_text_with_pdfplumber", _empty)
    monkeypatch.setattr(_engine, "_extract_pdf_text_with_fitz_words", _empty)
    monkeypatch.setattr(_engine, "_extract_pdf_text_with_fitz_blocks", _empty)
    monkeypatch.setattr(_engine, "_extract_pdf_text_with_fitz", _empty)
    monkeypatch.setattr(_engine, "_ocr_pdf_with_ocrmypdf", _redo)
    monkeypatch.setattr(_engine, "_ocr_pdf_with_fitz", _empty)
    monkeypatch.setattr(_engine, "_count_pdf_pages", lambda _p: 1)

    without_redo = _extract_text_from_pdf(pdf_path, force_ocr_redo=False)
    assert without_redo.source == "pdf_text_pypdf", (
        f"sanity: native should win by score when force_ocr_redo is off; "
        f"got {without_redo.source}"
    )

    with_redo = _extract_text_from_pdf(pdf_path, force_ocr_redo=True)
    assert with_redo.source == "pdf_ocrmypdf_redo", (
        f"force_ocr_redo=True must promote the redo candidate despite lower "
        f"score; got {with_redo.source} (candidates: "
        f"{[c['source'] for c in with_redo.metadata.get('candidate_sources', [])]})"
    )


def test_document_analysis_result_to_dict_excludes_segments() -> None:
    """``segments`` is runtime-only and must not appear in ``to_dict`` —
    otherwise persisted JSON would couple to internal engine types and bloat
    on every save."""
    from document_engine.engine import TextSegment
    from document_engine.models import DocumentAnalysisResult, DocumentFacts

    result = DocumentAnalysisResult(
        file_path="x.pdf",
        file_type=".pdf",
        source="pdf_text_fitz",
        facts=DocumentFacts(),
        segments=[TextSegment(text="hello", source="pdf_text_fitz", page=1)],
    )
    payload = result.to_dict()
    assert "segments" not in payload, (
        f"to_dict() leaked runtime segments; keys={sorted(payload.keys())}"
    )
    # Runtime attribute still accessible for in-memory consumers
    assert result.segments and result.segments[0].text == "hello"


def test_reanalyse_uses_analysis_segments_without_calling_reload_helper(monkeypatch) -> None:
    """When analyze_document_for_bilag returns segments, ``_reanalyse`` must
    take them directly from the analysis result and skip
    ``_reload_segments_for``. Calling the helper would re-extract and could
    pick a different candidate than the one analyze_document just chose
    (most importantly: would overwrite a redo-OCR selection with the native
    extraction)."""
    import document_control_app_service as _app_service
    from document_control_review_dialog import DocumentControlReviewDialog as _Dlg
    from document_engine.engine import TextSegment
    from document_engine.models import DocumentAnalysisResult, DocumentFacts

    analysis_segments = [TextSegment(
        text="Til betaling 1 000,00 NOK",
        source="pdf_ocrmypdf_redo",
        page=1,
        bbox=(400.0, 100.0, 480.0, 112.0),
    )]

    def _fake_analyze(path, *, df_bilag=None):
        return DocumentAnalysisResult(
            file_path=str(path),
            file_type=".pdf",
            source="pdf_ocrmypdf_redo",
            facts=DocumentFacts(total_amount="1000.00"),
            raw_text_excerpt="Til betaling 1 000,00 NOK",
            segments=list(analysis_segments),
        )

    monkeypatch.setattr(_app_service, "analyze_document_for_bilag", _fake_analyze)

    reload_calls: list[str] = []

    def _spy_reload(self, path):  # pragma: no cover — failure means called
        reload_calls.append(str(path))

    monkeypatch.setattr(_Dlg, "_reload_segments_for", _spy_reload)

    # Assemble a stand-in holder without running the real Tk __init__.
    class _Var:
        def __init__(self, v=""): self._v = v
        def get(self): return self._v
        def set(self, v): self._v = v

    class _Row:
        bilag_nr = "1"

    class _Preview:
        def search_all_pages(self, _): return []
        def load_file(self, _): pass
        def show_page(self, _): pass
        def highlight_bbox(self, *args, **kwargs): pass

    holder = _Dlg.__new__(_Dlg)
    holder._var_file_path = _Var("any.pdf")
    holder._current_index = 0
    holder._results = [_Row()]
    holder._df_all = None
    holder._var_status_bar = _Var("")
    holder._pdf_state = [{}]
    holder._field_evidence = {}
    holder._last_segments = None
    holder._last_raw_text_excerpt = ""
    holder._suppress_pdf_search = False
    holder.pdf_vars = {}
    holder._preview = _Preview()
    # Path.exists check in _reanalyse — point it at anything that exists
    holder._var_file_path.set(__file__)

    # Minimal stubs for tk-related methods called inside _reanalyse
    holder.configure = lambda **_: None
    holder.update_idletasks = lambda: None

    # Patch the module-level helpers used by _reanalyse (FIELD_DEFS, _bilag_rows)
    import document_control_review_dialog as _dlg_mod
    monkeypatch.setattr(_dlg_mod, "FIELD_DEFS", [], raising=False)
    monkeypatch.setattr(_dlg_mod, "_bilag_rows", lambda _df, _nr: None)

    try:
        _Dlg._reanalyse(holder)
    except Exception as exc:
        # Downstream UI code may still fail on our stub; that's fine. We only
        # care that _reload_segments_for wasn't invoked and _last_segments
        # got seeded from analysis.
        pass

    assert holder._last_segments == analysis_segments, (
        f"analysis.segments must be installed as _last_segments; got {holder._last_segments!r}"
    )
    assert reload_calls == [], (
        f"_reload_segments_for must NOT be called when analysis exposes segments; "
        f"was called with {reload_calls!r}"
    )


def test_ocrmypdf_redo_preserves_word_spans_from_fitz_words(monkeypatch, tmp_path) -> None:
    """Redo-OCR must route through fitz_words and preserve ``word_spans``,
    otherwise profile-hint geometry collapses to line-level bbox on the
    exact invoices where redo was needed (bad native OCR)."""
    from pathlib import Path as _P
    from document_engine import engine as _engine
    from document_engine.engine import TextSegment, _ocr_pdf_with_ocrmypdf

    class _FakeCompleted:
        returncode = 0

    def _fake_run(cmd, **_kwargs):
        return _FakeCompleted()

    # fitz_words returns segments with word_spans + a tight per-value bbox.
    precise_segments = [
        TextSegment(
            text="Til betaling 1 000,00 NOK",
            source="pdf_text_fitz_words",
            page=1,
            bbox=(400.0, 100.0, 480.0, 112.0),
            word_spans=[
                (0, 3,  (50.0, 100.0, 70.0, 112.0)),     # "Til"
                (4, 12, (72.0, 100.0, 130.0, 112.0)),    # "betaling"
                (13, 20, (400.0, 100.0, 440.0, 112.0)),  # "1 000,00"
                (21, 24, (442.0, 100.0, 480.0, 112.0)),  # "NOK"
            ],
        ),
    ]
    precise_text = precise_segments[0].text * 20   # push past _PDF_TEXT_THRESHOLD

    def _fake_fitz_words(_p):
        return precise_text, precise_segments

    monkeypatch.setattr(_engine.shutil, "which", lambda _name: "ocrmypdf")
    monkeypatch.setattr(_engine.subprocess, "run", _fake_run)
    monkeypatch.setattr(_engine, "_extract_pdf_text_with_fitz_words", _fake_fitz_words)
    # Other extractors should never be reached because fitz_words is tried first.
    for name in ("_extract_pdf_text_with_pypdf", "_extract_pdf_text_with_pdfplumber",
                 "_extract_pdf_text_with_fitz_blocks", "_extract_pdf_text_with_fitz"):
        monkeypatch.setattr(_engine, name,
                            lambda _p, _n=name: pytest_fail_if_called(_n))  # type: ignore[name-defined]

    pdf_path = tmp_path / "in.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    text, segments = _ocr_pdf_with_ocrmypdf(pdf_path, mode="redo")

    assert segments, f"redo should return segments; got text_len={len(text)}"
    assert all(s.source == "pdf_ocrmypdf_redo" for s in segments), (
        f"segments must be retagged as pdf_ocrmypdf_redo; got sources="
        f"{[s.source for s in segments]}"
    )
    # word_spans preserved (character offsets + per-word bbox)
    seg = segments[0]
    assert seg.word_spans, "word_spans lost during remap — hint geometry would collapse"
    assert seg.word_spans[-2][2] == (400.0, 100.0, 440.0, 112.0), (
        f"value-word bbox changed during remap: {seg.word_spans[-2]}"
    )
    # Line-level bbox preserved too
    assert seg.bbox == (400.0, 100.0, 480.0, 112.0)


def pytest_fail_if_called(name: str):
    raise AssertionError(f"{name} must not be called when fitz_words already succeeds")

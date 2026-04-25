from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.pages.consolidation.backend.pdf_line_suggestions import suggest_line_basis_from_pdf


def _regnskapslinjer_df() -> pd.DataFrame:
    return pd.DataFrame({
        "regnr": [10, 11, 20],
        "regnskapslinje": ["Eiendeler", "Driftsinntekter", "SUM"],
        "sumpost": [False, False, True],
        "formel": [None, None, "=10+11"],
    })


def test_suggest_line_basis_from_pdf_matches_lines_and_amounts(monkeypatch, tmp_path: Path) -> None:
    from document_engine import engine

    pdf_path = tmp_path / "rapport.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(
        engine,
        "extract_text_from_file",
        lambda _path: engine.ExtractedTextResult(
            text="Eiendeler 1 234,50\nDriftsinntekter (250,00)",
            source="pdf_text_fitz_blocks",
            ocr_used=False,
            segments=[
                engine.TextSegment(text="Eiendeler 1 234,50", source="pdf_text_fitz_blocks", page=1),
                engine.TextSegment(text="Driftsinntekter (250,00)", source="pdf_text_fitz_blocks", page=1),
            ],
        ),
    )

    suggestions = suggest_line_basis_from_pdf(
        pdf_path,
        regnskapslinjer=_regnskapslinjer_df(),
    )

    assert suggestions["regnr"].tolist() == [10, 11]
    assert float(suggestions.iloc[0]["ub"]) == 1234.50
    assert float(suggestions.iloc[1]["ub"]) == -250.0
    assert all(status == "suggested" for status in suggestions["match_status"].tolist())

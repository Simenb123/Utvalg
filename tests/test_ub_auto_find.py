from __future__ import annotations

from types import SimpleNamespace


class _Rect:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


class _FakePage:
    """Minimal fitz.Page-stub for document_control_viewer.find_ub_match_in_pdf."""

    def __init__(self, texts_at: dict[str, list[tuple[float, float, float, float]]]):
        self._texts = texts_at  # { term: [(x0,y0,x1,y1), ...] }

    def search_for(self, term, quads=False):  # noqa: ARG002
        rects = self._texts.get(term, [])
        return [_Rect(*r) for r in rects]


class _FakeDoc:
    def __init__(self, pages: list[_FakePage]):
        self._pages = pages

    def __len__(self):
        return len(self._pages)

    def load_page(self, idx):
        return self._pages[idx]


def test_variant_generation_covers_norwegian_and_english() -> None:
    from src.shared.document_control.viewer import generate_amount_search_variants

    variants = generate_amount_search_variants(954386.28)
    assert "954 386,28" in variants
    assert "954\u00a0386,28" in variants
    assert "954386,28" in variants
    assert "954.386,28" in variants
    assert "954,386.28" in variants
    assert "954386.28" in variants


def test_variant_generation_negative_wraps_with_minus_and_parens() -> None:
    from src.shared.document_control.viewer import generate_amount_search_variants

    variants = generate_amount_search_variants(-1250.0)
    assert any(v.startswith("-") for v in variants)
    assert any(v.startswith("(") and v.endswith(")") for v in variants)


def test_variant_generation_empty_for_bad_input() -> None:
    from src.shared.document_control.viewer import generate_amount_search_variants

    assert generate_amount_search_variants(float("nan")) == []
    assert generate_amount_search_variants(None) == []  # type: ignore[arg-type]


def test_find_ub_match_returns_best_when_keyword_is_near() -> None:
    from src.shared.document_control.viewer import find_ub_match_in_pdf

    # Side 1: én treff for verdien, og ordet "UB" rett ved siden av
    page1 = _FakePage({
        "1 234,56": [(100.0, 200.0, 160.0, 210.0)],
        "UB": [(80.0, 200.0, 95.0, 210.0)],
    })
    doc = _FakeDoc([page1])

    match = find_ub_match_in_pdf(doc, 1234.56)
    assert match is not None
    assert match["page"] == 1
    assert match["bbox"] == (100.0, 200.0, 160.0, 210.0)
    assert match["raw_value"] == "1 234,56"
    assert match["normalized_value"] == 1234.56
    assert match["score"] > 1.0  # keyword proximity boosted


def test_find_ub_match_returns_none_when_no_hit() -> None:
    from src.shared.document_control.viewer import find_ub_match_in_pdf

    page1 = _FakePage({})
    doc = _FakeDoc([page1])
    assert find_ub_match_in_pdf(doc, 9999.99) is None


def test_find_ub_match_returns_none_when_ambiguous() -> None:
    """To treff langt fra stikkord med samme score skal avvises som tvetydig."""
    from src.shared.document_control.viewer import find_ub_match_in_pdf

    page1 = _FakePage({
        "1 234,56": [
            (100.0, 100.0, 160.0, 110.0),
            (500.0, 400.0, 560.0, 410.0),
        ],
        # Ingen stikkord → begge treff får samme score på 1.0
    })
    doc = _FakeDoc([page1])
    assert find_ub_match_in_pdf(doc, 1234.56) is None


def test_find_ub_match_picks_winner_when_one_near_keyword() -> None:
    """Av to treff velges den som er tett på et stikkord."""
    from src.shared.document_control.viewer import find_ub_match_in_pdf

    page1 = _FakePage({
        "1 234,56": [
            (100.0, 100.0, 160.0, 110.0),   # ingen stikkord nær
            (500.0, 400.0, 560.0, 410.0),   # nær "UB"
        ],
        "UB": [(480.0, 400.0, 495.0, 410.0)],
    })
    doc = _FakeDoc([page1])
    match = find_ub_match_in_pdf(doc, 1234.56)
    assert match is not None
    assert match["bbox"][0] == 500.0


def test_find_ub_match_dedupes_across_variants_on_same_bbox() -> None:
    """Flere varianter som treffer nøyaktig samme bbox skal telles som én gruppe."""
    from src.shared.document_control.viewer import find_ub_match_in_pdf

    # Samme bbox for to varianter — skal behandles som én kandidat, ikke tvetydig
    shared = [(100.0, 200.0, 160.0, 210.0)]
    page1 = _FakePage({
        "1 234,56": shared,
        "1234,56": shared,
        "UB": [(80.0, 200.0, 95.0, 210.0)],
    })
    doc = _FakeDoc([page1])
    match = find_ub_match_in_pdf(doc, 1234.56)
    assert match is not None
    assert match["page"] == 1


def test_find_ub_match_handles_none_doc() -> None:
    from src.shared.document_control.viewer import find_ub_match_in_pdf
    assert find_ub_match_in_pdf(None, 100.0) is None


def test_preview_frame_find_ub_match_requires_pdf() -> None:
    """find_ub_match på preview-instans uten lastet PDF returnerer None."""
    from src.shared.document_control.viewer import DocumentPreviewFrame

    # Bruk en SimpleNamespace i stedet for å konstruere et ekte Tk-vindu
    frame = SimpleNamespace(
        _preview_kind="none",
        _pdf_doc=None,
        find_ub_match=DocumentPreviewFrame.find_ub_match.__get__(
            SimpleNamespace(_preview_kind="none", _pdf_doc=None),
            SimpleNamespace,
        ),
    )
    # Direkte bruk av ubound method via __get__ er flakt; test heller rent på instans:
    inst = SimpleNamespace(_preview_kind="none", _pdf_doc=None)
    assert DocumentPreviewFrame.find_ub_match(inst, 100.0) is None


def test_preview_frame_find_ub_match_delegates_to_doc() -> None:
    from src.shared.document_control.viewer import DocumentPreviewFrame

    page1 = _FakePage({
        "1 234,56": [(100.0, 200.0, 160.0, 210.0)],
        "UB": [(80.0, 200.0, 95.0, 210.0)],
    })
    doc = _FakeDoc([page1])
    inst = SimpleNamespace(_preview_kind="pdf", _pdf_doc=doc)
    match = DocumentPreviewFrame.find_ub_match(inst, 1234.56)
    assert match is not None
    assert match["page"] == 1

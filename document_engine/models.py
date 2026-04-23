from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PROFILE_SCHEMA_VERSION = 1
DOCUMENT_FIELD_ORDER = (
    "supplier_name",
    "supplier_orgnr",
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal_amount",
    "vat_amount",
    "total_amount",
    "currency",
    "description",
    "period",
)


@dataclass
class FieldEvidence:
    field_name: str
    normalized_value: str
    raw_value: str = ""
    source: str = ""
    confidence: float = 0.0
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    inferred_from_profile: bool = False
    validated_against_voucher: bool | None = None
    validation_note: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> FieldEvidence | None:
        if not payload:
            return None
        bbox = payload.get("bbox")
        bbox_tuple = tuple(bbox) if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else None
        return cls(
            field_name=str(payload.get("field_name", "") or ""),
            normalized_value=str(payload.get("normalized_value", "") or ""),
            raw_value=str(payload.get("raw_value", "") or ""),
            source=str(payload.get("source", "") or ""),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            page=int(payload["page"]) if payload.get("page") is not None else None,
            bbox=bbox_tuple,
            inferred_from_profile=bool(payload.get("inferred_from_profile", False)),
            validated_against_voucher=payload.get("validated_against_voucher"),
            validation_note=str(payload.get("validation_note", "") or ""),
            metadata=dict(payload.get("metadata", {}) or {}),
        )


@dataclass
class DocumentFacts:
    supplier_name: str = ""
    supplier_orgnr: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    subtotal_amount: str = ""
    vat_amount: str = ""
    total_amount: str = ""
    currency: str = ""
    description: str = ""
    period: str = ""

    def as_dict(self) -> dict[str, str]:
        return {field_name: str(getattr(self, field_name, "") or "") for field_name in DOCUMENT_FIELD_ORDER}

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> DocumentFacts:
        values = dict(payload or {})
        return cls(**{field_name: str(values.get(field_name, "") or "") for field_name in DOCUMENT_FIELD_ORDER})


@dataclass
class SupplierProfile:
    profile_key: str
    supplier_name: str = ""
    supplier_orgnr: str = ""
    aliases: list[str] = field(default_factory=list)
    sample_count: int = 0
    updated_at: str = ""
    source_app: str = ""
    static_fields: dict[str, str] = field(default_factory=dict)
    field_hints: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    schema_version: int = PROFILE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> SupplierProfile | None:
        if not payload:
            return None
        return cls(
            profile_key=str(payload.get("profile_key", "") or ""),
            supplier_name=str(payload.get("supplier_name", "") or ""),
            supplier_orgnr=str(payload.get("supplier_orgnr", "") or ""),
            aliases=[str(item) for item in list(payload.get("aliases", []) or []) if str(item).strip()],
            sample_count=int(payload.get("sample_count", 0) or 0),
            updated_at=str(payload.get("updated_at", "") or ""),
            source_app=str(payload.get("source_app", "") or ""),
            static_fields={str(key): str(value) for key, value in dict(payload.get("static_fields", {}) or {}).items()},
            field_hints={
                str(field_name): [dict(entry) for entry in list(entries or [])]
                for field_name, entries in dict(payload.get("field_hints", {}) or {}).items()
            },
            schema_version=int(payload.get("schema_version", PROFILE_SCHEMA_VERSION) or PROFILE_SCHEMA_VERSION),
        )


@dataclass
class VoucherContext:
    bilag: str = ""
    row_count: int = 0
    texts: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    amounts: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentCandidate:
    path: str
    score: float
    reasons: list[str] = field(default_factory=list)
    root_label: str = ""

    def display_label(self) -> str:
        from pathlib import Path

        base = Path(self.path).name
        label = f"Treff {int(round(self.score))}: {base}"
        if self.root_label:
            label += f" [{self.root_label}]"
        return label

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentAnalysisResult:
    file_path: str
    file_type: str
    source: str
    facts: DocumentFacts = field(default_factory=DocumentFacts)
    raw_text_excerpt: str = ""
    field_evidence: dict[str, FieldEvidence] = field(default_factory=dict)
    validation_messages: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    profile_status: str = "none"
    # Runtime-only: the TextSegment list that backed the selected text
    # extraction. Exposed so callers (review dialog) can learn against the
    # same geometry analyze_document actually used — including after a
    # redo-OCR swap. Intentionally typed as list[Any] and excluded from
    # to_dict() to avoid coupling persisted JSON to internal engine types.
    segments: list[Any] = field(default_factory=list)

    @property
    def fields(self) -> dict[str, str]:
        return self.facts.as_dict()

    @property
    def confidence(self) -> dict[str, float]:
        return {
            field_name: evidence.confidence
            for field_name, evidence in self.field_evidence.items()
            if evidence.normalized_value
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_type": self.file_type,
            "source": self.source,
            "facts": self.facts.as_dict(),
            "fields": self.fields,
            "raw_text_excerpt": self.raw_text_excerpt,
            "field_evidence": {
                field_name: evidence.to_dict()
                for field_name, evidence in self.field_evidence.items()
            },
            "validation_messages": list(self.validation_messages),
            "metadata": dict(self.metadata),
            "profile_status": self.profile_status,
            "confidence": self.confidence,
        }

@dataclass
class TextSegment:
    """A piece of extracted text + geometry on a PDF page.

    Populated by extractors in :mod:`document_engine.extractors` (and
    re-exported from :mod:`document_engine.engine` for back-compat).
    Fields with optional word-level geometry and per-page bilagsprint
    classification live here because the data crosses module boundaries
    between extraction and scoring.
    """
    text: str
    source: str
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    # Optional per-token span info (char_start, char_end_exclusive, word_bbox).
    # char offsets index into ``text``. Only populated by extractors that have
    # word-level geometry (currently ``pdf_text_fitz_words``); other sources
    # leave this empty so callers must fall back to ``bbox``.
    word_spans: list[tuple[int, int, tuple[float, float, float, float]]] = field(default_factory=list)
    # True when this segment comes from a page classified as a Tripletex
    # bilagsprint (accounting cover page). Set by the extractor based on
    # the *whole page's* text — word-level segments can't detect it on
    # their own because a single word-line rarely contains both the
    # "bilag nummer" and "konteringssammendrag" signals.
    is_bilagsprint_page: bool = False


@dataclass
class ExtractedTextResult:
    """Result of picking the best text-extraction candidate for a PDF.

    Produced by the top-level extraction orchestrator; consumed by the
    field-matching layer in :mod:`document_engine.engine`.
    """
    text: str
    source: str
    ocr_used: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    segments: list[TextSegment] = field(default_factory=list)


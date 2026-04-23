"""Public API for ``document_engine``.

This module defines the **stable** surface that external consumers
should rely on. Anything prefixed with an underscore in the submodules
is internal and may change without warning; use the symbols re-exported
here instead.

See ``ARCHITECTURE.md`` for module layout, dependency graph, and the
metadata schema exposed on ``FieldEvidence.metadata`` /
``DocumentAnalysisResult.metadata`` — both are documented there
because they are the primary integration point for ML pipelines.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Data structures — dataclasses that flow through the API
# ---------------------------------------------------------------------------
from .models import (
    DOCUMENT_FIELD_ORDER,
    PROFILE_SCHEMA_VERSION,
    DocumentAnalysisResult,
    DocumentCandidate,
    DocumentFacts,
    ExtractedTextResult,
    FieldEvidence,
    SupplierProfile,
    TextSegment,
    VoucherContext,
)

# ---------------------------------------------------------------------------
# Protocols / Ports — implement these to plug in storage + lookup
# ---------------------------------------------------------------------------
from .ports import (
    AnalysisRunner,
    DocumentLocator,
    DocumentSourceResolver,
    ProfileRepository,
)

# ---------------------------------------------------------------------------
# Orchestration — top-level entry points
# ---------------------------------------------------------------------------
from .engine import (
    analyze_document,
    build_validation_messages,
    extract_invoice_fields_from_text,
    extract_invoice_fields_from_xml,
    extract_text_from_file,
    normalize_bilag_key,
)

# ---------------------------------------------------------------------------
# Profile learning — build + match + apply per-supplier profiles
# ---------------------------------------------------------------------------
from .profiles import (
    apply_supplier_profile,
    build_supplier_profile,
    match_supplier_profile,
    normalize_profile_name,
)

# ---------------------------------------------------------------------------
# Label policy — validation + vocabulary for learned hints
# ---------------------------------------------------------------------------
# These control which labels are accepted into a supplier profile. They
# were previously only reachable via the ``profiles`` submodule; now
# exposed at package root so ML/cleanup pipelines can validate labels
# without importing the whole profiles module.
from .profiles import (
    GLOBAL_PROFILE_KEY,
    LEARNABLE_FIELDS,
    infer_field_hints,
    is_valid_label_for_field,
    normalize_hint_label,
)

# ---------------------------------------------------------------------------
# Search / candidate lookup — find documents on disk for a given voucher
# ---------------------------------------------------------------------------
from .finder import DocumentSearchTerms, build_search_terms, suggest_documents

# ---------------------------------------------------------------------------
# Contracts — job-input / job-output serialisation for external pipelines
# ---------------------------------------------------------------------------
from .contracts import (
    DocumentJobInput,
    DocumentJobOutput,
    document_job_input_to_dict,
    document_job_output_to_dict,
)


__all__ = [
    # Data structures
    "DOCUMENT_FIELD_ORDER",
    "PROFILE_SCHEMA_VERSION",
    "DocumentAnalysisResult",
    "DocumentCandidate",
    "DocumentFacts",
    "ExtractedTextResult",
    "FieldEvidence",
    "SupplierProfile",
    "TextSegment",
    "VoucherContext",
    # Protocols
    "AnalysisRunner",
    "DocumentLocator",
    "DocumentSourceResolver",
    "ProfileRepository",
    # Orchestration
    "analyze_document",
    "build_validation_messages",
    "extract_invoice_fields_from_text",
    "extract_invoice_fields_from_xml",
    "extract_text_from_file",
    "normalize_bilag_key",
    # Profile learning
    "apply_supplier_profile",
    "build_supplier_profile",
    "match_supplier_profile",
    "normalize_profile_name",
    # Label policy
    "GLOBAL_PROFILE_KEY",
    "LEARNABLE_FIELDS",
    "infer_field_hints",
    "is_valid_label_for_field",
    "normalize_hint_label",
    # Search
    "DocumentSearchTerms",
    "build_search_terms",
    "suggest_documents",
    # Contracts
    "DocumentJobInput",
    "DocumentJobOutput",
    "document_job_input_to_dict",
    "document_job_output_to_dict",
]

from __future__ import annotations

from document_engine.models import DocumentCandidate as DocumentSuggestion
from document_control_app_service import (
    LocalClientStoreDocumentSourceResolver,
    client_store,
    suggest_documents_for_bilag,
)


__all__ = [
    "DocumentSuggestion",
    "LocalClientStoreDocumentSourceResolver",
    "client_store",
    "suggest_documents_for_bilag",
]

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import DocumentAnalysisResult, DocumentCandidate, SupplierProfile, VoucherContext
from .finder import DocumentSearchTerms


class ProfileRepository(Protocol):
    def load_profiles(self) -> dict[str, SupplierProfile]:
        ...

    def save_profile(self, profile: SupplierProfile) -> SupplierProfile:
        ...


class DocumentLocator(Protocol):
    def locate(
        self,
        search_roots: list[tuple[Path, str]],
        terms: DocumentSearchTerms,
        *,
        max_results: int = 8,
    ) -> list[DocumentCandidate]:
        ...


class DocumentSourceResolver(Protocol):
    def resolve(self, *, client: str | None, year: str | None) -> list[tuple[Path, str]]:
        ...


class AnalysisRunner(Protocol):
    def analyze(
        self,
        file_path: str | Path,
        *,
        voucher_context: VoucherContext | None = None,
        profiles: dict[str, SupplierProfile] | None = None,
    ) -> DocumentAnalysisResult:
        ...

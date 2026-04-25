"""Readiness and snapshot checks for consolidation."""

from __future__ import annotations

from dataclasses import dataclass, field

import session


@dataclass(frozen=True)
class ReadinessIssue:
    severity: str
    category: str
    message: str
    action: str = ""
    company_id: str = ""
    company_name: str = ""
    action_target: str = ""


@dataclass
class ReadinessReport:
    issues: list[ReadinessIssue] = field(default_factory=list)
    input_digest: str = ""
    last_run_digest: str = ""

    @property
    def blockers(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "blocking")

    @property
    def warnings(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def infos(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "info")

    @property
    def is_stale(self) -> bool:
        return bool(self.input_digest) and self.input_digest != (self.last_run_digest or "")


from . import readiness_checks as _checks
from . import readiness_digest as _digest


def compute_input_digest(page) -> str:
    return _digest.compute_input_digest(page)


def build_readiness_report(page) -> ReadinessReport:
    return _checks.build_readiness_report(page)


def summarize_report(report: ReadinessReport) -> str:
    if not report.issues:
        return "Kontroller: OK"
    parts: list[str] = []
    if report.blockers:
        parts.append(f"{report.blockers} blokk.")
    if report.warnings:
        parts.append(f"{report.warnings} advarsler")
    if report.infos:
        parts.append(f"{report.infos} info")
    if report.is_stale:
        parts.append("utdatert run")
    return "Kontroller: " + " | ".join(parts)

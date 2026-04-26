from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd


TRUE_TEXT = {"1", "true", "ja", "yes", "y", "j"}
FALSE_TEXT = {"0", "false", "nei", "no", "n"}
AMOUNT_EVIDENCE_EXACT = {"exact", "within_tolerance"}
AMOUNT_EVIDENCE_REVIEW = {"exact", "within_tolerance", "near"}


def candidate_text(row: pd.Series | Mapping[str, object], column: str) -> str:
    getter = getattr(row, "get", None)
    if not callable(getter):
        return ""
    try:
        value = getter(column)
    except Exception:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").strip()


def candidate_value(row: pd.Series | Mapping[str, object], column: str) -> object:
    getter = getattr(row, "get", None)
    if not callable(getter):
        return ""
    try:
        return getter(column)
    except Exception:
        return ""


def candidate_bool(row: pd.Series | Mapping[str, object], column: str) -> bool:
    value = candidate_value(row, column)
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in TRUE_TEXT:
            return True
        if text in FALSE_TEXT:
            return False
    return bool(value)


def candidate_tokens(raw: object) -> tuple[str, ...]:
    if isinstance(raw, (list, tuple, set)):
        values = [str(value).strip() for value in raw if str(value).strip()]
    else:
        values = [part.strip() for part in str(raw or "").replace(";", ",").split(",") if part.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


@dataclass(frozen=True)
class CandidateEvidence:
    used_history: bool = False
    used_rulebook: bool = False
    used_usage: bool = False
    used_special_add: bool = False
    used_residual: bool = False
    within_tolerance: bool = False
    amount_evidence: str = ""
    hit_tokens: str = ""
    history_accounts: str = ""
    anchor_signals: str = ""
    match_basis: str = ""
    amount_basis: str = ""
    explain: str = ""

    @property
    def has_name_anchor(self) -> bool:
        anchors = self.anchor_signals.casefold()
        return bool(self.hit_tokens.strip()) or "navnetreff" in anchors

    @property
    def has_semantic_support(self) -> bool:
        return any(
            (
                bool(self.match_basis.strip()),
                bool(self.hit_tokens.strip()),
                bool(self.anchor_signals.strip()),
                self.used_history,
                self.used_rulebook,
                self.used_usage,
                self.used_special_add,
                self.has_name_anchor,
            )
        )

    @property
    def has_amount_support(self) -> bool:
        return bool(self.amount_basis.strip()) or self.amount_evidence in AMOUNT_EVIDENCE_EXACT or self.within_tolerance


def normalize_candidate_evidence(
    row: pd.Series | Mapping[str, object],
    *,
    legacy_explain_fallback: bool = True,
) -> CandidateEvidence:
    """Normalize machine-readable candidate evidence.

    `Explain` is a human display field going forward. While older cached rows may
    still only have encoded tokens there, this is the single compatibility
    boundary allowed to read those tokens.
    """

    explain = candidate_text(row, "Explain")
    explain_cf = explain.casefold()
    anchor_signals = candidate_text(row, "AnchorSignals")
    hit_tokens = candidate_text(row, "HitTokens")
    history_accounts = candidate_text(row, "HistoryAccounts")

    used_history = candidate_bool(row, "UsedHistory") or bool(history_accounts)
    used_rulebook = candidate_bool(row, "UsedRulebook")
    used_usage = candidate_bool(row, "UsedUsage")
    used_special_add = candidate_bool(row, "UsedSpecialAdd")
    used_residual = candidate_bool(row, "UsedResidual")

    if legacy_explain_fallback:
        used_rulebook = used_rulebook or "regel=" in explain_cf
        used_usage = used_usage or "bruk=" in explain_cf
        used_special_add = used_special_add or "special_add" in explain_cf
        if "navn=" in explain_cf and not hit_tokens:
            anchor_signals = ",".join(part for part in (anchor_signals, "navnetreff") if part)

    return CandidateEvidence(
        used_history=bool(used_history),
        used_rulebook=bool(used_rulebook),
        used_usage=bool(used_usage),
        used_special_add=bool(used_special_add),
        used_residual=bool(used_residual),
        within_tolerance=candidate_bool(row, "WithinTolerance"),
        amount_evidence=candidate_text(row, "AmountEvidence").casefold(),
        hit_tokens=hit_tokens,
        history_accounts=history_accounts,
        anchor_signals=anchor_signals,
        match_basis=candidate_text(row, "Matchgrunnlag"),
        amount_basis=candidate_text(row, "Belopsgrunnlag"),
        explain=explain,
    )


def backfill_candidate_evidence_fields(work: pd.DataFrame) -> None:
    if work is None or work.empty:
        return
    for column, default in (
        ("UsedHistory", False),
        ("UsedRulebook", False),
        ("UsedUsage", False),
        ("UsedSpecialAdd", False),
        ("UsedResidual", False),
        ("AmountEvidence", ""),
        ("AnchorSignals", ""),
    ):
        if column not in work.columns:
            work[column] = default

    for idx, row in work.iterrows():
        evidence = normalize_candidate_evidence(row)
        work.at[idx, "UsedHistory"] = evidence.used_history
        work.at[idx, "UsedRulebook"] = evidence.used_rulebook
        work.at[idx, "UsedUsage"] = evidence.used_usage
        work.at[idx, "UsedSpecialAdd"] = evidence.used_special_add
        work.at[idx, "UsedResidual"] = evidence.used_residual
        if not evidence.amount_evidence:
            work.at[idx, "AmountEvidence"] = ""
        if not str(work.at[idx, "AnchorSignals"] or "").strip():
            parts: list[str] = []
            if evidence.has_name_anchor:
                parts.append("navnetreff")
            if evidence.used_usage:
                parts.append("kontobruk")
            if evidence.used_history:
                parts.append("historikk")
            if evidence.used_special_add:
                parts.append("special_add")
            work.at[idx, "AnchorSignals"] = ",".join(dict.fromkeys(parts))


__all__ = [
    "AMOUNT_EVIDENCE_EXACT",
    "AMOUNT_EVIDENCE_REVIEW",
    "CandidateEvidence",
    "backfill_candidate_evidence_fields",
    "candidate_bool",
    "candidate_text",
    "candidate_tokens",
    "candidate_value",
    "normalize_candidate_evidence",
]

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

import classification_config
from a07_feature import AccountUsageFeatures
from a07_feature.suggest.helpers import _konto_in_ranges, _norm_token, _tokenize
from src.shared.regnskap.mapping import normalize_regnskapslinjer


NORMAL_BALANCE_AUTO = "auto"
NORMAL_BALANCE_DEBET = "debet_typisk"
NORMAL_BALANCE_KREDIT = "kredit_typisk"
NORMAL_BALANCE_NEUTRAL = "noytral"

_ALLOWED_BALANCE_HINTS = {
    NORMAL_BALANCE_AUTO,
    NORMAL_BALANCE_DEBET,
    NORMAL_BALANCE_KREDIT,
    NORMAL_BALANCE_NEUTRAL,
}

_GENERIC_TOKENS = {
    "andre",
    "annen",
    "annet",
    "diverse",
    "sum",
    "konto",
    "poster",
    "post",
    "eiendel",
    "eiendeler",
    "gjeld",
    "kontoer",
    "kostnad",
    "kostnader",
    "inntekt",
    "inntekter",
    "av",
    "og",
    "for",
    "til",
    "paa",
    "med",
}

_DEBET_HINT_TOKENS = {
    "bank",
    "fordring",
    "kundefordring",
    "forskudd",
    "lager",
    "goodwill",
    "bygg",
    "inventar",
    "maskin",
    "utstyr",
    "kostnad",
    "loennskostnad",
    "avskrivning",
    "tap",
}

_KREDIT_HINT_TOKENS = {
    "gjeld",
    "skyldig",
    "laan",
    "pensjon",
    "skatt",
    "avgift",
    "inntekt",
    "salg",
    "utbytte",
    "egenkapital",
}


@dataclass(frozen=True)
class RegnskapslinjeSuggestion:
    regnr: int
    regnskapslinje: str
    source: str
    reason: str
    confidence: float
    confidence_bucket: str
    sign_note: str = ""


@dataclass(frozen=True)
class _Candidate:
    regnr: int
    regnskapslinje: str
    aliases: tuple[str, ...]
    alias_tokens: frozenset[str]
    exclude_tokens: frozenset[str]
    usage_tokens: frozenset[str]
    account_ranges: tuple[tuple[int, int], ...]
    normal_balance_hint: str


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _string_list(values: object) -> list[str]:
    if isinstance(values, (list, tuple, set)):
        items = list(values)
    elif _clean_text(values):
        items = str(values).replace(";", "\n").splitlines()
    else:
        items = []
    out: list[str] = []
    for item in items:
        text = _clean_text(item)
        if text and text not in out:
            out.append(text)
    return out


def _parse_ranges(values: object) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for raw_value in _string_list(values):
        text = raw_value.replace(" ", "")
        if "-" not in text:
            continue
        start_text, end_text = text.split("-", 1)
        try:
            start = int(start_text)
            end = int(end_text)
        except Exception:
            continue
        if start > end:
            start, end = end, start
        if (start, end) not in ranges:
            ranges.append((start, end))
    return tuple(ranges)


def _dedupe_tokens(tokens: set[str]) -> frozenset[str]:
    return frozenset(token for token in tokens if token and token not in _GENERIC_TOKENS)


def _confidence_bucket(value: float) -> str:
    normalized = float(value) + 1e-9
    if normalized >= 0.75:
        return "Høy"
    if normalized >= 0.50:
        return "Middels"
    return "Lav"


def _default_balance_hint(label: str) -> str:
    tokens = _dedupe_tokens(_tokenize(label))
    if not tokens:
        return NORMAL_BALANCE_AUTO
    if tokens & _KREDIT_HINT_TOKENS:
        return NORMAL_BALANCE_KREDIT
    if tokens & _DEBET_HINT_TOKENS:
        return NORMAL_BALANCE_DEBET
    return NORMAL_BALANCE_AUTO


def _normalize_balance_hint(value: object, *, label: str = "") -> str:
    text = _norm_token(_clean_text(value))
    if text in _ALLOWED_BALANCE_HINTS:
        return text
    if text == "debet":
        return NORMAL_BALANCE_DEBET
    if text == "kredit":
        return NORMAL_BALANCE_KREDIT
    if text == "neutral":
        return NORMAL_BALANCE_NEUTRAL
    return _default_balance_hint(label)


def normalize_rulebook_document(document: Any) -> dict[str, Any]:
    base = dict(document) if isinstance(document, dict) else {}
    rules_out: dict[str, dict[str, Any]] = {}
    raw_rules = base.get("rules", {})
    if isinstance(raw_rules, dict):
        for key, payload in raw_rules.items():
            regnr = _clean_text(key)
            if not regnr.isdigit() or not isinstance(payload, dict):
                continue
            label = _clean_text(payload.get("label"))
            aliases = _string_list(payload.get("aliases"))
            exclude_aliases = _string_list(payload.get("exclude_aliases"))
            usage_keywords = _string_list(payload.get("usage_keywords"))
            account_ranges = list(_parse_ranges(payload.get("account_ranges")))
            normalized: dict[str, Any] = {}
            if label:
                normalized["label"] = label
            if aliases:
                normalized["aliases"] = aliases
            if exclude_aliases:
                normalized["exclude_aliases"] = exclude_aliases
            if usage_keywords:
                normalized["usage_keywords"] = usage_keywords
            if account_ranges:
                normalized["account_ranges"] = [f"{start}-{end}" for start, end in account_ranges]
            balance_hint = _normalize_balance_hint(payload.get("normal_balance_hint"), label=label)
            if balance_hint != NORMAL_BALANCE_AUTO:
                normalized["normal_balance_hint"] = balance_hint
            rules_out[regnr] = normalized
    base["rules"] = rules_out
    meta = base.get("meta")
    if isinstance(meta, dict):
        base["meta"] = meta
    return base


def load_rulebook_document() -> dict[str, Any]:
    return normalize_rulebook_document(
        classification_config.load_json(classification_config.resolve_regnskapslinje_rulebook_path(), fallback={})
    )


def save_rulebook_document(document: Any):
    normalized = normalize_rulebook_document(document)
    return classification_config.save_regnskapslinje_rulebook_document(normalized)


def _candidate_aliases(rule_payload: Mapping[str, Any], label: str) -> tuple[str, ...]:
    aliases = []
    label_text = _clean_text(rule_payload.get("label") or label)
    if label_text:
        aliases.append(label_text)
    aliases.extend(_string_list(rule_payload.get("aliases")))
    out: list[str] = []
    for alias in aliases:
        text = _clean_text(alias)
        if text and text not in out:
            out.append(text)
    return tuple(out)


def build_candidates(
    regnskapslinjer: pd.DataFrame | None,
    *,
    rulebook_document: Mapping[str, Any] | None = None,
) -> list[_Candidate]:
    if regnskapslinjer is None or not isinstance(regnskapslinjer, pd.DataFrame) or regnskapslinjer.empty:
        return []
    try:
        normalized = normalize_regnskapslinjer(regnskapslinjer)
    except Exception:
        return []
    rules = {}
    if isinstance(rulebook_document, Mapping):
        raw_rules = rulebook_document.get("rules", {})
        if isinstance(raw_rules, Mapping):
            rules = raw_rules
    candidates: list[_Candidate] = []
    for _, row in normalized.loc[~normalized["sumpost"]].sort_values("regnr").iterrows():
        regnr = int(row["regnr"])
        label = _clean_text(row.get("regnskapslinje"))
        payload = rules.get(str(regnr), {}) if isinstance(rules, Mapping) else {}
        payload = payload if isinstance(payload, Mapping) else {}
        aliases = _candidate_aliases(payload, label)
        alias_tokens = set()
        for alias in aliases:
            alias_tokens.update(_tokenize(alias))
        exclude_tokens = set()
        for alias in _string_list(payload.get("exclude_aliases")):
            exclude_tokens.update(_tokenize(alias))
        usage_tokens = set()
        for token in _string_list(payload.get("usage_keywords")):
            usage_tokens.update(_tokenize(token))
        candidates.append(
            _Candidate(
                regnr=regnr,
                regnskapslinje=label,
                aliases=aliases,
                alias_tokens=_dedupe_tokens(alias_tokens),
                exclude_tokens=_dedupe_tokens(exclude_tokens),
                usage_tokens=_dedupe_tokens(usage_tokens),
                account_ranges=_parse_ranges(payload.get("account_ranges")),
                normal_balance_hint=_normalize_balance_hint(
                    payload.get("normal_balance_hint"),
                    label=str(payload.get("label") or label),
                ),
            )
        )
    return candidates


def _sign_value(*, ub: float, movement: float, ib: float) -> float:
    for value in (ub, movement, ib):
        try:
            amount = float(value or 0.0)
        except Exception:
            amount = 0.0
        if abs(amount) > 0.005:
            return amount
    return 0.0


def _sign_note(*, hint: str, ub: float, movement: float, ib: float) -> tuple[float, str]:
    if hint not in {NORMAL_BALANCE_DEBET, NORMAL_BALANCE_KREDIT}:
        return 0.0, ""
    value = _sign_value(ub=ub, movement=movement, ib=ib)
    if abs(value) <= 0.005:
        return 0.0, ""
    expected_positive = hint == NORMAL_BALANCE_DEBET
    matches = value > 0 if expected_positive else value < 0
    if matches:
        return 0.08, "Fortegn passer med forventet normalbalanse."
    return -0.08, "Fortegn avviker fra forventet normalbalanse, men blokkerer ikke forslaget."


def suggest_with_candidates(
    candidates: list[_Candidate],
    *,
    konto: str,
    kontonavn: str,
    ib: float = 0.0,
    movement: float = 0.0,
    ub: float = 0.0,
    usage: AccountUsageFeatures | None = None,
    historical_regnr: int | None = None,
) -> RegnskapslinjeSuggestion | None:
    """Score forhåndsbygde kandidater mot konto+navn+bruk og returner beste forslag.

    Trukket ut fra ``suggest_regnskapslinje`` slik at kallere som behandler
    mange kontoer (f.eks. ``enrich_rl_mapping_issues_with_suggestions``)
    kan bygge kandidatene én gang og gjenbruke dem.
    """
    if not candidates:
        return None

    account_tokens = _dedupe_tokens(_tokenize(kontonavn))
    usage_tokens = _dedupe_tokens(set(getattr(usage, "top_text_tokens", ()) or ()))
    best: RegnskapslinjeSuggestion | None = None
    best_score = -10.0

    for candidate in candidates:
        score = 0.0
        reasons: list[str] = []

        alias_hits = sorted(account_tokens & candidate.alias_tokens)
        if alias_hits:
            score += min(0.52, 0.18 + (0.12 * len(alias_hits)))
            reasons.append(f"navn/alias: {', '.join(alias_hits[:3])}")

        exclude_hits = sorted((account_tokens | usage_tokens) & candidate.exclude_tokens)
        if exclude_hits:
            score -= min(0.40, 0.18 + (0.10 * len(exclude_hits)))
            reasons.append(f"negativt alias: {', '.join(exclude_hits[:2])}")

        usage_hits = sorted(usage_tokens & candidate.usage_tokens)
        if usage_hits:
            score += min(0.24, 0.12 + (0.08 * len(usage_hits)))
            reasons.append(f"kontobruk: {', '.join(usage_hits[:3])}")

        if candidate.account_ranges and _konto_in_ranges(konto, candidate.account_ranges):
            score += 0.16
            reasons.append("konto-intervall")

        if historical_regnr is not None and int(historical_regnr) == candidate.regnr:
            score += 0.48
            reasons.append("historikk")

        sign_score, sign_text = _sign_note(hint=candidate.normal_balance_hint, ub=ub, movement=movement, ib=ib)
        score += sign_score

        if not reasons and abs(sign_score) < 1e-9:
            continue

        score = max(0.0, min(score, 1.0))
        if score < 0.45:
            continue

        if historical_regnr is not None and int(historical_regnr) == candidate.regnr and not alias_hits and not usage_hits:
            source = "historikk"
        elif alias_hits and usage_hits:
            source = "alias+kontobruk"
        elif alias_hits:
            source = "alias"
        elif usage_hits:
            source = "kontobruk"
        elif candidate.account_ranges and _konto_in_ranges(konto, candidate.account_ranges):
            source = "konto_intervall"
        else:
            source = "heuristikk"

        if sign_text:
            reasons.append(sign_text)
        reason_text = "; ".join(reasons) if reasons else "Ingen tydelige signaler."
        suggestion = RegnskapslinjeSuggestion(
            regnr=candidate.regnr,
            regnskapslinje=candidate.regnskapslinje,
            source=source,
            reason=reason_text,
            confidence=score,
            confidence_bucket=_confidence_bucket(score),
            sign_note=sign_text,
        )
        if score > best_score:
            best = suggestion
            best_score = score

    return best


def suggest_regnskapslinje(
    *,
    konto: str,
    kontonavn: str,
    ib: float = 0.0,
    movement: float = 0.0,
    ub: float = 0.0,
    regnskapslinjer: pd.DataFrame | None,
    rulebook_document: Mapping[str, Any] | None = None,
    usage: AccountUsageFeatures | None = None,
    historical_regnr: int | None = None,
) -> RegnskapslinjeSuggestion | None:
    """Bygg kandidater og kall ``suggest_with_candidates``.

    Bakoverkompat-wrapper for kallere som ikke har grunn til å gjenbruke
    kandidatene mellom kontoer. Bruk ``build_candidates`` +
    ``suggest_with_candidates`` direkte når du itererer over mange kontoer.
    """
    candidates = build_candidates(regnskapslinjer, rulebook_document=rulebook_document)
    return suggest_with_candidates(
        candidates,
        konto=konto,
        kontonavn=kontonavn,
        ib=ib,
        movement=movement,
        ub=ub,
        usage=usage,
        historical_regnr=historical_regnr,
    )

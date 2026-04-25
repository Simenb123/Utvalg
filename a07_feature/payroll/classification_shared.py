from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from a07_feature.control.rf1022_bridge import RF1022_GROUP_LABELS
from a07_feature.suggest.api import _tokenize
from a07_feature.suggest.rulebook import RulebookRule, clear_rulebook_cache, load_rulebook
from account_profile import AccountProfileSuggestion

PAYROLL_RF1022_GROUPS: dict[str, str] = {
    group_id: RF1022_GROUP_LABELS[group_id]
    for group_id in ("100_loenn_ol", "100_refusjon", "111_naturalytelser", "112_pensjon")
}

PAYROLL_TAG_LABELS: dict[str, str] = {
    "opplysningspliktig": "Opplysningspliktig",
    "aga_pliktig": "AGA-pliktig",
    "finansskatt_pliktig": "Finansskatt-pliktig",
    "feriepengergrunnlag": "Feriepengegrunnlag",
    "refusjon": "Refusjon",
    "naturalytelse": "Naturalytelse",
    "pensjon": "Pensjon",
    "styrehonorar": "Styrehonorar",
}

PAYROLL_GROUP_IDS = tuple(PAYROLL_RF1022_GROUPS.keys())
PAYROLL_TAG_IDS = tuple(PAYROLL_TAG_LABELS.keys())

PAYROLL_CODE_DEFAULTS: dict[str, dict[str, tuple[str, ...] | str]] = {
    "fastloenn": {
        "control_group": "100_loenn_ol",
        "control_tags": ("opplysningspliktig", "aga_pliktig", "feriepengergrunnlag"),
    },
    "feriepenger": {
        "control_group": "100_loenn_ol",
        "control_tags": ("opplysningspliktig", "aga_pliktig"),
    },
    "tilskuddOgPremieTilPensjon": {
        "control_group": "112_pensjon",
        "control_tags": ("pensjon",),
    },
    "sumAvgiftsgrunnlagRefusjon": {
        "control_group": "100_refusjon",
        "control_tags": ("refusjon",),
    },
    "elektroniskKommunikasjon": {
        "control_group": "111_naturalytelser",
        "control_tags": ("naturalytelse", "opplysningspliktig", "aga_pliktig"),
    },
    "bil": {
        "control_group": "111_naturalytelser",
        "control_tags": ("naturalytelse", "opplysningspliktig", "aga_pliktig"),
    },
    "yrkebilTjenstligbehovListepris": {
        "control_group": "111_naturalytelser",
        "control_tags": ("naturalytelse", "opplysningspliktig", "aga_pliktig"),
    },
    "skattepliktigDelForsikringer": {
        "control_group": "111_naturalytelser",
        "control_tags": ("naturalytelse", "opplysningspliktig", "aga_pliktig"),
    },
    "styrehonorarOgGodtgjoerelseVerv": {
        "control_group": "100_loenn_ol",
        "control_tags": ("opplysningspliktig", "aga_pliktig", "styrehonorar"),
    },
}

_DIRECT_NAME_HINTS: tuple[tuple[str, tuple[str, ...], float, str], ...] = (
    ("tilskuddOgPremieTilPensjon", ("pensjon", "otp"), 0.96, "Navnemønster: pensjon"),
    ("sumAvgiftsgrunnlagRefusjon", ("refusjon", "sykepenger", "foreldrepenger"), 0.96, "Navnemønster: refusjon"),
    ("elektroniskKommunikasjon", ("telefon", "mobil", "ekom"), 0.93, "Navnemønster: elektronisk kommunikasjon"),
    ("skattepliktigDelForsikringer", ("forsikring", "helseforsikring"), 0.92, "Navnemønster: forsikring"),
    ("styrehonorarOgGodtgjoerelseVerv", ("styre", "honorar", "verv"), 0.92, "Navnemønster: styrehonorar"),
    ("bil", ("firmabil", "bil"), 0.9, "Navnemønster: bil"),
)

_PAYROLL_TOKENS = (
    "lønn",
    "lonn",
    "ferie",
    "pensjon",
    "otp",
    "telefon",
    "mobil",
    "ekom",
    "forsikring",
    "bil",
    "honorar",
    "styre",
    "refusjon",
    "sykepenger",
    "forskuddstrekk",
    "aga",
    "arbeidsgiveravgift",
)

_DIRECT_HINT_SCORES: dict[str, float] = {
    "tilskuddOgPremieTilPensjon": 0.96,
    "sumAvgiftsgrunnlagRefusjon": 0.96,
    "elektroniskKommunikasjon": 0.93,
    "skattepliktigDelForsikringer": 0.92,
    "styrehonorarOgGodtgjoerelseVerv": 0.92,
    "bil": 0.90,
    "yrkebilTjenstligbehovListepris": 0.90,
}

_PAYROLL_MIN_RULEBOOK_CONFIDENCE = 0.85
_PAYROLL_MIN_ALIAS_CONFIDENCE = 0.90
_PAYROLL_MIN_GENERIC_CONFIDENCE = 0.90
_STRONG_BALANCE_SHEET_PAYROLL_TOKENS = (
    "refusjon",
    "sykepenger",
    "feriepenger",
    "feriepengegjeld",
    "lonn",
    "lønn",
    "aga",
    "arbeidsgiveravgift",
    "forskuddstrekk",
    "skattetrekk",
    "trekk",
    "pensjon",
    "otp",
)
_BANK_ACCOUNT_NAME_TOKENS = (
    "bank",
    "sparekonto",
    "bedriftskonto",
    "mastercard",
    "visa",
    "kassekreditt",
)
_EQUITY_ACCOUNT_NAME_TOKENS = (
    "aksjekapital",
    "overkursfond",
    "egne aksjer",
    "egenkapital",
)
_VAT_OR_SETTLEMENT_NAME_TOKENS = (
    "merverdiavgift",
    "oppgjørskonto",
    "oppgjorskonto",
    "forhandsskatt",
    "forhåndsskatt",
)


_NON_PAYROLL_OPERATING_EXPENSE_TOKENS = (
    "leie",
    "lokale",
    "husleie",
    "parkering",
    "felleskostnad",
    "bodleie",
    "lys",
    "varme",
    "renhold",
    "frakt",
    "transport",
    "forsendelse",
    "inventar",
    "maskin",
    "kontormaskin",
    "datasystem",
    "datautstyr",
    "hardware",
    "software",
    "programvare",
    "rekvisita",
    "revisjon",
    "regnskap",
    "juridisk",
    "advokat",
    "vedlikehold",
    "service",
    "kontor",
)
_STRONG_EXPENSE_PAYROLL_NAME_TOKENS = (
    "lÃ¸nn",
    "lonn",
    "ferie",
    "pensjon",
    "otp",
    "telefon",
    "mobil",
    "ekom",
    "forsikring",
    "bil",
    "styre",
    "styrehonorar",
    "verv",
    "refusjon",
    "sykepenger",
    "forskuddstrekk",
    "aga",
    "arbeidsgiveravgift",
    "ansatt",
    "ansatte",
    "personalkostnad",
    "personalkostnader",
    "personell",
)

@dataclass(frozen=True)
class PayrollSuggestionResult:
    suggestions: dict[str, AccountProfileSuggestion]
    payroll_relevant: bool
    payroll_status: str
    unclear_reason: str | None = None
    has_strict_auto: bool = False
    is_unclear: bool = False


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_text_shared(value: object) -> str:
    text = _clean_text(value).casefold()
    replacements = {
        "ø": "o",
        "æ": "ae",
        "å": "a",
        "Ã¸": "o",
        "Ã¦": "ae",
        "Ã¥": "a",
        "-": " ",
        "_": " ",
        "/": " ",
        ",": " ",
        ".": " ",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return " ".join(text.split())


def _normalize_text(value: object) -> str:
    text = _clean_text(value).casefold()
    replacements = {
        "ø": "o",
        "æ": "ae",
        "å": "a",
        "-": " ",
        "_": " ",
        "/": " ",
        ",": " ",
        ".": " ",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return " ".join(text.split())


def _normalized_phrase_match(text_norm: str, term: object) -> bool:
    candidate = _normalize_text_shared(term)
    if not candidate:
        return False
    text_tokens = tuple(token for token in text_norm.split() if token)
    candidate_tokens = tuple(token for token in candidate.split() if token)
    if not candidate_tokens:
        return False
    if len(candidate_tokens) > 1:
        return f" {candidate} " in f" {text_norm} "
    needle = candidate_tokens[0]
    for token in text_tokens:
        if token == needle:
            return True
        if len(needle) >= 5 and (token.startswith(needle) or token.endswith(needle)):
            return True
    return False


def _matching_terms(text_norm: str, terms: Iterable[object]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        if _normalized_phrase_match(text_norm, term):
            cleaned = _clean_text(term)
            if cleaned and cleaned not in hits:
                hits.append(cleaned)
    return hits


def _has_strong_expense_payroll_signal(name_norm: str) -> bool:
    return bool(_matching_terms(name_norm, _STRONG_EXPENSE_PAYROLL_NAME_TOKENS))


def _has_non_payroll_operating_expense_signal(name_norm: str) -> bool:
    return bool(_matching_terms(name_norm, _NON_PAYROLL_OPERATING_EXPENSE_TOKENS))


def _code_tokens_for_rule(code: str, rule: RulebookRule | None) -> set[str]:
    tokens = _tokenize(str(code or ""))
    if rule is not None:
        tokens |= _tokenize(str(rule.label or ""))
        for keyword in tuple(rule.keywords or ()):
            tokens |= _tokenize(str(keyword or ""))
    return tokens


def _to_number(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean_text(value).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _account_no_int(account_no: str) -> int | None:
    try:
        return int(str(account_no).strip())
    except Exception:
        return None


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


_DEFAULT_RULEBOOK_CACHE: Mapping[str, RulebookRule] | None = None


def invalidate_runtime_caches() -> None:
    global _DEFAULT_RULEBOOK_CACHE
    _DEFAULT_RULEBOOK_CACHE = None
    clear_rulebook_cache()


def _default_rulebook() -> Mapping[str, RulebookRule]:
    global _DEFAULT_RULEBOOK_CACHE
    if _DEFAULT_RULEBOOK_CACHE is None:
        try:
            _DEFAULT_RULEBOOK_CACHE = load_rulebook(None)
        except Exception:
            _DEFAULT_RULEBOOK_CACHE = {}
    return _DEFAULT_RULEBOOK_CACHE or {}


def _in_allowed_ranges(account_no: str, ranges: Sequence[tuple[int, int]] | None) -> bool:
    konto_i = _account_no_int(account_no)
    if konto_i is None or not ranges:
        return False
    return any(start <= konto_i <= end for start, end in ranges)

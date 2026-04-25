from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


SAFE_EXACT = "safe_exact"
REVIEW_EXACT = "review_exact"
NO_SAFE_WHOLE_ACCOUNT_SOLUTION = "no_safe_whole_account_solution"
ALREADY_BALANCED = "already_balanced"

SCENARIO_SAFE_EXACT = "Trygg løsning"
SCENARIO_REVIEW = "Må vurderes"
SCENARIO_GROUP = "Krever gruppe"
SCENARIO_SPLIT = "Krever splitt"
SCENARIO_SUSPICIOUS = "Mistenkelig rest"

WEAK_MAPPING_STATUSES = {"", "Feil", "Mistenkelig", "Uavklart"}
SAFE_MAPPING_STATUSES = {"Trygg"}
RESIDUAL_REVIEW_CODES = {"annet"}


@dataclass(frozen=True)
class ResidualAccountCandidate:
    account: str
    name: str
    amount_cents: int
    current_code: str
    audit_status: str
    source: str


@dataclass(frozen=True)
class ResidualChange:
    account: str
    from_code: str
    to_code: str
    amount_cents: int
    reason: str


@dataclass(frozen=True)
class ResidualNearMatch:
    accounts: tuple[str, ...]
    amount_cents: int
    diff_after_cents: int


@dataclass(frozen=True)
class ResidualCodeResult:
    code: str
    diff_cents: int
    status: str
    exact_accounts: tuple[str, ...] = ()
    near_matches: tuple[ResidualNearMatch, ...] = ()
    review_required: bool = False
    explanation: str = ""


@dataclass(frozen=True)
class ResidualSuspiciousAccount:
    account: str
    name: str
    code: str
    amount_cents: int
    reason: str


@dataclass(frozen=True)
class ResidualGroupScenario:
    codes: tuple[str, ...]
    diff_cents: int
    accounts: tuple[str, ...] = ()
    amount_cents: int = 0
    diff_after_cents: int = 0
    reason: str = ""


@dataclass(frozen=True)
class ResidualAnalysis:
    status: str
    auto_safe: bool
    changes: tuple[ResidualChange, ...]
    total_diff_before_cents: int
    total_diff_after_cents: int
    affected_codes: tuple[str, ...]
    explanation: str
    code_results: tuple[ResidualCodeResult, ...]
    suspicious_accounts: tuple[ResidualSuspiciousAccount, ...] = ()
    group_scenarios: tuple[ResidualGroupScenario, ...] = ()
    review_required: bool = False


def amount_to_cents(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        amount = value
    else:
        text = str(value).strip()
        if not text:
            return 0
        text = text.replace("\xa0", " ").replace(" ", "")
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        try:
            amount = Decimal(text)
        except (InvalidOperation, ValueError):
            return 0
    return int((amount.quantize(Decimal("0.01")) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def cents_to_display(value: int) -> str:
    sign = "-" if int(value) < 0 else ""
    cents_abs = abs(int(value))
    whole, cents = divmod(cents_abs, 100)
    whole_text = f"{whole:,}".replace(",", " ")
    return f"{sign}{whole_text},{cents:02d}"


__all__ = [
    "ALREADY_BALANCED",
    "NO_SAFE_WHOLE_ACCOUNT_SOLUTION",
    "RESIDUAL_REVIEW_CODES",
    "REVIEW_EXACT",
    "SAFE_EXACT",
    "SAFE_MAPPING_STATUSES",
    "SCENARIO_GROUP",
    "SCENARIO_REVIEW",
    "SCENARIO_SAFE_EXACT",
    "SCENARIO_SPLIT",
    "SCENARIO_SUSPICIOUS",
    "WEAK_MAPPING_STATUSES",
    "ResidualAccountCandidate",
    "ResidualAnalysis",
    "ResidualChange",
    "ResidualCodeResult",
    "ResidualGroupScenario",
    "ResidualNearMatch",
    "ResidualSuspiciousAccount",
    "amount_to_cents",
    "cents_to_display",
]

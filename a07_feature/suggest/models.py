from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Optional, Set, Tuple


EXCLUDED_A07_CODES: Set[str] = {
    "aga",
    "forskuddstrekk",
    "forskuddstrekkarbeidstaker",
    "forskuddstrekk_arbeidstaker",
    "forskuddstrekk arbeidstaker",
}

PAYROLL_TOKENS: Set[str] = {
    "loenn",
    "fastloenn",
    "bonus",
    "feriepenger",
    "timeloenn",
    "overtid",
    "arbeidsgiveravgift",
    "aga",
    "forskuddstrekk",
    "trekk",
    "skatt",
    "sosial",
    "forsikring",
    "pensjon",
    "kilometergodtgjoerelse",
    "kommunikasjon",
    "telefon",
    "mobil",
    "naturalytelse",
    "fordel",
    "refusjon",
}

BASIS_UB = "UB"
BASIS_IB = "IB"
BASIS_ENDRING = "Endring"
BASIS_DEBET = "Debet"
BASIS_KREDIT = "Kredit"

BASIS_ALIASES: Dict[str, Tuple[str, ...]] = {
    BASIS_UB: ("ub", "closing", "closingbalance", "saldo", "ending", "utgaende"),
    BASIS_IB: ("ib", "opening", "openingbalance", "inngaaende"),
    BASIS_ENDRING: ("endring", "movement", "bevegelse", "delta", "period", "net"),
    BASIS_DEBET: ("debet", "debit", "dr"),
    BASIS_KREDIT: ("kredit", "credit", "cr"),
}

SUGGEST_OUT_COLUMNS: Tuple[str, ...] = (
    "Kode",
    "KodeNavn",
    "Basis",
    "A07_Belop",
    "ForslagKontoer",
    "GL_Sum",
    "Diff",
    "Score",
    "ComboSize",
    "WithinTolerance",
    "HitTokens",
    "HistoryAccounts",
    "Explain",
)


@dataclass(frozen=True)
class SuggestionRow:
    code: str
    accounts: Tuple[str, ...]
    gl_sum: float
    diff: float
    score: float
    within_tolerance: bool
    hit_tokens: Tuple[str, ...] = ()

    @property
    def gl_kontoer(self) -> list[str]:
        return [str(x) for x in self.accounts]

    @classmethod
    def from_df_row(cls, row: Any) -> "SuggestionRow":
        code = str(getattr(row, "get", lambda k, d=None: d)("Kode", "") or "").strip()
        konto_str = str(getattr(row, "get", lambda k, d=None: d)("ForslagKontoer", "") or "").strip()
        konto_tokens = [t.strip() for t in re.split(r"[+,;]+", konto_str) if t.strip()]

        def _num(name: str, default: float = 0.0) -> float:
            try:
                value = getattr(row, "get", lambda k, d=None: d)(name, default)
                if value is None or value == "":
                    return float(default)
                return float(value)
            except Exception:
                return float(default)

        hit = getattr(row, "get", lambda k, d=None: d)("HitTokens", ())
        if isinstance(hit, (list, tuple, set)):
            hit_tokens = tuple(str(x) for x in hit)
        else:
            hit_tokens = tuple(t for t in str(hit).split() if t)

        return cls(
            code=code,
            accounts=tuple(konto_tokens),
            gl_sum=_num("GL_Sum", 0.0),
            diff=_num("Diff", 0.0),
            score=_num("Score", 0.0),
            within_tolerance=bool(getattr(row, "get", lambda k, d=None: d)("WithinTolerance", False)),
            hit_tokens=hit_tokens,
        )


@dataclass
class SuggestConfig:
    max_combo: int = 2
    candidates_per_code: int = 20
    top_suggestions_per_code: int = 5
    top_codes: int = 30

    exclude_mapped_accounts: bool = True
    override_existing_mapping: bool = False
    use_residual: bool = True
    hide_solved_codes: bool = True

    filter_mode: str = "a07"
    basis_strategy: str = "per_code"
    basis: str = BASIS_UB
    basis_by_code: Dict[str, str] = field(default_factory=dict)

    tolerance_rel: float = 0.02
    tolerance_abs: float = 100.0

    rulebook_path: Optional[str] = None
    historical_account_boost: float = 0.12
    historical_combo_boost: float = 0.10

    basis_col: Optional[str] = None
    max_candidates_per_code: Optional[int] = None
    override_existing: Optional[bool] = None
    top_per_code: Optional[int] = None

    exclude_codes: Optional[Set[str]] = None
    exclude_tokens: Optional[Set[str]] = None
    filter_prefixes: Optional[Tuple[str, ...]] = None

    def __post_init__(self) -> None:
        if self.basis_by_code is None:
            self.basis_by_code = {}
        if self.exclude_codes is None:
            self.exclude_codes = set()
        if self.exclude_tokens is None:
            self.exclude_tokens = set()
        if self.filter_prefixes is None:
            self.filter_prefixes = ()

        if self.basis_col:
            self.basis = str(self.basis_col)

        if self.max_candidates_per_code is not None and self.candidates_per_code == 20:
            self.candidates_per_code = int(self.max_candidates_per_code)

        if self.override_existing is not None and self.override_existing_mapping is False:
            self.override_existing_mapping = bool(self.override_existing)

        if self.top_per_code is not None:
            self.top_suggestions_per_code = int(self.top_per_code)

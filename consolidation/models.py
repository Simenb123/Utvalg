"""consolidation.models – Dataklasser for konsolidering.

Hierarki:
    ConsolidationProject
      ├── companies: [CompanyTB]
      ├── mapping_config: MappingConfig
      ├── eliminations: [EliminationJournal]
      │     └── lines: [EliminationLine]
      ├── runs: [RunResult]
      └── suggestion state (ignored/applied keys)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Company TB
# ---------------------------------------------------------------------------

@dataclass
class CompanyTB:
    """En importert saldobalanse for ett selskap."""

    company_id: str = field(default_factory=_new_id)
    name: str = ""
    source_file: str = ""
    source_type: str = ""          # "excel" | "csv" | "saft" | "rl_excel" | "rl_csv" | "pdf_regnskap"
    basis_type: str = "tb"         # "tb" | "regnskapslinje"
    imported_at: float = field(default_factory=_now)
    row_count: int = 0
    has_ib: bool = False
    # Valuta — tom streng betyr same as reporting_currency (NOK default)
    currency_code: str = ""
    closing_rate: float = 1.0      # sluttkurs (balanse)
    average_rate: float = 1.0      # snittkurs (resultat)

    @property
    def is_line_basis(self) -> bool:
        return str(self.basis_type or "").strip().lower() == "regnskapslinje"


def _default_associate_line_mapping() -> dict[str, int]:
    return {
        "investment_regnr": 575,
        "result_regnr": 100,
        "other_equity_regnr": 695,
        "retained_earnings_regnr": 705,
    }


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

@dataclass
class MappingConfig:
    """Felles mapping-konfigurasjon for konsolideringsprosjektet.

    Alle selskaper bruker samme globale intervaller + regnskapslinjer
    fra regnskap_config. Per-selskap overstyringer haaandterer avvik.
    """

    company_overrides: dict[str, dict[str, int]] = field(default_factory=dict)
    # company_id -> {konto: regnr, ...}


# ---------------------------------------------------------------------------
# Elimination
# ---------------------------------------------------------------------------

@dataclass
class EliminationLine:
    """En debet/kredit-linje i en elimineringsjournal."""

    regnr: int = 0                    # konsernlinje-nummer
    company_id: str = ""              # hvilket selskap linjen gjelder
    amount: float = 0.0              # positiv = debet, negativ = kredit
    description: str = ""
    # Utvidet for forslags- og valutasporing
    counterparty_company_id: str = ""
    source_suggestion_key: str = ""
    source_currency: str = ""        # original valuta (tom = NOK)
    source_amount: float = 0.0       # beloep i original valuta
    fx_rate_used: float = 0.0        # kurs brukt ved konvertering
    # Kontonivå-eliminering (valgfritt — tom = regnskapslinje-nivå)
    konto: str = ""                  # kontonummer fra SB


@dataclass
class EliminationJournal:
    """En navngitt elimineringsbatch (justeringslag over raa TB)."""

    journal_id: str = field(default_factory=_new_id)
    voucher_no: int = 0
    name: str = ""
    created_at: float = field(default_factory=_now)
    lines: list[EliminationLine] = field(default_factory=list)
    # Opprinnelse: "manual" | "from_suggestion" | "template"
    kind: str = "manual"
    source_suggestion_key: str = ""
    # Status: "draft" | "active"
    status: str = "active"
    locked: bool = False
    locked_reason: str = ""
    source_associate_case_id: str = ""
    generation_hash: str = ""

    @property
    def is_balanced(self) -> bool:
        return abs(self.net) < 0.005

    @property
    def net(self) -> float:
        return sum(line.amount for line in self.lines)

    @property
    def total_debet(self) -> float:
        return sum(max(float(line.amount), 0.0) for line in self.lines)

    @property
    def total_kredit(self) -> float:
        return sum(abs(min(float(line.amount), 0.0)) for line in self.lines)

    @property
    def display_label(self) -> str:
        if int(self.voucher_no or 0) > 0:
            return f"Bilag {int(self.voucher_no)}"
        return self.name or self.journal_id


# ---------------------------------------------------------------------------
# Elimination suggestion (kandidat — ikke persistert i journal foer godkjent)
# ---------------------------------------------------------------------------

# Kandidatkategorier
SUGGESTION_KINDS = (
    "intercompany",         # KonsernmellomvÃ¦rende
    "interest",             # Renter
    "group_contribution",   # Konsernbidrag / Utbytte
    "investment_equity",    # Investering / EK-template
    "fx_difference",        # Valutadifferanse
)


@dataclass
class EliminationSuggestion:
    """En elimineringskandidat generert av forslagsmotoren."""

    suggestion_key: str = ""          # stabil noekkel for review-state
    kind: str = ""                    # en av SUGGESTION_KINDS
    company_a_id: str = ""
    company_b_id: str = ""
    regnr_a: int = 0
    regnr_b: int = 0
    line_name_a: str = ""
    line_name_b: str = ""
    amount_a: float = 0.0            # beloep i NOK (konvertert)
    amount_b: float = 0.0
    diff_nok: float = 0.0
    currency_a: str = ""
    currency_b: str = ""
    source_amount_a: float = 0.0     # beloep i originalvaluta
    source_amount_b: float = 0.0
    # Status: "ny" | "ignorert" | "journalfoert"
    status: str = "ny"
    journal_draft_lines: list[EliminationLine] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Currency control detail
# ---------------------------------------------------------------------------

@dataclass
class CurrencyDetail:
    """One row of currency control data: company × regnr."""

    company_id: str
    company_name: str
    currency: str
    regnr: int
    regnskapslinje: str
    line_type: str         # "Resultat" or "Balanse"
    amount_before: float
    rate: float
    rate_rule: str         # "Snittkurs" or "Sluttkurs"
    amount_after: float


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    """Immutable snapshot av en konsolideringskjoering."""

    run_id: str = field(default_factory=_new_id)
    run_at: float = field(default_factory=_now)
    company_ids: list[str] = field(default_factory=list)
    elimination_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result_hash: str = ""
    input_digest: str = ""
    currency_details: list[CurrencyDetail] = field(default_factory=list)
    account_details: Any = field(default=None)  # pd.DataFrame, flat per-company per-account


# ---------------------------------------------------------------------------
# Associate / equity method
# ---------------------------------------------------------------------------


@dataclass
class AssociateAdjustmentRow:
    """Ekstra EK-metode-justering med egen motpost."""

    row_id: str = field(default_factory=_new_id)
    label: str = ""
    amount: float = 0.0
    offset_regnr: int = 0
    description: str = ""


@dataclass
class AssociateCase:
    """Arbeidspapir for ett tilknyttet selskap etter EK-metoden."""

    case_id: str = field(default_factory=_new_id)
    name: str = ""
    investor_company_id: str = ""
    ownership_pct: float = 0.0
    status: str = "draft"          # "draft" | "generated" | "stale"
    source_mode: str = "manual"    # "manual" | "line_basis" | "pdf"
    notes: str = ""
    line_mapping: dict[str, int] = field(default_factory=_default_associate_line_mapping)
    journal_id: str = ""
    generation_hash: str = ""
    last_generated_at: float = 0.0
    acquisition_date: str = ""
    opening_carrying_amount: float = 0.0
    share_of_result: float = 0.0
    share_of_other_equity: float = 0.0
    dividends: float = 0.0
    impairment: float = 0.0
    excess_value_amortization: float = 0.0
    manual_adjustment_rows: list[AssociateAdjustmentRow] = field(default_factory=list)
    # Goodwill / merverdi
    acquisition_cost: float = 0.0
    share_of_net_assets_at_acquisition: float = 0.0
    goodwill_useful_life_years: int = 5
    goodwill_method: str = "linear"


# ---------------------------------------------------------------------------
# Project (root container)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 4


@dataclass
class ConsolidationProject:
    """Rotcontainer for ett konsolideringsprosjekt per klient/aar."""

    project_id: str = field(default_factory=_new_id)
    client: str = ""
    year: str = ""
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    parent_company_id: str = ""     # company_id for morselskapet
    companies: list[CompanyTB] = field(default_factory=list)
    associate_cases: list[AssociateCase] = field(default_factory=list)
    mapping_config: MappingConfig = field(default_factory=MappingConfig)
    eliminations: list[EliminationJournal] = field(default_factory=list)
    runs: list[RunResult] = field(default_factory=list)
    # Valuta
    reporting_currency: str = "NOK"
    match_tolerance_nok: float = 1000.0
    fx_gain_regnr: int = 0          # regnskapslinje for valutagevinst
    fx_loss_regnr: int = 0          # regnskapslinje for valutatap
    # Forslag review-state (persisterte noekler)
    ignored_suggestion_keys: list[str] = field(default_factory=list)
    applied_suggestion_keys: list[str] = field(default_factory=list)
    # Standard regnskapslinjer for nye EK-saker
    default_associate_line_mapping: dict[str, int] = field(default_factory=dict)

    def find_company(self, company_id: str) -> CompanyTB | None:
        for c in self.companies:
            if c.company_id == company_id:
                return c
        return None

    def find_journal(self, journal_id: str) -> EliminationJournal | None:
        for j in self.eliminations:
            if j.journal_id == journal_id:
                return j
        return None

    def find_associate_case(self, case_id: str) -> AssociateCase | None:
        for case in self.associate_cases:
            if case.case_id == case_id:
                return case
        return None

    def find_associate_case_by_journal(self, journal_id: str) -> AssociateCase | None:
        for case in self.associate_cases:
            if case.journal_id == journal_id:
                return case
        return None

    def ensure_elimination_voucher_numbers(self) -> bool:
        """Sikre stabile løpenummer på elimineringsbilag."""
        changed = False
        used: set[int] = set()
        next_no = 1

        for journal in self.eliminations:
            raw_no = int(journal.voucher_no or 0)
            if raw_no > 0 and raw_no not in used:
                used.add(raw_no)
                next_no = max(next_no, raw_no + 1)
                continue

            while next_no in used:
                next_no += 1
            journal.voucher_no = next_no
            used.add(next_no)
            next_no += 1
            changed = True

            if not str(journal.name or "").strip():
                journal.name = journal.display_label
                changed = True

        return changed

    def next_elimination_voucher_no(self) -> int:
        self.ensure_elimination_voucher_numbers()
        highest = 0
        for journal in self.eliminations:
            highest = max(highest, int(journal.voucher_no or 0))
        return highest + 1

    def touch(self) -> None:
        """Oppdater updated_at til naa."""
        self.updated_at = _now()


# ---------------------------------------------------------------------------
# Serialisering (dict <-> dataclass)
# ---------------------------------------------------------------------------

def project_to_dict(project: ConsolidationProject) -> dict[str, Any]:
    """Serialiser prosjekt til JSON-kompatibel dict."""
    d = asdict(project)
    d["schema_version"] = SCHEMA_VERSION
    # Strip runtime-only fields from RunResult that are not JSON-serializable
    for run in d.get("runs", []):
        run.pop("account_details", None)
        run.pop("currency_details", None)
    return d


def project_from_dict(d: dict[str, Any]) -> ConsolidationProject:
    """Deserialiser prosjekt fra dict (lest fra project.json).

    Bakoverkompatibel med v1 data — manglende felt faar defaults.
    """
    d = dict(d)
    d.pop("schema_version", None)

    # Rebuild nested dataklasser
    companies = []
    for c_raw in d.pop("companies", []):
        # Fjern ukjente felt som ikke finnes i CompanyTB
        known = {f.name for f in CompanyTB.__dataclass_fields__.values()}
        c_clean = {k: v for k, v in c_raw.items() if k in known}
        companies.append(CompanyTB(**c_clean))

    associate_cases = []
    for case_raw in d.pop("associate_cases", []):
        case_raw = dict(case_raw)
        row_known = {f.name for f in AssociateAdjustmentRow.__dataclass_fields__.values()}
        rows = []
        for row_raw in case_raw.pop("manual_adjustment_rows", []):
            row_clean = {k: v for k, v in row_raw.items() if k in row_known}
            rows.append(AssociateAdjustmentRow(**row_clean))
        case_known = {f.name for f in AssociateCase.__dataclass_fields__.values()}
        case_clean = {k: v for k, v in case_raw.items() if k in case_known}
        if "line_mapping" not in case_clean or not isinstance(case_clean["line_mapping"], dict):
            case_clean["line_mapping"] = _default_associate_line_mapping()
        associate_cases.append(AssociateCase(**case_clean, manual_adjustment_rows=rows))

    mc_raw = d.pop("mapping_config", {})
    mapping_config = MappingConfig(
        company_overrides=mc_raw.get("company_overrides", {}),
    )

    eliminations = []
    for ej in d.pop("eliminations", []):
        ej = dict(ej)
        line_known = {f.name for f in EliminationLine.__dataclass_fields__.values()}
        lines = []
        for el_raw in ej.pop("lines", []):
            el_clean = {k: v for k, v in el_raw.items() if k in line_known}
            lines.append(EliminationLine(**el_clean))
        journal_known = {f.name for f in EliminationJournal.__dataclass_fields__.values()}
        ej_clean = {k: v for k, v in ej.items() if k in journal_known}
        eliminations.append(EliminationJournal(**ej_clean, lines=lines))

    runs = [RunResult(**r) for r in d.pop("runs", [])]

    # Fjern ukjente felt som ikke finnes i ConsolidationProject
    proj_known = {f.name for f in ConsolidationProject.__dataclass_fields__.values()}
    d_clean = {k: v for k, v in d.items() if k in proj_known}

    return ConsolidationProject(
        **d_clean,
        companies=companies,
        associate_cases=associate_cases,
        mapping_config=mapping_config,
        eliminations=eliminations,
        runs=runs,
    )

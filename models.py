from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set, Tuple

# Norsk visning av beløp i UI-formattering
DECIMAL_COMMA: bool = True


class AmountMode(str, Enum):
    SINGLE = "single"             # beløp i én kolonne
    DEBIT_CREDIT = "debit_credit" # beløp = debit - credit


@dataclass
class Columns:
    """Kolonnekart for hovedbok/ressurs."""
    konto: str = ""
    kontonavn: str = ""
    bilag: str = ""
    # beløpsvalg
    belop: str = ""               # ved SINGLE
    debit: str = ""               # ved DEBIT_CREDIT
    credit: str = ""              # ved DEBIT_CREDIT
    tekst: str = ""               # valgfri (beskrivelse)
    dato: str = ""                # valgfri
    part: str = ""                # valgfri (kunde/leverandør/part)


@dataclass
class FilterState:
    """Gjeldende filter i hovedvinduet (for hovedtabell/statistikk)."""
    direction: str = "Alle"              # "Alle", "Debet", "Kredit"
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    series_filter: Optional[Set[int]] = None
    search_accounts: str = ""            # søk i kontoliste
    search_txn: str = ""                 # søk i bilag/tekst (drilldown)


# --- Scope (populasjon og underpop) ---

@dataclass
class ScopeConfig:
    """
    Definisjon av et scope (Populasjon/Underpopulasjon).
    accounts_expr: f.eks. "6000-7999, 7210, 65*"
    direction: "Alle" | "Debet" | "Kredit"
    min_amount / max_amount: terskler (None = ingen)
    apply_to: "Alle" | "Debet" | "Kredit" – hvem tersklene gjelder for
    use_abs: True => ved 'Alle' brukes |beløp| for terskler
    date_from/date_to: ISO "YYYY-MM-DD" (valgfritt)
    name: visningsnavn (brukes primært for underpop)
    """
    accounts_expr: str = ""
    direction: str = "Alle"
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    apply_to: str = "Alle"
    use_abs: bool = True
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    name: str = "Populasjon"


@dataclass
class BucketConfig:
    """Stratifisering i utvalgsvinduet."""
    n_buckets: int = 0
    method: str = "quantile"  # "quantile" eller "equal"
    basis: str = "abs"        # "abs" eller "signed"


# --- Analyseoppsett (enkelt datasett – scope-eksport) ---

@dataclass
class AnalysisConfig:
    # Eksisterende
    include_duplicates_doc_account: bool = True
    include_round_amounts: bool = True
    include_out_of_period: bool = True       # krever dato + periode i scope
    round_bases: Tuple[int, ...] = (1000, 500, 100)
    round_tolerance: float = 0.0             # ± kroner

    # NYTT – Outliers
    include_outliers: bool = True
    outlier_method: str = "MAD"              # "MAD" eller "IQR"
    outlier_threshold: float = 3.5           # MAD: z-terskel, IQR: k (typisk 1.5)
    outlier_group_by: str = "Konto"          # "Global", "Konto", "Part", "Konto+Part"
    outlier_min_group_size: int = 20
    outlier_basis: str = "abs"               # "abs" eller "signed"

    # NYTT – Runde beløp, andeler per gruppe
    include_round_share_by_group: bool = True
    round_share_group_by: str = "Konto"      # "Konto", "Part", "Måned"
    round_share_threshold: float = 0.30      # flagg grupper med andel >= terskel
    round_share_min_rows: int = 20
    # bruker round_bases/round_tolerance fra over


# --- A/B-analyseoppsett ---

@dataclass
class ABAnalysisConfig:
    # Tidligere
    same_amount: bool = True                 # A ↔ B likt beløp
    opposite_sign: bool = True               # A ↔ -B likt beløp
    two_sum: bool = True                     # A ≈ sum av 2 i B (eksakt øre)
    invoice_equal: bool = True               # likt faktura/dok.nr (normalisert)
    dup_invoice_per_party: bool = True       # duplikate faktura pr part i A/B
    days_tolerance: int = 3                  # ± dager (der det er relevant)
    amount_tolerance: float = 0.0            # ± kroner (likt/motsatt fortegn)
    require_same_party: bool = False         # krev lik part/kunde for match
    invoice_drop_non_alnum: bool = True      # fjern alt utenom [A-Za-z0-9]
    invoice_strip_leading_zeros: bool = True
    unique_match: bool = True                # maks én B pr A (og vice versa)

    # NYTT – Avvik på nøkkel (faktura)
    key_amount_deviation: bool = True        # rapportér |beløpsavvik| >= min_diff
    key_amount_min_diff: float = 1.0         # kroner
    key_date_deviation: bool = True          # rapportér dagsavvik > min_days
    key_days_min_diff: int = 7               # dager

"""MVA-avstemming: Skatteetaten-import og avstemming mot hovedbok.

Ren datamodul uten GUI-avhengigheter.

Leser Skatteetatens kontoutskrift (Excel) og sammenligner innrapportert MVA
med MVA beregnet fra hovedbok-transaksjoner.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

# Norske MVA-terminer (2-månedersperioder)
TERMIN_MONTHS = {
    1: (1, 2),
    2: (3, 4),
    3: (5, 6),
    4: (7, 8),
    5: (9, 10),
    6: (11, 12),
}


def month_to_termin(month: int) -> int:
    """Konverter måned (1-12) til termin (1-6)."""
    return (month - 1) // 2 + 1


# ---------------------------------------------------------------------------
# Skatteetaten kontoutskrift-parsing
# ---------------------------------------------------------------------------

@dataclass
class SkatteetatenData:
    """Parsed data fra Skatteetatens kontoutskrift."""
    org_nr: str = ""
    company: str = ""
    period: str = ""
    # MVA innrapportert per termin (termin-nr → beløp)
    mva_per_termin: dict[int, float] = field(default_factory=dict)
    # AGA per termin
    aga_per_termin: dict[int, float] = field(default_factory=dict)
    # Forskuddstrekk per termin
    forskuddstrekk_per_termin: dict[int, float] = field(default_factory=dict)
    # Rå Krav-data for referanse
    raw_krav: Optional[pd.DataFrame] = None
    # Rå Transaksjoner-data (bevegelser på skattekonto)
    raw_transaksjoner: Optional[pd.DataFrame] = None
    # År filtrert på (None = alle)
    year: Optional[int] = None

    def to_dict(self) -> dict:
        """Serialiser til JSON-kompatibel dict (for klient-persistens)."""
        def _jsonable(val):
            if val is None:
                return None
            if isinstance(val, (pd.Timestamp,)):
                if pd.isna(val):
                    return None
                return val.isoformat()
            # numpy-skalare
            try:
                import numpy as np
                if isinstance(val, np.generic):
                    if isinstance(val, np.floating) and np.isnan(val):
                        return None
                    return val.item()
            except Exception:
                pass
            if isinstance(val, float):
                import math
                if math.isnan(val):
                    return None
                return val
            if isinstance(val, (int, str, bool)):
                return val
            # datetime/date fallback
            try:
                import datetime as _dt
                if isinstance(val, (_dt.datetime, _dt.date)):
                    return val.isoformat()
            except Exception:
                pass
            return str(val)

        def _df_to_records(df: Optional[pd.DataFrame]) -> list:
            if df is None or df.empty:
                return []
            try:
                records = df.astype(object).where(df.notna(), None).to_dict("records")
                return [
                    {str(k): _jsonable(v) for k, v in rec.items()}
                    for rec in records
                ]
            except Exception:
                return []

        return {
            "org_nr": self.org_nr,
            "company": self.company,
            "period": self.period,
            "year": self.year,
            "mva_per_termin": {str(k): float(v) for k, v in self.mva_per_termin.items()},
            "aga_per_termin": {str(k): float(v) for k, v in self.aga_per_termin.items()},
            "forskuddstrekk_per_termin": {
                str(k): float(v) for k, v in self.forskuddstrekk_per_termin.items()
            },
            "raw_krav": _df_to_records(self.raw_krav),
            "raw_transaksjoner": _df_to_records(self.raw_transaksjoner),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkatteetatenData":
        """Deserialisér fra dict lagret via to_dict."""
        if not isinstance(data, dict):
            return cls()

        def _to_int_keys(d) -> dict[int, float]:
            out: dict[int, float] = {}
            if not isinstance(d, dict):
                return out
            for k, v in d.items():
                try:
                    out[int(k)] = float(v)
                except (TypeError, ValueError):
                    continue
            return out

        def _records_to_df(records) -> Optional[pd.DataFrame]:
            if not records:
                return None
            try:
                return pd.DataFrame(records)
            except Exception:
                return None

        result = cls(
            org_nr=str(data.get("org_nr", "") or ""),
            company=str(data.get("company", "") or ""),
            period=str(data.get("period", "") or ""),
            mva_per_termin=_to_int_keys(data.get("mva_per_termin")),
            aga_per_termin=_to_int_keys(data.get("aga_per_termin")),
            forskuddstrekk_per_termin=_to_int_keys(data.get("forskuddstrekk_per_termin")),
            raw_krav=_records_to_df(data.get("raw_krav")),
            raw_transaksjoner=_records_to_df(data.get("raw_transaksjoner")),
        )
        yr = data.get("year")
        if yr is not None:
            try:
                result.year = int(yr)
            except (TypeError, ValueError):
                result.year = None
        return result


def parse_skatteetaten_kontoutskrift(
    path: str | Path,
    *,
    year: int | str | None = None,
) -> SkatteetatenData:
    """Les kontoutskrift.xlsx fra Skatteetaten.

    Args:
        path: Sti til Excel-fil.
        year: Filtrer på år (valgfritt). Hvis None brukes alle år.

    Returns:
        SkatteetatenData med parsede beløp per termin.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    result = SkatteetatenData()
    if year is not None:
        result.year = int(year)

    # Les header-info
    try:
        df_header = pd.read_excel(p, sheet_name="Kontoutskrift gjelder", header=None)
        for _, row in df_header.iterrows():
            vals = [str(v).strip() for v in row if pd.notna(v)]
            if len(vals) >= 2 and vals[0].isdigit() and len(vals[0]) == 9:
                result.org_nr = vals[0]
                result.company = vals[1] if len(vals) > 1 else ""
            if len(vals) >= 2 and "periode" in vals[0].lower():
                result.period = vals[1]
    except Exception as exc:
        log.debug("Kunne ikke lese header-ark: %s", exc)

    # Les Krav-arket
    try:
        df_krav = pd.read_excel(p, sheet_name="Krav")
    except Exception as exc:
        raise ValueError(f"Kunne ikke lese 'Krav'-arket: {exc}") from exc

    result.raw_krav = df_krav

    # Normaliser kolonnenavn
    col_map = _find_krav_columns(df_krav)
    if not col_map.get("kravgruppe") or not col_map.get("beløp"):
        raise ValueError("Fant ikke forventede kolonner i Krav-arket")

    # Filtrer og grupper
    for _, row in df_krav.iterrows():
        kravgruppe = str(row.get(col_map["kravgruppe"], "") or "").strip()
        kravbeskrivelse = str(row.get(col_map.get("kravbeskrivelse", ""), "") or "").strip()
        raw_year = row.get(col_map.get("year", ""), "")
        periode = row.get(col_map.get("periode", ""), "")
        beløp = row.get(col_map["beløp"], 0)

        # Filtrere på år
        if result.year is not None and col_map.get("year"):
            try:
                row_year = int(float(str(raw_year)))
                if row_year != result.year:
                    continue
            except (ValueError, TypeError):
                continue

        # Parse termin
        try:
            termin = int(float(str(periode)))
        except (ValueError, TypeError):
            continue

        if termin < 1 or termin > 6:
            continue

        # Parse beløp
        try:
            amount = float(beløp) if pd.notna(beløp) else 0.0
        except (ValueError, TypeError):
            continue

        if kravgruppe == "Merverdiavgift" and "mva-melding" in kravbeskrivelse.lower():
            result.mva_per_termin[termin] = (
                result.mva_per_termin.get(termin, 0.0) + amount
            )
        elif kravgruppe == "Arbeidsgiveravgift":
            result.aga_per_termin[termin] = (
                result.aga_per_termin.get(termin, 0.0) + amount
            )
        elif kravgruppe == "Forskuddstrekk":
            result.forskuddstrekk_per_termin[termin] = (
                result.forskuddstrekk_per_termin.get(termin, 0.0) + amount
            )

    # Les Transaksjoner-arket (valgfritt — brukes i "Skyldig saldo"-fanen)
    try:
        df_trans = pd.read_excel(p, sheet_name="Transaksjoner")
        result.raw_transaksjoner = df_trans
    except Exception as exc:
        log.debug("Kunne ikke lese Transaksjoner-arket: %s", exc)

    return result


def _find_krav_columns(df: pd.DataFrame) -> dict[str, str]:
    """Finn relevante kolonner i Krav-arket (case-insensitive)."""
    result: dict[str, str] = {}
    lower_map = {str(c).lower(): str(c) for c in df.columns}

    patterns = {
        "kravgruppe": ["kravgruppe"],
        "kravbeskrivelse": ["kravbeskrivelse"],
        "year": ["år", "ar"],
        "periode": ["periode"],
        "beløp": ["opprinnelig beløp", "opprinnelig belop", "opprinnelig bel\u00f8p"],
    }

    for key, candidates in patterns.items():
        for cand in candidates:
            match = lower_map.get(cand)
            if match:
                result[key] = match
                break
            # Delvis match
            for col_lower, col_orig in lower_map.items():
                if cand in col_lower:
                    result[key] = col_orig
                    break
            if key in result:
                break

    return result


# ---------------------------------------------------------------------------
# Avstemming: HB vs Skatteetaten
# ---------------------------------------------------------------------------

def build_reconciliation(
    mva_pivot: pd.DataFrame,
    skatteetaten: SkatteetatenData,
) -> pd.DataFrame:
    """Sammenlign hovedbok MVA-totaler vs Skatteetaten-innrapportert per termin.

    Fortegn-konvensjon:
    - I HB er utgående MVA negativ (kredit) og inngående positiv (debet).
    - Skatteetaten rapporterer beløp-å-betale som positivt.
    - For sammenligning snur vi HB-fortegnet: positiv = skyldig MVA.

    Args:
        mva_pivot: MVA-pivot fra build_mva_pivot() (med direction-kolonne).
        skatteetaten: Parsed Skatteetaten-data.

    Returns:
        DataFrame med kolonner:
            Termin, HB Utgående, HB Inngående, HB Netto, Innrapportert, Differanse
    """
    rows = []

    for t in range(1, 7):
        t_col = f"T{t}"

        hb_utg = 0.0
        hb_inn = 0.0

        if not mva_pivot.empty and t_col in mva_pivot.columns and "direction" in mva_pivot.columns:
            utg_mask = mva_pivot["direction"] == "utgående"
            inn_mask = mva_pivot["direction"] == "inngående"
            hb_utg = mva_pivot.loc[utg_mask, t_col].sum()
            hb_inn = mva_pivot.loc[inn_mask, t_col].sum()

        # Snur fortegn: i HB er utgående negativ (kredit), men for
        # MVA-meldingen er utgående MVA positivt (beløp å beregne/betale).
        hb_utg_abs = abs(hb_utg)
        hb_inn_abs = abs(hb_inn)
        hb_netto = hb_utg_abs - hb_inn_abs
        innrapportert = skatteetaten.mva_per_termin.get(t, 0.0)
        differanse = hb_netto - innrapportert

        rows.append({
            "Termin": f"T{t}",
            "HB Utgående": hb_utg_abs,
            "HB Inngående": hb_inn_abs,
            "HB Netto": hb_netto,
            "Innrapportert": innrapportert,
            "Differanse": differanse,
        })

    # Sum-rad
    sum_row = {
        "Termin": "Sum",
        "HB Utgående": sum(r["HB Utgående"] for r in rows),
        "HB Inngående": sum(r["HB Inngående"] for r in rows),
        "HB Netto": sum(r["HB Netto"] for r in rows),
        "Innrapportert": sum(r["Innrapportert"] for r in rows),
        "Differanse": sum(r["Differanse"] for r in rows),
    }
    rows.append(sum_row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# MVA-kontroller
# ---------------------------------------------------------------------------

# Utgående MVA-koder knyttet til ordinært salg
_UTGAAENDE_SALG_CODES = {"1", "3", "5", "6", "7"}
# Alle utgående koder (inkl. omvendt avgiftsplikt, uttak m.m.)
_ALLE_UTGAAENDE_CODES = {
    "1", "3", "5", "6", "7", "9",
    "21", "22", "23", "24",
    "86", "87", "88", "91",
}
# Salgsinntekter-kontoer (NS 4102)
_SALG_RANGE = (3000, 3999)


@dataclass
class MvaKontrollResult:
    """Samlet resultat fra MVA-kontroller."""
    # K1: Salgsinntekter vs grunnlag utgående MVA per termin
    salg_vs_grunnlag: pd.DataFrame = field(default_factory=pd.DataFrame)
    # K2: Transaksjoner på salgskontoer uten MVA-kode
    salg_uten_mva: pd.DataFrame = field(default_factory=pd.DataFrame)
    # K3: Transaksjoner på ANDRE kontoer med utgående salgs-MVA
    andre_med_utg_mva: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Oppsummering
    summary: list[dict] = field(default_factory=list)


def build_mva_kontroller(df: pd.DataFrame) -> MvaKontrollResult:
    """Kjør standard MVA-kontroller på filtrert datasett.

    Kontroller:
        K1: Sammenlign sum salgsinntekter (konto 3000-3999) per termin
            mot grunnlag på transaksjoner med utgående MVA-koder.
        K2: Finn transaksjoner på salgskontoer uten MVA-kode.
        K3: Finn transaksjoner på andre kontoer som har utgående salgs-MVA.
    """
    result = MvaKontrollResult()
    if df is None or df.empty:
        return result

    # Finn relevante kolonner
    konto_col = _find_col_flex(df, ["Konto", "konto"])
    belop_col = _find_col_flex(df, ["Beløp", "beløp", "Belop"])
    dato_col = _find_col_flex(df, ["Dato", "dato"])
    mva_code_col = _find_col_flex(df, ["MVA-kode", "mva-kode", "Mva-kode"])

    if not konto_col or not belop_col or not dato_col:
        return result

    # Preparer
    work = df.copy()
    work["_konto_nr"] = pd.to_numeric(work[konto_col], errors="coerce")
    work["_belop"] = pd.to_numeric(work[belop_col], errors="coerce").fillna(0.0)
    work["_dato"] = pd.to_datetime(work[dato_col], errors="coerce")
    work["_termin"] = work["_dato"].dt.month.apply(
        lambda m: month_to_termin(int(m)) if pd.notna(m) else 0
    )
    work["_mva_code"] = (
        work[mva_code_col].astype(str).str.strip()
        if mva_code_col else ""
    )
    work.loc[work["_mva_code"].isin(["", "nan", "None", "0"]), "_mva_code"] = ""

    # Masker
    is_salg = work["_konto_nr"].between(*_SALG_RANGE)
    has_utg_mva = work["_mva_code"].isin(_UTGAAENDE_SALG_CODES)
    has_any_mva = work["_mva_code"].ne("")

    # --- K1: Salgsinntekter vs grunnlag utgående MVA per termin ---
    k1_rows = []
    for t in range(1, 7):
        t_mask = work["_termin"] == t
        # Salgsinntekter på konto 3xxx
        salg_sum = work.loc[is_salg & t_mask, "_belop"].sum()
        # Grunnlag (Beløp) på transaksjoner med utgående MVA-koder
        grunnlag_sum = work.loc[has_utg_mva & t_mask, "_belop"].sum()
        diff = salg_sum - grunnlag_sum
        k1_rows.append({
            "Termin": f"T{t}",
            "Salgsinntekter (3xxx)": salg_sum,
            "Grunnlag utg. MVA": grunnlag_sum,
            "Differanse": diff,
        })
    # Sum
    k1_rows.append({
        "Termin": "Sum",
        "Salgsinntekter (3xxx)": sum(r["Salgsinntekter (3xxx)"] for r in k1_rows),
        "Grunnlag utg. MVA": sum(r["Grunnlag utg. MVA"] for r in k1_rows),
        "Differanse": sum(r["Differanse"] for r in k1_rows),
    })
    result.salg_vs_grunnlag = pd.DataFrame(k1_rows)

    # --- K2: Salgskontoer uten MVA-kode ---
    # Standard kolonner for drilldown
    _std_cols = ["Bilag", konto_col, "Kontonavn", dato_col, belop_col, "Tekst", "Referanse"]
    mask_k2 = is_salg & ~has_any_mva
    if mask_k2.any():
        cols_show = [c for c in _std_cols if c and c in work.columns]
        result.salg_uten_mva = work.loc[mask_k2, cols_show].copy()

    # --- K3: Andre kontoer med utgående salgs-MVA ---
    mask_k3 = ~is_salg & has_utg_mva
    if mask_k3.any():
        _k3_cols = ["Bilag", konto_col, "Kontonavn", dato_col, belop_col, mva_code_col, "Tekst", "Referanse"]
        cols_show = [c for c in _k3_cols if c and c in work.columns]
        result.andre_med_utg_mva = work.loc[mask_k3, cols_show].copy()

    # --- Oppsummering ---
    result.summary = [
        {
            "Kontroll": "K1: Salgsinntekter vs grunnlag utg. MVA",
            "Status": "OK" if abs(k1_rows[-1]["Differanse"]) < 1.0 else "AVVIK",
            "Differanse": k1_rows[-1]["Differanse"],
            "Kommentar": (
                "Differanse kan skyldes transaksjoner på salgskontoer uten MVA "
                "eller MVA-pliktig omsetning bokført på andre kontoer."
                if abs(k1_rows[-1]["Differanse"]) >= 1.0
                else "Salgsinntekter stemmer med grunnlag for utgående MVA."
            ),
        },
        {
            "Kontroll": "K2: Salgskontoer uten MVA-kode",
            "Status": "OK" if result.salg_uten_mva.empty else "MERK",
            "Differanse": result.salg_uten_mva[belop_col].sum() if not result.salg_uten_mva.empty and belop_col in result.salg_uten_mva.columns else 0.0,
            "Kommentar": (
                f"{len(result.salg_uten_mva)} transaksjoner på salgskontoer (3xxx) uten MVA-kode."
                if not result.salg_uten_mva.empty
                else "Alle salgstransaksjoner har MVA-kode."
            ),
        },
        {
            "Kontroll": "K3: Utg. MVA på andre kontoer",
            "Status": "OK" if result.andre_med_utg_mva.empty else "MERK",
            "Differanse": result.andre_med_utg_mva[belop_col].sum() if not result.andre_med_utg_mva.empty and belop_col in result.andre_med_utg_mva.columns else 0.0,
            "Kommentar": (
                f"{len(result.andre_med_utg_mva)} transaksjoner med utgående salgs-MVA på andre kontoer enn 3xxx."
                if not result.andre_med_utg_mva.empty
                else "Ingen transaksjoner med utgående salgs-MVA utenfor salgskontoer."
            ),
        },
    ]

    return result


def _find_col_flex(df: pd.DataFrame, candidates: list[str]) -> str:
    """Finn første matchende kolonnenavn (case-insensitive)."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        actual = lower_map.get(cand.lower())
        if actual:
            return actual
    return ""

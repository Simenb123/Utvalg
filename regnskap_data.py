"""regnskap_data.py — Datastrukturer og rene hjelpefunksjoner for årsregnskap.

Importeres av page_regnskap (GUI) og regnskap_report (eksport).
Ingen tkinter-avhengighet — kun stdlib + pandas.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Resultatregnskap-struktur
# (regnr, label, level, is_sum, is_header)
# regnr=None → seksjonstekst uten verdi
# ---------------------------------------------------------------------------

RS_STRUCTURE: list[tuple] = [
    (None,  "DRIFTSINNTEKTER",                          0, False, True),
    (10,    "Salgsinntekter",                            1, False, False),
    (15,    "Andre driftsinntekter",                     1, False, False),
    (19,    "Sum driftsinntekter",                       1, True,  False),
    (None,  "DRIFTSKOSTNADER",                          0, False, True),
    (20,    "Varekostnad",                               1, False, False),
    (40,    "Lønnskostnad og sosiale kostnader",         1, False, False),
    (50,    "Avskrivning",                               1, False, False),
    (70,    "Annen driftskostnad",                       1, False, False),
    (79,    "Sum driftskostnader",                       1, True,  False),
    (80,    "DRIFTSRESULTAT",                            0, True,  False),
    (None,  "FINANSPOSTER",                             0, False, True),
    (135,   "Finansinntekter",                           1, False, False),
    (145,   "Finanskostnader",                           1, False, False),
    (160,   "RESULTAT FØR SKATTEKOSTNAD",                0, True,  False),
    (260,   "Skattekostnad",                             1, False, False),
    (280,   "ÅRSRESULTAT",                               0, True,  False),
]

# ---------------------------------------------------------------------------
# Balanse-struktur
# ---------------------------------------------------------------------------

BS_STRUCTURE: list[tuple] = [
    (None,  "EIENDELER",                                0, False, True),
    (None,  "Anleggsmidler",                            1, False, True),
    (555,   "Varige driftsmidler",                       2, False, False),
    (580,   "Finansielle anleggsmidler",                 2, False, False),
    (590,   "Sum anleggsmidler",                         2, True,  False),
    (None,  "Omløpsmidler",                             1, False, True),
    (605,   "Varelager",                                 2, False, False),
    (610,   "Kundefordringer",                           2, False, False),
    (630,   "Andre fordringer",                          2, False, False),
    (655,   "Bankinnskudd",                              2, False, False),
    (660,   "Sum omløpsmidler",                          2, True,  False),
    (665,   "SUM EIENDELER",                             0, True,  False),
    (None,  "EGENKAPITAL OG GJELD",                     0, False, True),
    (None,  "Egenkapital",                              1, False, True),
    (715,   "Sum egenkapital",                           2, True,  False),
    (None,  "Langsiktig gjeld",                         1, False, True),
    (735,   "Avsetning for forpliktelser",               2, False, False),
    (760,   "Annen langsiktig gjeld",                    2, False, False),
    (770,   "Sum langsiktig gjeld",                      2, True,  False),
    (None,  "Kortsiktig gjeld",                         1, False, True),
    (780,   "Leverandørgjeld",                           2, False, False),
    (800,   "Skattetrekk og offentlige avgifter",        2, False, False),
    (805,   "Utbytte",                                   2, False, False),
    (810,   "Sum kortsiktig gjeld",                      2, True,  False),
    (820,   "Sum gjeld",                                 1, True,  False),
    (830,   "SUM EGENKAPITAL OG GJELD",                  0, True,  False),
]

# ---------------------------------------------------------------------------
# Note-spec format
# type: "header" | "auto" | "field" | "sep" | "text"
#   header  — bold seksjonstittel, ingen verdi
#   auto    — beregnet fra regnskapstall (readonly)
#             regnr: int, period: "current" | "prev" (default "current")
#   field   — brukerfelt (editable Entry)
#             key: str, default: str (default "")
#   sep     — visuell skillelinje
#   text    — flerlinjet fritekst (bare for regnskapsprinsipper)
#             key: str
# ---------------------------------------------------------------------------

LONNS_SPEC: list[dict] = [
    {"type": "header", "label": "Lønnskostnader"},
    {"type": "auto",   "label": "Sum lønnskostnad (i år)",    "regnr": 40, "period": "current"},
    {"type": "auto",   "label": "Sum lønnskostnad (fjorår)",  "regnr": 40, "period": "prev"},
    {"type": "sep"},
    {"type": "field",  "label": "Antall ansatte",                          "key": "ansatte",          "default": ""},
    {"type": "field",  "label": "Gjennomsnittlig antall årsverk",           "key": "aarsverk",         "default": ""},
    {"type": "header", "label": "Ytelser til ledende personer"},
    {"type": "field",  "label": "Daglig leder — lønn",                     "key": "dl_lonn",          "default": ""},
    {"type": "field",  "label": "Daglig leder — pensjonsforpliktelse",      "key": "dl_pensjon",       "default": ""},
    {"type": "field",  "label": "Daglig leder — andre ytelser",             "key": "dl_andre",         "default": ""},
    {"type": "field",  "label": "Styrehonorar",                             "key": "styre_honorar",    "default": ""},
    {"type": "header", "label": "Kostnader for revisor (ekskl. mva.)"},
    {"type": "field",  "label": "Lovpålagt revisjon",                       "key": "rev_lovpaalagt",   "default": ""},
    {"type": "field",  "label": "Andre attestasjonstjenester",               "key": "rev_attestasjon",  "default": ""},
    {"type": "field",  "label": "Skatterådgivning",                         "key": "rev_skatt",        "default": ""},
    {"type": "field",  "label": "Andre tjenester",                          "key": "rev_andre",        "default": ""},
]

EK_SPEC: list[dict] = [
    {"type": "header", "label": "Egenkapitalbevegelse"},
    {"type": "auto",   "label": "Egenkapital 01.01 (IB)",           "regnr": 715, "period": "prev"},
    {"type": "auto",   "label": "+ Årsresultat",                     "regnr": 280, "period": "current"},
    {"type": "field",  "label": "- Utbytte utbetalt",                "key": "utbytte",             "default": ""},
    {"type": "field",  "label": "± Øvrige endringer",                "key": "andre_ek_end",        "default": ""},
    {"type": "auto",   "label": "Egenkapital 31.12 (UB)",           "regnr": 715, "period": "current"},
    {"type": "sep"},
    {"type": "header", "label": "Aksjekapital"},
    {"type": "field",  "label": "Antall aksjer",                     "key": "antall_aksjer",       "default": ""},
    {"type": "field",  "label": "Pålydende pr. aksje (kr)",          "key": "paalydende",          "default": ""},
    {"type": "field",  "label": "Aksjekapital (kr)",                 "key": "aksjekapital",        "default": ""},
    {"type": "field",  "label": "Overkursfond (kr)",                 "key": "overkursfond",        "default": ""},
]

AKS_SPEC: list[dict] = [
    {"type": "header", "label": "Aksjonærer pr. 31.12"},
    {"type": "field",  "label": "Aksjonær 1 — navn",                "key": "aks1_navn",           "default": ""},
    {"type": "field",  "label": "Aksjonær 1 — antall aksjer",       "key": "aks1_aksjer",         "default": ""},
    {"type": "field",  "label": "Aksjonær 1 — eierandel (%)",       "key": "aks1_pct",            "default": ""},
    {"type": "field",  "label": "Aksjonær 2 — navn",                "key": "aks2_navn",           "default": ""},
    {"type": "field",  "label": "Aksjonær 2 — antall aksjer",       "key": "aks2_aksjer",         "default": ""},
    {"type": "field",  "label": "Aksjonær 2 — eierandel (%)",       "key": "aks2_pct",            "default": ""},
    {"type": "field",  "label": "Aksjonær 3 — navn",                "key": "aks3_navn",           "default": ""},
    {"type": "field",  "label": "Aksjonær 3 — antall aksjer",       "key": "aks3_aksjer",         "default": ""},
    {"type": "field",  "label": "Aksjonær 3 — eierandel (%)",       "key": "aks3_pct",            "default": ""},
    {"type": "field",  "label": "Aksjonær 4 — navn",                "key": "aks4_navn",           "default": ""},
    {"type": "field",  "label": "Aksjonær 4 — antall aksjer",       "key": "aks4_aksjer",         "default": ""},
    {"type": "field",  "label": "Aksjonær 4 — eierandel (%)",       "key": "aks4_pct",            "default": ""},
    {"type": "sep"},
    {"type": "auto",   "label": "Sum egenkapital (UB)",             "regnr": 715, "period": "current"},
]

SKATT_SPEC: list[dict] = [
    {"type": "header", "label": "Skattekostnad"},
    {"type": "auto",   "label": "Resultat før skattekostnad",        "regnr": 160, "period": "current"},
    {"type": "field",  "label": "Permanente forskjeller",             "key": "perm_forskj",          "default": ""},
    {"type": "field",  "label": "Endring midlertidige forskjeller",   "key": "end_midf",             "default": ""},
    {"type": "field",  "label": "Grunnlag betalbar skatt",            "key": "grunnlag_skatt",       "default": ""},
    {"type": "field",  "label": "Betalbar skatt (22 %)",              "key": "betalbar_skatt",       "default": ""},
    {"type": "field",  "label": "Endring utsatt skatt",               "key": "end_utsatt_skatt",     "default": ""},
    {"type": "auto",   "label": "Sum skattekostnad",                  "regnr": 260, "period": "current"},
    {"type": "sep"},
    {"type": "header", "label": "Midlertidige forskjeller"},
    {"type": "field",  "label": "Driftsmidler (skattem. vs. regnskapsmessig)", "key": "midf_dm",     "default": ""},
    {"type": "field",  "label": "Gevinst-/tapskonto",                 "key": "midf_gtk",             "default": ""},
    {"type": "field",  "label": "Fremførbart underskudd",             "key": "midf_underskudd",      "default": ""},
    {"type": "field",  "label": "Andre midlertidige forskjeller",     "key": "midf_andre",           "default": ""},
    {"type": "field",  "label": "Sum midlertidige forskjeller",       "key": "midf_sum",             "default": ""},
    {"type": "field",  "label": "Utsatt skatteforpliktelse (22 %)",   "key": "utsatt_forplikt",      "default": ""},
    {"type": "field",  "label": "Utsatt skattefordel (22 %)",         "key": "utsatt_fordel",        "default": ""},
]

PRINSIPP_DEFAULT = (
    "Årsregnskapet er satt opp i samsvar med regnskapslovens bestemmelser "
    "og god regnskapsskikk for små foretak.\n\n"
    "Inntektsføring\n"
    "Inntekter resultatføres etter opptjeningsprinsippet.\n\n"
    "Klassifisering og vurdering av balanseposter\n"
    "Omløpsmidler og kortsiktig gjeld omfatter poster som forfaller til "
    "betaling innen ett år etter balansedagen, samt poster som knytter seg "
    "til varekretsløpet.\n\n"
    "Fordringer\n"
    "Kundefordringer og andre fordringer er oppført til pålydende etter "
    "fradrag for avsetning til forventet tap.\n\n"
    "Varige driftsmidler\n"
    "Varige driftsmidler balanseføres og avskrives lineært over driftsmidlets "
    "forventede levetid. Direkte vedlikehold av driftsmidler kostnadsføres "
    "løpende.\n\n"
    "Skatter\n"
    "Skattekostnaden i resultatregnskapet omfatter periodens betalbare skatt "
    "og endring i utsatt skatt. Utsatt skatt er beregnet med 22 % på grunnlag "
    "av de midlertidige forskjeller som eksisterer mellom regnskapsmessige og "
    "skattemessige verdier."
)

# Ordered note registry: (note_id, display_label, spec | None)
# spec=None → renders as free-text (regnskapsprinsipper)
NOTE_SPECS: list[tuple[str, str, list | None]] = [
    ("regnskapsprinsipper", "Regnskapsprinsipper", None),
    ("lonnsnote",           "Lønnskostnader",      LONNS_SPEC),
    ("egenkapitalnote",     "Egenkapital",          EK_SPEC),
    ("aksjonaernote",       "Aksjonærer",           AKS_SPEC),
    ("skattenote",          "Skatter",              SKATT_SPEC),
]

# Note numbers (1-based, matching NOTE_SPECS order)
NOTE_NUMBERS: dict[str, int] = {
    note_id: idx + 1
    for idx, (note_id, _, _) in enumerate(NOTE_SPECS)
}

# regnr → (note_number, note_id) — hvilke regnskapslinjer har notehenvisning
NOTE_REFS: dict[int, tuple[int, str]] = {
    40:  (NOTE_NUMBERS["lonnsnote"],       "lonnsnote"),
    260: (NOTE_NUMBERS["skattenote"],      "skattenote"),
    715: (NOTE_NUMBERS["egenkapitalnote"], "egenkapitalnote"),
}


# ---------------------------------------------------------------------------
# Rene hjelpefunksjoner (ingen tkinter)
# ---------------------------------------------------------------------------

def _is_credit(regnr: int) -> bool:
    """Regnskapslinjer som naturlig har kredittsaldo (negativ i SAF-T)."""
    if regnr <= 19:
        return True
    if regnr in (80, 135, 160, 280):
        return True
    if regnr >= 700:
        return True
    return False


def ub_lookup(rl_df: pd.DataFrame, col: str = "UB") -> dict[int, float]:
    """Bygg regnr → visningsverdi fra rl_df. Inverterer fortegn for kredittlinjer."""
    out: dict[int, float] = {}
    if rl_df is None or rl_df.empty or col not in rl_df.columns:
        return out
    for _, row in rl_df.iterrows():
        try:
            regnr = int(float(row["regnr"]))
        except (ValueError, TypeError):
            continue
        try:
            val = float(row[col])
        except (ValueError, TypeError):
            continue
        if _is_credit(regnr):
            val = -val
        out[regnr] = val
    return out


def fmt_amount(val: float | None, blank_zero: bool = True) -> str:
    """Formater beløp med norsk tusenskille og 2 desimaler. Returnerer '–' for None."""
    if val is None:
        return "–"
    if blank_zero and abs(val) < 0.005:
        return "–"
    # Norsk format: mellomrom som tusenskille, komma som desimalskille
    abs_val = abs(val)
    int_part = int(abs_val)
    dec_part = round((abs_val - int_part) * 100)
    if dec_part == 100:
        int_part += 1
        dec_part = 0
    int_str = f"{int_part:,}".replace(",", "\u202f")  # narrow no-break space
    sign = "-" if val < 0 else ""
    return f"{sign}{int_str},{dec_part:02d}"


def eval_auto_row(
    row_spec: dict,
    ub: dict[int, float],
    ub_prev: dict[int, float] | None,
) -> float | None:
    """Hent verdien for en 'auto'-rad fra ub eller ub_prev."""
    regnr = row_spec.get("regnr")
    if regnr is None:
        return None
    period = row_spec.get("period", "current")
    lookup = ub_prev if (period == "prev" and ub_prev) else ub
    return lookup.get(regnr)


def build_cf_rows(
    ub: dict[int, float],
    ub_prev: dict[int, float] | None,
) -> list[tuple[str, float | None, bool, bool]]:
    """Kontantstrøm (indirekte metode). Returnerer (label, amount, is_sum, is_header)."""

    def chg(regnr: int) -> float | None:
        if ub_prev is None:
            return None
        a = ub.get(regnr)
        b = ub_prev.get(regnr)
        if a is None or b is None:
            return None
        return a - b

    rows: list[tuple[str, float | None, bool, bool]] = []

    def row(label: str, val: float | None, is_sum: bool = False, is_hdr: bool = False) -> None:
        rows.append((label, val, is_sum, is_hdr))

    row("KONTANTSTRØM FRA DRIFTEN", None, False, True)
    aarsres = ub.get(280)
    row("  Årsresultat", aarsres)
    avskr = ub.get(50)
    row("  Tilbakeføring avskrivninger", avskr)
    cf_ar = chg(610)
    row("  Endring kundefordringer", (-cf_ar) if cf_ar is not None else None)
    cf_vl = chg(605)
    row("  Endring varelager", (-cf_vl) if cf_vl is not None else None)
    cf_lev = chg(780)
    row("  Endring leverandørgjeld", cf_lev)
    parts = [aarsres, avskr,
             (-cf_ar) if cf_ar is not None else None,
             (-cf_vl) if cf_vl is not None else None,
             cf_lev]
    sum_drift = sum(v for v in parts if v is not None) if any(v is not None for v in parts) else None
    row("  Netto kontantstrøm fra driften", sum_drift, is_sum=True)

    row("KONTANTSTRØM FRA INVESTERING", None, False, True)
    cf_dm = chg(555)
    row("  Netto investering i driftsmidler", (-cf_dm) if cf_dm is not None else None)
    row("  Netto kontantstrøm fra investering",
        (-cf_dm) if cf_dm is not None else None, is_sum=True)

    row("KONTANTSTRØM FRA FINANSIERING", None, False, True)
    cf_ek = chg(715)
    cf_lang = chg(770) if chg(770) is not None else chg(760)
    ek_ex = (cf_ek - aarsres) if (cf_ek is not None and aarsres is not None) else cf_ek
    row("  Endring egenkapital (eks. årsresultat)", ek_ex)
    row("  Endring langsiktig gjeld", cf_lang)
    parts_fin = [ek_ex, cf_lang]
    sum_fin = sum(v for v in parts_fin if v is not None) if any(v is not None for v in parts_fin) else None
    row("  Netto kontantstrøm fra finansiering", sum_fin, is_sum=True)

    row("", None, False, False)
    all_sums = [sum_drift, (-cf_dm) if cf_dm is not None else None, sum_fin]
    net = sum(v for v in all_sums if v is not None) if any(v is not None for v in all_sums) else None
    row("NETTO ENDRING I KONTANTER", net, is_sum=True)

    bank_prev = ub_prev.get(655) if ub_prev else None
    bank_this = ub.get(655)
    row("  Kontanter ved årets begynnelse", bank_prev)
    row("  Kontanter ved årets slutt", bank_this, is_sum=True)

    return rows

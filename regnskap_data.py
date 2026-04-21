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
    (785,   "Betalbar skatt",                             2, False, False),
    (800,   "Skattetrekk og offentlige avgifter",        2, False, False),
    (803,   "Annen kortsiktig gjeld",                     2, False, False),
    (805,   "Utbytte",                                   2, False, False),
    (810,   "Sum kortsiktig gjeld",                      2, True,  False),
    (820,   "Sum gjeld",                                 1, True,  False),
    (830,   "SUM EGENKAPITAL OG GJELD",                  0, True,  False),
]

# Balanse splittet i to sider for PDF-eksport
BS_EIENDELER: list[tuple] = [row for row in BS_STRUCTURE
                              if row[0] != 830 or row[1] != "SUM EGENKAPITAL OG GJELD"]
BS_EIENDELER = BS_STRUCTURE[:BS_STRUCTURE.index(
    (665, "SUM EIENDELER", 0, True, False)
) + 1]

BS_EK_GJELD: list[tuple] = BS_STRUCTURE[BS_STRUCTURE.index(
    (None, "EGENKAPITAL OG GJELD", 0, False, True)
):]

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

# ---------------------------------------------------------------------------
# Finansielt rammeverk
# ---------------------------------------------------------------------------

FRAMEWORK_CHOICES: list[str] = [
    "NGAAP — små foretak",
    "NGAAP — mellomstore foretak",
    "NGAAP — store foretak",
]

PRINSIPP_DEFAULTS: dict[str, str] = {
    "NGAAP — små foretak": (
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
    ),
    "NGAAP — mellomstore foretak": (
        "Årsregnskapet er avlagt i samsvar med regnskapsloven og god "
        "regnskapsskikk for mellomstore foretak i Norge.\n\n"
        "Inntektsføring\n"
        "Inntekter resultatføres etter opptjeningsprinsippet. Tjenestesalg "
        "inntektsføres i takt med utførelsen.\n\n"
        "Klassifisering og vurdering av balanseposter\n"
        "Omløpsmidler og kortsiktig gjeld omfatter poster som forfaller til "
        "betaling innen ett år etter balansedagen, samt poster som knytter seg "
        "til varekretsløpet. Øvrige poster er klassifisert som anleggsmiddel/"
        "langsiktig gjeld.\n\n"
        "Omløpsmidler vurderes til laveste av anskaffelseskost og virkelig verdi. "
        "Anleggsmidler vurderes til anskaffelseskost med fradrag for planmessige "
        "avskrivninger og nedskrivninger.\n\n"
        "Fordringer\n"
        "Kundefordringer og andre fordringer er oppført til pålydende etter "
        "fradrag for avsetning til forventet tap. Avsetning vurderes individuelt.\n\n"
        "Varige driftsmidler\n"
        "Varige driftsmidler balanseføres og avskrives lineært over driftsmidlets "
        "forventede levetid. Direkte vedlikehold kostnadsføres løpende, "
        "mens påkostninger aktiveres.\n\n"
        "Skatter\n"
        "Skattekostnaden i resultatregnskapet omfatter periodens betalbare skatt "
        "og endring i utsatt skatt. Utsatt skatt er beregnet med 22 % på grunnlag "
        "av de midlertidige forskjeller som eksisterer mellom regnskapsmessige og "
        "skattemessige verdier. Utsatt skattefordel balanseføres når det er "
        "sannsynlig at den kan utnyttes.\n\n"
        "Kontantstrøm\n"
        "Kontantstrømoppstillingen er utarbeidet etter den indirekte metoden."
    ),
    "NGAAP — store foretak": (
        "Årsregnskapet er avlagt i samsvar med regnskapsloven og god "
        "regnskapsskikk for store foretak i Norge.\n\n"
        "Inntektsføring\n"
        "Inntekter resultatføres etter opptjeningsprinsippet. Tjenestesalg "
        "inntektsføres i takt med utførelsen.\n\n"
        "Klassifisering og vurdering av balanseposter\n"
        "Omløpsmidler og kortsiktig gjeld omfatter poster som forfaller til "
        "betaling innen ett år etter balansedagen, samt poster som knytter seg "
        "til varekretsløpet. Øvrige poster er klassifisert som anleggsmiddel/"
        "langsiktig gjeld.\n\n"
        "Omløpsmidler vurderes til laveste av anskaffelseskost og virkelig verdi. "
        "Anleggsmidler vurderes til anskaffelseskost med fradrag for planmessige "
        "avskrivninger og nedskrivninger.\n\n"
        "Fordringer\n"
        "Kundefordringer og andre fordringer er oppført til pålydende etter "
        "fradrag for avsetning til forventet tap. Avsetning vurderes individuelt.\n\n"
        "Varige driftsmidler\n"
        "Varige driftsmidler balanseføres og avskrives lineært over driftsmidlets "
        "forventede levetid. Direkte vedlikehold kostnadsføres løpende, "
        "mens påkostninger aktiveres.\n\n"
        "Immaterielle eiendeler\n"
        "Utgifter til forskning kostnadsføres løpende. Utgifter til utvikling "
        "balanseføres i den grad det kan identifiseres en fremtidig økonomisk "
        "fordel knyttet til utviklingen av en identifiserbar immateriell "
        "eiendel, og utgiftene kan måles pålitelig.\n\n"
        "Pensjoner\n"
        "Selskapet har pensjonsordning som behandles som en innskuddsordning. "
        "Pensjonskostnaden innregnes i resultatregnskapet i den perioden den "
        "påløper.\n\n"
        "Skatter\n"
        "Skattekostnaden i resultatregnskapet omfatter periodens betalbare skatt "
        "og endring i utsatt skatt. Utsatt skatt er beregnet med 22 % på grunnlag "
        "av de midlertidige forskjeller som eksisterer mellom regnskapsmessige og "
        "skattemessige verdier. Utsatt skattefordel balanseføres når det er "
        "sannsynlig at den kan utnyttes.\n\n"
        "Kontantstrøm\n"
        "Kontantstrømoppstillingen er utarbeidet etter den indirekte metoden."
    ),
}

# Backwards compat alias
PRINSIPP_DEFAULT = PRINSIPP_DEFAULTS["NGAAP — små foretak"]

# ---------------------------------------------------------------------------
# Tilleggsnote-specs for mellomstore/store foretak
# ---------------------------------------------------------------------------

PENSJON_SPEC: list[dict] = [
    {"type": "header", "label": "Pensjonsforpliktelser"},
    {"type": "field",  "label": "Innskuddsbasert pensjonskostnad",    "key": "pensjon_innskudd",  "default": ""},
    {"type": "field",  "label": "Ytelsesbasert pensjonskostnad",      "key": "pensjon_ytelse",    "default": ""},
    {"type": "field",  "label": "Netto pensjonsforpliktelse",         "key": "pensjon_netto",     "default": ""},
    {"type": "field",  "label": "Antall personer i ordningen",        "key": "pensjon_antall",    "default": ""},
]

DRIFTSMIDLER_SPEC: list[dict] = [
    {"type": "header", "label": "Varige driftsmidler"},
    {"type": "field",  "label": "Anskaffelseskost 01.01",             "key": "dm_akk_01",     "default": ""},
    {"type": "field",  "label": "+ Tilgang i år",                     "key": "dm_tilgang",    "default": ""},
    {"type": "field",  "label": "- Avgang i år",                      "key": "dm_avgang",     "default": ""},
    {"type": "field",  "label": "Anskaffelseskost 31.12",             "key": "dm_akk_31",     "default": ""},
    {"type": "sep"},
    {"type": "field",  "label": "Akkumulerte avskrivninger 01.01",    "key": "dm_avskr_01",   "default": ""},
    {"type": "field",  "label": "Årets avskrivninger",                "key": "dm_avskr_aar",  "default": ""},
    {"type": "field",  "label": "Akkumulerte avskrivninger 31.12",    "key": "dm_avskr_31",   "default": ""},
    {"type": "sep"},
    {"type": "auto",   "label": "Bokført verdi 31.12",               "regnr": 555, "period": "current"},
    {"type": "field",  "label": "Avskrivningsplan",                   "key": "dm_plan",       "default": "Lineær"},
    {"type": "field",  "label": "Økonomisk levetid (år)",             "key": "dm_levetid",    "default": ""},
]

BUNDNE_MIDLER_SPEC: list[dict] = [
    {"type": "header", "label": "Bundne midler"},
    {"type": "field",  "label": "Skattetrekksmidler",                 "key": "bundne_skatt",   "default": ""},
    {"type": "field",  "label": "Andre bundne midler",                "key": "bundne_andre",   "default": ""},
]

GJELD_SPEC: list[dict] = [
    {"type": "header", "label": "Langsiktig gjeld"},
    {"type": "field",  "label": "Pantelån",                           "key": "gjeld_pant",      "default": ""},
    {"type": "field",  "label": "Kassakreditt (trekk/limit)",         "key": "gjeld_kasse",     "default": ""},
    {"type": "field",  "label": "Annen langsiktig gjeld",             "key": "gjeld_annen",     "default": ""},
    {"type": "auto",   "label": "Sum langsiktig gjeld",               "regnr": 770, "period": "current"},
    {"type": "sep"},
    {"type": "header", "label": "Pantstillelser og garantier"},
    {"type": "field",  "label": "Bokført verdi pantsatte eiendeler",  "key": "pant_verdi",      "default": ""},
    {"type": "field",  "label": "Garantiforpliktelser",               "key": "pant_garanti",    "default": ""},
]

# Hvilke noter som kreves per rammeverk (note_id → (label, spec | None))
_BASE_NOTES: list[tuple[str, str, list | None]] = [
    ("regnskapsprinsipper", "Regnskapsprinsipper", None),
    ("lonnsnote",           "Lønnskostnader",      LONNS_SPEC),
    ("egenkapitalnote",     "Egenkapital",          EK_SPEC),
    ("aksjonaernote",       "Aksjonærer",           AKS_SPEC),
    ("skattenote",          "Skatter",              SKATT_SPEC),
    ("driftsmidlernote",    "Varige driftsmidler",  DRIFTSMIDLER_SPEC),
]

_MELLOMSTORE_EXTRA: list[tuple[str, str, list | None]] = [
    ("bundnemidlernote",    "Bundne midler",        BUNDNE_MIDLER_SPEC),
    ("gjeldnote",           "Gjeld og pant",        GJELD_SPEC),
]

_STORE_EXTRA: list[tuple[str, str, list | None]] = [
    ("pensjonsnote",        "Pensjoner",            PENSJON_SPEC),
    ("bundnemidlernote",    "Bundne midler",        BUNDNE_MIDLER_SPEC),
    ("gjeldnote",           "Gjeld og pant",        GJELD_SPEC),
]

FRAMEWORK_NOTES: dict[str, list[tuple[str, str, list | None]]] = {
    "NGAAP — små foretak":         _BASE_NOTES,
    "NGAAP — mellomstore foretak": _BASE_NOTES + _MELLOMSTORE_EXTRA,
    "NGAAP — store foretak":       _BASE_NOTES + _STORE_EXTRA,
}

# Default NOTE_SPECS for backward compat (små foretak)
NOTE_SPECS: list[tuple[str, str, list | None]] = _BASE_NOTES


def get_notes_for_framework(framework: str) -> list[tuple[str, str, list | None]]:
    """Returner liste med (note_id, label, spec) for gitt rammeverk."""
    return FRAMEWORK_NOTES.get(framework, _BASE_NOTES)


def build_note_numbers(
    notes: list[tuple[str, str, list | None]],
) -> tuple[dict[str, int], dict[int, tuple[int, str]]]:
    """Bygg note-nummerering og note-refs for et gitt sett med noter."""
    numbers: dict[str, int] = {}
    for idx, (note_id, _, _) in enumerate(notes):
        numbers[note_id] = idx + 1

    # regnr → (note_number, note_id)
    _REF_MAP: dict[int, str] = {
        40: "lonnsnote",
        260: "skattenote",
        715: "egenkapitalnote",
        555: "driftsmidlernote",
        770: "gjeldnote",
    }
    refs: dict[int, tuple[int, str]] = {}
    for regnr, nid in _REF_MAP.items():
        if nid in numbers:
            refs[regnr] = (numbers[nid], nid)

    return numbers, refs


# Static defaults for backward compat
NOTE_NUMBERS: dict[str, int] = {
    note_id: idx + 1
    for idx, (note_id, _, _) in enumerate(NOTE_SPECS)
}

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


# Computed sum rows for balance sheet.
# Order matters: leaf sums first, then higher-level sums.
_BS_SUM_FORMULAS: list[tuple[int, list[int]]] = [
    (590, [555, 580]),                # Sum anleggsmidler
    (660, [605, 610, 630, 655]),      # Sum omløpsmidler
    (665, [590, 660]),                # SUM EIENDELER
    (770, [735, 760]),                # Sum langsiktig gjeld
    (810, [780, 785, 800, 803, 805]), # Sum kortsiktig gjeld
    (820, [770, 810]),                # Sum gjeld
    (830, [715, 820]),                # SUM EGENKAPITAL OG GJELD
]


def _fill_computed_sums(ub: dict[int, float]) -> None:
    """Fill in missing balance sheet sum rows from their components."""
    for sum_regnr, components in _BS_SUM_FORMULAS:
        if sum_regnr in ub:
            continue  # already has a value from the data
        parts = [ub.get(c, 0) for c in components]
        total = sum(parts)
        if any(c in ub for c in components):
            ub[sum_regnr] = total


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
    _fill_computed_sums(out)
    return out


def fmt_amount(val: float | None, blank_zero: bool = True) -> str:
    """Formater beløp med norsk tusenskille, uten desimaler. Returnerer '–' for None."""
    if val is None:
        return "–"
    if isinstance(val, float) and val != val:  # NaN
        return "–"
    if blank_zero and abs(val) < 0.5:
        return "–"
    rounded = round(val)
    abs_val = abs(rounded)
    int_str = f"{abs_val:,}".replace(",", "\u202f")  # narrow no-break space
    sign = "-" if rounded < 0 else ""
    return f"{sign}{int_str}"


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


# ---------------------------------------------------------------------------
# Note-malbibliotek (lagres som JSON i config/regnskap/)
# ---------------------------------------------------------------------------

import json
from pathlib import Path

_TEMPLATE_DIR = Path(__file__).parent / "config" / "regnskap" / "note_templates"


def _ensure_template_dir() -> Path:
    _TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    return _TEMPLATE_DIR


def save_note_template(name: str, note_data: dict[str, dict[str, str]]) -> Path:
    """Lagre en notemal til biblioteket. Returnerer filstien."""
    d = _ensure_template_dir()
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
    path = d / f"{safe}.json"
    path.write_text(json.dumps({
        "name": name,
        "notes": note_data,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_note_templates() -> list[str]:
    """Returner navnene på alle lagrede notemaler."""
    d = _ensure_template_dir()
    names: list[str] = []
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            names.append(data.get("name", p.stem))
        except Exception:
            names.append(p.stem)
    return names


def load_note_template(name: str) -> dict[str, dict[str, str]] | None:
    """Last inn notemal fra biblioteket. Returnerer notes-dict eller None."""
    d = _ensure_template_dir()
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
    path = d / f"{safe}.json"
    if not path.exists():
        # Try fuzzy match on stem
        for p in d.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("name") == name:
                    return data.get("notes", {})
            except Exception:
                continue
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("notes", {})
    except Exception:
        return None


def delete_note_template(name: str) -> bool:
    """Slett en notemal. Returnerer True hvis slettet."""
    d = _ensure_template_dir()
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
    path = d / f"{safe}.json"
    if path.exists():
        path.unlink()
        return True
    return False

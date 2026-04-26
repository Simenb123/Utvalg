from __future__ import annotations

import tempfile
from pathlib import Path

from .control.data import (
    CONTROL_STATEMENT_VIEW_ALL,
    CONTROL_STATEMENT_VIEW_LABELS as _PAGE_CONTROL_STATEMENT_VIEW_LABELS,
    CONTROL_STATEMENT_VIEW_LEGACY,
    CONTROL_STATEMENT_VIEW_PAYROLL,
    CONTROL_STATEMENT_VIEW_UNCLASSIFIED,
    control_statement_view_requires_unclassified,
)
from .control.rf1022_contract import (
    RF1022_ACCOUNT_COLUMNS as _RF1022_ACCOUNT_DATA_COLUMNS,
    RF1022_OVERVIEW_COLUMNS as _RF1022_OVERVIEW_DATA_COLUMNS,
)
from .control.rf1022_bridge import RF1022_A07_BRIDGE as _RF1022_A07_BRIDGE


_A07_DIAGNOSTICS_ENABLED = True
_A07_DIAGNOSTICS_LOG = Path(tempfile.gettempdir()) / "utvalg_a07_debug.log"

_A07_COLUMNS = (
    ("Kode", "Kode", 180, "w"),
    ("Navn", "Navn", 280, "w"),
    ("Belop", "Belop", 120, "e"),
    ("Status", "Status", 120, "w"),
    ("Kontoer", "Kontoer", 200, "w"),
)

_CONTROL_COLUMNS = (
    ("A07Post", "A07-post", 320, "w"),
    ("AgaPliktig", "AGA", 70, "center"),
    ("A07_Belop", "A07", 120, "e"),
    ("GL_Belop", "SB", 120, "e"),
    ("Diff", "Diff", 120, "e"),
)

_CONTROL_A07_TOTAL_IID = "__a07_total__"
_SUMMARY_TOTAL_TAG = "summary_total"
_A07_MATCHED_TAG = "a07_matched"

_CONTROL_RF1022_COLUMNS = (
    ("Post", "Post", 70, "w"),
    ("Kontrollgruppe", "Kontrollgruppe", 260, "w"),
    ("GL_Belop", "SB", 120, "e"),
    ("A07", "A07", 120, "e"),
    ("Diff", "Diff", 120, "e"),
)

_CONTROL_GL_COLUMNS = (
    ("Konto", "Konto", 80, "w"),
    ("Navn", "Kontonavn", 240, "w"),
    ("Kode", "A07-kode", 155, "w"),
    ("Rf1022GroupId", "RF-1022", 135, "w"),
    ("AliasStatus", "Alias", 85, "w"),
    ("Kol", "Kol", 70, "w"),
    ("MappingAuditStatus", "Kontroll", 100, "w"),
    ("IB", "IB", 110, "e"),
    ("Endring", "Endring", 120, "e"),
    ("UB", "UB", 110, "e"),
)

_CONTROL_GL_DATA_COLUMNS = (
    "Konto",
    "Navn",
    "IB",
    "Endring",
    "UB",
    "BelopAktiv",
    "Kol",
    "Kode",
    "Rf1022GroupId",
    "AliasStatus",
    "WorkFamily",
    "MappingAuditStatus",
    "MappingAuditReason",
    "MappingAuditRawStatus",
    "MappingAuditRawReason",
    "A07CodeDiff",
)

_CONTROL_SELECTED_ACCOUNT_COLUMNS = (
    ("Konto", "Konto", 90, "w"),
    ("Navn", "Kontonavn", 260, "w"),
    ("AliasStatus", "Alias", 85, "w"),
    ("MappingAuditStatus", "Kontroll", 110, "w"),
    ("MappingAuditReason", "Hvorfor", 320, "w"),
    ("IB", "IB", 110, "e"),
    ("Endring", "Endring", 120, "e"),
    ("UB", "UB", 110, "e"),
)

_CONTROL_SUGGESTION_COLUMNS = (
    ("ForslagVisning", "Kontoer", 420, "w"),
    ("A07_Belop", "A07", 110, "e"),
    ("GL_Sum", "SB forslag", 120, "e"),
    ("Diff", "Diff", 110, "e"),
    ("Forslagsstatus", "Status", 120, "w"),
    ("HvorforKort", "Hvorfor", 240, "w"),
)

_RF1022_CANDIDATE_COLUMNS = (
    ("Konto", "Konto", 90, "w"),
    ("Navn", "Kontonavn", 260, "w"),
    ("Kode", "A07-kode", 170, "w"),
    ("BelopAktiv", "Belop", 120, "e"),
    ("Matchgrunnlag", "Matchgrunnlag", 220, "w"),
    ("Belopsgrunnlag", "Belopsgrunnlag", 180, "w"),
    ("Forslagsstatus", "Status", 120, "w"),
)

_CONTROL_GL_SCOPE_LABELS = {
    "alle": "Alle kontoer",
    "koblede": "Koblet til valgt A07-kode",
    "forslag": "Forslag for valgt A07-kode",
    # Legacy input alias only. It is intentionally not shown in the UI.
    "relevante": "Koblet til valgt A07-kode",
}

_CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL = {
    "rf1022": {
        "alle": "Alle kontoer",
        "koblede": "Valgt RF-1022-post",
    },
    "a07": {
        "alle": "Alle kontoer",
        "koblede": "Koblet til valgt A07-kode",
        "forslag": "Forslag for valgt A07-kode",
    },
}

_CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL = {
    "rf1022": ("alle", "koblede"),
    "a07": ("alle", "koblede", "forslag"),
}

_CONTROL_GL_SCOPE_ALIASES = {
    "relevante": "koblede",
}

_CONTROL_GL_MAPPING_LABELS = {
    "alle": "Alle",
    "mappede": "Kun mappede",
}

_CONTROL_GL_SERIES_LABELS = {
    "alle": "Alle serier",
    "1": "1xxx",
    "2": "2xxx",
    "3": "3xxx",
    "4": "4xxx",
    "5": "5xxx",
    "6": "6xxx",
    "7": "7xxx",
    "8": "8xxx",
    "9": "9xxx",
}

_A07_MATCH_FILTER_LABELS = {
    "alle": "Alle",
    "avstemt": "Avstemt",
    "ikke_avstemt": "Ikke avstemt",
}

_MAPPING_FILTER_LABELS = {
    "alle": "Alle",
    "kritiske": "Kritiske",
    "feil": "Feil",
    "mistenkelige": "Mistenkelige",
    "uavklarte": "Uavklarte",
    "trygge": "Trygge",
}

_MAPPING_FILTER_KEYS = ("alle", "kritiske", "feil", "mistenkelige", "uavklarte", "trygge")

_CONTROL_ALTERNATIVE_MODE_LABELS = {
    "suggestions": "Beste forslag",
    "history": "Historikk",
}

_CONTROL_HIDDEN_CODES = {
    "aga",
    "forskuddstrekk",
    "finansskattloenn",
    "finansskattlønn",
    # Legacy/mojibake alias accepted as input, but never shown.
    "finansskattlÃ¸nn",
}

_CONTROL_EXTRA_COLUMNS = (
    "Kode",
    "Navn",
    "Status",
    "AntallKontoer",
    "Anbefalt",
    "DagensMapping",
    "Arbeidsstatus",
    "GuidetStatus",
    "GuidetNeste",
    "MatchingReady",
    "SuggestionGuardrail",
    "SuggestionGuardrailReason",
    "CurrentMappingSuspicious",
    "CurrentMappingSuspiciousReason",
    "Rf1022GroupId",
    "WorkFamily",
    "ReconcileStatus",
    "NesteHandling",
    "Locked",
    "Hvorfor",
)

_GROUP_COLUMNS = (
    ("Navn", "Gruppe", 260, "w"),
    ("Members", "A07-koder", 360, "w"),
    ("A07_Belop", "A07", 110, "e"),
    ("GL_Belop", "SB", 110, "e"),
    ("Diff", "Diff", 110, "e"),
    ("Locked", "Låst", 60, "center"),
)

_SUGGESTION_COLUMNS = (
    ("Kode", "Kode", 140, "w"),
    ("KodeNavn", "Navn", 220, "w"),
    ("Basis", "Basis", 80, "w"),
    ("A07_Belop", "A07", 120, "e"),
    ("ForslagVisning", "Kontoer", 320, "w"),
    ("GL_Sum", "SB forslag", 120, "e"),
    ("Diff", "Diff", 120, "e"),
    ("Forslagsstatus", "Status", 110, "w"),
    ("HvorforKort", "Hvorfor", 220, "w"),
)

_RECONCILE_COLUMNS = (
    ("Kode", "Kode", 140, "w"),
    ("Navn", "Navn", 220, "w"),
    ("A07_Belop", "A07", 120, "e"),
    ("GL_Belop", "SB", 120, "e"),
    ("Diff", "Diff", 120, "e"),
    ("AntallKontoer", "AntallKontoer", 110, "e"),
    ("Kontoer", "Kontoer", 200, "w"),
    ("WithinTolerance", "OK", 70, "center"),
)

_MAPPING_COLUMNS = (
    ("Konto", "Konto", 110, "w"),
    ("Navn", "Kontonavn", 240, "w"),
    ("Kode", "Kode", 180, "w"),
    ("Rf1022GroupId", "RF-1022", 140, "w"),
    ("AliasStatus", "Alias", 90, "w"),
    ("Kol", "Kol", 70, "w"),
    ("Status", "Kontroll", 110, "w"),
    ("Reason", "Hvorfor", 340, "w"),
)

_UNMAPPED_COLUMNS = (
    ("Konto", "Konto", 110, "w"),
    ("Navn", "Kontonavn", 260, "w"),
    ("GL_Belop", "SB", 120, "e"),
)

_HISTORY_COLUMNS = (
    ("Kode", "Kode", 140, "w"),
    ("Navn", "Navn", 220, "w"),
    ("AarKontoer", "I år", 180, "w"),
    ("HistorikkKontoer", "Historikk", 180, "w"),
    ("Status", "Status", 160, "w"),
    ("KanBrukes", "Kan brukes", 90, "center"),
    ("Merknad", "Merknad", 320, "w"),
)

_CONTROL_STATEMENT_COLUMNS = (
    ("Gruppe", "Gruppe", 180, "w"),
    ("Navn", "Navn", 220, "w"),
    ("IB", "IB", 110, "e"),
    ("Endring", "Endring", 120, "e"),
    ("UB", "UB", 110, "e"),
    ("A07", "A07", 110, "e"),
    ("Diff", "Diff", 110, "e"),
    ("Status", "Status", 140, "w"),
    ("AntallKontoer", "Antall", 90, "e"),
)

_RF1022_OVERVIEW_COLUMNS = (
    ("Post", "Post", 70, "w"),
    ("Omraade", "Område", 190, "w"),
    ("Kontrollgruppe", "Kontrollgruppe", 220, "w"),
    ("GL_Belop", "SB", 110, "e"),
    ("SamledeYtelser", "SB opplys.", 120, "e"),
    ("A07", "A07 opplys.", 120, "e"),
    ("Diff", "Diff opplys.", 120, "e"),
    ("AgaGrunnlag", "SB AGA", 110, "e"),
    ("A07Aga", "A07 AGA", 110, "e"),
    ("AgaDiff", "Diff AGA", 110, "e"),
    ("Status", "Status", 100, "w"),
    ("AntallKontoer", "Antall", 80, "e"),
)

_CONTROL_WORK_LEVEL_LABELS = {
    "rf1022": "RF-1022",
    "a07": "A07",
}

_RF1022_ACCOUNT_COLUMNS = (
    ("Post", "Post", 150, "w"),
    ("Konto", "Kontonr", 90, "w"),
    ("Navn", "Kontobetegnelse", 240, "w"),
    ("KostnadsfortYtelse", "Kostnadsført", 120, "e"),
    ("TilleggTidligereAar", "Tillegg tidl. år", 120, "e"),
    ("FradragPaalopt", "Fradrag påløpt", 120, "e"),
    ("SamledeYtelser", "Samlede ytelser", 120, "e"),
    ("AgaPliktig", "AGA-pliktig", 95, "center"),
    ("AgaGrunnlag", "AGA-grunnlag", 120, "e"),
    ("Feriepengegrunnlag", "Feriep.grl.", 95, "center"),
)

assert tuple(column_id for column_id, *_rest in _RF1022_OVERVIEW_COLUMNS) == tuple(
    column_id for column_id in _RF1022_OVERVIEW_DATA_COLUMNS if column_id != "GroupId"
)
assert tuple(column_id for column_id, *_rest in _RF1022_ACCOUNT_COLUMNS) == _RF1022_ACCOUNT_DATA_COLUMNS

_RF1022_POST_RULES = (
    (100, "Lønn o.l.", {"100_loenn_ol"}),
    (100, "Refusjon", {"100_refusjon"}),
    (111, "Naturalytelser", {"111_naturalytelser"}),
    (112, "Pensjon", {"112_pensjon"}),
    (999, "Uavklart RF-1022", {"uavklart_rf1022"}),
    (
        100,
        "Lønn og trekk",
        {"Lønnskostnad", "Skyldig lønn", "Feriepenger", "Skyldig feriepenger", "Skattetrekk"},
    ),
    (
        110,
        "Arbeidsgiveravgift",
        {
            "Kostnadsfort arbeidsgiveravgift",
            "Kostnadsfort arbeidsgiveravgift av feriepenger",
            "Skyldig arbeidsgiveravgift",
            "Skyldig arbeidsgiveravgift av feriepenger",
        },
    ),
    (120, "Pensjon og refusjon", {"Pensjonskostnad", "Skyldig pensjon", "Refusjon"}),
    (130, "Naturalytelser og styrehonorar", {"Naturalytelse", "Styrehonorar"}),
)

_A07_FILTER_LABELS = {
    "alle": "Alle",
    "uloste": "Uløste",
    "avvik": "Avvik",
    "ikke_mappet": "Ikke mappet",
    "ok": "OK",
    "ekskludert": "Ekskludert",
}

# Guided standardvisning viser arbeidsko, mistenkelige, alle og ferdige i filteret,
# men vi beholder resten av noklene for compat i status-/filterlogikken.
_CONTROL_PRIMARY_VIEW_KEYS = ("neste", "mistenkelig", "alle", "ferdig")

_CONTROL_VIEW_LABELS = {
    "neste": "Arbeidskø",
    "mistenkelig": "Mistenkelige",
    "ulost": "Må avklares",
    "forslag": "Trygge forslag",
    "historikk": "Historikk",
    "manuell": "Til kontroll",
    "ferdig": "Ferdig",
    "alle": "Alle",
}

_SUGGESTION_SCOPE_LABELS = {
    "valgt_kode": "Valgt kode",
    "uloste": "Uløste koder",
    "alle": "Alle forslag",
}

_BASIS_LABELS = {
    "Endring": "Endring",
    "UB": "UB",
    "IB": "IB",
}

_CONTROL_DRAG_IDLE_HINT = "Velg kode og konto, eller dra konto inn."
_CONTROL_STATEMENT_VIEW_LABELS = dict(_PAGE_CONTROL_STATEMENT_VIEW_LABELS)

_NUMERIC_COLUMNS_ZERO_DECIMALS = {"AntallKontoer"}
_NUMERIC_COLUMNS_THREE_DECIMALS = {"Score"}
_NUMERIC_COLUMNS_TWO_DECIMALS = {
    "Belop",
    "Diff",
    "A07",
    "A07_Belop",
    "GL_Belop",
    "GL_Sum",
    "IB",
    "UB",
    "Endring",
}

_MATCHER_SETTINGS_DEFAULTS = {
    "tolerance_rel": 0.02,
    "tolerance_abs": 100.0,
    "max_combo": 2,
    "candidates_per_code": 20,
    "top_suggestions_per_code": 5,
    "historical_account_boost": 0.12,
    "historical_combo_boost": 0.10,
}


__all__ = [
    "CONTROL_STATEMENT_VIEW_ALL",
    "CONTROL_STATEMENT_VIEW_LEGACY",
    "CONTROL_STATEMENT_VIEW_PAYROLL",
    "CONTROL_STATEMENT_VIEW_UNCLASSIFIED",
    "_A07_COLUMNS",
    "_A07_DIAGNOSTICS_ENABLED",
    "_A07_DIAGNOSTICS_LOG",
    "_A07_FILTER_LABELS",
    "_A07_MATCH_FILTER_LABELS",
    "_A07_MATCHED_TAG",
    "_BASIS_LABELS",
    "_CONTROL_ALTERNATIVE_MODE_LABELS",
    "_CONTROL_A07_TOTAL_IID",
    "_CONTROL_COLUMNS",
    "_CONTROL_DRAG_IDLE_HINT",
    "_CONTROL_EXTRA_COLUMNS",
    "_CONTROL_GL_COLUMNS",
    "_CONTROL_GL_DATA_COLUMNS",
    "_CONTROL_GL_SCOPE_ALIASES",
    "_CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL",
    "_CONTROL_GL_SCOPE_LABELS",
    "_CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL",
    "_CONTROL_GL_MAPPING_LABELS",
    "_CONTROL_GL_SERIES_LABELS",
    "_CONTROL_HIDDEN_CODES",
    "_CONTROL_RF1022_COLUMNS",
    "_CONTROL_SELECTED_ACCOUNT_COLUMNS",
    "_CONTROL_STATEMENT_COLUMNS",
    "_CONTROL_STATEMENT_VIEW_LABELS",
    "_CONTROL_SUGGESTION_COLUMNS",
    "_CONTROL_PRIMARY_VIEW_KEYS",
    "_CONTROL_VIEW_LABELS",
    "_CONTROL_WORK_LEVEL_LABELS",
    "_GROUP_COLUMNS",
    "_HISTORY_COLUMNS",
    "_MAPPING_FILTER_KEYS",
    "_MAPPING_FILTER_LABELS",
    "_MAPPING_COLUMNS",
    "_MATCHER_SETTINGS_DEFAULTS",
    "_NUMERIC_COLUMNS_THREE_DECIMALS",
    "_NUMERIC_COLUMNS_TWO_DECIMALS",
    "_NUMERIC_COLUMNS_ZERO_DECIMALS",
    "_RECONCILE_COLUMNS",
    "_RF1022_A07_BRIDGE",
    "_RF1022_ACCOUNT_COLUMNS",
    "_RF1022_OVERVIEW_COLUMNS",
    "_RF1022_POST_RULES",
    "_SUGGESTION_COLUMNS",
    "_SUGGESTION_SCOPE_LABELS",
    "_SUMMARY_TOTAL_TAG",
    "_UNMAPPED_COLUMNS",
    "control_statement_view_requires_unclassified",
]

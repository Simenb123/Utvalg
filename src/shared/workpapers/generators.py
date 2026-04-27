"""Register over innebygde arbeidspapir-generatorer.

Speiler høyreklikk-menyen i page_analyse_ui.py (rapportseksjon). Hver
oppføring peker på en metode på AnalysePage som allerede finnes. Registret
brukes av Arbeidspapir-fanen i Admin og av handling-kobling for å
gjenkjenne innebygde (i motsetning til manuelle) arbeidspapir.

ID-konvensjon: `wp:<kort_navn>` for innebygde. Manuelle arbeidspapir
bruker UUID (se workpaper_library.Workpaper.new).
"""

from __future__ import annotations

from dataclasses import dataclass


BUILTIN_ID_PREFIX = "wp:"


@dataclass(frozen=True)
class BuiltinGenerator:
    id: str
    navn: str
    method_name: str  # navn på AnalysePage-metoden som kjører eksporten
    beskrivelse: str = ""


BUILTIN_GENERATORS: tuple[BuiltinGenerator, ...] = (
    BuiltinGenerator(
        id="wp:regnskap_excel",
        navn="Eksporter regnskapsoppstilling til Excel",
        method_name="_export_regnskapsoppstilling_excel",
    ),
    BuiltinGenerator(
        id="wp:nokkeltall_html",
        navn="Nøkkeltallsrapport (HTML)",
        method_name="_export_nokkeltall_html",
    ),
    BuiltinGenerator(
        id="wp:nokkeltall_pdf",
        navn="Nøkkeltallsrapport (PDF)",
        method_name="_export_nokkeltall_pdf",
    ),
    BuiltinGenerator(
        id="wp:motpost_flowchart_html",
        navn="Motpost-flytdiagram (HTML)",
        method_name="_export_motpost_flowchart_html",
    ),
    BuiltinGenerator(
        id="wp:motpost_flowchart_pdf",
        navn="Motpost-flytdiagram (PDF)",
        method_name="_export_motpost_flowchart_pdf",
    ),
    BuiltinGenerator(
        id="wp:sb_hb_avstemming",
        navn="SB/HB Avstemming",
        method_name="_export_ib_ub_control",
    ),
    BuiltinGenerator(
        id="wp:ib_ub_kontinuitet",
        navn="IB/UB-kontinuitetskontroll",
        method_name="_export_ib_ub_continuity",
    ),
    BuiltinGenerator(
        id="wp:hb_versjonsdiff",
        navn="HB Versjonsdiff",
        method_name="_export_hb_version_diff",
    ),
    BuiltinGenerator(
        id="wp:klientinfo",
        navn="Klientinfo, roller & eierskap",
        method_name="_export_klientinfo_workpaper",
    ),
)


def is_builtin(wp_id: str) -> bool:
    return bool(wp_id) and wp_id.startswith(BUILTIN_ID_PREFIX)


def builtin_by_id() -> dict[str, BuiltinGenerator]:
    return {g.id: g for g in BUILTIN_GENERATORS}


def find_builtin(wp_id: str) -> BuiltinGenerator | None:
    return builtin_by_id().get(wp_id)

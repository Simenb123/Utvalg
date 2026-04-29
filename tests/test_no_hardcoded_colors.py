"""Lint-test som hindrer at nye hardkodede hex-farger introduseres.

Bakgrunn
--------
Repo-et har historisk samlet ~652 hardkodede ``"#XXXXXX"``-strenger på tvers
av ~70 filer. Dette gjør at endringer i ``src/shared/ui/tokens.py`` ikke
forplanter seg til hele appen — designendringer må manuelt jages opp i
hver enkelt fil.

Strategi
--------
**To tester:**

1. ``test_no_hardcoded_colors_outside_allowlist`` — feiler hvis nye filer
   utenfor en kjent allowlist har hardkodede hex-farger. Tvinger ny kode
   til å bruke tokens.

2. ``test_total_hardcoded_color_count_does_not_increase`` — global teller
   med BASELINE som "tak". Feiler hvis totalen øker. Når en allowlistet
   fil ryddes, MÅ både fila fjernes fra ``_ALLOWLIST`` og ``BASELINE``
   senkes tilsvarende.

Migrering
---------
Når du rydder en fil:
1. Fjern fila fra ``_ALLOWLIST``
2. Senk ``BASELINE`` med antall farger du fjernet
3. Kjør ``pytest tests/test_no_hardcoded_colors.py -v`` — alt skal fortsatt passere

Unntak per linje
----------------
Hvis du HAR en god grunn til å beholde en hardkodet farge (f.eks. matchende
farge til ekstern brand), legg til kommentaren ``# design-exception: <grunn>``
på samme linje. Linja vil da ignoreres av testen.

Eksempel:

    BRAND_BLUE = "#1A4C7A"  # design-exception: ekstern logo må matches eksakt
"""
from __future__ import annotations

import re
from pathlib import Path


_HEX_RE = re.compile(r'"#[0-9A-Fa-f]{6}"')

# Filer/kataloger der hardkodede farger er TILLATT (token-eier, tester osv.).
_EXEMPT_PREFIXES = (
    "src/shared/ui/tokens.py",       # eier av tokenene
    "src/shared/ui/page_header.py",  # ikon-fargeforsterkning bruker bevisst hardkodede RGB
    "tests/",                        # tester kan ha hex (regex-patterns, asserts)
    "flowchart_editor/",             # eget design-domene, ekskludert
    ".venv/",
    "build/",
    "dist/",
    "__pycache__/",
)

# Kjente filer med hardkodede farger — gjeld vi vil rydde gradvis.
# Når en fil ryddes:
#   1. Fjern den herfra
#   2. Senk BASELINE tilsvarende antall farger som ble fjernet
_ALLOWLIST: set[str] = {
    "analyse_disponering_dialog.py",
    "analyse_sb_motpost.py",
    "analyse_sb_refresh.py",
    "analyse_sb_remap.py",
    "analyse_sb_tree.py",
    "client_store_enrich_ui.py",
    "page_analyse_nokkeltall_render.py",
    "page_analyse_pivot.py",
    "page_analyse_ui_helpers.py",
    "page_analyse_ui_panels.py",
    "src/audit_actions/link_dialog.py",
    "src/audit_actions/motpost/combinations_popup.py",
    "src/audit_actions/motpost/expected_rules_dialog.py",
    "src/audit_actions/motpost/flowchart_report.py",
    "src/audit_actions/motpost/flowchart_svg.py",
    "src/audit_actions/motpost/view_konto_ui.py",
    "src/audit_actions/nokkeltall/report.py",
    "src/audit_actions/nokkeltall/svg.py",
    "src/monitoring/dashboard.py",
    "src/pages/a07/frontend/drag_drop_helpers.py",
    "src/pages/admin/brreg_mapping.py",
    "src/pages/admin/page.py",
    "src/pages/admin/rl.py",
    "src/pages/admin/workpapers.py",
    "src/pages/ar/backend/formatters.py",
    "src/pages/ar/frontend/compare.py",
    "src/pages/ar/frontend/drilldown.py",
    "src/pages/ar/frontend/import_detail_dialog.py",
    "src/pages/ar/frontend/pdf_review_dialog.py",
    "src/pages/consolidation/frontend/associate_ui.py",
    "src/pages/consolidation/frontend/elim_ui.py",
    "src/pages/consolidation/frontend/mapping_tab.py",
    "src/pages/consolidation/frontend/pdf_review_dialog.py",
    "src/pages/consolidation/frontend/shell_ui.py",
    "src/pages/dataset/frontend/pane_store_section.py",
    "src/pages/dataset/frontend/pane_store_ui.py",
    "src/pages/driftsmidler/frontend/page.py",
    "src/pages/fagchat/page_fagchat.py",
    "src/pages/mva/frontend/avstemming_dialog.py",
    "src/pages/mva/frontend/page.py",
    "src/pages/regnskap/frontend/klient.py",
    "src/pages/regnskap/frontend/noter.py",
    "src/pages/regnskap/frontend/page.py",
    "src/pages/reskontro/frontend/brreg_panel.py",
    "src/pages/reskontro/frontend/popups.py",
    "src/pages/reskontro/frontend/ui_build.py",
    "src/pages/revisjonshandlinger/detail.py",
    "src/pages/revisjonshandlinger/page.py",
    "src/pages/saldobalanse/frontend/page.py",
    # scoping ryddet 2026-04-28: 4 farger til tokens, 32 markert som design-exception
    # skatt ryddet 2026-04-28: 5 til tokens (POS_TEXT_DARK ×2, NEG_TEXT_DARK ×2, INFO_TEXT ×1), 4 markert
    "src/pages/utvalg/selection_studio/bilag_split_view.py",
    "src/pages/utvalg/selection_studio/drill.py",
    "src/pages/utvalg/selection_studio/ui_builder.py",
    "src/shared/document_control/batch_dialog.py",
    "src/shared/document_control/dialog.py",
    "src/shared/document_control/review_dialog.py",
    "src/shared/document_control/viewer.py",
    "src/shared/ui/loading.py",
    "src/shared/ui/managed_treeview.py",
    "tb_preview_dialog.py",
    "theme.py",
    "ui_main.py",
    "version_overview_dialog.py",
    "views_column_chooser.py",
    "views_konto_klassifisering.py",
    "views_rl_account_drill.py",
}

# Total telling i allowlist + alle uten allowlist. SKAL synke over tid.
# Senk denne hver gang du fjerner en fil fra _ALLOWLIST.
#
# Historikk:
#   2026-04-28: 652 (initial baseline)
#   2026-04-28: 616 (-36, scoping/page.py ryddet — 4 til tokens, 32 markert)
#   2026-04-28: 604 (-12, skatt/page.py ryddet — 5 til tokens, 4 markert + Utvalg PageHeader)
#   2026-04-28: 573 (-31, statistikk/frontend/page.py ryddet — 13 til tokens, 18 markert)
#   2026-04-28: 513 (-60, ar/frontend/page.py + chart.py ryddet — 3 til tokens, resten markert)
BASELINE: int = 513


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_exempt(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix.rstrip("/")) for prefix in _EXEMPT_PREFIXES)


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Returner (linjenummer, hex-streng) for hver hardkodet farge i filen.

    Linjer med kommentaren ``# design-exception:`` ignoreres.
    """
    out: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    for i, line in enumerate(text.splitlines(), 1):
        if "design-exception:" in line:
            continue
        for match in _HEX_RE.finditer(line):
            out.append((i, match.group(0)))
    return out


def _all_python_files() -> list[Path]:
    root = _repo_root()
    return sorted(root.rglob("*.py"))


def test_no_hardcoded_colors_outside_allowlist() -> None:
    """Filer som ikke er i _ALLOWLIST eller _EXEMPT_PREFIXES skal være rene.

    Dette er hovedmekanismen som hindrer ny gjeld: enhver ny fil må enten
    bruke tokens, eller dokumentere unntaket per linje med
    ``# design-exception: <grunn>``.
    """
    root = _repo_root()
    violations: list[str] = []
    for py in _all_python_files():
        rel = py.relative_to(root).as_posix()
        if _is_exempt(rel):
            continue
        if rel in _ALLOWLIST:
            continue
        for line, hex_val in _scan_file(py):
            violations.append(f"  {rel}:{line}  {hex_val}")

    if violations:
        msg = (
            f"\nHardkodede farger funnet i {len(violations)} linje(r) utenfor allowlist.\n"
            f"Bruk tokens fra src/shared/ui/tokens.py, eller hvis du virkelig må,\n"
            f"legg til '# design-exception: <grunn>' på samme linje.\n\n"
            + "\n".join(violations[:30])
        )
        if len(violations) > 30:
            msg += f"\n  ... og {len(violations) - 30} flere"
        raise AssertionError(msg)


def test_total_hardcoded_color_count_does_not_increase() -> None:
    """Total telling skal aldri øke. Synker over tid når filer ryddes.

    Hvis denne testen feiler med "ØKNING": du har lagt til hardkodede farger
    i en fil som er i allowlist. Bruk tokens i stedet.

    Hvis denne testen feiler med "MISMATCH": du har ryddet en fil men ikke
    senket BASELINE. Oppdater BASELINE til faktisk antall.
    """
    root = _repo_root()
    total = 0
    for py in _all_python_files():
        rel = py.relative_to(root).as_posix()
        if _is_exempt(rel):
            continue
        total += len(_scan_file(py))

    assert total <= BASELINE, (
        f"\nØKNING: Hardkodede farger har økt fra {BASELINE} til {total}.\n"
        f"Bruk tokens fra src/shared/ui/tokens.py i stedet for nye hex-strenger."
    )

    # Hvis tallet har sunket vesentlig, varsle slik at BASELINE oppdateres.
    # Vi tillater drift på opp til 5 linjer (folk fjerner ad-hoc bruk uten
    # å oppdatere BASELINE), men advarer ved mer.
    if total < BASELINE - 5:
        raise AssertionError(
            f"\nMISMATCH: Faktisk antall hardkodede farger ({total}) er nå "
            f"vesentlig under BASELINE ({BASELINE}).\n"
            f"Oppdater BASELINE i tests/test_no_hardcoded_colors.py til {total}."
        )


def test_allowlist_entries_actually_exist() -> None:
    """Hver fil i _ALLOWLIST må eksistere og inneholde minst én hardkodet farge.

    Hvis denne testen feiler: noen har slettet eller migrert en fil uten å
    oppdatere _ALLOWLIST. Fjern stale-entry derfra.
    """
    root = _repo_root()
    stale: list[str] = []
    for rel in sorted(_ALLOWLIST):
        path = root / rel
        if not path.exists():
            stale.append(f"{rel}  (eksisterer ikke)")
            continue
        if not _scan_file(path):
            stale.append(f"{rel}  (ingen hardkodede farger igjen — fjern fra allowlist)")

    if stale:
        raise AssertionError(
            "\nStale entries i _ALLOWLIST (fjern dem):\n  " + "\n  ".join(stale)
        )

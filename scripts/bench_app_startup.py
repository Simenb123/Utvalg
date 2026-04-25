"""bench_app_startup.py - mål hvor lang tid app-oppstart bruker.

Bryter ned i:
  1. Import av tunge pakker (pandas, openpyxl, etc.)
  2. Import av hver page-modul
  3. Opprettelse av hver Page-instans (UI-konstruksjon)

Bruk:
    python scripts/bench_app_startup.py

Skriver tabell sortert etter tid, så du ser hvilke importer/page-builders
som dominerer startup-tiden.
"""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

# Legg repo-rot på path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def time_import(module_name: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    try:
        importlib.import_module(module_name)
        ok = True
    except Exception as exc:
        print(f"  FEIL ved {module_name}: {exc}")
        ok = False
    elapsed = (time.perf_counter() - t0) * 1000
    return (module_name, elapsed if ok else -1)


def main() -> None:
    print("=== STEG 1: Tunge eksterne pakker ===")
    print(f"{'Modul':<35} {'ms':>10}")
    print("-" * 50)
    heavy = [
        "pandas", "numpy", "openpyxl", "tkinter",
        "PIL", "PIL.Image", "PIL.ImageTk",
    ]
    for mod in heavy:
        name, ms = time_import(mod)
        print(f"{name:<35} {ms:>9.0f}ms")

    print()
    print("=== STEG 2: Page-moduler (kun import) ===")
    print(f"{'Modul':<35} {'ms':>10}")
    print("-" * 50)
    page_modules = [
        "page_oversikt",
        "page_dataset",
        "page_revisjonshandlinger",
        "page_analyse",
        "page_saldobalanse",
        "page_admin",
        "page_reskontro",
        "page_regnskap",
        "src.pages.driftsmidler",
        "page_materiality",
        "page_scoping",
        "page_mva",
        "page_skatt",
        "src.pages.a07.page_a07",
        "src.pages.ar.frontend.page",
        "src.pages.consolidation.frontend.page",
        "page_utvalg",
        "page_utvalg_strata",
        "page_logg",
        "page_fagchat",
        "page_documents",
        "src.pages.statistikk",
    ]
    page_results = []
    for mod in page_modules:
        name, ms = time_import(mod)
        page_results.append((name, ms))
        print(f"{name:<35} {ms:>9.0f}ms")

    print()
    print("=== STEG 3: Topp 10 mest tidkrevende imports ===")
    sorted_pages = sorted([p for p in page_results if p[1] > 0], key=lambda x: -x[1])[:10]
    for name, ms in sorted_pages:
        print(f"  {name:<35} {ms:>9.0f}ms")

    total_pages = sum(ms for _, ms in page_results if ms > 0)
    print(f"\nTotal page-import: {total_pages:.0f}ms")

    # ui_main importerer ALLE page-modulene øverst — så total app-import
    # er sum av alle imports + ui_main selv.
    print()
    print("=== STEG 4: ui_main (importerer alle pages) ===")
    # Fjern alt fra cache så vi måler ærlig
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith(("page_", "src.pages.", "ui_main")):
            del sys.modules[mod_name]
    name, ms = time_import("ui_main")
    print(f"  ui_main (full):                       {ms:>9.0f}ms")


if __name__ == "__main__":
    main()

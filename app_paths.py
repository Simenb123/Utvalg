"""app_paths.py

Felles hjelpefunksjoner for filstier i Utvalg.

Problemet vi løser
------------------
Når applikasjonen pakkes som *onefile* med PyInstaller, blir Python-filer
og medfølgende ressurser pakket inn i .exe og kjørt fra en midlertidig
utpakkingsmappe. Kode som skriver til stier basert på ``__file__`` ender da
opp med å skrive til en temp-mappe (eller feiler), og brukerdata som
innstillinger/mapping-minne forsvinner ved neste kjøring.

Løsning
--------
Vi legger brukerdata i en stabil per-bruker mappe (typisk AppData på
Windows) når vi kjører som "frozen" (PyInstaller). I utviklingsmodus
(ikke frozen) beholder vi eksisterende filplassering (prosjektmappen),
slik at repoet fortsatt er portabelt for utvikling.

Overstyring
-----------
- UTVALG_DATA_DIR: Sett eksplisitt data-mappe (for test/CI eller kundespesifikke
  oppsett). Hvis satt, brukes den også i frozen.
- utvalg_data_dir.txt: Hvis filen finnes ved siden av prosjektet/.exe kan den
  inneholde en sti som brukes som data-mappe (praktisk for fellesmappe på jobb).
- UTVALG_PORTABLE=1: I frozen-modus, lagrer vi brukerdata ved siden av .exe
  (portable modus).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


APP_NAME = "Utvalg"
DATA_DIR_HINT_FILENAME = "utvalg_data_dir.txt"


def is_frozen() -> bool:
    """Returnerer True når programmet kjører som en PyInstaller/"frozen" app."""
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def executable_dir() -> Path:
    """Mappen der den kjørbare filen ligger.

    I frozen-modus er dette mappen til ``sys.executable``.
    I utviklingsmodus bruker vi mappen der denne modulen ligger.
    """
    try:
        if is_frozen() and getattr(sys, "executable", None):
            return Path(sys.executable).resolve().parent
    except Exception:
        pass
    return Path(__file__).resolve().parent


def data_dir_hint_file() -> Path:
    """Sti til valgfri fil som kan overstyre data_dir.

    Filen ligger ved siden av prosjektet i dev, og ved siden av .exe i frozen.
    Innholdet skal være en sti (én linje), f.eks. en nettverksmappe.
    """

    return executable_dir() / DATA_DIR_HINT_FILENAME


def read_data_dir_hint() -> Optional[Path]:
    """Les data-dir hint fra ``utvalg_data_dir.txt`` hvis den finnes."""

    try:
        p = data_dir_hint_file()
        if not p.exists() or not p.is_file():
            return None
        raw = p.read_text(encoding="utf-8", errors="ignore").strip()
        if not raw:
            return None
        # Tillat anførselstegn rundt stien
        raw = raw.strip().strip('"').strip("'").strip()
        if not raw:
            return None
        return Path(raw).expanduser().resolve()
    except Exception:
        return None


def write_data_dir_hint(path: str | Path) -> Path:
    """Skriv/oppdater ``utvalg_data_dir.txt`` ved siden av prosjektet/.exe."""

    p = data_dir_hint_file()
    p.write_text(str(Path(path).expanduser()), encoding="utf-8")
    return p


def _truthy_env(name: str) -> bool:
    val = os.getenv(name, "")
    return val.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _default_data_root() -> Path:
    """Finn OS-typisk base for brukerdata."""
    # Windows
    if sys.platform.startswith("win"):
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            return Path(base)
        # Fallback
        return Path.home() / "AppData" / "Local"

    # macOS
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"

    # Linux/Unix
    xdg = os.getenv("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "share"


def data_dir(app_name: str = APP_NAME) -> Path:
    """Returner mappe for brukerdata.

    Regler:
      1) UTVALG_DATA_DIR (hvis satt) vinner alltid
      2) I frozen: UTVALG_PORTABLE=1 -> bruk exe-mappe
      3) I frozen: bruk OS-standard (AppData/...)\app_name
      4) Ikke frozen: bruk prosjektmappen (samme som executable_dir())
    """

    override = os.getenv("UTVALG_DATA_DIR")
    if override and override.strip():
        return Path(override).expanduser().resolve()

    hint = read_data_dir_hint()
    if hint is not None:
        return hint

    if is_frozen():
        if _truthy_env("UTVALG_PORTABLE"):
            return executable_dir()
        return (_default_data_root() / app_name).resolve()

    # Dev/ikke-frozen: bruk prosjektmappen
    return executable_dir()


def ensure_dir(path: Path) -> None:
    """Sørg for at en mappe eksisterer."""
    path.mkdir(parents=True, exist_ok=True)


def data_file(filename: str, *, app_name: str = APP_NAME, subdir: Optional[str] = None) -> Path:
    """Full sti til en fil i data-mappen (og opprett mappe ved behov)."""
    base = data_dir(app_name=app_name)
    if subdir:
        base = base / subdir
    ensure_dir(base)
    return (base / filename).resolve()


def best_effort_legacy_paths(*candidates: Path) -> list[Path]:
    """Returner en filtrert liste med eksisterende filer fra candidates."""
    out: list[Path] = []
    for p in candidates:
        try:
            p = Path(p)
            if p.exists() and p.is_file():
                out.append(p)
        except Exception:
            continue
    return out

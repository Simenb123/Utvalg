"""ui_selection_summary.py

Felles summering av markerte rader i GUI (Treeview/Listbox).

Mål:
- Når brukeren markerer rader: vis "Markert: N rader | Beløp: X | Sum: Y ..." et sted i GUI.
- Sentralisert: én install-funksjon som binder globalt med bind_all, så alle views får samme oppførsel.

Design:
- UI-uavhengig logikk for summering (duck typing) + best-effort parsing.
- For visning forsøker vi (i rekkefølge):
  1) status_setter callback (hvis gitt)
  2) eksisterende `set_status()` på toplevel
  3) auto-laget status label nederst i toplevel (pack/grid hvis mulig)
  4) fallback: oppdater vindu-tittel (title)

Merk:
- Vi gjør *ingen* antakelser om konkrete widget-klasser (ingen isinstance mot Tk-klasser),
  for å gjøre dette testbart uten Tk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

try:  # pragma: no cover
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore


_REGISTRATION_ATTR = "_ui_selection_summary_config"


# --------------------------------------------------------------------------------------
# Parsing / heuristikk
# --------------------------------------------------------------------------------------

def _parse_number_best_effort(value: Any) -> Optional[float]:
    """Robust parsing av tall (best effort).

    Støtter typiske GUI-strenger:
      - "1 234,50"
      - "-200,00"
      - "(34,50)"
      - "1234.56"
      - "1.234,56"
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return None

    low = s.lower()
    if low in {"nan", "none", "null", "na"}:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    # remove spaces incl NBSP
    s = s.replace("\u00a0", " ").replace(" ", "")

    # remove currency suffixes
    for suf in ("kr", "nok"):
        if s.lower().endswith(suf):
            s = s[: -len(suf)].strip()

    # If both ',' and '.' present -> assume '.' thousands, ',' decimal (NO style)
    if "," in s and "." in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")

    try:
        n = float(s)
    except Exception:
        return None

    if negative:
        n = -abs(n)
    return n


def _format_amount_no(value: float, decimals: int = 2) -> str:
    """Norsk format: tusenskiller mellomrom, desimal komma."""
    try:
        v = float(value)
    except Exception:
        v = 0.0

    sign = "-" if v < 0 else ""
    v = abs(v)

    s = f"{v:.{decimals}f}"
    whole, dec = s.split(".")
    parts = []
    while len(whole) > 3:
        parts.insert(0, whole[-3:])
        whole = whole[:-3]
    parts.insert(0, whole)
    whole_spaced = " ".join(parts)
    return f"{sign}{whole_spaced},{dec}"


def _score_column_for_sum(col_name: str) -> int:
    name = str(col_name).strip().lower()

    if "%" in name or "pct" in name or "andel" in name:
        return 0
    if "antall" in name or "linjer" in name:
        return 10

    if "beløp" in name or "belop" in name or "amount" in name:
        return 100
    if "sum" in name:
        return 80
    if "bevegelse" in name:
        return 90
    if name == "endring" or name.startswith("endring_") or name.endswith("_endring"):
        return 85
    if name == "ib" or name.startswith("ib_") or name.endswith("_ib"):
        return 75
    if name == "ub" or name.startswith("ub_") or name.endswith("_ub"):
        return 75
    if "netto" in name:
        return 70
    if "diff" in name:
        return 60
    if "saldo" in name:
        return 50

    return 0


def guess_sum_columns(columns: list[str], *, max_cols: int = 3) -> list[str]:
    """Velg relevante kolonner å summere basert på navn."""
    scored = [(c, _score_column_for_sum(c)) for c in columns]
    scored = [x for x in scored if x[1] >= 60]
    scored.sort(key=lambda x: (-x[1], str(x[0]).lower()))
    return [str(c) for c, _ in scored[:max_cols]]


# --------------------------------------------------------------------------------------
# Treeview summering (duck typing)
# --------------------------------------------------------------------------------------

def _tree_is_treeview(widget: Any) -> bool:
    return all(hasattr(widget, attr) for attr in ("selection", "set", "get_children"))


def _tree_get_columns(tree: Any) -> list[str]:
    try:
        return [str(c) for c in list(tree["columns"])]  # type: ignore[index]
    except Exception:
        return []


def _tree_get_heading_text(tree: Any, col_id: str) -> str:
    try:
        txt = tree.heading(col_id, option="text")
        return str(txt) if txt else str(col_id)
    except Exception:
        return str(col_id)


def _tree_get_displaycolumns(tree: Any) -> Optional[set[str]]:
    """Returner sett av aktive displaycolumns, eller None om alle vises."""
    try:
        dc = tree["displaycolumns"]  # type: ignore[index]
    except Exception:
        return None
    if dc is None:
        return None
    try:
        items = list(dc)
    except Exception:
        return None
    if not items:
        return None
    if len(items) == 1 and str(items[0]) == "#all":
        return None
    return {str(c) for c in items}


def _tree_column_is_visible(tree: Any, col_id: str) -> bool:
    """Sjekk om en kolonne er faktisk synlig for brukeren.

    Skjulte kolonner identifiseres via:
      - `displaycolumns` ekskluderer den
      - bredde er `0`
      - headingtekst er tom
    """
    display = _tree_get_displaycolumns(tree)
    if display is not None and str(col_id) not in display:
        return False
    try:
        width = int(tree.column(col_id, option="width"))
    except Exception:
        width = -1
    if width == 0:
        return False
    try:
        heading_text = tree.heading(col_id, option="text")
    except Exception:
        heading_text = ""
    if not str(heading_text or "").strip():
        return False
    return True


PriorityColumnsT = Any  # tuple[str, ...] | Callable[[Any], Sequence[str]] | None


@dataclass
class _SelectionSummaryConfig:
    columns: Optional[tuple[str, ...]] = None
    enabled: bool = True
    row_noun: str = "rader"
    max_items: int = 3
    hide_zero: bool = True
    priority_columns: PriorityColumnsT = None


_PLURAL_TO_SINGULAR: dict[str, str] = {
    "rader": "rad",
    "kontoer": "konto",
    "transaksjoner": "transaksjon",
    "bilag": "bilag",
    "poster": "post",
    "linjer": "linje",
}


def _row_noun_singular(plural: str) -> str:
    """Avled entallsform fra en flertallsform (beste innsats for norsk)."""
    p = str(plural or "rader").strip().lower()
    if p in _PLURAL_TO_SINGULAR:
        return _PLURAL_TO_SINGULAR[p]
    if p.endswith("er"):
        return p[:-2]
    return p


def _get_registration(tree: Any) -> Optional[_SelectionSummaryConfig]:
    cfg = getattr(tree, _REGISTRATION_ATTR, None)
    if isinstance(cfg, _SelectionSummaryConfig):
        return cfg
    return None


def register_treeview_selection_summary(
    tree: Any,
    *,
    columns: Optional[Sequence[str]] = None,
    enabled: bool = True,
    row_noun: str = "rader",
    max_items: int = 3,
    hide_zero: bool = True,
    priority_columns: PriorityColumnsT = None,
) -> None:
    """Registrer eksplisitt oppsett for selection-summary på en Treeview.

    - `columns`: kolonne-id-er som *kan* summeres (fallback når ingen priority).
    - `priority_columns`: eksplisitt rekkefølge for hvilke summer som vises,
      enten som en sekvens av kolonne-id-er eller som en callable
      `(tree) -> Sequence[str]` som beregnes på hvert selection-event (nyttig
      når en kontekst — f.eks. aktiv aggregeringsmodus — styrer hva som vises).
    - `row_noun`: flertallsform for radbetegnelsen i footer-teksten (f.eks.
      "rader", "transaksjoner", "kontoer"). Entallsform avledes automatisk.
    - `max_items`: maks antall summer som vises.
    - `hide_zero`: skjul summer som runder til `0,00`.
    - `enabled=False` gjør at treet ignoreres i opt-in-modus.
    """
    if tree is None:
        return
    cfg = _SelectionSummaryConfig(
        columns=tuple(str(c) for c in columns) if columns is not None else None,
        enabled=bool(enabled),
        row_noun=str(row_noun),
        max_items=int(max_items),
        hide_zero=bool(hide_zero),
        priority_columns=priority_columns,
    )
    try:
        setattr(tree, _REGISTRATION_ATTR, cfg)
    except Exception:
        return


def _resolve_priority_columns(
    cfg: Optional[_SelectionSummaryConfig], tree: Any
) -> Optional[tuple[str, ...]]:
    """Hent priority-kolonner; kaller resolver hvis registrert som callable."""
    if cfg is None or cfg.priority_columns is None:
        return None
    pc = cfg.priority_columns
    if callable(pc):
        try:
            resolved = pc(tree)
        except Exception:
            return None
        if not resolved:
            return None
        return tuple(str(c) for c in resolved)
    try:
        return tuple(str(c) for c in pc)
    except Exception:
        return None


def _resolve_sum_columns(tree: Any, cols: list[str]) -> list[str]:
    """Finn kolonner å summere.

    Prioritet:
      1. Dynamisk/eksplisitt `priority_columns` fra registrering
      2. Eksplisitt `columns` fra registrering
      3. Heuristikk
    """
    cfg = _get_registration(tree)
    priority = _resolve_priority_columns(cfg, tree)
    if priority is not None:
        cols_set = set(cols)
        return [c for c in priority if c in cols_set]
    if cfg is not None and cfg.columns is not None:
        cols_set = set(cols)
        return [c for c in cfg.columns if c in cols_set]
    return guess_sum_columns(cols)


def treeview_selection_sums(tree: Any) -> tuple[int, dict[str, float]]:
    """Returnerer (antall markerte, {kolonne-id: sum}).

    Summerer på interne kolonne-id-er. Usynlige kolonner ignoreres selv om
    de er eksplisitt registrert, slik at teksten speiler det brukeren ser.
    """
    if not _tree_is_treeview(tree):
        return 0, {}

    try:
        selected = list(tree.selection())
    except Exception:
        selected = []

    if not selected:
        return 0, {}

    cols = _tree_get_columns(tree)
    sum_cols = _resolve_sum_columns(tree, cols)
    sum_cols = [c for c in sum_cols if _tree_column_is_visible(tree, c)]
    if not sum_cols:
        return len(selected), {}

    sums: dict[str, float] = {c: 0.0 for c in sum_cols}
    parsed_counts: dict[str, int] = {c: 0 for c in sum_cols}

    for iid in selected:
        for c in sum_cols:
            try:
                raw = tree.set(iid, c)
            except Exception:
                raw = None
            n = _parse_number_best_effort(raw)
            if n is None:
                continue
            sums[c] += float(n)
            parsed_counts[c] += 1

    sums = {c: sums[c] for c in sum_cols if parsed_counts.get(c, 0) > 0}
    return len(selected), sums


_ZERO_EPSILON = 0.005  # under denne rundes verdien til 0,00 ved to desimaler


def build_selection_summary_text(
    count: int,
    sums: dict[str, float],
    *,
    row_noun: str = "rader",
    priority: Optional[Sequence[str]] = None,
    max_items: int = 3,
    hide_zero: bool = True,
) -> str:
    """Bygg footer-tekst på formatet "{N} {rownoun} valgt | Label: verdi | ...".

    `sums` er en ordnet dict der nøkkelen kan være intern kolonne-id eller
    synlig headingtekst — denne funksjonen bryr seg ikke om hvilken, men
    forventer at kaller har gjort mapping i riktig retning.

    `priority` gir eksplisitt rekkefølge blant nøklene i `sums`. Uten
    priority sorteres summene heuristisk slik som før.
    """
    noun_singular = _row_noun_singular(row_noun)
    noun = noun_singular if count == 1 else row_noun
    parts = [f"{count} {noun} valgt"]

    if sums:
        if priority:
            priority_list = [p for p in priority if p in sums]
            rest = [c for c in sums.keys() if c not in priority_list]
            ordered = priority_list + sorted(
                rest, key=lambda c: (-_score_column_for_sum(c), str(c).lower())
            )
        else:
            ordered = sorted(
                sums.keys(), key=lambda c: (-_score_column_for_sum(c), str(c).lower())
            )

        if hide_zero:
            ordered = [c for c in ordered if abs(float(sums[c])) >= _ZERO_EPSILON]

        if max_items and max_items > 0:
            ordered = ordered[:max_items]

        for c in ordered:
            parts.append(f"{c}: {_format_amount_no(sums[c])}")

    return " | ".join(parts)


# --------------------------------------------------------------------------------------
# Status output (setter/label/title) + install
# --------------------------------------------------------------------------------------

def _safe_call(fn: Callable[[str], None], txt: str) -> None:
    try:
        fn(txt)
    except Exception:
        return


def _get_toplevel(widget: Any) -> Any:
    try:
        return widget.winfo_toplevel()
    except Exception:
        return None


def _toplevel_title_get(win: Any) -> str:
    try:
        return str(win.title())
    except Exception:
        return ""


def _toplevel_title_set(win: Any, txt: str) -> None:
    try:
        win.title(txt)
    except Exception:
        return


def _ensure_status_label(win: Any) -> Any:
    """Lag (eller hent) en label i bunnen av vinduet. Best effort."""
    existing = getattr(win, "_ui_selection_summary_status_label", None)
    if existing is not None:
        return existing

    if tk is None or ttk is None:
        return None

    # Prøv å se hvilket geometry manager vinduet allerede bruker
    uses_grid = False
    uses_pack = False
    try:
        uses_grid = bool(getattr(win, "grid_slaves")())  # type: ignore[misc]
    except Exception:
        uses_grid = False
    try:
        uses_pack = bool(getattr(win, "pack_slaves")())  # type: ignore[misc]
    except Exception:
        uses_pack = False

    try:
        lbl = ttk.Label(win, relief=tk.SUNKEN, anchor="w")
        if uses_grid and not uses_pack:
            # Grid fallback: legg langt nede
            try:
                lbl.grid(row=999, column=0, sticky="ew", columnspan=999)
                try:
                    win.grid_rowconfigure(999, weight=0)
                except Exception:
                    pass
            except Exception:
                return None
        else:
            # Pack default (eller hvis vi ikke vet)
            try:
                lbl.pack(side=tk.BOTTOM, fill=tk.X)
            except Exception:
                # Kan feile hvis root bruker grid; da har vi grid forsøkt over.
                return None
    except Exception:
        return None

    try:
        setattr(win, "_ui_selection_summary_status_label", lbl)
    except Exception:
        pass
    return lbl


def _default_status_setter_for_window(win: Any) -> Callable[[str], None]:
    """Finn et sted å skrive status for et gitt vindu."""
    if win is None:
        return lambda _txt: None

    # 1) win.set_status
    if callable(getattr(win, "set_status", None)):
        return getattr(win, "set_status")  # type: ignore[return-value]

    # 2) status label eksisterer / kan opprettes
    lbl = _ensure_status_label(win)
    if lbl is not None and callable(getattr(lbl, "config", None)):

        def _setter(txt: str) -> None:
            try:
                lbl.config(text=txt)
            except Exception:
                pass

        return _setter

    # 3) fallback: title
    base_title = getattr(win, "_ui_selection_summary_base_title", None)
    if base_title is None:
        base_title = _toplevel_title_get(win)
        try:
            setattr(win, "_ui_selection_summary_base_title", base_title)
        except Exception:
            pass

    def _setter(txt: str) -> None:
        if not txt:
            _toplevel_title_set(win, str(base_title))
            return
        _toplevel_title_set(win, f"{base_title} | {txt}")

    return _setter


@dataclass
class _Installed:
    installed: bool = False


def _get_install_state(root: Any) -> _Installed:
    st = getattr(root, "_ui_selection_summary_installed", None)
    if isinstance(st, _Installed):
        return st
    st = _Installed()
    try:
        setattr(root, "_ui_selection_summary_installed", st)
    except Exception:
        pass
    return st


def install_global_selection_summary(
    root: Any,
    *,
    status_setter: Optional[Callable[[str], None]] = None,
    require_opt_in: bool = False,
) -> None:
    """Installer global selection-summary (idempotent).

    I opt-in-modus vises summary bare for Treeviews som er registrert via
    `register_treeview_selection_summary(..., enabled=True)`. Uregistrerte
    trees og registrerte med `enabled=False` ignoreres uten å røre footeren.
    """
    if not callable(getattr(root, "bind_all", None)):
        return

    st = _get_install_state(root)
    if st.installed:
        return

    def _emit(widget: Any, txt: str) -> None:
        if status_setter is not None:
            _safe_call(status_setter, txt)
            return
        win = _get_toplevel(widget)
        setter = _default_status_setter_for_window(win)
        _safe_call(setter, txt)

    def on_tree_select(event: Any) -> None:
        tree = getattr(event, "widget", None)
        if tree is None or not _tree_is_treeview(tree):
            return

        cfg = _get_registration(tree)
        if require_opt_in:
            if cfg is None or not cfg.enabled:
                return
        elif cfg is not None and not cfg.enabled:
            return

        n, sums = treeview_selection_sums(tree)
        row_noun = cfg.row_noun if cfg is not None else "rader"
        max_items = cfg.max_items if cfg is not None else 3
        hide_zero = cfg.hide_zero if cfg is not None else True

        if n == 0:
            _emit(tree, "")
            return

        # Map id -> synlig heading; behold rekkefølgen fra treeview_selection_sums
        # (som allerede følger registrert priority).
        heading_for: dict[str, str] = {
            c: _tree_get_heading_text(tree, c) for c in sums.keys()
        }
        pretty = {heading_for[c]: v for c, v in sums.items()}
        priority_headings = [heading_for[c] for c in sums.keys()]

        txt = build_selection_summary_text(
            n,
            pretty,
            row_noun=row_noun,
            priority=priority_headings,
            max_items=max_items,
            hide_zero=hide_zero,
        )
        _emit(tree, txt)

    def on_listbox_select(event: Any) -> None:
        lb = getattr(event, "widget", None)
        if lb is None:
            return
        # Duck typing listbox
        if not all(hasattr(lb, a) for a in ("curselection", "size")):
            return
        cfg = _get_registration(lb)
        if require_opt_in:
            if cfg is None or not cfg.enabled:
                return
        try:
            n = len(list(lb.curselection()))
        except Exception:
            n = 0
        row_noun = cfg.row_noun if cfg is not None else "rader"
        if n == 0:
            _emit(lb, "")
            return
        txt = build_selection_summary_text(n, {}, row_noun=row_noun)
        _emit(lb, txt)

    try:
        root.bind_all("<<TreeviewSelect>>", on_tree_select, add="+")
        root.bind_all("<<ListboxSelect>>", on_listbox_select, add="+")
    except Exception:
        return

    st.installed = True


__all__ = [
    "install_global_selection_summary",
    "register_treeview_selection_summary",
    "guess_sum_columns",
    "treeview_selection_sums",
    "build_selection_summary_text",
]

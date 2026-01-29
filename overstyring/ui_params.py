from __future__ import annotations

from typing import Any

import math
import re

import tkinter as tk
from tkinter import ttk

import formatting

from .registry import ParamSpec


def _is_int_like(x: float) -> bool:
    return math.isfinite(x) and abs(x - round(x)) < 1e-9


def _format_default(kind: str, default: Any) -> str:
    """Format a default value for display in Entry widgets.

    We prefer Norwegian-friendly formatting:
    - thousand separators (NBSP)
    - comma decimals
    - no decimals for whole kroner (e.g. 1500000.0 -> 1 500 000)
    """
    if default is None:
        return ""

    try:
        if kind == "int":
            return formatting.format_number_no(int(float(default)), decimals=0)

        if kind == "float":
            f = float(default)
            decimals = 0 if _is_int_like(f) else 2
            return formatting.format_number_no(f, decimals=decimals)
    except Exception:
        pass

    return str(default)


def safe_float(s: str) -> float:
    """Parse a number that may be written in Norwegian/Excel style."""
    s = s.strip()
    if s == "":
        raise ValueError("Empty")

    # Remove spaces and NBSP used as thousand separators.
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", "", s)

    # If both ',' and '.', assume '.' are thousand separators and ',' decimal.
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")

    return float(s)


def build_param_widgets(
    parent: tk.Widget, params: list[ParamSpec]
) -> dict[str, tuple[tk.Variable, ParamSpec]]:
    """Create parameter widgets for a list of ParamSpec.

    Returns a map: key -> (tk.Variable, ParamSpec)
    """
    out: dict[str, tuple[tk.Variable, ParamSpec]] = {}
    for row, p in enumerate(params):
        ttk.Label(parent, text=p.label).grid(row=row, column=0, sticky="w", padx=4, pady=2)

        kind = p.kind
        if kind == "bool":
            var = tk.BooleanVar(parent, value=bool(p.default))
            cb = ttk.Checkbutton(parent, variable=var)
            cb.grid(row=row, column=1, sticky="w", padx=4, pady=2)
        else:
            var = tk.StringVar(parent)
            if kind in ("int", "float"):
                var.set(_format_default(kind, p.default))
            else:
                var.set("" if p.default is None else str(p.default))

            justify = "right" if kind in ("int", "float") else "left"
            ent = ttk.Entry(parent, textvariable=var, width=40, justify=justify)
            ent.grid(row=row, column=1, sticky="we", padx=4, pady=2)

            if kind in ("int", "float"):

                def _reformat(_event=None, *, v=var, k=kind):
                    raw = str(v.get()).strip()
                    if raw == "":
                        return
                    try:
                        parsed = _parse_int(raw) if k == "int" else _parse_float(raw)
                    except Exception:
                        return
                    v.set(_format_default(k, parsed))

                ent.bind("<FocusOut>", _reformat)
                ent.bind("<Return>", _reformat)

        if p.help:
            ttk.Label(parent, text=p.help, foreground="#666").grid(
                row=row, column=2, sticky="w", padx=8, pady=2
            )

        out[p.key] = (var, p)
    return out


def _parse_float(s: str) -> float:
    return safe_float(s)


def _parse_int(s: str) -> int:
    f = safe_float(s)
    if _is_int_like(f):
        return int(round(f))
    return int(f)


def read_param_values(var_map: dict[str, tuple[tk.Variable, ParamSpec]]) -> dict[str, Any]:
    """Read and parse parameter values from a var map.

    Empty fields are omitted (caller should fall back to ParamSpec.default).
    """
    out: dict[str, Any] = {}
    for key, (var, p) in var_map.items():
        kind = p.kind
        if kind == "bool":
            out[key] = bool(var.get())
            continue

        raw = str(var.get()).strip()
        if raw == "":
            # Omit -> allows check implementation to apply ParamSpec.default
            continue

        if kind == "float":
            out[key] = _parse_float(raw)
        elif kind == "int":
            out[key] = _parse_int(raw)
        else:
            out[key] = raw

    return out

from __future__ import annotations

from typing import Any, Callable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore


from page_admin_helpers import (
    _clean_text,
    _normalize_threshold_document,
)


class _ThresholdEditor(ttk.Frame):  # type: ignore[misc]
    _FIELDS: tuple[tuple[str, str, str], ...] = (
        ("tolerance_rel", "Relativ toleranse", "Hvor stor prosentvis differanse som aksepteres i A07-avstemming."),
        ("tolerance_abs", "Absolutt toleranse", "Fast beløpsgrense før differanser må vurderes manuelt."),
        ("historical_account_boost", "Boost historisk konto", "Ekstra vekt når samme konto traff i historikk."),
        ("historical_combo_boost", "Boost historisk kombinasjon", "Ekstra vekt når historisk kombinasjon av kontoer/code traff."),
        ("max_combo", "Maks kombinasjon", "Hvor mange kontoer som prøves i kombinasjon ved matching."),
        ("candidates_per_code", "Kandidater per kode", "Hvor mange kandidater hver A07-kode får i motoren."),
        ("top_suggestions_per_code", "Toppforslag per kode", "Hvor mange forslag som beholdes per kode i UI-et."),
    )

    def __init__(
        self,
        master: Any,
        *,
        title: str,
        loader: Callable[[], tuple[Any, str]],
        saver: Callable[[Any], str],
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._title = title
        self._loader = loader
        self._saver = saver
        self._on_saved = on_saved
        self._path_var = tk.StringVar(value="") if tk is not None else None
        self._vars: dict[str, Any] = {
            key: (tk.StringVar(value="") if tk is not None else None)
            for key, _label, _help in self._FIELDS
        }

        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._path_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(header, text="Last på nytt", command=self.reload).grid(row=0, column=1, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Lagre", command=self.save).grid(row=0, column=2, rowspan=2, padx=(8, 0))

        ttk.Label(
            self,
            text="Juster kjerneytelse og aggressivitet i matcher. Endringene slår gjennom etter oppfrisk.",
            style="Muted.TLabel",
            padding=(8, 0, 8, 4),
        ).grid(row=1, column=0, sticky="ew")

        body = ttk.Frame(self, padding=(8, 0, 8, 8))
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        for row_no, (key, label, help_text) in enumerate(self._FIELDS):
            ttk.Label(body, text=label).grid(row=row_no, column=0, sticky="nw", pady=(0, 10))
            field_host = ttk.Frame(body)
            field_host.grid(row=row_no, column=1, sticky="ew", pady=(0, 10))
            field_host.columnconfigure(0, weight=1)
            ttk.Entry(field_host, textvariable=self._vars[key]).grid(row=0, column=0, sticky="ew")
            ttk.Label(field_host, text=help_text, style="Muted.TLabel", wraplength=520, justify="left").grid(
                row=1, column=0, sticky="w", pady=(4, 0)
            )

        self.reload()

    def reload(self) -> None:
        document, path_text = self._loader()
        normalized = _normalize_threshold_document(document)
        for key, _label, _help in self._FIELDS:
            variable = self._vars.get(key)
            if variable is not None:
                variable.set(str(normalized.get(key, "")))
        if self._path_var is not None:
            self._path_var.set(path_text)

    def save(self) -> None:
        payload = {
            key: (_clean_text(variable.get()) if variable is not None else "")
            for key, variable in self._vars.items()
        }
        try:
            saved_path = self._saver(_normalize_threshold_document(payload))
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lagre: {exc}")
            return
        if self._path_var is not None:
            self._path_var.set(saved_path)
        self.reload()
        if self._on_saved is not None:
            self._on_saved()

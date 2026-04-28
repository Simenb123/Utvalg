from __future__ import annotations

import json
from typing import Any, Callable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore


class _JsonEditor(ttk.Frame):  # type: ignore[misc]
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

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(8, 8, 8, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._path_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(header, text="Last på nytt", command=self.reload).grid(row=0, column=1, rowspan=2, padx=(8, 0))
        ttk.Button(header, text="Lagre", command=self.save).grid(row=0, column=2, rowspan=2, padx=(8, 0))

        ttk.Label(
            self,
            text="Endringene her påvirker regler og forslag, ikke lagrede klientprofiler.",
            style="Muted.TLabel",
            padding=(8, 0, 8, 4),
        ).grid(row=1, column=0, sticky="ew")

        body = ttk.Frame(self, padding=(8, 0, 8, 8))
        body.grid(row=2, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self._text = tk.Text(body, wrap="none", undo=True)
        self._text.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(body, orient="vertical", command=self._text.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(body, orient="horizontal", command=self._text.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self._text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.reload()

    def reload(self) -> None:
        document, path_text = self._loader()
        try:
            pretty = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception:
            pretty = "{}"
        self._text.delete("1.0", "end")
        self._text.insert("1.0", pretty)
        if self._path_var is not None:
            self._path_var.set(path_text)

    def save(self) -> None:
        raw = self._text.get("1.0", "end").strip() or "{}"
        try:
            document = json.loads(raw)
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lese JSON: {exc}")
            return
        try:
            saved_path = self._saver(document)
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lagre: {exc}")
            return
        if self._path_var is not None:
            self._path_var.set(saved_path)
        if self._on_saved is not None:
            self._on_saved()

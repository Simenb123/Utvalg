from __future__ import annotations

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore


class ConsolidationPage(ttk.Frame):  # type: ignore[misc]
    """Tynn sideklasse for konsolidering.

    Denne siden markerer scope for konsolidering MVP i Utvalg:
    TB-import per selskap, felles mapping, manuell elimineringsjournal,
    reproduserbar run og eksport av arbeidsbok.
    """

    def __init__(self, master=None):
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception:
            self._tk_ok = False
            self._title_var = None
            self._status_var = None
            return

        self._title_var = tk.StringVar(value="Konsolidering")
        self._status_var = tk.StringVar(
            value=(
                "MVP-scope: importer TB per selskap, map til konsernlinjer, "
                "registrer manuelle elimineringer, kjor run og eksporter arbeidsbok. "
                "Kun saldobalanse skal vaere nok i denne flyten."
            )
        )
        self._build_ui()

    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Label(header, textvariable=self._title_var, style="Heading.TLabel").pack(anchor="w")
        ttk.Label(header, textvariable=self._status_var, style="Muted.TLabel", wraplength=900).pack(
            anchor="w", pady=(4, 0)
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        companies = ttk.LabelFrame(body, text="Selskaper og import")
        companies.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(
            companies,
            text=(
                "Planlagt arbeidsflate:\n"
                "- selskaper og importstatus\n"
                "- TB-import fra Excel/CSV og SAF-T\n"
                "- mapping og review\n"
                "- kjoring og eksport"
            ),
            justify="left",
        ).pack(anchor="w", padx=12, pady=12)

        side = ttk.LabelFrame(body, text="MVP og avgrensning")
        side.grid(row=0, column=1, sticky="nsew")
        ttk.Label(
            side,
            text=(
                "Er med i MVP:\n"
                "- klient/aar-prosjekt\n"
                "- TB-only arbeidsflyt\n"
                "- felles mapping\n"
                "- manuell elimineringsjournal\n"
                "- reproduserbar run\n"
                "- Excel-eksport\n\n"
                "Ikke med i MVP:\n"
                "- minoriteter\n"
                "- PPA/goodwill\n"
                "- egenkapitalmetoden\n"
                "- avansert valuta\n"
                "- smart auto-eliminering"
            ),
            justify="left",
            wraplength=340,
        ).pack(anchor="w", padx=12, pady=12)

    def refresh_from_session(self, sess: object) -> None:
        if not self._tk_ok or self._status_var is None:
            return

        client = str(getattr(sess, "client", "") or "").strip()
        year = str(getattr(sess, "year", "") or "").strip()
        if client and year:
            self._status_var.set(
                f"Kontekst {client} / {year}. Konsolidering MVP er avgrenset til TB-import, mapping, eliminering, run og eksport."
            )

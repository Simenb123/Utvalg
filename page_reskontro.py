from __future__ import annotations

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore


class ReskontroPage(ttk.Frame):  # type: ignore[misc]
    """Samlet arbeidsflate for kunde- og leverandorreskontro.

    V1 i Utvalg er en motpartsoversikt fra eksisterende hovedbokstransaksjoner,
    ikke full aapen-post-reskontro.
    """

    def __init__(self, master=None):
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception:
            self._tk_ok = False
            self._mode_var = None
            self._status_var = None
            return

        self._mode_var = tk.StringVar(value="Kunder")
        self._status_var = tk.StringVar(
            value=(
                "V1-scope: samlet motpartsoversikt med modus for kunder og leverandorer, "
                "drill til transaksjoner og enkle lokale risikosignaler. "
                "Denne modulen krever transaksjonsgrunnlag, ikke bare saldobalanse."
            )
        )
        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Label(toolbar, text="Reskontro", style="Heading.TLabel").pack(side="left")
        ttk.Label(toolbar, text="Vis:", style="Muted.TLabel").pack(side="left", padx=(16, 4))
        mode = ttk.Combobox(
            toolbar,
            textvariable=self._mode_var,
            state="readonly",
            values=("Kunder", "Leverandorer"),
            width=16,
        )
        mode.pack(side="left")

        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel", wraplength=980).pack(
            anchor="w", padx=10, pady=(0, 8)
        )

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        overview = ttk.LabelFrame(main, text="Motparter")
        overview.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(
            overview,
            text=(
                "Planlagt v1:\n"
                "- motpart-id og motpart-navn\n"
                "- saldo og antall transaksjoner\n"
                "- siste og forste dato\n"
                "- konto-/periodefilter\n"
                "- drill til transaksjoner"
            ),
            justify="left",
        ).pack(anchor="w", padx=12, pady=12)

        detail = ttk.LabelFrame(main, text="Status og avgrensning")
        detail.grid(row=0, column=1, sticky="nsew")
        ttk.Label(
            detail,
            text=(
                "Lokale risikosignaler i v1:\n"
                "- mangler id\n"
                "- mangler navn\n"
                "- saldo uten nylig aktivitet\n"
                "- mange transaksjoner\n"
                "- feil fortegn i valgt modus\n\n"
                "Ikke med i v1:\n"
                "- full aging\n"
                "- orgnr som launchkrav\n"
                "- BRREG/registerintegrasjoner"
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
                f"Kontekst {client} / {year}. Reskontro v1 er avgrenset til motpartsoversikt, drill og lokale risikosignaler."
            )

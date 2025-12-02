# -*- coding: utf-8 -*-
"""
page_analyse.py

Denne modulen definerer en AnalysePage som viser en oppsummering av
regnskapsdata etter at datasetet er bygd. Klassen er designet for å
fungere sammen med Tkinter‐basert GUI (bruker ttk.Widget). Den kan
fremvise en pivotert oversikt per konto, vise detaljlinjer for valgte
kontoer og sende utvalgte kontoer videre til utvalgsmodulen.

Sammenlignet med den minimale implementasjonen tidligere i prosjektet,
inneholder denne versjonen en faktisk visning av data. Pivotlogikken
ligger i analyse_model.py for å kunne testes separat.

Merk: Når Tkinter ikke er tilgjengelig (f.eks. i headless testmiljø),
faller klassen tilbake til en dummy-implementasjon av ttk.Frame. Da
bygges ingen faktiske widgets, men metoder som refresh_from_session
og set_utvalg_callback fungerer fortsatt slik at tester kan kjøre
uavhengig av GUI.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Optional

try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None  # type: ignore

try:
    import tkinter as tk  # noqa: F401
    from tkinter import ttk  # type: ignore
except Exception:
    # Fallback dummy Frame if tkinter is unavailable
    class _DummyFrame:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._dummy_args = args
            self._dummy_kwargs = kwargs

    class _DummyTtk:
        Frame = _DummyFrame  # type: ignore

    ttk = _DummyTtk()  # type: ignore

from analyse_model import build_pivot_by_account, filter_by_accounts


class AnalysePage(ttk.Frame):
    """
    AnalysePage viser en pivotert oversikt per konto og en liste over
    tilhørende transaksjoner. Brukeren kan markere kontoer og sende dem
    videre til utvalg.
    """

    def __init__(self, parent: Any) -> None:
        super().__init__(parent)
        self.parent: Any = parent
        self._session: Optional[Any] = None
        self.dataset: Optional[pd.DataFrame] = None
        self._utvalg_callback: Optional[Callable[[Iterable[Any]], None]] = None
        # GUI widgets set in _build_ui() (may be None in headless env)
        self.summary_tree: Any = None
        self.detail_tree: Any = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Offentlig API

    def set_utvalg_callback(self, callback: Callable[[Iterable[Any]], None]) -> None:
        """Registrer en callback for når kontoer skal sendes videre til utvalg."""
        self._utvalg_callback = callback

    def refresh_from_session(self, session: Any) -> None:
        """
        Oppdater AnalysePage basert på en ny session.

        Hvis session har en attributt ``dataset`` settes denne på siden,
        og pivot og detaljer oppdateres.
        """
        self._session = session
        # Forsøk å hente et dataset fra sessionen
        df = None
        if hasattr(session, "dataset"):
            try:
                df = session.dataset  # type: ignore[assignment]
            except Exception:
                df = None
        # Støtt fallback attributtnavn fra andre implementasjoner
        if df is None and hasattr(session, "df"):
            try:
                df = session.df  # type: ignore[assignment]
            except Exception:
                df = None
        # Oppdater dataset og UI
        if isinstance(df, pd.DataFrame):
            self.dataset = df
        else:
            self.dataset = None
        self._update_summary()

    # ------------------------------------------------------------------
    # Intern API (GUI)

    def _build_ui(self) -> None:
        """
        Konstruer GUI-komponentene for analysefanen. Hvis Tkinter er
        utilgjengelig, settes widgets til None slik at de ikke brukes.
        """
        # Dersom ttk er dummy (f.eks. i testmiljø uten GUI), hopp over
        try:
            # Oppsett av grid. To kolonner: pivotoversikt og detaljvisning
            self.columnconfigure(0, weight=1)
            self.columnconfigure(1, weight=2)
            self.rowconfigure(0, weight=1)

            # Venstre side: pivotert oversikt per konto
            left = ttk.Frame(self)
            left.grid(row=0, column=0, sticky="nsew")
            # Treeview for pivot
            self.summary_tree = ttk.Treeview(left, show="headings")
            yscroll = ttk.Scrollbar(left, orient="vertical", command=self.summary_tree.yview)
            self.summary_tree.configure(yscrollcommand=yscroll.set)
            self.summary_tree.pack(side="left", fill="both", expand=True)
            yscroll.pack(side="right", fill="y")
            # Bind velg
            self.summary_tree.bind("<<TreeviewSelect>>", self._on_summary_select)

            # Høyre side: detaljvisning for valgte kontoer
            right = ttk.Frame(self)
            right.grid(row=0, column=1, sticky="nsew")
            self.detail_tree = ttk.Treeview(right, show="headings")
            yscroll2 = ttk.Scrollbar(right, orient="vertical", command=self.detail_tree.yview)
            self.detail_tree.configure(yscrollcommand=yscroll2.set)
            self.detail_tree.pack(side="left", fill="both", expand=True)
            yscroll2.pack(side="right", fill="y")

            # Bunnlinje med knapp for å sende til utvalg
            bottom = ttk.Frame(self)
            bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 4))
            btn = ttk.Button(bottom, text="Til utvalg", command=self._on_send_selection)
            btn.pack(side="left", padx=(4, 4))
        except Exception:
            # Ikke tilgjengelig GUI – bruk None som plassholdere
            self.summary_tree = None
            self.detail_tree = None

    def _update_summary(self) -> None:
        """
        Beregn pivotoversikt og oppdater GUI. Hvis det ikke finnes GUI,
        returneres bare.
        """
        if self.summary_tree is None or self.dataset is None:
            return
        # Bygg pivot
        try:
            pivot = build_pivot_by_account(self.dataset)
        except Exception:
            pivot = None
        # Rens tidligere innhold
        for item in self.summary_tree.get_children() if self.summary_tree else []:
            self.summary_tree.delete(item)
        if pivot is None or pivot.empty:
            # Fjern tidligere kolonner
            self.summary_tree["columns"] = []
            return
        # Sett opp kolonner
        columns = list(pivot.columns)
        self.summary_tree["columns"] = columns
        for col in columns:
            self.summary_tree.heading(col, text=str(col))
            # Sett en generisk bredde (kan justeres basert på innhold)
            self.summary_tree.column(col, width=120, anchor="w")
        # Legg til rader
        for _, row in pivot.iterrows():
            self.summary_tree.insert("", "end", values=list(row))
        # Etter oppdatering bør detaljvisningen tømmes
        self._update_details([])

    def _on_summary_select(self, _event: Any) -> None:
        """
        Når brukeren markerer konto(er) i pivot-tabellen, filtrer dataset
        og vis tilhørende transaksjoner i detaljvisningen.
        """
        if self.summary_tree is None or self.detail_tree is None or self.dataset is None:
            return
        sel = self.summary_tree.selection()
        accounts: List[Any] = []
        for iid in sel:
            # Første kolonne er alltid "Konto"
            values = self.summary_tree.item(iid).get("values", [])
            if values:
                accounts.append(values[0])
        self._update_details(accounts)

    def _update_details(self, accounts: Iterable[Any]) -> None:
        """
        Oppdater detaljvisningen med transaksjoner for de gitte kontoene.
        Hvis listen er tom, tømmes detaljvisningen.
        """
        if self.detail_tree is None:
            return
        # Fjern eksisterende rader
        for iid in self.detail_tree.get_children():
            self.detail_tree.delete(iid)
        # Hvis dataset ikke satt eller ingen kontoer valgt, tøm kolonner
        if self.dataset is None or not accounts:
            self.detail_tree["columns"] = []
            return
        # Filtrer dataset på konto
        try:
            df = filter_by_accounts(self.dataset, accounts)
        except Exception:
            df = None
        if df is None or df.empty:
            self.detail_tree["columns"] = []
            return
        # Sett opp kolonner
        cols = list(df.columns)
        self.detail_tree["columns"] = cols
        for col in cols:
            self.detail_tree.heading(col, text=str(col))
            self.detail_tree.column(col, width=120, anchor="w")
        # Legg til rader
        for _, row in df.iterrows():
            # Konverter alle verdier til str for sikkerhets skyld
            vals = [str(v) if v is not None else "" for v in row.tolist()]
            self.detail_tree.insert("", "end", values=vals)

    def _on_send_selection(self) -> None:
        """
        Hent markerte kontoer i pivotvisningen og send dem videre via
        registrert callback.
        """
        if self.summary_tree is None:
            return
        sel = self.summary_tree.selection()
        accounts: List[Any] = []
        for iid in sel:
            values = self.summary_tree.item(iid).get("values", [])
            if values:
                accounts.append(values[0])
        # Send videre hvis callback finnes
        self._send_to_selection(accounts)

    # ------------------------------------------------------------------
    # Arvet fra minimal implementasjon

    def _send_to_selection(self, accounts: Iterable[Any]) -> None:
        """
        Invokér registrert utvalg-callback med en liste over kontoer.
        Svak exceptions for å unngå at GUI krasjer på callback-feil.
        """
        if self._utvalg_callback is not None:
            try:
                self._utvalg_callback(accounts)
            except Exception:
                pass
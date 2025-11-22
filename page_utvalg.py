""" page_utvalg.py

Denne koden lager “Utvalg”-fanen i et Tkinter-GUI der du kan se,
filtrere og sende transaksjoner videre til stratifisering.

Utvalg – fane for transaksjonsutvalg og stratifisering."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd
from typing import Optional, Callable, List

# Forsøk å importere stratifiseringsdialogen fra pakken.
# Ved feil vises en klar feilmelding i stedet for fallback-stub.
try:
    from views_selection_studio import SelectionStudio
    _STRAT_IMPORT_ERROR_MSG = ""  # ikke i bruk når importen lykkes
except Exception as e:  # pragma: no cover - kun fallback i runtime
    from tkinter import messagebox as _messagebox

    _STRAT_IMPORT_ERROR_MSG = f"Feil ved lasting av stratifieringsmodul: {e}"

    def _show_strat_error() -> None:
        _messagebox.showerror(
            "Stratifisering",
            _STRAT_IMPORT_ERROR_MSG or "Ukjent feil ved lasting av stratifiseringsmodul."
        )

    class SelectionStudio:  # type: ignore[misc]
        def __init__(
            self,
            master,
            df: pd.DataFrame,
            on_commit: Callable | None = None,
            df_all: pd.DataFrame | None = None,
        ) -> None:
            _show_strat_error()


# Import av resten av applikasjonens komponenter
from views_virtual_transactions import VirtualTransactionsPanel
import preferences
import session
from bus import emit, set_utvalg_page


def filter_utvalg_dataframe(
    df_all: pd.DataFrame,
    query: str,
    dir_value: str,
    selected_series: List[int],
) -> pd.DataFrame:
    """
    Ren filtreringsfunksjon for Utvalg-fanen.

    Brukes både av UtvalgPage.apply_filters (GUI) og av pytest-testene
    i tests/test_utvalg_filters.py.

    Parametre
    ---------
    df_all : DataFrame
        Grunnlaget som skal filtreres.
    query : str
        Tekstsøk som matches mot Tekst og Kontonavn (case-insensitiv).
    dir_value : {"Alle", "Debet", "Kredit"}
        Retningsfilter (fortegn på Beløp).
    selected_series : list[int]
        Liste med kontoserier (første siffer i Konto) som skal beholdes.

    Returnerer
    ----------
    DataFrame
        Filtrert DataFrame.
    """
    if df_all is None or df_all.empty:
        return df_all.iloc[0:0].copy() if df_all is not None else pd.DataFrame()

    df = df_all.copy()

    # 1) Tekst/kontonavn
    q = (query or "").strip().lower()
    if q:
        mask = pd.Series(False, index=df.index)

        if "Tekst" in df.columns:
            mask = mask | df["Tekst"].astype(str).str.lower().str.contains(q)

        if "Kontonavn" in df.columns:
            mask = mask | df["Kontonavn"].astype(str).str.lower().str.contains(q)

        df = df[mask]

    # 2) Retning (Debet/Kredit/Alle)
    bel = pd.to_numeric(
        df.get("Beløp", pd.Series(dtype="float64")),
        errors="coerce",
    ).fillna(0.0)

    if dir_value == "Debet":
        df = df[bel > 0]
    elif dir_value == "Kredit":
        df = df[bel < 0]

    # 3) Kontoserier
    if selected_series:
        if "Konto" not in df.columns:
            return df.iloc[0:0].copy()
        konto_first = df["Konto"].astype(str).str[0]
        mask_series = konto_first.str.isdigit() & konto_first.astype(int).isin(selected_series)
        df = df[mask_series]

    return df


class UtvalgPage(ttk.Frame):
    """
    Fane for å vise utvalgte transaksjoner og starte stratifisering.
    Den viser alle transaksjoner for de kontoene du markerer i Analyse-fanen,
    og lar deg filtrere og sende videre til stratifisering.
    """

    def __init__(self, parent, *_, **__) -> None:
        super().__init__(parent)
        self.pack(fill="both", expand=True)

        # DataFrame for alle transaksjoner (basert på valgte kontoer)
        self._df_all: Optional[pd.DataFrame] = None
        # DataFrame med filtrerte transaksjoner som vises i tabellen
        self._df_show: pd.DataFrame = pd.DataFrame()

        # Preferanser for hvilke kolonner som vises og er pinned
        self._visible_columns: list[str] = []
        self._pinned_columns: list[str] = []
        self._display_limit = preferences.get("utvalg.display_limit", 200)

        # Registrer deg hos bus slik at Analyse-siden kan trigge apply_filters
        set_utvalg_page(self)
        emit("UTVALG_PAGE_READY", self)

        # UI-variabler for søk og filtre
        self.var_search = tk.StringVar()
        self.var_dir = tk.StringVar(value="Alle")
        self.vars_series = [tk.BooleanVar(value=False) for _ in range(9)]

        # Bygg brukergrensesnittet
        self._build_ui()

        # Oppdater sammendrag
        self._update_filter_summary()

    def _build_ui(self) -> None:
        """Bygg topp-panel med søk, retning og kontoserier samt transaksjonstabell."""
        top = ttk.Frame(self)
        top.pack(fill="x", pady=4, padx=4)

        ttk.Label(top, text="Søk:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.var_search, width=20).grid(row=0, column=1, sticky="w")
        ttk.Label(top, text="Retning:").grid(row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Combobox(
            top,
            values=("Alle", "Debet", "Kredit"),
            textvariable=self.var_dir,
            state="readonly",
            width=10,
        ).grid(row=0, column=3, sticky="w")

        ttk.Label(top, text="Kontoserier:").grid(row=0, column=4, sticky="w", padx=(10, 0))
        for i in range(9):
            ttk.Checkbutton(top, text=str(i + 1), variable=self.vars_series[i]).grid(
                row=0, column=5 + i, sticky="w"
            )

        ttk.Button(top, text="Bruk filtre", command=self.apply_filters).grid(
            row=0, column=14, sticky="w", padx=(10, 0)
        )
        ttk.Button(top, text="Til underpop/Stratifisering", command=self._open_studio).grid(
            row=0, column=15, sticky="w"
        )

        # Oppsummering av antall rader og sum
        self.lbl_summary = ttk.Label(self, text="Grunnlag: rader=0 | sum=0,00")
        self.lbl_summary.pack(anchor="w", padx=4)

        # Transaksjonsliste (VirtualTransactionsPanel)
        self.trans = VirtualTransactionsPanel(self, on_row_dblclick=self._on_row_dblclick)
        self.trans.pack(fill="both", expand=True)

    def on_dataset_loaded(self, df: pd.DataFrame) -> None:
        """Kalles når Dataset-panelet har lastet inn et datasett."""
        self._df_all = df.copy()
        self.apply_filters()

    def _get_dataset_from_session(self) -> Optional[pd.DataFrame]:
        """Hent dataset fra session dersom _df_all er tomt."""
        try:
            df = getattr(session, "dataset", None)
        except Exception:
            df = None
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
        return None

    def _get_selected_accounts(self) -> list[str]:
        """Hent kontoliste fra session.SELECTION.accounts (som strenger)."""
        try:
            sel = getattr(session, "SELECTION", {}) or {}
            accounts = sel.get("accounts") or []
        except Exception:
            accounts = []
        # Normaliser til str
        return [str(a) for a in accounts]

    def apply_filters(self) -> None:
        """
        Filtrer transaksjoner basert på kontoutvalg, søk, retning og kontoserier.
        Denne metoden oppdaterer _df_show og tabellen.
        """
        # Sørg for at vi har et grunnlag å filtrere på
        if self._df_all is None:
            df_session = self._get_dataset_from_session()
            if df_session is None:
                # Ingen datasett tilgjengelig
                self._df_show = pd.DataFrame()
                self.trans.set_dataframe(pd.DataFrame(), columns=[], pinned=[], limit=0)
                self._update_filter_summary()
                return
            self._df_all = df_session.copy()

        df = self._df_all.copy()

        # 1) Filter på kontoutvalg fra Analyse (session.SELECTION["accounts"])
        accounts = self._get_selected_accounts()
        if accounts:
            if "Konto" in df.columns:
                df = df[df["Konto"].astype(str).isin(accounts)]
            else:
                df = df.iloc[0:0]

        # 2–4) Bruk den rene hjelpefunksjonen for resten av filtrene
        selected_series = [i + 1 for i, var in enumerate(self.vars_series) if var.get()]

        df = filter_utvalg_dataframe(
            df_all=df,
            query=self.var_search.get(),
            dir_value=self.var_dir.get(),
            selected_series=selected_series,
        )

        self._df_show = df
        self._prepare_columns()
        self.trans.set_dataframe(
            df,
            columns=self._visible_columns,
            pinned=self._pinned_columns,
            limit=self._display_limit,
        )
        self._update_filter_summary()

    def _prepare_columns(self) -> None:
        """
        Bestem rekkefølge og visning av kolonner basert på default rekkefølge og preferanser.
        """
        base_columns = [
            "Bilag",
            "Konto",
            "Kontonavn",
            "Dato",
            "Beløp",
            "Tekst",
            "Kundenr",
            "Kundenavn",
            "Leverandørnr",
            "Leverandørnavn",
            "Valuta",
            "Valutabeløp",
            "MVA-kode",
            "MVA-beløp",
            "MVA-prosent",
        ]
        cols = [c for c in base_columns if c in self._df_show.columns]

        pinned = preferences.get("utvalg.pinned", [])
        visible = preferences.get("utvalg.visible", cols)

        pinned_ordered = [c for c in pinned if c in cols]
        self._pinned_columns = pinned_ordered
        self._visible_columns = pinned_ordered + [c for c in visible if c not in pinned_ordered]

    def _update_filter_summary(self) -> None:
        """Vis antall rader og sum av beløp for visningen."""
        if self._df_show.empty:
            self.lbl_summary.config(text="Grunnlag: rader=0 | sum=0,00")
            return
        total = len(self._df_show)
        sum_bel = pd.to_numeric(
            self._df_show.get("Beløp", pd.Series(dtype="float64")),
            errors="coerce",
        ).fillna(0.0).sum()
        text = f"Grunnlag: rader={total:,} | sum={sum_bel:,.2f}".replace(",", " ").replace(".", ",")
        self.lbl_summary.config(text=text)

    def _open_studio(self) -> None:
        """
        Åpne stratifiseringsvinduet (SelectionStudio) med gjeldende utvalg.
        """
        if self._df_show.empty:
            messagebox.showinfo("Stratifisering", "Ingen rader i utvalget.")
            return

        def on_commit(df_sample: pd.DataFrame) -> None:
            """
            Oppdater tabellen med sample etter stratifisering.
            """
            if df_sample is not None and not df_sample.empty:
                # Fjern 'Stratum'-kolonne hvis den finnes
                df_sample = df_sample.drop(columns=[c for c in df_sample.columns if c == "Stratum"], errors="ignore")
                self._df_show = df_sample
                self._prepare_columns()
                self.trans.set_dataframe(
                    df_sample,
                    columns=self._visible_columns,
                    pinned=self._pinned_columns,
                    limit=self._display_limit,
                )
                self._update_filter_summary()

        # Åpne SelectionStudio
        SelectionStudio(self, self._df_show, on_commit, self._df_all)

    def _on_row_dblclick(self, row_data: dict) -> None:
        """
        Ved dobbeltklikk: scroll til alle linjer i utvalget med samme bilag.
        """
        try:
            bilag = row_data.get("Bilag")
            if bilag is None:
                return
            mask = self._df_show["Bilag"] == bilag
            self.trans.set_dataframe(
                self._df_show.loc[mask],
                columns=self._visible_columns,
                pinned=self._pinned_columns,
                limit=0,  # vis alle rader for bilaget
            )
        except Exception:
            pass

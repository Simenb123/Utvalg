"""
AnalysePage
-----------

This module provides a more functional implementation of the
``AnalysePage`` class for the Utvalg application.  It extends
``tkinter.ttk.Frame`` so that it can be inserted into a tabbed
interface and presents two tree views: one summarising the dataset by
account and another showing the transactions for any selected
accounts.  A "Til utvalg" button lets users forward the selected
accounts to downstream components via a callback.

Unlike the stripped‑down stub previously provided, this version
includes simple pivoting logic: when a new session is loaded via
``refresh_from_session``, the page computes a pivot table over the
``Konto`` (account) and ``Kontonavn`` columns using the helper
functions in ``analyse_model``.  It then populates the summary tree.
Selecting rows in the summary tree filters the original dataset and
displays the matching transactions in the detail tree.  The GUI
behaviour degrades gracefully in environments without Tkinter or
pandas by falling back to dummy widgets.

Note that this implementation does not know anything about the event
bus used elsewhere in the application.  Consumers of this class
should call ``refresh_from_session(session)`` manually when the
dataset is ready and should register a callback via
``set_utvalg_callback`` to receive selected accounts.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Iterable, List

# Optional pandas import: all numeric and date handling happens in
# analyse_model, so we only use pandas here to type check the dataset
# attribute.  If pandas is unavailable, the code still runs.
try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - fallback for headless/test envs
    pd = None  # type: ignore

# Try to import Tkinter/ttk.  In headless environments (e.g. CI on
# Linux without a display) this may fail.  Provide dummy classes so
# that tests which import this module do not crash.  The dummy
# widgets expose the few methods used in this module but do nothing.
try:
    import tkinter as tk  # noqa: F401
    from tkinter import ttk  # type: ignore
except Exception:  # pragma: no cover
    class _DummyWidget:
        """Fallback widget that does nothing but satisfies the API."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        # Layout methods
        def grid(self, *args: Any, **kwargs: Any) -> None:
            return None

        def pack(self, *args: Any, **kwargs: Any) -> None:
            return None

        # Tree methods
        def delete(self, *args: Any, **kwargs: Any) -> None:
            return None

        def insert(self, *args: Any, **kwargs: Any) -> None:
            return None

        def heading(self, *args: Any, **kwargs: Any) -> None:
            return None

        def column(self, *args: Any, **kwargs: Any) -> None:
            return None

        def bind(self, *args: Any, **kwargs: Any) -> None:
            return None

        def selection(self) -> Iterable[str]:  # type: ignore[override]
            return []

        def get_children(self) -> Iterable[str]:  # type: ignore[override]
            return []

        def item(self, _item: str, option: str = "values"):  # type: ignore[override]
            return {"values": []}

    # A dummy ttk namespace that provides the widget classes used below
    class _DummyTtk:
        Frame = _DummyWidget  # type: ignore
        Treeview = _DummyWidget  # type: ignore
        Button = _DummyWidget  # type: ignore
        Label = _DummyWidget  # type: ignore

    ttk = _DummyTtk()  # type: ignore

# Import analyse_model lazily; if unavailable (e.g. in tests where it
# isn't part of the dependency graph), the page will simply not
# compute pivots.  The names are pulled into the local namespace for
# readability.
try:
    from analyse_model import build_pivot_by_account, filter_by_accounts  # type: ignore
except Exception:  # pragma: no cover
    build_pivot_by_account = None  # type: ignore
    filter_by_accounts = None  # type: ignore

# Import analysis_filters for parsing and filtering.  These modules
# provide functions for parsing numeric filter values and filtering
# datasets based on search/direction/amounts.  If unavailable,
# filtering simply won't be applied.
try:
    from analysis_filters import parse_amount, filter_dataset  # type: ignore
except Exception:  # pragma: no cover
    parse_amount = None  # type: ignore
    filter_dataset = None  # type: ignore


class AnalysePage(ttk.Frame):
    """Tkinter frame that displays dataset summaries and details.

    This class can be embedded in a :class:`ttk.Notebook` and relies on
    the caller to update it with a session object via
    :meth:`refresh_from_session`.  When a session is supplied and a
    dataset is present on that session, the page displays a pivot
    summary by account and allows the user to drill into the
    underlying transactions.  A callback registered via
    :meth:`set_utvalg_callback` will be invoked when the user clicks
    the "Til utvalg" button.
    """

    def __init__(self, parent: Any) -> None:
        # Initialise base class so the widget can be added to containers
        super().__init__(parent)
        # Store parent for future use
        self.parent: Any = parent
        # Session and dataset references
        self._session: Optional[Any] = None
        self.dataset: Optional[Any] = None
        # A filtered view of the dataset based on the current filter
        # criteria.  When filters are applied, this holds the subset
        # used for pivoting and detail display.  Otherwise it may be
        # None.
        self._filtered_df: Optional[Any] = None
        # Callback for sending selected accounts
        self._utvalg_callback: Optional[Callable[[Any], None]] = None
        # Internal widgets initialised in _build_ui
        self._summary_tree: Any = None
        self._detail_tree: Any = None
        self._send_button: Any = None
        # Filter widgets
        self._search_var: Any = None
        self._search_entry: Any = None
        self._dir_var: Any = None
        self._dir_combo: Any = None
        self._min_var: Any = None
        self._min_entry: Any = None
        self._max_var: Any = None
        self._max_entry: Any = None
        self._apply_button: Any = None
        self._reset_button: Any = None
        # Build the GUI components
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_utvalg_callback(self, callback: Callable[[Any], None]) -> None:
        """Register a callback to receive selected accounts.

        Parameters
        ----------
        callback : Callable[[Any], None]
            A function that accepts a single argument containing the
            selected accounts.  It will be invoked by
            :meth:`_send_to_selection` when the user presses the
            "Til utvalg" button.
        """
        self._utvalg_callback = callback

    def refresh_from_session(self, session: Any) -> None:
        """Update the page with a new session object.

        This method stores the session reference and attempts to pull
        out a dataset via either the ``dataset`` or ``df`` attribute.
        Whatever value is found is stored on the instance (even if
        it's not a pandas DataFrame) so that unit tests can verify the
        assignment.  If a dataset is set, :meth:`_load_from_session`
        will be invoked to rebuild the GUI state.  Exceptions raised
        during that process are silently ignored to prevent the GUI
        from crashing.

        Parameters
        ----------
        session : Any
            An arbitrary object representing the current session.  It
            should carry either a ``dataset`` or ``df`` attribute.
        """
        self._session = session
        # Extract dataset if available
        value = None
        if hasattr(session, "dataset"):
            try:
                value = session.dataset  # type: ignore[attr-defined]
            except Exception:
                value = None
        if value is None and hasattr(session, "df"):
            try:
                value = session.df  # type: ignore[attr-defined]
            except Exception:
                value = None
        if value is not None:
            self.dataset = value
        # Rebuild GUI based on the dataset.  Swallow errors to avoid
        # breaking the application when e.g. pandas isn't installed.
        try:
            self._load_from_session()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Construct the GUI elements for the analysis page.

        This method creates a summary tree view on the left and a
        detail tree view on the right, plus a button at the bottom to
        forward selected accounts.  The tree views will be configured
        later when a dataset is loaded.
        """
        # Configure a grid with three rows: filters, main view and buttons
        try:
            for col in (0, 1):
                self.columnconfigure(col, weight=1)
            # Row 0: filter bar (not expandable)
            self.rowconfigure(0, weight=0)
            # Row 1: summary/detail trees (expandable)
            self.rowconfigure(1, weight=1)
            # Row 2: bottom buttons (not expandable)
            self.rowconfigure(2, weight=0)
        except Exception:
            pass
        # --- Filter bar (top row) ---
        filter_frame = ttk.Frame(self)
        try:
            filter_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 4), padx=(4, 4))
        except Exception:
            pass
        # Søk/tekstfilter
        try:
            ttk.Label(filter_frame, text="Søk:").pack(side="left")
        except Exception:
            pass
        try:
            import tkinter as tk  # noqa: F401
            self._search_var = tk.StringVar()  # type: ignore
        except Exception:
            self._search_var = None  # type: ignore
        # Use Entry from ttk; if unavailable, fallback to dummy
        try:
            self._search_entry = ttk.Entry(filter_frame, textvariable=self._search_var, width=16)
            self._search_entry.pack(side="left", padx=(2, 8))
            # Bind key release to filter update
            self._search_entry.bind("<KeyRelease>", self._on_filters_changed)
        except Exception:
            self._search_entry = None
        # Retning
        try:
            ttk.Label(filter_frame, text="Retning:").pack(side="left")
        except Exception:
            pass
        try:
            self._dir_var = tk.StringVar(value="Alle")  # type: ignore
        except Exception:
            self._dir_var = None  # type: ignore
        try:
            self._dir_combo = ttk.Combobox(filter_frame, state="readonly", width=8,
                                           values=["Alle", "Debet", "Kredit"], textvariable=self._dir_var)
            self._dir_combo.pack(side="left", padx=(2, 8))
            # Bind selection change to filter update
            self._dir_combo.bind("<<ComboboxSelected>>", self._on_filters_changed)
        except Exception:
            self._dir_combo = None
        # Min beløp
        try:
            ttk.Label(filter_frame, text="Min beløp:").pack(side="left")
        except Exception:
            pass
        try:
            self._min_var = tk.StringVar()  # type: ignore
        except Exception:
            self._min_var = None  # type: ignore
        try:
            self._min_entry = ttk.Entry(filter_frame, textvariable=self._min_var, width=10)
            self._min_entry.pack(side="left", padx=(2, 8))
            self._min_entry.bind("<KeyRelease>", self._on_filters_changed)
        except Exception:
            self._min_entry = None
        # Max beløp
        try:
            ttk.Label(filter_frame, text="Maks beløp:").pack(side="left")
        except Exception:
            pass
        try:
            self._max_var = tk.StringVar()  # type: ignore
        except Exception:
            self._max_var = None  # type: ignore
        try:
            self._max_entry = ttk.Entry(filter_frame, textvariable=self._max_var, width=10)
            self._max_entry.pack(side="left", padx=(2, 8))
            self._max_entry.bind("<KeyRelease>", self._on_filters_changed)
        except Exception:
            self._max_entry = None
        # Reset and apply buttons
        try:
            self._reset_button = ttk.Button(filter_frame, text="Nulstill", command=self._on_reset_filters)
            self._reset_button.pack(side="left", padx=(4, 4))
        except Exception:
            self._reset_button = None
        try:
            self._apply_button = ttk.Button(filter_frame, text="Bruk filtre", command=self._apply_filters)
            self._apply_button.pack(side="left")
        except Exception:
            self._apply_button = None
        # --- Main views (second row) ---
        self._summary_tree = ttk.Treeview(self, columns=(), show="headings", selectmode="extended")
        try:
            self._summary_tree.bind("<<TreeviewSelect>>", self._on_summary_select)
        except Exception:
            pass
        try:
            self._summary_tree.grid(row=1, column=0, sticky="nsew")
        except Exception:
            pass
        self._detail_tree = ttk.Treeview(self, columns=(), show="headings", selectmode="browse")
        try:
            self._detail_tree.grid(row=1, column=1, sticky="nsew")
        except Exception:
            pass
        # --- Bottom row: send to selection ---
        btn_frame = ttk.Frame(self)
        try:
            btn_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 4), padx=(4, 4))
        except Exception:
            pass
        self._send_button = ttk.Button(btn_frame, text="Til utvalg", command=self._on_send)
        try:
            self._send_button.pack(side="left")
        except Exception:
            pass

    def _load_from_session(self) -> None:
        """Rebuild the trees from the current dataset.

        When a session provides a dataset, this method will invoke
        :meth:`_apply_filters` to compute a filtered view and update
        the pivot.  If dependencies are missing, both trees are
        cleared.
        """
        # Always clear existing entries
        try:
            for tree in (self._summary_tree, self._detail_tree):
                tree.delete(*tree.get_children())
        except Exception:
            pass
        # If we don't have pandas or the pivot builder, we cannot compute
        # anything.  Bail out early.
        if not (build_pivot_by_account and pd and isinstance(self.dataset, pd.DataFrame)):
            return
        # Apply current filters and update pivot
        self._apply_filters()

    def _on_summary_select(self, _event: Any) -> None:
        """Handle selection changes in the summary tree.

        When the user selects one or more accounts in the summary tree,
        this method filters the original dataset for those accounts
        (using ``filter_by_accounts``) and populates the detail tree
        with the matching transactions.  If no accounts are selected
        the entire dataset is shown.
        """
        # Guard against missing dependencies
        if not (filter_by_accounts and pd and isinstance(self.dataset, pd.DataFrame)):
            return
        # Use the filtered DataFrame if available, otherwise fall back to full dataset
        df: pd.DataFrame = (self._filtered_df if isinstance(self._filtered_df, pd.DataFrame) else self.dataset)  # type: ignore[assignment]
        # Determine selected accounts from the first column of each selected row
        selected_items: Iterable[str] = self._summary_tree.selection() if self._summary_tree else []
        accounts: List[Any] = []
        for item_id in selected_items:
            try:
                item = self._summary_tree.item(item_id)
            except Exception:
                continue
            vals = item.get("values", [])
            if vals:
                accounts.append(vals[0])
        # Filter dataset
        try:
            if accounts:
                sub_df = filter_by_accounts(df, accounts)
            else:
                sub_df = df
        except Exception:
            sub_df = df
        # Update detail tree: clear existing items and configure columns
        try:
            self._detail_tree.delete(*self._detail_tree.get_children())
        except Exception:
            pass
        if sub_df is None or sub_df.empty:
            return
        detail_cols: List[str] = list(sub_df.columns)
        try:
            self._detail_tree.configure(columns=detail_cols)
        except Exception:
            pass
        for col in detail_cols:
            try:
                self._detail_tree.heading(col, text=str(col))
            except Exception:
                pass
            try:
                self._detail_tree.column(col, width=100, anchor="w", stretch=True)
            except Exception:
                pass
        # Insert rows
        for _, row in sub_df.iterrows():
            values = [row.get(col) for col in detail_cols]
            try:
                self._detail_tree.insert("", "end", values=values)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def _on_filters_changed(self, _event: Any) -> None:
        """Handle changes in search and amount filter fields.

        This method is bound to key events and combo selections on
        filter widgets.  It simply invokes :meth:`_apply_filters` to
        recompute the pivot based on the current filter values.
        """
        # Debounce frequent key events by scheduling an update on the event
        # loop.  In headless environments this is a no‑op.
        try:
            self.after_idle(self._apply_filters)
        except Exception:
            # Fallback to immediate invocation
            self._apply_filters()

    def _apply_filters(self) -> None:
        """Apply search/direction/amount filters and update the pivot.

        This method reads the current filter widget values, parses
        numeric inputs using :func:`analysis_filters.parse_amount`,
        filters the dataset using :func:`analysis_filters.filter_dataset`,
        computes a new pivot using :func:`build_pivot_by_account`, and
        updates the summary tree accordingly.  It always clears the
        detail tree; the user must re‑select accounts to repopulate it.
        """
        # If we can't filter or pivot, bail out early
        if not (parse_amount and filter_dataset and build_pivot_by_account and pd and isinstance(self.dataset, pd.DataFrame)):
            # As a fallback, keep the full dataset as filtered
            self._filtered_df = self.dataset
            return
        df: pd.DataFrame = self.dataset  # type: ignore[assignment]
        # Extract current filter values
        search = ""
        direction = "Alle"
        min_v = None
        max_v = None
        try:
            if self._search_var is not None:
                search = (self._search_var.get() or "").strip()
        except Exception:
            pass
        try:
            if self._dir_var is not None:
                direction = self._dir_var.get() or "Alle"
        except Exception:
            pass
        try:
            if self._min_var is not None:
                min_v = parse_amount(self._min_var.get())
        except Exception:
            min_v = None
        try:
            if self._max_var is not None:
                max_v = parse_amount(self._max_var.get())
        except Exception:
            max_v = None
        # Filter dataset
        try:
            filtered = filter_dataset(df, search=search, direction=direction, min_amount=min_v, max_amount=max_v)
        except Exception:
            filtered = df
        # Store filtered view
        self._filtered_df = filtered
        # Compute pivot on filtered
        try:
            pivot: pd.DataFrame = build_pivot_by_account(filtered)
        except Exception:
            pivot = None  # type: ignore[assignment]
        # Clear summary and detail trees
        try:
            self._summary_tree.delete(*self._summary_tree.get_children())
            self._detail_tree.delete(*self._detail_tree.get_children())
        except Exception:
            pass
        # Populate pivot if available
        if pivot is not None and not pivot.empty:
            cols: List[str] = list(pivot.columns)
            # Reconfigure summary tree columns
            try:
                self._summary_tree.configure(columns=cols)
            except Exception:
                pass
            for col in cols:
                try:
                    self._summary_tree.heading(col, text=str(col))
                except Exception:
                    pass
                try:
                    self._summary_tree.column(col, width=100, anchor="w", stretch=True)
                except Exception:
                    pass
            # Insert pivot rows
            for _, row in pivot.iterrows():
                vals = [row.get(col) for col in cols]
                try:
                    self._summary_tree.insert("", "end", values=vals)
                except Exception:
                    pass

    def _on_reset_filters(self) -> None:
        """Reset all filter widgets to their default values and refresh.

        This clears the search text, resets direction to "Alle", and
        clears minimum and maximum amount fields.  The pivot is then
        recomputed on the full dataset.
        """
        try:
            if self._search_var is not None:
                self._search_var.set("")
            if self._dir_var is not None:
                self._dir_var.set("Alle")
            if self._min_var is not None:
                self._min_var.set("")
            if self._max_var is not None:
                self._max_var.set("")
        except Exception:
            pass
        # Apply filters using defaults
        self._apply_filters()

    def _on_send(self) -> None:
        """Handle clicking the 'Til utvalg' button.

        Gather the accounts selected in the summary tree and invoke
        :meth:`_send_to_selection` with that list.  If no rows are
        selected, an empty list is passed.
        """
        accounts: List[Any] = []
        try:
            selected_items: Iterable[str] = self._summary_tree.selection()
            for item_id in selected_items:
                item = self._summary_tree.item(item_id)
                vals = item.get("values", [])
                if vals:
                    accounts.append(vals[0])
        except Exception:
            accounts = []
        self._send_to_selection(accounts)

    def _send_to_selection(self, accounts: Any) -> None:
        """Forward selected accounts to the registered callback.

        This method simply wraps invocation of the callback in a try/
        except so that errors in user‑supplied callbacks do not
        propagate back into the GUI.

        Parameters
        ----------
        accounts : Any
            The accounts to send on.  Typically this is a list of
            account identifiers.
        """
        if self._utvalg_callback is not None:
            try:
                self._utvalg_callback(accounts)
            except Exception:
                pass
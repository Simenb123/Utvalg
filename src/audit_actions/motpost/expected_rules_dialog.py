from __future__ import annotations

"""Dialog for redigering av strukturerte forventningsregler per kilde-RL.

Rene hjelpere (rendering-uavhengige) er eksportert for enhetstesting.
UI-delen bygger på Tkinter/ttk og returnerer oppdatert ``ExpectedRuleSet``
eller ``None`` ved avbryt.
"""

from dataclasses import dataclass, field
from typing import Iterable, Mapping

import tkinter as tk
from tkinter import messagebox, ttk

from .expected_rules import (
    DEFAULT_BALANCE_TOLERANCE,
    BalancePair,
    ExpectedRule,
    ExpectedRuleSet,
    empty_rule_set,
    normalize_direction,
)
from .utils import _konto_str


MVA_GROUP_IDS: frozenset[str] = frozenset(
    {"Skyldig MVA", "Inngående MVA", "Utgående MVA"}
)


def _label_regnr(label: str) -> int | None:
    head = str(label or "").strip().split(" ", 1)[0].strip()
    try:
        return int(head)
    except Exception:
        return None


def build_rl_options(
    konto_regnskapslinje_map: Mapping[str, str] | None,
    *,
    exclude_regnr: int | None = None,
) -> list[tuple[int, str]]:
    """Liste av (regnr, label) sortert på regnr, én entry per unike RL.

    ``exclude_regnr`` tar bort f.eks. kilde-RL fra target-listen.
    """
    options: dict[int, str] = {}
    for _, label in (konto_regnskapslinje_map or {}).items():
        regnr = _label_regnr(label)
        if regnr is None:
            continue
        if exclude_regnr is not None and regnr == int(exclude_regnr):
            continue
        if regnr not in options:
            options[regnr] = str(label).strip()
    return sorted(options.items(), key=lambda kv: kv[0])


def load_all_rl_options(
    *,
    loader=None,
    exclude_regnr: int | None = None,
) -> list[tuple[int, str]]:
    """Komplett RL-liste fra regnskap_config. Tom ved feil/manglende fil.

    ``loader`` er injiserbar for testing (default: ``regnskap_config.load_regnskapslinjer``).
    """
    if loader is None:
        try:
            import src.shared.regnskap.config as regnskap_config

            loader = regnskap_config.load_regnskapslinjer
        except Exception:
            return []
    try:
        df = loader()
    except Exception:
        return []
    if df is None:
        return []
    try:
        from src.shared.regnskap.mapping import normalize_regnskapslinjer

        regn = normalize_regnskapslinjer(df)
    except Exception:
        return []
    options: list[tuple[int, str]] = []
    seen: set[int] = set()
    for row in regn.itertuples(index=False):
        try:
            regnr = int(getattr(row, "regnr"))
        except Exception:
            continue
        if regnr in seen:
            continue
        if exclude_regnr is not None and regnr == int(exclude_regnr):
            continue
        name = str(getattr(row, "regnskapslinje", "") or "").strip()
        label = f"{regnr} {name}".strip() if name else str(regnr)
        options.append((regnr, label))
        seen.add(regnr)
    options.sort(key=lambda kv: kv[0])
    return options


def accounts_in_target_rl(
    konto_regnskapslinje_map: Mapping[str, str] | None,
    target_regnr: int,
) -> list[str]:
    """Kontoer som mapper til target-RL, sortert alfanumerisk."""
    result: list[str] = []
    for konto, label in (konto_regnskapslinje_map or {}).items():
        if _label_regnr(label) == int(target_regnr):
            k = _konto_str(konto)
            if k and k not in result:
                result.append(k)
    return sorted(result)


def mva_flagged_accounts(
    mva_group_map: Mapping[str, str] | None,
    scope_accounts: Iterable[str],
) -> set[str]:
    """Kontoer innen scope som er klassifisert i en MVA-gruppe."""
    flagged: set[str] = set()
    mapping = mva_group_map or {}
    for konto in scope_accounts:
        k = _konto_str(konto)
        if not k:
            continue
        group = str(mapping.get(k, "") or "").strip()
        if group in MVA_GROUP_IDS:
            flagged.add(k)
    return flagged


def build_mva_group_map(
    client: str | None,
    *,
    loader=None,
) -> dict[str, str]:
    """Last konto -> MVA-gruppe. Kun MVA-klassifiserte kontoer returneres.

    ``loader`` er injiserbar for testing (default: ``konto_klassifisering.load``).
    """
    if not client:
        return {}
    if loader is None:
        try:
            import konto_klassifisering

            loader = konto_klassifisering.load
        except Exception:
            return {}
    try:
        raw = loader(client) or {}
    except Exception:
        return {}
    result: dict[str, str] = {}
    for konto, group in raw.items():
        k = _konto_str(konto)
        g = str(group or "").strip()
        if k and g in MVA_GROUP_IDS:
            result[k] = g
    return result


def format_rule_summary(
    rule: ExpectedRule,
    *,
    regnr_to_label: Mapping[int, str] | None = None,
) -> str:
    """Kort én-linje tekst for en regel i venstre liste."""
    label_map = regnr_to_label or {}
    label = label_map.get(int(rule.target_regnr), str(rule.target_regnr))
    if rule.account_mode == "selected":
        count = len(rule.allowed_accounts)
        body = f"{label}  (kun {count} konto{'er' if count != 1 else ''})"
    else:
        excl_count = len(rule.excluded_accounts)
        if excl_count:
            body = (
                f"{label}  (alle kontoer, {excl_count} "
                f"skopet ut)"
            )
        else:
            body = f"{label}  (alle kontoer)"
    return body


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


@dataclass
class _RuleEdit:
    """Mutable arbeidskopi av en regel brukt i dialogen.

    UI-en er eksklusjonsbasert: alle kontoer i RL regnes som forventet,
    og `excluded_accounts` er skopet ut. Eldre regler med
    ``account_mode="selected"`` konverteres til eksklusjon ved åpning via
    :meth:`from_rule` (scope_kontos gis som parameter).
    """
    target_regnr: int | None
    account_mode: str = "all"
    allowed_accounts: list[str] = field(default_factory=list)
    excluded_accounts: list[str] = field(default_factory=list)

    @classmethod
    def from_rule(
        cls,
        rule: ExpectedRule,
        *,
        target_rl_accounts: Iterable[str] | None = None,
    ) -> "_RuleEdit":
        excluded = list(rule.excluded_accounts)
        if rule.account_mode == "selected" and target_rl_accounts is not None:
            whitelist = {_konto_str(k) for k in rule.allowed_accounts if _konto_str(k)}
            for konto in target_rl_accounts:
                k = _konto_str(konto)
                if k and k not in whitelist and k not in excluded:
                    excluded.append(k)
        return cls(
            target_regnr=int(rule.target_regnr),
            account_mode="all",
            allowed_accounts=[],
            excluded_accounts=excluded,
        )

    def to_rule(self) -> ExpectedRule:
        if self.target_regnr is None:
            raise ValueError("target_regnr må være satt før regelen lagres")
        return ExpectedRule(
            target_regnr=int(self.target_regnr),
            account_mode="all",
            allowed_accounts=(),
            excluded_accounts=tuple(self.excluded_accounts),
        )


def choose_expected_rules(
    parent: tk.Misc,
    *,
    client: str | None,
    source_regnr: int,
    source_label: str,
    selected_direction: str | None,
    konto_regnskapslinje_map: Mapping[str, str] | None,
    konto_navn_map: Mapping[str, str] | None = None,
    initial_rule_set: ExpectedRuleSet | None = None,
    mva_group_map: Mapping[str, str] | None = None,
    all_rl_options: list[tuple[int, str]] | None = None,
    konto_sum_map: Mapping[str, float] | None = None,
    konto_sb_map: Mapping[str, Mapping[str, object]] | None = None,
    motpost_konto_set: Iterable[str] | None = None,
) -> ExpectedRuleSet | None:
    """Åpne modal dialog. Returnerer oppdatert regelsett eller ``None`` ved avbryt."""
    direction = normalize_direction(selected_direction)
    rule_set = initial_rule_set or empty_rule_set(source_regnr, direction)
    rules: list[_RuleEdit] = [
        _RuleEdit.from_rule(
            r,
            target_rl_accounts=accounts_in_target_rl(
                konto_regnskapslinje_map, r.target_regnr
            ),
        )
        for r in rule_set.rules
    ]
    balance_pairs_state: list[BalancePair] = list(
        getattr(rule_set, "balance_pairs", ()) or ()
    )
    scope_rl_options = build_rl_options(konto_regnskapslinje_map, exclude_regnr=int(source_regnr))
    # RL-er som faktisk observeres som motpost til kilden i aktuelt utvalg.
    motpost_rl_map: dict[str, str] = {}
    for konto_key in motpost_konto_set or ():
        key = _konto_str(konto_key)
        if not key:
            continue
        label = (konto_regnskapslinje_map or {}).get(key)
        if label:
            motpost_rl_map[key] = str(label)
    motpost_rl_options = build_rl_options(
        motpost_rl_map, exclude_regnr=int(source_regnr)
    )
    if all_rl_options is None:
        all_rl_options = load_all_rl_options(exclude_regnr=int(source_regnr))
    # Fallback: hvis full liste er tom (f.eks. ingen regnskapslinjer.xlsx), bruk scope.
    if not all_rl_options:
        all_rl_options = list(scope_rl_options)
    # Sørg for at eksisterende regler sine target_regnr er representert i full-lista.
    scope_regnrs = {r for r, _ in scope_rl_options}
    known_regnrs = {r for r, _ in all_rl_options}
    for edit in rules:
        if edit.target_regnr is None:
            continue
        if edit.target_regnr not in known_regnrs:
            all_rl_options.append((edit.target_regnr, f"{edit.target_regnr}"))
            known_regnrs.add(edit.target_regnr)
    all_rl_options.sort(key=lambda kv: kv[0])
    regnr_to_label = {regnr: label for regnr, label in all_rl_options}
    navn_map = {_konto_str(k): str(v) for k, v in (konto_navn_map or {}).items()}
    sum_map: dict[str, float] = {}
    for k, v in (konto_sum_map or {}).items():
        key = _konto_str(k)
        if not key:
            continue
        try:
            sum_map[key] = float(v)
        except Exception:
            continue
    sb_map: dict[str, dict[str, float]] = {}
    for k, v in (konto_sb_map or {}).items():
        key = _konto_str(k)
        if not key or not isinstance(v, Mapping):
            continue
        entry: dict[str, float] = {}
        for field in ("ib", "ub", "netto"):
            raw = v.get(field)
            if raw is None:
                continue
            try:
                entry[field] = float(raw)
            except Exception:
                continue
        navn = v.get("kontonavn")
        if isinstance(navn, str) and navn.strip():
            navn_map.setdefault(key, navn.strip())
        if entry:
            sb_map[key] = entry
    mva_map = mva_group_map if mva_group_map is not None else build_mva_group_map(client)
    motpost_kontos: set[str] = set()
    for k in motpost_konto_set or ():
        key = _konto_str(k)
        if key:
            motpost_kontos.add(key)

    result: dict[str, ExpectedRuleSet | None] = {"value": None}

    win = tk.Toplevel(parent)
    win.title(f"Forventningsregler — {source_label}")
    win.geometry("960x640")
    win.minsize(820, 520)
    win.grab_set()

    outer = ttk.Frame(win, padding=10)
    outer.pack(fill=tk.BOTH, expand=True)

    # Header: kilde + intro
    header = ttk.Frame(outer)
    header.pack(fill=tk.X, pady=(0, 8))
    ttk.Label(
        header,
        text=f"Kilde: {source_label}  |  Retning: {direction.capitalize()}",
        font=("", 10, "bold"),
    ).pack(side=tk.LEFT)
    ttk.Label(
        header,
        text="Definer hvilke motposter som er forventet for denne kilde-regnskapslinjen.",
        foreground="#555555",
    ).pack(side=tk.LEFT, padx=(12, 0))

    body = ttk.Frame(outer)
    body.pack(fill=tk.BOTH, expand=True)
    body.columnconfigure(0, weight=1, minsize=280)
    body.columnconfigure(1, weight=2, minsize=480)
    body.rowconfigure(0, weight=1)

    # --- Left: rules list + balance pairs ----------------------------------
    left_wrap = ttk.Frame(body)
    left_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    left_wrap.columnconfigure(0, weight=1)
    left_wrap.rowconfigure(0, weight=2)
    left_wrap.rowconfigure(1, weight=1)

    left = ttk.LabelFrame(left_wrap, text="Forventede motposter")
    left.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
    left.rowconfigure(1, weight=1)
    left.columnconfigure(0, weight=1)

    list_bar = ttk.Frame(left)
    list_bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
    btn_add = ttk.Button(list_bar, text="+ Legg til regel")
    btn_add.pack(side=tk.LEFT)
    btn_delete = ttk.Button(list_bar, text="Slett regel", state="disabled")
    btn_delete.pack(side=tk.LEFT, padx=(6, 0))

    rules_list = tk.Listbox(left, exportselection=False, activestyle="dotbox")
    rules_list.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))

    pair_frame = ttk.LabelFrame(left_wrap, text="Utligningspar")
    pair_frame.grid(row=1, column=0, sticky="nsew")
    pair_frame.rowconfigure(1, weight=1)
    pair_frame.columnconfigure(0, weight=1)

    pair_bar = ttk.Frame(pair_frame)
    pair_bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
    btn_pair_add = ttk.Button(pair_bar, text="+ Legg til par")
    btn_pair_add.pack(side=tk.LEFT)
    btn_pair_delete = ttk.Button(pair_bar, text="Slett par", state="disabled")
    btn_pair_delete.pack(side=tk.LEFT, padx=(6, 0))

    pairs_list = tk.Listbox(
        pair_frame, exportselection=False, activestyle="dotbox", height=4
    )
    pairs_list.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))

    # Empty-state hint (vises kun når ingen regler finnes)
    hint_var = tk.StringVar(
        value=(
            "Ingen regler ennå.\n\n"
            "Klikk \"+ Legg til regel\" for å velge en motpost-RL."
        )
    )
    hint_label = ttk.Label(
        left,
        textvariable=hint_var,
        foreground="#888888",
        justify="center",
        anchor="center",
    )

    # --- Right: detail panel -----------------------------------------------
    right = ttk.LabelFrame(body, text="Detaljer for valgt regel")
    right.grid(row=0, column=1, sticky="nsew")
    right.columnconfigure(1, weight=1)
    right.rowconfigure(4, weight=1)

    # Placeholder (vises når ingen regel er valgt)
    placeholder_var = tk.StringVar(value="Velg en regel til venstre eller legg til en ny.")
    placeholder_label = ttk.Label(
        right,
        textvariable=placeholder_var,
        foreground="#888888",
        anchor="center",
        justify="center",
    )

    # Ekte kontroller (pakkes kun når en regel er valgt)
    detail_widgets: list[tk.Misc] = []

    lbl_target = ttk.Label(right, text="Motpost-regnskapslinje:")
    target_var = tk.StringVar()
    combo_target = ttk.Combobox(
        right,
        textvariable=target_var,
        values=[label for _, label in all_rl_options],
        state="readonly",
        height=25,
    )
    scope_only_var = tk.BooleanVar(value=False)
    chk_scope_only = ttk.Checkbutton(
        right,
        text="Vis bare RL-er som har motposter i utvalget",
        variable=scope_only_var,
    )
    if not motpost_rl_options:
        chk_scope_only.state(("disabled",))
    motpost_only_var = tk.BooleanVar(value=False)
    chk_motpost_only = ttk.Checkbutton(
        right,
        text="Skjul kontoer uten bokføringer",
        variable=motpost_only_var,
    )
    if not motpost_kontos:
        chk_motpost_only.state(("disabled",))
    detail_widgets.extend([lbl_target, combo_target, chk_scope_only, chk_motpost_only])

    instruction_label = ttk.Label(
        right,
        text="Markér kontoer du vil ekskludere fra regelen.",
        foreground="#555555",
        wraplength=700,
        justify="left",
    )
    detail_widgets.append(instruction_label)

    list_frame = ttk.Frame(right)
    list_frame.columnconfigure(0, weight=1)
    list_frame.rowconfigure(0, weight=1)
    detail_widgets.append(list_frame)

    accounts_tree = ttk.Treeview(
        list_frame,
        columns=("konto", "navn", "ib", "endring", "ub", "mva"),
        show="headings",
        selectmode="extended",
        height=12,
    )
    accounts_tree.heading("konto", text="Konto")
    accounts_tree.heading("navn", text="Kontonavn")
    accounts_tree.heading("ib", text="IB")
    accounts_tree.heading("endring", text="Endring")
    accounts_tree.heading("ub", text="UB")
    accounts_tree.heading("mva", text="MVA")
    accounts_tree.column("konto", width=80, anchor=tk.W)
    accounts_tree.column("navn", width=230, anchor=tk.W)
    accounts_tree.column("ib", width=95, anchor=tk.E)
    accounts_tree.column("endring", width=95, anchor=tk.E)
    accounts_tree.column("ub", width=95, anchor=tk.E)
    accounts_tree.column("mva", width=55, anchor=tk.W)
    accounts_tree.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=accounts_tree.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    accounts_tree.configure(yscrollcommand=scroll.set)

    btn_row = ttk.Frame(right)
    btn_scope_out = ttk.Button(btn_row, text="Ekskluder valgte", state="disabled")
    btn_scope_out.pack(side=tk.LEFT)
    btn_include = ttk.Button(btn_row, text="Inkluder valgte", state="disabled")
    btn_include.pack(side=tk.LEFT, padx=(6, 0))
    selection_status_var = tk.StringVar(value="")
    selection_status_label = ttk.Label(
        btn_row,
        textvariable=selection_status_var,
        foreground="#333333",
        font=("", 9, "bold"),
    )
    selection_status_label.pack(side=tk.RIGHT)
    detail_widgets.append(btn_row)

    # Bottom buttons
    bottom = ttk.Frame(outer)
    bottom.pack(fill=tk.X, pady=(10, 0))
    try:
        style = ttk.Style(win)
        style.configure("Primary.TButton", font=("", 9, "bold"))
    except Exception:
        pass
    btn_ok = ttk.Button(bottom, text="Lagre regler", style="Primary.TButton")
    btn_ok.pack(side=tk.RIGHT)
    btn_cancel = ttk.Button(bottom, text="Avbryt", command=win.destroy)
    btn_cancel.pack(side=tk.RIGHT, padx=(0, 6))

    # item_id -> konto (seleksjonen i treet fungerer som "avkrysning")
    item_to_konto: dict[str, str] = {}
    konto_to_item: dict[str, str] = {}

    # --- Behavior -----------------------------------------------------------
    def _layout_detail_panel(show: bool) -> None:
        for w in detail_widgets:
            try:
                w.grid_forget()
            except Exception:
                pass
        try:
            placeholder_label.grid_forget()
        except Exception:
            pass

        if not show:
            placeholder_label.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
            return

        lbl_target.grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        combo_target.grid(row=0, column=1, sticky="ew", padx=6, pady=(6, 2))
        chk_scope_only.grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(2, 2))
        chk_motpost_only.grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 2))
        instruction_label.grid(row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=(2, 4))
        list_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=6, pady=(0, 6))
        btn_row.grid(row=5, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))

    def _layout_left_panel() -> None:
        try:
            hint_label.grid_forget()
        except Exception:
            pass
        if rules:
            return
        hint_label.grid(row=1, column=0, sticky="nsew", padx=6, pady=20)

    def _format_edit_summary(edit: _RuleEdit) -> str:
        if edit.target_regnr is None:
            return "(velg motpost…)"
        return format_rule_summary(edit.to_rule(), regnr_to_label=regnr_to_label)

    def _refresh_rules_list(select_idx: int | None = None) -> None:
        rules_list.delete(0, tk.END)
        for edit in rules:
            rules_list.insert(tk.END, _format_edit_summary(edit))
        _layout_left_panel()
        if select_idx is not None and 0 <= select_idx < len(rules):
            rules_list.selection_clear(0, tk.END)
            rules_list.selection_set(select_idx)
            rules_list.activate(select_idx)
            _on_rule_selected()
        else:
            _on_rule_selected()
        _update_delete_button()

    def _update_delete_button() -> None:
        try:
            if rules_list.curselection():
                btn_delete.state(("!disabled",))
            else:
                btn_delete.state(("disabled",))
        except Exception:
            pass

    def _current_edit() -> _RuleEdit | None:
        sel = rules_list.curselection()
        if not sel:
            return None
        idx = int(sel[0])
        if 0 <= idx < len(rules):
            return rules[idx]
        return None

    def _format_amount(value: float | None) -> str:
        if value is None:
            return ""
        try:
            v = float(value)
        except Exception:
            return ""
        return f"{v:,.0f}".replace(",", " ")

    def _konto_field(konto: str, field: str) -> float | None:
        entry = sb_map.get(konto)
        if entry is None:
            return None
        return entry.get(field)  # type: ignore[return-value]

    def _konto_endring(konto: str) -> float | None:
        # Prefer SB netto, fall back til summen av transaksjoner.
        val = _konto_field(konto, "netto")
        if val is not None:
            return val
        return sum_map.get(konto)

    try:
        import src.shared.ui.tokens as vt  # type: ignore

        accounts_tree.tag_configure("excluded", foreground=vt.hex_gui(vt.NEG_TEXT), background=vt.hex_gui(vt.NEG_SOFT))
        accounts_tree.tag_configure("included", foreground=vt.hex_gui(vt.POS_TEXT))
    except Exception:
        pass

    def _rebuild_accounts_tree(edit: _RuleEdit) -> None:
        prior_selected_kontos: set[str] = set()
        try:
            for iid in accounts_tree.selection():
                konto = item_to_konto.get(iid, "")
                if konto:
                    prior_selected_kontos.add(konto)
        except Exception:
            prior_selected_kontos = set()
        accounts_tree.delete(*accounts_tree.get_children(""))
        item_to_konto.clear()
        konto_to_item.clear()
        if edit.target_regnr is None:
            _update_selection_status(edit)
            _update_action_buttons()
            return
        target_accounts = accounts_in_target_rl(konto_regnskapslinje_map, edit.target_regnr)
        excluded_set = {_konto_str(k) for k in edit.excluded_accounts if _konto_str(k)}
        if motpost_only_var.get() and motpost_kontos:
            # Behold ekskluderte kontoer så brukeren ser dem, selv om de mangler
            # motpostføringer i dette utvalget.
            target_accounts = [
                k for k in target_accounts
                if k in motpost_kontos or k in excluded_set
            ]
        for konto in target_accounts:
            is_excluded = konto in excluded_set
            mva_badge = "MVA" if konto in mva_map else ""
            navn = navn_map.get(konto, "")
            if is_excluded:
                navn = f"✗ {navn}" if navn else "✗"
            ib_txt = _format_amount(_konto_field(konto, "ib"))
            ub_txt = _format_amount(_konto_field(konto, "ub"))
            endring_txt = _format_amount(_konto_endring(konto))
            tag = "excluded" if is_excluded else "included"
            item_id = accounts_tree.insert(
                "",
                tk.END,
                values=(konto, navn, ib_txt, endring_txt, ub_txt, mva_badge),
                tags=(tag,),
            )
            item_to_konto[item_id] = konto
            konto_to_item[konto] = item_id
        # Bevar seleksjon for kontoer som fortsatt er synlige (f.eks. etter
        # filter-toggle). Ved bytte av regel vil prior_selected_kontos
        # typisk ikke overlappe det nye kontosettet.
        restore_iids = [
            konto_to_item[k] for k in prior_selected_kontos if k in konto_to_item
        ]
        if restore_iids:
            accounts_tree.selection_set(restore_iids)
        else:
            accounts_tree.selection_remove(accounts_tree.selection())
        _update_selection_status(edit)
        _update_action_buttons()

    def _refresh_rule_label_only() -> None:
        sel = rules_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(rules):
            rules_list.delete(idx)
            rules_list.insert(idx, _format_edit_summary(rules[idx]))
            rules_list.selection_set(idx)
            rules_list.activate(idx)

    def _update_action_buttons() -> None:
        sel = accounts_tree.selection()
        edit = _current_edit()
        if edit is None or not sel:
            btn_scope_out.state(("disabled",))
            btn_include.state(("disabled",))
            return
        excluded_set = {_konto_str(k) for k in edit.excluded_accounts if _konto_str(k)}
        selected_kontos = [item_to_konto.get(iid, "") for iid in sel]
        has_included = any(k and k not in excluded_set for k in selected_kontos)
        has_excluded = any(k and k in excluded_set for k in selected_kontos)
        btn_scope_out.state(("!disabled",) if has_included else ("disabled",))
        btn_include.state(("!disabled",) if has_excluded else ("disabled",))

    def _on_selection_changed(_event: tk.Event | None = None) -> None:
        _update_action_buttons()

    accounts_tree.bind("<<TreeviewSelect>>", _on_selection_changed)

    def _update_selection_status(edit: _RuleEdit | None) -> None:
        if edit is None or edit.target_regnr is None:
            selection_status_var.set("")
            return
        target_accounts = accounts_in_target_rl(konto_regnskapslinje_map, edit.target_regnr)
        total = len(target_accounts)
        excluded_set = {_konto_str(k) for k in edit.excluded_accounts if _konto_str(k)}
        excluded_count = sum(1 for k in target_accounts if k in excluded_set)
        included = total - excluded_count
        if excluded_count == 0:
            selection_status_var.set(f"{total} kontoer inkludert")
        else:
            selection_status_var.set(
                f"{included} av {total} inkludert · {excluded_count} ekskludert"
            )

    _suppress_trace = {"value": False}

    def _on_rule_selected(_event: tk.Event | None = None) -> None:
        edit = _current_edit()
        if edit is None:
            _layout_detail_panel(show=False)
            _update_delete_button()
            return
        _layout_detail_panel(show=True)
        _suppress_trace["value"] = True
        try:
            if edit.target_regnr is None:
                target_var.set("")
            else:
                target_var.set(regnr_to_label.get(int(edit.target_regnr), ""))
        finally:
            _suppress_trace["value"] = False
        _rebuild_accounts_tree(edit)
        _update_delete_button()

    rules_list.bind("<<ListboxSelect>>", _on_rule_selected)

    def _on_target_changed(_e: tk.Event | None = None) -> None:
        if _suppress_trace["value"]:
            return
        edit = _current_edit()
        if edit is None:
            return
        label = target_var.get()
        regnr = _label_regnr(label)
        if regnr is None:
            return
        if regnr == edit.target_regnr:
            return
        clash = next(
            (other for other in rules if other is not edit and other.target_regnr == regnr),
            None,
        )
        if clash is not None:
            messagebox.showinfo(
                "RL er allerede i bruk",
                f"Det finnes allerede en regel for {regnr_to_label.get(regnr, regnr)}. "
                "Rediger den eksisterende regelen i stedet, eller slett den først.",
                parent=win,
            )
            _suppress_trace["value"] = True
            try:
                target_var.set(regnr_to_label.get(int(edit.target_regnr), ""))
            finally:
                _suppress_trace["value"] = False
            return
        edit.target_regnr = regnr
        target_accounts = accounts_in_target_rl(konto_regnskapslinje_map, regnr)
        edit.allowed_accounts = []
        edit.excluded_accounts = [k for k in edit.excluded_accounts if k in target_accounts]
        _rebuild_accounts_tree(edit)
        _refresh_rule_label_only()

    combo_target.bind("<<ComboboxSelected>>", _on_target_changed)

    def _apply_target_options() -> None:
        scope_only = bool(scope_only_var.get())
        base = motpost_rl_options if scope_only else all_rl_options
        edit = _current_edit()
        current_regnr = edit.target_regnr if edit is not None else None
        options = list(base)
        if current_regnr is not None and current_regnr not in {r for r, _ in options}:
            label = regnr_to_label.get(int(current_regnr), str(current_regnr))
            options.append((int(current_regnr), label))
            options.sort(key=lambda kv: kv[0])
        combo_target.configure(values=[label for _, label in options])
        if edit is not None:
            _suppress_trace["value"] = True
            try:
                if edit.target_regnr is None:
                    target_var.set("")
                else:
                    target_var.set(regnr_to_label.get(int(edit.target_regnr), ""))
            finally:
                _suppress_trace["value"] = False

    def _on_scope_toggle(*_args) -> None:
        _apply_target_options()

    scope_only_var.trace_add("write", _on_scope_toggle)

    def _on_motpost_only_toggle(*_args) -> None:
        edit = _current_edit()
        if edit is None:
            return
        _rebuild_accounts_tree(edit)

    motpost_only_var.trace_add("write", _on_motpost_only_toggle)

    def _on_add_rule() -> None:
        if not all_rl_options:
            messagebox.showinfo(
                "Ingen RL tilgjengelig",
                "Det finnes ingen regnskapslinjer å velge som motpost.",
                parent=win,
            )
            return
        rules.append(
            _RuleEdit(
                target_regnr=None,
                account_mode="all",
                allowed_accounts=[],
                excluded_accounts=[],
            )
        )
        _refresh_rules_list(select_idx=len(rules) - 1)

    def _format_pair(pair: BalancePair) -> str:
        a = regnr_to_label.get(int(pair.rl_a), str(pair.rl_a))
        b = regnr_to_label.get(int(pair.rl_b), str(pair.rl_b))
        tol = max(float(pair.tolerance), 0.0)
        return f"{a}  ↔  {b}  (±{tol:g} kr)"

    def _refresh_pairs_list(select_idx: int | None = None) -> None:
        pairs_list.delete(0, tk.END)
        for pair in balance_pairs_state:
            pairs_list.insert(tk.END, _format_pair(pair))
        if select_idx is not None and 0 <= select_idx < len(balance_pairs_state):
            pairs_list.selection_clear(0, tk.END)
            pairs_list.selection_set(select_idx)
            pairs_list.activate(select_idx)
        _update_pair_delete_button()

    def _update_pair_delete_button() -> None:
        try:
            if pairs_list.curselection():
                btn_pair_delete.state(("!disabled",))
            else:
                btn_pair_delete.state(("disabled",))
        except Exception:
            pass

    def _on_pair_selected(_event: tk.Event | None = None) -> None:
        _update_pair_delete_button()

    pairs_list.bind("<<ListboxSelect>>", _on_pair_selected)

    def _available_pair_options() -> list[tuple[int, str]]:
        options: list[tuple[int, str]] = []
        seen: set[int] = set()
        for edit in rules:
            if edit.target_regnr is None or edit.target_regnr in seen:
                continue
            seen.add(int(edit.target_regnr))
            options.append(
                (int(edit.target_regnr), regnr_to_label.get(int(edit.target_regnr), str(edit.target_regnr)))
            )
        options.sort(key=lambda kv: kv[0])
        return options

    def _on_pair_add() -> None:
        options = _available_pair_options()
        if len(options) < 2:
            messagebox.showinfo(
                "For få regler",
                "Du må ha minst to regler med valgt motpost før du kan lage et par.",
                parent=win,
            )
            return
        modal = tk.Toplevel(win)
        modal.title("Legg til utligningspar")
        modal.transient(win)
        modal.grab_set()
        frm = ttk.Frame(modal, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="RL A:").grid(row=0, column=0, sticky="w", pady=(0, 4))
        var_a = tk.StringVar(value=options[0][1])
        combo_a = ttk.Combobox(
            frm,
            textvariable=var_a,
            values=[lbl for _, lbl in options],
            state="readonly",
            width=32,
        )
        combo_a.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 4))

        ttk.Label(frm, text="RL B:").grid(row=1, column=0, sticky="w", pady=(0, 4))
        var_b = tk.StringVar(value=options[1][1])
        combo_b = ttk.Combobox(
            frm,
            textvariable=var_b,
            values=[lbl for _, lbl in options],
            state="readonly",
            width=32,
        )
        combo_b.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(0, 4))

        ttk.Label(frm, text="Toleranse (kr):").grid(row=2, column=0, sticky="w", pady=(0, 4))
        tol_var_pair = tk.StringVar(value=f"{DEFAULT_BALANCE_TOLERANCE:g}")
        entry_tol_pair = ttk.Entry(frm, textvariable=tol_var_pair, width=10)
        entry_tol_pair.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(0, 4))

        err_var = tk.StringVar(value="")
        ttk.Label(frm, textvariable=err_var, foreground="#B00000").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(2, 6)
        )

        label_to_regnr = {lbl: regnr for regnr, lbl in options}

        def _commit_pair() -> None:
            rl_a = label_to_regnr.get(var_a.get())
            rl_b = label_to_regnr.get(var_b.get())
            if rl_a is None or rl_b is None:
                err_var.set("Velg begge RL-er.")
                return
            if rl_a == rl_b:
                err_var.set("Par må bestå av to forskjellige RL-er.")
                return
            try:
                tol = float(tol_var_pair.get().replace(",", "."))
            except Exception:
                err_var.set("Toleransen må være et tall ≥ 0.")
                return
            if tol < 0:
                err_var.set("Toleransen må være et tall ≥ 0.")
                return
            existing = {
                tuple(sorted((p.rl_a, p.rl_b))) for p in balance_pairs_state
            }
            if tuple(sorted((rl_a, rl_b))) in existing:
                err_var.set("Dette paret finnes allerede.")
                return
            balance_pairs_state.append(
                BalancePair(rl_a=int(rl_a), rl_b=int(rl_b), tolerance=max(tol, 0.0))
            )
            modal.destroy()
            _refresh_pairs_list(select_idx=len(balance_pairs_state) - 1)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(6, 0))
        ttk.Button(btns, text="Avbryt", command=modal.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btns, text="Lagre", command=_commit_pair).pack(side=tk.RIGHT)
        combo_a.focus_set()
        modal.wait_window()

    btn_pair_add.configure(command=_on_pair_add)

    def _on_pair_delete() -> None:
        sel = pairs_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(balance_pairs_state):
            balance_pairs_state.pop(idx)
            new_idx = min(idx, len(balance_pairs_state) - 1) if balance_pairs_state else None
            _refresh_pairs_list(select_idx=new_idx)

    btn_pair_delete.configure(command=_on_pair_delete)

    btn_add.configure(command=_on_add_rule)

    def _on_delete_rule() -> None:
        sel = rules_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(rules):
            rules.pop(idx)
            new_idx = min(idx, len(rules) - 1) if rules else None
            _refresh_rules_list(select_idx=new_idx)

    btn_delete.configure(command=_on_delete_rule)

    def _on_scope_out() -> None:
        edit = _current_edit()
        if edit is None:
            return
        selected = [item_to_konto.get(iid, "") for iid in accounts_tree.selection()]
        for konto in selected:
            if konto and konto not in edit.excluded_accounts:
                edit.excluded_accounts.append(konto)
        _rebuild_accounts_tree(edit)
        _refresh_rule_label_only()

    btn_scope_out.configure(command=_on_scope_out)

    def _on_include() -> None:
        edit = _current_edit()
        if edit is None:
            return
        selected = {item_to_konto.get(iid, "") for iid in accounts_tree.selection()}
        edit.excluded_accounts = [
            k for k in edit.excluded_accounts if k not in selected
        ]
        _rebuild_accounts_tree(edit)
        _refresh_rule_label_only()

    btn_include.configure(command=_on_include)

    def _on_save() -> None:
        unset = [idx for idx, edit in enumerate(rules) if edit.target_regnr is None]
        if unset:
            messagebox.showwarning(
                "Uvalgt motpost",
                "Én eller flere regler mangler motpost-regnskapslinje. "
                "Velg motpost for alle regler, eller slett de ubrukte.",
                parent=win,
            )
            try:
                rules_list.selection_clear(0, tk.END)
                rules_list.selection_set(unset[0])
                _on_rule_selected()
            except Exception:
                pass
            return
        rule_regnrs = {int(edit.target_regnr) for edit in rules}
        orphan_pair = next(
            (p for p in balance_pairs_state if p.rl_a not in rule_regnrs or p.rl_b not in rule_regnrs),
            None,
        )
        if orphan_pair is not None:
            missing = [
                regnr_to_label.get(r, str(r))
                for r in (orphan_pair.rl_a, orphan_pair.rl_b)
                if r not in rule_regnrs
            ]
            messagebox.showwarning(
                "Utligningspar mangler regel",
                "Et utligningspar peker på en RL som ikke har en regel: "
                + ", ".join(missing)
                + ". Legg til regelen eller slett paret.",
                parent=win,
            )
            return
        result["value"] = ExpectedRuleSet(
            source_regnr=int(source_regnr),
            selected_direction=direction,
            rules=tuple(edit.to_rule() for edit in rules),
            balance_pairs=tuple(balance_pairs_state),
        )
        win.destroy()

    btn_ok.configure(command=_on_save)

    def _has_unsaved_changes() -> bool:
        try:
            current = tuple(
                edit.to_rule() for edit in rules if edit.target_regnr is not None
            )
        except Exception:
            return True
        has_unset = any(edit.target_regnr is None for edit in rules)
        initial_rules = tuple(rule_set.rules)
        initial_pairs = tuple(getattr(rule_set, "balance_pairs", ()) or ())
        current_pairs = tuple(balance_pairs_state)
        return (
            has_unset
            or current != initial_rules
            or current_pairs != initial_pairs
        )

    def _on_cancel() -> None:
        if not _has_unsaved_changes():
            win.destroy()
            return
        answer = messagebox.askyesnocancel(
            "Lagre endringer?",
            "Du har ulagrede endringer i forventningsreglene. "
            "Vil du lagre før du lukker?",
            parent=win,
        )
        if answer is None:
            return
        if answer:
            _on_save()
        else:
            win.destroy()

    btn_cancel.configure(command=_on_cancel)
    try:
        win.protocol("WM_DELETE_WINDOW", _on_cancel)
    except Exception:
        pass

    _refresh_rules_list(select_idx=0 if rules else None)
    _refresh_pairs_list()

    win.wait_window()
    return result["value"]

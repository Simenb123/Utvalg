"""Draft and preview helpers for elimination workflow."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:  # pragma: no cover
    tk = None  # type: ignore

import pandas as pd

from ..backend import storage
from ..backend.models import EliminationJournal, EliminationLine

if TYPE_CHECKING:
    from .page import ConsolidationPage

logger = logging.getLogger(__name__)


def _reset_sort_state(tree) -> None:
    if hasattr(tree, "_sort_state"):
        tree._sort_state.last_col = None
        tree._sort_state.descending = False


def _fmt_no(value: float, decimals: int = 0) -> str:
    if abs(value) < 0.005 and decimals == 0:
        return "0"
    sign = "-" if value < 0 else ""
    formatted = f"{abs(value):,.{decimals}f}" if decimals > 0 else f"{round(abs(value)):,}"
    return sign + formatted.replace(",", " ").replace(".", ",")


def _parse_regnr_from_combo(val: str) -> int | None:
    if not val:
        return None
    try:
        return int(val.split(" - ")[0])
    except (ValueError, IndexError):
        return None


def _parse_konto_from_combo(val: str) -> str:
    if not val:
        return ""
    return val.split(" - ")[0].strip()


def get_sum_foer_elim(page: "ConsolidationPage", regnr: int) -> float | None:
    df = page._consolidated_result_df
    if df is None or "sum_foer_elim" not in df.columns:
        return None
    match = df[df["regnr"] == regnr]
    if match.empty:
        return None
    return float(match.iloc[0]["sum_foer_elim"])


def compute_preview(page: "ConsolidationPage", draft_lines: list[EliminationLine]) -> None:
    if page._consolidated_result_df is None or not draft_lines:
        page._clear_preview()
        return

    from ..backend.elimination import aggregate_eliminations_by_regnr

    preview_journal = EliminationJournal(name="Preview", lines=draft_lines)
    preview_by_regnr = aggregate_eliminations_by_regnr([preview_journal])

    df = page._consolidated_result_df.copy()
    df["preview_elim"] = df["regnr"].map(lambda r: preview_by_regnr.get(int(r), 0.0))
    df.loc[df["sumpost"], "preview_elim"] = 0.0

    leaf = ~df["sumpost"]
    df.loc[leaf, "konsolidert"] = (
        df.loc[leaf, "sum_foer_elim"]
        + df.loc[leaf, "eliminering"]
        + df.loc[leaf, "preview_elim"]
    )

    try:
        from ..backend.mapping import load_shared_config
        from regnskap_mapping import compute_sumlinjer

        _, regnskapslinjer = load_shared_config()
        for col in ("preview_elim", "konsolidert"):
            base_values = {
                int(r): float(v)
                for r, v in zip(df.loc[leaf, "regnr"], df.loc[leaf, col])
            }
            all_values = compute_sumlinjer(
                base_values=base_values,
                regnskapslinjer=regnskapslinjer,
            )
            sum_mask = df["sumpost"]
            df.loc[sum_mask, col] = df.loc[sum_mask, "regnr"].map(
                lambda r, av=all_values: float(av.get(int(r), 0.0))
            )
    except Exception:
        logger.debug("Could not recompute sumlinjer for preview", exc_info=True)

    page._preview_result_df = df
    page._result_mode_var.set("Konsolidert")
    page._refresh_result_view()


def clear_preview(page: "ConsolidationPage") -> None:
    page._preview_result_df = None
    page._preview_label_var.set("")
    page._refresh_result_view()


def populate_elim_combos(page: "ConsolidationPage") -> None:
    if page._regnskapslinjer is None:
        return
    rl = page._regnskapslinjer
    leaf = rl[~rl["sumpost"]]
    items = []
    for _, row in leaf.iterrows():
        rn = int(row["regnr"])
        name = str(row["regnskapslinje"])
        items.append(f"{rn} - {name}")
    page._elim_rl_items = items

    konto_items: list[str] = []
    konto_set: set[str] = set()
    for _cid, tb in (page._company_tbs or {}).items():
        if tb is None or tb.empty or "konto" not in tb.columns:
            continue
        for _, row in tb.iterrows():
            konto = str(row.get("konto") or "").strip()
            if not konto or konto in konto_set:
                continue
            konto_set.add(konto)
            name = str(row.get("kontonavn") or "").strip()
            konto_items.append(f"{konto} - {name}" if name else konto)
    konto_items.sort()
    page._elim_konto_items = konto_items
    _apply_elim_combo_level(page)


def _apply_elim_combo_level(page: "ConsolidationPage") -> None:
    level = getattr(page, "_elim_level_var", None)
    if level is None:
        return
    if level.get() == "konto":
        page._elim_cb_rl["values"] = getattr(page, "_elim_konto_items", [])
    else:
        page._elim_cb_rl["values"] = getattr(page, "_elim_rl_items", [])


def on_elim_level_changed(page: "ConsolidationPage") -> None:
    _apply_elim_combo_level(page)
    page._elim_line_var.set("")
    page._elim_line_sum_var.set("")


def on_elim_line_selected(page: "ConsolidationPage") -> None:
    rn = _parse_regnr_from_combo(page._elim_line_var.get())
    if rn is not None:
        amt = get_sum_foer_elim(page, rn)
        page._elim_line_sum_var.set(
            f"Sum: {_fmt_no(amt)}" if amt is not None else "(kjør konsolidering først)"
        )
        if amt is not None and not page._elim_amount_var.get().strip():
            neg = -amt
            page._elim_amount_var.set(str(round(neg, 2)))
            if hasattr(page, "_elim_amount_entry"):
                page._elim_amount_entry.focus_set()
                page._elim_amount_entry.select_range(0, "end")
    else:
        page._elim_line_sum_var.set("")


def on_elim_combo_filter(page: "ConsolidationPage", event=None) -> None:
    if not hasattr(page, "_elim_rl_items"):
        return
    typed = page._elim_line_var.get().strip().lower()
    if not typed:
        page._elim_cb_rl["values"] = page._elim_rl_items
        return
    page._elim_cb_rl["values"] = [item for item in page._elim_rl_items if typed in item.lower()]


def ensure_elim_draft_voucher_no(page: "ConsolidationPage") -> int:
    raw_no = int(getattr(page, "_draft_voucher_no", 0) or 0)
    if raw_no > 0:
        return raw_no
    proj = getattr(page, "_project", None)
    next_no = proj.next_elimination_voucher_no() if proj is not None else 1
    page._draft_voucher_no = next_no
    return next_no


def update_elim_draft_header(page: "ConsolidationPage") -> None:
    voucher_no = page._ensure_elim_draft_voucher_no()
    source_journal_id = str(getattr(page, "_draft_source_journal_id", "") or "").strip()
    editing = bool(source_journal_id)

    if hasattr(page, "_elim_voucher_var"):
        page._elim_voucher_var.set(f"Bilag nr: {voucher_no}")
    if hasattr(page, "_elim_mode_var"):
        page._elim_mode_var.set(f"Redigerer bilag {voucher_no}" if editing else "Nytt bilag")
    if hasattr(page, "_elim_save_btn_var"):
        page._elim_save_btn_var.set("Lagre endringer" if editing else "Opprett bilag")


def begin_new_elim_draft(page: "ConsolidationPage", reset_inputs: bool = True) -> None:
    proj = getattr(page, "_project", None)
    page._draft_source_journal_id = None
    page._draft_voucher_no = proj.next_elimination_voucher_no() if proj is not None else 1
    page._draft_lines.clear()
    page._draft_edit_idx = None
    if reset_inputs:
        if hasattr(page, "_elim_line_var"):
            page._elim_line_var.set("")
        if hasattr(page, "_elim_amount_var"):
            page._elim_amount_var.set("")
        if hasattr(page, "_elim_line_desc_var"):
            page._elim_line_desc_var.set("")
        if hasattr(page, "_elim_line_sum_var"):
            page._elim_line_sum_var.set("")
    page._refresh_draft_tree()
    try:
        page._tree_simple_elims.selection_remove(page._tree_simple_elims.selection())
    except Exception:
        pass
    if hasattr(page, "_elim_nb") and hasattr(page, "_elim_tab_simple"):
        try:
            page._elim_nb.select(page._elim_tab_simple)
        except Exception:
            pass


def load_journal_into_draft(page: "ConsolidationPage", journal: EliminationJournal, *, copy_mode: bool) -> None:
    proj = getattr(page, "_project", None)
    page._draft_lines.clear()
    page._draft_edit_idx = None
    for line in journal.lines:
        konto = str(getattr(line, "konto", "") or "")
        page._draft_lines.append({
            "regnr": line.regnr,
            "name": page._regnr_to_name.get(line.regnr, ""),
            "amount": line.amount,
            "desc": line.description,
            "konto": konto,
        })
    page._draft_source_journal_id = None if copy_mode else journal.journal_id
    if copy_mode:
        page._draft_voucher_no = proj.next_elimination_voucher_no() if proj is not None else 1
    else:
        page._draft_voucher_no = int(journal.voucher_no or 0) or page._ensure_elim_draft_voucher_no()
    page._elim_amount_var.set("")
    page._elim_line_desc_var.set("")
    page._refresh_draft_tree()
    if hasattr(page, "_elim_nb") and hasattr(page, "_elim_tab_simple"):
        try:
            page._elim_nb.select(page._elim_tab_simple)
        except Exception:
            pass
    if hasattr(page, "_elim_amount_entry"):
        page._elim_amount_entry.focus_set()


def _resolve_regnr_for_konto(page: "ConsolidationPage", konto: str) -> int | None:
    for _cid, tb in (getattr(page, "_mapped_tbs", None) or {}).items():
        if tb is None or tb.empty or "konto" not in tb.columns:
            continue
        match = tb[tb["konto"].astype(str).str.strip() == konto]
        if not match.empty:
            rn = match.iloc[0].get("regnr")
            if pd.notna(rn):
                return int(rn)
    return None


def on_draft_add_line(page: "ConsolidationPage") -> None:
    level = getattr(page, "_elim_level_var", None)
    is_konto = level is not None and level.get() == "konto"

    if is_konto:
        konto = _parse_konto_from_combo(page._elim_line_var.get())
        if not konto:
            messagebox.showwarning("Eliminering", "Velg en konto.")
            return
        rn = _resolve_regnr_for_konto(page, konto)
    else:
        konto = ""
        rn = _parse_regnr_from_combo(page._elim_line_var.get())
        if rn is None:
            messagebox.showwarning("Eliminering", "Velg en regnskapslinje.")
            return

    raw = page._elim_amount_var.get().strip().replace(",", ".").replace(" ", "")
    try:
        amount = float(raw)
    except ValueError:
        messagebox.showwarning("Eliminering", "Ugyldig beløp.")
        return
    if abs(amount) < 0.005:
        messagebox.showwarning("Eliminering", "Beløpet må være forskjellig fra null.")
        return

    if is_konto:
        combo_text = page._elim_line_var.get()
        name = combo_text.split(" - ", 1)[1] if " - " in combo_text else konto
    else:
        name = page._regnr_to_name.get(rn, str(rn))
    line_desc = page._elim_line_desc_var.get().strip()
    entry = {"regnr": rn or 0, "name": name, "amount": amount, "desc": line_desc, "konto": konto}

    if page._draft_edit_idx is not None:
        page._draft_lines[page._draft_edit_idx] = entry
        page._draft_edit_idx = None
    else:
        page._draft_lines.append(entry)

    page._refresh_draft_tree()
    page._elim_amount_var.set("")
    page._elim_line_desc_var.set("")
    if hasattr(page, "_elim_amount_entry"):
        page._elim_amount_entry.focus_set()


def on_draft_edit_line(page: "ConsolidationPage") -> None:
    sel = page._tree_draft_lines.selection()
    if not sel:
        return
    idx = int(sel[0])
    if idx < 0 or idx >= len(page._draft_lines):
        return
    line = page._draft_lines[idx]
    page._draft_edit_idx = idx

    combo_val = f"{line['regnr']} - {line['name']}"
    if combo_val in (page._elim_cb_rl["values"] or []):
        page._elim_line_var.set(combo_val)
    else:
        page._elim_line_var.set("")
    page._elim_amount_var.set(str(line["amount"]))
    page._elim_line_desc_var.set(line.get("desc", ""))
    page._on_elim_line_selected()


def on_draft_remove_line(page: "ConsolidationPage") -> None:
    sel = page._tree_draft_lines.selection()
    if not sel:
        return
    idx = int(sel[0])
    if 0 <= idx < len(page._draft_lines):
        page._draft_lines.pop(idx)
    page._draft_edit_idx = None
    page._refresh_draft_tree()


def on_draft_clear(page: "ConsolidationPage") -> None:
    page._draft_lines.clear()
    page._draft_edit_idx = None
    if hasattr(page, "_elim_amount_var"):
        page._elim_amount_var.set("")
    if hasattr(page, "_elim_line_desc_var"):
        page._elim_line_desc_var.set("")
    if hasattr(page, "_elim_line_sum_var"):
        page._elim_line_sum_var.set("")
    page._refresh_draft_tree()


def refresh_draft_tree(page: "ConsolidationPage") -> None:
    tree = page._tree_draft_lines
    _reset_sort_state(tree)
    tree.delete(*tree.get_children())
    for i, line in enumerate(page._draft_lines):
        amt = line["amount"]
        debet = _fmt_no(amt, 2) if amt > 0 else ""
        kredit = _fmt_no(abs(amt), 2) if amt < 0 else ""
        konto = line.get("konto", "")
        regnr_display = f"{line['regnr']} (kto {konto})" if konto else str(line["regnr"])
        tree.insert("", "end", iid=str(i), values=(regnr_display, line["name"], debet, kredit, line.get("desc", "")))

    sum_debet = sum(d["amount"] for d in page._draft_lines if d["amount"] > 0)
    sum_kredit = sum(abs(d["amount"]) for d in page._draft_lines if d["amount"] < 0)
    diff = sum_debet - sum_kredit
    n = len(page._draft_lines)

    if n > 0:
        status = "Balansert" if abs(diff) < 0.005 else "Ubalansert"
        page._elim_ctrl_var.set(
            f"Sum debet: {_fmt_no(sum_debet, 2)}  |  Sum kredit: {_fmt_no(sum_kredit, 2)}  |  Diff: {_fmt_no(diff, 2)}  |  {status}"
        )
    else:
        page._elim_ctrl_var.set("")

    can_create = n >= 2 and abs(diff) < 0.005
    page._btn_create_elim.configure(state="normal" if can_create else "disabled")
    if n < 2:
        page._elim_create_hint_var.set("Legg til minst 2 linjer")
    elif abs(diff) >= 0.005:
        page._elim_create_hint_var.set("Journalen må balansere")
    else:
        page._elim_create_hint_var.set("")

    page._update_elim_draft_header()


def on_create_simple_elim(page: "ConsolidationPage") -> None:
    if len(page._draft_lines) < 2:
        return
    netto = sum(d["amount"] for d in page._draft_lines)
    if abs(netto) >= 0.005:
        return

    proj = page._ensure_project()
    voucher_no = int(getattr(page, "_draft_voucher_no", 0) or 0) or proj.next_elimination_voucher_no()
    lines = [
        EliminationLine(
            regnr=d["regnr"],
            amount=d["amount"],
            description=d.get("desc", ""),
            konto=d.get("konto", ""),
        )
        for d in page._draft_lines
    ]
    source_journal_id = str(getattr(page, "_draft_source_journal_id", "") or "").strip()
    journal = proj.find_journal(source_journal_id) if source_journal_id else None
    if journal is None:
        journal = EliminationJournal(
            voucher_no=voucher_no,
            name=f"Bilag {voucher_no}",
            kind="manual",
            lines=lines,
        )
        proj.eliminations.append(journal)
    else:
        journal.voucher_no = voucher_no
        journal.name = f"Bilag {voucher_no}"
        journal.kind = "manual"
        journal.lines = lines
    storage.save_project(proj)

    page._refresh_simple_elim_tree()
    page._refresh_journal_tree()
    try:
        page._tree_simple_elims.selection_set((journal.journal_id,))
        page._tree_simple_elims.focus(journal.journal_id)
        page._show_elim_detail(journal.journal_id)
    except Exception:
        pass
    try:
        page._tree_journals.selection_set((journal.journal_id,))
        page._tree_journals.focus(journal.journal_id)
        page._refresh_elim_lines(journal)
    except Exception:
        pass
    page._update_status()
    page._begin_new_elim_draft()
    page._clear_preview()
    page._rerun_consolidation()


def on_delete_simple_elim(page: "ConsolidationPage") -> None:
    sel = page._tree_simple_elims.selection()
    if not sel or page._project is None:
        return
    jid = sel[0]
    journal = page._project.find_journal(jid)
    if journal is None:
        return
    if bool(getattr(journal, "locked", False)):
        messagebox.showinfo("Låst journal", "EK-journaler må endres fra Tilknyttede-fanen.")
        return
    if not messagebox.askyesno("Slett bilag", f"Slett '{journal.display_label}'?"):
        return
    page._project.eliminations.remove(journal)
    storage.save_project(page._project)
    page._refresh_simple_elim_tree()
    page._refresh_journal_tree()
    if getattr(page, "_draft_source_journal_id", None) == jid:
        page._begin_new_elim_draft()
    page._update_status()
    page._clear_preview()
    page._rerun_consolidation()

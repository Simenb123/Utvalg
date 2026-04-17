"""Elimination journal list, detail and CRUD helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog
except Exception:  # pragma: no cover
    tk = None  # type: ignore

from consolidation import storage
from consolidation.models import EliminationJournal, EliminationLine

if TYPE_CHECKING:
    from page_consolidation import ConsolidationPage


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


def refresh_journal_tree(page: "ConsolidationPage") -> None:
    tree = page._tree_journals
    _reset_sort_state(tree)
    _reset_sort_state(page._tree_elim_lines)
    tree.delete(*tree.get_children())
    page._tree_elim_lines.delete(*page._tree_elim_lines.get_children())
    page._elim_balance_var.set("")
    if hasattr(page, "_journal_meta_var"):
        page._journal_meta_var.set("")
    if page._project is None:
        return
    kind_labels = {"manual": "Manuell", "from_suggestion": "Forslag", "template": "Template", "equity_method": "EK-metode"}
    for j in page._project.eliminations:
        status_text = "Klar"
        if j.is_balanced:
            bal_text = "OK"
            tag = ("done",)
        else:
            bal_text = f"Ubalanse ({_fmt_no(j.net)})"
            tag = ("warning",)
        if j.kind == "template":
            tag = ("template",)
        if str(j.kind or "") == "equity_method":
            status_text = "Oppdatert"
            tag = ("locked",)
        if str(j.status or "").strip().lower() == "stale":
            status_text = "Utdatert"
            tag = ("stale",)
        elif str(j.status or "").strip().lower() == "draft":
            status_text = "Utkast"
        tree.insert(
            "",
            "end",
            iid=j.journal_id,
            values=(j.display_label, kind_labels.get(j.kind, j.kind), len(j.lines), status_text, bal_text),
            tags=tag,
        )


def refresh_elim_lines(page: "ConsolidationPage", journal: EliminationJournal) -> None:
    tree = page._tree_elim_lines
    tree.delete(*tree.get_children())
    name_map = {}
    if page._project:
        name_map = {c.company_id: c.name for c in page._project.companies}
    for i, line in enumerate(journal.lines):
        tree.insert(
            "",
            "end",
            iid=str(i),
            values=(line.regnr, name_map.get(line.company_id, line.company_id[:12]), _fmt_no(line.amount, 2), line.description),
        )
    if journal.is_balanced:
        page._elim_balance_var.set("Balansert")
    else:
        page._elim_balance_var.set(f"Netto: {_fmt_no(journal.net, 2)}")
    if hasattr(page, "_journal_meta_var"):
        if str(getattr(journal, "source_associate_case_id", "") or "").strip():
            page._journal_meta_var.set(f"Låst EK-journal | Status: {journal.status or 'active'}")
        else:
            page._journal_meta_var.set("")


def on_journal_select(page: "ConsolidationPage", _event=None) -> None:
    sel = page._tree_journals.selection()
    if not sel or page._project is None:
        return
    journal = page._project.find_journal(sel[0])
    if journal:
        page._refresh_elim_lines(journal)


def on_use_result_rl(page: "ConsolidationPage") -> None:
    sel = page._tree_result.selection()
    if not sel:
        messagebox.showinfo("Regnskapslinje", "Velg en regnskapslinje i Resultat-fanen først.")
        return
    vals = page._tree_result.item(sel[0], "values")
    if not vals:
        return
    try:
        regnr = int(vals[0])
    except (ValueError, TypeError):
        return
    target = None
    for item in getattr(page, "_elim_rl_items", []):
        if page._parse_regnr_from_combo(item) == regnr:
            target = item
            break
    if target:
        page._elim_line_var.set(target)
        page._on_elim_line_selected()


def show_elim_detail(page: "ConsolidationPage", journal_id: str) -> None:
    tree = page._tree_elim_detail
    tree.delete(*tree.get_children())
    if page._project is None:
        return
    journal = page._project.find_journal(journal_id)
    if journal is None:
        return
    for line in journal.lines:
        debet = _fmt_no(line.amount, 2) if line.amount > 0.005 else ""
        kredit = _fmt_no(abs(line.amount), 2) if line.amount < -0.005 else ""
        rl_name = page._regnr_to_name.get(line.regnr, "")
        tree.insert("", "end", values=(line.regnr, rl_name, debet, kredit, line.description))


def on_load_journal_to_draft(page: "ConsolidationPage") -> None:
    sel = page._tree_simple_elims.selection()
    if not sel or page._project is None:
        return
    journal = page._project.find_journal(sel[0])
    if journal is None:
        return
    if bool(getattr(journal, "locked", False)):
        messagebox.showinfo("Låst journal", "EK-journaler kan ikke lastes som redigerbart utkast.")
        return
    page._load_journal_into_draft(journal, copy_mode=False)


def on_copy_journal_to_draft(page: "ConsolidationPage") -> None:
    sel = page._tree_simple_elims.selection()
    if not sel or page._project is None:
        return
    journal = page._project.find_journal(sel[0])
    if journal is None:
        return
    if bool(getattr(journal, "locked", False)):
        messagebox.showinfo("Låst journal", "EK-journaler kan ikke kopieres til utkast herfra.")
        return
    page._load_journal_into_draft(journal, copy_mode=True)


def on_new_journal(page: "ConsolidationPage") -> None:
    page._begin_new_elim_draft()


def on_delete_journal(page: "ConsolidationPage") -> None:
    sel = page._tree_journals.selection()
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
    page._project.eliminations = [j for j in page._project.eliminations if j.journal_id != jid]
    storage.save_project(page._project)
    page._refresh_journal_tree()
    if getattr(page, "_draft_source_journal_id", None) == jid:
        page._begin_new_elim_draft()
    page._update_status()


def on_add_elim_line(page: "ConsolidationPage") -> None:
    sel = page._tree_journals.selection()
    if not sel or page._project is None:
        return
    journal = page._project.find_journal(sel[0])
    if journal is None:
        return
    if bool(getattr(journal, "locked", False)):
        messagebox.showinfo("Låst journal", "EK-journaler kan ikke redigeres linje for linje.")
        return

    company_names = {c.company_id: c.name for c in page._project.companies}
    if not company_names:
        messagebox.showwarning("Ingen selskaper", "Importer minst ett selskap først.")
        return

    company_hint = ", ".join(company_names.values())
    raw = simpledialog.askstring(
        "Ny elimineringslinje",
        f"Regnr ; Beløp ; Selskap ; Beskrivelse\nSelskaper: {company_hint}\nEksempel: 3000 ; -500000 ; {list(company_names.values())[0]} ; Interco salg",
    )
    if not raw:
        return

    parts = [p.strip() for p in raw.split(";")]
    if len(parts) < 2:
        messagebox.showerror("Feil", "Skriv minst: regnr ; beløp")
        return

    try:
        regnr = int(parts[0])
    except ValueError:
        messagebox.showerror("Feil", "Regnr må være et heltall.")
        return

    try:
        amount = float(parts[1].replace(",", ".").replace(" ", ""))
    except ValueError:
        messagebox.showerror("Feil", "Ugyldig beløp.")
        return

    company_id = list(company_names.keys())[0]
    if len(parts) >= 3 and parts[2]:
        needle = parts[2].lower()
        for cid, cname in company_names.items():
            if needle in cname.lower() or needle in cid.lower():
                company_id = cid
                break

    desc = parts[3] if len(parts) >= 4 else ""
    journal.lines.append(EliminationLine(regnr=regnr, company_id=company_id, amount=amount, description=desc))
    storage.save_project(page._project)
    page._refresh_journal_tree()
    page._refresh_elim_lines(journal)


def on_delete_elim_line(page: "ConsolidationPage") -> None:
    sel_j = page._tree_journals.selection()
    sel_l = page._tree_elim_lines.selection()
    if not sel_j or not sel_l or page._project is None:
        return
    journal = page._project.find_journal(sel_j[0])
    if journal is None:
        return
    if bool(getattr(journal, "locked", False)):
        messagebox.showinfo("Låst journal", "EK-journaler kan ikke redigeres linje for linje.")
        return
    try:
        idx = int(sel_l[0])
        if 0 <= idx < len(journal.lines):
            journal.lines.pop(idx)
            storage.save_project(page._project)
            page._refresh_journal_tree()
            page._refresh_elim_lines(journal)
    except (ValueError, IndexError):
        pass


def refresh_simple_elim_tree(page: "ConsolidationPage") -> None:
    tree = page._tree_simple_elims
    _reset_sort_state(tree)
    _reset_sort_state(page._tree_elim_detail)
    tree.delete(*tree.get_children())
    if hasattr(page, "_tree_elim_detail"):
        page._tree_elim_detail.delete(*page._tree_elim_detail.get_children())
    if page._project is None:
        return
    last_jid = None
    for j in page._project.eliminations:
        diff = j.total_debet - j.total_kredit
        status = "Balansert" if j.is_balanced else "Ubalansert"
        tags = ("balanced",) if j.is_balanced else ("unbalanced",)
        tree.insert(
            "",
            "end",
            iid=j.journal_id,
            values=(j.display_label, len(j.lines), _fmt_no(j.total_debet, 2), _fmt_no(j.total_kredit, 2), _fmt_no(diff, 2), status),
            tags=tags,
        )
        last_jid = j.journal_id
    if last_jid:
        tree.selection_set(last_jid)
        page._show_elim_detail(last_jid)


def on_simple_elim_selected(page: "ConsolidationPage", _event=None) -> None:
    sel = page._tree_simple_elims.selection()
    if not sel or page._project is None:
        if hasattr(page, "_tree_elim_detail"):
            page._tree_elim_detail.delete(*page._tree_elim_detail.get_children())
        return
    page._show_elim_detail(sel[0])

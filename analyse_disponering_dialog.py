"""Enkel disponeringsdialog for ÅO på enkeltselskapsnivå."""

from __future__ import annotations

from typing import Any

import pandas as pd

import analyse_disposition_service
import formatting
import regnskap_client_overrides


def open_dialog(
    parent: Any,
    *,
    client: str,
    year: str,
    hb_df: pd.DataFrame | None,
    effective_sb_df: pd.DataFrame | None,
    intervals: pd.DataFrame | None,
    regnskapslinjer: pd.DataFrame | None,
    account_overrides: dict[str, int] | None = None,
    on_changed: Any = None,
) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception:
        return

    if not client or not year:
        return

    try:
        summary = analyse_disposition_service.build_disposition_summary(
            hb_df=hb_df,
            effective_sb_df=effective_sb_df,
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )
    except Exception as exc:
        messagebox.showerror(
            "Disponering via ÅO",
            f"Kunne ikke beregne disponeringsstatus.\n\n{exc}",
            parent=parent,
        )
        return

    account_lookup = analyse_disposition_service.build_account_name_lookup(
        hb_df=hb_df,
        effective_sb_df=effective_sb_df,
    )

    dlg = tk.Toplevel(parent)
    dlg.title(f"Disponering via ÅO — {client} ({year})")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.minsize(980, 520)

    state: dict[str, Any] = {
        "draft": [],
        "edit_index": None,
    }

    var_bilag = tk.StringVar(value="ÅODISP")
    var_konto = tk.StringVar(value="")
    var_belop = tk.StringVar(value="")
    var_beskrivelse = tk.StringVar(value="")
    var_line_hint = tk.StringVar(value="Velg konto og beløp for å legge til en disponeringslinje.")
    var_summary = tk.StringVar(value="")

    ttk.Label(
        dlg,
        text=(
            "Dette oppretter vanlige ÅO-linjer på kontonivå. "
            "Regnskapslinje vises kun som kontroll, slik at sporbarheten beholdes."
        ),
        wraplength=920,
        justify="left",
    ).pack(fill="x", padx=10, pady=(10, 6))

    top = ttk.Frame(dlg)
    top.pack(fill="x", padx=10)
    for col in range(6):
        top.columnconfigure(col, weight=1 if col % 2 else 0)

    ttk.Label(top, text="Årsresultat (280):").grid(row=0, column=0, sticky="w")
    ttk.Label(top, text=formatting.fmt_amount(summary.arsresultat)).grid(row=0, column=1, sticky="w", padx=(4, 18))
    ttk.Label(top, text="Sum overføringer (350):").grid(row=0, column=2, sticky="w")
    ttk.Label(top, text=formatting.fmt_amount(summary.sum_overforinger)).grid(row=0, column=3, sticky="w", padx=(4, 18))
    ttk.Label(top, text="Rest å disponere:").grid(row=0, column=4, sticky="w")
    lbl_rest = ttk.Label(top, text=formatting.fmt_amount(summary.rest_a_disponere))
    lbl_rest.grid(row=0, column=5, sticky="w", padx=(4, 0))

    ttk.Label(top, text="Avsatt til utbytte (295):").grid(row=1, column=0, sticky="w", pady=(6, 0))
    ttk.Label(top, text=formatting.fmt_amount(summary.line_295)).grid(row=1, column=1, sticky="w", padx=(4, 18), pady=(6, 0))
    ttk.Label(top, text="Avsatt til annen EK (320):").grid(row=1, column=2, sticky="w", pady=(6, 0))
    ttk.Label(top, text=formatting.fmt_amount(summary.line_320)).grid(row=1, column=3, sticky="w", padx=(4, 18), pady=(6, 0))

    form = ttk.LabelFrame(dlg, text="Ny disponeringslinje")
    form.pack(fill="x", padx=10, pady=(10, 6))
    for col in range(7):
        form.columnconfigure(col, weight=1 if col in {1, 5} else 0)

    ttk.Label(form, text="Bilag:").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=(8, 4))
    ent_bilag = ttk.Entry(form, textvariable=var_bilag, width=12)
    ent_bilag.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(8, 4))

    ttk.Label(form, text="Konto:").grid(row=0, column=2, sticky="w", padx=(0, 4), pady=(8, 4))
    ent_konto = ttk.Entry(form, textvariable=var_konto, width=12)
    ent_konto.grid(row=0, column=3, sticky="w", padx=(0, 12), pady=(8, 4))

    ttk.Label(form, text="Beløp:").grid(row=0, column=4, sticky="w", padx=(0, 4), pady=(8, 4))
    ent_belop = ttk.Entry(form, textvariable=var_belop, width=16)
    ent_belop.grid(row=0, column=5, sticky="w", padx=(0, 12), pady=(8, 4))
    ttk.Label(form, text="positiv = debet, negativ = kredit", style="Muted.TLabel").grid(
        row=0, column=6, sticky="w", padx=(0, 8), pady=(8, 4)
    )

    ttk.Label(form, text="Beskrivelse:").grid(row=1, column=0, sticky="w", padx=(8, 4), pady=(0, 8))
    ent_beskrivelse = ttk.Entry(form, textvariable=var_beskrivelse)
    ent_beskrivelse.grid(row=1, column=1, columnspan=5, sticky="ew", padx=(0, 12), pady=(0, 8))

    lbl_hint = ttk.Label(form, textvariable=var_line_hint, style="Muted.TLabel", wraplength=900)
    lbl_hint.grid(row=2, column=0, columnspan=7, sticky="w", padx=8, pady=(0, 8))

    btn_row = ttk.Frame(form)
    btn_row.grid(row=3, column=0, columnspan=7, sticky="w", padx=8, pady=(0, 8))

    tree_frame = ttk.Frame(dlg)
    tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 4))
    cols = ("Bilag", "Konto", "Kontonavn", "Debet", "Kredit", "Regnr", "Regnskapslinje", "Beskrivelse")
    tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse", height=10)
    tree.grid(row=0, column=0, sticky="nsew")
    y_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    y_scroll.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=y_scroll.set)
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)

    widths = {
        "Bilag": 90,
        "Konto": 90,
        "Kontonavn": 170,
        "Debet": 110,
        "Kredit": 110,
        "Regnr": 70,
        "Regnskapslinje": 180,
        "Beskrivelse": 220,
    }
    anchors = {"Debet": "e", "Kredit": "e", "Regnr": "e"}
    for col in cols:
        tree.heading(col, text=col)
        tree.column(col, width=widths[col], anchor=anchors.get(col, "w"), stretch=(col in {"Kontonavn", "Regnskapslinje", "Beskrivelse"}))

    tree.tag_configure("invalid", foreground="#9C1C1C")

    bottom = ttk.Frame(dlg)
    bottom.pack(fill="x", padx=10, pady=(2, 10))
    ttk.Label(bottom, textvariable=var_summary).pack(side="left")
    btn_save = ttk.Button(bottom, text="Lagre som ÅO")
    btn_save.pack(side="right", padx=(6, 0))
    ttk.Button(bottom, text="Avbryt", command=dlg.destroy).pack(side="right")

    def _parse_amount(raw: str) -> float:
        text = str(raw or "").strip().replace("\u00a0", "").replace(" ", "")
        if not text:
            return 0.0
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
        return float(text)

    def _selected_projection() -> analyse_disposition_service.DraftLineProjection:
        try:
            belop = _parse_amount(var_belop.get())
        except Exception:
            belop = 0.0
        return analyse_disposition_service.project_draft_line(
            konto=var_konto.get(),
            belop=belop,
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
            account_name_lookup=account_lookup,
        )

    def _set_form_from_projection() -> None:
        projection = _selected_projection()
        konto_text = projection.konto or "—"
        name_text = projection.kontonavn or "ukjent konto"
        if projection.regnr is None:
            var_line_hint.set(f"Konto {konto_text} ({name_text}) mangler regnskapslinje-mapping.")
        elif projection.mapping_status == "sumline":
            var_line_hint.set(
                f"Konto {konto_text} ({name_text}) treffer sumpost {projection.regnr} {projection.regnskapslinje}. "
                "Bruk en konto som treffer en vanlig regnskapslinje."
            )
        else:
            var_line_hint.set(
                f"Konto {konto_text} ({name_text}) treffer {projection.regnr} {projection.regnskapslinje}."
            )

    def _clear_form(*, keep_bilag: bool = True) -> None:
        if not keep_bilag:
            var_bilag.set("ÅODISP")
        var_konto.set("")
        var_belop.set("")
        var_beskrivelse.set("")
        state["edit_index"] = None
        var_line_hint.set("Velg konto og beløp for å legge til en disponeringslinje.")
        try:
            ent_konto.focus_set()
        except Exception:
            pass

    def _refresh_tree() -> None:
        for item in tree.get_children():
            tree.delete(item)

        draft_summary = analyse_disposition_service.summarize_draft(
            state["draft"],
            disposition_summary=summary,
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
            account_name_lookup=account_lookup,
        )

        for idx, entry in enumerate(state["draft"]):
            projection = analyse_disposition_service.project_draft_line(
                konto=str(entry.get("konto", "") or ""),
                belop=float(entry.get("belop", 0.0) or 0.0),
                intervals=intervals,
                regnskapslinjer=regnskapslinjer,
                account_overrides=account_overrides,
                account_name_lookup=account_lookup,
            )
            belop = projection.belop
            debet = formatting.fmt_amount(belop) if belop > 0 else ""
            kredit = formatting.fmt_amount(abs(belop)) if belop < 0 else ""
            tags = ("invalid",) if projection.mapping_status in {"unmapped", "sumline"} else ()
            tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    entry.get("bilag", ""),
                    projection.konto,
                    projection.kontonavn,
                    debet,
                    kredit,
                    "" if projection.regnr is None else str(projection.regnr),
                    projection.regnskapslinje,
                    entry.get("beskrivelse", ""),
                ),
                tags=tags,
            )

        rest_color = "#9C1C1C" if abs(draft_summary.rest_etter_utkast) > 0.005 else "#1B5E20"
        try:
            lbl_rest.configure(foreground=rest_color)
        except Exception:
            pass

        diff_txt = formatting.fmt_amount(draft_summary.diff)
        rest_txt = formatting.fmt_amount(draft_summary.rest_etter_utkast)
        transfer_txt = formatting.fmt_amount(draft_summary.transfer_effect)
        flags = []
        if abs(draft_summary.diff) > 0.005:
            flags.append("Ubalansert utkast")
        if draft_summary.has_invalid_lines:
            flags.append("Ugyldig mapping i utkast")
        status_suffix = f" | {' | '.join(flags)}" if flags else ""
        var_summary.set(
            "Sum debet: "
            f"{formatting.fmt_amount(draft_summary.debet)} | "
            f"Sum kredit: {formatting.fmt_amount(draft_summary.kredit)} | "
            f"Diff: {diff_txt} | "
            f"Treffer overføringer: {transfer_txt} | "
            f"Rest etter utkast: {rest_txt}{status_suffix}"
        )
        save_enabled = (
            len(state["draft"]) >= 2
            and abs(draft_summary.diff) <= 0.005
            and not draft_summary.has_invalid_lines
        )
        try:
            btn_save.state(["!disabled"] if save_enabled else ["disabled"])
        except Exception:
            pass

    def _store_form() -> None:
        konto = str(var_konto.get() or "").strip()
        beskrivelse = str(var_beskrivelse.get() or "").strip()
        bilag = str(var_bilag.get() or "").strip() or "ÅODISP"
        if not konto:
            messagebox.showwarning("Disponering via ÅO", "Konto må fylles ut.", parent=dlg)
            return
        try:
            belop = _parse_amount(var_belop.get())
        except Exception:
            messagebox.showwarning("Disponering via ÅO", "Beløp er ikke gyldig.", parent=dlg)
            return
        if abs(belop) <= 0.005:
            messagebox.showwarning("Disponering via ÅO", "Beløp må være forskjellig fra 0.", parent=dlg)
            return

        entry = {
            "bilag": bilag,
            "konto": konto,
            "belop": belop,
            "beskrivelse": beskrivelse,
        }
        edit_index = state.get("edit_index")
        if edit_index is None:
            state["draft"].append(entry)
        else:
            state["draft"][int(edit_index)] = entry
        _refresh_tree()
        _clear_form()

    def _load_selected() -> None:
        sel = tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if not (0 <= idx < len(state["draft"])):
            return
        entry = state["draft"][idx]
        state["edit_index"] = idx
        var_bilag.set(str(entry.get("bilag", "") or "ÅODISP"))
        var_konto.set(str(entry.get("konto", "") or ""))
        var_belop.set(formatting.fmt_amount(float(entry.get("belop", 0.0) or 0.0)).replace("\u00a0", " "))
        var_beskrivelse.set(str(entry.get("beskrivelse", "") or ""))
        _set_form_from_projection()
        try:
            ent_belop.focus_set()
        except Exception:
            pass

    def _delete_selected() -> None:
        sel = tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(state["draft"]):
            state["draft"].pop(idx)
        _refresh_tree()
        _clear_form()

    def _save_and_close() -> None:
        draft_summary = analyse_disposition_service.summarize_draft(
            state["draft"],
            disposition_summary=summary,
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
            account_name_lookup=account_lookup,
        )
        if len(state["draft"]) < 2:
            messagebox.showwarning("Disponering via ÅO", "Legg til minst 2 linjer.", parent=dlg)
            return
        if abs(draft_summary.diff) > 0.005:
            messagebox.showwarning("Disponering via ÅO", "Utkastet balanserer ikke.", parent=dlg)
            return
        if draft_summary.has_invalid_lines:
            messagebox.showwarning(
                "Disponering via ÅO",
                "Minst én linje mangler gyldig regnskapslinje-mapping.",
                parent=dlg,
            )
            return

        existing = regnskap_client_overrides.load_supplementary_entries(client, year)
        regnskap_client_overrides.save_supplementary_entries(client, year, [*existing, *state["draft"]])
        if callable(on_changed):
            on_changed()
        dlg.destroy()

    ttk.Button(btn_row, text="Legg til linje", command=_store_form).pack(side="left", padx=(0, 4))
    ttk.Button(btn_row, text="Rediger valgt", command=_load_selected).pack(side="left", padx=(0, 4))
    ttk.Button(btn_row, text="Fjern valgt", command=_delete_selected).pack(side="left", padx=(0, 4))
    ttk.Button(btn_row, text="Nullstill utkast", command=lambda: (state["draft"].clear(), _refresh_tree(), _clear_form())).pack(side="left")

    btn_save.configure(command=_save_and_close)

    ent_konto.bind("<FocusOut>", lambda _e: _set_form_from_projection())
    ent_belop.bind("<FocusOut>", lambda _e: _set_form_from_projection())
    ent_konto.bind("<Return>", lambda _e: (ent_belop.focus_set(), "break"))
    ent_belop.bind("<Return>", lambda _e: (_store_form(), "break"))
    ent_beskrivelse.bind("<Return>", lambda _e: (_store_form(), "break"))
    tree.bind("<Double-1>", lambda _e: _load_selected())
    tree.bind("<Delete>", lambda _e: _delete_selected())

    _refresh_tree()

    dlg.update_idletasks()
    w = max(dlg.winfo_width(), 980)
    h = max(dlg.winfo_height(), 520)
    x = parent.winfo_rootx() + max((parent.winfo_width() - w) // 2, 0)
    y = parent.winfo_rooty() + max((parent.winfo_height() - h) // 2, 0)
    dlg.geometry(f"{w}x{h}+{x}+{y}")

    try:
        ent_konto.focus_set()
    except Exception:
        pass

"""page_consolidation_result.py - result view implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from page_consolidation import ConsolidationPage

logger = logging.getLogger(__name__)


def _reset_sort_state(tree) -> None:
    if hasattr(tree, "_sort_state"):
        tree._sort_state.last_col = None
        tree._sort_state.descending = False


def build_company_result(page: "ConsolidationPage", company_id: str) -> None:
    mapped_tb = page._mapped_tbs.get(company_id)
    if mapped_tb is None or page._regnskapslinjer is None:
        page._company_result_df = None
        return

    try:
        from regnskap_mapping import compute_sumlinjer

        rl = page._regnskapslinjer
        skeleton = rl[["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
        skeleton["regnr"] = skeleton["regnr"].astype(int)
        result = skeleton.copy()
        leaf_mask = ~result["sumpost"]

        valid = mapped_tb.dropna(subset=["regnr"]).copy()
        if valid.empty:
            page._company_result_df = None
            return
        valid["regnr"] = valid["regnr"].astype(int)
        agg_before = valid.groupby("regnr")["ub"].sum().to_dict()

        agg_after: dict[int, float] = {}
        agg_kurs: dict[int, float] = {}
        run = getattr(page, "_last_run_result", None)
        proj = getattr(page, "_project", None)
        if run and run.account_details is not None and proj:
            company = proj.find_company(company_id)
            cname = company.name if company else ""
            co = run.account_details[run.account_details["selskap"] == cname].copy()
            co_valid = co.dropna(subset=["regnr"]).copy()
            if not co_valid.empty:
                co_valid["regnr"] = co_valid["regnr"].astype(int)
                agg_after = co_valid.groupby("regnr")["ub"].sum().to_dict()
                agg_kurs = co_valid.groupby("regnr")["kurs"].first().to_dict()

        if not agg_after:
            agg_after = dict(agg_before)
            agg_kurs = {r: 1.0 for r in agg_before}

        result["UB"] = result["regnr"].map(lambda r: agg_after.get(int(r), 0.0))
        result.loc[result["sumpost"], "UB"] = 0.0

        result["Før"] = result["regnr"].map(lambda r: agg_before.get(int(r), 0.0))
        result.loc[result["sumpost"], "Før"] = 0.0

        result["Kurs"] = result["regnr"].map(lambda r: agg_kurs.get(int(r), 1.0))

        result["Valutaeffekt"] = 0.0
        result.loc[leaf_mask, "Valutaeffekt"] = (
            result.loc[leaf_mask, "UB"] - result.loc[leaf_mask, "Før"]
        )

        for col in ["UB", "Før", "Valutaeffekt"]:
            base = {
                int(r): float(v)
                for r, v in zip(result.loc[leaf_mask, "regnr"], result.loc[leaf_mask, col])
            }
            all_v = compute_sumlinjer(base_values=base, regnskapslinjer=rl)
            sm = result["sumpost"]
            result.loc[sm, col] = result.loc[sm, "regnr"].map(
                lambda r, av=all_v: float(av.get(int(r), 0.0)),
            )

        result.loc[result["sumpost"], "Kurs"] = float("nan")
        page._company_result_df = result.sort_values("regnr").reset_index(drop=True)

    except Exception:
        logger.exception("Failed to build company result for %s", company_id)
        page._company_result_df = None


def on_result_mode_changed(page: "ConsolidationPage") -> None:
    page._refresh_result_view()


def fx_cols_active(page: "ConsolidationPage") -> tuple[bool, bool, bool]:
    before = getattr(page, "_col_before_var", None)
    kurs = getattr(page, "_col_kurs_var", None)
    effect = getattr(page, "_col_fx_effect_var", None)
    return (
        before.get() if before else False,
        kurs.get() if kurs else False,
        effect.get() if effect else False,
    )


def refresh_result_view(page: "ConsolidationPage") -> None:
    mode = page._result_mode_var.get()
    show_before, show_kurs, show_effect = page._fx_cols_active()

    if mode == "Konsolidert":
        if page._preview_result_df is not None:
            page._preview_label_var.set("Preview aktiv")
            page._populate_result_tree(
                page._preview_result_df,
                ["Mor", "Doetre", "eliminering", "preview_elim", "konsolidert"],
            )
        elif page._consolidated_result_df is not None:
            page._preview_label_var.set("")
            cols = ["Mor", "Doetre", "eliminering", "konsolidert"]
            page._populate_result_tree(page._consolidated_result_df, cols)
        else:
            page._show_empty_result("Ingen konsolidering kjørt ennå")
    elif mode == "Per selskap":
        if page._consolidated_result_df is not None:
            page._preview_label_var.set("")
            cols = page._get_per_company_columns()
            page._populate_result_tree(page._consolidated_result_df, cols)
        else:
            page._show_empty_result("Kjør konsolidering for å se per selskap")
    elif page._company_result_df is not None:
        cid = getattr(page, "_current_detail_cid", None)
        proj = getattr(page, "_project", None)
        company = proj.find_company(cid) if proj and cid else None
        reporting = (proj.reporting_currency or "NOK").upper() if proj else "NOK"
        ccur = (company.currency_code or "").upper() if company else ""
        has_fx = ccur and ccur != reporting
        page._preview_label_var.set(ccur if has_fx else "")

        cols = ["UB"]
        if show_before:
            cols.append("Før")
        if show_kurs:
            cols.append("Kurs")
        if show_effect:
            cols.append("Valutaeffekt")
        page._populate_result_tree(page._company_result_df, cols)
    else:
        page._show_empty_result("Velg et selskap eller kjør konsolidering")


def ensure_consolidated_fx_cols(
    page: "ConsolidationPage",
    *,
    show_before: bool,
    show_effect: bool,
) -> pd.DataFrame:
    df = page._consolidated_result_df
    if not show_before and not show_effect:
        return df
    run = getattr(page, "_last_run_result", None)
    proj = getattr(page, "_project", None)
    if run is None or run.account_details is None or proj is None:
        return df
    if page._regnskapslinjer is None:
        return df

    try:
        from regnskap_mapping import compute_sumlinjer

        ad = run.account_details.copy()
        ad_valid = ad.dropna(subset=["regnr"]).copy()
        ad_valid["regnr"] = ad_valid["regnr"].astype(int)

        parent_id = proj.parent_company_id or ""
        parent_name = ""
        child_names = []
        for company in proj.companies:
            if company.company_id == parent_id:
                parent_name = company.name
            else:
                child_names.append(company.name)

        rl = page._regnskapslinjer
        leaf_mask = ~df["sumpost"]
        result = df.copy()

        def _agg_before(names: list[str]) -> dict[int, float]:
            mask = ad_valid["selskap"].isin(names)
            return ad_valid.loc[mask].groupby("regnr")["ub_original"].sum().to_dict()

        def _fill_col(col_name: str, agg: dict[int, float]) -> None:
            result[col_name] = result["regnr"].map(lambda r: agg.get(int(r), 0.0))
            result.loc[result["sumpost"], col_name] = 0.0
            base = {
                int(r): float(v)
                for r, v in zip(result.loc[leaf_mask, "regnr"], result.loc[leaf_mask, col_name])
            }
            all_v = compute_sumlinjer(base_values=base, regnskapslinjer=rl)
            sm = result["sumpost"]
            result.loc[sm, col_name] = result.loc[sm, "regnr"].map(
                lambda r, av=all_v: float(av.get(int(r), 0.0)),
            )

        if show_before:
            _fill_col("Mor_foer", _agg_before([parent_name]) if parent_name else {})
            _fill_col("Doetre_foer", _agg_before(child_names) if child_names else {})

        if show_effect:
            if show_before:
                result["Mor_effekt"] = result["Mor"] - result.get("Mor_foer", 0.0)
                result["Doetre_effekt"] = result["Doetre"] - result.get("Doetre_foer", 0.0)
            else:
                mor_foer = _agg_before([parent_name]) if parent_name else {}
                doetre_foer = _agg_before(child_names) if child_names else {}
                result["Mor_effekt"] = result["regnr"].map(
                    lambda r: mor_foer.get(int(r), 0.0),
                )
                result.loc[leaf_mask, "Mor_effekt"] = (
                    result.loc[leaf_mask, "Mor"] - result.loc[leaf_mask, "Mor_effekt"]
                )
                result["Doetre_effekt"] = result["regnr"].map(
                    lambda r: doetre_foer.get(int(r), 0.0),
                )
                result.loc[leaf_mask, "Doetre_effekt"] = (
                    result.loc[leaf_mask, "Doetre"] - result.loc[leaf_mask, "Doetre_effekt"]
                )
                for ecol in ["Mor_effekt", "Doetre_effekt"]:
                    base = {
                        int(r): float(v)
                        for r, v in zip(result.loc[leaf_mask, "regnr"], result.loc[leaf_mask, ecol])
                    }
                    all_v = compute_sumlinjer(base_values=base, regnskapslinjer=rl)
                    sm = result["sumpost"]
                    result.loc[sm, ecol] = result.loc[sm, "regnr"].map(
                        lambda r, av=all_v: float(av.get(int(r), 0.0)),
                    )

        return result

    except Exception:
        logger.debug("Could not build FX columns for consolidated", exc_info=True)
        return df


def get_per_company_columns(
    page: "ConsolidationPage",
    df: pd.DataFrame | None = None,
) -> list[str]:
    if df is None:
        df = page._consolidated_result_df
    if page._project is None or df is None:
        return ["Mor", "Doetre", "eliminering", "konsolidert"]
    parent_id = page._project.parent_company_id or ""
    company_names = {}
    for company in sorted(page._project.companies, key=lambda item: item.company_id):
        company_names[company.company_id] = company.name
    parent_col = company_names.get(parent_id, "")
    cols: list[str] = []
    if parent_col and parent_col in df.columns:
        cols.append(parent_col)
    for cid, cname in company_names.items():
        if cid != parent_id and cname in df.columns:
            cols.append(cname)
    cols.extend(["eliminering", "konsolidert"])
    return cols


def show_empty_result(page: "ConsolidationPage", message: str = "") -> None:
    tree = page._tree_result
    tree.delete(*tree.get_children())
    page._preview_label_var.set("")
    default_cols = ("regnr", "regnskapslinje", "info")
    page._reset_result_tree_display_state()
    tree["columns"] = default_cols
    tree.heading("regnr", text="Regnr")
    tree.heading("regnskapslinje", text="Regnskapslinje")
    tree.heading("info", text="")
    tree.column("regnr", width=60, anchor="center")
    tree.column("regnskapslinje", width=200)
    tree.column("info", width=300)
    if message:
        tree.insert("", "end", values=("", "", message))


def reset_result_tree_display_state(page: "ConsolidationPage") -> None:
    tree = getattr(page, "_tree_result", None)
    if tree is None:
        return
    try:
        tree["displaycolumns"] = "#all"
    except Exception:
        pass


def populate_result_tree(
    page: "ConsolidationPage",
    result_df: pd.DataFrame,
    *,
    data_cols: list[str] | None = None,
    fmt_no,
    append_control_rows_fn,
    enable_treeview_sorting_fn,
    kurs_cols,
) -> None:
    _reset_sort_state(page._tree_result)
    if data_cols is not None:
        augmented = append_control_rows_fn(
            result_df,
            amount_cols=[c for c in data_cols if c not in kurs_cols],
        )
    else:
        augmented = append_control_rows_fn(result_df)
    if augmented is not None:
        result_df = augmented
    tree = page._tree_result
    tree.delete(*tree.get_children())

    meta_cols = {"regnr", "regnskapslinje", "sumpost", "formel"}
    if data_cols is None:
        data_cols = [c for c in result_df.columns if c not in meta_cols]
    data_cols = [c for c in data_cols if c in result_df.columns]
    all_cols = ["regnr", "regnskapslinje"] + data_cols

    col_labels = {
        "Mor": "Mor",
        "Doetre": "Døtre",
        "eliminering": "Eliminering",
        "konsolidert": "Konsolidert",
        "preview_elim": "Preview elim.",
        "Før": "Før omr.",
        "Kurs": "Kurs",
        "Valutaeffekt": "Val.effekt",
        "Mor_foer": "Mor før",
        "Mor_effekt": "Mor effekt",
        "Doetre_foer": "Døtre før",
        "Doetre_effekt": "Døtre effekt",
    }
    col_widths = {
        "Kurs": 60,
        "Valutaeffekt": 85,
        "Før": 90,
        "Mor_foer": 85,
        "Mor_effekt": 85,
        "Doetre_foer": 85,
        "Doetre_effekt": 85,
    }

    page._reset_result_tree_display_state()
    tree["columns"] = all_cols
    tree.heading("regnr", text="Nr")
    tree.heading("regnskapslinje", text="Regnskapslinje")
    tree.column("regnr", width=50, anchor="e")
    tree.column("regnskapslinje", width=160, anchor="w")
    for dc in data_cols:
        tree.heading(dc, text=col_labels.get(dc, dc))
        tree.column(dc, width=col_widths.get(dc, 100), anchor="e")

    hide_zero = page._hide_zero_var.get()
    amount_cols = [dc for dc in data_cols if dc not in kurs_cols]

    for _, row in result_df.iterrows():
        is_sum = bool(row.get("sumpost", False))
        if hide_zero and not is_sum:
            if all(
                abs(float(row.get(dc, 0.0)) if pd.notna(row.get(dc, 0.0)) else 0.0) < 0.005
                for dc in amount_cols
            ):
                continue

        vals: list[object] = [int(row["regnr"]), row["regnskapslinje"]]
        any_neg = False
        for dc in data_cols:
            value = row.get(dc, 0.0)
            if dc in kurs_cols:
                if is_sum or pd.isna(value):
                    vals.append("")
                else:
                    fv = float(value)
                    vals.append(fmt_no(fv, 4) if abs(fv - 1.0) > 0.0001 else "1")
            else:
                fv = float(value) if pd.notna(value) else 0.0
                vals.append(fmt_no(fv, 2))
                if fv < -0.005:
                    any_neg = True

        tags = []
        if is_sum:
            tags.append("sumline")
        if any_neg and not is_sum:
            tags.append("neg")
        tree.insert("", "end", values=vals, tags=tuple(tags))

    if enable_treeview_sorting_fn is not None:
        enable_treeview_sorting_fn(tree, columns=all_cols)

    if hasattr(page, "_result_col_mgr"):
        page._result_col_mgr.update_columns(all_cols)


def show_result(page: "ConsolidationPage", result_df: pd.DataFrame) -> None:
    page._consolidated_result_df = result_df
    page._preview_result_df = None
    page._preview_label_var.set("")
    cid = getattr(page, "_current_detail_cid", None)
    if cid:
        page._build_company_result(cid)
    page._result_mode_var.set("Konsolidert")
    page._refresh_result_view()
    page._select_right_tab(2, "_right_tab_result")


def ensure_consolidated_result(page: "ConsolidationPage") -> bool:
    if page._consolidated_result_df is not None:
        return True
    if page._project is None or not page._project.companies:
        return False
    if not page._company_tbs:
        return False
    page._on_run()
    return page._consolidated_result_df is not None


def on_show_unmapped(page: "ConsolidationPage") -> None:
    sel = page._tree_companies.selection()
    if not sel:
        return
    company_id = sel[0]
    page._show_company_detail(company_id)
    page._mapping_tab.show_unmapped()
    page._select_right_tab(1, "_right_tab_mapping")

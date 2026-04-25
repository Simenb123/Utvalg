from __future__ import annotations

import pytest


def _make_ar_page():
    import tkinter as tk
    from tkinter import ttk

    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("Tk not available in this environment")

    root.withdraw()
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    import src.pages.ar.frontend.page as page_ar
    page = page_ar.ARPage(nb)
    nb.add(page, text="AR")
    root.update_idletasks()
    return root, page


def test_owned_right_nb_is_lifted_to_top_with_rowspan() -> None:
    root, page = _make_ar_page()
    try:
        info = page._owned_right_nb.grid_info()
        assert int(info["row"]) == 0, info
        assert int(info["column"]) == 1, info
        assert int(info["rowspan"]) == 3, info
        sticky = str(info.get("sticky", ""))
        assert "n" in sticky and "s" in sticky, info
    finally:
        root.destroy()


def test_owned_tab_expands_only_on_tree_row() -> None:
    root, page = _make_ar_page()
    try:
        frm_owned = page._owned_right_nb.master
        weights = {i: int(frm_owned.grid_rowconfigure(i)["weight"]) for i in range(3)}
        assert weights[0] == 0, weights
        assert weights[1] == 0, weights
        assert weights[2] >= 1, weights
    finally:
        root.destroy()


def test_owned_tree_sits_below_search_bar() -> None:
    root, page = _make_ar_page()
    try:
        tree_info = page._tree_owned.grid_info()
        assert int(tree_info["row"]) == 2, tree_info
        assert int(tree_info["column"]) == 0, tree_info
    finally:
        root.destroy()

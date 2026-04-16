"""Tester at Analyse-eksporten respekterer `displaycolumns`.

Når brukeren skjuler kolonner via `Kolonner…` skal Excel-eksporten bare
inneholde de synlige kolonnene, i samme rekkefølge som i Treeview-en.
"""
from __future__ import annotations

import pytest

import analyse_export_excel


class FakeTree:
    """Minimal Treeview-stub for testing av eksporthjelperen."""

    def __init__(
        self,
        columns,
        headings,
        rows,
        displaycolumns="#all",
    ):
        self._columns = list(columns)
        self._headings = dict(headings)
        self._displaycolumns = displaycolumns
        # rows: [(iid, values, tags)]
        self._children = [iid for iid, _, _ in rows]
        self._items = {iid: (list(vals), tuple(tags)) for iid, vals, tags in rows}

    def __getitem__(self, key):
        if key == "columns":
            return tuple(self._columns)
        if key == "displaycolumns":
            return self._displaycolumns
        raise KeyError(key)

    def heading(self, col, option=None):
        return {"text": self._headings.get(col, col)}

    def get_children(self, parent=""):
        return tuple(self._children)

    def item(self, iid, option):
        vals, tags = self._items[iid]
        if option == "values":
            return vals
        if option == "tags":
            return tags
        raise ValueError(option)


def test_displaycolumns_all_exports_every_column():
    tree = FakeTree(
        columns=("konto", "navn", "sum"),
        headings={"konto": "Konto", "navn": "Kontonavn", "sum": "UB 2024"},
        rows=[("r1", ["1500", "Kundefordringer", "1000"], ())],
        displaycolumns="#all",
    )

    sheet = analyse_export_excel.treeview_to_sheet(tree, title="Test")

    assert sheet["columns"] == ["Konto", "Kontonavn", "UB 2024"]
    assert len(sheet["rows"]) == 1
    assert sheet["rows"][0]["values"] == [1500.0, "Kundefordringer", 1000.0]


def test_displaycolumns_subset_hides_non_visible_columns():
    tree = FakeTree(
        columns=("konto", "navn", "ib", "sum", "endring"),
        headings={
            "konto": "Konto",
            "navn": "Kontonavn",
            "ib": "IB",
            "sum": "UB 2024",
            "endring": "Endring",
        },
        rows=[("r1", ["1500", "Kundefordringer", "200", "1000", "800"], ())],
        displaycolumns=("konto", "navn", "sum"),
    )

    sheet = analyse_export_excel.treeview_to_sheet(tree, title="Test")

    assert sheet["columns"] == ["Konto", "Kontonavn", "UB 2024"]
    assert sheet["rows"][0]["values"] == [1500.0, "Kundefordringer", 1000.0]


def test_displaycolumns_preserves_reordered_display():
    tree = FakeTree(
        columns=("konto", "navn", "sum"),
        headings={"konto": "Konto", "navn": "Kontonavn", "sum": "UB 2024"},
        rows=[("r1", ["1500", "Kundefordringer", "1000"], ())],
        displaycolumns=("sum", "konto"),
    )

    sheet = analyse_export_excel.treeview_to_sheet(tree, title="Test")

    assert sheet["columns"] == ["UB 2024", "Konto"]
    assert sheet["rows"][0]["values"] == [1000.0, 1500.0]


def test_displaycolumns_unknown_columns_fall_back_to_all():
    tree = FakeTree(
        columns=("konto", "navn"),
        headings={"konto": "Konto", "navn": "Kontonavn"},
        rows=[("r1", ["1500", "Kundefordringer"], ())],
        displaycolumns=("whatever",),
    )

    sheet = analyse_export_excel.treeview_to_sheet(tree, title="Test")

    assert sheet["columns"] == ["Konto", "Kontonavn"]
    assert sheet["rows"][0]["values"] == [1500.0, "Kundefordringer"]


def test_heading_text_from_tree_is_used_in_excel():
    tree = FakeTree(
        columns=("sum",),
        headings={"sum": "UB 2024"},
        rows=[("r1", ["1000"], ())],
    )

    sheet = analyse_export_excel.treeview_to_sheet(tree, title="Ark")

    assert sheet["columns"] == ["UB 2024"]


def test_heading_defaults_to_title_when_omitted():
    tree = FakeTree(
        columns=("sum",),
        headings={"sum": "UB"},
        rows=[("r1", ["1"], ())],
    )

    sheet = analyse_export_excel.treeview_to_sheet(tree, title="Min fane")
    assert sheet["heading"] == "Min fane"

    sheet2 = analyse_export_excel.treeview_to_sheet(
        tree, title="Min fane", heading="Egen overskrift"
    )
    assert sheet2["heading"] == "Egen overskrift"


def test_treeview_to_sheet_dict_is_alias():
    assert (
        analyse_export_excel.treeview_to_sheet_dict
        is analyse_export_excel.treeview_to_sheet
    )

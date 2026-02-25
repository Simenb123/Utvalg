from __future__ import annotations

from types import SimpleNamespace

import dataset_pane_store


class MiniVar:
    def __init__(self, v: str = "") -> None:
        self._v = v

    def get(self) -> str:
        return self._v

    def set(self, v: str) -> None:
        self._v = v


class FakeCombobox(dict):
    def __init__(self) -> None:
        super().__init__()
        self["values"] = []


def test_client_filter_is_substring_and_case_insensitive() -> None:
    sec = dataset_pane_store.ClientStoreSection(
        frame=None,  # type: ignore[arg-type]
        client_var=MiniVar(""),
        year_var=MiniVar("2025"),
        hb_var=MiniVar(""),
        on_path_selected=lambda _p: None,
        get_current_path=lambda: "",
        lbl_storage=None,  # type: ignore[arg-type]
        cb_client=FakeCombobox(),
        cb_hb=FakeCombobox(),
    )

    sec._all_clients = ["Ortomedia AS", "Demo AS", "BHL klienter"]

    sec.client_var.set("demo")
    sec._on_client_keyrelease(SimpleNamespace(keysym="d"))
    assert sec.cb_client["values"] == ["Demo AS"]

    sec.client_var.set("KLIENT")
    sec._on_client_keyrelease(SimpleNamespace(keysym="k"))
    assert sec.cb_client["values"] == ["BHL klienter"]

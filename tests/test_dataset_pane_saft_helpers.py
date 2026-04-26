from __future__ import annotations


def test_is_saft_path_detects_zip_and_xml() -> None:
    from src.pages.dataset.frontend.pane import is_saft_path

    assert is_saft_path("C:/tmp/SAF-T.zip")
    assert is_saft_path("C:/tmp/SAF-T.XML")
    assert not is_saft_path("C:/tmp/hb.xlsx")

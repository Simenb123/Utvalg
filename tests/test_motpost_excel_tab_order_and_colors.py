import re
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd

from motpost.excel_sheets.common import TAB_OUTLIER_YELLOW
from motpost.konto_core import build_motpost_data
from src.audit_actions.motpost.konto_core import build_motpost_excel_workbook


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Bilag": 1,
                "Dato": "2025-01-01",
                "Tekst": "Utgående faktura",
                "Konto": "3000",
                "Kontonavn": "Salg",
                "Beløp": -1000.0,
            },
            {
                "Bilag": 1,
                "Dato": "2025-01-01",
                "Tekst": "Utgående faktura",
                "Konto": "1500",
                "Kontonavn": "Kundefordringer",
                "Beløp": 1000.0,
            },
        ]
    )


def _sheet_tab_colors_from_xlsx(path) -> dict[str, str]:
    """Returnerer map {sheet_xml: rgb} for ark som har tabColor."""

    out: dict[str, str] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not (name.startswith("xl/worksheets/sheet") and name.endswith(".xml")):
                continue

            root = ET.fromstring(zf.read(name))
            ns = {"m": root.tag.split("}")[0].strip("{")}

            pr = root.find("m:sheetPr", ns)
            if pr is None:
                continue

            tc = pr.find("m:tabColor", ns)
            if tc is None:
                continue

            rgb = tc.attrib.get("rgb")
            if rgb:
                out[name] = rgb

    return out


def _table_display_names_from_xlsx(path) -> list[str]:
    names: list[str] = []

    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not (name.startswith("xl/tables/table") and name.endswith(".xml")):
                continue

            root = ET.fromstring(zf.read(name))
            disp = root.attrib.get("displayName")
            if disp:
                names.append(disp)

    return names


def test_tab_order_and_colors_match_workpaper_style(tmp_path):
    df = _sample_df()
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")
    wb = build_motpost_excel_workbook(data, combo_status_map={"1500": "outlier"})

    # Rekkefølge: oversikt først, så outlier-detaljer, så outlier-transaksjoner, så data.
    assert wb.sheetnames == [
        "Oversikt",
        "#2",
        "Outlier - alle transaksjoner",
        "Data",
    ]

    # Outlier-faner skal være gule
    assert wb["#2"].sheet_properties.tabColor.rgb == TAB_OUTLIER_YELLOW
    assert wb["Outlier - alle transaksjoner"].sheet_properties.tabColor.rgb == TAB_OUTLIER_YELLOW

    # Ikke-outlier faner har ingen eksplisitt farge
    assert wb["Oversikt"].sheet_properties.tabColor is None
    assert wb["Data"].sheet_properties.tabColor is None

    # Lagre og sjekk at vi ikke får alpha=00 i tabColor (kan trigge Excel-repair)
    out_path = tmp_path / "motpost.xlsx"
    wb.save(out_path)
    tab_colors = _sheet_tab_colors_from_xlsx(out_path)

    # Alle tabColor-rgb i filen skal ha FF (ikke 00)
    assert tab_colors  # minst noen
    for rgb in tab_colors.values():
        assert rgb.startswith("FF")


def test_table_names_are_unique_and_not_cell_references(tmp_path):
    """Regresjon: Excel kan 'reparere' filer hvis table.displayName ligner på en cellereferanse.

    Dette har tidligere gitt:
      - "Removed Records: Formula ..."
      - "Repaired Records: Table ..."

    Vi verifiserer derfor at alle tabellnavn:
      1) er unike i hele workbooken
      2) ikke matcher mønsteret [A-Z]{1,3}\d+ (A1, TT2, ...)
    """

    df = _sample_df()
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")
    wb = build_motpost_excel_workbook(data, combo_status_map={"1500": "outlier"})

    out_path = tmp_path / "motpost.xlsx"
    wb.save(out_path)

    names = _table_display_names_from_xlsx(out_path)
    assert names  # minst én tabell

    assert len(names) == len(set(names))

    cell_ref_re = re.compile(r"^[A-Za-z]{1,3}\d+$")
    assert not any(cell_ref_re.match(n) for n in names)

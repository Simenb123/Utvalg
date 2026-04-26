"""Tests for scoping_export."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pages.scoping.backend.engine import ScopingLine, ScopingResult
from src.pages.scoping.backend.export import export_scoping


@pytest.fixture()
def sample_result():
    return ScopingResult(
        lines=[
            ScopingLine(
                regnr="10", regnskapslinje="Salgsinntekt", line_type="PL",
                amount=12_000_000, amount_prior=10_000_000,
                change_amount=2_000_000,
                change_pct=20.0, pct_of_pm=3200.0,
                classification="vesentlig", auto_classification="vesentlig",
                scoping="inn", action_count=7,
            ),
            ScopingLine(
                regnr="19", regnskapslinje="Sum driftsinntekter", line_type="PL",
                amount=12_000_000, is_summary=True,
            ),
            ScopingLine(
                regnr="70", regnskapslinje="Annen driftskostnad", line_type="PL",
                amount=18_000, classification="ikke_vesentlig",
                auto_classification="ikke_vesentlig",
                scoping="ut", rationale="Under SUM",
            ),
        ],
        om=500_000, pm=375_000, sum_threshold=25_000,
        scoped_out_total=18_000, aggregation_ok=True,
    )


def test_export_creates_file(sample_result, tmp_path):
    path = tmp_path / "scoping_test.xlsx"
    result = export_scoping(sample_result, path, client_name="Test AS", year="2025")
    assert result.exists()
    assert result.stat().st_size > 0


def test_export_content(sample_result, tmp_path):
    import openpyxl

    path = tmp_path / "scoping_test.xlsx"
    export_scoping(sample_result, path, client_name="Test AS", year="2025")

    wb = openpyxl.load_workbook(str(path))
    ws = wb.active
    assert ws.title == "Scoping"

    # Check title
    assert ws["A1"].value == "Scoping regnskapslinjer"

    # Check materiality info
    values = [ws.cell(row=r, column=2).value for r in range(3, 8)]
    assert "Test AS" in values
    assert "2025" in values

    headers = [ws.cell(row=9, column=c).value for c in range(1, 14)]
    assert headers[:7] == [
        "Regnr",
        "Regnskapslinje",
        "Type",
        "UB 2025",
        "UB 2024",
        "Endring",
        "Endring %",
    ]
    assert headers[7:] == [
        "% av PM",
        "Klassifisering",
        "Scoping",
        "Revisjonshandling",
        "Begrunnelse",
        "Handl.",
    ]

    assert ws.cell(row=10, column=4).value == 12_000_000
    assert ws.cell(row=10, column=5).value == 10_000_000
    assert ws.cell(row=10, column=6).value == 2_000_000
    assert ws.cell(row=10, column=7).value == "+20.0%"


def test_export_hides_prior_year_columns_when_absent(tmp_path):
    import openpyxl

    result = ScopingResult(
        lines=[
            ScopingLine(
                regnr="70",
                regnskapslinje="Annen driftskostnad",
                line_type="PL",
                amount=18_000,
                classification="ikke_vesentlig",
                auto_classification="ikke_vesentlig",
            )
        ],
        om=500_000,
        pm=375_000,
        sum_threshold=25_000,
    )

    path = tmp_path / "scoping_no_prev.xlsx"
    export_scoping(result, path, client_name="Test AS", year="2025")

    wb = openpyxl.load_workbook(str(path))
    ws = wb.active
    headers = [ws.cell(row=9, column=c).value for c in range(1, 11)]
    assert headers == [
        "Regnr",
        "Regnskapslinje",
        "Type",
        "UB 2025",
        "% av PM",
        "Klassifisering",
        "Scoping",
        "Revisjonshandling",
        "Begrunnelse",
        "Handl.",
    ]

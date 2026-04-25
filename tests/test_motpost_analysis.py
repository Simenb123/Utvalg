import pandas as pd
from datetime import datetime
import pytest

from src.audit_actions.motpost.combinations import build_bilag_to_motkonto_combo
from src.audit_actions.motpost.combinations import build_motkonto_combinations_per_selected_account
from src.audit_actions.motpost.combo_workflow import (
    account_display_name_for_mode,
    apply_combo_status,
    combo_display_name_for_mode,
    find_expected_combos_by_netting_regnskapslinjer,
    find_expected_combos_by_regnskapslinjer,
    compute_selected_net_sum_by_combo,
)
from src.audit_actions.motpost.konto_core import build_bilag_details, build_motpost_excel_workbook
from views_motpost_konto import build_motpost_data


def _sample_df() -> pd.DataFrame:
    # A tiny dataset with two bilag. Selected account is 3000.
    #
    # Bilag 1: 3000 kredit -1000, motposter 2700 debet 250, 1500 debet 750
    # Bilag 2: 3000 kredit -500,  motposter 1500 debet 500
    return pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 2, 2],
            "Dato": [
                "2025-01-01",
                "2025-01-01",
                "2025-01-01",
                "2025-01-02",
                "2025-01-02",
            ],
            "Konto": ["3000", "2700", "1500", "3000", "1500"],
            "Kontonavn": [
                "Salg",
                "Utgående mva",
                "Kundefordringer",
                "Salg",
                "Kundefordringer",
            ],
            "Tekst": ["Salg A", "MVA", "Kunde A", "Salg B", "Kunde B"],
            "Beløp": [-1000.0, 250.0, 750.0, -500.0, 500.0],
        }
    )


def test_build_motpost_data_credit_only_sums():
    df = _sample_df()
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")
    assert data.bilag_count == 2
    # Selected sum is only the credit lines on 3000: -1000 + -500 = -1500
    assert data.selected_sum == -1500.0
    # Control sum on scope should be 0.0
    assert abs(data.control_sum) < 1e-9


def test_build_bilag_details_includes_selected_side_mva_fields() -> None:
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 2, 2],
            "Dato": ["2025-01-01", "2025-01-01", "2025-01-01", "2025-01-02", "2025-01-02"],
            "Konto": ["3000", "2700", "1500", "3000", "1500"],
            "Kontonavn": ["Salg", "Utgående mva", "Kundefordringer", "Salg", "Kundefordringer"],
            "Tekst": ["Salg A", "MVA", "Kunde A", "Salg B", "Kunde B"],
            "Beløp": [-1000.0, 250.0, 750.0, -500.0, 500.0],
            "MVA-kode": ["3", "", "", "", ""],
            "MVA-prosent": ["25", "", "", "", ""],
            "MVA-beløp": [250.0, 0.0, 0.0, 0.0, 0.0],
        }
    )

    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")
    details = build_bilag_details(data, "1500")

    assert list(details["Bilag"]) == ["1", "2"]
    assert details.loc[0, "MVA-kode"] == "3"
    assert details.loc[0, "MVA-prosent"] == "25"
    assert details.loc[0, "MVA-beløp"] == pytest.approx(250.0)
    assert details.loc[1, "MVA-kode"] == ""
    assert details.loc[1, "MVA-prosent"] == ""
    assert details.loc[1, "MVA-beløp"] == pytest.approx(0.0)


def test_build_bilag_details_uses_cached_detail_rows() -> None:
    df = _sample_df()
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")

    prebuilt = data.df_details.copy()
    object.__setattr__(data, "_df_details_cache", prebuilt)

    details = build_bilag_details(data, "1500")

    assert list(details["Bilag"]) == ["1", "2"]
    assert details.loc[0, "Motbel\u00f8p"] == pytest.approx(750.0)
    assert details.loc[1, "Motbel\u00f8p"] == pytest.approx(500.0)


def test_bilag_to_motkonto_combo_and_drilldown_symmetry():
    df = _sample_df()
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")

    bilag_to_combo = build_bilag_to_motkonto_combo(data.df_scope, ["3000"])
    assert bilag_to_combo["1"] == "1500, 2700"
    assert bilag_to_combo["2"] == "1500"

    # For bilag 1, selected sum is -1000 and mot sum is +1000 (250+750)
    df_b1 = data.df_scope[data.df_scope["Bilag_str"] == "1"].copy()
    sel_mask = (df_b1["Konto_str"] == "3000") & (df_b1["Beløp"] < 0)
    sum_sel = float(df_b1.loc[sel_mask, "Beløp"].sum())
    sum_mot = float(df_b1.loc[~sel_mask, "Beløp"].sum())
    assert sum_sel == -1000.0
    assert sum_mot == 1000.0
    assert abs(sum_sel + sum_mot) < 1e-9




def test_compute_selected_net_sum_by_combo_includes_debet_on_selected_accounts():
    # Bilag 1 har både kredit og debet på valgt konto 3000.
    # Netto på valgt konto i bilag 1 er -800 (kredit -1000 + debet 200).
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1, 2, 2],
            "Dato": [
                "2025-01-01",
                "2025-01-01",
                "2025-01-01",
                "2025-01-01",
                "2025-01-02",
                "2025-01-02",
            ],
            "Konto": ["3000", "3000", "2700", "1500", "3000", "1500"],
            "Kontonavn": [
                "Salg",
                "Salg",
                "Utgående mva",
                "Kundefordringer",
                "Salg",
                "Kundefordringer",
            ],
            "Tekst": ["Salg A", "Korr", "MVA", "Kunde A", "Salg B", "Kunde B"],
            "Beløp": [-1000.0, 200.0, 250.0, 550.0, -500.0, 500.0],
        }
    )

    net_map = compute_selected_net_sum_by_combo(df, ["3000"], selected_direction="Kredit")
    assert net_map["1500, 2700"] == pytest.approx(-800.0)
    assert net_map["1500"] == pytest.approx(-500.0)



def test_compute_selected_net_sum_by_combo_clips_positive_net_when_direction_kredit():
    """Når retning=Kredit ønsker vi kun bilag med kredit-overvekt (netto < 0).

    Bilag med netto debet på valgte kontoer (netto > 0) skal bidra 0.
    """
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1, 2, 2],
            "Dato": [
                "2025-01-01",
                "2025-01-01",
                "2025-01-01",
                "2025-01-01",
                "2025-01-02",
                "2025-01-02",
            ],
            "Konto": ["3000", "3000", "1500", "2700", "3000", "1500"],
            "Kontonavn": [
                "Salg",
                "Salg",
                "Kundefordringer",
                "Utgående mva",
                "Salg",
                "Kundefordringer",
            ],
            "Tekst": ["Salg", "Korr", "Kunde", "MVA", "Salg B", "Kunde B"],
            # Bilag 1: -1000 (kredit) + 2000 (debet) => netto +1000 (netto debet) => skal klippes til 0
            # Bilag 2: -500 (kredit) => netto -500 (netto kredit) => beholdes
            "Beløp": [-1000.0, 2000.0, -500.0, -500.0, -500.0, 500.0],
        }
    )

    net_map = compute_selected_net_sum_by_combo(df, ["3000"], selected_direction="Kredit")
    assert net_map["1500, 2700"] == pytest.approx(0.0)
    assert net_map["1500"] == pytest.approx(-500.0)


def test_compute_selected_net_sum_by_combo_raises_on_empty_selected_accounts():
    df = _sample_df()
    with pytest.raises(ValueError):
        compute_selected_net_sum_by_combo(df, [])


def test_combo_display_helpers_can_show_regnskapslinjer() -> None:
    rl_map = {
        "3000": "10 Salgsinntekt",
        "3001": "15 Annen driftsinntekt",
    }

    combo_name = combo_display_name_for_mode(
        "3000, 3001",
        display_mode="Regnskapslinje",
        konto_regnskapslinje_map=rl_map,
    )
    account_name = account_display_name_for_mode(
        "3000",
        display_mode="Regnskapslinje",
        konto_regnskapslinje_map=rl_map,
    )

    assert combo_name == "10 Salgsinntekt; 15 Annen driftsinntekt"
    assert account_name == "10 Salgsinntekt"


def test_find_expected_combos_by_regnskapslinjer_matches_subset_of_expected_lines() -> None:
    combos = ["1500", "1500, 2700", "1500, 2900", "3909"]
    rl_map = {
        "1500": "610 Kundefordringer",
        "2700": "790 Skyldig offentlige avgifter",
        "2900": "798 Konserngjeld",
        "3909": "15 Annen driftsinntekt",
    }

    matched = find_expected_combos_by_regnskapslinjer(
        combos,
        expected_regnskapslinjer=["610 Kundefordringer", "790 Skyldig offentlige avgifter"],
        konto_regnskapslinje_map=rl_map,
    )

    assert matched == ["1500", "1500, 2700"]


def test_find_expected_combos_by_netting_regnskapslinjer_respects_tolerance() -> None:
    combos = ["1400, 7790", "1400, 7790, 6800"]
    rl_map = {
        "1400": "146 Varelager",
        "7790": "79 Sum driftskostnader",
        "6800": "70 Annen driftskostnad",
    }
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 2, 2, 2],
            "Konto": ["4000", "1400", "7790", "4000", "1400", "6800"],
            "Beløp": [1000.0, -999.6, -0.4, 1000.0, -900.0, -100.0],
        }
    )

    matched_loose = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=1.0,
    )
    matched_strict = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=0.1,
    )

    assert matched_loose == ["1400, 7790"]
    assert matched_strict == []


def test_find_expected_combos_by_netting_regnskapslinjer_uses_selected_source_regnskapslinjer() -> None:
    combos = ["1400", "2400"]
    rl_map = {
        "4000": "20 Varekostnad",
        "4010": "70 Annen driftskostnad",
        "1400": "146 Varelager",
        "2400": "780 Leverandørgjeld",
    }
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 2, 2],
            "Konto": ["4000", "1400", "4010", "2400"],
            "Beløp": [1000.0, -1000.0, 200.0, -200.0],
        }
    )

    matched = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000", "4010"],
        selected_regnskapslinjer=["20 Varekostnad"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=1.0,
    )

    assert matched == ["1400"]


def test_find_expected_combos_by_netting_regnskapslinjer_balanced_rounding_lines_always_pass() -> None:
    """Rounding lines that net to 0 should never block a match, regardless of tolerance."""
    combos = ["1400, 6800, 6900"]
    rl_map = {
        "4000": "20 Varekostnad",
        "1400": "146 Varelager",
        "6800": "70 Annen driftskostnad",
        "6900": "70 Annen driftskostnad",
    }
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1],
            "Konto": ["4000", "1400", "6800", "6900"],
            "Beløp": [1000.0, -1000.0, -0.6, 0.6],
        }
    )

    matched = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        selected_regnskapslinjer=["20 Varekostnad"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=0.5,
    )

    # Other lines (6800 + 6900) net to 0 → passes even with strict tolerance
    assert matched == ["1400, 6800, 6900"]


def test_find_expected_combos_by_netting_unbalanced_rounding_lines_blocked_by_tolerance() -> None:
    """A single unbalanced 'other' line creates a net residual that tolerance catches."""
    combos = ["1400, 6800"]
    rl_map = {
        "4000": "20 Varekostnad",
        "1400": "146 Varelager",
        "6800": "70 Annen driftskostnad",
    }
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1],
            "Konto": ["4000", "1400", "6800"],
            # Selected 1000 + Expected -999 = Residual 1, Other -1 (net)
            "Beløp": [1000.0, -999.0, -1.0],
        }
    )

    matched_loose = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        selected_regnskapslinjer=["20 Varekostnad"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=1.0,
    )
    matched_strict = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        selected_regnskapslinjer=["20 Varekostnad"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=0.5,
    )

    # Residual = 1.0, OtherNet = 1.0 — loose (1.0) passes, strict (0.5) fails
    assert matched_loose == ["1400, 6800"]
    assert matched_strict == []


def test_find_expected_combos_by_netting_regnskapslinjer_accepts_balanced_other_lines() -> None:
    """Other lines that net to zero (e.g. 6800: -100, 6900: +100) should NOT block
    a match — the selected/expected offset is clean and the 'noise' cancels out."""
    combos = ["1400, 6800, 6900"]
    rl_map = {
        "1400": "146 Varelager",
        "6800": "70 Annen driftskostnad",
        "6900": "70 Annen driftskostnad",
    }
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1],
            "Konto": ["4000", "1400", "6800", "6900"],
            "Beløp": [1000.0, -1000.0, -100.0, 100.0],
        }
    )

    matched = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=1.0,
    )

    # Other lines net to 0 → should match
    assert matched == ["1400, 6800, 6900"]


def test_find_expected_combos_by_netting_regnskapslinjer_rejects_unbalanced_other_lines() -> None:
    """When other lines do NOT net to ~0, the combo should be rejected."""
    combos = ["1400, 6800"]
    rl_map = {
        "1400": "146 Varelager",
        "6800": "70 Annen driftskostnad",
    }
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1],
            "Konto": ["4000", "1400", "6800"],
            "Beløp": [1000.0, -900.0, -100.0],
        }
    )

    matched = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=1.0,
    )

    # Residual = 1000 + (-900) = 100, OtherNet = -100 → both exceed tolerance
    assert matched == []


def test_find_expected_combos_by_netting_mva_scenario() -> None:
    """Classic purchase: varekostnad D, varelager K, MVA D, leverandoergjeld K.
    MVA + leverandoergjeld net to 0 and should not block the match."""
    combos = ["1400, 2400, 2710"]  # sorted order from build_bilag_to_motkonto_combo
    rl_map = {
        "4000": "20 Varekostnad",
        "1400": "146 Varelager",
        "2710": "170 Inngaaende merverdiavgift",
        "2400": "230 Leverandoergjeld",
    }
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1],
            "Konto": ["4000", "1400", "2710", "2400"],
            "Beløp": [800.0, -800.0, 200.0, -200.0],
        }
    )

    matched = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=1.0,
    )

    assert matched == ["1400, 2400, 2710"]


def test_find_expected_combos_by_netting_mva_with_rounding() -> None:
    """MVA-scenario with small rounding difference in the offset."""
    combos = ["1400, 2400, 2710"]
    rl_map = {
        "4000": "20 Varekostnad",
        "1400": "146 Varelager",
        "2710": "170 Inngaaende merverdiavgift",
        "2400": "230 Leverandoergjeld",
    }
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1],
            "Konto": ["4000", "1400", "2710", "2400"],
            # varekostnad og varelager har 0.50 differanse
            "Beløp": [800.0, -799.5, 200.0, -200.0],
        }
    )

    matched_loose = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=1.0,
    )
    matched_strict = find_expected_combos_by_netting_regnskapslinjer(
        combos,
        df_scope=df,
        selected_accounts=["4000"],
        expected_regnskapslinjer=["146 Varelager"],
        konto_regnskapslinje_map=rl_map,
        selected_direction="Debet",
        tolerance=0.1,
    )

    assert matched_loose == ["1400, 2400, 2710"]
    assert matched_strict == []


def _find_header_row(ws, must_contain: set[str]) -> int:
    for r in range(1, ws.max_row + 1):
        row_vals = []
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            if v not in (None, ""):
                row_vals.append(str(v).strip())
        if must_contain.issubset(set(row_vals)):
            return r
    raise AssertionError(f"Could not find table header row containing {must_contain}")


def _read_sheet_table(ws, must_contain: set[str]) -> tuple[list[str], list[dict[str, object]]]:
    """Helper: reads a sheet written by _write_df_table (title row + blank + header)."""
    header_row = _find_header_row(ws, must_contain)

    headers: list[str] = []
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=header_row, column=c).value
        if v in (None, ""):
            break
        headers.append(str(v))

    rows: list[dict[str, object]] = []
    for r in range(header_row + 1, ws.max_row + 1):
        row_values = [ws.cell(row=r, column=c).value for c in range(1, len(headers) + 1)]
        if all(v in (None, "") for v in row_values):
            continue
        row: dict[str, object] = {}
        for c, h in enumerate(headers, start=1):
            row[h] = ws.cell(row=r, column=c).value
        rows.append(row)
    return headers, rows


def test_excel_workbook_combo_status_and_outlier_bilag_extract_happy_path():
    """Status/kommentar fra kombinasjons-popup skal gå helt til Excel, og outlier-bilag skal trekkes ut."""

    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 2, 2],
            "Dato": [datetime(2025, 1, 1)] * 3 + [datetime(2025, 1, 2)] * 2,
            "Tekst": ["", "", "", "", ""],
            "Konto": [3000, 1500, 2700, 3000, 1500],
            "Kontonavn": ["Salg", "Kundefordringer", "Utgående mva", "Salg", "Kundefordringer"],
            "Beløp": [-1000.0, 800.0, 200.0, -500.0, 500.0],
        }
    )

    data = build_motpost_data(df, ["3000"], selected_direction="Kredit")

    # Kombinasjons-popup: 1500,2700 = outlier, 1500 = forventet
    status_map = {"1500, 2700": "outlier", "1500": "expected"}
    comment_map = {"1500, 2700": "Review this combo", "1500": "OK"}

    wb = build_motpost_excel_workbook(
        data,
        combo_status_map=status_map,
        combo_comment_map=comment_map,
    )

    # Nye ark: Oversikt, #<n>, Outlier - alle transaksjoner, Data
    required = {"Oversikt", "Outlier - alle transaksjoner", "Data"}
    assert required.issubset(set(wb.sheetnames))
    assert "Kombinasjoner" not in wb.sheetnames

    # Det skal finnes minst én outlier-detaljfane (#n)
    assert any(name.startswith("#") and name[1:].isdigit() for name in wb.sheetnames)

    # Kombinasjonstabellen ligger på Data-arket
    _, df_combo = _read_sheet_table(wb["Data"], must_contain={"Kombinasjon", "Status"})
    by_combo = {row["Kombinasjon"]: row for row in df_combo}

    assert by_combo["1500, 2700"]["Status"] == "Ikke forventet"
    assert by_combo["1500, 2700"]["Kommentar"] == "Review this combo"

    assert by_combo["1500"]["Status"] == "Forventet"
    assert by_combo["1500"]["Kommentar"] == "OK"

    # Valgte kontoer (populasjon) ligger på Data-arket
    _, df_sel = _read_sheet_table(wb["Data"], must_contain={"Konto", "Kredit", "Debet", "Netto"})
    by_konto = {row["Konto"]: row for row in df_sel}

    assert by_konto["3000"]["Kredit"] == -1500.0
    assert by_konto["3000"]["Debet"] == 0.0
    assert by_konto["3000"]["Netto"] == -1500.0

    # Outlier-uttrekk: kun bilag 1 skal inn (hele bilaget)
    _, df_out = _read_sheet_table(wb["Outlier - alle transaksjoner"], must_contain={"Bilag", "Konto", "Beløp"})
    bilags_in_out = {row["Bilag"] for row in df_out}
    assert bilags_in_out == {"1"}  # bilag 2 er forventet, og skal ikke være med


def test_excel_workbook_excludes_blank_bilag_and_documents_note():
    """Bilag uten bilagsnummer skal ikke trekkes inn, og dette skal dokumenteres i outlier-arket."""

    df = pd.DataFrame(
        {
            "Bilag": [None, None, None],
            "Dato": [datetime(2025, 1, 1)] * 3,
            "Tekst": ["", "", ""],
            "Konto": [3000, 1500, 2700],
            "Kontonavn": ["Salg", "Kundefordringer", "Utgående mva"],
            "Beløp": [-1000.0, 800.0, 200.0],
        }
    )

    data = build_motpost_data(df, ["3000"], selected_direction="Kredit")

    wb = build_motpost_excel_workbook(
        data,
        combo_status_map={"1500, 2700": "outlier"},
    )

    ws_out = wb["Outlier - alle transaksjoner"]
    found_note = False
    for row in ws_out.iter_rows(min_row=1, max_row=10, max_col=10, values_only=True):
        for val in row:
            if isinstance(val, str) and "uten bilagsnummer" in val:
                found_note = True
                break
        if found_note:
            break

    assert found_note

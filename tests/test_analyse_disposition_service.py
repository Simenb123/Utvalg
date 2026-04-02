from __future__ import annotations

import pandas as pd

import analyse_disposition_service as svc


def _regnskapslinjer_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nr": [280, 295, 320, 350],
            "regnskapslinje": [
                "Arsresultat",
                "Avsatt til utbytte",
                "Avsatt til annen EK",
                "Sum overforinger",
            ],
            "sumpost": ["nei", "nei", "nei", "ja"],
            "delsumnr": [None, 350, 350, None],
            "sumnr": [None, None, None, None],
            "sumnr2": [None, None, None, None],
            "sluttsumnr": [None, None, None, None],
            "formel": [None, None, None, None],
        }
    )


def test_build_disposition_summary_uses_leaf_lines_under_350() -> None:
    effective_sb = pd.DataFrame(
        {
            "konto": ["8999", "8740", "8745"],
            "kontonavn": ["Arets resultat", "Avsatt utbytte", "Disponering EK"],
            "ib": [0.0, 0.0, 0.0],
            "ub": [-100.0, 40.0, 60.0],
        }
    )
    intervals = pd.DataFrame(
        {
            "fra": [8740, 8745, 8999],
            "til": [8740, 8745, 8999],
            "regnr": [295, 320, 280],
        }
    )

    summary = svc.build_disposition_summary(
        hb_df=None,
        effective_sb_df=effective_sb,
        intervals=intervals,
        regnskapslinjer=_regnskapslinjer_df(),
        account_overrides={},
    )

    assert summary.arsresultat == -100.0
    assert summary.line_295 == 40.0
    assert summary.line_320 == 60.0
    assert summary.sum_overforinger == 100.0
    assert summary.rest_a_disponere == 0.0
    assert set(summary.line_350_leafs) == {295, 320}


def test_project_draft_line_flags_unmapped_and_sumline() -> None:
    intervals = pd.DataFrame({"fra": [8800], "til": [9999], "regnr": [350]})
    regn = _regnskapslinjer_df()

    unmapped = svc.project_draft_line(
        konto="7777",
        belop=50.0,
        intervals=intervals,
        regnskapslinjer=regn,
        account_overrides={},
        account_name_lookup={"7777": "Ukjent"},
    )
    sumline = svc.project_draft_line(
        konto="8800",
        belop=50.0,
        intervals=intervals,
        regnskapslinjer=regn,
        account_overrides={},
        account_name_lookup={"8800": "Skatt"},
    )

    assert unmapped.mapping_status == "unmapped"
    assert unmapped.regnr is None
    assert sumline.mapping_status == "sumline"
    assert sumline.regnr == 350


def test_summarize_draft_tracks_transfer_effect_and_invalid_lines() -> None:
    summary = svc.DispositionSummary(
        arsresultat=-100.0,
        sum_overforinger=0.0,
        rest_a_disponere=-100.0,
        line_295=0.0,
        line_320=0.0,
        line_350_leafs=(295, 320),
    )
    intervals = pd.DataFrame(
        {
            "fra": [8740, 8999, 8800],
            "til": [8740, 8999, 9999],
            "regnr": [295, 280, 350],
        }
    )
    regn = _regnskapslinjer_df()

    draft = [
        {"konto": "8740", "belop": 100.0, "beskrivelse": "Utbytte"},
        {"konto": "8999", "belop": -100.0, "beskrivelse": "Motpost resultat"},
        {"konto": "8800", "belop": 5.0, "beskrivelse": "Ugyldig sumlinje"},
    ]
    summary_result = svc.summarize_draft(
        draft,
        disposition_summary=summary,
        intervals=intervals,
        regnskapslinjer=regn,
        account_overrides={},
        account_name_lookup={"8740": "Avsatt utbytte", "8999": "Arets resultat", "8800": "Skatt"},
    )

    assert summary_result.debet == 105.0
    assert summary_result.kredit == 100.0
    assert summary_result.diff == 5.0
    assert summary_result.transfer_effect == 100.0
    assert summary_result.rest_etter_utkast == 0.0
    assert summary_result.has_invalid_lines is True

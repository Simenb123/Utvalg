from __future__ import annotations


def test_rf1022_treatment_details_for_skyldig_feriepenger_uses_accrual_pay() -> None:
    from a07_feature import page_control_data

    treatment = page_control_data.rf1022_treatment_details(
        account_no="2940",
        account_name="Skyldig feriepenger",
        ib=-743_491.69,
        endring=-4_207.18,
        ub=-747_698.87,
        group_id="100_loenn_ol",
        post_text="Post 100 Lønn o.l.",
        aga_pliktig=True,
    )

    assert treatment.kind == "accrual_pay"
    assert treatment.cost_amount is None
    assert treatment.addition_amount == 743_491.69
    assert treatment.deduction_amount == 747_698.87
    assert treatment.taxable_amount == -4_207.18
    assert treatment.aga_amount == -4_207.18


def test_rf1022_treatment_text_for_skyldig_feriepenger_shows_ib_minus_ub() -> None:
    from a07_feature import page_control_data

    text = page_control_data.format_rf1022_treatment_text(
        account_no="2940",
        account_name="Skyldig feriepenger",
        ib=-743_491.69,
        endring=-4_207.18,
        ub=-747_698.87,
        group_id="100_loenn_ol",
        post_text="Post 100 Lønn o.l.",
    )

    assert text == "RF-1022: +|IB| 743 491,69 - |UB| 747 698,87 = -4 207,18"


def test_rf1022_treatment_details_for_skyldig_aga_uses_accrual_aga() -> None:
    from a07_feature import page_control_data

    treatment = page_control_data.rf1022_treatment_details(
        account_no="2770",
        account_name="Skyldig arbeidsgiveravgift",
        ib=-230_441.00,
        endring=1_597.00,
        ub=-228_844.00,
        group_id="aga",
        post_text="Post 110 Arbeidsgiveravgift",
        aga_pliktig=True,
    )

    assert treatment.kind == "accrual_aga"
    assert treatment.cost_amount is None
    assert treatment.addition_amount == 230_441.0
    assert treatment.deduction_amount == 228_844.0
    assert treatment.taxable_amount is None
    assert treatment.aga_amount == 1_597.0


def test_rf1022_treatment_details_for_forskuddstrekk_uses_withholding() -> None:
    from a07_feature import page_control_data

    treatment = page_control_data.rf1022_treatment_details(
        account_no="2600",
        account_name="Forskuddstrekk",
        ib=-341_244.00,
        endring=-109_358.00,
        ub=-450_602.00,
        group_id="forskuddstrekk",
        post_text="Post 100 Lønn o.l.",
        aga_pliktig=False,
    )

    assert treatment.kind == "withholding"
    assert treatment.cost_amount is None
    assert treatment.addition_amount is None
    assert treatment.deduction_amount is None
    assert treatment.taxable_amount is None
    assert treatment.aga_amount is None


def test_rf1022_treatment_details_for_periodisering_av_lonn_uses_periodisation_pay() -> None:
    from a07_feature import page_control_data

    treatment = page_control_data.rf1022_treatment_details(
        account_no="5095",
        account_name="Periodisering av lønn",
        ib=0.0,
        endring=45_709.73,
        ub=45_709.73,
        group_id="100_loenn_ol",
        post_text="Post 100 Lønn o.l.",
        aga_pliktig=False,
    )

    assert treatment.kind == "periodisation_pay"
    assert treatment.cost_amount == 45_709.73
    assert treatment.addition_amount is None
    assert treatment.deduction_amount is None
    assert treatment.taxable_amount == 45_709.73


def test_rf1022_treatment_details_for_additional_periodisation_and_accrual_accounts() -> None:
    from a07_feature import page_control_data

    skyldig_lonn = page_control_data.rf1022_treatment_details(
        account_no="2930",
        account_name="Skyldig lonn",
        ib=-90_590.00,
        endring=-45_709.73,
        ub=-136_299.73,
        group_id="100_loenn_ol",
        post_text="Post 100 Lønn o.l.",
        aga_pliktig=True,
    )
    palopt_aga_ferielonn = page_control_data.rf1022_treatment_details(
        account_no="2785",
        account_name="Påløpt arbeidsgiveravgift på ferielønn",
        ib=-104_832.38,
        endring=-593.17,
        ub=-105_425.55,
        group_id="aga",
        post_text="Post 110 Arbeidsgiveravgift",
        aga_pliktig=True,
    )
    periodisering_feriepenger = page_control_data.rf1022_treatment_details(
        account_no="5096",
        account_name="Periodisering av feriepenger",
        ib=0.0,
        endring=6_861.97,
        ub=6_861.97,
        group_id="100_loenn_ol",
        post_text="Post 100 Lønn o.l.",
        aga_pliktig=False,
    )
    periodisering_balanse = page_control_data.rf1022_treatment_details(
        account_no="2945",
        account_name="Periodisering av lønn",
        ib=-10_000.0,
        endring=0.0,
        ub=-12_500.0,
        group_id="100_loenn_ol",
        post_text="Post 100 Lønn o.l.",
        aga_pliktig=False,
    )

    assert skyldig_lonn.kind == "accrual_pay"
    assert skyldig_lonn.taxable_amount == -45_709.73
    assert palopt_aga_ferielonn.kind == "accrual_aga"
    assert palopt_aga_ferielonn.aga_amount == -593.17
    assert periodisering_feriepenger.kind == "periodisation_pay"
    assert periodisering_feriepenger.cost_amount == 6_861.97
    assert periodisering_balanse.kind == "accrual_pay"
    assert periodisering_balanse.addition_amount == 10_000.0
    assert periodisering_balanse.deduction_amount == 12_500.0


def test_rf1022_treatment_details_for_refusjon_and_pensjon_keep_special_kinds() -> None:
    from a07_feature import page_control_data

    refund = page_control_data.rf1022_treatment_details(
        account_no="5800",
        account_name="Refusjon av sykepenger",
        ib=0.0,
        endring=-465_809.0,
        ub=-465_809.0,
        group_id="100_refusjon",
        post_text="Post 100 Refusjon",
        aga_pliktig=False,
    )
    pension = page_control_data.rf1022_treatment_details(
        account_no="5930",
        account_name="Pensjonsforsikring OTP",
        ib=0.0,
        endring=2_314_663.21,
        ub=2_314_663.21,
        group_id="112_pensjon",
        post_text="Post 112 Pensjon",
        aga_pliktig=False,
    )

    assert refund.kind == "refund"
    assert refund.aga_amount == -465_809.0
    assert pension.kind == "pension"
    assert pension.aga_amount == 2_314_663.21

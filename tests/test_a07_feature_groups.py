from __future__ import annotations

from decimal import Decimal

import pandas as pd

from a07_feature import A07Group, apply_groups_to_mapping, build_grouped_a07_df


def test_build_grouped_a07_df_creates_group_rows_and_membership():
    a07_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "fastloenn", "Belop": Decimal("100"), "Diff": Decimal("0")},
            {"Kode": "timeloenn", "Navn": "timeloenn", "Belop": Decimal("50"), "Diff": Decimal("0")},
            {"Kode": "bonus", "Navn": "bonus", "Belop": Decimal("10"), "Diff": Decimal("0")},
        ]
    )

    groups = {
        "fastloenn + timeloenn": A07Group(
            group_id="fastloenn + timeloenn",
            group_name="fastloenn + timeloenn",
            member_codes=["fastloenn", "timeloenn"],
        )
    }

    grouped, membership = build_grouped_a07_df(a07_df, groups)

    assert "fastloenn + timeloenn" in set(grouped["Kode"].astype(str).tolist())
    assert "fastloenn" not in set(grouped["Kode"].astype(str).tolist())
    assert "timeloenn" not in set(grouped["Kode"].astype(str).tolist())
    assert membership["fastloenn"] == "fastloenn + timeloenn"
    assert membership["timeloenn"] == "fastloenn + timeloenn"


def test_build_grouped_a07_df_supports_legacy_kilometer_aliases():
    a07_df = pd.DataFrame(
        [
            {
                "Kode": "kilometergodtgjoerelseBil",
                "Navn": "kilometergodtgjoerelse bil",
                "Belop": Decimal("100"),
                "Diff": Decimal("0"),
            },
            {
                "Kode": "kilometergodtgjoerelsePassasjertillegg",
                "Navn": "kilometergodtgjoerelse passasjertillegg",
                "Belop": Decimal("25"),
                "Diff": Decimal("0"),
            },
        ]
    )

    group_id = "kilometergodtjoerelseBil + kilometergodtjoerelsePassasjertillegg"
    groups = {
        group_id: A07Group(
            group_id=group_id,
            group_name=group_id,
            member_codes=[
                "kilometergodtjoerelseBil",
                "kilometergodtjoerelsePassasjertillegg",
            ],
        )
    }

    grouped, membership = build_grouped_a07_df(a07_df, groups)
    row = grouped.loc[grouped["Kode"] == group_id].iloc[0]

    assert membership["kilometergodtgjoerelseBil"] == group_id
    assert membership["kilometergodtgjoerelsePassasjertillegg"] == group_id
    assert row["Belop"] == Decimal("125")


def test_apply_groups_to_mapping_projects_codes_to_group_id():
    mapping = {"5000": "fastloenn", "5001": "bonus"}
    membership = {"fastloenn": "fastloenn + timeloenn"}

    out = apply_groups_to_mapping(mapping, membership)

    assert out["5000"] == "fastloenn + timeloenn"
    assert out["5001"] == "bonus"

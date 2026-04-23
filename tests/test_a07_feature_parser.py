from __future__ import annotations

import json
from decimal import Decimal

from a07_feature import build_monthly_summary, parse_a07_json


def _inntekt_items():
    return [
        {"loennsinntekt": {"beskrivelse": "fastloenn"}, "beloep": 100},
        {"loennsinntekt": {"beskrivelse": "bonus"}, "beloep": 10},
    ]


def test_parse_a07_json_prefers_summary_nodes_without_double_counting(tmp_path):
    payload = {
        "mottatt": {
            "oppgave": {
                "oppsummerteVirksomheter": {"inntekt": _inntekt_items()},
                "virksomhet": [
                    {
                        "inntekt": _inntekt_items(),
                        "inntektsmottaker": [{"inntekt": _inntekt_items()}],
                    }
                ],
            }
        }
    }

    path = tmp_path / "a07.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    df = parse_a07_json(path, top_n=50)

    assert df.loc[df["Kode"] == "fastloenn", "Belop"].iloc[0] == Decimal("100.00")
    assert df.loc[df["Kode"] == "bonus", "Belop"].iloc[0] == Decimal("10.00")


def test_parse_a07_json_carries_aga_pliktig_flag(tmp_path):
    payload = {
        "inntekter": [
            {
                "loennsinntekt": {
                    "beskrivelse": "fastloenn",
                    "inngaarIGrunnlagForArbeidsgiveravgift": True,
                },
                "beloep": 100,
            },
            {
                "loennsinntekt": {"beskrivelse": "bil", "agaPliktig": "nei"},
                "beloep": 50,
            },
        ]
    }
    path = tmp_path / "a07.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    df = parse_a07_json(path, top_n=50)

    assert bool(df.loc[df["Kode"] == "fastloenn", "AgaPliktig"].iloc[0]) is True
    assert bool(df.loc[df["Kode"] == "bil", "AgaPliktig"].iloc[0]) is False


def test_build_monthly_summary_groups_multiple_submissions_by_month(tmp_path):
    payload = {
        "mottatt": {
            "opplysningspliktig": {
                "innsendinger": [
                    {
                        "kalendermaaned": "2025-01",
                        "status": "GODKJENT",
                        "antallInntektsmottakere": 2,
                        "mottattAvgiftOgTrekkTotalt": {
                            "sumArbeidsgiveravgift": 100,
                            "sumForskuddstrekk": 50,
                            "sumFinansskattLoenn": 0,
                        },
                    },
                    {
                        "kalendermaaned": "2025-01",
                        "status": "GODKJENT",
                        "antallInntektsmottakere": 3,
                        "mottattAvgiftOgTrekkTotalt": {
                            "sumArbeidsgiveravgift": 20,
                            "sumForskuddstrekk": 10,
                            "sumFinansskattLoenn": "0.50",
                        },
                    },
                    {
                        "kalendermaaned": "2025-02",
                        "status": "GODKJENT",
                        "antallInntektsmottakere": 1,
                        "mottattAvgiftOgTrekkTotalt": {
                            "sumArbeidsgiveravgift": 30,
                            "sumForskuddstrekk": 15,
                            "sumFinansskattLoenn": 0,
                        },
                    },
                ]
            }
        }
    }

    path = tmp_path / "a07_months.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    df = build_monthly_summary(path)

    jan = df[df["kalendermaaned"] == "2025-01"].iloc[0]
    feb = df[df["kalendermaaned"] == "2025-02"].iloc[0]

    assert jan["sumArbeidsgiveravgift"] == Decimal("120.00")
    assert jan["sumForskuddstrekk"] == Decimal("60.00")
    assert jan["innsendinger"] == 2
    assert jan["antallInntektsmottakere"] == 3
    assert jan["Maaned"] == "2025-01"
    assert jan["FinansskattLoenn"] == Decimal("0.50")

    assert feb["sumArbeidsgiveravgift"] == Decimal("30.00")
    assert feb["sumForskuddstrekk"] == Decimal("15.00")
    assert feb["innsendinger"] == 1

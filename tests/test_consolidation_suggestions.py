"""Tests for consolidation.suggestions — forslagsmotor for elimineringer."""

from __future__ import annotations

import pytest
import pandas as pd

from consolidation.models import (
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    EliminationSuggestion,
    project_from_dict,
    project_to_dict,
)
from consolidation.suggestions import (
    create_journal_from_suggestion,
    generate_suggestions,
    ignore_suggestion,
    unignore_suggestion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project(
    *,
    companies: list[CompanyTB] | None = None,
    reporting_currency: str = "NOK",
    tolerance: float = 1000.0,
) -> ConsolidationProject:
    if companies is None:
        companies = [
            CompanyTB(company_id="mor", name="Mor AS"),
            CompanyTB(company_id="dat", name="Datter AS"),
        ]
    return ConsolidationProject(
        client="Test", year="2025",
        companies=companies,
        reporting_currency=reporting_currency,
        match_tolerance_nok=tolerance,
    )


def _mapped_tb(regnr_amounts: dict[int, float]) -> pd.DataFrame:
    """Lag en mapped TB med gitt regnr -> UB beloep."""
    rows = []
    for rn, ub in regnr_amounts.items():
        rows.append({
            "konto": str(rn * 10),
            "kontonavn": f"Konto {rn}",
            "ib": 0.0, "ub": ub, "netto": ub,
            "regnr": rn,
        })
    df = pd.DataFrame(rows)
    df["regnr"] = df["regnr"].astype("Int64")
    return df


# ---------------------------------------------------------------------------
# Kandidatgenerering
# ---------------------------------------------------------------------------

class TestGenerateSuggestions:

    def test_intercompany_fordring_gjeld(self):
        """Konsernfordring mot konserngjeld skal generere en kandidat."""
        proj = _project()
        regnr_names = {10: "Konsernfordringer", 20: "Konserngjeld"}
        tbs = {
            "mor": _mapped_tb({10: 500_000.0}),
            "dat": _mapped_tb({20: -500_000.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        assert len(suggestions) >= 1
        s = suggestions[0]
        assert s.kind == "intercompany"
        assert abs(s.diff_nok) < 0.01  # perfekt match
        assert s.status == "ny"

    def test_interest_income_vs_expense(self):
        """Renteinntekt mot rentekostnad i samme konsern."""
        proj = _project()
        regnr_names = {
            30: "Renteinntekt fra foretak i samme konsern",
            40: "Rentekostnad til foretak i samme konsern",
        }
        tbs = {
            "mor": _mapped_tb({30: -100_000.0}),
            "dat": _mapped_tb({40: 95_000.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        interest = [s for s in suggestions if s.kind == "interest"]
        assert len(interest) >= 1
        # diff = amount_a + amount_b in NOK (sign_flip sum)
        # -100_000 + 95_000 = -5_000  (abs = 5_000)
        assert abs(interest[0].diff_nok) == pytest.approx(5_000, abs=1)

    def test_group_contribution(self):
        """Mottatt konsernbidrag mot avgitt konsernbidrag."""
        proj = _project()
        regnr_names = {50: "Mottatt konsernbidrag", 60: "Avgitt konsernbidrag"}
        tbs = {
            "mor": _mapped_tb({50: -200_000.0}),
            "dat": _mapped_tb({60: 200_000.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        gc = [s for s in suggestions if s.kind == "group_contribution"]
        assert len(gc) >= 1

    def test_investment_equity_template(self):
        """Investering i datterselskap mot egenkapital -> template-kandidat."""
        proj = _project()
        regnr_names = {
            70: "Investering i datterselskap",
            80: "Aksjekapital",
        }
        tbs = {
            "mor": _mapped_tb({70: 1_000_000.0}),
            "dat": _mapped_tb({80: -1_000_000.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        inv = [s for s in suggestions if s.kind == "investment_equity"]
        assert len(inv) >= 1

    def test_ignored_candidate_stays_ignored(self):
        """Ignorert kandidat faar status 'ignorert', ikke 'ny'."""
        proj = _project()
        regnr_names = {10: "Konsernfordringer", 20: "Konserngjeld"}
        tbs = {
            "mor": _mapped_tb({10: 500_000.0}),
            "dat": _mapped_tb({20: -500_000.0}),
        }
        # Generer foerst for aa finne noekkel
        s1 = generate_suggestions(proj, tbs, regnr_names)
        assert s1[0].status == "ny"

        # Ignorer
        ignore_suggestion(s1[0].suggestion_key, proj)

        # Generer paa nytt
        s2 = generate_suggestions(proj, tbs, regnr_names)
        assert s2[0].status == "ignorert"

    def test_no_suggestions_when_no_matching_lines(self):
        """Ingen kandidater naar regnskapslinjene ikke matcher reglene."""
        proj = _project()
        regnr_names = {10: "Bankinnskudd", 20: "Varekostnad"}
        tbs = {
            "mor": _mapped_tb({10: 100.0}),
            "dat": _mapped_tb({20: -200.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        assert len(suggestions) == 0

    def test_no_suggestions_for_zero_amounts(self):
        """Ingen kandidater naar begge beloep er null."""
        proj = _project()
        regnr_names = {10: "Konsernfordringer", 20: "Konserngjeld"}
        tbs = {
            "mor": _mapped_tb({10: 0.0}),
            "dat": _mapped_tb({20: 0.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        assert len(suggestions) == 0


# ---------------------------------------------------------------------------
# Valuta
# ---------------------------------------------------------------------------

class TestCurrencyConversion:

    def test_balance_line_uses_closing_rate(self):
        """Balanselinje (regnr >= 500) bruker sluttkurs."""
        proj = _project(companies=[
            CompanyTB(company_id="mor", name="Mor AS"),
            CompanyTB(
                company_id="dat", name="Datter SE",
                currency_code="SEK", closing_rate=0.95, average_rate=0.97,
            ),
        ])
        regnr_names = {500: "Konsernfordringer", 510: "Konserngjeld"}
        tbs = {
            "mor": _mapped_tb({500: 950_000.0}),    # NOK
            "dat": _mapped_tb({510: -1_000_000.0}),  # SEK
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        assert len(suggestions) >= 1
        s = suggestions[0]
        # SEK beloep * sluttkurs = -1_000_000 * 0.95 = -950_000 NOK
        # Diff bør vaere 0 (950_000 + -950_000 = 0)
        assert abs(s.diff_nok) < 1.0

    def test_result_line_uses_average_rate(self):
        """Resultatlinje (regnr < 500) bruker snittkurs."""
        proj = _project(companies=[
            CompanyTB(company_id="mor", name="Mor AS"),
            CompanyTB(
                company_id="dat", name="Datter SE",
                currency_code="SEK", closing_rate=0.95, average_rate=0.97,
            ),
        ])
        regnr_names = {
            30: "Renteinntekt fra foretak i samme konsern",
            40: "Rentekostnad til foretak i samme konsern",
        }
        tbs = {
            "mor": _mapped_tb({30: -97_000.0}),     # NOK
            "dat": _mapped_tb({40: 100_000.0}),      # SEK
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        interest = [s for s in suggestions if s.kind == "interest"]
        assert len(interest) >= 1
        # SEK beloep * snittkurs = 100_000 * 0.97 = 97_000 NOK
        # Diff: -97_000 + 97_000 = 0
        assert abs(interest[0].diff_nok) < 1.0


# ---------------------------------------------------------------------------
# Journalutkast
# ---------------------------------------------------------------------------

class TestCreateJournal:

    def test_creates_journal_with_lines(self):
        """Kandidat -> journal lager riktige linjer."""
        proj = _project()
        regnr_names = {10: "Konsernfordringer", 20: "Konserngjeld"}
        tbs = {
            "mor": _mapped_tb({10: 500_000.0}),
            "dat": _mapped_tb({20: -500_000.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        s = suggestions[0]

        journal = create_journal_from_suggestion(s, proj)
        assert journal.kind == "from_suggestion"
        assert journal.source_suggestion_key == s.suggestion_key
        assert len(journal.lines) == 2
        assert journal.is_balanced  # reverser begge sider

    def test_applied_key_persists(self):
        """source_suggestion_key roundtripper via serialisering."""
        proj = _project()
        regnr_names = {10: "Konsernfordringer", 20: "Konserngjeld"}
        tbs = {
            "mor": _mapped_tb({10: 500_000.0}),
            "dat": _mapped_tb({20: -500_000.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        journal = create_journal_from_suggestion(suggestions[0], proj)
        proj.eliminations.append(journal)

        d = project_to_dict(proj)
        restored = project_from_dict(d)

        assert suggestions[0].suggestion_key in restored.applied_suggestion_keys
        j = restored.eliminations[0]
        assert j.source_suggestion_key == suggestions[0].suggestion_key
        assert j.kind == "from_suggestion"

    def test_applied_candidate_gets_journalfoert_status(self):
        """Journalfoert kandidat faar status 'journalfoert' ved regenerering."""
        proj = _project()
        regnr_names = {10: "Konsernfordringer", 20: "Konserngjeld"}
        tbs = {
            "mor": _mapped_tb({10: 500_000.0}),
            "dat": _mapped_tb({20: -500_000.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        create_journal_from_suggestion(suggestions[0], proj)

        # Regenerer
        s2 = generate_suggestions(proj, tbs, regnr_names)
        assert s2[0].status == "journalfoert"

    def test_investment_equity_gets_template_kind(self):
        """Investering/EK-kandidat lager journal med kind='template'."""
        proj = _project()
        regnr_names = {70: "Investering i datterselskap", 80: "Aksjekapital"}
        tbs = {
            "mor": _mapped_tb({70: 1_000_000.0}),
            "dat": _mapped_tb({80: -1_000_000.0}),
        }
        suggestions = generate_suggestions(proj, tbs, regnr_names)
        inv = [s for s in suggestions if s.kind == "investment_equity"]
        assert inv
        journal = create_journal_from_suggestion(inv[0], proj)
        assert journal.kind == "template"


# ---------------------------------------------------------------------------
# Ignore / unignore
# ---------------------------------------------------------------------------

class TestIgnoreUnignore:

    def test_ignore_adds_key(self):
        proj = _project()
        ignore_suggestion("test-key", proj)
        assert "test-key" in proj.ignored_suggestion_keys

    def test_unignore_removes_key(self):
        proj = _project()
        proj.ignored_suggestion_keys.append("test-key")
        unignore_suggestion("test-key", proj)
        assert "test-key" not in proj.ignored_suggestion_keys

    def test_ignore_removes_from_applied(self):
        proj = _project()
        proj.applied_suggestion_keys.append("test-key")
        ignore_suggestion("test-key", proj)
        assert "test-key" not in proj.applied_suggestion_keys
        assert "test-key" in proj.ignored_suggestion_keys


# ---------------------------------------------------------------------------
# Model v2 backwards compatibility
# ---------------------------------------------------------------------------

class TestModelBackwardsCompat:

    def test_v1_project_loads_with_defaults(self):
        """V1 project.json uten nye felt skal laste med defaults."""
        v1_data = {
            "schema_version": 1,
            "project_id": "p1", "client": "Old", "year": "2024",
            "created_at": 0, "updated_at": 0, "parent_company_id": "",
            "companies": [{
                "company_id": "c1", "name": "Foo", "source_file": "",
                "source_type": "excel", "imported_at": 0,
                "row_count": 5, "has_ib": True,
            }],
            "mapping_config": {},
            "eliminations": [{
                "journal_id": "j1", "name": "Old journal",
                "created_at": 0, "lines": [
                    {"regnr": 10, "company_id": "c1", "amount": 100.0, "description": "Test"},
                ],
            }],
            "runs": [],
        }
        proj = project_from_dict(v1_data)
        # Nye Company-felt
        assert proj.companies[0].currency_code == ""
        assert proj.companies[0].closing_rate == 1.0
        # Nye Project-felt
        assert proj.reporting_currency == "NOK"
        assert proj.match_tolerance_nok == 1000.0
        assert proj.ignored_suggestion_keys == []
        # Nye Journal-felt
        j = proj.eliminations[0]
        assert j.kind == "manual"
        assert j.source_suggestion_key == ""
        assert j.status == "active"
        # Nye Line-felt
        line = j.lines[0]
        assert line.counterparty_company_id == ""
        assert line.source_suggestion_key == ""

    def test_v2_roundtrip(self):
        """V2 prosjekt med alle nye felt roundtripper korrekt."""
        proj = ConsolidationProject(
            client="V2", year="2025",
            reporting_currency="SEK",
            match_tolerance_nok=500.0,
            fx_gain_regnr=810,
            fx_loss_regnr=820,
            ignored_suggestion_keys=["key1"],
            applied_suggestion_keys=["key2"],
            companies=[
                CompanyTB(
                    company_id="c1", name="Test",
                    currency_code="SEK", closing_rate=0.95, average_rate=0.97,
                ),
            ],
            eliminations=[
                EliminationJournal(
                    journal_id="j1", name="From suggestion",
                    kind="from_suggestion",
                    source_suggestion_key="key2",
                    status="active",
                    lines=[
                        EliminationLine(
                            regnr=10, company_id="c1", amount=-500.0,
                            counterparty_company_id="c2",
                            source_suggestion_key="key2",
                            source_currency="SEK",
                            source_amount=-526.0,
                            fx_rate_used=0.95,
                        ),
                    ],
                ),
            ],
        )
        d = project_to_dict(proj)
        restored = project_from_dict(d)

        assert restored.reporting_currency == "SEK"
        assert restored.match_tolerance_nok == 500.0
        assert restored.fx_gain_regnr == 810
        assert restored.ignored_suggestion_keys == ["key1"]
        assert restored.applied_suggestion_keys == ["key2"]

        c = restored.companies[0]
        assert c.currency_code == "SEK"
        assert c.closing_rate == 0.95

        j = restored.eliminations[0]
        assert j.kind == "from_suggestion"
        assert j.source_suggestion_key == "key2"

        line = j.lines[0]
        assert line.counterparty_company_id == "c2"
        assert line.source_currency == "SEK"
        assert line.fx_rate_used == 0.95

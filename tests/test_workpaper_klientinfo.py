"""Tester for workpaper_klientinfo — navnematching + arkbygging."""

from __future__ import annotations

import pytest

import src.shared.workpapers.klientinfo as wk
from src.shared.workpapers.klientinfo import (
    CrossMatch,
    build_conclusion_text,
    build_cross_matches,
    normalize_person_name,
    owner_birth_year,
    _fmt_roles_natural,
)


# ---------------------------------------------------------------------------
# Navnematching


class TestNormalizePersonName:
    def test_casefold_and_strip(self) -> None:
        assert normalize_person_name("  Ola Nordmann ") == normalize_person_name("ola nordmann")

    def test_handles_special_chars(self) -> None:
        assert normalize_person_name("Kåre Ødegård") == normalize_person_name("kåre ødegård")

    def test_order_invariant(self) -> None:
        assert normalize_person_name("Ola Nordmann") == normalize_person_name("Nordmann, Ola")

    def test_punct_collapse(self) -> None:
        assert normalize_person_name("Ola-Marie Hansen") == normalize_person_name("Ola Marie Hansen")

    def test_empty(self) -> None:
        assert normalize_person_name("") == ""
        assert normalize_person_name(None) == ""


# ---------------------------------------------------------------------------
# Kryssreferanse


class TestOwnerBirthYear:
    def test_four_digit_year(self) -> None:
        assert owner_birth_year({"shareholder_kind": "person", "shareholder_orgnr": "1970"}) == "1970"

    def test_fnr_1900s(self) -> None:
        # DDMMYY=120570, individ=345 (<500) ⇒ 1970
        assert owner_birth_year({"shareholder_kind": "person", "shareholder_orgnr": "12057034512"}) == "1970"

    def test_fnr_2000s(self) -> None:
        # DDMMYY=120510, individ=789 (≥500) ⇒ 2010
        assert owner_birth_year({"shareholder_kind": "person", "shareholder_orgnr": "12051078901"}) == "2010"

    def test_company_orgnr_no_year(self) -> None:
        assert owner_birth_year({"shareholder_kind": "company", "shareholder_orgnr": "915321445"}) == ""

    def test_missing(self) -> None:
        assert owner_birth_year({"shareholder_kind": "person", "shareholder_orgnr": ""}) == ""


class TestCrossMatches:
    def test_owner_that_is_also_dagl(self) -> None:
        owners = [
            {
                "shareholder_name": "Ola Nordmann",
                "shareholder_orgnr": "",
                "shareholder_kind": "person",
                "ownership_pct": 60.0,
            },
            {
                "shareholder_name": "Holding AS",
                "shareholder_orgnr": "999999999",
                "shareholder_kind": "enhet",
                "ownership_pct": 40.0,
            },
        ]
        roller = [
            {"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Ola Nordmann", "fodselsdato": "1970-05-12"},
            {"rolle": "Styreleder", "rolle_kode": "LEDE", "navn": "Kari Hansen", "fodselsdato": ""},
        ]
        matches = build_cross_matches(owners, roller)
        assert len(matches) == 1
        m = matches[0]
        assert isinstance(m, CrossMatch)
        assert m.shareholder_name == "Ola Nordmann"
        assert m.ownership_pct == 60.0
        assert m.roles == ["Daglig leder"]

    def test_owner_with_multiple_roles(self) -> None:
        owners = [{"shareholder_name": "Kari Hansen", "shareholder_kind": "person", "ownership_pct": 100.0}]
        roller = [
            {"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Kari Hansen", "fodselsdato": ""},
            {"rolle": "Styreleder", "rolle_kode": "LEDE", "navn": "Kari Hansen", "fodselsdato": ""},
        ]
        matches = build_cross_matches(owners, roller)
        assert len(matches) == 1
        assert matches[0].roles == ["Daglig leder", "Styreleder"]

    def test_no_match_when_no_overlap(self) -> None:
        owners = [{"shareholder_name": "Ola Nordmann", "ownership_pct": 100.0}]
        roller = [{"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Kari Hansen", "fodselsdato": ""}]
        assert build_cross_matches(owners, roller) == []

    def test_sort_descending_by_pct(self) -> None:
        owners = [
            {"shareholder_name": "Liten Eier", "ownership_pct": 10.0},
            {"shareholder_name": "Stor Eier", "ownership_pct": 80.0},
        ]
        roller = [
            {"rolle": "DL", "rolle_kode": "DAGL", "navn": "Liten Eier", "fodselsdato": ""},
            {"rolle": "Styreleder", "rolle_kode": "LEDE", "navn": "Stor Eier", "fodselsdato": ""},
        ]
        matches = build_cross_matches(owners, roller)
        assert [m.shareholder_name for m in matches] == ["Stor Eier", "Liten Eier"]

    def test_empty_inputs(self) -> None:
        assert build_cross_matches([], []) == []
        assert build_cross_matches(None, None) == []

    def test_name_order_invariant_match(self) -> None:
        owners = [{"shareholder_name": "Nordmann, Ola", "ownership_pct": 55.0}]
        roller = [{"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Ola Nordmann", "fodselsdato": ""}]
        matches = build_cross_matches(owners, roller)
        assert len(matches) == 1
        assert matches[0].roles == ["Daglig leder"]

    def test_birth_year_match_upgrades_confidence(self) -> None:
        owners = [{
            "shareholder_name": "Ola Nordmann",
            "shareholder_kind": "person",
            "shareholder_orgnr": "1970",
            "ownership_pct": 60.0,
        }]
        roller = [{"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Ola Nordmann", "fodselsdato": "1970-05-12"}]
        matches = build_cross_matches(owners, roller)
        assert matches[0].match_confidence == "Bekreftet"

    def test_birth_year_mismatch_keeps_navn_match_with_note(self) -> None:
        owners = [{
            "shareholder_name": "Ola Nordmann",
            "shareholder_kind": "person",
            "shareholder_orgnr": "1980",
            "ownership_pct": 60.0,
        }]
        roller = [{"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Ola Nordmann", "fodselsdato": "1970-05-12"}]
        matches = build_cross_matches(owners, roller)
        assert matches[0].match_confidence == "Navn-match"
        assert "1980" in matches[0].notat and "1970" in matches[0].notat

    def test_company_shareholder_matched_on_name(self) -> None:
        owners = [{
            "shareholder_name": "Holding AS",
            "shareholder_kind": "company",
            "shareholder_orgnr": "999999999",
            "ownership_pct": 100.0,
        }]
        roller = [{"rolle": "Styreleder", "rolle_kode": "LEDE", "navn": "Holding AS", "fodselsdato": ""}]
        matches = build_cross_matches(owners, roller)
        assert len(matches) == 1
        # Firmaer har ikke fødselsår → forblir "Navn-match"
        assert matches[0].match_confidence == "Navn-match"


# ---------------------------------------------------------------------------
# Indirekte match via holdingselskap


class TestIndirectCrossMatches:
    def test_indirect_via_holding(self) -> None:
        owners = [
            {
                "shareholder_name": "JOZANI HOLDING AS",
                "shareholder_orgnr": "914601819",
                "shareholder_kind": "company",
                "ownership_pct": 33.33,
            },
        ]
        roller = [
            {"rolle": "Styremedlem", "rolle_kode": "MEDL",
             "navn": "Sorush Ghiasvand Jozani", "fodselsdato": "1987-03-10"},
        ]
        holding_owners = {
            "914601819": [
                {"shareholder_name": "Sorush Ghiasvand Jozani",
                 "shareholder_kind": "person",
                 "shareholder_orgnr": "1987",
                 "ownership_pct": 100.0},
            ]
        }
        matches = build_cross_matches(
            owners, roller, indirect_owners_fn=lambda o: holding_owners.get(o, []),
        )
        assert len(matches) == 1
        m = matches[0]
        assert m.match_type == "indirect"
        assert m.via == "JOZANI HOLDING AS"
        assert m.shareholder_name == "Sorush Ghiasvand Jozani"
        assert m.match_confidence == "Bekreftet"  # fødselsår matcher
        assert m.roles == ["Styremedlem"]
        # effektiv pct = 100 × 33.33 / 100 = 33.33
        assert m.ownership_pct == pytest.approx(33.33)
        assert "JOZANI HOLDING AS" in m.notat

    def test_effective_pct_with_partial_holding_ownership(self) -> None:
        owners = [{
            "shareholder_name": "Holding AS",
            "shareholder_orgnr": "999999999",
            "shareholder_kind": "company",
            "ownership_pct": 60.0,
        }]
        roller = [{"rolle": "Daglig leder", "rolle_kode": "DAGL",
                   "navn": "Ola Nordmann", "fodselsdato": ""}]
        holding_owners = {
            "999999999": [
                {"shareholder_name": "Ola Nordmann", "shareholder_kind": "person",
                 "ownership_pct": 50.0},
            ]
        }
        matches = build_cross_matches(
            owners, roller, indirect_owners_fn=lambda o: holding_owners.get(o, []),
        )
        # 50% av 60% = 30%
        assert matches[0].ownership_pct == pytest.approx(30.0)

    def test_direct_sorted_before_indirect(self) -> None:
        owners = [
            {"shareholder_name": "Kari Hansen", "shareholder_kind": "person",
             "ownership_pct": 10.0},
            {"shareholder_name": "Holding AS", "shareholder_orgnr": "999",
             "shareholder_kind": "company", "ownership_pct": 90.0},
        ]
        roller = [
            {"rolle": "Daglig leder", "rolle_kode": "DAGL",
             "navn": "Kari Hansen", "fodselsdato": ""},
            {"rolle": "Styreleder", "rolle_kode": "LEDE",
             "navn": "Ola Nordmann", "fodselsdato": ""},
        ]
        holding_owners = {
            "999": [{"shareholder_name": "Ola Nordmann",
                     "shareholder_kind": "person", "ownership_pct": 100.0}],
        }
        matches = build_cross_matches(
            owners, roller, indirect_owners_fn=lambda o: holding_owners.get(o, []),
        )
        # Direkte (Kari 10%) først selv om indirekte Ola har større effektiv pct (90%).
        assert [m.match_type for m in matches] == ["direct", "indirect"]
        assert matches[0].shareholder_name == "Kari Hansen"
        assert matches[1].shareholder_name == "Ola Nordmann"

    def test_no_indirect_when_no_callback(self) -> None:
        owners = [{"shareholder_name": "Holding AS", "shareholder_orgnr": "999",
                   "shareholder_kind": "company", "ownership_pct": 100.0}]
        roller = [{"rolle": "DL", "rolle_kode": "DAGL", "navn": "X", "fodselsdato": ""}]
        # Uten callback → ingen indirekte lookup, ingen match.
        assert build_cross_matches(owners, roller) == []

    def test_indirect_skips_when_orgnr_missing(self) -> None:
        owners = [{"shareholder_name": "Holding", "shareholder_orgnr": "",
                   "shareholder_kind": "company", "ownership_pct": 100.0}]
        roller = [{"rolle": "DL", "rolle_kode": "DAGL", "navn": "X", "fodselsdato": ""}]
        called = []
        build_cross_matches(
            owners, roller,
            indirect_owners_fn=lambda o: called.append(o) or [],
        )
        assert called == []  # ingen orgnr → ingen oppslag

    def test_indirect_tolerates_callback_exception(self) -> None:
        owners = [{"shareholder_name": "Holding", "shareholder_orgnr": "123",
                   "shareholder_kind": "company", "ownership_pct": 100.0}]
        roller = [{"rolle": "DL", "rolle_kode": "DAGL", "navn": "X", "fodselsdato": ""}]

        def _boom(_o: str) -> list[dict]:
            raise RuntimeError("db offline")

        assert build_cross_matches(owners, roller, indirect_owners_fn=_boom) == []

    def test_indirect_person_shareholder_is_not_expanded(self) -> None:
        """Kun selskaps-aksjonærer skal trigge indirekte oppslag."""
        owners = [{"shareholder_name": "Ola Nordmann", "shareholder_kind": "person",
                   "shareholder_orgnr": "12057034512", "ownership_pct": 100.0}]
        roller = [{"rolle": "DL", "rolle_kode": "DAGL", "navn": "Kari Hansen",
                   "fodselsdato": ""}]
        called = []
        build_cross_matches(
            owners, roller,
            indirect_owners_fn=lambda o: called.append(o) or [],
        )
        assert called == []


# ---------------------------------------------------------------------------
# Formatering + konklusjonstekst


class TestFormatRolesNatural:
    def test_single(self) -> None:
        assert _fmt_roles_natural(["Daglig leder"]) == "Daglig leder"

    def test_two(self) -> None:
        assert _fmt_roles_natural(["Daglig leder", "Styrets leder"]) \
            == "Daglig leder og styrets leder"

    def test_three(self) -> None:
        assert _fmt_roles_natural(["Daglig leder", "Styrets leder", "Styremedlem"]) \
            == "Daglig leder, styrets leder og styremedlem"

    def test_empty_fallback(self) -> None:
        assert _fmt_roles_natural([]) == "Rolleinnehaver"
        assert _fmt_roles_natural(["", "  "]) == "Rolleinnehaver"


class TestConclusionText:
    def test_empty_matches_gives_clean_state_sentence(self) -> None:
        text = build_conclusion_text([])
        assert "Ingen" in text
        assert "roller" in text.lower()

    def test_direct_match_produces_natural_sentence(self) -> None:
        owners = [{"shareholder_name": "Ola Nordmann", "shareholder_kind": "person",
                   "ownership_pct": 60.0}]
        roller = [
            {"rolle": "Daglig leder", "rolle_kode": "DAGL",
             "navn": "Ola Nordmann", "fodselsdato": ""},
            {"rolle": "Styrets leder", "rolle_kode": "LEDE",
             "navn": "Ola Nordmann", "fodselsdato": ""},
        ]
        matches = build_cross_matches(owners, roller)
        text = build_conclusion_text(matches)
        assert "Daglig leder og styrets leder Ola Nordmann" in text
        assert "direkte aksjonær" in text
        assert "60,00 %" in text

    def test_indirect_match_mentions_holding(self) -> None:
        owners = [{"shareholder_name": "JOZANI HOLDING AS",
                   "shareholder_orgnr": "914601819",
                   "shareholder_kind": "company", "ownership_pct": 33.33}]
        roller = [{"rolle": "Styremedlem", "rolle_kode": "MEDL",
                   "navn": "Sorush Jozani", "fodselsdato": ""}]
        holding_owners = {"914601819": [
            {"shareholder_name": "Sorush Jozani", "shareholder_kind": "person",
             "ownership_pct": 100.0},
        ]}
        matches = build_cross_matches(
            owners, roller,
            indirect_owners_fn=lambda o: holding_owners.get(o, []),
        )
        text = build_conclusion_text(matches)
        assert "indirekte aksjonær" in text
        assert "JOZANI HOLDING AS" in text
        assert "33,33 %" in text

    def test_navn_match_produces_plain_sentence(self) -> None:
        owners = [{"shareholder_name": "Ola Nordmann", "shareholder_kind": "person",
                   "ownership_pct": 50.0}]
        roller = [{"rolle": "Daglig leder", "rolle_kode": "DAGL",
                   "navn": "Ola Nordmann", "fodselsdato": ""}]
        matches = build_cross_matches(owners, roller)
        text = build_conclusion_text(matches)
        assert "Ola Nordmann" in text and "direkte aksjonær" in text
        # Ingen verifiserings-advarsel på forsiden.
        assert "verifiseres" not in text


# ---------------------------------------------------------------------------
# Multi-level (max_indirect_depth)


class TestMultiLevelIndirect:
    def test_two_levels_deep(self) -> None:
        """Rolleinnehaver eier mellom-holding som eier holding som eier klient."""
        owners = [{"shareholder_name": "TOPP HOLDING AS",
                   "shareholder_orgnr": "111111111",
                   "shareholder_kind": "company", "ownership_pct": 50.0}]
        roller = [{"rolle": "Daglig leder", "rolle_kode": "DAGL",
                   "navn": "Ola Eier", "fodselsdato": ""}]
        # TOPP eies 100% av MELLOM-HOLDING; MELLOM-HOLDING eies 40% av Ola Eier
        def _lookup(orgnr: str) -> list[dict]:
            if orgnr == "111111111":
                return [{"shareholder_name": "MELLOM HOLDING AS",
                         "shareholder_orgnr": "222222222",
                         "shareholder_kind": "company",
                         "ownership_pct": 100.0}]
            if orgnr == "222222222":
                return [{"shareholder_name": "Ola Eier",
                         "shareholder_kind": "person",
                         "ownership_pct": 40.0}]
            return []

        matches = build_cross_matches(
            owners, roller, indirect_owners_fn=_lookup, max_indirect_depth=2,
        )
        assert len(matches) == 1
        m = matches[0]
        assert m.match_type == "indirect"
        # 40% × 100% × 50% = 20%
        assert m.ownership_pct == pytest.approx(20.0)
        assert "MELLOM HOLDING AS" in m.via or "TOPP HOLDING AS" in m.notat

    def test_depth_1_does_not_recurse_further(self) -> None:
        """Med max_depth=1 skal vi ikke finne match som ligger 2 nivåer dypt."""
        owners = [{"shareholder_name": "TOPP", "shareholder_orgnr": "111",
                   "shareholder_kind": "company", "ownership_pct": 50.0}]
        roller = [{"rolle": "DL", "rolle_kode": "DAGL",
                   "navn": "Ola Eier", "fodselsdato": ""}]

        def _lookup(orgnr: str) -> list[dict]:
            if orgnr == "111":
                return [{"shareholder_name": "MELLOM", "shareholder_orgnr": "222",
                         "shareholder_kind": "company", "ownership_pct": 100.0}]
            if orgnr == "222":
                return [{"shareholder_name": "Ola Eier",
                         "shareholder_kind": "person", "ownership_pct": 100.0}]
            return []

        matches = build_cross_matches(
            owners, roller, indirect_owners_fn=_lookup, max_indirect_depth=1,
        )
        assert matches == []

    def test_indirect_chain_three_levels(self) -> None:
        """Eierkjede med 3 holding-ledd over klient krever max_depth >= 3.

        Klient ← H1 ← H2 ← H3 ← person.
        Direkte H1 er depth=1; sub_owners-sjekk på depth=3 finner personen.
        Med depth=2 skal vi IKKE finne match (regresjonstest for tidligere
        for-restriktiv default). Med depth=5 (ny default for build_klientinfo_workpaper)
        skal vi finne den.
        """
        owners = [{
            "shareholder_name": "H1 HOLDING AS",
            "shareholder_orgnr": "111",
            "shareholder_kind": "company",
            "ownership_pct": 100.0,
        }]
        roller = [{"rolle": "Daglig leder", "rolle_kode": "DAGL",
                   "navn": "Indirekte Eier", "fodselsdato": ""}]

        def _lookup(orgnr: str) -> list[dict]:
            mapping = {
                "111": [{"shareholder_name": "H2 HOLDING AS",
                         "shareholder_orgnr": "222",
                         "shareholder_kind": "company", "ownership_pct": 100.0}],
                "222": [{"shareholder_name": "H3 HOLDING AS",
                         "shareholder_orgnr": "333",
                         "shareholder_kind": "company", "ownership_pct": 100.0}],
                "333": [{"shareholder_name": "Indirekte Eier",
                         "shareholder_kind": "person", "ownership_pct": 80.0}],
            }
            return mapping.get(orgnr, [])

        # depth=2 er for grunt — personen er 4 hopp fra klient, krever depth>=3.
        shallow = build_cross_matches(
            owners, roller, indirect_owners_fn=_lookup, max_indirect_depth=2,
        )
        assert shallow == []

        deep = build_cross_matches(
            owners, roller, indirect_owners_fn=_lookup, max_indirect_depth=5,
        )
        assert len(deep) == 1
        m = deep[0]
        assert m.match_type == "indirect"
        assert m.shareholder_name == "Indirekte Eier"
        # 80% × 100% × 100% × 100% = 80%
        assert m.ownership_pct == pytest.approx(80.0)
        # Eierkjeden skal nevnes i notatet
        assert "H1 HOLDING AS" in m.notat
        assert "H2 HOLDING AS" in m.notat or "H3 HOLDING AS" in m.notat

    def test_cycle_guard_does_not_loop_forever(self) -> None:
        owners = [{"shareholder_name": "A AS", "shareholder_orgnr": "A",
                   "shareholder_kind": "company", "ownership_pct": 100.0}]
        roller = [{"rolle": "DL", "rolle_kode": "DAGL",
                   "navn": "Ola", "fodselsdato": ""}]

        def _lookup(orgnr: str) -> list[dict]:
            # A eies av B, B eies av A (sirkulært)
            if orgnr == "A":
                return [{"shareholder_name": "B AS", "shareholder_orgnr": "B",
                         "shareholder_kind": "company", "ownership_pct": 100.0}]
            if orgnr == "B":
                return [{"shareholder_name": "A AS", "shareholder_orgnr": "A",
                         "shareholder_kind": "company", "ownership_pct": 100.0}]
            return []

        # Skal terminere uten å henge, og ikke finne noe match.
        matches = build_cross_matches(
            owners, roller, indirect_owners_fn=_lookup, max_indirect_depth=5,
        )
        assert matches == []


# ---------------------------------------------------------------------------
# Arbeidsboken


class TestBuildWorkpaper:
    def test_produces_all_sheets(self) -> None:
        wb = wk.build_klientinfo_workpaper(
            client="ACME",
            year="2025",
            client_orgnr="915321445",
            enhet={
                "navn": "ACME AS",
                "organisasjonsform": {"beskrivelse": "AS", "kode": "AS"},
                "registrertIMvaregisteret": True,
                "naeringsnavn": "Utvikling av programvare",
            },
            roller=[
                {"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Ola Nordmann", "fodselsdato": "1970-05-12"},
            ],
            owners=[
                {"shareholder_name": "Ola Nordmann", "shareholder_kind": "person", "ownership_pct": 60.0, "shares": 60, "total_shares": 100},
            ],
            owned_companies=[
                {"company_name": "Datter AS", "company_orgnr": "111111111", "ownership_pct": 100.0,
                 "relation_type": "datterselskap", "source": "accepted_register"},
            ],
            owners_year_used="2025",
        )
        assert "Oversikt" in wb.sheetnames
        assert "Roller" in wb.sheetnames
        assert "Aksjonærer" in wb.sheetnames
        assert "Kryssreferanse" in wb.sheetnames
        assert "Eide selskaper" in wb.sheetnames

    def test_survives_empty_data(self) -> None:
        wb = wk.build_klientinfo_workpaper(client="ACME", year="2025")
        assert "Oversikt" in wb.sheetnames
        # Fanen viser "ingen roller/aksjonærer" men arket finnes
        assert "Roller" in wb.sheetnames
        assert wb["Aksjonærer"]["A5"].value == "Ingen aksjonærer registrert."

    def test_konkurs_flag_rendered(self) -> None:
        wb = wk.build_klientinfo_workpaper(
            client="ACME", year="2025", client_orgnr="123",
            enhet={"navn": "ACME AS", "konkurs": True},
        )
        ws = wb["Oversikt"]
        texts = [c.value for row in ws.iter_rows() for c in row if c.value]
        assert any("Konkurs" in str(t) for t in texts)

    def test_no_fallback_owner_year_note(self) -> None:
        """Aksjonærer-arket skal ikke ha noen ekstra note-rad på A3."""
        wb = wk.build_klientinfo_workpaper(
            client="ACME", year="2025",
            owners=[{"shareholder_name": "X", "ownership_pct": 100.0}],
            owners_year_used="2024",
        )
        ws = wb["Aksjonærer"]
        assert not ws["A3"].value

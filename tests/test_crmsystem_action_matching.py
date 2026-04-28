"""Tests for crmsystem_action_matching."""

from __future__ import annotations

from src.audit_actions.crm_action_matching import (
    ActionMatch,
    RegnskapslinjeInfo,
    group_by_regnskapslinje,
    match_actions_to_regnskapslinjer,
)
from src.audit_actions.crm_actions import AuditAction

# Standard regnskapslinjer used in tests
_RL = [
    RegnskapslinjeInfo(nr="10", regnskapslinje="Salgsinntekt"),
    RegnskapslinjeInfo(nr="20", regnskapslinje="Varekostnad"),
    RegnskapslinjeInfo(nr="40", regnskapslinje="Lønnskostnad"),
    RegnskapslinjeInfo(nr="70", regnskapslinje="Annen driftskostnad"),
    RegnskapslinjeInfo(nr="605", regnskapslinje="Lager av varer og annen beholdning"),
    RegnskapslinjeInfo(nr="610", regnskapslinje="Kundefordringer"),
    RegnskapslinjeInfo(nr="655", regnskapslinje="Bankinnskudd, kontanter o.l."),
    RegnskapslinjeInfo(nr="715", regnskapslinje="Sum egenkapital"),
    RegnskapslinjeInfo(nr="780", regnskapslinje="Leverandørgjeld"),
    RegnskapslinjeInfo(nr="785", regnskapslinje="Betalbar skatt"),
    RegnskapslinjeInfo(nr="790", regnskapslinje="Skyldig offentlige avgifter"),
]


def _action(proc: str, area: str = "") -> AuditAction:
    return AuditAction(action_id=0, procedure_name=proc, area_name=area)


class TestPrefixMatch:
    def test_three_digit_prefix(self):
        [m] = match_actions_to_regnskapslinjer([_action("605 Varelager - Ukurans")], _RL)
        assert m.regnr == "605"
        assert m.match_method == "prefix"
        assert m.confidence == 1.0

    def test_leading_zero_prefix(self):
        [m] = match_actions_to_regnskapslinjer([_action("010 Salgsinntekter")], _RL)
        assert m.regnr == "10"
        assert m.match_method == "prefix"

    def test_070_prefix(self):
        [m] = match_actions_to_regnskapslinjer([_action("070 ADK - Detaljkontroll")], _RL)
        assert m.regnr == "70"
        assert m.match_method == "prefix"


class TestAliasMatch:
    def test_adk_keyword(self):
        [m] = match_actions_to_regnskapslinjer([_action("ADK - Detaljkontroll")], _RL)
        assert m.regnr == "70"
        assert m.match_method == "alias"

    def test_varelager_keyword(self):
        [m] = match_actions_to_regnskapslinjer([_action("Varelager - Ukurans")], _RL)
        assert m.regnr == "605"
        assert m.match_method == "alias"

    def test_procedure_name_beats_area_name(self):
        """ADK in procedure name should win over 'varelager' in area name."""
        [m] = match_actions_to_regnskapslinjer(
            [_action("ADK - Detaljkontroll andre driftskostnader", area="Innkjøp og varelager")],
            _RL,
        )
        assert m.regnr == "70", f"Expected 70 (ADK), got {m.regnr}"

    def test_area_fallback_when_procedure_has_no_alias(self):
        """Area name used when procedure has no alias match."""
        [m] = match_actions_to_regnskapslinjer(
            [_action("2023 - Test av kontroll", area="Innkjøp og varelager")],
            _RL,
        )
        assert m.regnr == "605"
        assert m.match_method == "alias"

    def test_longest_alias_wins(self):
        """'leverandørgjeld' (longer) should win over 'gjeld' if both match."""
        [m] = match_actions_to_regnskapslinjer([_action("Leverandørgjeld")], _RL)
        assert m.regnr == "780"


class TestFuzzyMatch:
    def test_salgsinntekter_fuzzy(self):
        [m] = match_actions_to_regnskapslinjer(
            [_action("Kontroll av salgsrutinen", area="Salg")],
            _RL,
        )
        # May match via fuzzy or alias; just check it matched to 10
        assert m.regnr == "10"

    def test_no_match_for_generic_action(self):
        [m] = match_actions_to_regnskapslinjer(
            [_action("Ledelsens overstyring av estimater og posteringer")],
            _RL,
        )
        assert m.regnr == ""


class TestGroupByRegnskapslinje:
    def test_grouping(self):
        actions = [
            _action("010 Salgsinntekter"),
            _action("ADK - Detaljkontroll"),
            _action("Ukjent handling"),
        ]
        matches = match_actions_to_regnskapslinjer(actions, _RL)
        groups = group_by_regnskapslinje(matches)
        assert "10" in groups
        assert "70" in groups
        assert "" in groups  # unmatched

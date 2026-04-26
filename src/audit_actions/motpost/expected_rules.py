from __future__ import annotations

"""Strukturerte forventningsregler for motpost-kombinasjoner.

Modellen har to lag:

* ``ExpectedRule`` — én regel peker mot én motpost-regnskapslinje.
  Arbeidsflyten er eksklusjonsbasert: alle kontoer i RL regnes som forventet,
  og ``excluded_accounts`` ramser opp eventuelle kontoer som skal skopes ut.
  ``account_mode="selected"`` + ``allowed_accounts`` beholdes bak kulissene
  for bakoverkompatibilitet med eldre lagrede regler.
* ``BalancePair`` — to motpost-RL-er som må utligne hverandre 1:1 per bilag,
  innenfor en liten toleranse (default 100 kr). Uavhengig av kilde-RL.

Regelsettet tilhører én kilde-RL + retningsvalg og persisteres via
``regnskap_client_overrides``.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import src.shared.regnskap.client_overrides as regnskap_client_overrides


AccountMode = Literal["all", "selected"]

DEFAULT_BALANCE_TOLERANCE = 100.0


@dataclass(frozen=True)
class ExpectedRule:
    target_regnr: int
    account_mode: AccountMode = "all"
    allowed_accounts: tuple[str, ...] = ()
    excluded_accounts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BalancePair:
    rl_a: int
    rl_b: int
    tolerance: float = DEFAULT_BALANCE_TOLERANCE


@dataclass(frozen=True)
class ExpectedRuleSet:
    source_regnr: int
    selected_direction: str
    rules: tuple[ExpectedRule, ...] = ()
    balance_pairs: tuple[BalancePair, ...] = ()

    def is_empty(self) -> bool:
        return not self.rules and not self.balance_pairs


def normalize_direction(value: str | None) -> str:
    text = str(value or "alle").strip().lower()
    if text.startswith("deb"):
        return "debet"
    if text.startswith("kre") or text.startswith("cre"):
        return "kredit"
    return "alle"


def _rule_from_dict(raw: dict) -> ExpectedRule | None:
    try:
        regnr = int(raw.get("target_regnr"))
    except Exception:
        return None
    mode = str(raw.get("account_mode", "all")).strip().lower()
    if mode not in ("all", "selected"):
        mode = "all"
    raw_accounts = raw.get("allowed_accounts") or []
    if not isinstance(raw_accounts, (list, tuple)):
        raw_accounts = []
    allowed: list[str] = []
    for value in raw_accounts:
        text = str(value or "").strip()
        if text and text not in allowed:
            allowed.append(text)
    raw_excluded = raw.get("excluded_accounts") or []
    if not isinstance(raw_excluded, (list, tuple)):
        raw_excluded = []
    excluded: list[str] = []
    for value in raw_excluded:
        text = str(value or "").strip()
        if text and text not in excluded:
            excluded.append(text)
    return ExpectedRule(
        target_regnr=regnr,
        account_mode=mode,  # type: ignore[arg-type]
        allowed_accounts=tuple(allowed),
        excluded_accounts=tuple(excluded),
    )


def _rule_to_dict(rule: ExpectedRule) -> dict:
    return {
        "target_regnr": int(rule.target_regnr),
        "account_mode": rule.account_mode,
        "allowed_accounts": list(rule.allowed_accounts),
        "excluded_accounts": list(rule.excluded_accounts),
    }


def _pair_from_dict(raw: dict) -> BalancePair | None:
    try:
        rl_a = int(raw.get("rl_a"))
        rl_b = int(raw.get("rl_b"))
    except Exception:
        return None
    if rl_a == rl_b:
        return None
    try:
        tol = float(raw.get("tolerance", DEFAULT_BALANCE_TOLERANCE) or 0.0)
    except Exception:
        tol = DEFAULT_BALANCE_TOLERANCE
    return BalancePair(rl_a=rl_a, rl_b=rl_b, tolerance=max(tol, 0.0))


def _pair_to_dict(pair: BalancePair) -> dict:
    return {
        "rl_a": int(pair.rl_a),
        "rl_b": int(pair.rl_b),
        "tolerance": max(float(pair.tolerance), 0.0),
    }


def empty_rule_set(source_regnr: int, selected_direction: str | None) -> ExpectedRuleSet:
    return ExpectedRuleSet(
        source_regnr=int(source_regnr),
        selected_direction=normalize_direction(selected_direction),
    )


def load_rule_set(
    client: str | None,
    *,
    source_regnr: int,
    selected_direction: str | None = None,
) -> ExpectedRuleSet:
    """Last regelsett fra klientens overrides-JSON. Tomt sett hvis ingen finnes."""
    direction = normalize_direction(selected_direction)
    if not client:
        return empty_rule_set(source_regnr, direction)

    payload = regnskap_client_overrides.load_expected_motpost_rules(
        client,
        source_regnr=int(source_regnr),
        selected_direction=direction,
    )
    rules: list[ExpectedRule] = []
    for raw in payload.get("rules", []) or []:
        if not isinstance(raw, dict):
            continue
        rule = _rule_from_dict(raw)
        if rule is not None:
            rules.append(rule)
    pairs: list[BalancePair] = []
    for raw in payload.get("balance_pairs", []) or []:
        if not isinstance(raw, dict):
            continue
        pair = _pair_from_dict(raw)
        if pair is not None:
            pairs.append(pair)
    return ExpectedRuleSet(
        source_regnr=int(source_regnr),
        selected_direction=direction,
        rules=tuple(rules),
        balance_pairs=tuple(pairs),
    )


def save_rule_set(client: str, rule_set: ExpectedRuleSet) -> Path:
    """Lagre regelsett som JSON. Regelløse sett lagres også (tom rules-liste)."""
    payload = {
        "version": 4,
        "rules": [_rule_to_dict(r) for r in rule_set.rules],
        "balance_pairs": [_pair_to_dict(p) for p in rule_set.balance_pairs],
    }
    return regnskap_client_overrides.save_expected_motpost_rules(
        client,
        source_regnr=rule_set.source_regnr,
        selected_direction=rule_set.selected_direction,
        payload=payload,
    )


def remove_rule_set(
    client: str,
    *,
    source_regnr: int,
    selected_direction: str | None = None,
) -> Path:
    """Slett lagret regelsett for (source_regnr, direction)."""
    return regnskap_client_overrides.remove_expected_motpost_rules(
        client,
        source_regnr=int(source_regnr),
        selected_direction=selected_direction,
    )


def expected_motkontoer(
    rule_set: ExpectedRuleSet | None,
    konto_regnskapslinje_map: dict[str, str] | None,
) -> set[str]:
    """Alle motkontoer som rule-settet aksepterer, utledet fra RL-mapping.

    Brukes av hovedvinduet for å farge pivot-rader grønne og legge til
    "(forventet)"-tag på kontonavn.
    """
    from .utils import _konto_str

    if rule_set is None or not rule_set.rules or not konto_regnskapslinje_map:
        return set()
    allowed: set[str] = set()
    for rule in rule_set.rules:
        try:
            regnr = int(rule.target_regnr)
        except Exception:
            continue
        kontos_in_rl: list[str] = []
        for konto, label in konto_regnskapslinje_map.items():
            head = str(label or "").strip().split(" ", 1)[0].strip()
            try:
                if int(head) != regnr:
                    continue
            except Exception:
                continue
            k = _konto_str(konto)
            if k and k not in kontos_in_rl:
                kontos_in_rl.append(k)
        if not kontos_in_rl:
            continue
        if rule.account_mode == "selected":
            whitelist = {_konto_str(k) for k in rule.allowed_accounts if _konto_str(k)}
            allowed.update(k for k in kontos_in_rl if k in whitelist)
        else:
            excluded = {_konto_str(k) for k in rule.excluded_accounts if _konto_str(k)}
            allowed.update(k for k in kontos_in_rl if k not in excluded)
    return allowed

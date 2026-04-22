from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import app_paths
import classification_config

from .suggest.alias_library import normalize_alias_term
from .suggest.rulebook import load_rulebook


def _normal_key(value: object) -> str:
    text = normalize_alias_term(value)
    for old, new in (("ø", "oe"), ("æ", "ae"), ("å", "aa")):
        text = text.replace(old, new)
    return text


@dataclass(frozen=True)
class A07RuleLearningResult:
    code: str
    term: str
    field: str
    changed: bool
    path: Path


@dataclass(frozen=True)
class A07RuleLearningBatchResult:
    results: tuple[A07RuleLearningResult, ...]
    changed_count: int
    path: Path


def _string_list(values: object) -> list[str]:
    if isinstance(values, (list, tuple, set)):
        items = values
    elif str(values or "").strip():
        items = str(values).replace(";", "\n").splitlines()
    else:
        items = ()
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        normalized = _normal_key(text)
        if not text or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(text)
    return out


def _int_list(values: object) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for raw in _string_list(values):
        try:
            value = int(str(raw).strip())
        except Exception:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _save_rulebook_document(document: dict[str, Any]) -> Path:
    path = classification_config.save_rulebook_document(document)
    try:
        classification_config.save_json(
            app_paths.data_dir() / "a07" / "global_full_a07_rulebook.json",
            document,
        )
    except Exception:
        pass
    return path


def _ensure_rule_payload(document: dict[str, Any], code: str) -> dict[str, Any]:
    rules = document.setdefault("rules", {})
    if not isinstance(rules, dict):
        rules = {}
        document["rules"] = rules
    payload = rules.get(code)
    if not isinstance(payload, dict):
        payload = {}
    rules[code] = payload
    return payload


def append_a07_rule_keywords(
    entries: object,
    *,
    exclude: bool = False,
) -> A07RuleLearningBatchResult:
    normalized_entries: list[tuple[str, str]] = []
    for entry in entries or ():
        if isinstance(entry, dict):
            code_s = str(entry.get("code") or entry.get("Kode") or "").strip()
            term_s = str(entry.get("term") or entry.get("Navn") or entry.get("name") or "").strip()
        else:
            try:
                code_raw, term_raw = entry  # type: ignore[misc]
            except Exception as exc:
                raise ValueError("Hver batch-entry maa ha A07-kode og term.") from exc
            code_s = str(code_raw or "").strip()
            term_s = str(term_raw or "").strip()
        if not code_s or not term_s:
            raise ValueError("A07-kode og term maa vaere satt.")
        normalized_entries.append((code_s, term_s))

    if not normalized_entries:
        raise ValueError("Ingen A07-regeltermer aa lagre.")

    document = classification_config.load_rulebook_document()
    target_field = "exclude_keywords" if exclude else "keywords"
    opposite_field = "keywords" if exclude else "exclude_keywords"
    result_payloads: list[tuple[str, str, bool]] = []

    for code_s, term_s in normalized_entries:
        payload = _ensure_rule_payload(document, code_s)
        payload.setdefault("label", code_s)
        normalized = _normal_key(term_s)

        target_values = _string_list(payload.get(target_field))
        opposite_values = _string_list(payload.get(opposite_field))
        original_target = list(target_values)
        original_opposite = list(opposite_values)

        target_seen = {_normal_key(value) for value in target_values}
        if normalized not in target_seen:
            target_values.append(term_s)
        opposite_values = [value for value in opposite_values if _normal_key(value) != normalized]

        payload[target_field] = target_values
        if opposite_values:
            payload[opposite_field] = opposite_values
        else:
            payload.pop(opposite_field, None)

        changed = target_values != original_target or opposite_values != original_opposite
        result_payloads.append((code_s, term_s, changed))

    path = _save_rulebook_document(document)
    results = tuple(
        A07RuleLearningResult(
            code=code_s,
            term=term_s,
            field=target_field,
            changed=changed,
            path=path,
        )
        for code_s, term_s, changed in result_payloads
    )
    return A07RuleLearningBatchResult(
        results=results,
        changed_count=sum(1 for result in results if result.changed),
        path=path,
    )


def append_a07_rule_keyword(code: object, term: object, *, exclude: bool = False) -> A07RuleLearningResult:
    batch_result = append_a07_rule_keywords([(code, term)], exclude=exclude)
    if not batch_result.results:
        raise ValueError("Ingen A07-regelterm ble lagret.")
    return batch_result.results[0]


def append_a07_rule_boost_account(code: object, account: object) -> A07RuleLearningResult:
    code_s = str(code or "").strip()
    try:
        account_i = int(str(account or "").strip())
    except Exception as exc:
        raise ValueError("Kontonummer maa vaere et heltall.") from exc
    if not code_s:
        raise ValueError("A07-kode maa vaere satt.")

    document = classification_config.load_rulebook_document()
    payload = _ensure_rule_payload(document, code_s)
    payload.setdefault("label", code_s)
    boost_accounts = _int_list(payload.get("boost_accounts"))
    changed = account_i not in boost_accounts
    if changed:
        boost_accounts.append(account_i)
    payload["boost_accounts"] = sorted(boost_accounts)
    path = _save_rulebook_document(document)
    return A07RuleLearningResult(
        code=code_s,
        term=str(account_i),
        field="boost_accounts",
        changed=changed,
        path=path,
    )


def _term_matches_name(term: object, account_name: object) -> bool:
    term_s = _normal_key(term)
    name_s = _normal_key(account_name)
    if not term_s or not name_s:
        return False
    return term_s in name_s or name_s in term_s


def evaluate_a07_rule_name_status(code: object, account_name: object, rulebook: object | None = None) -> str:
    code_s = str(code or "").strip()
    name_s = str(account_name or "").strip()
    if not code_s or not name_s:
        return ""
    if rulebook is None:
        try:
            rulebook = load_rulebook(None)
        except Exception:
            rulebook = {}
    getter = getattr(rulebook, "get", None)
    rule = getter(code_s) if callable(getter) else None
    if rule is None:
        return ""
    included = any(_term_matches_name(term, name_s) for term in getattr(rule, "keywords", ()) or ())
    excluded = any(_term_matches_name(term, name_s) for term in getattr(rule, "exclude_keywords", ()) or ())
    if included and excluded:
        return "Konflikt"
    if excluded:
        return "Ekskludert"
    if included:
        return "Inkludert"
    return ""

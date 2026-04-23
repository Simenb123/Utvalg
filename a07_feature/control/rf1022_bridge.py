from __future__ import annotations

from ..groups import a07_code_aliases

RF1022_UNKNOWN_GROUP = "uavklart_rf1022"
A07_GROUP_PREFIX = "A07_GROUP:"

RF1022_GROUP_LABELS: dict[str, str] = {
    "100_loenn_ol": "Post 100 Lønn o.l.",
    "100_refusjon": "Post 100 Refusjon",
    "111_naturalytelser": "Post 111 Naturalytelser",
    "112_pensjon": "Post 112 Pensjon",
    RF1022_UNKNOWN_GROUP: "Uavklart RF-1022",
}

RF1022_A07_BRIDGE: dict[str, tuple[str, ...]] = {
    "100_loenn_ol": (
        "fastloenn",
        "timeloenn",
        "bonus",
        "fastTillegg",
        "overtidsgodtgjoerelse",
        "feriepenger",
        "trekkILoennForFerie",
        "trekkLoennForFerie",
        "trekkloennForFerie",
        "styrehonorarOgGodtgjoerelseVerv",
        "kilometergodtgjorelseBil",
        "kilometergodtgjorelsePassasjertillegg",
        "annet",
    ),
    "100_refusjon": (
        "sumAvgiftsgrunnlagRefusjon",
    ),
    "111_naturalytelser": (
        "elektroniskKommunikasjon",
        "skattepliktigDelForsikringer",
        "bil",
        "yrkebilTjenstligbehovListepris",
    ),
    "112_pensjon": (
        "tilskuddOgPremieTilPensjon",
    ),
}

_RF1022_GROUP_BY_A07_CODE = {
    str(alias).strip().casefold(): group_id
    for group_id, codes in RF1022_A07_BRIDGE.items()
    for code in codes
    for alias in a07_code_aliases(code)
    if str(alias).strip()
}


def rf1022_group_label(group_id: object) -> str:
    group_s = str(group_id or "").strip()
    if not group_s:
        return ""
    return RF1022_GROUP_LABELS.get(group_s, group_s)


def _a07_group_pairs(rulebook_path: str | None = None) -> tuple[tuple[str, str], ...]:
    pairs: dict[str, tuple[str, str]] = {
        str(alias).strip().casefold(): (str(alias).strip(), group_id)
        for group_id, codes in RF1022_A07_BRIDGE.items()
        for code in codes
        for alias in a07_code_aliases(code)
        if str(alias).strip()
    }
    try:
        from a07_feature.suggest.rulebook import load_rulebook

        rulebook = load_rulebook(rulebook_path)
    except Exception:
        rulebook = {}
    for code, rule in (rulebook or {}).items():
        code_s = str(code or "").strip()
        if not code_s:
            continue
        group_s = str(getattr(rule, "rf1022_group", "") or "").strip()
        if not group_s:
            continue
        for alias in a07_code_aliases(code_s):
            alias_s = str(alias or "").strip()
            if alias_s:
                pairs[alias_s.casefold()] = (alias_s, group_s)
    return tuple(pairs.values())


def rf1022_group_a07_codes(group_id: object, *, rulebook_path: str | None = None) -> tuple[str, ...]:
    group_s = str(group_id or "").strip()
    if not group_s:
        return ()
    return tuple(code for code, group in _a07_group_pairs(rulebook_path) if group == group_s)


def a07_group_member_codes(code: object) -> tuple[str, ...]:
    code_s = str(code or "").strip()
    if not code_s.casefold().startswith(A07_GROUP_PREFIX.casefold()):
        return ()
    tail = code_s[len(A07_GROUP_PREFIX) :]
    members: list[str] = []
    for raw in tail.replace(";", "+").replace(",", "+").split("+"):
        member = raw.strip()
        if member:
            members.append(member)
    return tuple(members)


def resolve_a07_rf1022_group(code: object, *, rulebook_path: str | None = None) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return ""
    lookup = {
        str(member_code).strip().casefold(): str(group_id).strip()
        for member_code, group_id in _a07_group_pairs(rulebook_path)
        if str(member_code).strip() and str(group_id).strip()
    }

    members = a07_group_member_codes(code_s)
    if members:
        resolved = [lookup.get(member.casefold()) for member in members]
        if resolved and all(group for group in resolved) and len(set(resolved)) == 1:
            return str(resolved[0])
        return RF1022_UNKNOWN_GROUP

    return lookup.get(code_s.casefold(), RF1022_UNKNOWN_GROUP)

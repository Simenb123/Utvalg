from __future__ import annotations

from functools import lru_cache

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


def _rulebook_mtime_ns(rulebook_path: str | None) -> int:
    """Hent mtime for rulebook-fila. Del av cache-nøkkel så filendringer
    invaliderer cache automatisk (samme mønster som load_rulebook)."""
    try:
        from pathlib import Path

        from a07_feature.suggest.rulebook import _find_rulebook_path

        path = _find_rulebook_path(rulebook_path)
        if not path:
            return 0
        return Path(path).stat().st_mtime_ns
    except Exception:
        return 0


def _a07_group_pairs(rulebook_path: str | None = None) -> tuple[tuple[str, str], ...]:
    # Cachet fordi kalles 250+ ganger per SB-refresh (en gang per konto-klassifisering).
    # mtime er del av cache-nøkkelen så filendringer invaliderer automatisk.
    return _a07_group_pairs_cached(rulebook_path, _rulebook_mtime_ns(rulebook_path))


@lru_cache(maxsize=8)
def _a07_group_pairs_cached(
    rulebook_path: str | None, mtime_ns: int
) -> tuple[tuple[str, str], ...]:
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


def _a07_group_lookup(rulebook_path: str | None = None) -> dict[str, str]:
    """Returner pre-bygd lookup casefold(code) -> group_id.

    Brukes av resolve_a07_rf1022_group så den slipper å bygge dicten selv
    hver gang. Cache invalideres via mtime + clear_rulebook_cache().
    """
    return _a07_group_lookup_cached(rulebook_path, _rulebook_mtime_ns(rulebook_path))


@lru_cache(maxsize=8)
def _a07_group_lookup_cached(
    rulebook_path: str | None, mtime_ns: int
) -> dict[str, str]:
    return {
        str(member_code).strip().casefold(): str(group_id).strip()
        for member_code, group_id in _a07_group_pairs_cached(rulebook_path, mtime_ns)
        if str(member_code).strip() and str(group_id).strip()
    }


def _clear_group_caches() -> None:
    """Tøm rf1022-bridge-caches. Kalles fra clear_rulebook_cache()."""
    _a07_group_pairs_cached.cache_clear()
    _a07_group_lookup_cached.cache_clear()


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
    lookup = _a07_group_lookup(rulebook_path)

    members = a07_group_member_codes(code_s)
    if members:
        resolved = [lookup.get(member.casefold()) for member in members]
        if resolved and all(group for group in resolved) and len(set(resolved)) == 1:
            return str(resolved[0])
        return RF1022_UNKNOWN_GROUP

    return lookup.get(code_s.casefold(), RF1022_UNKNOWN_GROUP)

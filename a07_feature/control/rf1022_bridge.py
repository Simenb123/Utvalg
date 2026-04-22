from __future__ import annotations

RF1022_UNKNOWN_GROUP = "uavklart_rf1022"
A07_GROUP_PREFIX = "A07_GROUP:"

RF1022_A07_BRIDGE: dict[str, tuple[str, ...]] = {
    "100_loenn_ol": (
        "fastloenn",
        "timeloenn",
        "bonus",
        "fastTillegg",
        "overtidsgodtgjoerelse",
        "feriepenger",
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
    str(code).strip().casefold(): group_id
    for group_id, codes in RF1022_A07_BRIDGE.items()
    for code in codes
    if str(code).strip()
}


def rf1022_group_a07_codes(group_id: object) -> tuple[str, ...]:
    group_s = str(group_id or "").strip()
    if not group_s:
        return ()
    return tuple(RF1022_A07_BRIDGE.get(group_s, ()))


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


def resolve_a07_rf1022_group(code: object) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return ""

    members = a07_group_member_codes(code_s)
    if members:
        resolved = [_RF1022_GROUP_BY_A07_CODE.get(member.casefold()) for member in members]
        if resolved and all(group for group in resolved) and len(set(resolved)) == 1:
            return str(resolved[0])
        return RF1022_UNKNOWN_GROUP

    return _RF1022_GROUP_BY_A07_CODE.get(code_s.casefold(), RF1022_UNKNOWN_GROUP)

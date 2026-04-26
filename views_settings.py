from __future__ import annotations

import os
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import app_paths
import client_store
import formatting  # for refresh_from_prefs()


def _fmt_cfg_meta(meta: dict) -> str:
    """Kort statuslinje for importert config."""

    if not meta:
        return "(ikke importert)"

    fn = str(meta.get("filename") or "")
    ts = str(meta.get("imported_at") or "")
    sha = str(meta.get("sha256") or "")
    sha_short = (sha[:10] + "...") if sha else ""

    bits = [b for b in [fn, ts, sha_short] if b]
    return " | ".join(bits) if bits else "(importert)"


def format_admin_json_label(kind_label: str, path: Path | None) -> str:
    """Bygg label for aktiv delt JSON-baseline."""

    if path is None:
        return f"Aktiv {kind_label}-fil: (ikke funnet i datamappen)"
    return f"Aktiv {kind_label}-fil: {path}"


try:
    from preferences import load_preferences, save_preferences  # type: ignore
except Exception:  # pragma: no cover
    from preferences import load as load_preferences, save as save_preferences


@dataclass(frozen=True)
class DataSourceRow:
    id: str
    display_name: str
    group: str
    scope: str
    role: str
    kind: str
    active_location: str
    origin: str
    status: str
    description: str
    storage_guidance: str
    rebuildable: bool
    delete_safe: bool
    control_hint: str = ""
    target_type: str = "path"
    target_value: str = ""
    advanced_children: tuple["DataSourceRow", ...] = ()
    is_advanced: bool = False
    parent_id: str = ""


_GROUP_ORDER = {
    "Global adminlogikk": 0,
    "Delt klientdata": 1,
    "Lokal brukerprofil": 2,
    "Lokal mellomlagring": 3,
    "Eksterne tjenester": 4,
    "Valgfrie sidekilder": 5,
}

_GROUP_LABELS = {
    "Global adminlogikk": "Appregler",
    "Delt klientdata": "Delt arbeidsdata",
    "Lokal brukerprofil": "Min profil",
    "Lokal mellomlagring": "Lokal cache",
    "Eksterne tjenester": "Eksterne tjenester",
    "Valgfrie sidekilder": "Sidekilder",
}

_SCOPE_LABELS = {
    "shared": "Delt",
    "local": "Lokal",
    "external": "Ekstern",
    "optional": "Valgfri",
}

_SCOPE_STORAGE_GUIDANCE = {
    "shared": "Delt klientdata",
    "local": "Lokal brukerprofil",
    "external": "Ekstern tjeneste",
    "optional": "Valgfri sidekilde",
}

_STORAGE_GUIDANCE_LABELS = {
    "Delt klientdata": "Delt arbeidsdata",
    "Lokal brukerprofil": "Min profil",
    "Lokal mellomlagring": "Lokal cache",
    "Ekstern tjeneste": "Ekstern tjeneste",
    "Valgfri sidekilde": "Sidekilde",
    "Global adminlogikk": "Appregler",
}


def _scope_label(scope: str) -> str:
    return _SCOPE_LABELS.get(scope, scope)


def _group_label(group: str) -> str:
    return _GROUP_LABELS.get(group, group)


def _storage_guidance_label(text: str) -> str:
    return _STORAGE_GUIDANCE_LABELS.get(text, _group_label(text))


def _bool_label(flag: bool) -> str:
    return "Ja" if flag else "Nei"


def _path_text(path: Path | None) -> str:
    if path is None:
        return "–"
    return str(path)


def _path_status(path: Path | None, *, optional: bool = False, missing_ok: bool = False) -> str:
    if path is None:
        if optional:
            return "Valgfri"
        return "Ikke opprettet enna" if missing_ok else "Feil"
    try:
        exists = path.exists()
    except Exception:
        return "Feil"
    if exists:
        return "I bruk"
    if optional:
        return "Valgfri"
    return "Ikke opprettet enna" if missing_ok else "Feil"


def _pattern_status(directory: Path, pattern: str, *, optional: bool = False, missing_ok: bool = False) -> str:
    try:
        if directory.exists():
            for _ in directory.glob(pattern):
                return "I bruk"
    except Exception:
        return "Feil"
    if optional:
        return "Valgfri"
    return "Ikke opprettet enna" if missing_ok else "Feil"


def _aggregate_status(children: tuple[DataSourceRow, ...], *, optional: bool = False) -> str:
    statuses = [child.status for child in children]
    if any(status == "Feil" for status in statuses):
        return "Feil"
    if any(status == "I bruk" for status in statuses):
        return "I bruk"
    if optional:
        return "Valgfri"
    if any(status == "Ikke opprettet enna" for status in statuses):
        return "Ikke opprettet enna"
    return "Ikke opprettet enna"


def _row_sort_key(row: DataSourceRow) -> tuple[int, str]:
    return (_GROUP_ORDER.get(row.group, 99), row.display_name.casefold())


def _walk_data_source_rows(rows: list[DataSourceRow] | tuple[DataSourceRow, ...]):
    for row in rows:
        yield row
        yield from _walk_data_source_rows(row.advanced_children)


def _matches_scope(row: DataSourceRow, scope_filter: str) -> bool:
    return scope_filter == "all" or row.scope == scope_filter


def _flatten_children(
    rows: tuple[DataSourceRow, ...],
    *,
    include_advanced: bool,
    scope_filter: str,
) -> list[DataSourceRow]:
    if not include_advanced:
        return []
    visible: list[DataSourceRow] = []
    for row in rows:
        child_rows = _flatten_children(row.advanced_children, include_advanced=include_advanced, scope_filter=scope_filter)
        if _matches_scope(row, scope_filter) or child_rows:
            visible.append(row)
            visible.extend(child_rows)
    return visible


def flatten_data_source_rows(
    rows: list[DataSourceRow],
    *,
    include_advanced: bool = False,
    scope_filter: str = "all",
) -> list[DataSourceRow]:
    visible: list[DataSourceRow] = []
    for row in sorted(rows, key=_row_sort_key):
        child_rows = _flatten_children(row.advanced_children, include_advanced=include_advanced, scope_filter=scope_filter)
        if _matches_scope(row, scope_filter) or child_rows:
            visible.append(row)
            visible.extend(child_rows)
    return visible


def build_data_source_summary(rows: list[DataSourceRow]) -> dict[str, tuple[str, str]]:
    admin_rows = [row for row in rows if row.group == "Global adminlogikk"]
    shared_rows = [row for row in rows if row.group == "Delt klientdata"]
    profile_rows = [row for row in rows if row.group == "Lokal brukerprofil"]
    external_rows = [row for row in rows if row.scope == "external"]
    return {
        "admin": (
            f"{len(admin_rows)} globale kilder",
            "Teamoppsett og sentrale regler i appen",
        ),
        "shared": (
            f"{len(shared_rows)} delte kilder",
            "Arbeidsomrade, mapping og klientdata",
        ),
        "profile": (
            f"{len(profile_rows)} lokale kilder",
            "Dine innstillinger, presets og kolonnevalg",
        ),
        "external": (
            f"{len(external_rows)} ekstern tjeneste" + ("r" if len(external_rows) != 1 else ""),
            ", ".join(row.display_name for row in external_rows) or "Ingen",
        ),
    }


def _discover_fagchat_repo(data_dir: Path, sources_dir: Path | None) -> Path | None:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "src" / "pages" / "openai",
        here / "src" / "openai",
        here / "src" / "pages" / "fagchat" / "rag_engine",
    ]
    if sources_dir is not None:
        candidates.extend([
            sources_dir / "openai",
            sources_dir.parent / "openai",
        ])
    candidates.extend([
        data_dir.parent / "openai",
        data_dir / "openai",
        data_dir / "rag_engine",
    ])
    for candidate in candidates:
        try:
            if (candidate / "src" / "rag_assistant").is_dir():
                return candidate
        except Exception:
            continue
    return None


def build_data_source_rows() -> list[DataSourceRow]:
    data_dir = app_paths.data_dir()
    data_hint = app_paths.read_data_dir_hint()
    data_hint_file = app_paths.data_dir_hint_file()
    sources_dir = app_paths.sources_dir()
    sources_hint = app_paths.read_sources_dir_hint()
    sources_hint_file = app_paths.sources_dir_hint_file()

    def advanced_row(
        parent_id: str,
        *,
        row_id: str,
        display_name: str,
        group: str,
        scope: str,
        role: str,
        kind: str,
        active_location: str,
        origin: str,
        status: str,
        description: str,
        storage_guidance: str,
        rebuildable: bool,
        delete_safe: bool,
        control_hint: str = "",
        target_type: str = "path",
        target_value: str = "",
    ) -> DataSourceRow:
        return DataSourceRow(
            id=row_id,
            display_name=display_name,
            group=group,
            scope=scope,
            role=role,
            kind=kind,
            active_location=active_location,
            origin=origin,
            status=status,
            description=description,
            storage_guidance=storage_guidance,
            rebuildable=rebuildable,
            delete_safe=delete_safe,
            control_hint=control_hint,
            target_type=target_type,
            target_value=target_value,
            advanced_children=(),
            is_advanced=True,
            parent_id=parent_id,
        )

    try:
        clients_root = client_store.get_clients_root()
    except Exception:
        clients_root = data_dir / "clients"

    try:
        import src.shared.regnskap.config as regnskap_config

        regnskap_status = regnskap_config.get_status()
        regn_json = regnskap_status.regnskapslinjer_json_path
        kontoplan_json = regnskap_status.kontoplan_mapping_json_path
        regnskap_config_dir = regnskap_config.config_dir()
    except Exception:
        regnskap_status = None
        regnskap_config_dir = Path(__file__).resolve().parent / "config" / "regnskap"
        regn_json = regnskap_config_dir / "regnskapslinjer.json"
        kontoplan_json = regnskap_config_dir / "kontoplan_mapping.json"

    try:
        import src.pages.ar.backend.store as ar_store

        ar_db = data_dir / ar_store.GLOBAL_DIR / ar_store.DB_FILE
    except Exception:
        ar_db = data_dir / "aksjonaerregister" / "ar_index.sqlite"

    try:
        import document_control_store

        document_store = document_control_store._store_path()  # type: ignore[attr-defined]
    except Exception:
        document_store = data_dir / "document_control" / "document_control_store.json"
    document_control_dir = document_store.parent

    try:
        import preferences

        prefs_path = Path(preferences._prefs_path())  # type: ignore[attr-defined]
    except Exception:
        prefs_path = data_dir / ".session" / "preferences.json"

    try:
        import ab_prefs

        ab_presets = ab_prefs._file_path()  # type: ignore[attr-defined]
    except Exception:
        ab_presets = data_dir / "ab_presets.json"

    try:
        import column_memory

        column_memory_path = column_memory._memory_path()  # type: ignore[attr-defined]
    except Exception:
        column_memory_path = data_dir / "column_memory.json"

    try:
        import action_library

        action_library_path = action_library.library_path()
    except Exception:
        action_library_path = data_dir / "action_library.json"

    try:
        import workpaper_library

        workpaper_library_path = workpaper_library.library_path()
    except Exception:
        workpaper_library_path = data_dir / "workpaper_library.json"

    try:
        import brreg_client

        brreg_cache_path = brreg_client.cache_path()
    except Exception:
        brreg_cache_path = Path.home() / ".utvalg" / "brreg_cache.json"

    try:
        import classification_config

        rulebook_path = classification_config.resolve_rulebook_path()
        flag_catalog_path = classification_config.resolve_catalog_path()
        rl_rulebook_path = classification_config.resolve_regnskapslinje_rulebook_path()
        thresholds_path = classification_config.resolve_thresholds_path()
        account_detail_path = classification_config.resolve_account_detail_classification_path()
    except Exception:
        base = Path(__file__).resolve().parent / "config" / "classification"
        rulebook_path = base / "global_full_a07_rulebook.json"
        flag_catalog_path = base / "account_classification_catalog.json"
        rl_rulebook_path = base / "regnskapslinje_rulebook.json"
        thresholds_path = base / "thresholds.json"
        account_detail_path = base / "account_detail_classification.json"

    try:
        import team_config

        team_path = team_config._CONFIG_PATH  # type: ignore[attr-defined]
    except Exception:
        team_path = Path(__file__).resolve().parent / "config" / "team.json"

    try:
        import client_meta_index

        client_meta_path = client_meta_index._index_path()  # type: ignore[attr-defined]
    except Exception:
        client_meta_path = data_dir / "client_meta_index.json"

    try:
        import client_store as _client_store_mod

        clients_index_path = data_dir / _client_store_mod.CLIENTS_INDEX_FILE
        clients_stamp_path = data_dir / _client_store_mod.CLIENTS_INDEX_STAMP_NAME
    except Exception:
        clients_index_path = data_dir / "clients_index.json"
        clients_stamp_path = data_dir / "clients_index.stamp"

    a07_profiles_path = data_dir / "konto_klassifisering_profiles"
    voucher_index_pattern = document_control_dir / "voucher_index_<klient>_<ar>.json"

    fagchat_repo = _discover_fagchat_repo(data_dir, sources_dir)
    fagchat_library = fagchat_repo / "kildebibliotek.json" if fagchat_repo is not None else None

    regnskapslinjer_children = (
        advanced_row(
            "rules_regnskapslinjer",
            row_id="rules_regnskapslinjer_json",
            display_name="Aktiv JSON-fil",
            group="Delt klientdata",
            scope="shared",
            role="rules",
            kind="JSON",
            active_location=_path_text(regn_json),
            origin="workspace",
            status=_path_status(regn_json, missing_ok=True),
            description="Delt JSON-baseline som runtime leser direkte for regnskapslinjer.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            control_hint="Redigeres i Admin og lagres i delt datamappe.",
            target_value=str(regn_json),
        ),
    )

    kontoplan_children = (
        advanced_row(
            "rules_kontoplanmapping",
            row_id="rules_kontoplanmapping_json",
            display_name="Aktiv JSON-fil",
            group="Delt klientdata",
            scope="shared",
            role="rules",
            kind="JSON",
            active_location=_path_text(kontoplan_json),
            origin="workspace",
            status=_path_status(kontoplan_json, missing_ok=True),
            description="Delt JSON-baseline som runtime leser direkte for kontoplanmapping.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            control_hint="Redigeres i Admin og lagres i delt datamappe.",
            target_value=str(kontoplan_json),
        ),
    )

    brreg_children = (
        advanced_row(
            "brreg_lookup",
            row_id="brreg_lookup_enhet",
            display_name="Enhetsregisteret",
            group="Eksterne tjenester",
            scope="external",
            role="service",
            kind="API",
            active_location="https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}",
            origin="external_service",
            status="Ekstern",
            description="Henter enhetsinfo som navn, organisasjonsform, MVA-status, ansatte og kapital.",
            storage_guidance="Ekstern tjeneste",
            rebuildable=False,
            delete_safe=False,
            control_hint="Readonly ekstern kilde.",
            target_type="url",
            target_value="https://data.brreg.no/enhetsregisteret/api/dokumentasjon/no/index.html",
        ),
        advanced_row(
            "brreg_lookup",
            row_id="brreg_lookup_roller",
            display_name="Roller",
            group="Eksterne tjenester",
            scope="external",
            role="service",
            kind="API",
            active_location="https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}/roller",
            origin="external_service",
            status="Ekstern",
            description="Henter roller som daglig leder, styremedlemmer, revisor og regnskapsforer.",
            storage_guidance="Ekstern tjeneste",
            rebuildable=False,
            delete_safe=False,
            control_hint="Readonly ekstern kilde.",
            target_type="url",
            target_value="https://data.brreg.no/enhetsregisteret/api/dokumentasjon/no/index.html",
        ),
        advanced_row(
            "brreg_lookup",
            row_id="brreg_lookup_regnskap",
            display_name="Regnskap",
            group="Eksterne tjenester",
            scope="external",
            role="service",
            kind="API",
            active_location="https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}",
            origin="external_service",
            status="Ekstern",
            description="Henter innsendte arsregnskapstall og metadata for analyser.",
            storage_guidance="Ekstern tjeneste",
            rebuildable=False,
            delete_safe=False,
            control_hint="Readonly ekstern kilde.",
            target_type="url",
            target_value="https://data.brreg.no/regnskapsregisteret/regnskap/v3/api-docs",
        ),
    )

    sidecar_children = (
        advanced_row(
            "sidecar_fagchat",
            row_id="sidecar_sources_dir",
            display_name="Aktiv kildemappe",
            group="Valgfrie sidekilder",
            scope="optional",
            role="service",
            kind="Mappe",
            active_location=_path_text(sources_dir),
            origin="sidecar",
            status=_path_status(sources_dir, optional=True),
            description="Valgfri rot for sidekick-kilder som Fagchat og tilhorende ressurser.",
            storage_guidance="Valgfri sidekilde",
            rebuildable=False,
            delete_safe=True,
            control_hint="Velges fra denne dialogen hvis sidekilder skal brukes.",
            target_value=str(sources_dir) if sources_dir is not None else "",
        ),
        advanced_row(
            "sidecar_fagchat",
            row_id="sidecar_sources_dir_hint",
            display_name="Kildemappe-override",
            group="Valgfrie sidekilder",
            scope="optional",
            role="settings",
            kind="Hint-fil",
            active_location=_path_text(sources_hint_file),
            origin="sidecar",
            status=_path_status(sources_hint_file, optional=True),
            description=(
                f"Peker i dag til: {sources_hint}" if sources_hint is not None else
                "Teknisk override-fil for valgfrie sidekilder."
            ),
            storage_guidance="Valgfri sidekilde",
            rebuildable=True,
            delete_safe=True,
            control_hint="Kan settes eller fjernes fra denne dialogen.",
            target_value=str(sources_hint_file),
        ),
        advanced_row(
            "sidecar_fagchat",
            row_id="sidecar_fagchat_repo",
            display_name="Fagchat / RAG-repo",
            group="Valgfrie sidekilder",
            scope="optional",
            role="service",
            kind="Repo",
            active_location=_path_text(fagchat_repo),
            origin="sidecar",
            status=_path_status(fagchat_repo, optional=True),
            description="Valgfritt repo som sidekick-funksjoner bruker for QA og kildebibliotek.",
            storage_guidance="Valgfri sidekilde",
            rebuildable=False,
            delete_safe=True,
            control_hint="Holdes utenfor vanlig drift hvis sidekick ikke er i bruk.",
            target_value=str(fagchat_repo) if fagchat_repo is not None else "",
        ),
        advanced_row(
            "sidecar_fagchat",
            row_id="sidecar_fagchat_library",
            display_name="Fagchat kildebibliotek",
            group="Valgfrie sidekilder",
            scope="optional",
            role="service",
            kind="JSON",
            active_location=_path_text(fagchat_library),
            origin="sidecar",
            status=_path_status(fagchat_library, optional=True),
            description="Bibliotek over faglige dokumenter brukt av sidekick-kilder.",
            storage_guidance="Valgfri sidekilde",
            rebuildable=True,
            delete_safe=True,
            control_hint="Folger sidekick-repoet og kan ignoreres i vanlig drift.",
            target_value=str(fagchat_library) if fagchat_library is not None else "",
        ),
    )

    client_index_children = (
        advanced_row(
            "local_client_index",
            row_id="local_client_index_clients_json",
            display_name="clients_index.json",
            group="Lokal mellomlagring",
            scope="local",
            role="cache",
            kind="JSON",
            active_location=_path_text(clients_index_path),
            origin="workspace",
            status=_path_status(clients_index_path, missing_ok=True),
            description="Avledet indeks for raskere klientoppslag.",
            storage_guidance="Lokal mellomlagring",
            rebuildable=True,
            delete_safe=True,
            target_value=str(clients_index_path),
        ),
        advanced_row(
            "local_client_index",
            row_id="local_client_index_meta_json",
            display_name="client_meta_index.json",
            group="Lokal mellomlagring",
            scope="local",
            role="cache",
            kind="JSON",
            active_location=_path_text(client_meta_path),
            origin="workspace",
            status=_path_status(client_meta_path, missing_ok=True),
            description="Avledet metadata-indeks for team, orgnr og klientkort.",
            storage_guidance="Lokal mellomlagring",
            rebuildable=True,
            delete_safe=True,
            target_value=str(client_meta_path),
        ),
        advanced_row(
            "local_client_index",
            row_id="local_client_index_stamp",
            display_name="clients_index.stamp",
            group="Lokal mellomlagring",
            scope="local",
            role="cache",
            kind="Stamp",
            active_location=_path_text(clients_stamp_path),
            origin="workspace",
            status=_path_status(clients_stamp_path, missing_ok=True),
            description="Teknisk stempel brukt ved oppfrisking av klientindeks.",
            storage_guidance="Lokal mellomlagring",
            rebuildable=True,
            delete_safe=True,
            target_value=str(clients_stamp_path),
        ),
    )

    voucher_index_children = (
        advanced_row(
            "local_voucher_index",
            row_id="local_voucher_index_pattern",
            display_name="voucher_index_<klient>_<ar>.json",
            group="Lokal mellomlagring",
            scope="local",
            role="cache",
            kind="JSON",
            active_location=str(voucher_index_pattern),
            origin="workspace",
            status=_pattern_status(document_control_dir, "voucher_index_*.json", missing_ok=True),
            description="Avledet bilagsindeks per klient og ar for raskere bilagsoppslag.",
            storage_guidance="Lokal mellomlagring",
            rebuildable=True,
            delete_safe=True,
            target_value=str(document_control_dir),
        ),
    )

    rows: list[DataSourceRow] = [
        DataSourceRow(
            id="workspace",
            display_name="Arbeidsomrade",
            group="Delt klientdata",
            scope="shared",
            role="workdata",
            kind="Mappe",
            active_location=_path_text(data_dir),
            origin="workspace",
            status=_path_status(data_dir, missing_ok=True),
            description="Hovedrot for klientlager, globale imports, dokumentlager og andre arbeidsfiler.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            control_hint="Endres her i innstillinger via 'Velg datamappe'.",
            target_value=str(data_dir),
            advanced_children=(
                advanced_row(
                    "workspace",
                    row_id="workspace_data_dir_hint",
                    display_name="Datamappe-override",
                    group="Delt klientdata",
                    scope="local",
                    role="settings",
                    kind="Hint-fil",
                    active_location=_path_text(data_hint_file),
                    origin="local_profile",
                    status=_path_status(data_hint_file, missing_ok=True),
                    description=(
                        f"Peker i dag til: {data_hint}" if data_hint is not None else
                        "Teknisk override-fil som kan tvinge en annen datamappe."
                    ),
                    storage_guidance="Lokal brukerprofil",
                    rebuildable=True,
                    delete_safe=True,
                    control_hint="Kan settes eller nullstilles fra denne dialogen.",
                    target_value=str(data_hint_file),
                ),
            ),
        ),
        DataSourceRow(
            id="shared_clients_root",
            display_name="Felles klientlager",
            group="Delt klientdata",
            scope="shared",
            role="workdata",
            kind="Mappe",
            active_location=_path_text(clients_root),
            origin="workspace",
            status=_path_status(clients_root, missing_ok=True),
            description="Her lagres klientmapper, ar, versjoner, imports og arbeidsdata per klient.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            control_hint="Folger arbeidsomradet.",
            target_value=str(clients_root),
        ),
        DataSourceRow(
            id="shared_ar_db",
            display_name="Felles AR-database",
            group="Delt klientdata",
            scope="shared",
            role="workdata",
            kind="SQLite",
            active_location=_path_text(ar_db),
            origin="workspace",
            status=_path_status(ar_db, missing_ok=True),
            description="Global database med importerte aksjonaerregister-data og relasjoner.",
            storage_guidance="Delt klientdata",
            rebuildable=True,
            delete_safe=False,
            control_hint="CSV importeres under Generelt > Aksjonaerregister (AR).",
            target_value=str(ar_db),
        ),
        DataSourceRow(
            id="shared_document_control",
            display_name="Felles dokumentkontroll",
            group="Delt klientdata",
            scope="shared",
            role="workdata",
            kind="JSON",
            active_location=_path_text(document_store),
            origin="workspace",
            status=_path_status(document_store, missing_ok=True),
            description="Lagrer dokumentprofiler og koblinger brukt i dokumentkontroll-flyten.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            target_value=str(document_store),
        ),
        DataSourceRow(
            id="shared_action_library",
            display_name="Felles handlingsbibliotek",
            group="Delt klientdata",
            scope="shared",
            role="workdata",
            kind="JSON",
            active_location=_path_text(action_library_path),
            origin="workspace",
            status=_path_status(action_library_path, missing_ok=True),
            description="Delte revisjonshandlinger som teamet jobber videre pa.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            target_value=str(action_library_path),
        ),
        DataSourceRow(
            id="shared_workpaper_library",
            display_name="Felles arbeidspapirbibliotek",
            group="Delt klientdata",
            scope="shared",
            role="workdata",
            kind="JSON",
            active_location=_path_text(workpaper_library_path),
            origin="workspace",
            status=_path_status(workpaper_library_path, missing_ok=True),
            description="Delte arbeidspapirtyper og generatorreferanser.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            target_value=str(workpaper_library_path),
        ),
        DataSourceRow(
            id="shared_a07_profiles",
            display_name="Felles A07-profiler",
            group="Delt klientdata",
            scope="shared",
            role="workdata",
            kind="Mappe",
            active_location=_path_text(a07_profiles_path),
            origin="workspace",
            status=_path_status(a07_profiles_path, missing_ok=True),
            description="Klient- og arsprofiler for A07 og konto-klassifisering.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            target_value=str(a07_profiles_path),
        ),
        DataSourceRow(
            id="rules_regnskapslinjer",
            display_name="Regnskapslinjer",
            group="Delt klientdata",
            scope="shared",
            role="rules",
            kind="JSON-baseline",
            active_location=_path_text(regnskap_config_dir),
            origin="workspace",
            status=_path_status(regn_json, missing_ok=True),
            description="Felles sannhetskilde for regnskapslinjer i delt datamappe.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            control_hint="Redigeres i Admin og lagres i delt datamappe.",
            target_value=str(regnskap_config_dir),
            advanced_children=regnskapslinjer_children,
        ),
        DataSourceRow(
            id="rules_kontoplanmapping",
            display_name="Kontoplanmapping",
            group="Delt klientdata",
            scope="shared",
            role="rules",
            kind="JSON-baseline",
            active_location=_path_text(regnskap_config_dir),
            origin="workspace",
            status=_path_status(kontoplan_json, missing_ok=True),
            description="Felles sannhetskilde for kontoplanmapping i delt datamappe.",
            storage_guidance="Delt klientdata",
            rebuildable=False,
            delete_safe=False,
            control_hint="Redigeres i Admin og lagres i delt datamappe.",
            target_value=str(regnskap_config_dir),
            advanced_children=kontoplan_children,
        ),
        DataSourceRow(
            id="rules_team_config",
            display_name="Teamoppsett",
            group="Global adminlogikk",
            scope="local",
            role="rules",
            kind="JSON",
            active_location=_path_text(team_path),
            origin="repo_default",
            status=_path_status(team_path, missing_ok=True),
            description="Mapper Windows-brukere til initialer, navn og roller i appen.",
            storage_guidance="Global adminlogikk",
            rebuildable=False,
            delete_safe=False,
            target_value=str(team_path),
        ),
        DataSourceRow(
            id="rules_a07_rulebook",
            display_name="A07-regelsett",
            group="Global adminlogikk",
            scope="local",
            role="rules",
            kind="JSON",
            active_location=_path_text(rulebook_path),
            origin="repo_default",
            status=_path_status(rulebook_path, missing_ok=True),
            description="Global regelbok for A07-regler og aliaser.",
            storage_guidance="Global adminlogikk",
            rebuildable=False,
            delete_safe=False,
            control_hint="Redigeres i Admin > A07-regler.",
            target_value=str(rulebook_path),
        ),
        DataSourceRow(
            id="rules_flag_groups",
            display_name="Flagg og analysegrupper",
            group="Global adminlogikk",
            scope="local",
            role="rules",
            kind="JSON",
            active_location=_path_text(flag_catalog_path),
            origin="repo_default",
            status=_path_status(flag_catalog_path, missing_ok=True),
            description="Katalog for flagg, analysegrupper og tilhorende metadata.",
            storage_guidance="Global adminlogikk",
            rebuildable=False,
            delete_safe=False,
            control_hint="Redigeres i Admin > Flagg og grupper.",
            target_value=str(flag_catalog_path),
        ),
        DataSourceRow(
            id="rules_regnskapslinje_rulebook",
            display_name="Regnskapslinje-regelbok",
            group="Global adminlogikk",
            scope="local",
            role="rules",
            kind="JSON",
            active_location=_path_text(rl_rulebook_path),
            origin="repo_default",
            status=_path_status(rl_rulebook_path, missing_ok=True),
            description="Regler og metadata for regnskapslinjer i admin-laget.",
            storage_guidance="Global adminlogikk",
            rebuildable=False,
            delete_safe=False,
            control_hint="Redigeres i Admin > Regnskapslinjer.",
            target_value=str(rl_rulebook_path),
        ),
        DataSourceRow(
            id="rules_thresholds",
            display_name="Terskler",
            group="Global adminlogikk",
            scope="local",
            role="rules",
            kind="JSON",
            active_location=_path_text(thresholds_path),
            origin="repo_default",
            status=_path_status(thresholds_path, missing_ok=True),
            description="Globale terskler brukt i klassifisering og forslag.",
            storage_guidance="Global adminlogikk",
            rebuildable=False,
            delete_safe=False,
            control_hint="Redigeres i Admin > Terskler.",
            target_value=str(thresholds_path),
        ),
        DataSourceRow(
            id="rules_account_detail_classification",
            display_name="Kontodetalj-klassifisering",
            group="Global adminlogikk",
            scope="local",
            role="rules",
            kind="JSON",
            active_location=_path_text(account_detail_path),
            origin="repo_default",
            status=_path_status(account_detail_path, missing_ok=True),
            description="Detaljert kontoklassifisering brukt av admin- og analysefunksjoner.",
            storage_guidance="Global adminlogikk",
            rebuildable=False,
            delete_safe=False,
            control_hint="Redigeres i Admin > Kontoklassifisering.",
            target_value=str(account_detail_path),
        ),
        DataSourceRow(
            id="profile_preferences",
            display_name="Mine innstillinger",
            group="Lokal brukerprofil",
            scope="local",
            role="settings",
            kind="JSON",
            active_location=_path_text(prefs_path),
            origin="local_profile",
            status=_path_status(prefs_path, missing_ok=True),
            description="Personlige innstillinger, visningsvalg og eksportpreferanser.",
            storage_guidance="Lokal brukerprofil",
            rebuildable=False,
            delete_safe=False,
            target_value=str(prefs_path),
        ),
        DataSourceRow(
            id="profile_ab_presets",
            display_name="Mine AB-presets",
            group="Lokal brukerprofil",
            scope="local",
            role="settings",
            kind="JSON",
            active_location=_path_text(ab_presets),
            origin="local_profile",
            status=_path_status(ab_presets, missing_ok=True),
            description="Lagrede preset-oppsett for analyser og arbeidsvisninger.",
            storage_guidance="Lokal brukerprofil",
            rebuildable=False,
            delete_safe=False,
            target_value=str(ab_presets),
        ),
        DataSourceRow(
            id="profile_column_memory",
            display_name="Mine kolonnevalg",
            group="Lokal brukerprofil",
            scope="local",
            role="settings",
            kind="JSON",
            active_location=_path_text(column_memory_path),
            origin="local_profile",
            status=_path_status(column_memory_path, missing_ok=True),
            description="Laer-av-bruk-minne for kolonnekart og kildekolonner.",
            storage_guidance="Lokal brukerprofil",
            rebuildable=True,
            delete_safe=True,
            target_value=str(column_memory_path),
        ),
        DataSourceRow(
            id="local_client_index",
            display_name="Lokal klientindeks",
            group="Lokal mellomlagring",
            scope="local",
            role="cache",
            kind="Indeks",
            active_location=_path_text(client_meta_path),
            origin="workspace",
            status=_aggregate_status(client_index_children),
            description="Avledede klient- og metadataindekser for raskere oppslag i GUI-et.",
            storage_guidance="Lokal mellomlagring",
            rebuildable=True,
            delete_safe=True,
            advanced_children=client_index_children,
            target_value=str(client_meta_path),
        ),
        DataSourceRow(
            id="local_voucher_index",
            display_name="Lokal bilagsindeks",
            group="Lokal mellomlagring",
            scope="local",
            role="cache",
            kind="Indeks",
            active_location=str(voucher_index_pattern),
            origin="workspace",
            status=_aggregate_status(voucher_index_children),
            description="Avledet bilagsindeks som gjor dokumentkontroll raskere nar store bilags-PDF-er brukes.",
            storage_guidance="Lokal mellomlagring",
            rebuildable=True,
            delete_safe=True,
            advanced_children=voucher_index_children,
            target_value=str(document_control_dir),
        ),
        DataSourceRow(
            id="brreg_cache",
            display_name="Lokal BRREG-cache",
            group="Lokal mellomlagring",
            scope="local",
            role="cache",
            kind="JSON",
            active_location=_path_text(brreg_cache_path),
            origin="local_profile",
            status=_path_status(brreg_cache_path, missing_ok=True),
            description="Mellomlagring av BRREG-oppslag for a redusere nettverkskall og lastetid.",
            storage_guidance="Lokal mellomlagring",
            rebuildable=True,
            delete_safe=True,
            control_hint="Kan tommes fra denne dialogen.",
            target_value=str(brreg_cache_path),
        ),
        DataSourceRow(
            id="brreg_lookup",
            display_name="BRREG-oppslag",
            group="Eksterne tjenester",
            scope="external",
            role="service",
            kind="API",
            active_location="https://data.brreg.no",
            origin="external_service",
            status="Ekstern",
            description="Apen BRREG-integrasjon for enhet, roller og regnskap.",
            storage_guidance="Ekstern tjeneste",
            rebuildable=False,
            delete_safe=False,
            control_hint="Readonly ekstern kilde. Lokal kontroll er cache og nettverkstilgang.",
            target_type="url",
            target_value="https://data.brreg.no/enhetsregisteret/api/dokumentasjon/no/index.html",
            advanced_children=brreg_children,
        ),
        DataSourceRow(
            id="sidecar_fagchat",
            display_name="Fagchat / sidekick-kilder",
            group="Valgfrie sidekilder",
            scope="optional",
            role="service",
            kind="Sidekick",
            active_location=_path_text(fagchat_repo or sources_dir),
            origin="sidecar",
            status=_aggregate_status(sidecar_children, optional=True),
            description="Valgfrie sidekilder utenfor kjerne-appen. Kan holdes helt utenfor vanlig drift.",
            storage_guidance="Valgfri sidekilde",
            rebuildable=False,
            delete_safe=True,
            control_hint="Sett kildemappe bare hvis sidekick-funksjoner skal brukes.",
            target_value=str(fagchat_repo or sources_dir) if (fagchat_repo or sources_dir) is not None else "",
            advanced_children=sidecar_children,
        ),
    ]

    rows.sort(key=_row_sort_key)
    return rows


class SettingsView:
    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        *,
        on_data_dir_changed: Optional[Callable[[], None]] = None,
        on_clients_changed: Optional[Callable[[], None]] = None,
    ):
        self._on_data_dir_changed = on_data_dir_changed
        self._on_clients_changed = on_clients_changed
        self._logical_source_rows: list[DataSourceRow] = []
        self._source_rows: list[DataSourceRow] = []
        self._all_source_rows: dict[str, DataSourceRow] = {}
        self._source_by_id: dict[str, DataSourceRow] = {}
        self._selected_source_id: str | None = None

        self.win = tk.Toplevel(parent)
        self.win.title("Innstillinger")
        self.win.geometry("980x680")

        self.p = load_preferences() or {}

        frm = ttk.Frame(self.win, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(0, weight=1)

        self._settings_tabs = ttk.Notebook(frm)
        self._settings_tabs.grid(row=0, column=0, sticky="nsew")

        self._general_tab = ttk.Frame(self._settings_tabs, padding=12)
        self._sources_tab = ttk.Frame(self._settings_tabs, padding=12)
        self._settings_tabs.add(self._general_tab, text="Generelt")
        self._settings_tabs.add(self._sources_tab, text="Datakilder")

        self._build_general_tab(self._general_tab)
        self._build_data_sources_tab(self._sources_tab)
        self._refresh_data_sources()

        btn = ttk.Frame(frm)
        btn.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(btn, text="Lagre", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(btn, text="Avbryt", command=self.win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def _build_general_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        store = ttk.LabelFrame(parent, text="Datamappe og klienter", padding=8)
        store.pack(fill=tk.X)
        store.columnconfigure(1, weight=1)

        self.var_datadir = tk.StringVar(value=str(app_paths.data_dir()))

        ttk.Label(store, text="Datamappe:").grid(row=0, column=0, sticky="w")
        ent_dir = ttk.Entry(store, textvariable=self.var_datadir, state="readonly")
        ent_dir.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(store, text="Velg...", command=self._pick_data_dir).grid(row=0, column=2, sticky="e")

        self.lbl_clients = ttk.Label(store, text="")
        self.lbl_clients.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        btns = ttk.Frame(store)
        btns.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Opprett klient...", command=self._create_client).pack(side=tk.LEFT)
        ttk.Button(btns, text="Importer klientliste...", command=self._import_client_list).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="Bygg indeks på nytt", command=self._rebuild_client_index).pack(side=tk.LEFT, padx=(8, 0))

        self._refresh_store_info()
        grp = ttk.LabelFrame(parent, text="Hovedvisning", padding=8)
        grp.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(grp, text="Standard retning:").grid(row=0, column=0, sticky="w")
        self.cbo_dir = ttk.Combobox(grp, state="readonly", values=["Alle", "Debet", "Kredit"], width=10)
        cur_dir = str(_pref_get(self.p, "default_direction", "Alle") or "Alle")
        if cur_dir not in ("Alle", "Debet", "Kredit"):
            cur_dir = "Alle"
        self.cbo_dir.set(cur_dir)
        self.cbo_dir.grid(row=0, column=1, sticky="w", padx=(6, 0))

        exp = ttk.LabelFrame(parent, text="Eksport", padding=8)
        exp.pack(fill=tk.X, pady=(12, 0))
        self.var_export = tk.StringVar(value=str(_pref_get(self.p, "export_mode", "open_now") or "open_now"))
        ttk.Radiobutton(exp, text="Åpne i Excel nå (midlertidig fil)", value="open_now", variable=self.var_export).pack(anchor="w")
        ttk.Radiobutton(exp, text="Spør om lagringsmappe (Lagre som ...)", value="save_dialog", variable=self.var_export).pack(anchor="w")

        fmt = ttk.LabelFrame(parent, text="Formater", padding=8)
        fmt.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(fmt, text="Tusen-separator:").grid(row=0, column=0, sticky="w")
        self.cbo_th = ttk.Combobox(fmt, state="readonly", width=18, values=["Mellomrom", "Punktum", "Tynt mellomrom", "Ingen"])
        m = {" ": "Mellomrom", ".": "Punktum", "\u202f": "Tynt mellomrom", "": "Ingen"}
        self._thousands_revmap = {v: k for k, v in m.items()}
        self.cbo_th.set(m.get(str(_pref_get(self.p, "thousands_sep", " ") or " "), "Mellomrom"))
        self.cbo_th.grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(fmt, text="Desimal-separator:").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.cbo_dec = ttk.Combobox(fmt, state="readonly", width=8, values=[",", "."])
        self.cbo_dec.set(str(_pref_get(self.p, "decimal_sep", ",") or ","))
        self.cbo_dec.grid(row=0, column=3, sticky="w", padx=(6, 0))

        ttk.Label(fmt, text="Datoformat (strftime):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.ent_date = ttk.Entry(fmt, width=22)
        self.ent_date.insert(0, str(_pref_get(self.p, "date_fmt", "%d.%m.%Y") or "%d.%m.%Y"))
        self.ent_date.grid(row=1, column=1, sticky="w", pady=(8, 0))

        reg = ttk.LabelFrame(parent, text="Felles mapping", padding=8)
        reg.pack(fill=tk.X, pady=(12, 0))
        reg.columnconfigure(1, weight=1)

        ttk.Label(reg, text="Regnskapslinjer:").grid(row=0, column=0, sticky="w")
        self.lbl_regn = ttk.Label(reg, text="")
        self.lbl_regn.grid(row=0, column=1, sticky="w", padx=(6, 0), columnspan=2)

        self.lbl_regn_src = ttk.Label(reg, text="")
        self.lbl_regn_src.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        ttk.Label(reg, text="Kontoplanmapping:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.lbl_map = ttk.Label(reg, text="")
        self.lbl_map.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(6, 0), columnspan=2)

        self.lbl_map_src = ttk.Label(reg, text="")
        self.lbl_map_src.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Label(
            reg,
            text=(
                "Aktiv mapping for regnskapslinjer og kontoplan lagres i delt datamappe. "
                "Endringer i Admin skal derfor følge samme felles JSON-kilde."
            ),
            wraplength=760,
            justify="left",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        reg_btns = ttk.Frame(reg)
        reg_btns.grid(row=5, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(reg_btns, text="Åpne mappingmappe", command=self._open_global_admin_config).pack(side=tk.LEFT)
        self._refresh_regnskap_info()

        ar = ttk.LabelFrame(parent, text="Aksjonærregister (AR)", padding=8)
        ar.pack(fill=tk.X, pady=(12, 0))
        ar.columnconfigure(1, weight=1)
        ttk.Label(ar, text="Register-CSV:").grid(row=0, column=0, sticky="w")
        self.lbl_ar = ttk.Label(ar, text="")
        self.lbl_ar.grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Button(ar, text="Importer...", command=self._import_ar_registry_csv).grid(row=0, column=2, sticky="e")
        self._refresh_ar_info()


    def _build_data_sources_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(3, weight=1)
        ttk.Label(
            parent,
            text=(
                "Oversikt over hvor Utvalg leser og lagrer data. Dette er bare en oversikt og endrer ikke "
                "selve lagringsmodellen. Standardvisningen viser de viktigste kildene, mens avansert "
                "visning viser tekniske underkilder."
            ),
            wraplength=920,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        summary = ttk.Frame(parent)
        summary.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        for col in range(4):
            summary.columnconfigure(col, weight=1)

        self.var_summary_admin = tk.StringVar(value="")
        self.var_summary_admin_detail = tk.StringVar(value="")
        self.var_summary_shared = tk.StringVar(value="")
        self.var_summary_shared_detail = tk.StringVar(value="")
        self.var_summary_profile = tk.StringVar(value="")
        self.var_summary_profile_detail = tk.StringVar(value="")
        self.var_summary_external = tk.StringVar(value="")
        self.var_summary_external_detail = tk.StringVar(value="")

        cards = [
            ("Appregler", self.var_summary_admin, self.var_summary_admin_detail),
            ("Delt arbeidsdata", self.var_summary_shared, self.var_summary_shared_detail),
            ("Min profil", self.var_summary_profile, self.var_summary_profile_detail),
            ("Eksterne tjenester", self.var_summary_external, self.var_summary_external_detail),
        ]
        for idx, (title, value_var, detail_var) in enumerate(cards):
            card = ttk.LabelFrame(summary, text=title, padding=8)
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 8, 0))
            ttk.Label(card, textvariable=value_var, wraplength=200, justify="left").pack(anchor="w")
            ttk.Label(card, textvariable=detail_var, wraplength=200, justify="left").pack(anchor="w", pady=(4, 0))

        filters = ttk.LabelFrame(parent, text="Visning", padding=8)
        filters.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.var_source_filter = tk.StringVar(value="all")
        self.var_source_show_advanced = tk.BooleanVar(value=False)
        for idx, (label, value) in enumerate([
            ("Alle", "all"),
            ("Delt", "shared"),
            ("Lokal", "local"),
            ("Ekstern", "external"),
            ("Valgfri", "optional"),
        ]):
            ttk.Radiobutton(
                filters,
                text=label,
                value=value,
                variable=self.var_source_filter,
                command=self._on_source_filters_changed,
            ).grid(row=0, column=idx, sticky="w", padx=(0 if idx == 0 else 12, 0))
        ttk.Checkbutton(
            filters,
            text="Vis avansert",
            variable=self.var_source_show_advanced,
            command=self._on_source_filters_changed,
        ).grid(row=0, column=5, sticky="w", padx=(16, 0))

        list_frame = ttk.LabelFrame(parent, text="Datakilder", padding=8)
        list_frame.grid(row=3, column=0, sticky="nsew", padx=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        cols = ("name", "group", "scope", "kind", "location", "status")
        self._source_tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=18)
        for col, label, width, anchor, stretch in [
            ("name", "Navn", 220, "w", False),
            ("group", "Gruppe", 180, "w", False),
            ("scope", "Omfang", 80, "center", False),
            ("kind", "Type", 90, "w", False),
            ("location", "Plassering", 280, "w", True),
            ("status", "Status", 120, "center", False),
        ]:
            self._source_tree.heading(col, text=label)
            self._source_tree.column(col, width=width, anchor=anchor, stretch=stretch)
        self._source_tree.grid(row=0, column=0, sticky="nsew")
        self._source_tree.bind("<<TreeviewSelect>>", self._on_source_selected, add="+")
        src_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._source_tree.yview)
        src_scroll.grid(row=0, column=1, sticky="ns")
        self._source_tree.configure(yscrollcommand=src_scroll.set)

        detail = ttk.LabelFrame(parent, text="Detaljer og styring", padding=8)
        detail.grid(row=3, column=1, sticky="nsew")
        detail.columnconfigure(1, weight=1)

        self.var_source_name = tk.StringVar(value="")
        self.var_source_group = tk.StringVar(value="")
        self.var_source_kind = tk.StringVar(value="")
        self.var_source_scope = tk.StringVar(value="")
        self.var_source_status = tk.StringVar(value="")
        self.var_source_storage = tk.StringVar(value="")
        self.var_source_delete_safe = tk.StringVar(value="")
        self.var_source_rebuildable = tk.StringVar(value="")
        self.var_source_location = tk.StringVar(value="")
        self.var_source_description = tk.StringVar(value="Velg en rad til venstre for forklaring og handlinger.")
        self.var_source_control = tk.StringVar(value="")

        fields = [
            (0, "Navn:", self.var_source_name),
            (1, "Gruppe:", self.var_source_group),
            (2, "Type:", self.var_source_kind),
            (3, "Omfang:", self.var_source_scope),
            (4, "Status:", self.var_source_status),
            (5, "Bor normalt i:", self.var_source_storage),
            (6, "Kan slettes?:", self.var_source_delete_safe),
            (7, "Kan bygges opp igjen?:", self.var_source_rebuildable),
        ]
        for row_idx, label, var in fields:
            ttk.Label(detail, text=label).grid(row=row_idx, column=0, sticky="nw", pady=(6 if row_idx else 0, 0))
            ttk.Label(detail, textvariable=var, wraplength=320, justify="left").grid(row=row_idx, column=1, sticky="nw", pady=(6 if row_idx else 0, 0))

        ttk.Label(detail, text="Plassering na:").grid(row=8, column=0, sticky="nw", pady=(8, 0))
        ttk.Entry(detail, textvariable=self.var_source_location, state="readonly").grid(row=8, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(detail, text="Hva er dette?:").grid(row=9, column=0, sticky="nw", pady=(10, 0))
        ttk.Label(detail, textvariable=self.var_source_description, wraplength=320, justify="left").grid(row=9, column=1, sticky="nw", pady=(10, 0))
        ttk.Label(detail, text="Styring:").grid(row=10, column=0, sticky="nw", pady=(10, 0))
        ttk.Label(detail, textvariable=self.var_source_control, wraplength=320, justify="left").grid(row=10, column=1, sticky="nw", pady=(10, 0))

        buttons = ttk.Frame(detail)
        buttons.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        for col in range(4):
            buttons.columnconfigure(col, weight=1)
        self.btn_source_open = ttk.Button(buttons, text="Apne", command=self._open_selected_source)
        self.btn_source_open.grid(row=0, column=0, sticky="ew")
        self.btn_source_copy = ttk.Button(buttons, text="Kopier sti", command=self._copy_selected_source)
        self.btn_source_copy.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.btn_source_primary = ttk.Button(buttons, text="", command=self._run_primary_source_action)
        self.btn_source_primary.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        self.btn_source_secondary = ttk.Button(buttons, text="", command=self._run_secondary_source_action)
        self.btn_source_secondary.grid(row=0, column=3, sticky="ew", padx=(8, 0))
        self._set_source_details(None)


    def _on_source_filters_changed(self) -> None:
        self._refresh_data_sources(select_key=self._selected_source_id)

    def _refresh_source_summary(self) -> None:
        if not hasattr(self, "var_summary_admin"):
            return
        summary = build_data_source_summary(self._logical_source_rows)
        admin = summary.get("admin", ("", ""))
        shared = summary.get("shared", ("", ""))
        profile = summary.get("profile", ("", ""))
        external = summary.get("external", ("", ""))
        self.var_summary_admin.set(admin[0])
        self.var_summary_admin_detail.set(admin[1])
        self.var_summary_shared.set(shared[0])
        self.var_summary_shared_detail.set(shared[1])
        self.var_summary_profile.set(profile[0])
        self.var_summary_profile_detail.set(profile[1])
        self.var_summary_external.set(external[0])
        self.var_summary_external_detail.set(external[1])
    def _refresh_store_info(self) -> None:
        try:
            self.var_datadir.set(str(app_paths.data_dir()))
        except Exception:
            self.var_datadir.set("(ukjent)")
        try:
            n = len(client_store.list_clients())
            self.lbl_clients.configure(text=f"Klienter: {n}")
        except Exception:
            self.lbl_clients.configure(text="Klienter: (ukjent)")

    def _after_data_dir_change(self, *, select_key: str = "data_dir") -> None:
        try:
            client_store.refresh_client_cache()
        except Exception:
            pass
        self._refresh_store_info()
        self._refresh_regnskap_info()
        self._refresh_ar_info()
        self._refresh_data_sources(select_key=select_key)
        if self._on_data_dir_changed:
            try:
                self._on_data_dir_changed()
            except Exception:
                pass

    def _pick_data_dir(self) -> None:
        cur = None
        try:
            cur = str(app_paths.data_dir())
        except Exception:
            cur = None
        chosen = filedialog.askdirectory(parent=self.win, initialdir=cur or os.getcwd(), title="Velg datamappe")
        if not chosen:
            return
        p = Path(chosen)
        try:
            app_paths.write_data_dir_hint(p)
        except Exception as exc:
            messagebox.showerror("Datamappe", f"Kunne ikke lagre datamappe: {exc}", parent=self.win)
            return
        os.environ["UTVALG_DATA_DIR"] = str(p)
        self._after_data_dir_change(select_key="workspace")

    def _reset_data_dir(self) -> None:
        if not messagebox.askyesno("Datamappe", "Fjern eksplisitt datamappe-override og bruk standard plassering igjen?", parent=self.win):
            return
        try:
            app_paths.clear_data_dir_hint()
        except Exception as exc:
            messagebox.showerror("Datamappe", f"Kunne ikke fjerne datamappe-override: {exc}", parent=self.win)
            return
        os.environ.pop("UTVALG_DATA_DIR", None)
        self._after_data_dir_change(select_key="workspace_data_dir_hint")

    def _pick_sources_dir(self) -> None:
        initial = None
        try:
            current = app_paths.sources_dir()
            if current is not None:
                initial = str(current)
        except Exception:
            initial = None
        if not initial:
            try:
                initial = str(app_paths.data_dir())
            except Exception:
                initial = os.getcwd()
        chosen = filedialog.askdirectory(parent=self.win, initialdir=initial, title="Velg kildemappe")
        if not chosen:
            return
        p = Path(chosen)
        try:
            app_paths.write_sources_dir_hint(p)
        except Exception as exc:
            messagebox.showerror("Kildemappe", f"Kunne ikke lagre kildemappe: {exc}", parent=self.win)
            return
        os.environ["UTVALG_SOURCES_DIR"] = str(p)
        self._refresh_data_sources(select_key="sidecar_fagchat")

    def _reset_sources_dir(self) -> None:
        if not messagebox.askyesno("Kildemappe", "Fjern kildemappe-override og la valgfrie kilder være ukonfigurert?", parent=self.win):
            return
        try:
            app_paths.clear_sources_dir_hint()
        except Exception as exc:
            messagebox.showerror("Kildemappe", f"Kunne ikke fjerne kildemappe-override: {exc}", parent=self.win)
            return
        os.environ.pop("UTVALG_SOURCES_DIR", None)
        self._refresh_data_sources(select_key="sidecar_sources_dir_hint")

    def _create_client(self) -> None:
        name = simpledialog.askstring("Opprett klient", "Klientnavn:", parent=self.win)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        try:
            client_store.ensure_client(name)
        except Exception as exc:
            messagebox.showerror("Opprett klient", f"Kunne ikke opprette klient: {exc}", parent=self.win)
            return
        self._refresh_store_info()
        self._refresh_data_sources(select_key="shared_clients_root")
        if self._on_clients_changed:
            try:
                self._on_clients_changed()
            except Exception:
                pass

    def _import_client_list(self) -> None:
        fn = filedialog.askopenfilename(parent=self.win, title="Importer klientliste", filetypes=[("Excel", "*.xlsx *.xls"), ("Alle filer", "*.*")])
        if not fn:
            return
        try:
            from src.pages.dataset.frontend.pane_store_import_ui import import_client_list_with_progress
            import_client_list_with_progress(self.win, Path(fn))
        except Exception as exc:
            messagebox.showerror("Importer", f"Import feilet: {exc}", parent=self.win)
            return
        self._refresh_store_info()
        self._refresh_data_sources(select_key="shared_clients_root")
        if self._on_clients_changed:
            try:
                self._on_clients_changed()
            except Exception:
                pass

    def _rebuild_client_index(self) -> None:
        if not messagebox.askyesno("Bygg indeks", "Dette vil bygge klientindeksen på nytt ved å skanne mappestrukturen.\n\nFortsette?", parent=self.win):
            return
        try:
            client_store.refresh_client_cache()
        except Exception as exc:
            messagebox.showerror("Bygg indeks", f"Kunne ikke bygge indeks: {exc}", parent=self.win)
            return
        self._refresh_store_info()
        self._refresh_data_sources(select_key="shared_clients_root")
        if self._on_clients_changed:
            try:
                self._on_clients_changed()
            except Exception:
                pass

    def _refresh_regnskap_info(self) -> None:
        if not hasattr(self, "lbl_regn"):
            return
        try:
            import src.shared.regnskap.config as regnskap_config
            st = regnskap_config.get_status()
            self.lbl_regn.configure(text=_fmt_cfg_meta(st.regnskapslinjer_meta))
            self.lbl_map.configure(text=_fmt_cfg_meta(st.kontoplan_mapping_meta))
            if hasattr(self, "lbl_regn_src"):
                self.lbl_regn_src.configure(text=format_admin_json_label("regnskapslinjer", st.regnskapslinjer_json_path))
            if hasattr(self, "lbl_map_src"):
                self.lbl_map_src.configure(text=format_admin_json_label("kontoplanmapping", st.kontoplan_mapping_json_path))
        except Exception:
            self.lbl_regn.configure(text="(ukjent)")
            self.lbl_map.configure(text="(ukjent)")
            if hasattr(self, "lbl_regn_src"):
                self.lbl_regn_src.configure(text="")
            if hasattr(self, "lbl_map_src"):
                self.lbl_map_src.configure(text="")

    def _open_global_admin_config(self) -> None:
        try:
            import src.shared.regnskap.config as regnskap_config
            target = str(regnskap_config.config_dir())
        except Exception as exc:
            messagebox.showerror("Felles mapping", f"Kunne ikke finne mappingmappe: {exc}", parent=self.win)
            return
        self._open_path_or_url(target, "path")

    def _refresh_ar_info(self) -> None:
        try:
            from src.pages.ar.backend.store import list_imported_years
            years = list_imported_years()
            if years:
                self.lbl_ar.config(text=f"Importert for: {', '.join(years)}")
            else:
                self.lbl_ar.config(text="(ikke importert)")
        except Exception:
            self.lbl_ar.config(text="(ikke tilgjengelig)")

    def _import_ar_registry_csv(self) -> None:
        fn = filedialog.askopenfilename(parent=self.win, title="Importer aksjonærregister (CSV)", filetypes=[("CSV", "*.csv"), ("Alle filer", "*.*")])
        if not fn:
            return
        from src.pages.ar.backend.store import parse_year_from_filename
        default_year = parse_year_from_filename(fn)
        year = simpledialog.askstring("Aksjonærregister", "År for aksjonærregisteret:", initialvalue=default_year, parent=self.win)
        if not year:
            return
        try:
            from src.pages.ar.backend.store import import_registry_csv
            meta = import_registry_csv(Path(fn), year=str(year).strip())
            rows = meta.get("rows_read", 0)
            rels = meta.get("relations_count", 0)
            messagebox.showinfo("Aksjonærregister", f"Importert: {rows} rader, {rels} relasjoner for {year}.", parent=self.win)
        except Exception as exc:
            messagebox.showerror("Aksjonærregister", f"Kunne ikke importere: {exc}", parent=self.win)
            return
        self._refresh_ar_info()
        self._refresh_data_sources(select_key="shared_ar_db")


    def _refresh_data_sources(self, *, select_key: str | None = None) -> None:
        if not hasattr(self, "_source_tree"):
            return
        if select_key is None:
            select_key = self._selected_source_id
        self._logical_source_rows = build_data_source_rows()
        self._all_source_rows = {row.id: row for row in _walk_data_source_rows(self._logical_source_rows)}
        self._refresh_source_summary()
        scope_filter = self.var_source_filter.get() if hasattr(self, "var_source_filter") else "all"
        include_advanced = bool(self.var_source_show_advanced.get()) if hasattr(self, "var_source_show_advanced") else False
        self._source_rows = flatten_data_source_rows(
            self._logical_source_rows,
            include_advanced=include_advanced,
            scope_filter=scope_filter,
        )
        self._source_by_id = {row.id: row for row in self._source_rows}
        tree = self._source_tree
        tree.delete(*tree.get_children())
        for row in self._source_rows:
            display_name = f"↳ {row.display_name}" if row.is_advanced else row.display_name
            tree.insert(
                "",
                "end",
                iid=row.id,
                values=(display_name, _group_label(row.group), _scope_label(row.scope), row.kind, row.active_location, row.status),
            )
        if not self._source_rows:
            self._selected_source_id = None
            self._set_source_details(None)
            return
        if select_key not in self._source_by_id:
            candidate = self._all_source_rows.get(select_key or "")
            if candidate is not None and candidate.parent_id in self._source_by_id:
                select_key = candidate.parent_id
        if not select_key or select_key not in self._source_by_id:
            select_key = self._source_rows[0].id
        self._selected_source_id = select_key
        tree.selection_set(select_key)
        tree.focus(select_key)
        tree.see(select_key)
        self._set_source_details(self._source_by_id.get(select_key))

    def _selected_source_row(self) -> DataSourceRow | None:
        if not hasattr(self, "_source_tree"):
            return None
        sel = self._source_tree.selection()
        if not sel:
            return None
        row_id = str(sel[0])
        self._selected_source_id = row_id
        return self._source_by_id.get(row_id)

    def _on_source_selected(self, _event=None) -> None:
        self._set_source_details(self._selected_source_row())

    def _source_action_labels(self, row: DataSourceRow | None) -> tuple[str, str]:
        if row is None:
            return "", ""
        if row.id in {"workspace", "workspace_data_dir_hint", "shared_clients_root"}:
            return "Velg datamappe...", "Bruk standard"
        if row.id in {"sidecar_fagchat", "sidecar_sources_dir", "sidecar_sources_dir_hint", "sidecar_fagchat_repo", "sidecar_fagchat_library"}:
            return "Velg kildemappe...", "Fjern override"
        if row.id == "brreg_cache":
            return "Tøm cache", ""
        if row.id in {
            "rules_regnskapslinjer",
            "rules_regnskapslinjer_json",
            "rules_kontoplanmapping",
            "rules_kontoplanmapping_json",
            "shared_ar_db",
        }:
            return "Gå til Generelt", ""
        return "", ""

    def _set_source_details(self, row: DataSourceRow | None) -> None:
        if row is None:
            self.var_source_name.set("")
            self.var_source_group.set("")
            self.var_source_kind.set("")
            self.var_source_scope.set("")
            self.var_source_status.set("")
            self.var_source_storage.set("")
            self.var_source_delete_safe.set("")
            self.var_source_rebuildable.set("")
            self.var_source_location.set("")
            self.var_source_description.set("Velg en rad til venstre for forklaring og handlinger.")
            self.var_source_control.set("")
            self.btn_source_open.state(["disabled"])
            self.btn_source_copy.state(["disabled"])
            self.btn_source_primary.configure(text="")
            self.btn_source_primary.state(["disabled"])
            self.btn_source_secondary.configure(text="")
            self.btn_source_secondary.state(["disabled"])
            return

        self.var_source_name.set(row.display_name)
        self.var_source_group.set(_group_label(row.group))
        self.var_source_kind.set(row.kind)
        self.var_source_scope.set(_scope_label(row.scope))
        self.var_source_status.set(row.status)
        storage_text = row.storage_guidance or _SCOPE_STORAGE_GUIDANCE.get(row.scope, "")
        self.var_source_storage.set(_storage_guidance_label(storage_text))
        self.var_source_delete_safe.set(_bool_label(row.delete_safe))
        self.var_source_rebuildable.set(_bool_label(row.rebuildable))
        self.var_source_location.set(row.active_location)
        self.var_source_description.set(row.description)
        control_hint = row.control_hint or "Ingen direkte styring fra denne dialogen."
        if row.is_advanced:
            control_hint = f"Teknisk underkilde i avansert visning. {control_hint}"
        self.var_source_control.set(control_hint)

        target = row.target_value or row.active_location
        can_open = bool(target and target != "(ikke satt)")
        can_copy = bool(row.active_location and row.active_location != "(ikke satt)")
        self.btn_source_open.state(["!disabled"] if can_open else ["disabled"])
        self.btn_source_copy.state(["!disabled"] if can_copy else ["disabled"])

        primary_text, secondary_text = self._source_action_labels(row)
        self.btn_source_primary.configure(text=primary_text)
        self.btn_source_primary.state(["!disabled"] if primary_text else ["disabled"])
        self.btn_source_secondary.configure(text=secondary_text)
        self.btn_source_secondary.state(["!disabled"] if secondary_text else ["disabled"])

    def _open_path_or_url(self, target: str, target_type: str) -> None:
        if not target:
            return
        if target_type == "url":
            webbrowser.open(target)
            return
        path = Path(target)
        if path.exists():
            if hasattr(os, "startfile"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                webbrowser.open(path.resolve().as_uri())
            return
        parent = path.parent
        if parent.exists():
            if hasattr(os, "startfile"):
                os.startfile(str(parent))  # type: ignore[attr-defined]
            else:
                webbrowser.open(parent.resolve().as_uri())
            return
        messagebox.showwarning("Datakilde", "Fant ikke valgt sti.", parent=self.win)

    def _open_selected_source(self) -> None:
        row = self._selected_source_row()
        if row is None:
            return
        target = row.target_value or row.active_location
        if not target or target == "(ikke satt)":
            return
        self._open_path_or_url(target, row.target_type)

    def _copy_selected_source(self) -> None:
        row = self._selected_source_row()
        if row is None:
            return
        text = row.active_location
        if not text or text == "(ikke satt)":
            return
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(text)
            self.win.update_idletasks()
        except Exception as exc:
            messagebox.showerror("Datakilde", f"Kunne ikke kopiere sti: {exc}", parent=self.win)

    def _show_general_tab(self) -> None:
        try:
            self._settings_tabs.select(self._general_tab)
        except Exception:
            pass

    def _clear_brreg_cache(self) -> None:
        if not messagebox.askyesno("BRREG-cache", "Tomme lokal BRREG-cache og tvinge ny henting ved neste oppslag?", parent=self.win):
            return
        try:
            import brreg_client
            brreg_client.clear_cache()
        except Exception as exc:
            messagebox.showerror("BRREG-cache", f"Kunne ikke tomme cache: {exc}", parent=self.win)
            return
        self._refresh_data_sources(select_key="brreg_cache")

    def _run_primary_source_action(self) -> None:
        row = self._selected_source_row()
        if row is None:
            return
        if row.id in {"workspace", "workspace_data_dir_hint", "shared_clients_root"}:
            self._pick_data_dir()
            return
        if row.id in {"sidecar_fagchat", "sidecar_sources_dir", "sidecar_sources_dir_hint", "sidecar_fagchat_repo", "sidecar_fagchat_library"}:
            self._pick_sources_dir()
            return
        if row.id == "brreg_cache":
            self._clear_brreg_cache()
            return
        if row.id in {
            "rules_regnskapslinjer",
            "rules_regnskapslinjer_json",
            "rules_kontoplanmapping",
            "rules_kontoplanmapping_json",
            "shared_ar_db",
        }:
            self._show_general_tab()

    def _run_secondary_source_action(self) -> None:
        row = self._selected_source_row()
        if row is None:
            return
        if row.id in {"workspace", "workspace_data_dir_hint", "shared_clients_root"}:
            self._reset_data_dir()
            return
        if row.id in {"sidecar_fagchat", "sidecar_sources_dir", "sidecar_sources_dir_hint", "sidecar_fagchat_repo", "sidecar_fagchat_library"}:
            self._reset_sources_dir()

    def _save(self) -> None:
        prefs = self.p
        _pref_set(prefs, "default_direction", self.cbo_dir.get())
        _pref_set(prefs, "export_mode", self.var_export.get())
        _pref_set(prefs, "thousands_sep", self._thousands_revmap.get(self.cbo_th.get(), " "))
        _pref_set(prefs, "decimal_sep", self.cbo_dec.get())
        _pref_set(prefs, "date_fmt", self.ent_date.get().strip() or "%d.%m.%Y")
        save_preferences(prefs)

        try:
            if hasattr(formatting, "refresh_from_prefs"):
                formatting.refresh_from_prefs()
        except Exception:
            pass

        messagebox.showinfo("Lagret", "Innstillinger er lagret.", parent=self.win)
        try:
            self.win.destroy()
        except Exception:
            pass


def open_settings(
    parent: tk.Tk | tk.Toplevel,
    *,
    on_data_dir_changed: Optional[Callable[[], None]] = None,
    on_clients_changed: Optional[Callable[[], None]] = None,
) -> None:
    SettingsView(parent, on_data_dir_changed=on_data_dir_changed, on_clients_changed=on_clients_changed)

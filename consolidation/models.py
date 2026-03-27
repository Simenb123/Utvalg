"""consolidation.models – Dataklasser for konsolidering MVP.

Hierarki:
    ConsolidationProject
      ├── companies: [CompanyTB]
      ├── mapping_config: MappingConfig
      ├── eliminations: [EliminationJournal]
      │     └── lines: [EliminationLine]
      └── runs: [RunResult]
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Company TB
# ---------------------------------------------------------------------------

@dataclass
class CompanyTB:
    """En importert saldobalanse for ett selskap."""

    company_id: str = field(default_factory=_new_id)
    name: str = ""
    source_file: str = ""
    source_type: str = ""          # "excel" | "csv" | "saft"
    imported_at: float = field(default_factory=_now)
    row_count: int = 0
    has_ib: bool = False


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

@dataclass
class MappingConfig:
    """Felles mapping-konfigurasjon for konsolideringsprosjektet.

    Alle selskaper bruker samme globale intervaller + regnskapslinjer
    fra regnskap_config. Per-selskap overstyringer haaandterer avvik.
    """

    company_overrides: dict[str, dict[str, int]] = field(default_factory=dict)
    # company_id -> {konto: regnr, ...}


# ---------------------------------------------------------------------------
# Elimination
# ---------------------------------------------------------------------------

@dataclass
class EliminationLine:
    """En debet/kredit-linje i en elimineringsjournal."""

    regnr: int = 0                    # konsernlinje-nummer
    company_id: str = ""              # hvilket selskap linjen gjelder
    amount: float = 0.0              # positiv = debet, negativ = kredit
    description: str = ""


@dataclass
class EliminationJournal:
    """En navngitt elimineringsbatch (justeringslag over raa TB)."""

    journal_id: str = field(default_factory=_new_id)
    name: str = ""
    created_at: float = field(default_factory=_now)
    lines: list[EliminationLine] = field(default_factory=list)

    @property
    def is_balanced(self) -> bool:
        return abs(self.net) < 0.005

    @property
    def net(self) -> float:
        return sum(line.amount for line in self.lines)


# ---------------------------------------------------------------------------
# Run result
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    """Immutable snapshot av en konsolideringskjoering."""

    run_id: str = field(default_factory=_new_id)
    run_at: float = field(default_factory=_now)
    company_ids: list[str] = field(default_factory=list)
    elimination_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result_hash: str = ""


# ---------------------------------------------------------------------------
# Project (root container)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1


@dataclass
class ConsolidationProject:
    """Rotcontainer for ett konsolideringsprosjekt per klient/aar."""

    project_id: str = field(default_factory=_new_id)
    client: str = ""
    year: str = ""
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    companies: list[CompanyTB] = field(default_factory=list)
    mapping_config: MappingConfig = field(default_factory=MappingConfig)
    eliminations: list[EliminationJournal] = field(default_factory=list)
    runs: list[RunResult] = field(default_factory=list)

    def find_company(self, company_id: str) -> CompanyTB | None:
        for c in self.companies:
            if c.company_id == company_id:
                return c
        return None

    def find_journal(self, journal_id: str) -> EliminationJournal | None:
        for j in self.eliminations:
            if j.journal_id == journal_id:
                return j
        return None

    def touch(self) -> None:
        """Oppdater updated_at til naa."""
        self.updated_at = _now()


# ---------------------------------------------------------------------------
# Serialisering (dict <-> dataclass)
# ---------------------------------------------------------------------------

def project_to_dict(project: ConsolidationProject) -> dict[str, Any]:
    """Serialiser prosjekt til JSON-kompatibel dict."""
    d = asdict(project)
    d["schema_version"] = SCHEMA_VERSION
    return d


def project_from_dict(d: dict[str, Any]) -> ConsolidationProject:
    """Deserialiser prosjekt fra dict (lest fra project.json)."""
    # Ignorer schema_version for naa (v1 eneste versjon)
    d = dict(d)
    d.pop("schema_version", None)

    # Rebuild nested dataklasser
    companies = [CompanyTB(**c) for c in d.pop("companies", [])]

    mc_raw = d.pop("mapping_config", {})
    mapping_config = MappingConfig(
        company_overrides=mc_raw.get("company_overrides", {}),
    )

    eliminations = []
    for ej in d.pop("eliminations", []):
        lines = [EliminationLine(**el) for el in ej.pop("lines", [])]
        eliminations.append(EliminationJournal(**ej, lines=lines))

    runs = [RunResult(**r) for r in d.pop("runs", [])]

    return ConsolidationProject(
        **d,
        companies=companies,
        mapping_config=mapping_config,
        eliminations=eliminations,
        runs=runs,
    )

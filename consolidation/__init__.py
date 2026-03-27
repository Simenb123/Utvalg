"""consolidation – Konsolidering MVP.

Public API for domenemodell, lagring, TB-import, mapping,
eliminering, konsolideringsmotor og Excel-eksport.
"""

from consolidation.models import (  # noqa: F401
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    MappingConfig,
    RunResult,
    SCHEMA_VERSION,
    project_from_dict,
    project_to_dict,
)

from consolidation.storage import (  # noqa: F401
    delete_company_tb,
    delete_project,
    export_path,
    load_company_tb,
    load_project,
    project_dir,
    save_company_tb,
    save_project,
)

from consolidation.tb_import import (  # noqa: F401
    import_company_tb,
)

from consolidation.mapping import (  # noqa: F401
    ConfigNotLoadedError,
    load_shared_config,
    map_company_tb,
)

from consolidation.elimination import (  # noqa: F401
    aggregate_eliminations_by_regnr,
    journals_to_dataframe,
    validate_journal,
)

from consolidation.engine import (  # noqa: F401
    run_consolidation,
)

from consolidation.export import (  # noqa: F401
    build_consolidation_workbook,
    save_consolidation_workbook,
)

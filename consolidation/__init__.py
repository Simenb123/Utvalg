"""consolidation – Konsolidering MVP.

Public API for domenemodell, lagring, TB-import, mapping,
eliminering, konsolideringsmotor og Excel-eksport.
"""

from consolidation.models import (  # noqa: F401
    AssociateAdjustmentRow,
    AssociateCase,
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    EliminationSuggestion,
    MappingConfig,
    RunResult,
    SCHEMA_VERSION,
    SUGGESTION_KINDS,
    project_from_dict,
    project_to_dict,
)

from consolidation.storage import (  # noqa: F401
    delete_company_line_basis,
    delete_company_tb,
    delete_project,
    export_path,
    load_company_line_basis,
    load_company_tb,
    load_project,
    project_dir,
    save_company_line_basis,
    save_company_tb,
    save_project,
)

from consolidation.line_basis_import import (  # noqa: F401
    export_line_basis_template,
    import_company_line_basis,
    normalize_company_line_basis,
    validate_company_line_basis,
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

from consolidation.suggestions import (  # noqa: F401
    create_journal_from_suggestion,
    generate_suggestions,
    ignore_suggestion,
    unignore_suggestion,
)

from consolidation.pdf_line_suggestions import (  # noqa: F401
    suggest_line_basis_from_pdf,
)

from consolidation.associate_equity_method import (  # noqa: F401
    AssociateFieldSuggestion,
    build_associate_case_calculation,
    build_associate_journal,
    compute_associate_case_generation_hash,
    delete_associate_case,
    mark_associate_case_stale,
    suggest_associate_fields_from_line_basis,
    sync_associate_case_journal,
    validate_associate_case,
)

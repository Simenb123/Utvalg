from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DocumentJobInput:
    engagement_id: str = ""
    gl_import_id: str = ""
    sample_run_id: str = ""
    sample_item_id: str = ""
    task_id: str = ""
    anchor_task_id: str = ""
    voucher_no: str = ""
    document_no: str = ""
    line_ids: list[str] = field(default_factory=list)
    source_meta_json: dict[str, Any] = field(default_factory=dict)
    params_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentJobOutput:
    document_facts: dict[str, str] = field(default_factory=dict)
    field_evidence: list[dict[str, Any]] = field(default_factory=list)
    validation_messages: list[str] = field(default_factory=list)
    matched_profile: dict[str, Any] = field(default_factory=dict)
    result_file_path: str = ""
    result_json: dict[str, Any] = field(default_factory=dict)


def document_job_input_to_dict(job_input: DocumentJobInput) -> dict[str, Any]:
    return asdict(job_input)


def document_job_output_to_dict(job_output: DocumentJobOutput) -> dict[str, Any]:
    return asdict(job_output)

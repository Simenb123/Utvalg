from __future__ import annotations

from document_engine.contracts import (
    DocumentJobInput,
    DocumentJobOutput,
    document_job_input_to_dict,
    document_job_output_to_dict,
)


def test_document_job_contracts_are_serializable() -> None:
    job_input = DocumentJobInput(
        engagement_id="eng-1",
        gl_import_id="gl-1",
        sample_run_id="sr-1",
        sample_item_id="si-1",
        task_id="task-1",
        voucher_no="1001",
        document_no="INV-77",
        line_ids=["1", "2"],
        source_meta_json={"voucher_key": "1001-2025"},
        params_json={"mode": "document_control"},
    )
    job_output = DocumentJobOutput(
        document_facts={"invoice_number": "INV-77"},
        field_evidence=[{"field_name": "invoice_number", "source": "pdf_text_fitz_blocks"}],
        validation_messages=["ok"],
        matched_profile={"profile_key": "orgnr:987654321"},
        result_file_path="task-attachments/eng-1/report.pdf",
        result_json={"profile_status": "applied"},
    )

    input_dict = document_job_input_to_dict(job_input)
    output_dict = document_job_output_to_dict(job_output)

    assert input_dict["voucher_no"] == "1001"
    assert input_dict["line_ids"] == ["1", "2"]
    assert output_dict["document_facts"]["invoice_number"] == "INV-77"
    assert output_dict["matched_profile"]["profile_key"] == "orgnr:987654321"

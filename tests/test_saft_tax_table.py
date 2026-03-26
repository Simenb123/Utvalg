"""Tester for saft_tax_table – ekstraksjon av TaxTable fra SAF-T."""

from __future__ import annotations

import zipfile
from pathlib import Path

import saft_tax_table


_SAMPLE_XML_WITH_STD = """\
<?xml version="1.0" encoding="UTF-8"?>
<AuditFile xmlns="urn:StandardAuditFile-Taxation-Financial:NO">
  <Header>
    <AuditFileVersion>1.10</AuditFileVersion>
  </Header>
  <MasterFiles>
    <GeneralLedgerAccounts>
      <Account>
        <AccountID>1500</AccountID>
        <AccountDescription>Kundefordringer</AccountDescription>
      </Account>
    </GeneralLedgerAccounts>
    <TaxTable>
      <TaxTableEntry>
        <TaxCodeDetails>
          <TaxCode>1</TaxCode>
          <Description>Utgående MVA 25%</Description>
          <TaxPercentage>25.00</TaxPercentage>
          <Country>NO</Country>
          <StandardTaxCode>1</StandardTaxCode>
        </TaxCodeDetails>
      </TaxTableEntry>
      <TaxTableEntry>
        <TaxCodeDetails>
          <TaxCode>11</TaxCode>
          <Description>Inngående MVA 25%</Description>
          <TaxPercentage>25.00</TaxPercentage>
          <Country>NO</Country>
          <StandardTaxCode>11</StandardTaxCode>
        </TaxCodeDetails>
      </TaxTableEntry>
      <TaxTableEntry>
        <TaxCodeDetails>
          <TaxCode>5</TaxCode>
          <Description>Utgående MVA 15% mat</Description>
          <TaxPercentage>15.00</TaxPercentage>
          <Country>NO</Country>
          <StandardTaxCode>5</StandardTaxCode>
        </TaxCodeDetails>
      </TaxTableEntry>
    </TaxTable>
  </MasterFiles>
  <GeneralLedgerEntries>
    <NumberOfEntries>0</NumberOfEntries>
  </GeneralLedgerEntries>
</AuditFile>
"""

_SAMPLE_XML_NO_STD = """\
<?xml version="1.0" encoding="UTF-8"?>
<AuditFile>
  <MasterFiles>
    <TaxTable>
      <TaxTableEntry>
        <TaxCodeDetails>
          <TaxCode>MVA25</TaxCode>
          <Description>Utgående 25%</Description>
          <TaxPercentage>25</TaxPercentage>
        </TaxCodeDetails>
      </TaxTableEntry>
      <TaxTableEntry>
        <TaxCodeDetails>
          <TaxCode>MVA0</TaxCode>
          <Description>Ingen MVA</Description>
          <TaxPercentage>0</TaxPercentage>
        </TaxCodeDetails>
      </TaxTableEntry>
    </TaxTable>
  </MasterFiles>
</AuditFile>
"""

_SAMPLE_XML_EMPTY_TAX_TABLE = """\
<?xml version="1.0" encoding="UTF-8"?>
<AuditFile>
  <MasterFiles>
    <TaxTable/>
  </MasterFiles>
</AuditFile>
"""


def _write_xml(tmp_path: Path, content: str, name: str = "data.xml") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _write_zip(tmp_path: Path, content: str) -> Path:
    xml_path = tmp_path / "saft.xml"
    xml_path.write_text(content, encoding="utf-8")
    zip_path = tmp_path / "saft.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(xml_path, "saft.xml")
    return zip_path


def test_extract_with_standard_codes(tmp_path):
    path = _write_xml(tmp_path, _SAMPLE_XML_WITH_STD)
    entries = saft_tax_table.extract_tax_table(path)

    assert len(entries) == 3

    by_code = {e.code: e for e in entries}
    assert "1" in by_code
    assert by_code["1"].description == "Utgående MVA 25%"
    assert by_code["1"].percentage == 25.0
    assert by_code["1"].standard_code == "1"

    assert "11" in by_code
    assert by_code["11"].standard_code == "11"

    assert "5" in by_code
    assert by_code["5"].percentage == 15.0


def test_extract_without_standard_codes(tmp_path):
    path = _write_xml(tmp_path, _SAMPLE_XML_NO_STD)
    entries = saft_tax_table.extract_tax_table(path)

    assert len(entries) == 2

    by_code = {e.code: e for e in entries}
    assert "MVA25" in by_code
    assert by_code["MVA25"].standard_code == ""
    assert by_code["MVA25"].percentage == 25.0

    assert "MVA0" in by_code
    assert by_code["MVA0"].percentage == 0.0


def test_extract_empty_tax_table(tmp_path):
    path = _write_xml(tmp_path, _SAMPLE_XML_EMPTY_TAX_TABLE)
    entries = saft_tax_table.extract_tax_table(path)
    assert entries == []


def test_extract_from_zip(tmp_path):
    path = _write_zip(tmp_path, _SAMPLE_XML_WITH_STD)
    entries = saft_tax_table.extract_tax_table(path)
    assert len(entries) == 3


def test_file_not_found(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        saft_tax_table.extract_tax_table(tmp_path / "nonexistent.xml")


def test_entries_are_frozen():
    entry = saft_tax_table.TaxCodeEntry(
        code="1", description="Test", percentage=25.0, standard_code="1"
    )
    import pytest
    with pytest.raises(AttributeError):
        entry.code = "2"  # type: ignore[misc]

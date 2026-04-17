from __future__ import annotations

import classification_workspace
from classification_workspace import (
    ClassificationCurrentState,
    ClassificationFieldState,
    ClassificationProvenance,
    ClassificationQueueState,
    ClassificationSuggestedState,
    ClassificationWorkspaceItem,
)
from account_profile import AccountClassificationCatalog
from a07_feature.suggest.api import AccountUsageFeatures


def test_build_workspace_item_keeps_direct_rf1022_provenance_separate_from_a07_default(tmp_path) -> None:
    rulebook_path = tmp_path / "rulebook.json"
    rulebook_path.write_text(
        """
        {
          "rules": {
            "tilskuddOgPremieTilPensjon": {
              "label": "Pensjon",
              "keywords": ["pensjon", "otp"],
              "boost_accounts": [5940]
            }
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    catalog = AccountClassificationCatalog.from_dict(
        {
            "groups": [
                {
                    "id": "112_pensjon",
                    "label": "Post 112 Pensjon",
                    "active": True,
                    "sort_order": 10,
                    "applies_to": ["kontrolloppstilling"],
                    "aliases": ["otp"],
                }
            ],
            "tags": [],
        }
    )

    item = classification_workspace.build_workspace_item(
        account_no="5940",
        account_name="Diverse personalkostnad",
        movement=551590.0,
        catalog=catalog,
        usage=AccountUsageFeatures(
            posting_count=12,
            unique_vouchers=12,
            active_months=12,
            monthly_regularity=1.0,
            repeat_amount_ratio=0.8,
            top_text_tokens=("otp",),
        ),
        rulebook_path=str(rulebook_path),
    )

    assert item.suggested.a07_code is not None
    assert item.suggested.control_group is not None
    assert item.suggested.control_tags is not None
    assert item.suggested.control_group.provenance is not None
    assert item.suggested.control_group.provenance.derived_from is None
    assert str(item.suggested.control_group.provenance.reason).startswith("Direkte RF-1022:")
    assert item.suggested.control_tags.provenance is not None
    assert item.suggested.control_tags.provenance.derived_from == "a07_standard"

    detail = classification_workspace.format_why_panel(item)

    assert "RF-1022: kontobruk: otp" in detail["why"]
    assert "Flagg: Avledet fra A07-standard" in detail["why"]


def test_format_why_panel_explains_when_suggestion_matches_saved_values() -> None:
    blank = ClassificationFieldState(value="", display="", provenance=None)
    item = ClassificationWorkspaceItem(
        account_no="5000",
        account_name="Lonn til ansatte",
        ib=0.0,
        movement=7073783.57,
        ub=7073783.57,
        current=ClassificationCurrentState(
            a07_code=ClassificationFieldState(
                value="fastloenn",
                display="fastloenn",
                provenance=ClassificationProvenance(source="manual", reason="Lagret profil", confidence=1.0),
            ),
            control_group=ClassificationFieldState(
                value="100_loenn_ol",
                display="Post 100 Lonn o.l.",
                provenance=ClassificationProvenance(source="manual", reason="Lagret profil", confidence=1.0),
            ),
            control_tags=ClassificationFieldState(
                value=("aga_pliktig", "feriepengegrunnlag"),
                display="AGA-pliktig, Feriepengegrunnlag",
                provenance=ClassificationProvenance(source="manual", reason="Lagret profil", confidence=1.0),
            ),
            source="Manuell",
            confidence=1.0,
            locked=False,
        ),
        suggested=ClassificationSuggestedState(
            a07_code=ClassificationFieldState(
                value="fastloenn",
                display="fastloenn",
                provenance=ClassificationProvenance(source="heuristic", reason="Navn/alias: lonn", confidence=0.9),
            ),
            control_group=ClassificationFieldState(
                value="100_loenn_ol",
                display="Post 100 Lonn o.l.",
                provenance=ClassificationProvenance(
                    source="heuristic",
                    reason="Kode-standard",
                    confidence=0.9,
                    derived_from="a07_standard",
                ),
            ),
            control_tags=ClassificationFieldState(
                value=("aga_pliktig", "feriepengegrunnlag"),
                display="AGA-pliktig, Feriepengegrunnlag",
                provenance=ClassificationProvenance(
                    source="heuristic",
                    reason="Kode-standard",
                    confidence=0.9,
                    derived_from="a07_standard",
                ),
            ),
        ),
        previous=ClassificationCurrentState(
            a07_code=blank,
            control_group=blank,
            control_tags=ClassificationFieldState(value=(), display="", provenance=None),
            source="",
            confidence=None,
            locked=False,
        ),
        queue_state=ClassificationQueueState(review_saved=True),
        queue_name=classification_workspace.QUEUE_SAVED,
        status_label="Lagret",
        next_action=classification_workspace.NEXT_REVIEW_SAVED,
        next_action_label="Kontroller lagret klassifisering.",
        current_summary="A07: fastloenn | RF-1022: Post 100 Lonn o.l. | Flagg: AGA-pliktig, Feriepengegrunnlag",
        suggested_summary="Ingen forslag",
        why_summary="A07: navn/alias: lonn | RF-1022: Avledet fra A07-standard | Flagg: Avledet fra A07-standard",
        issue_text="",
        confidence=0.9,
        confidence_label="90%",
        confidence_bucket="Hoy",
        payroll_relevant=True,
        result=None,
    )

    detail = classification_workspace.format_why_panel(item)

    assert "Forslag: Ingen nytt forslag - lagret klassifisering brukes" in detail["suggested"]
    assert detail["next"] == "Kontroller lagret klassifisering."
    assert "RF-1022:" in detail["treatment"]


def test_format_why_panel_handles_missing_control_group_display_without_crashing() -> None:
    blank = ClassificationFieldState(value="", display="", provenance=None)
    item = ClassificationWorkspaceItem(
        account_no="2940",
        account_name="Skyldig feriepenger",
        ib=-743491.69,
        movement=-4207.18,
        ub=-747698.87,
        current=ClassificationCurrentState(
            a07_code=blank,
            control_group=blank,
            control_tags=ClassificationFieldState(value=(), display="", provenance=None),
            source="",
            confidence=None,
            locked=False,
        ),
        suggested=ClassificationSuggestedState(
            a07_code=blank,
            control_group=None,
            control_tags=None,
        ),
        previous=ClassificationCurrentState(
            a07_code=blank,
            control_group=blank,
            control_tags=ClassificationFieldState(value=(), display="", provenance=None),
            source="",
            confidence=None,
            locked=False,
        ),
        queue_state=ClassificationQueueState(review_saved=True),
        queue_name=classification_workspace.QUEUE_REVIEW,
        status_label="Trenger vurdering",
        next_action=classification_workspace.NEXT_OPEN_CLASSIFIER,
        next_action_label="Åpne klassifisering.",
        current_summary="Ikke klassifisert",
        suggested_summary="Ingen forslag",
        why_summary="",
        issue_text="",
        confidence=None,
        confidence_label="",
        confidence_bucket="",
        payroll_relevant=True,
        result=None,
    )

    detail = classification_workspace.format_why_panel(item)

    assert detail["headline"].startswith("2940 | Skyldig feriepenger")
    assert detail["treatment"] == "RF-1022-behandling er ikke avklart ennå."


def test_format_why_panel_surfaces_rf1022_exclude_alias_block() -> None:
    catalog = AccountClassificationCatalog.from_dict(
        {
            "groups": [
                {
                    "id": "100_loenn_ol",
                    "label": "Post 100 Lønn o.l.",
                    "active": True,
                    "sort_order": 10,
                    "applies_to": ["kontrolloppstilling"],
                    "aliases": ["lønn", "lonn"],
                    "exclude_aliases": ["aga", "arbeidsgiveravgift"],
                }
            ],
            "tags": [],
        }
    )

    item = classification_workspace.build_workspace_item(
        account_no="5422",
        account_name="AGA av påløpt lønn",
        movement=125000.0,
        catalog=catalog,
    )

    assert item.rf1022_exclude_blocks
    assert ("Post 100 Lønn o.l.", "aga") in item.rf1022_exclude_blocks

    detail = classification_workspace.format_why_panel(item)

    assert "Blokkert av ekskluder-alias: aga" in detail["why"]
    assert "Post 100 Lønn o.l." in detail["why"]

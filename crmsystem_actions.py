"""Read audit actions (revisjonshandlinger) from the CRMSystem database.

Read-only access — all mutations happen in the CRM app itself.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional, Sequence

from crmsystem_materiality import discover_crm_db_path, suggest_client_numbers_from_name


@dataclass
class AuditAction:
    action_id: int = 0
    area_name: str = ""
    action_type: str = ""       # "control" | "substantive"
    procedure_name: str = ""
    timing: str = ""
    owner: str = ""
    status: str = ""
    due_date: str = ""
    comments: list[ActionComment] = field(default_factory=list)


@dataclass
class ActionComment:
    comment: str = ""
    created_at: str = ""
    created_by: str = ""


@dataclass
class EngagementInfo:
    client_number: str = ""
    client_name: str = ""
    engagement_year: int = 0
    engagement_name: str = ""
    partner: str = ""
    ansvarlig: str = ""


@dataclass
class AuditActionsResult:
    engagement: EngagementInfo | None = None
    actions: list[AuditAction] = field(default_factory=list)
    error: str = ""


def load_audit_actions(
    client_name: str,
    year: int | str,
    *,
    client_numbers: Sequence[str] | None = None,
    action_type: str | None = None,
) -> AuditActionsResult:
    """Load audit actions for a client and year from the CRM database.

    Parameters
    ----------
    client_name : str
        Display name used for fuzzy matching if *client_numbers* is empty.
    year : int | str
        Engagement year.
    client_numbers : sequence of str, optional
        Known CRM client numbers to try (skips fuzzy matching).
    action_type : str, optional
        Filter by type: "control", "substantive", or None for all.
    """
    db_path = discover_crm_db_path()
    if db_path is None or not db_path.exists():
        return AuditActionsResult(error="Fant ikke CRMSystem-database.")

    # Resolve client number
    numbers: list[str] = list(client_numbers or [])
    if not numbers and client_name:
        numbers = suggest_client_numbers_from_name(client_name)
    if not numbers:
        return AuditActionsResult(error=f"Fant ikke klienten '{client_name}' i CRMSystem.")

    target_year = int(year)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        return AuditActionsResult(error=f"Kunne ikke åpne CRM-database: {exc}")

    try:
        # Find engagement
        engagement_row = None
        matched_number = ""
        for cn in numbers:
            engagement_row = conn.execute(
                """
                SELECT e.id, e.client_number, e.engagement_name, e.engagement_year,
                       e.partner, e.ansvarlig, c.client_name
                FROM engagements e
                JOIN clients c ON c.client_number = e.client_number
                WHERE e.client_number = ? AND e.engagement_year = ?
                LIMIT 1
                """,
                (cn, target_year),
            ).fetchone()
            if engagement_row:
                matched_number = cn
                break

        if not engagement_row:
            return AuditActionsResult(
                error=f"Fant ikke oppdrag for klient {numbers} i år {target_year}."
            )

        engagement = EngagementInfo(
            client_number=matched_number,
            client_name=str(engagement_row["client_name"] or ""),
            engagement_year=target_year,
            engagement_name=str(engagement_row["engagement_name"] or ""),
            partner=str(engagement_row["partner"] or ""),
            ansvarlig=str(engagement_row["ansvarlig"] or ""),
        )
        engagement_id = engagement_row["id"]

        # Load actions
        type_filter = ""
        params: list = [engagement_id]
        if action_type:
            type_filter = " AND aa.type = ?"
            params.append(action_type)

        rows = conn.execute(
            f"""
            SELECT aa.id, a.area_name, aa.type, aa.procedure_name,
                   aa.timing, aa.owner, aa.status, aa.due_date
            FROM audit_actions aa
            JOIN areas a ON a.id = aa.area_id
            WHERE a.engagement_id = ?{type_filter}
            ORDER BY a.area_name, aa.type, aa.procedure_name
            """,
            params,
        ).fetchall()

        actions: list[AuditAction] = []
        action_ids: list[int] = []
        for row in rows:
            a = AuditAction(
                action_id=row["id"],
                area_name=str(row["area_name"] or ""),
                action_type=str(row["type"] or ""),
                procedure_name=str(row["procedure_name"] or ""),
                timing=str(row["timing"] or ""),
                owner=str(row["owner"] or ""),
                status=str(row["status"] or ""),
                due_date=str(row["due_date"] or ""),
            )
            actions.append(a)
            action_ids.append(a.action_id)

        # Load comments in bulk
        if action_ids:
            placeholders = ",".join("?" * len(action_ids))
            comment_rows = conn.execute(
                f"""
                SELECT action_id, comment, created_at, created_by
                FROM action_comments
                WHERE action_id IN ({placeholders})
                ORDER BY created_at
                """,
                action_ids,
            ).fetchall()

            comments_by_action: dict[int, list[ActionComment]] = {}
            for cr in comment_rows:
                aid = cr["action_id"]
                comments_by_action.setdefault(aid, []).append(
                    ActionComment(
                        comment=str(cr["comment"] or ""),
                        created_at=str(cr["created_at"] or ""),
                        created_by=str(cr["created_by"] or ""),
                    )
                )
            for a in actions:
                a.comments = comments_by_action.get(a.action_id, [])

        return AuditActionsResult(engagement=engagement, actions=actions)

    except Exception as exc:
        return AuditActionsResult(error=f"Feil ved lesing av handlinger: {exc}")
    finally:
        conn.close()

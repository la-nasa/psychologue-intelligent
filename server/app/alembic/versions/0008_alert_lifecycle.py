"""alert lifecycle: add NOTIFIED state

Revision ID: 0008_alert_lifecycle
Revises: 0007_phq9
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_alert_lifecycle"
down_revision: str | None = "0007_phq9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "status IN ('OPEN','ACKNOWLEDGED','IN_REVIEW','ESCALATED','RESOLVED','CLOSED','CANCELLED')"
_NEW = "status IN ('OPEN','NOTIFIED','ACKNOWLEDGED','IN_REVIEW','ESCALATED','RESOLVED','CLOSED','CANCELLED')"


def upgrade() -> None:
    op.drop_constraint("ck_alert_status", "alerts", type_="check")
    op.create_check_constraint("ck_alert_status", "alerts", _NEW)


def downgrade() -> None:
    op.execute("UPDATE alerts SET status = 'OPEN' WHERE status = 'NOTIFIED'")
    op.drop_constraint("ck_alert_status", "alerts", type_="check")
    op.create_check_constraint("ck_alert_status", "alerts", _OLD)

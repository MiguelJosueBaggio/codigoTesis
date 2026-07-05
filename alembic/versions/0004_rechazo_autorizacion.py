"""rechazo_autorizacion (auditoria de rechazos RBAC) -- change
telegram-interaction-layer (C-13)

Change `telegram-interaction-layer` (C-13), grupo 2 del tasks.md: crea la
tabla de auditoria de rechazos de `pipeline.rbac.resolver_rol_y_autorizar`.
NO reusa `evento_sesion` (exige `session_id` ya existente; un rechazo puede
ocurrir antes de que exista ninguna sesion). Tipos genericos de SQLAlchemy
para sostener la paridad SQLite/PostgreSQL (DD-03).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rechazo_autorizacion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.String(), nullable=False),
        sa.Column("accion", sa.String(), nullable=False),
        sa.Column("motivo", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_rechazo_autorizacion_telegram_user_id",
        "rechazo_autorizacion",
        ["telegram_user_id"],
    )


def downgrade() -> None:
    op.drop_table("rechazo_autorizacion")

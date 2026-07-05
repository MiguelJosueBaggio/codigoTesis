"""usuario_telegram (RBAC de aplicacion) -- change telegram-interaction-layer (C-13)

Change `telegram-interaction-layer` (C-13), Decision 1 del design: crea la
tabla `usuario_telegram` que mapea `telegram_user_id -> rol` (fail-closed,
resuelto en Python -- `pipeline.session_cli`, nunca en el grafo de n8n), con
tipos genericos de SQLAlchemy para sostener la paridad SQLite/PostgreSQL
(DD-03) y PK entero autoincremental (DD-11).

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usuario_telegram",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.String(), nullable=False),
        sa.Column("rol", sa.String(), nullable=False),
        sa.Column("ensayo_id", sa.Integer(), sa.ForeignKey("ensayo.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("telegram_user_id", name="uq_usuario_telegram_telegram_user_id"),
        sa.CheckConstraint(
            "rol IN ('ingeniero', 'ayudante')",
            name="ck_usuario_telegram_rol_valido",
        ),
    )
    op.create_index(
        "ix_usuario_telegram_telegram_user_id", "usuario_telegram", ["telegram_user_id"]
    )
    op.create_index("ix_usuario_telegram_ensayo_id", "usuario_telegram", ["ensayo_id"])


def downgrade() -> None:
    op.drop_table("usuario_telegram")

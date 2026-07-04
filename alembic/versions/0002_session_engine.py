"""motor de sesiones: sesion, config_paso_sesion, evento_sesion (C-12)

Change session-engine (C-12), Decision 7 del design: igual criterio que
C-06 (migracion escrita/revisada a mano, no `--autogenerate` sin revisar,
para un dominio con auditoria). Crea las tres tablas nuevas del motor de
sesiones -- `sesion`, `config_paso_sesion` (configuracion de pasos,
RN-SES-03), `evento_sesion` (auditoria, RN-SES-06) -- con tipos genericos
de SQLAlchemy para sostener la paridad SQLite/PostgreSQL (DD-03).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sesion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.String(), nullable=False),
        sa.Column("ensayo_id", sa.Integer(), sa.ForeignKey("ensayo.id"), nullable=True),
        sa.Column("tipo_sesion", sa.String(), nullable=False),
        sa.Column("paso_actual", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("respuestas_acumuladas", sa.JSON(), nullable=False),
        sa.Column("estado", sa.String(), nullable=False, server_default="abierta"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "estado IN ('abierta', 'completada', 'expirada', 'abandonada')",
            name="ck_sesion_estado_valido",
        ),
    )
    op.create_index("ix_sesion_telegram_user_id", "sesion", ["telegram_user_id"])
    op.create_index("ix_sesion_ensayo_id", "sesion", ["ensayo_id"])
    op.create_index("ix_sesion_tipo_sesion", "sesion", ["tipo_sesion"])

    op.create_table(
        "config_paso_sesion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tipo_sesion", sa.String(), nullable=False),
        sa.Column("paso", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("tipo_respuesta", sa.String(), nullable=False),
        sa.Column("regla_validacion", sa.JSON(), nullable=True),
        sa.UniqueConstraint("tipo_sesion", "paso", name="uq_config_paso_sesion_tipo_paso"),
        sa.CheckConstraint(
            "tipo_respuesta IN ('texto', 'numero', 'foto', 'choice')",
            name="ck_config_paso_sesion_tipo_respuesta_valido",
        ),
    )
    op.create_index("ix_config_paso_sesion_tipo_sesion", "config_paso_sesion", ["tipo_sesion"])

    op.create_table(
        "evento_sesion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("sesion.id"), nullable=False),
        sa.Column("paso", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.String(), nullable=False),
        sa.Column("respuesta", sa.JSON(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evento_sesion_session_id", "evento_sesion", ["session_id"])


def downgrade() -> None:
    # Orden inverso a `upgrade` para respetar las FK.
    op.drop_table("evento_sesion")
    op.drop_table("config_paso_sesion")
    op.drop_table("sesion")

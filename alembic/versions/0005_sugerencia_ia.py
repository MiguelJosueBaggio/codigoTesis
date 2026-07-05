"""sugerencia_ia (soporte IA de estandarizacion/anomalias) + seed de
config_paso_sesion para confirmacion_ia -- change ai-support-standardization
(C-09).

Migracion ADITIVA (D-5/D-6 del design): crea la tabla `sugerencia_ia` (handle
durable del gate de aprobacion humana, RN-IA-01/02/03) y siembra los pasos de
`confirmacion_ia` en `config_paso_sesion` (RN-SES-03: la secuencia de pasos
es DATA, nunca codigo) -- un paso `choice` (aprobar/rechazar) y un paso
`texto` de justificacion. No altera ninguna tabla existente de C-06/C-12/C-13.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TIPO_SESION_CONFIRMACION_IA = "confirmacion_ia"


def upgrade() -> None:
    op.create_table(
        "sugerencia_ia",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("columna", sa.String(), nullable=False),
        sa.Column("valor_original", sa.JSON(), nullable=False),
        sa.Column("valor_sugerido", sa.JSON(), nullable=True),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("origen", sa.String(), nullable=False),
        sa.Column("estado", sa.String(), nullable=False),
        sa.Column("justificacion", sa.String(), nullable=True),
        sa.Column("ejecucion_id", sa.Integer(), sa.ForeignKey("ejecucion.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("tipo IN ('lexica', 'anomalia')", name="ck_sugerencia_ia_tipo_valido"),
        sa.CheckConstraint(
            "origen IN ('fuzzy', 'estadistica', 'llm')", name="ck_sugerencia_ia_origen_valido"
        ),
        sa.CheckConstraint(
            "estado IN ('generada', 'aprobada', 'rechazada', 'aplicada')",
            name="ck_sugerencia_ia_estado_valido",
        ),
    )
    op.create_index(
        "ix_sugerencia_ia_ejecucion_id", "sugerencia_ia", ["ejecucion_id"]
    )

    config_paso_sesion = sa.table(
        "config_paso_sesion",
        sa.column("tipo_sesion", sa.String()),
        sa.column("paso", sa.Integer()),
        sa.column("prompt", sa.String()),
        sa.column("tipo_respuesta", sa.String()),
        sa.column("regla_validacion", sa.JSON()),
    )
    op.bulk_insert(
        config_paso_sesion,
        [
            {
                "tipo_sesion": _TIPO_SESION_CONFIRMACION_IA,
                "paso": 0,
                "prompt": (
                    "Se sugiere un cambio de estandarizacion/revision de anomalia. "
                    "Respondé 'aprobar' o 'rechazar'."
                ),
                "tipo_respuesta": "choice",
                "regla_validacion": {
                    "tipo_dato": "categorico",
                    "obligatorio": True,
                    "valores_admisibles": ["aprobar", "rechazar"],
                },
            },
            {
                "tipo_sesion": _TIPO_SESION_CONFIRMACION_IA,
                "paso": 1,
                "prompt": "Enviame una breve justificacion de tu decision (texto libre).",
                "tipo_respuesta": "texto",
                "regla_validacion": {"tipo_dato": "texto_libre", "obligatorio": True},
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM config_paso_sesion WHERE tipo_sesion = :tipo_sesion"
        ).bindparams(tipo_sesion=_TIPO_SESION_CONFIRMACION_IA)
    )
    op.drop_index("ix_sugerencia_ia_ejecucion_id", table_name="sugerencia_ia")
    op.drop_table("sugerencia_ia")

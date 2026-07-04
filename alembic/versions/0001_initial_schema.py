"""esquema inicial: entidades de dominio y sistema (C-06)

Change persistence-audit-module (C-06), Decision 6 del design: migracion
inicial escrita/revisada a mano (no se confia el commit fundacional de un
dominio CRITICO a un diff de `--autogenerate` sin revisar entero). Crea las
siete tablas del ERD -- cinco de dominio (ensayo, ambiente, tratamiento,
unidad_experimental, observacion) y dos de sistema (ejecucion,
bitacora_transformacion) -- con tipos genericos de SQLAlchemy para sostener
la paridad SQLite/PostgreSQL (DD-03, Decision 3 del design).

Revision ID: 0001
Revises:
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Dominio --------------------------------------------------------
    op.create_table(
        "ensayo",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("codigo", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("codigo", name="uq_ensayo_codigo"),
    )
    op.create_index("ix_ensayo_codigo", "ensayo", ["codigo"])

    op.create_table(
        "ambiente",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ensayo_id", sa.Integer(), sa.ForeignKey("ensayo.id"), nullable=False),
        sa.Column("descripcion", sa.String(), nullable=True),
        sa.Column("latitud", sa.Float(), nullable=True),
        sa.Column("longitud", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "latitud IS NULL OR (latitud >= -90 AND latitud <= 90)",
            name="ck_ambiente_latitud_rango",
        ),
        sa.CheckConstraint(
            "longitud IS NULL OR (longitud >= -180 AND longitud <= 180)",
            name="ck_ambiente_longitud_rango",
        ),
    )
    op.create_index("ix_ambiente_ensayo_id", "ambiente", ["ensayo_id"])

    op.create_table(
        "tratamiento",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ensayo_id", sa.Integer(), sa.ForeignKey("ensayo.id"), nullable=False),
        sa.Column("descripcion", sa.String(), nullable=True),
    )
    op.create_index("ix_tratamiento_ensayo_id", "tratamiento", ["ensayo_id"])

    op.create_table(
        "unidad_experimental",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tratamiento_id", sa.Integer(), sa.ForeignKey("tratamiento.id"), nullable=False
        ),
        sa.Column("ambiente_id", sa.Integer(), sa.ForeignKey("ambiente.id"), nullable=False),
        sa.Column("identificador", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_unidad_experimental_tratamiento_id", "unidad_experimental", ["tratamiento_id"]
    )
    op.create_index("ix_unidad_experimental_ambiente_id", "unidad_experimental", ["ambiente_id"])

    # -- Sistema (RN-AUD-01 / RN-AUD-02) ---------------------------------
    op.create_table(
        "ejecucion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("iniciada_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalizada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commit_git", sa.String(length=64), nullable=True),
        sa.Column("hash_archivo_entrada", sa.String(length=64), nullable=True),
        sa.Column("registros_leidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("registros_validos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("registros_rechazados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("registros_almacenados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errores", sa.JSON(), nullable=True),
        sa.Column("advertencias", sa.JSON(), nullable=True),
    )

    op.create_table(
        "observacion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "unidad_experimental_id",
            sa.Integer(),
            sa.ForeignKey("unidad_experimental.id"),
            nullable=False,
        ),
        sa.Column("ejecucion_id", sa.Integer(), sa.ForeignKey("ejecucion.id"), nullable=False),
        sa.Column("variable", sa.String(), nullable=False),
        sa.Column("valor", sa.Float(), nullable=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_observacion_unidad_experimental_id", "observacion", ["unidad_experimental_id"]
    )
    op.create_index("ix_observacion_ejecucion_id", "observacion", ["ejecucion_id"])

    op.create_table(
        "bitacora_transformacion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ejecucion_id", sa.Integer(), sa.ForeignKey("ejecucion.id"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("columna", sa.String(), nullable=False),
        sa.Column("registros_afectados", sa.Integer(), nullable=False),
        sa.Column("muestra_antes", sa.JSON(), nullable=True),
        sa.Column("muestra_despues", sa.JSON(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_bitacora_transformacion_ejecucion_id", "bitacora_transformacion", ["ejecucion_id"]
    )


def downgrade() -> None:
    # Orden inverso a `upgrade` para respetar las FK.
    op.drop_table("bitacora_transformacion")
    op.drop_table("observacion")
    op.drop_table("ejecucion")
    op.drop_table("unidad_experimental")
    op.drop_table("tratamiento")
    op.drop_table("ambiente")
    op.drop_table("ensayo")

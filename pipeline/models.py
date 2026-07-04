"""Modelos ORM declarativos (SQLAlchemy 2.0) -- change persistence-audit-module
(C-06).

Fuente UNICA del esquema de base de datos (DD-11): las cinco entidades de
dominio (Ensayo, Ambiente, Tratamiento, UnidadExperimental, Observacion) y
las dos de sistema (Ejecucion, BitacoraTransformacion) del ERD de
`knowledge-base/04_modelo_de_datos.md`. Alembic deriva sus migraciones de
`Base.metadata`; el esquema NUNCA se define por SQL crudo ni por motor
(regla dura del proyecto).

Decision 3 del design (paridad SQLite/PostgreSQL, DD-03): solo tipos
GENERICOS de SQLAlchemy (Integer, String, Float, `DateTime(timezone=True)`,
JSON) -- nunca tipos dialect-specific (JSONB, TIMESTAMPTZ, UUID de
Postgres). Todo timestamp se almacena en UTC (Riesgo TZ del design).

Decision 8 (DD-12): `latitud`/`longitud` son `Float` (double), no
`Numeric(9,6)`, para preservar la precision capturada sin imponer una
escala de redondeo; el rango se exige con un CHECK constraint a nivel de
tabla en vez de a nivel de tipo.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarativa comun; `Base.metadata` es la fuente que consume Alembic."""


class Ensayo(Base):
    """Entidad de dominio raiz del ERD: un ensayo agricola identificado por
    `codigo` (clave natural, unica -- Decision 4)."""

    __tablename__ = "ensayo"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ambientes: Mapped[List["Ambiente"]] = relationship(back_populates="ensayo")
    tratamientos: Mapped[List["Tratamiento"]] = relationship(back_populates="ensayo")


class Ambiente(Base):
    """Entidad de dominio: un ambiente/campo dentro de un `Ensayo`.

    `latitud`/`longitud` opcionales (DD-12): capturadas con precision
    exacta, sin uso funcional en v1 (geolocalizacion reservada para
    trabajo futuro, `14_reuso_academico_y_geolocalizacion.md`). El CHECK
    constraint exige rango WGS84 valido cuando estan presentes; ausentes
    (NULL) siempre son validas.
    """

    __tablename__ = "ambiente"
    __table_args__ = (
        CheckConstraint(
            "latitud IS NULL OR (latitud >= -90 AND latitud <= 90)",
            name="ck_ambiente_latitud_rango",
        ),
        CheckConstraint(
            "longitud IS NULL OR (longitud >= -180 AND longitud <= 180)",
            name="ck_ambiente_longitud_rango",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ensayo_id: Mapped[int] = mapped_column(ForeignKey("ensayo.id"), nullable=False, index=True)
    descripcion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    latitud: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitud: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    ensayo: Mapped["Ensayo"] = relationship(back_populates="ambientes")
    unidades: Mapped[List["UnidadExperimental"]] = relationship(back_populates="ambiente")


class Tratamiento(Base):
    """Entidad de dominio: un tratamiento experimental dentro de un `Ensayo`."""

    __tablename__ = "tratamiento"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ensayo_id: Mapped[int] = mapped_column(ForeignKey("ensayo.id"), nullable=False, index=True)
    descripcion: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    ensayo: Mapped["Ensayo"] = relationship(back_populates="tratamientos")
    unidades: Mapped[List["UnidadExperimental"]] = relationship(back_populates="tratamiento")


class UnidadExperimental(Base):
    """Entidad de dominio: la interseccion Tratamiento x Ambiente donde se
    observa un valor (p. ej. una parcela o planta), identificada por
    `identificador` dentro de ese par (clave natural compuesta)."""

    __tablename__ = "unidad_experimental"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tratamiento_id: Mapped[int] = mapped_column(
        ForeignKey("tratamiento.id"), nullable=False, index=True
    )
    ambiente_id: Mapped[int] = mapped_column(ForeignKey("ambiente.id"), nullable=False, index=True)
    identificador: Mapped[str] = mapped_column(String, nullable=False)

    tratamiento: Mapped["Tratamiento"] = relationship(back_populates="unidades")
    ambiente: Mapped["Ambiente"] = relationship(back_populates="unidades")
    observaciones: Mapped[List["Observacion"]] = relationship(back_populates="unidad_experimental")


class Observacion(Base):
    """Entidad de dominio: un valor observado (`variable`/`valor`) para una
    `UnidadExperimental`, ligada tambien a la `Ejecucion` que la produjo
    (habilita RN-AUD y el reprocesamiento idempotente, Decision 4)."""

    __tablename__ = "observacion"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    unidad_experimental_id: Mapped[int] = mapped_column(
        ForeignKey("unidad_experimental.id"), nullable=False, index=True
    )
    ejecucion_id: Mapped[int] = mapped_column(ForeignKey("ejecucion.id"), nullable=False, index=True)
    variable: Mapped[str] = mapped_column(String, nullable=False)
    valor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    momento: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    unidad_experimental: Mapped["UnidadExperimental"] = relationship(back_populates="observaciones")
    ejecucion: Mapped["Ejecucion"] = relationship(back_populates="observaciones")


class Ejecucion(Base):
    """Entidad de sistema (RN-AUD-01): registro de auditoria de cada corrida
    del pipeline que persiste datos -- timestamps, hash de commit Git, hash
    SHA-256 del archivo de entrada, conteos y errores/advertencias."""

    __tablename__ = "ejecucion"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    iniciada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalizada_en: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    commit_git: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    hash_archivo_entrada: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    registros_leidos: Mapped[int] = mapped_column(nullable=False, default=0)
    registros_validos: Mapped[int] = mapped_column(nullable=False, default=0)
    registros_rechazados: Mapped[int] = mapped_column(nullable=False, default=0)
    registros_almacenados: Mapped[int] = mapped_column(nullable=False, default=0)
    errores: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    advertencias: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    bitacora: Mapped[List["BitacoraTransformacion"]] = relationship(back_populates="ejecucion")
    observaciones: Mapped[List["Observacion"]] = relationship(back_populates="ejecucion")


class BitacoraTransformacion(Base):
    """Entidad de sistema (RN-AUD-02): una fila por cada
    `OperacionTransformacion` de C-05, ligada a su `Ejecucion` y con `orden`
    para reconstruir la secuencia aplicada."""

    __tablename__ = "bitacora_transformacion"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ejecucion_id: Mapped[int] = mapped_column(ForeignKey("ejecucion.id"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    columna: Mapped[str] = mapped_column(String, nullable=False)
    registros_afectados: Mapped[int] = mapped_column(nullable=False)
    muestra_antes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    muestra_despues: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    orden: Mapped[int] = mapped_column(nullable=False)

    ejecucion: Mapped["Ejecucion"] = relationship(back_populates="bitacora")

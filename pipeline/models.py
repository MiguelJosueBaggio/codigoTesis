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

Change `session-engine` (C-12) EXTIENDE esta misma `Base` con las tres
entidades del motor de sesiones (`Sesion`, `ConfigPasoSesion`,
`EventoSesion`, RN-SES-02..06) -- ver seccion homonima mas abajo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, JSON, String, UniqueConstraint
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


# --- Motor de sesiones (RN-SES-02..07) -- change session-engine (C-12) ----
# Extiende la MISMA `Base` de C-06 (RN-SES-02: prohibido un almacen paralelo).
# Tipos genericos (JSON, no JSONB; DateTime(timezone=True)) para sostener la
# paridad SQLite/PostgreSQL (DD-03); PK entero autoincremental (DD-11).

TIPOS_RESPUESTA_VALIDOS = ("texto", "numero", "foto", "choice")
ESTADOS_SESION_VALIDOS = ("abierta", "completada", "expirada", "abandonada")


def _check_in(columna: str, valores: tuple) -> str:
    """Construye la expresion SQL `columna IN (...)` para un CHECK constraint
    a partir de una tupla de valores admisibles (evita duplicar el enum
    entre el constraint y las constantes que consume `pipeline.session_engine`)."""
    lista = ", ".join(f"'{valor}'" for valor in valores)
    return f"{columna} IN ({lista})"


class Sesion(Base):
    """Entidad de sistema (RN-SES-02): una interaccion conversacional en
    curso o cerrada, dirigida por el motor de `pipeline.session_engine`.

    `ensayo_id` es nullable (RN-SES-02, Scenario "ensayo_id nullable para
    sesiones de setup"): una sesion `setup_ensayo` referencia un ensayo que
    todavia no existe. `respuestas_acumuladas` es `JSON` generico (Decision
    5 del design): arranca en `{}` y se puebla `paso -> valor validado`.
    """

    __tablename__ = "sesion"
    __table_args__ = (
        CheckConstraint(_check_in("estado", ESTADOS_SESION_VALIDOS), name="ck_sesion_estado_valido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ensayo_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ensayo.id"), nullable=True, index=True
    )
    tipo_sesion: Mapped[str] = mapped_column(String, nullable=False, index=True)
    paso_actual: Mapped[int] = mapped_column(nullable=False, default=0)
    respuestas_acumuladas: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    estado: Mapped[str] = mapped_column(String, nullable=False, default="abierta")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    eventos: Mapped[List["EventoSesion"]] = relationship(back_populates="sesion")


class ConfigPasoSesion(Base):
    """Entidad de configuracion (RN-SES-03): una fila por paso de un
    `tipo_sesion`. La secuencia de pasos es DATA en esta tabla, nunca
    bifurcaciones hardcodeadas en el motor (DD-10 fijo el formato JSON-en
    -base). `tipo_respuesta` esta restringido por CHECK al enum declarado
    en la spec (`texto`, `numero`, `foto`, `choice`)."""

    __tablename__ = "config_paso_sesion"
    __table_args__ = (
        UniqueConstraint("tipo_sesion", "paso", name="uq_config_paso_sesion_tipo_paso"),
        CheckConstraint(
            _check_in("tipo_respuesta", TIPOS_RESPUESTA_VALIDOS),
            name="ck_config_paso_sesion_tipo_respuesta_valido",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tipo_sesion: Mapped[str] = mapped_column(String, nullable=False, index=True)
    paso: Mapped[int] = mapped_column(nullable=False)
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    tipo_respuesta: Mapped[str] = mapped_column(String, nullable=False)
    regla_validacion: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class EventoSesion(Base):
    """Entidad de auditoria propia (RN-SES-06, Decision 2 del design): NO
    reusa `BitacoraTransformacion` (semantica ajena, atada a `ejecucion_id`
    del pipeline de datos). Respeta la MISMA cadena de custodia de RN-AUD:
    inmutable, timestamp UTC, escrita en la misma transaccion que el avance
    de sesion que la origina."""

    __tablename__ = "evento_sesion"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sesion.id"), nullable=False, index=True)
    paso: Mapped[int] = mapped_column(nullable=False)
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    respuesta: Mapped[Any] = mapped_column(JSON, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sesion: Mapped["Sesion"] = relationship(back_populates="eventos")


# --- RBAC de aplicacion (telegram_user_id -> rol) -- change
# telegram-interaction-layer (C-13), migracion Alembic 0003. Extiende la
# MISMA `Base` (DD-11); tipos genericos para paridad SQLite/PostgreSQL
# (DD-03); PK entero autoincremental. La resolucion de rol y la
# autorizacion ocurren en Python (D-1 del design), nunca en el grafo de n8n.

ROLES_USUARIO_TELEGRAM_VALIDOS = ("ingeniero", "ayudante")


class UsuarioTelegram(Base):
    """Entidad de RBAC (D-1): mapea `telegram_user_id -> rol`, acotado por
    `ensayo_id` cuando corresponde (un ayudante se acota a su ensayo; un
    ingeniero puede tener `ensayo_id=NULL` hasta crear el ensayo, KB 03
    §RBAC). Fail-closed: un `telegram_user_id` ausente de esta tabla se
    rechaza en la capa de autorizacion (`pipeline.session_cli`), no aqui."""

    __tablename__ = "usuario_telegram"
    __table_args__ = (
        CheckConstraint(
            _check_in("rol", ROLES_USUARIO_TELEGRAM_VALIDOS),
            name="ck_usuario_telegram_rol_valido",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, index=True
    )
    rol: Mapped[str] = mapped_column(String, nullable=False)
    ensayo_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ensayo.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RechazoAutorizacion(Base):
    """Entidad de auditoria de rechazos de RBAC (RN-AUD/RN-SES-06, change
    telegram-interaction-layer / C-13, grupo 2): una fila por cada intento
    de accion rechazado por `pipeline.rbac.resolver_rol_y_autorizar` --
    usuario no mapeado, rol sin permiso, `ensayo_id` fuera de alcance o
    accion desconocida. NO reusa `EventoSesion` (esa tabla exige un
    `session_id` ya existente -- RN-SES-02/06 -- y un rechazo puede ocurrir
    ANTES de que exista ninguna sesion, p. ej. un usuario no mapeado)."""

    __tablename__ = "rechazo_autorizacion"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    accion: Mapped[str] = mapped_column(String, nullable=False)
    motivo: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# --- SugerenciaIA (RN-IA-01/02/03) -- change ai-support-standardization
# (C-09), migracion Alembic 0005. Extiende la MISMA Base (DD-11); tipos
# genericos para paridad SQLite/PostgreSQL (DD-03); PK entero autoincremental.
# Handle durable de una sugerencia de apoyo (lexica/anomalia) a traves del
# gate asincrono de aprobacion humana (generacion -> confirmacion por
# Telegram -> aplicacion), D-5 del design.

TIPOS_SUGERENCIA_IA_VALIDOS = ("lexica", "anomalia")
ORIGENES_SUGERENCIA_IA_VALIDOS = ("fuzzy", "estadistica", "llm")
ESTADOS_SUGERENCIA_IA_VALIDOS = ("generada", "aprobada", "rechazada", "aplicada")


class SugerenciaIA(Base):
    """Entidad de sistema (D-5): una sugerencia de estandarizacion lexica o
    de anomalia estadistica propuesta por `pipeline.ai_support`, con su ciclo
    de vida de aprobacion humana (RN-IA-01/02/03). `valor_sugerido` es JSON
    nullable (`None` para anomalias, D-3: marcan para revision, no proponen
    reemplazo). `ejecucion_id` es nullable hasta que la sugerencia se aplica
    (liga la decision a la `Ejecucion` de C-06 que la aplico)."""

    __tablename__ = "sugerencia_ia"
    __table_args__ = (
        CheckConstraint(_check_in("tipo", TIPOS_SUGERENCIA_IA_VALIDOS), name="ck_sugerencia_ia_tipo_valido"),
        CheckConstraint(
            _check_in("origen", ORIGENES_SUGERENCIA_IA_VALIDOS), name="ck_sugerencia_ia_origen_valido"
        ),
        CheckConstraint(
            _check_in("estado", ESTADOS_SUGERENCIA_IA_VALIDOS), name="ck_sugerencia_ia_estado_valido"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    columna: Mapped[str] = mapped_column(String, nullable=False)
    valor_original: Mapped[Any] = mapped_column(JSON, nullable=False)
    valor_sugerido: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    origen: Mapped[str] = mapped_column(String, nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False, default="generada")
    justificacion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ejecucion_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ejecucion.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

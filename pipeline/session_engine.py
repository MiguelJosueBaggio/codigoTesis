"""Motor generico de sesion, dirigido por datos -- change session-engine
(C-12).

DD-09 establecio el motor generico (rechazando un arbol de conversacion
hardcodeado por rol en n8n). Este modulo resuelve reanudar-vs-nueva sesion
(RN-SES-04), avanza con validacion por paso (RN-SES-05), finaliza al ultimo
paso, audita cada evento (RN-SES-06) y expira sesiones abandonadas por
timeout (RN-SES-07, 24h uniforme -- DD-10 ya lo fijo, ver design.md
Decision 1).

La secuencia de pasos de cada `tipo_sesion` es DATA en `config_paso_sesion`
(RN-SES-03): este modulo NUNCA bifurca por `tipo_sesion` en el codigo, solo
lee la configuracion. Fuera de alcance (Non-Goals del design): nada de
Telegram (nodo, trigger, RBAC) -- el motor recibe `telegram_user_id` y `rol`
como parametros de entrada; eso es C-13.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, List, Optional

import great_expectations as gx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline.data_dictionary import VariableDefinition
from pipeline.models import ConfigPasoSesion, EventoSesion, Sesion
from pipeline.validation import _expectations_de_variable

# RN-SES-07 / DD-10: timeout uniforme de 24h para los cuatro `tipo_sesion`
# (Decision 1 del design -- NO reabrir como open question, ya resuelta).
TIMEOUT_SESION = timedelta(hours=24)

# RN-SES-04 / Decision 4 del design: el resolver RECIBE el rol, no consulta
# RBAC (eso es C-13, governance ALTO). Mapa rol -> tipo_sesion por defecto.
ROL_A_TIPO_SESION = {
    "ingeniero": "setup_ensayo",
    "ayudante": "carga_dato",
}

_ESTADOS_ABIERTOS = ("abierta",)


class SessionEngineError(Exception):
    """Base de los errores propios del motor de sesiones."""


class TipoSesionSinPasosError(SessionEngineError):
    """`tipo_sesion` no tiene ninguna fila en `config_paso_sesion`.

    Fail-closed (patron de `pipeline.db.DatabaseUrlNotConfiguredError`):
    mejor fallar explicito que crear/avanzar una sesion que nunca puede
    progresar (Riesgo del design: "`config_paso_sesion` sin filas para un
    `tipo_sesion`").
    """


class RolNoReconocidoError(SessionEngineError):
    """El `rol` recibido no mapea a ningun `tipo_sesion` conocido."""


class PasoSesionNoConfiguradoError(SessionEngineError):
    """El `paso_actual` de una sesion no tiene fila de configuracion
    correspondiente (inconsistencia entre `sesion` y `config_paso_sesion`)."""


def _obtener_secuencia_pasos(session: Session, tipo_sesion: str) -> List[ConfigPasoSesion]:
    """Lee la secuencia de pasos de `tipo_sesion` desde `config_paso_sesion`,
    ordenada por `paso` (RN-SES-03). Fail-closed si no hay filas."""
    secuencia = list(
        session.execute(
            select(ConfigPasoSesion)
            .where(ConfigPasoSesion.tipo_sesion == tipo_sesion)
            .order_by(ConfigPasoSesion.paso)
        ).scalars()
    )
    if not secuencia:
        raise TipoSesionSinPasosError(
            f"El tipo_sesion '{tipo_sesion}' no tiene ninguna fila configurada "
            "en config_paso_sesion; no se puede crear ni avanzar una sesion "
            "de este tipo sin su secuencia de pasos."
        )
    return secuencia


def _obtener_paso(session: Session, tipo_sesion: str, paso: int) -> ConfigPasoSesion:
    """Devuelve la fila de configuracion del `paso` dado dentro de
    `tipo_sesion`. Fail-closed si no existe (inconsistencia de datos)."""
    secuencia = _obtener_secuencia_pasos(session, tipo_sesion)
    for config_paso in secuencia:
        if config_paso.paso == paso:
            return config_paso
    raise PasoSesionNoConfiguradoError(
        f"No hay configuracion para el paso {paso} de tipo_sesion '{tipo_sesion}'."
    )


def _tipo_sesion_para_rol(rol: str) -> str:
    """Resuelve `rol -> tipo_sesion` por defecto (Decision 4 del design): el
    motor RECIBE el rol ya resuelto, no consulta ninguna tabla RBAC (eso es
    C-13, governance ALTO)."""
    tipo_sesion = ROL_A_TIPO_SESION.get(rol)
    if tipo_sesion is None:
        raise RolNoReconocidoError(
            f"El rol '{rol}' no mapea a ningun tipo_sesion conocido "
            f"(roles soportados: {sorted(ROL_A_TIPO_SESION)})."
        )
    return tipo_sesion


def _buscar_sesion_abierta(session: Session, telegram_user_id: str) -> Optional[Sesion]:
    return session.execute(
        select(Sesion).where(
            Sesion.telegram_user_id == telegram_user_id,
            Sesion.estado.in_(_ESTADOS_ABIERTOS),
        )
    ).scalar_one_or_none()


def resolver_sesion(
    session: Session,
    telegram_user_id: str,
    rol: str,
    ahora: datetime,
) -> Sesion:
    """Resuelve la sesion de `telegram_user_id` (RN-SES-04): si ya tiene una
    sesion `abierta`, la devuelve (reanudacion); si no, resuelve el
    `tipo_sesion` a partir de `rol` y crea una sesion nueva en paso 0.

    Fail-closed si `rol` no mapea a ningun `tipo_sesion`, o si ese
    `tipo_sesion` no tiene secuencia de pasos configurada (RN-SES-03).
    """
    sesion_abierta = _buscar_sesion_abierta(session, telegram_user_id)
    if sesion_abierta is not None:
        return sesion_abierta

    tipo_sesion = _tipo_sesion_para_rol(rol)
    _obtener_secuencia_pasos(session, tipo_sesion)  # fail-closed si no hay pasos

    sesion = Sesion(
        telegram_user_id=telegram_user_id,
        tipo_sesion=tipo_sesion,
        paso_actual=0,
        respuestas_acumuladas={},
        estado="abierta",
        created_at=ahora,
        updated_at=ahora,
    )
    session.add(sesion)
    session.commit()
    return sesion


# --- Validacion por paso (RN-SES-05) ---------------------------------------
# Decision 6 del design: la `regla_validacion` de cada paso se modela como
# una `VariableDefinition` (mismo contrato tipado de C-02,
# `pipeline.data_dictionary`) y se valida reusando las expectations
# declarativas de `pipeline.validation` (RN-VAL-02/03/04) -- NUNCA una
# comparacion imperativa `if`/`else` nueva (disciplina DD-04). Para pasos
# `foto` la regla puede omitirse: se valida forma minima (presencia de un
# valor de tipo texto/referencia).

_NOMBRE_VARIABLE_RESPUESTA = "respuesta"
_TIPO_DATO_POR_DEFECTO_FOTO = "texto_libre"


def _variable_desde_regla(tipo_respuesta: str, regla_validacion: Optional[dict]) -> VariableDefinition:
    """Reconstruye una `VariableDefinition` (pipeline.data_dictionary) a
    partir de la `regla_validacion` JSON de un `ConfigPasoSesion`."""
    regla = regla_validacion or {}
    tipo_dato = regla.get("tipo_dato")
    if tipo_dato is None:
        # `foto`/`choice` sin regla explicita: validacion minima de forma
        # (presencia de un valor de tipo texto), Decision 6 del design.
        tipo_dato = _TIPO_DATO_POR_DEFECTO_FOTO
    return VariableDefinition(
        nombre_canonico=_NOMBRE_VARIABLE_RESPUESTA,
        descripcion=regla.get("descripcion", f"Respuesta de paso tipo '{tipo_respuesta}'"),
        tipo_dato=tipo_dato,
        obligatorio=regla.get("obligatorio", True),
        unidad=regla.get("unidad"),
        rango=regla.get("rango"),
        valores_admisibles=regla.get("valores_admisibles"),
    )


def _es_respuesta_valida(config_paso: ConfigPasoSesion, respuesta: Any) -> bool:
    """Valida `respuesta` contra la `regla_validacion` del paso, reusando el
    mismo constructor de expectations declarativas que `pipeline.validation`
    usa para el dataset completo (RN-VAL-02/03/04) -- nunca logica imperativa
    nueva (DD-04)."""
    variable = _variable_desde_regla(config_paso.tipo_respuesta, config_paso.regla_validacion)
    df = pd.DataFrame({variable.nombre_canonico: [respuesta]})

    contexto = gx.get_context(mode="ephemeral")
    batch = contexto.data_sources.pandas_default.read_dataframe(df)
    suite = gx.ExpectationSuite(
        name="validacion_paso_sesion",
        expectations=_expectations_de_variable(variable),
    )
    resultado = batch.validate(suite, result_format="COMPLETE")
    return bool(resultado.success)


@dataclass(frozen=True)
class ResultadoAvance:
    """Resultado de `avanzar` (RN-SES-05).

    Attributes:
        valido: si la respuesta satisfizo la `regla_validacion` del paso.
        sesion: la `Sesion` (actualizada si `valido`, intacta si no).
        mensaje: motivo de rechazo (solo si `not valido`) -- el motor
            senala que el paso debe re-preguntarse, no decide COMO
            (eso es la capa de Telegram, C-13).
    """

    valido: bool
    sesion: Sesion
    mensaje: Optional[str] = None


def avanzar(session: Session, sesion: Sesion, respuesta: Any, ahora: datetime) -> ResultadoAvance:
    """Valida `respuesta` contra el paso actual de `sesion` y, si es valida,
    la almacena y avanza (RN-SES-05); si es el ultimo paso de la secuencia,
    transiciona a `completada` en vez de avanzar a un paso inexistente.

    Una respuesta invalida NO modifica la sesion: `paso_actual` y
    `respuestas_acumuladas` quedan intactos y el resultado indica
    re-preguntar (`valido=False`).

    El avance valido y su `evento_sesion` de auditoria (RN-SES-06) se
    persisten en UNA transaccion atomica (Decision 2/7 del design, mismo
    patron que `pipeline.persistence.persist`): si algo falla, no queda ni
    el avance ni un evento huerfano.
    """
    config_paso = _obtener_paso(session, sesion.tipo_sesion, sesion.paso_actual)

    if not _es_respuesta_valida(config_paso, respuesta):
        return ResultadoAvance(
            valido=False,
            sesion=sesion,
            mensaje=(
                f"La respuesta no satisface la regla de validacion del paso "
                f"{sesion.paso_actual} ('{config_paso.prompt}'); re-preguntar."
            ),
        )

    secuencia = _obtener_secuencia_pasos(session, sesion.tipo_sesion)
    ultimo_paso = secuencia[-1].paso
    paso_respondido = sesion.paso_actual

    nuevas_respuestas = dict(sesion.respuestas_acumuladas)
    nuevas_respuestas[str(paso_respondido)] = respuesta

    # NOTA: no se usa `with session.begin():` (patron de `persistence.persist`)
    # porque para cuando llegamos aca la `Session` ya puede tener una
    # transaccion auto-iniciada por los `select` previos (autobegin de
    # SQLAlchemy 2.0 en `_obtener_paso`/`_obtener_secuencia_pasos`), y anidar
    # un `begin()` explicito sobre una transaccion ya abierta levanta
    # `InvalidRequestError`. El try/commit/except-rollback logra la MISMA
    # atomicidad (Decision 2/7 del design): si algo falla antes del commit,
    # se revierte tanto el avance de `sesion` como el `evento_sesion` recien
    # agregado -- no queda ningun evento huerfano.
    try:
        sesion.respuestas_acumuladas = nuevas_respuestas
        sesion.updated_at = ahora
        if paso_respondido >= ultimo_paso:
            sesion.estado = "completada"
        else:
            sesion.paso_actual = paso_respondido + 1

        session.add(
            EventoSesion(
                session_id=sesion.id,
                paso=paso_respondido,
                prompt=config_paso.prompt,
                respuesta=respuesta,
                timestamp=ahora,
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    return ResultadoAvance(valido=True, sesion=sesion)


def expirar_sesiones_vencidas(session: Session, ahora: datetime) -> int:
    """Transiciona a `expirada` toda sesion `abierta` cuya `updated_at`
    supere `TIMEOUT_SESION` (24h uniforme, RN-SES-07/DD-10 -- Decision 1 del
    design, NO reabrir).

    Decision 3 del design: barrido explicito e inyectable, no lazy-on-access
    ni scheduler interno; `ahora` se recibe como parametro para ser
    determinista y testeable sin esperar 24h reales ni mockear el reloj.
    Quien dispara este barrido (cron de n8n) es cableado de orquestacion
    fuera de C-12.

    Returns:
        Cantidad de sesiones transicionadas a `expirada` en esta corrida.
    """
    umbral = ahora - TIMEOUT_SESION
    vencidas = list(
        session.execute(
            select(Sesion).where(
                Sesion.estado.in_(_ESTADOS_ABIERTOS),
                Sesion.updated_at < umbral,
            )
        ).scalars()
    )
    for sesion in vencidas:
        sesion.estado = "expirada"
    session.commit()
    return len(vencidas)

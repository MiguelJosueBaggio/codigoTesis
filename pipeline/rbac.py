"""RBAC de aplicacion: resolucion de rol y autorizacion fail-closed -- change
`telegram-interaction-layer` (C-13), grupo 2 del tasks.md.

Decision 1 del design: la resolucion de rol y la comprobacion de permiso
ocurren en Python (este modulo, consumido por `pipeline.session_cli`),
NUNCA en el grafo de n8n. Fail-closed (KB 03 §RBAC): un `telegram_user_id`
no mapeado, un rol sin permiso para la accion, un `ensayo_id` fuera del
alcance del usuario, o una accion desconocida, se rechazan con el MISMO
mensaje neutro -- nunca se filtra si el usuario existe o no. Cada rechazo
se registra en `RechazoAutorizacion` (auditoria, RN-AUD/RN-SES-06).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline.models import RechazoAutorizacion, UsuarioTelegram

# Mensaje unico para TODO rechazo (fail-closed, KB 03 SS RBAC): no distingue
# "no existe" de "existe pero sin permiso" -- evitar filtrar informacion.
MENSAJE_RECHAZO_NEUTRO = "Usuario no autorizado."

# KB 03 SS RBAC -- Matriz de permisos resuelta (unica fuente de verdad del
# mapeo rol -> acciones permitidas; nunca un if/else disperso por el codigo).
ACCIONES_POR_ROL = {
    "ingeniero": frozenset(
        {
            "setup_ensayo",
            "carga_dato",
            "confirmacion_ocr",
            "confirmacion_ia",
            "recibir_resultados",
            "elegir_autoria_reporte",
        }
    ),
    "ayudante": frozenset({"carga_dato", "confirmacion_ocr", "confirmacion_ia"}),
}

ACCIONES_CONOCIDAS = frozenset().union(*ACCIONES_POR_ROL.values())


@dataclass(frozen=True)
class ResultadoAutorizacion:
    """Resultado de `resolver_rol_y_autorizar`.

    Attributes:
        autorizado: si la accion fue permitida.
        rol: rol resuelto (solo si el usuario esta mapeado, autorizado o no).
        mensaje: mensaje neutro de rechazo (solo si `not autorizado`).
    """

    autorizado: bool
    rol: Optional[str] = None
    mensaje: Optional[str] = None


def _registrar_rechazo(
    session: Session, telegram_user_id: str, accion: str, motivo: str, ahora: datetime
) -> None:
    """Deja un evento auditable del rechazo (RN-AUD/RN-SES-06) -- misma
    cadena de custodia que el resto de la auditoria del proyecto: inmutable,
    timestamp UTC, escrito antes de responder al usuario."""
    session.add(
        RechazoAutorizacion(
            telegram_user_id=telegram_user_id,
            accion=accion,
            motivo=motivo,
            timestamp=ahora,
        )
    )
    session.commit()


def resolver_rol_y_autorizar(
    session: Session,
    telegram_user_id: str,
    accion: str,
    ahora: datetime,
    ensayo_id: Optional[int] = None,
) -> ResultadoAutorizacion:
    """Resuelve el rol de `telegram_user_id` y autoriza `accion` (fail-closed).

    Args:
        session: `Session` de SQLAlchemy real (nunca mock, regla dura C-06).
        telegram_user_id: identidad cruda que Telegram provee.
        accion: una de `ACCIONES_CONOCIDAS`; cualquier otro valor es
            fail-closed (2.4 TRIANGULATE).
        ahora: instante UTC inyectado (determinismo, mismo patron que
            `pipeline.session_engine`).
        ensayo_id: si se pasa, y el usuario mapeado ya tiene un `ensayo_id`
            propio distinto, se rechaza (un ayudante acotado a su ensayo no
            puede operar sobre otro).

    Returns:
        `ResultadoAutorizacion`. Cada rechazo deja un evento auditable en
        `RechazoAutorizacion` ANTES de devolver el resultado.
    """
    if accion not in ACCIONES_CONOCIDAS:
        _registrar_rechazo(session, telegram_user_id, accion, "accion_desconocida", ahora)
        return ResultadoAutorizacion(autorizado=False, mensaje=MENSAJE_RECHAZO_NEUTRO)

    usuario = session.execute(
        select(UsuarioTelegram).where(UsuarioTelegram.telegram_user_id == telegram_user_id)
    ).scalar_one_or_none()

    if usuario is None:
        _registrar_rechazo(session, telegram_user_id, accion, "usuario_no_mapeado", ahora)
        return ResultadoAutorizacion(autorizado=False, mensaje=MENSAJE_RECHAZO_NEUTRO)

    acciones_permitidas = ACCIONES_POR_ROL.get(usuario.rol, frozenset())
    if accion not in acciones_permitidas:
        _registrar_rechazo(session, telegram_user_id, accion, "rol_sin_permiso", ahora)
        return ResultadoAutorizacion(
            autorizado=False, rol=usuario.rol, mensaje=MENSAJE_RECHAZO_NEUTRO
        )

    if (
        ensayo_id is not None
        and usuario.ensayo_id is not None
        and usuario.ensayo_id != ensayo_id
    ):
        _registrar_rechazo(session, telegram_user_id, accion, "ensayo_no_autorizado", ahora)
        return ResultadoAutorizacion(
            autorizado=False, rol=usuario.rol, mensaje=MENSAJE_RECHAZO_NEUTRO
        )

    return ResultadoAutorizacion(autorizado=True, rol=usuario.rol)

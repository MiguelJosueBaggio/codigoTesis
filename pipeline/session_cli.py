"""CLI interna del motor de sesiones -- frontera n8n<->Python (DD-05), change
`telegram-interaction-layer` (C-13), Decision 2 del design, grupo 3 del
tasks.md.

n8n NUNCA importa Python (DD-05): este modulo es la UNICA puerta por la que
el workflow `interaccion_telegram.json` invoca el motor de sesiones de C-12
(`pipeline.session_engine`) y el RBAC de aplicacion (`pipeline.rbac`,
Decision 1). Se invoca como `python -m pipeline.session_cli <subcomando>`
(Execute Command).

Contrato I/O (D-2): JSON por stdin, JSON por stdout, **exit code SIEMPRE 0**
-- un fallo de negocio (usuario no autorizado, respuesta invalida, sesion
inexistente) se comunica como un campo en el JSON de salida, NUNCA como una
excepcion no capturada ni un exit code distinto de 0 (mismo criterio que el
wrapper exit-0 de la cadena CLI de C-08: Execute Command de n8n hace THROW
ante cualquier exit code != 0). `DATABASE_URL` se toma de la variable de
entorno homonima (DD-11); cero credenciales en la entrada/salida.

Subcomandos:
    resolver        -- resuelve/crea la sesion de `telegram_user_id` (RBAC +
                        `session_engine.resolver_sesion`) y devuelve el
                        prompt del paso actual.
    avanzar         -- valida la `respuesta` del paso actual (RBAC +
                        `session_engine.avanzar`) y devuelve el resultado.
    expirar         -- barre sesiones vencidas (`expirar_sesiones_vencidas`,
                        RN-SES-07/DD-10, 24h) para un trigger programado.
    finalizar_setup -- construye los config files de una sesion
                        `setup_ensayo` completa (`pipeline.setup_ensayo`).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select

from pipeline.models import ConfigPasoSesion, Sesion, UsuarioTelegram
from pipeline.rbac import resolver_rol_y_autorizar
from pipeline.session_engine import (
    ROL_A_TIPO_SESION,
    SessionEngineError,
    avanzar as motor_avanzar,
    expirar_sesiones_vencidas,
    resolver_sesion,
)
from pipeline.setup_ensayo import finalizar_setup as construir_configs_de_setup

# Placeholder de auditoria para el caso "usuario no mapeado" en `resolver`:
# `resolver_rol_y_autorizar` verifica la existencia del usuario ANTES que la
# validez de `accion` (pipeline.rbac), asi que cualquier valor aqui deriva
# en el motivo correcto ('usuario_no_mapeado') sin necesitar saber el rol.
_ACCION_PLACEHOLDER_USUARIO_DESCONOCIDO = "resolver_sesion"


def _buscar_usuario(session, telegram_user_id: str) -> Optional[UsuarioTelegram]:
    return session.execute(
        select(UsuarioTelegram).where(UsuarioTelegram.telegram_user_id == telegram_user_id)
    ).scalar_one_or_none()


def _buscar_sesion_abierta(session, telegram_user_id: str) -> Optional[Sesion]:
    return session.execute(
        select(Sesion).where(
            Sesion.telegram_user_id == telegram_user_id,
            Sesion.estado == "abierta",
        )
    ).scalar_one_or_none()


def _paso_actual(session, sesion: Sesion) -> Optional[ConfigPasoSesion]:
    return session.execute(
        select(ConfigPasoSesion).where(
            ConfigPasoSesion.tipo_sesion == sesion.tipo_sesion,
            ConfigPasoSesion.paso == sesion.paso_actual,
        )
    ).scalar_one_or_none()


def _respuesta_rechazo(mensaje: str) -> dict:
    return {"autorizado": False, "mensaje": mensaje}


def cmd_resolver(session, payload: dict, ahora: datetime) -> dict:
    """Subcomando `resolver` (D-2): resuelve rol + RBAC y crea/reanuda la
    sesion de `telegram_user_id`, devolviendo el prompt del paso actual."""
    telegram_user_id = payload["telegram_user_id"]

    usuario = _buscar_usuario(session, telegram_user_id)
    if usuario is None:
        resultado = resolver_rol_y_autorizar(
            session, telegram_user_id, _ACCION_PLACEHOLDER_USUARIO_DESCONOCIDO, ahora
        )
        return _respuesta_rechazo(resultado.mensaje)

    sesion_abierta = _buscar_sesion_abierta(session, telegram_user_id)
    accion = sesion_abierta.tipo_sesion if sesion_abierta is not None else ROL_A_TIPO_SESION.get(
        usuario.rol
    )
    if accion is None:
        resultado = resolver_rol_y_autorizar(
            session, telegram_user_id, _ACCION_PLACEHOLDER_USUARIO_DESCONOCIDO, ahora
        )
        return _respuesta_rechazo(resultado.mensaje)

    ensayo_id_objetivo = sesion_abierta.ensayo_id if sesion_abierta is not None else usuario.ensayo_id
    resultado = resolver_rol_y_autorizar(
        session, telegram_user_id, accion, ahora, ensayo_id=ensayo_id_objetivo
    )
    if not resultado.autorizado:
        return _respuesta_rechazo(resultado.mensaje)

    try:
        sesion = resolver_sesion(session, telegram_user_id, usuario.rol, ahora)
    except SessionEngineError as exc:
        return {"autorizado": True, "error": str(exc)}

    config_paso = _paso_actual(session, sesion)
    return {
        "autorizado": True,
        "session_id": sesion.id,
        "tipo_sesion": sesion.tipo_sesion,
        "paso_actual": sesion.paso_actual,
        "prompt": config_paso.prompt if config_paso else None,
        "tipo_respuesta": config_paso.tipo_respuesta if config_paso else None,
    }


def cmd_avanzar(session, payload: dict, ahora: datetime) -> dict:
    """Subcomando `avanzar` (D-2): valida RBAC + `session_engine.avanzar`
    para la respuesta del paso actual de la sesion abierta de
    `telegram_user_id`."""
    telegram_user_id = payload["telegram_user_id"]
    respuesta = payload["respuesta"]

    usuario = _buscar_usuario(session, telegram_user_id)
    if usuario is None:
        resultado = resolver_rol_y_autorizar(
            session, telegram_user_id, _ACCION_PLACEHOLDER_USUARIO_DESCONOCIDO, ahora
        )
        return _respuesta_rechazo(resultado.mensaje)

    sesion_abierta = _buscar_sesion_abierta(session, telegram_user_id)
    if sesion_abierta is None:
        return {"valido": False, "error": "No hay sesion abierta para este usuario."}

    resultado_rbac = resolver_rol_y_autorizar(
        session,
        telegram_user_id,
        sesion_abierta.tipo_sesion,
        ahora,
        ensayo_id=sesion_abierta.ensayo_id,
    )
    if not resultado_rbac.autorizado:
        return _respuesta_rechazo(resultado_rbac.mensaje)

    try:
        resultado_avance = motor_avanzar(session, sesion_abierta, respuesta, ahora)
    except SessionEngineError as exc:
        return {"valido": False, "error": str(exc)}

    if not resultado_avance.valido:
        return {
            "autorizado": True,
            "valido": False,
            "mensaje_reintento": resultado_avance.mensaje,
            "completada": False,
        }

    sesion = resultado_avance.sesion
    if sesion.estado == "completada":
        return {
            "autorizado": True,
            "valido": True,
            "completada": True,
            "session_id": sesion.id,
            "tipo_sesion": sesion.tipo_sesion,
        }

    config_paso = _paso_actual(session, sesion)
    return {
        "autorizado": True,
        "valido": True,
        "completada": False,
        "session_id": sesion.id,
        "prompt": config_paso.prompt if config_paso else None,
        "tipo_respuesta": config_paso.tipo_respuesta if config_paso else None,
    }


def cmd_expirar(session, payload: dict, ahora: datetime) -> dict:
    """Subcomando `expirar` (D-2): barre sesiones vencidas (RN-SES-07,
    24h DD-10) para un trigger programado de n8n."""
    cantidad = expirar_sesiones_vencidas(session, ahora)
    return {"expiradas": cantidad}


def cmd_finalizar_setup(session, payload: dict, ahora: datetime) -> dict:
    """Subcomando `finalizar_setup` (D-2/D-4): construye
    `config/data_dictionary.json` + `config/analysis_config.yaml` de una
    sesion `setup_ensayo` completa.

    Las rutas de destino son las reales del repo (`pipeline.setup_ensayo`
    defaults) SALVO que las variables de entorno
    `SESSION_CLI_DATA_DICTIONARY_PATH`/`SESSION_CLI_ANALYSIS_CONFIG_PATH`
    las sobreescriban -- unico mecanismo para que los tests e2e (D-9) NUNCA
    toquen los archivos reales de `config/` mientras siguen invocando el
    CLI real (subprocess) tal como lo haria n8n."""
    sesion_id = payload["session_id"]
    dictionary_path = os.environ.get("SESSION_CLI_DATA_DICTIONARY_PATH")
    analysis_config_path = os.environ.get("SESSION_CLI_ANALYSIS_CONFIG_PATH")
    resultado = construir_configs_de_setup(
        session,
        sesion_id,
        ahora,
        dictionary_path=dictionary_path,
        analysis_config_path=analysis_config_path,
    )
    if not resultado.ok:
        return {"ok": False, "error": resultado.error}
    return {
        "ok": True,
        "data_dictionary_path": str(resultado.data_dictionary_path),
        "analysis_config_path": str(resultado.analysis_config_path),
    }


_SUBCOMANDOS = {
    "resolver": cmd_resolver,
    "avanzar": cmd_avanzar,
    "expirar": cmd_expirar,
    "finalizar_setup": cmd_finalizar_setup,
}


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.session_cli",
        description=(
            "Frontera interna n8n<->Python del motor de sesiones (DD-05): "
            "recibe JSON por stdin, responde JSON por stdout, exit code "
            "SIEMPRE 0. Nunca es una interfaz para usuarios humanos (DD-09)."
        ),
    )
    parser.add_argument("subcomando", choices=sorted(_SUBCOMANDOS))
    return parser.parse_args(argv)


def _leer_payload_stdin() -> dict:
    crudo = sys.stdin.read().strip()
    if not crudo:
        return {}
    return json.loads(crudo)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entrypoint CLI (D-2): SIEMPRE devuelve 0 -- cualquier fallo (de
    negocio o inesperado) se reporta como `{"error": ...}` en el JSON de
    stdout, nunca como excepcion no capturada ni exit code distinto de 0
    (n8n Execute Command hace THROW ante cualquier exit code != 0)."""
    args = _parse_args(argv)

    try:
        payload = _leer_payload_stdin()
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"stdin no es JSON valido: {exc}"}, ensure_ascii=False))
        return 0

    from pipeline.db import DatabaseUrlNotConfiguredError, build_engine, build_session

    try:
        engine = build_engine()
    except DatabaseUrlNotConfiguredError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 0

    session = build_session(engine)
    ahora = datetime.now(timezone.utc)
    try:
        handler = _SUBCOMANDOS[args.subcomando]
        resultado = handler(session, payload, ahora)
    except Exception as exc:  # noqa: BLE001 -- wrapper exit-0 (D-2): jamas propagar
        resultado = {"error": f"Fallo inesperado en '{args.subcomando}': {exc}"}
    finally:
        session.close()
        engine.dispose()

    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

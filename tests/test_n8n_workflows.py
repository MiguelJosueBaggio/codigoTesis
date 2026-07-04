"""Validacion ESTRUCTURAL de los workflows n8n exportados (change
`n8n-orchestration-workflows` / C-08, D-9 capa 1).

No hay instancia de n8n en la maquina de desarrollo (Context, design.md):
estos exports JSON se testean como DATOS -- se parsean y se verifica su
forma (nodos esperados, orden de conexiones, referencias a `$env`, ausencia
de rutas absolutas/credenciales) -- nunca se ejecutan contra un runtime n8n
real ni se finge uno (D-9, decision honesta central del change).

La capa 2 (e2e real de la cadena CLI) vive en `tests/test_cli_chain.py`; la
capa 3 (runbook manual) vive en `n8n_workflows/README.md`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

WORKFLOWS_DIR = Path(__file__).parent.parent / "n8n_workflows"

RUTA_PRINCIPAL = WORKFLOWS_DIR / "pipeline_principal.json"
RUTA_REINTENTOS = WORKFLOWS_DIR / "ejecutar_etapa_con_reintentos.json"
RUTA_ESCALAMIENTO = WORKFLOWS_DIR / "escalamiento_notificacion.json"

ETAPAS_OBLIGATORIAS = ("ingestion", "validation", "transformation", "persistence")

# Patrones de ruta absoluta de ESTA maquina que jamas deben aparecer en un
# export versionado (D-10: todo por $env, nada hardcodeado).
_PATRONES_RUTA_ABSOLUTA_PROHIBIDOS = (
    "C:\\\\Users",
    "C:/Users",
    "/home/",
    "/Users/",
)
_PATRONES_CREDENCIAL_PROHIBIDOS = ("TELEGRAM_BOT_TOKEN=", "apiKey\":", "password\":", "token\":")


def _cargar(ruta: Path) -> dict:
    with ruta.open(encoding="utf-8") as fh:
        return json.load(fh)


def _texto_crudo(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _nodos_por_tipo(workflow: dict, tipo: str) -> list:
    return [n for n in workflow["nodes"] if n["type"] == tipo]


def _nombres_nodos(workflow: dict) -> set:
    return {n["name"] for n in workflow["nodes"]}


def _bfs_nombres_alcanzables(workflow: dict, origen: str) -> list:
    """Devuelve los nombres de nodo alcanzables desde `origen` siguiendo
    `connections`, en orden de primera visita (BFS) -- para verificar el
    ORDEN relativo de la cadena del Flujo 1 sin depender de la topologia
    exacta de cada rama de error."""
    conexiones = workflow["connections"]
    visitados = [origen]
    cola = [origen]
    vistos = {origen}
    while cola:
        actual = cola.pop(0)
        salidas = conexiones.get(actual, {}).get("main", [])
        for salida in salidas:
            for destino in salida or []:
                nombre = destino["node"]
                if nombre not in vistos:
                    vistos.add(nombre)
                    visitados.append(nombre)
                    cola.append(nombre)
    return visitados


class TestArchivosExisten:
    def test_los_tres_workflows_existen_y_son_json_valido(self):
        for ruta in (RUTA_PRINCIPAL, RUTA_REINTENTOS, RUTA_ESCALAMIENTO):
            assert ruta.exists(), f"Falta el export {ruta}"
            _cargar(ruta)  # no debe levantar json.JSONDecodeError


class TestPipelinePrincipal:
    def test_tiene_los_tres_triggers_del_flujo_1(self):
        """D-7: trigger por archivo nuevo, programacion horaria y manual."""
        workflow = _cargar(RUTA_PRINCIPAL)

        assert _nodos_por_tipo(workflow, "n8n-nodes-base.localFileTrigger")
        assert _nodos_por_tipo(workflow, "n8n-nodes-base.scheduleTrigger")
        assert _nodos_por_tipo(workflow, "n8n-nodes-base.manualTrigger")

    def test_comandos_referencian_python_bin_y_modulo_de_cada_etapa(self):
        """D-1/D-10: los comandos que arma el workflow principal para las 4
        etapas obligatorias referencian `{{$env.PYTHON_BIN}} -m
        pipeline.<etapa>` -- nunca un import de Python (blindaje DD-05)."""
        texto = _texto_crudo(RUTA_PRINCIPAL)

        for etapa in ETAPAS_OBLIGATORIAS:
            patron = "$env.PYTHON_BIN}} -m pipeline." + etapa
            assert patron in texto, f"Falta el patron de comando para la etapa '{etapa}'"

        assert "import pipeline" not in texto
        assert "from pipeline" not in texto

    def test_conexiones_encadenan_las_etapas_en_orden_del_flujo_1(self):
        """D-1: el grafo de conexiones visita las etapas en el orden
        ingestion -> validation -> transformation -> persistence (Flujo 1),
        alcanzables desde el nodo de normalizacion de entrada."""
        workflow = _cargar(RUTA_PRINCIPAL)

        nodo_normalizacion = next(
            n["name"] for n in workflow["nodes"] if "Normalizar" in n["name"]
        )
        alcanzables = _bfs_nombres_alcanzables(workflow, nodo_normalizacion)

        indices_etapa = {}
        for etapa in ETAPAS_OBLIGATORIAS:
            candidatos = [
                nombre
                for nombre in alcanzables
                if etapa.capitalize()[:4].lower() in nombre.lower()
                or etapa in nombre.lower()
            ]
            assert candidatos, f"Ninguna etapa alcanzable menciona '{etapa}'"
            indices_etapa[etapa] = min(alcanzables.index(n) for n in candidatos)

        # El orden relativo de los INDICES de BFS respeta el Flujo 1.
        orden = [indices_etapa[etapa] for etapa in ETAPAS_OBLIGATORIAS]
        assert orden == sorted(orden), (
            f"Las etapas no aparecen en el orden del Flujo 1 (indices BFS: {indices_etapa})"
        )

    def test_analisis_es_condicional_via_if_sobre_analysis_config(self):
        """D-8: tras persistencia exitosa, un nodo IF decide si correr
        analisis segun `analysis_config.yaml`."""
        workflow = _cargar(RUTA_PRINCIPAL)

        nodos_if = _nodos_por_tipo(workflow, "n8n-nodes-base.if")
        assert any("analysis_config" in json.dumps(n["parameters"]).lower() for n in nodos_if)

        texto = _texto_crudo(RUTA_PRINCIPAL)
        assert "$env.PYTHON_BIN}} -m pipeline.analysis" in texto

    def test_mueve_el_archivo_a_procesados_o_errores(self):
        """D-7: el estado 'procesado' es por filesystem -- el archivo de
        entrada se mueve a `procesados/` o `errores/` al terminar."""
        workflow = _cargar(RUTA_PRINCIPAL)
        nombres = _nombres_nodos(workflow)

        assert any("procesados" in n.lower() for n in nombres)
        assert any("errores" in n.lower() for n in nombres)

    def test_escalamiento_via_stop_and_error(self):
        """D-6: ante fallo persistente, un nodo Stop and Error marca la
        ejecucion como fallida (visible/auditable en el dashboard de n8n)."""
        workflow = _cargar(RUTA_PRINCIPAL)

        assert _nodos_por_tipo(workflow, "n8n-nodes-base.stopAndError")

    def test_settings_de_logging_activados(self):
        """D-10: logging de cada ejecucion via settings nativos del workflow."""
        workflow = _cargar(RUTA_PRINCIPAL)
        settings = workflow.get("settings", {})

        assert settings.get("saveDataSuccessExecution") == "all"
        assert settings.get("saveDataErrorExecution") == "all"
        assert settings.get("saveManualExecutions") is True
        assert settings.get("executionOrder") == "v1"

    def test_invoca_el_subworkflow_de_reintentos_por_cada_etapa(self):
        """D-1/D-5: cada etapa se ejecuta via Execute Workflow -> el
        sub-workflow generico de reintentos -- una sola implementacion de la
        politica, no un loop copiado 5 veces."""
        workflow = _cargar(RUTA_PRINCIPAL)

        nodos_execute_workflow = _nodos_por_tipo(workflow, "n8n-nodes-base.executeWorkflow")
        assert len(nodos_execute_workflow) >= len(ETAPAS_OBLIGATORIAS)


class TestSubworkflowReintentos:
    def test_tiene_wait_con_expresion_de_backoff_exponencial(self):
        """D-5: el Wait usa `base * 2^intento` (no el `retryOnFail` nativo de
        intervalo fijo, que no cumple la letra de RN-GLB-03)."""
        workflow = _cargar(RUTA_REINTENTOS)
        nodos_wait = _nodos_por_tipo(workflow, "n8n-nodes-base.wait")

        assert nodos_wait
        texto_parametros = json.dumps([n["parameters"] for n in nodos_wait])
        assert "PIPELINE_BACKOFF_BASE_SEGUNDOS" in texto_parametros
        assert "2" in texto_parametros and ("**" in texto_parametros or "Math.pow" in texto_parametros)

    def test_limite_de_intentos_configurable_por_env(self):
        """D-5: `PIPELINE_REINTENTOS_MAX` (default 3), nunca hardcodeado."""
        texto = _texto_crudo(RUTA_REINTENTOS)
        assert "$env.PIPELINE_REINTENTOS_MAX" in texto

    def test_execute_command_recibe_el_comando_por_parametro_no_hardcodeado(self):
        """D-1: el Execute Command del sub-workflow ejecuta EXACTAMENTE el
        comando que le paso el workflow principal (`$json.comando`) -- una
        sola implementacion generica de la politica de reintentos, sin
        acoplarse a ninguna etapa en particular."""
        workflow = _cargar(RUTA_REINTENTOS)
        nodos_comando = _nodos_por_tipo(workflow, "n8n-nodes-base.executeCommand")

        assert nodos_comando
        texto_parametros = json.dumps([n["parameters"] for n in nodos_comando])
        assert "$json.comando" in texto_parametros
        assert "pipeline." not in texto_parametros  # generico, no acoplado a una etapa

    def test_switch_de_exit_code_distingue_los_tres_casos(self):
        """D-4: el sub-workflow enruta explicitamente sobre `exitCode` (0/1/2)
        -- no depende de que n8n interprete un exit code no-cero como fallo
        de nodo (Riesgo documentado en el design)."""
        workflow = _cargar(RUTA_REINTENTOS)
        nodos_switch = _nodos_por_tipo(workflow, "n8n-nodes-base.switch")

        assert nodos_switch
        texto_parametros = json.dumps([n["parameters"] for n in nodos_switch])
        assert "exitCode" in texto_parametros


class TestEscalamientoNotificacion:
    def test_tiene_error_trigger(self):
        workflow = _cargar(RUTA_ESCALAMIENTO)
        assert _nodos_por_tipo(workflow, "n8n-nodes-base.errorTrigger")

    def test_nodo_telegram_esta_deshabilitado_como_enganche_documentado_c13(self):
        """D-6: el canal Telegram es C-13 (fuera de scope) -- el nodo queda
        como documentacion ejecutable del punto de enganche, deshabilitado."""
        workflow = _cargar(RUTA_ESCALAMIENTO)
        nodos_telegram = _nodos_por_tipo(workflow, "n8n-nodes-base.telegram")

        assert nodos_telegram
        assert all(n.get("disabled") is True for n in nodos_telegram)


class TestAntiDivergenciaConElE2e:
    def test_las_etapas_obligatorias_del_e2e_estan_declaradas_en_el_json(self):
        """6.5 TRIANGULATE: los MISMOS modulos que `tests/test_cli_chain.py`
        ejercita por subprocess (`pipeline.ingestion`, `pipeline.validation`,
        `pipeline.transformation`, `pipeline.persistence`) estan declarados
        como comandos `{{$env.PYTHON_BIN}} -m pipeline.<etapa>` en el
        workflow exportado -- si alguno de los dos se modifica sin el otro,
        este test lo detecta (anti-divergencia workflow/test, Riesgo
        documentado en design.md)."""
        import re

        texto_workflow = _texto_crudo(RUTA_PRINCIPAL)
        texto_e2e = _texto_crudo(Path(__file__).parent / "test_cli_chain.py")

        # `_correr("ingestion", ...)` etc -- el primer argumento posicional
        # de cada invocacion por subprocess en el e2e (D-9 capa 2).
        modulos_en_e2e = set(re.findall(r'_correr\(\s*"(\w+)"', texto_e2e))
        modulos_en_workflow = set(
            re.findall(r"\$env\.PYTHON_BIN\}\} -m pipeline\.(\w+)", texto_workflow)
        )

        etapas_obligatorias_e2e = modulos_en_e2e & set(ETAPAS_OBLIGATORIAS)
        assert etapas_obligatorias_e2e == set(ETAPAS_OBLIGATORIAS), (
            "El e2e no ejercita alguna de las etapas obligatorias esperadas"
        )
        assert etapas_obligatorias_e2e <= modulos_en_workflow, (
            f"Etapas ejercitadas por el e2e mimeticas al workflow: "
            f"e2e={etapas_obligatorias_e2e}, workflow={modulos_en_workflow}"
        )


class TestSinRutasAbsolutasNiCredenciales:
    @pytest.mark.parametrize("ruta", [RUTA_PRINCIPAL, RUTA_REINTENTOS, RUTA_ESCALAMIENTO])
    def test_ningun_export_contiene_ruta_absoluta_ni_credencial(self, ruta):
        """D-10: cero rutas absolutas de esta maquina, cero credenciales --
        todo por variables de entorno, documentado en `.env.example`."""
        texto = _texto_crudo(ruta)

        for patron in _PATRONES_RUTA_ABSOLUTA_PROHIBIDOS:
            assert patron not in texto, f"Ruta absoluta prohibida '{patron}' en {ruta.name}"
        for patron in _PATRONES_CREDENCIAL_PROHIBIDOS:
            assert patron not in texto, f"Posible credencial '{patron}' en {ruta.name}"

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
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

WORKFLOWS_DIR = Path(__file__).parent.parent / "n8n_workflows"

RUTA_PRINCIPAL = WORKFLOWS_DIR / "pipeline_principal.json"
RUTA_REINTENTOS = WORKFLOWS_DIR / "ejecutar_etapa_con_reintentos.json"
RUTA_ESCALAMIENTO = WORKFLOWS_DIR / "escalamiento_notificacion.json"
RUTA_INTERACCION = WORKFLOWS_DIR / "interaccion_telegram.json"

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
    def test_los_cuatro_workflows_existen_y_son_json_valido(self):
        for ruta in (RUTA_PRINCIPAL, RUTA_REINTENTOS, RUTA_ESCALAMIENTO, RUTA_INTERACCION):
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

    def test_trigger_de_archivo_no_observa_subcarpetas(self):
        """Fix post-C-08 (bug #4, verificado en corrida real): el
        localFileTrigger observaba `entrada/` RECURSIVAMENTE -- mover el
        archivo a procesados/ al final del pipeline disparaba OTRO evento
        'add' y el flujo se retroalimentaba en loop (los prefijos run_id se
        acumulaban en el nombre hasta superar MAX_PATH de Windows). El
        trigger debe observar SOLO el nivel raiz (depth=0, 'Top Folder
        Only')."""
        workflow = _cargar(RUTA_PRINCIPAL)
        triggers = _nodos_por_tipo(workflow, "n8n-nodes-base.localFileTrigger")

        assert triggers
        for trigger in triggers:
            assert trigger["parameters"].get("options", {}).get("depth") == 0

    def test_normalizar_ignora_eventos_de_subcarpetas(self):
        """Fix post-C-08 (bug #4, defensa en profundidad): aunque el trigger
        vuelva a observar subcarpetas (p. ej. si alguien toca depth en la
        UI), 'Normalizar Entrada del Archivo' solo acepta rutas que viven
        DIRECTO en PIPELINE_CARPETA_ENTRADA; un evento de procesados/ o
        errores/ cae al barrido de la raiz."""
        workflow = _cargar(RUTA_PRINCIPAL)
        nodo = next(n for n in workflow["nodes"] if "Normalizar" in n["name"])
        codigo = nodo["parameters"]["jsCode"]

        assert "esRutaDirectaDeEntrada" in codigo

    def test_etapas_y_movimientos_referencian_contexto_del_nodo_normalizar(self):
        """Fix post-C-08: la salida del sub-workflow de reintentos es
        {status, stdout} -- NO trae run_id/corrida_dir/ruta_archivo.
        Referenciarlos via `$json` armaba comandos con rutas vacias
        (validacion llego a correr con `--output-dir \"\"`). Todo nodo aguas
        abajo debe tomar el contexto de $('Normalizar Entrada del
        Archivo')."""
        workflow = _cargar(RUTA_PRINCIPAL)

        nodos_a_verificar = _nodos_por_tipo(workflow, "n8n-nodes-base.executeWorkflow") + [
            n
            for n in workflow["nodes"]
            if n["type"] == "n8n-nodes-base.executeCommand"
        ]
        for nodo in nodos_a_verificar:
            texto = json.dumps(nodo["parameters"])
            assert "$('Normalizar Entrada del Archivo')" in texto, nodo["name"]
            for referencia_rota in ("$json.run_id", "$json.corrida_dir", "$json.ruta_archivo"):
                assert referencia_rota not in texto, f"{nodo['name']}: usa {referencia_rota}"


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

    def test_execute_command_ejecuta_via_wrapper_que_nunca_sale_no_cero(self):
        """D-1/D-4 (fix post-C-08): Execute Command de n8n hace THROW cuando
        el proceso sale con exit code != 0 (verificado en
        ExecuteCommand.node.js) -- con `$json.comando` directo la
        clasificacion 0/1/2 del Switch jamas veia un codigo distinto de 0.
        El contrato nuevo: el comando de la etapa se escribe a un archivo en
        el directorio de corrida (`$json.archivo_comando`) y un wrapper
        `python -c` lo ejecuta con subprocess.run(shell=True), sale SIEMPRE 0
        e imprime JSON {exitCode, stdout, stderr} por stdout."""
        workflow = _cargar(RUTA_REINTENTOS)
        nodos_comando = _nodos_por_tipo(workflow, "n8n-nodes-base.executeCommand")

        assert nodos_comando
        texto_parametros = json.dumps([n["parameters"] for n in nodos_comando])
        assert "$json.archivo_comando" in texto_parametros
        assert "subprocess.run" in texto_parametros
        assert "pipeline." not in texto_parametros  # generico, no acoplado a una etapa

        # El archivo de comando se escribe desde el parametro `comando` que
        # paso el workflow principal -- el contrato D-1 sigue vigente.
        texto = _texto_crudo(RUTA_REINTENTOS)
        assert "$json.comando" in texto

    def test_incrementar_intento_conserva_el_contexto_del_loop(self):
        """Fix post-C-08: el Set 'Incrementar Intento' solo emitia `intento`
        -- en el reintento, 'Ejecutar Comando' perdia comando/etapa/run_id.
        Debe incluir los campos de entrada."""
        workflow = _cargar(RUTA_REINTENTOS)
        nodo = next(n for n in workflow["nodes"] if n["name"] == "Incrementar Intento")

        assert nodo["parameters"].get("includeOtherFields") is True

    def test_resultado_del_wrapper_se_recombina_con_el_contexto(self):
        """Fix post-C-08: la salida de Execute Command ({exitCode, stdout,
        stderr}) pierde intento/etapa/comando/run_id -- '¿Quedan
        Reintentos?' leia intento=undefined y escalaba sin reintentar. Un
        nodo Code entre 'Ejecutar Comando' y 'Evaluar Exit Code' parsea el
        JSON del wrapper y lo recombina con el contexto del intento."""
        workflow = _cargar(RUTA_REINTENTOS)
        conexiones = workflow["connections"]

        destino = conexiones["Ejecutar Comando"]["main"][0][0]["node"]
        assert destino != "Evaluar Exit Code", "Falta el nodo que recombina contexto"

        nodo = next(n for n in workflow["nodes"] if n["name"] == destino)
        codigo = nodo["parameters"]["jsCode"]
        assert "JSON.parse" in codigo
        assert "$('Inicializar Intento')" in codigo  # contexto del primer intento
        assert "$('Incrementar Intento')" in codigo  # contexto de los reintentos
        assert conexiones[destino]["main"][0][0]["node"] == "Evaluar Exit Code"

    def test_switch_de_exit_code_distingue_los_tres_casos(self):
        """D-4: el sub-workflow enruta explicitamente sobre `exitCode` (0/1/2)
        -- no depende de que n8n interprete un exit code no-cero como fallo
        de nodo (Riesgo documentado en el design)."""
        workflow = _cargar(RUTA_REINTENTOS)
        nodos_switch = _nodos_por_tipo(workflow, "n8n-nodes-base.switch")

        assert nodos_switch
        texto_parametros = json.dumps([n["parameters"] for n in nodos_switch])
        assert "exitCode" in texto_parametros


def _extraer_codigo_python_c(comando_nodo: str) -> str:
    """Extrae el codigo `-c \"...\"` de un comando de nodo executeCommand.

    Los tests de comportamiento ejecutan ESE codigo (el mismo que corre n8n)
    con el interprete local, sustituyendo las expresiones {{...}} -- se
    ejercita la logica real sin fingir un runtime n8n (D-9)."""
    coincidencia = re.search(r'-c "(.*)"$', comando_nodo)
    assert coincidencia, f"El comando no tiene la forma `-c \"...\"`: {comando_nodo}"
    return coincidencia.group(1)


class TestWrapperDeEjecucionComportamiento:
    """Ejecuta de verdad el wrapper del nodo 'Ejecutar Comando' (fix
    post-C-08): siempre sale 0 y reporta el exitCode real en JSON."""

    def _codigo_wrapper(self, archivo_comando: Path) -> str:
        workflow = _cargar(RUTA_REINTENTOS)
        nodo = _nodos_por_tipo(workflow, "n8n-nodes-base.executeCommand")[0]
        codigo = _extraer_codigo_python_c(nodo["parameters"]["command"])
        return codigo.replace("{{$json.archivo_comando}}", str(archivo_comando))

    def _correr_wrapper(self, tmp_path: Path, comando_interno: str) -> dict:
        archivo_comando = tmp_path / "comando_etapa.txt"
        archivo_comando.write_text(comando_interno, encoding="utf-8")
        resultado = subprocess.run(
            [sys.executable, "-c", self._codigo_wrapper(archivo_comando)],
            capture_output=True,
            text=True,
        )
        assert resultado.returncode == 0, (
            f"El wrapper DEBE salir siempre 0 (salio {resultado.returncode}): "
            f"{resultado.stderr}"
        )
        return json.loads(resultado.stdout)

    def test_exit_code_no_cero_se_reporta_sin_romper_el_nodo(self, tmp_path):
        payload = self._correr_wrapper(
            tmp_path,
            f'"{sys.executable}" -c "import sys; sys.stdout.write(str(21 * 2)); sys.exit(2)"',
        )
        assert payload["exitCode"] == 2
        assert "42" in payload["stdout"]

    def test_exit_cero_conserva_stdout_y_stderr(self, tmp_path):
        payload = self._correr_wrapper(
            tmp_path,
            f'"{sys.executable}" -c "import sys; sys.stdout.write(str(6 * 7)); sys.stderr.write(str(9))"',
        )
        assert payload["exitCode"] == 0
        assert "42" in payload["stdout"]
        assert "9" in payload["stderr"]


class TestMoverArchivoComportamiento:
    """Ejecuta de verdad los comandos de 'Mover Archivo a Procesados' /
    'Mover Archivo a Errores' (fix post-C-08): con un archivo homonimo ya
    presente en el destino, NO pisa ni borra -- mueve con sufijo run_id."""

    def _codigo_mover(self, nombre_nodo: str, ruta_archivo: Path, entrada: Path) -> str:
        workflow = _cargar(RUTA_PRINCIPAL)
        nodo = next(n for n in workflow["nodes"] if n["name"] == nombre_nodo)
        codigo = _extraer_codigo_python_c(nodo["parameters"]["command"])
        return (
            codigo.replace(
                "{{$('Normalizar Entrada del Archivo').first().json.ruta_archivo}}",
                str(ruta_archivo),
            )
            .replace(
                "{{$('Normalizar Entrada del Archivo').first().json.run_id}}",
                "20260704T000000Z_abcd1234",
            )
            .replace("{{$env.PIPELINE_CARPETA_ENTRADA}}", str(entrada))
        )

    @pytest.mark.parametrize(
        ("nombre_nodo", "subcarpeta"),
        [
            ("Mover Archivo a Procesados", "procesados"),
            ("Mover Archivo a Errores", "errores"),
        ],
    )
    def test_mueve_sin_colision(self, tmp_path, nombre_nodo, subcarpeta):
        entrada = tmp_path / "entrada"
        entrada.mkdir()
        archivo = entrada / "demo.csv"
        archivo.write_text("contenido nuevo", encoding="utf-8")

        resultado = subprocess.run(
            [sys.executable, "-c", self._codigo_mover(nombre_nodo, archivo, entrada)],
            capture_output=True,
            text=True,
        )

        assert resultado.returncode == 0, resultado.stderr
        assert not archivo.exists()
        assert (entrada / subcarpeta / "demo.csv").read_text(encoding="utf-8") == "contenido nuevo"

    @pytest.mark.parametrize(
        ("nombre_nodo", "subcarpeta"),
        [
            ("Mover Archivo a Procesados", "procesados"),
            ("Mover Archivo a Errores", "errores"),
        ],
    )
    def test_con_homonimo_en_destino_no_pisa_ni_borra(self, tmp_path, nombre_nodo, subcarpeta):
        entrada = tmp_path / "entrada"
        destino = entrada / subcarpeta
        destino.mkdir(parents=True)
        (destino / "demo.csv").write_text("resto de corrida previa", encoding="utf-8")
        archivo = entrada / "demo.csv"
        archivo.write_text("contenido nuevo", encoding="utf-8")

        resultado = subprocess.run(
            [sys.executable, "-c", self._codigo_mover(nombre_nodo, archivo, entrada)],
            capture_output=True,
            text=True,
        )

        assert resultado.returncode == 0, resultado.stderr
        assert not archivo.exists()
        # El homonimo previo queda intacto; el nuevo entra con sufijo run_id.
        assert (destino / "demo.csv").read_text(encoding="utf-8") == "resto de corrida previa"
        assert (
            destino / "20260704T000000Z_abcd1234_demo.csv"
        ).read_text(encoding="utf-8") == "contenido nuevo"


class TestEscalamientoNotificacion:
    def test_tiene_error_trigger(self):
        workflow = _cargar(RUTA_ESCALAMIENTO)
        assert _nodos_por_tipo(workflow, "n8n-nodes-base.errorTrigger")

    def test_nodo_telegram_existe(self):
        """D-6 (C-08): el nodo Telegram del error-workflow existe. Su estado
        `disabled` cambio de `True` (enganche documentado de C-08) a `False`
        en el change telegram-interaction-layer (C-13, D-7) -- ver
        `TestEscalamientoTelegramHabilitado` mas abajo, que verifica el
        `disabled: false` post-C-13 explicitamente."""
        workflow = _cargar(RUTA_ESCALAMIENTO)
        nodos_telegram = _nodos_por_tipo(workflow, "n8n-nodes-base.telegram")

        assert nodos_telegram


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
    @pytest.mark.parametrize(
        "ruta", [RUTA_PRINCIPAL, RUTA_REINTENTOS, RUTA_ESCALAMIENTO, RUTA_INTERACCION]
    )
    def test_ningun_export_contiene_ruta_absoluta_ni_credencial(self, ruta):
        """D-10: cero rutas absolutas de esta maquina, cero credenciales --
        todo por variables de entorno, documentado en `.env.example`."""
        texto = _texto_crudo(ruta)

        for patron in _PATRONES_RUTA_ABSOLUTA_PROHIBIDOS:
            assert patron not in texto, f"Ruta absoluta prohibida '{patron}' en {ruta.name}"
        for patron in _PATRONES_CREDENCIAL_PROHIBIDOS:
            assert patron not in texto, f"Posible credencial '{patron}' en {ruta.name}"


class TestInteraccionTelegram:
    """Change telegram-interaction-layer (C-13), grupo 5 del tasks.md, D-3:
    UN UNICO loop generico -- se testea como DATOS (D-9), nunca contra un
    runtime n8n real."""

    def test_tiene_telegram_trigger_y_al_menos_un_envio(self):
        """5.1: Telegram Trigger (mensajes + callbacks) y al menos un nodo
        Telegram de envio."""
        workflow = _cargar(RUTA_INTERACCION)

        assert _nodos_por_tipo(workflow, "n8n-nodes-base.telegramTrigger")
        assert _nodos_por_tipo(workflow, "n8n-nodes-base.telegram")

    def test_invoca_session_cli_por_execute_command(self):
        """5.1/5.2: el grafo invoca `pipeline.session_cli` via Execute
        Command (DD-05) -- nunca un import de Python."""
        workflow = _cargar(RUTA_INTERACCION)
        texto = _texto_crudo(RUTA_INTERACCION)

        assert _nodos_por_tipo(workflow, "n8n-nodes-base.executeCommand")
        assert "pipeline.session_cli" in texto
        assert "import pipeline" not in texto
        assert "from pipeline" not in texto

    def test_tiene_wait_for_webhook(self):
        """5.1/5.4: mecanismo de pausa/reanudacion human-in-the-loop (D-5)."""
        workflow = _cargar(RUTA_INTERACCION)
        nodos_wait = _nodos_por_tipo(workflow, "n8n-nodes-base.wait")

        assert nodos_wait
        assert any(n["parameters"].get("resume") == "webhook" for n in nodos_wait)

    def test_nodo_ocr_c11_existe_y_esta_deshabilitado(self):
        """5.3: enganche C-11 documentado y deshabilitado (D-6) -- mismo
        patron que el nodo Telegram disabled de C-08."""
        workflow = _cargar(RUTA_INTERACCION)
        nodo_ocr = next(
            n for n in workflow["nodes"] if "ocr" in n["name"].lower() and "c-11" in n["name"].lower()
        )

        assert nodo_ocr["disabled"] is True

    def test_router_no_ramifica_por_tipo_sesion(self):
        """5.2/5.5 TRIANGULATE: el Switch central decide por el RESULTADO
        del CLI (autorizado/valido/completada), nunca por `tipo_sesion` --
        agregar un paso a `config_paso_sesion` no toca este grafo (D-3)."""
        workflow = _cargar(RUTA_INTERACCION)
        nodo_router = next(
            n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.switch"
        )
        texto_reglas = json.dumps(nodo_router["parameters"])

        assert "tipo_sesion" not in texto_reglas
        assert "autorizado" in texto_reglas or "completada" in texto_reglas or "valido" in texto_reglas

    def test_par_mensaje_botones_antes_del_wait(self):
        """5.4: el nodo que envia el mensaje con botones inline esta
        conectado inmediatamente antes del Wait for Webhook."""
        workflow = _cargar(RUTA_INTERACCION)
        conexiones = workflow["connections"]
        nodo_botones = next(
            n for n in workflow["nodes"] if "botones" in n["name"].lower() and n["type"] == "n8n-nodes-base.telegram"
        )
        assert "inlineKeyboard" in json.dumps(nodo_botones["parameters"])

        destino = conexiones[nodo_botones["name"]]["main"][0][0]["node"]
        nodo_destino = next(n for n in workflow["nodes"] if n["name"] == destino)
        assert nodo_destino["type"] == "n8n-nodes-base.wait"
        assert nodo_destino["parameters"].get("resume") == "webhook"

    def test_agregar_paso_a_config_no_cambia_el_workflow(self):
        """5.5 TRIANGULATE: el JSON del workflow es identico independientemente
        de cuantas filas tenga `config_paso_sesion` -- es DATA en la base, no
        en el grafo. Se verifica indirectamente: ningun nodo referencia un
        `tipo_sesion` concreto (`setup_ensayo` es la unica excepcion
        estructural, usada solo para decidir si INVOCAR finalizar_setup, no
        para bifurcar el flujo de preguntas)."""
        workflow = _cargar(RUTA_INTERACCION)
        # Solo el CONTENIDO ejecutable de los nodos (parametros/tipo/nombre) --
        # la documentacion humana (`meta.description`, `notes`) puede nombrar
        # los cuatro tipo_sesion sin que eso implique una bifurcacion real.
        texto_parametros = json.dumps(
            [{"name": n["name"], "type": n["type"], "parameters": n["parameters"]} for n in workflow["nodes"]]
        )
        tipos_sesion_no_permitidos = ("carga_dato", "confirmacion_ocr", "confirmacion_ia")

        for tipo in tipos_sesion_no_permitidos:
            assert tipo not in texto_parametros, f"El grafo no debe referenciar '{tipo}' (D-3)"


class TestEscalamientoTelegramHabilitado:
    """Change telegram-interaction-layer (C-13), grupo 6 del tasks.md, D-7:
    delta de la capability pipeline-orchestration."""

    def test_nodo_telegram_ya_no_esta_deshabilitado(self):
        """6.1/6.2: el nodo Telegram de escalamiento pasa de `disabled: true`
        (enganche de C-08) a habilitado (RN-GLB-03)."""
        workflow = _cargar(RUTA_ESCALAMIENTO)
        nodos_telegram = _nodos_por_tipo(workflow, "n8n-nodes-base.telegram")

        assert nodos_telegram
        assert all(n.get("disabled") is not True for n in nodos_telegram)

    def test_sigue_sin_token_ni_chat_id_embebidos(self):
        """6.2: `TELEGRAM_BOT_TOKEN`/`chat_id` provienen de credencial/entorno
        de n8n, nunca del JSON."""
        texto = _texto_crudo(RUTA_ESCALAMIENTO)

        assert "TELEGRAM_BOT_TOKEN=" not in texto
        assert "$env.TELEGRAM_CHAT_ID_INGENIERO" in texto

    def test_resto_del_error_workflow_permanece_intacto(self):
        """6.3: el payload de escalamiento estructurado (Error Trigger +
        registro del payload) sigue presente."""
        workflow = _cargar(RUTA_ESCALAMIENTO)

        assert _nodos_por_tipo(workflow, "n8n-nodes-base.errorTrigger")
        nombres = _nombres_nodos(workflow)
        assert any("payload" in n.lower() for n in nombres)

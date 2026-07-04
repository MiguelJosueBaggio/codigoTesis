"""Suite TDD del modulo de ingesta de datos crudos (change ingestion-module / C-03).

Cubre:
- Seccion 2: lectura multi-formato CSV/Excel -> DataFrame crudo (RN-ING-01).
- Seccion 3: deteccion de codificacion/formato antes de continuar (RN-ING-02).
- Seccion 4: validacion de estructura contra el diccionario, con tolerancia
  configurable de capitalizacion/espaciado (RN-ING-03).
- Seccion 5: detencion del proceso + informe estructurado ante error (RN-ING-04).
- Seccion 6: invocacion independiente por CLI (DD-05/DD-09).

NO valida los *valores* de cada registro (eso es C-04); NO normaliza los
nombres de columna del DataFrame devuelto (eso es C-05). Solo fixtures
sinteticos genericos (guardarrail anti-caso-real, igual que C-02).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

FIXTURES_DIR = Path("tests/fixtures")
FIXTURE_DICT_PATH = FIXTURES_DIR / "data_dictionary_sintetico.json"
FIXTURE_CSV_PATH = FIXTURES_DIR / "dataset_sintetico.csv"
FIXTURE_XLSX_PATH = FIXTURES_DIR / "dataset_sintetico.xlsx"
FIXTURE_COLUMNAS_RENOMBRADAS_PATH = FIXTURES_DIR / "dataset_columnas_renombradas.csv"


# ---------------------------------------------------------------------------
# Seccion 2: lectura multi-formato (CSV/Excel) -> DataFrame crudo (RN-ING-01)
# ---------------------------------------------------------------------------


class TestLecturaMultiformato:
    def test_lee_csv_valido_y_devuelve_dataframe_crudo(self):
        """2.1/2.2: lee el CSV sintetico y devuelve un DataFrame con todas las
        filas/columnas y los nombres de columna originales, sin renombrar."""
        from pipeline.ingestion import ingest

        df = ingest(FIXTURE_CSV_PATH, dictionary_path=FIXTURE_DICT_PATH)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 12
        assert list(df.columns) == [
            "id_unidad",
            "bloque",
            "tratamiento",
            "variable_respuesta_1",
            "variable_respuesta_2",
            "fecha_inicio",
            "fecha_fin",
        ]

    def test_lee_excel_valido_y_devuelve_dataframe_equivalente_al_csv(self):
        """2.4 TRIANGULATE: el `.xlsx` (misma tabla que el CSV) converge a la
        misma estructura (filas/columnas) que el CSV."""
        from pipeline.ingestion import ingest

        df_csv = ingest(FIXTURE_CSV_PATH, dictionary_path=FIXTURE_DICT_PATH)
        df_xlsx = ingest(FIXTURE_XLSX_PATH, dictionary_path=FIXTURE_DICT_PATH)

        assert list(df_xlsx.columns) == list(df_csv.columns)
        assert len(df_xlsx) == len(df_csv)


# ---------------------------------------------------------------------------
# Seccion 3: deteccion de codificacion y formato (RN-ING-02)
# ---------------------------------------------------------------------------


class TestDeteccionCodificacionYFormato:
    def test_archivo_con_encoding_invalido_levanta_encoding_error(self, tmp_path):
        """3.1: bytes Latin-1 con caracteres altos, leidos como UTF-8 (default)
        -> `EncodingError`, ningun DataFrame."""
        from pipeline.ingestion import EncodingError, ingest

        ruta = tmp_path / "dataset_encoding_invalido.csv"
        contenido = "id_unidad,bloque\n1,B1 ñoño\n".encode("latin-1")
        ruta.write_bytes(contenido)

        with pytest.raises(EncodingError) as exc_info:
            ingest(ruta, dictionary_path=FIXTURE_DICT_PATH)

        assert exc_info.value.informe.archivo == str(ruta)

    def test_archivo_corrupto_levanta_format_error(self, tmp_path):
        """3.3: un `.xlsx` cuyo contenido no es un archivo Excel real (bytes
        arbitrarios, no un ZIP valido) -> `FormatError`, ningun DataFrame."""
        from pipeline.ingestion import FormatError, ingest

        ruta = tmp_path / "dataset_corrupto.xlsx"
        ruta.write_bytes(b"esto no es un archivo xlsx valido, solo bytes sueltos")

        with pytest.raises(FormatError):
            ingest(ruta, dictionary_path=FIXTURE_DICT_PATH)

    def test_extension_no_soportada_levanta_format_error_sin_leer(self, tmp_path):
        """3.4: extension que no es .csv/.xlsx/.xls -> `FormatError` sin
        intentar leer el contenido."""
        from pipeline.ingestion import FormatError, ingest

        ruta = tmp_path / "dataset.txt"
        ruta.write_text("id_unidad,bloque\n1,B1\n", encoding="utf-8")

        with pytest.raises(FormatError) as exc_info:
            ingest(ruta, dictionary_path=FIXTURE_DICT_PATH)

        assert "no soportad" in exc_info.value.informe.descripcion.lower()

    def test_archivo_inexistente_levanta_format_error_con_informe(self, tmp_path):
        """3.5 TRIANGULATE: archivo inexistente -> `FormatError` (no un
        `FileNotFoundError` crudo) con informe."""
        from pipeline.ingestion import FormatError, ingest

        ruta = tmp_path / "no_existe.csv"

        with pytest.raises(FormatError) as exc_info:
            ingest(ruta, dictionary_path=FIXTURE_DICT_PATH)

        assert exc_info.value.informe.descripcion


# ---------------------------------------------------------------------------
# Seccion 4: validacion de estructura con tolerancia configurable (RN-ING-03)
# ---------------------------------------------------------------------------


class TestValidacionDeEstructura:
    def test_estructura_que_coincide_exactamente_es_aceptada(self):
        """4.1: columnas = nombre_canonico del diccionario -> valida, devuelve
        el DataFrame."""
        from pipeline.ingestion import ingest

        df = ingest(FIXTURE_CSV_PATH, dictionary_path=FIXTURE_DICT_PATH)

        assert not df.empty

    def test_tolerancia_acepta_diferencias_de_capitalizacion_y_espaciado(self, tmp_path):
        """4.3: modo tolerante (default) acepta encabezados que difieren solo
        en capitalizacion/espaciado, y preserva los nombres originales en el
        DataFrame devuelto (la normalizacion es solo para comparar)."""
        from pipeline.ingestion import ingest

        ruta = tmp_path / "dataset_encabezados_variantes.csv"
        ruta.write_text(
            "Id Unidad,BLOQUE,Tratamiento,Variable Respuesta 1,"
            "VARIABLE-RESPUESTA-2,Fecha Inicio,Fecha Fin\n"
            "1,B1,T1,12.5,4.2,2020-01-10,2020-01-20\n",
            encoding="utf-8",
        )

        df = ingest(ruta, dictionary_path=FIXTURE_DICT_PATH)

        assert list(df.columns) == [
            "Id Unidad",
            "BLOQUE",
            "Tratamiento",
            "Variable Respuesta 1",
            "VARIABLE-RESPUESTA-2",
            "Fecha Inicio",
            "Fecha Fin",
        ]

    def test_modo_estricto_rechaza_diferencias_de_capitalizacion_o_espaciado(self, tmp_path):
        """4.4: en modo estricto (`tolerancia=False`), un encabezado que solo
        difiere en capitalizacion/espaciado es rechazado con `StructureError`."""
        from pipeline.ingestion import StructureError, ingest

        ruta = tmp_path / "dataset_encabezados_variantes.csv"
        ruta.write_text(
            "Id Unidad,BLOQUE,Tratamiento,Variable Respuesta 1,"
            "VARIABLE-RESPUESTA-2,Fecha Inicio,Fecha Fin\n"
            "1,B1,T1,12.5,4.2,2020-01-10,2020-01-20\n",
            encoding="utf-8",
        )

        with pytest.raises(StructureError):
            ingest(ruta, dictionary_path=FIXTURE_DICT_PATH, tolerancia=False)

    def test_normalizar_nombre_no_confunde_variables_distintas(self):
        """4.5 TRIANGULATE (guardarrail anti-colision): `variable_respuesta_1`
        y `variable_respuesta_2` normalizan a formas DISTINTAS."""
        from pipeline.ingestion import _normalizar_nombre

        assert _normalizar_nombre("variable_respuesta_1") != _normalizar_nombre(
            "variable_respuesta_2"
        )
        # Caso positivo: variantes del MISMO nombre normalizan igual.
        assert (
            _normalizar_nombre("Variable Respuesta 1")
            == _normalizar_nombre("  variable_respuesta_1 ")
            == _normalizar_nombre("VARIABLE-RESPUESTA-1")
            == "variable_respuesta_1"
        )


# ---------------------------------------------------------------------------
# Seccion 5: detencion del proceso + informe estructurado (RN-ING-04)
# ---------------------------------------------------------------------------


class TestDetencionEInforme:
    def test_columnas_faltantes_o_renombradas_detienen_la_ingesta_con_informe(self):
        """5.1: una columna faltante y una renombrada mas alla de la
        tolerancia -> `StructureError`, ningun DataFrame, informe describe
        que columnas faltan/sobran."""
        from pipeline.ingestion import StructureError, ingest

        with pytest.raises(StructureError) as exc_info:
            ingest(FIXTURE_COLUMNAS_RENOMBRADAS_PATH, dictionary_path=FIXTURE_DICT_PATH)

        informe = exc_info.value.informe
        assert informe.archivo == str(FIXTURE_COLUMNAS_RENOMBRADAS_PATH)
        assert "variable_respuesta_1" in informe.descripcion
        assert "variable_respuesta_X" in informe.descripcion

    @pytest.mark.parametrize(
        "construir_excepcion",
        [
            "encoding",
            "formato",
            "estructura",
        ],
    )
    def test_informe_expone_los_tres_datos_exigidos_por_rn_ing_04(
        self, tmp_path, construir_excepcion
    ):
        """5.3: cualquier `IngestionError` (encoding, formato o estructura)
        expone archivo, fecha/hora y descripcion."""
        from pipeline.ingestion import IngestionError, ingest

        if construir_excepcion == "encoding":
            ruta = tmp_path / "invalido.csv"
            ruta.write_bytes("id_unidad,bloque\n1,ñ\n".encode("latin-1"))
        elif construir_excepcion == "formato":
            ruta = tmp_path / "invalido.txt"
            ruta.write_text("contenido", encoding="utf-8")
        else:
            ruta = FIXTURE_COLUMNAS_RENOMBRADAS_PATH

        with pytest.raises(IngestionError) as exc_info:
            ingest(ruta, dictionary_path=FIXTURE_DICT_PATH)

        informe = exc_info.value.informe
        assert informe.archivo
        assert informe.fecha_hora
        assert informe.descripcion

    def test_descripcion_de_structure_error_enumera_columnas_concretamente(self):
        """5.4 TRIANGULATE: la descripcion enumera QUE columnas faltan/sobran
        (informe accionable), no un mensaje generico."""
        from pipeline.ingestion import StructureError, ingest

        with pytest.raises(StructureError) as exc_info:
            ingest(FIXTURE_COLUMNAS_RENOMBRADAS_PATH, dictionary_path=FIXTURE_DICT_PATH)

        descripcion = exc_info.value.informe.descripcion
        # No es un mensaje generico: nombra las columnas puntuales involucradas.
        assert "variable_respuesta_1" in descripcion
        assert "variable_respuesta_2" in descripcion
        assert "variable_respuesta_X" in descripcion


# ---------------------------------------------------------------------------
# Seccion 6: invocacion por CLI (DD-05/DD-09)
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_ingiere_archivo_valido_con_exito(self, capsys):
        """6.1: `main` sobre un archivo valido -> exit code 0 y resumen de
        filas/columnas en la salida."""
        from pipeline.ingestion import main

        exit_code = main(
            [
                str(FIXTURE_CSV_PATH),
                "--dictionary-path",
                str(FIXTURE_DICT_PATH),
            ]
        )

        salida = capsys.readouterr().out
        assert exit_code == 0
        assert "12" in salida  # filas
        assert "7" in salida  # columnas

    def test_cli_reporta_informe_y_falla_ante_archivo_invalido(self, capsys):
        """6.3: `main` sobre un archivo con error de estructura -> exit code
        no-cero y el informe estructurado (JSON) emitido."""
        from pipeline.ingestion import main

        exit_code = main(
            [
                str(FIXTURE_COLUMNAS_RENOMBRADAS_PATH),
                "--dictionary-path",
                str(FIXTURE_DICT_PATH),
            ]
        )

        salida_error = capsys.readouterr().err
        assert exit_code != 0
        informe = json.loads(salida_error)
        assert informe["archivo"] == str(FIXTURE_COLUMNAS_RENOMBRADAS_PATH)
        assert informe["fecha_hora"]
        assert informe["descripcion"]

    @pytest.mark.parametrize(
        "modo,ruta_fixture,contenido_bytes",
        [
            ("encoding", None, "id_unidad,bloque\n1,ñ\n"),
            ("formato", None, None),
            ("estructura", FIXTURE_COLUMNAS_RENOMBRADAS_PATH, None),
        ],
    )
    def test_cli_distingue_los_tres_modos_de_fallo(
        self, tmp_path, capsys, modo, ruta_fixture, contenido_bytes
    ):
        """6.4 TRIANGULATE: `main` distingue encoding/formato/estructura
        reportando el informe correspondiente; el exito no emite informe."""
        from pipeline.ingestion import main

        if modo == "encoding":
            ruta = tmp_path / "invalido.csv"
            ruta.write_bytes(contenido_bytes.encode("latin-1"))
        elif modo == "formato":
            ruta = tmp_path / "invalido.txt"
            ruta.write_text("contenido", encoding="utf-8")
        else:
            ruta = ruta_fixture

        exit_code = main([str(ruta), "--dictionary-path", str(FIXTURE_DICT_PATH)])
        salida_error = capsys.readouterr().err

        assert exit_code != 0
        informe = json.loads(salida_error)
        assert informe["descripcion"]


# ---------------------------------------------------------------------------
# Seccion 7: convencion de exit codes 0/1/2 (D-4, change n8n-orchestration-workflows)
# ---------------------------------------------------------------------------


class TestConvencionExitCodes:
    def test_error_de_dominio_sale_con_exit_code_1_pinneado(self, capsys):
        """1.2 (D-4): un `IngestionError` de dominio (estructura) sale con
        exit code 1 EXACTO (no un `!= 0` generico) -- n8n distingue esto de
        un fallo transitorio de infraestructura (exit 2) para no reintentar
        un error de datos determinista (RN-GLB-03)."""
        from pipeline.ingestion import main

        exit_code = main(
            [str(FIXTURE_COLUMNAS_RENOMBRADAS_PATH), "--dictionary-path", str(FIXTURE_DICT_PATH)]
        )

        assert exit_code == 1

    def test_fallo_de_infraestructura_sale_con_exit_code_2(self, capsys):
        """1.2 (D-4): un fallo REAL de infraestructura -- el diccionario de
        variables (`--dictionary-path`) apunta a una ruta inaccesible, lo que
        levanta un `OSError` crudo (nunca envuelto en `IngestionError`) desde
        `load_data_dictionary` -- sale con exit code 2, distinto del exit 1
        de errores de dominio. n8n reintenta solo el 2 (RN-GLB-03)."""
        from pipeline.ingestion import main

        exit_code = main(
            [
                str(FIXTURE_CSV_PATH),
                "--dictionary-path",
                "carpeta_inexistente/diccionario_inaccesible.json",
            ]
        )

        salida_error = capsys.readouterr().err
        assert exit_code == 2
        informe = json.loads(salida_error)
        assert informe["error"]


# ---------------------------------------------------------------------------
# Seccion 8: --output + manifest.json (D-2, D-3, change n8n-orchestration-workflows)
# ---------------------------------------------------------------------------


class TestCLIOutputYManifest:
    def test_output_preserva_dtypes_al_recargar_pickle(self, tmp_path):
        """2.1: el artefacto serializado por `--output` (pickle, D-2) preserva
        los dtypes EXACTOS (incluida la columna con `NaN`,
        `variable_respuesta_2`) al recargarlo -- `assert_frame_equal` es
        estricto en dtype por default. Un round-trip CSV (alternativa
        descartada en D-2) perderia esa fidelidad: todo vuelve como texto/objeto
        y hay que re-parsear en cada etapa, exactamente lo que el pickle evita."""
        from pipeline.ingestion import ingest, main

        ruta_salida = tmp_path / "corrida" / "ingerido.pkl"
        exit_code = main(
            [
                str(FIXTURE_XLSX_PATH),
                "--dictionary-path",
                str(FIXTURE_DICT_PATH),
                "--output",
                str(ruta_salida),
            ]
        )

        assert exit_code == 0
        assert ruta_salida.exists()

        df_original = ingest(FIXTURE_XLSX_PATH, dictionary_path=FIXTURE_DICT_PATH)
        df_recargado = pd.read_pickle(ruta_salida)

        pd.testing.assert_frame_equal(df_original, df_recargado)
        # dtype por columna preservado 1:1 -- ninguna columna vuelve como
        # texto/objeto generico tras el round-trip pickle (D-2).
        for columna in df_original.columns:
            assert df_recargado[columna].dtype == df_original[columna].dtype

    def test_output_escribe_manifest_json_con_ruta_y_conteo(self, tmp_path):
        """2.2: `--output` crea/actualiza `manifest.json` (D-3) en el mismo
        directorio, con la ruta original y el conteo de registros leidos --
        el unico lugar donde viven esos datos para la etapa siguiente."""
        from pipeline.ingestion import main

        ruta_salida = tmp_path / "corrida" / "ingerido.pkl"
        exit_code = main(
            [
                str(FIXTURE_CSV_PATH),
                "--dictionary-path",
                str(FIXTURE_DICT_PATH),
                "--output",
                str(ruta_salida),
            ]
        )

        assert exit_code == 0
        manifest_path = ruta_salida.parent / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["ruta_archivo_entrada"] == str(FIXTURE_CSV_PATH)
        assert manifest["registros_leidos"] == 12

    def test_fallo_real_de_escritura_del_artefacto_sale_exit_code_2(self, tmp_path):
        """2.3 TRIANGULATE: fallo REAL de escritura -- el directorio padre de
        `--output` no puede crearse porque un ARCHIVO ya ocupa ese nombre --
        sale con exit code 2 (infraestructura), sin excepcion sin capturar."""
        from pipeline.ingestion import main

        bloqueador = tmp_path / "bloqueador"
        bloqueador.write_text("ocupo el nombre de archivo", encoding="utf-8")
        ruta_salida = bloqueador / "sub" / "ingerido.pkl"

        exit_code = main(
            [
                str(FIXTURE_CSV_PATH),
                "--dictionary-path",
                str(FIXTURE_DICT_PATH),
                "--output",
                str(ruta_salida),
            ]
        )

        assert exit_code == 2

    def test_sin_output_el_comportamiento_actual_queda_intacto(self, capsys, tmp_path):
        """2.3 TRIANGULATE: sin `--output`, el comportamiento pre-existente
        (solo resumen, sin escribir artefactos ni manifest) queda intacto."""
        from pipeline.ingestion import main

        exit_code = main([str(FIXTURE_CSV_PATH), "--dictionary-path", str(FIXTURE_DICT_PATH)])

        assert exit_code == 0
        assert "12" in capsys.readouterr().out
        assert not (tmp_path / "manifest.json").exists()

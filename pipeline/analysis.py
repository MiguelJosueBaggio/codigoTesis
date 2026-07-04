"""pipeline/analysis.py — Módulo operativo de análisis estadístico (C-07).

Change `statistical-analysis-module` (openspec/changes/statistical-analysis-module/).

Envoltorio operativo del núcleo puro `pipeline/analysis_core.py` (change
`anova-tukey-core`, archivado y validado): este módulo (1) reconstruye un
``DataFrame`` tidy a partir de un dataset ya persistido (change
`persistence-audit-module`, C-06), identificado por el id de su ``Ensayo``;
(2) despacha el análisis parametrizado (``anova``, ``kruskal``, ``glm``)
delegando SIEMPRE en el núcleo para la estadística de ANOVA/Tukey/
diagnósticos; (3) materializa los artefactos de reporte (tabla CSV+HTML,
diagnóstico con gráficos PNG, config YAML re-ejecutable); y (4) expone un
CLI fino (patrón ``pipeline/ingestion.py``) que n8n invoca internamente
(DD-09).

Restricción dura (DD-07 / RN-EST-06): la comparación de medias post-ANOVA
SIEMPRE proviene de ``pipeline.analysis_core.tukey_hsd`` (que usa el
``MS_error``/``df_error`` del modelo COMPLETO). Este módulo NUNCA llama a
``statsmodels.stats.multicomp.pairwise_tukeyhsd`` sobre grupos crudos — ese
es el bug ya encontrado y corregido en el núcleo (``npk``: naive p≈0.0221
vs. correcto p≈0.0071, ver knowledge-base/11_analisis_estadistico_anova_tukey.md).

``analysis_core.py`` NO se modifica ni se reimplementa (regla dura del
proyecto): este módulo solo lo CONSUME.

Alcance v1 (SU-02, Open Question 2 resuelta): ``anova`` (DCA/BCA vía OLS,
delegado al núcleo), ``kruskal`` (delegado al núcleo) y una vía ``glm``
gaussiana mínima ajustada acá mismo vía
``statsmodels.formula.api.glm`` (sin tocar el núcleo). Modelos lineales
mixtos (``lmm``) quedan explícitamente FUERA de v1 y se rechazan con un
error claro — no es un fallo opaco, es una decisión de alcance documentada.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

import matplotlib

matplotlib.use("Agg")  # nunca interactivo / display (D4, RN-EST-03).
import matplotlib.pyplot as plt

import pandas as pd
import yaml
from scipy import stats as scipy_stats
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from statsmodels.formula.api import glm as _smf_glm
from statsmodels.genmod.families import Gaussian
from statsmodels.graphics.gofplots import qqplot
from statsmodels.stats.outliers_influence import OLSInfluence

from pipeline import analysis_core
from pipeline.models import Ambiente, Ensayo, Observacion, Tratamiento, UnidadExperimental

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Mapeo rol->nombre de columna de salida para v1 (Decision 3 del design,
# mismo patrón que `persistence._COLUMNAS_JERARQUIA_V1`): sobreescribible
# por parámetro (`mapeo_roles`) cuando el caso de estudio real lo requiera.
_MAPEO_ROLES_V1: Mapping[str, str] = {
    "tratamiento": "tratamiento",
    "bloque": "bloque",
}

_TIPOS_SOPORTADOS = ("anova", "kruskal", "glm")


class AnalysisError(Exception):
    """Base de los errores propios de la capa operativa de análisis (C-07)."""


class DatasetNoEncontradoError(AnalysisError):
    """No existe (o no tiene observaciones) el dataset persistido solicitado."""


class TipoAnalisisNoSoportadoError(AnalysisError):
    """El tipo de análisis solicitado no está soportado en v1 (ej. `lmm`)."""


# --- Lectura del dataset persistido por id (RN-EST-05, D2/D3) --------------


def cargar_dataset(
    session: Session,
    ensayo_id: int,
    mapeo_roles: Optional[Mapping[str, str]] = None,
) -> pd.DataFrame:
    """Reconstruye un `DataFrame` tidy a partir de un dataset ya persistido.

    Une `Observacion` + `UnidadExperimental` + `Tratamiento` + `Ambiente` por
    ORM (DD-11 — nunca SQL crudo) filtrando por el `Ensayo` indicado, y
    pivota el formato largo (`variable`/`valor` por unidad) a tidy: una fila
    por `UnidadExperimental`, una columna por cada `variable` observada más
    las columnas de rol `tratamiento`/`bloque` (Decision 2 del design).

    Recibe la `Session` ya ligada (Decision 2/7 del design, patrón de
    `pipeline.persistence`): este módulo NUNCA construye el `Engine`.

    Args:
        session: `Session` de SQLAlchemy ya ligada a un engine.
        ensayo_id: id del `Ensayo` cuyo dataset se quiere reconstruir.
        mapeo_roles: sobreescribe el nombre de columna de salida para los
            roles `tratamiento`/`bloque` (Decision 3); por default usa el
            contrato v1 (`_MAPEO_ROLES_V1`).

    Returns:
        `DataFrame` tidy apto para pasar a `pipeline.analysis_core.fit_model`.

    Raises:
        DatasetNoEncontradoError: si no existe un `Ensayo` con ese id, o si
            existe pero no tiene ninguna observación almacenada (nunca se
            devuelve un `DataFrame` vacío silenciosamente).
    """
    mapeo = dict(_MAPEO_ROLES_V1)
    if mapeo_roles:
        mapeo.update(mapeo_roles)

    ensayo = session.get(Ensayo, ensayo_id)
    if ensayo is None:
        raise DatasetNoEncontradoError(
            f"No existe un dataset persistido: no hay ningun Ensayo con id={ensayo_id}."
        )

    filas = session.execute(
        select(
            Observacion.unidad_experimental_id,
            Observacion.variable,
            Observacion.valor,
            Tratamiento.descripcion,
            Ambiente.descripcion,
        )
        .join(UnidadExperimental, Observacion.unidad_experimental_id == UnidadExperimental.id)
        .join(Tratamiento, UnidadExperimental.tratamiento_id == Tratamiento.id)
        .join(Ambiente, UnidadExperimental.ambiente_id == Ambiente.id)
        .where(Tratamiento.ensayo_id == ensayo_id)
    ).all()

    if not filas:
        raise DatasetNoEncontradoError(
            f"El Ensayo id={ensayo_id} (codigo={ensayo.codigo!r}) no tiene "
            "ninguna observacion almacenada."
        )

    largo = pd.DataFrame(
        filas,
        columns=[
            "unidad_experimental_id",
            "variable",
            "valor",
            "_tratamiento_desc",
            "_ambiente_desc",
        ],
    )

    pivote = largo.pivot_table(
        index="unidad_experimental_id", columns="variable", values="valor", aggfunc="first"
    )
    pivote.columns.name = None
    pivote = pivote.reset_index()

    metadatos = largo[
        ["unidad_experimental_id", "_tratamiento_desc", "_ambiente_desc"]
    ].drop_duplicates(subset="unidad_experimental_id")

    tidy = pivote.merge(metadatos, on="unidad_experimental_id")
    tidy = tidy.rename(
        columns={
            "_tratamiento_desc": mapeo["tratamiento"],
            "_ambiente_desc": mapeo["bloque"],
        }
    )
    tidy = tidy.drop(columns=["unidad_experimental_id"]).reset_index(drop=True)
    return tidy


# --- Dispatch del análisis delegando en el núcleo (RN-EST-01, D1) ----------


@dataclass
class ResultadoAnalisis:
    """Resultado en memoria de `ejecutar_analisis`: la tabla que se
    materializa en CSV/HTML (RN-EST-02), la comparación de medias (Tukey,
    solo `anova` con `factor`), el diagnóstico de supuestos del núcleo, y el
    objeto `modelo` ajustado (`None` para `kruskal`, que no ajusta OLS)."""

    tipo: str
    tabla: pd.DataFrame
    tukey: Optional[pd.DataFrame] = None
    diagnosticos: dict = field(default_factory=dict)
    modelo: Any = None


def _resolver_familia_glm(familia_glm: Optional[str]):
    """Resuelve la familia de un GLM (D7, Open Question 2 resuelta): v1
    ofrece únicamente la familia Gaussiana; cualquier otra se rechaza con un
    error claro en vez de intentar ajustarla a ciegas (familias no
    gaussianas y GLM avanzado quedan como extensión futura junto a LMM)."""
    familia_glm = familia_glm or "gaussian"
    if familia_glm != "gaussian":
        raise AnalysisError(
            f"Familia GLM '{familia_glm}' no soportada en v1 (solo 'gaussian'). "
            "Familias no gaussianas quedan como extension futura."
        )
    return Gaussian()


def ejecutar_analisis(
    df: pd.DataFrame,
    formula: str,
    tipo: str,
    factor: Optional[str] = None,
    alpha: float = 0.05,
    familia_glm: Optional[str] = None,
) -> ResultadoAnalisis:
    """Ejecuta el análisis parametrizado (RN-EST-01) delegando EXCLUSIVAMENTE
    en `pipeline.analysis_core` para ANOVA/Tukey/diagnósticos (D1). Nunca
    reimplementa esa estadística ni recalcula medias por su cuenta.

    Args:
        df: `DataFrame` tidy (de `cargar_dataset` o encadenado del pipeline).
        formula: fórmula R-style (ej. `"rendimiento ~ C(bloque) + C(tratamiento)"`).
        tipo: `"anova"`, `"kruskal"` o `"glm"`.
        factor: factor de agrupamiento para la comparación de medias
            (Tukey) y el diagnóstico de supuestos (`anova`), o el factor de
            agrupamiento requerido por `kruskal`. Ignorado en `glm`.
        alpha: nivel de significancia.
        familia_glm: familia del GLM (solo `"gaussian"` soportada en v1).

    Raises:
        TipoAnalisisNoSoportadoError: `tipo` no está en
            `{"anova", "kruskal", "glm"}` (ej. `"lmm"`) — LMM es trabajo
            futuro, documentado como Non-Goal.
        AnalysisError: `tipo="kruskal"` sin `factor`, o familia GLM no
            gaussiana.
    """
    if tipo not in _TIPOS_SOPORTADOS:
        raise TipoAnalisisNoSoportadoError(
            f"Tipo de analisis '{tipo}' no soportado en v1 (soportados: "
            f"{list(_TIPOS_SOPORTADOS)}). Los modelos lineales mixtos (LMM) "
            "son trabajo futuro, fuera de alcance de v1 (SU-02)."
        )

    if tipo == "kruskal":
        if factor is None:
            raise AnalysisError("El analisis 'kruskal' requiere el parametro 'factor'.")
        resultado_kw = analysis_core.kruskal_wallis(df, formula, factor, alpha=alpha)
        tabla = pd.DataFrame([resultado_kw])
        return ResultadoAnalisis(tipo=tipo, tabla=tabla)

    if tipo == "glm":
        familia = _resolver_familia_glm(familia_glm)
        modelo = _smf_glm(formula, data=df, family=familia).fit()
        tabla = pd.DataFrame(
            {
                "coef": modelo.params,
                "std_err": modelo.bse,
                "z_value": modelo.tvalues,
                "p_value": modelo.pvalues,
            }
        )
        return ResultadoAnalisis(tipo=tipo, tabla=tabla, modelo=modelo)

    # tipo == "anova": único punto de ajuste (`fit_model`), el mismo `modelo`
    # se comparte con `compute_anova_table`/`tukey_hsd`/`diagnose_assumptions`
    # (patrón D3 del núcleo) — nunca se reajusta ni se recalculan medias por
    # fuera de esas funciones (blindaje DD-07 / RN-EST-06).
    modelo = analysis_core.fit_model(df, formula)
    tabla = analysis_core.compute_anova_table(df, formula, modelo=modelo)

    tukey = None
    diagnosticos: dict = {}
    if factor is not None:
        tukey = analysis_core.tukey_hsd(df, formula, factor, alpha=alpha, modelo=modelo)
        diagnosticos = analysis_core.diagnose_assumptions(df, formula, factor, modelo=modelo)

    return ResultadoAnalisis(tipo=tipo, tabla=tabla, tukey=tukey, diagnosticos=diagnosticos, modelo=modelo)


# --- Reporte: tabla CSV+HTML (RN-EST-02) -----------------------------------


def escribir_tabla_resultados(
    tabla: pd.DataFrame, directorio_salida: Union[str, Path], nombre_base: str = "resultados"
) -> tuple[Path, Path]:
    """Materializa `tabla` en CSV y HTML (RN-EST-02), con los mismos valores
    numéricos en ambos formatos. Sin timestamps/nonces (D6, RN-GLB-02): esos
    metadatos viven solo en el YAML de config/auditoría."""
    directorio_salida = Path(directorio_salida)
    directorio_salida.mkdir(parents=True, exist_ok=True)
    ruta_csv = directorio_salida / f"{nombre_base}.csv"
    ruta_html = directorio_salida / f"{nombre_base}.html"
    tabla.to_csv(ruta_csv, index=True)
    tabla.to_html(ruta_html, index=True)
    return ruta_csv, ruta_html


# --- Diagnóstico de supuestos con gráficos PNG (RN-EST-03, D4, OQ3/OQ4) ----


def generar_graficos_diagnostico(
    modelo, directorio_salida: Union[str, Path]
) -> tuple[Path, Path]:
    """Genera los dos PNG de diagnóstico (Q-Q normal y residuos-vs-ajustados)
    con matplotlib backend `Agg` (D4): sin display, apto para CI/n8n
    headless. Cierra las figuras tras guardarlas."""
    directorio_salida = Path(directorio_salida)
    directorio_salida.mkdir(parents=True, exist_ok=True)

    ruta_qq = directorio_salida / "diagnostico_qq.png"
    fig_qq = qqplot(modelo.resid, line="s")
    fig_qq.savefig(ruta_qq)
    plt.close(fig_qq)

    ruta_residuos = directorio_salida / "diagnostico_residuos_vs_ajustados.png"
    fig_residuos, ejes = plt.subplots()
    ejes.scatter(modelo.fittedvalues, modelo.resid)
    ejes.axhline(0, linestyle="--", color="gray")
    ejes.set_xlabel("Valores ajustados")
    ejes.set_ylabel("Residuos")
    ejes.set_title("Residuos vs. Ajustados")
    fig_residuos.savefig(ruta_residuos)
    plt.close(fig_residuos)

    return ruta_qq, ruta_residuos


def diagnostico_extendido(
    modelo,
    df: pd.DataFrame,
    formula: str,
    factor: str,
    top_n: int = 5,
) -> dict:
    """Diagnóstico adicional de I/O que el núcleo no expone (OQ3/OQ4): NO es
    estadística nueva de ANOVA — usa `OLSInfluence` (statsmodels) y
    `scipy.stats.bartlett` como complemento del Shapiro/Levene del núcleo.

    - **Distancia de Cook** (OQ4): apalancamiento/outliers vía
      `OLSInfluence(modelo).cooks_distance`, top-`top_n`.
    - **Bartlett** (OQ3): columna adicional opcional de homocedasticidad,
      complementaria a Levene (que ya es el diagnóstico primario del
      núcleo, validado sobre `npk`).
    """
    influencia = OLSInfluence(modelo)
    cooks, _ = influencia.cooks_distance
    cooks_serie = pd.Series(cooks, index=df.index).nlargest(top_n)
    tabla_cooks = pd.DataFrame(
        {"indice": cooks_serie.index, "cooks_distance": cooks_serie.to_numpy()}
    ).reset_index(drop=True)

    variable_respuesta = formula.split("~")[0].strip()
    grupos = [valores[variable_respuesta].to_numpy() for _, valores in df.groupby(factor)]
    bartlett_stat, bartlett_p = scipy_stats.bartlett(*grupos)

    return {
        "cooks_distance_top": tabla_cooks,
        "bartlett": {"statistic": float(bartlett_stat), "p_value": float(bartlett_p)},
    }


# --- Config YAML re-ejecutable (RN-EST-04, D5) ------------------------------


@dataclass
class ConfigAnalisis:
    """Config re-ejecutable del análisis (RN-EST-04): documenta exactamente
    qué se ejecutó — dataset id, fórmula, tipo, parámetros, versión del
    código (commit git) y las rutas de salida."""

    dataset_id: Optional[int]
    formula: str
    tipo: str
    alpha: float
    metodo_comparacion: str
    factor: Optional[str]
    commit_git: Optional[str]
    ejecucion_id: Optional[str]
    directorio_salida: str

    def to_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "formula": self.formula,
            "tipo": self.tipo,
            "alpha": self.alpha,
            "metodo_comparacion": self.metodo_comparacion,
            "factor": self.factor,
            "commit_git": self.commit_git,
            "ejecucion_id": self.ejecucion_id,
            "directorio_salida": self.directorio_salida,
        }


def _commit_git_actual() -> Optional[str]:
    """Hash del commit Git del repo del proyecto (mismo patrón que
    `pipeline.persistence._commit_git_actual`, duplicado localmente para no
    depender de una función privada de otro módulo). Devuelve `None` si no
    hay repo Git disponible en vez de fallar la corrida por un dato
    secundario de auditoria."""
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        return resultado.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def escribir_config_yaml(config: ConfigAnalisis, ruta: Union[str, Path]) -> Path:
    """Escribe `config` como YAML (D5, requiere PyYAML)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8") as archivo:
        yaml.safe_dump(config.to_dict(), archivo, allow_unicode=True, sort_keys=False)
    return ruta


def leer_config_yaml(ruta: Union[str, Path]) -> dict:
    """Lee un YAML de config previamente escrito por `escribir_config_yaml`."""
    with Path(ruta).open("r", encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


# --- Orquestación de punta a punta (standalone o encadenado) ---------------


@dataclass
class ResultadoReporte:
    """Resultado completo de `analizar`: el `ResultadoAnalisis` en memoria
    más las rutas de todos los artefactos materializados en disco."""

    resultado_analisis: ResultadoAnalisis
    diagnosticos_extendidos: dict
    directorio_salida: Path
    ruta_csv: Path
    ruta_html: Path
    ruta_yaml: Path
    ruta_qq: Optional[Path] = None
    ruta_residuos: Optional[Path] = None


def analizar(
    *,
    directorio_salida: Union[str, Path],
    formula: str,
    tipo: str,
    session: Optional[Session] = None,
    dataset_id: Optional[int] = None,
    df: Optional[pd.DataFrame] = None,
    factor: Optional[str] = None,
    alpha: float = 0.05,
    metodo_comparacion: str = "tukey",
    mapeo_roles: Optional[Mapping[str, str]] = None,
    familia_glm: Optional[str] = None,
    ejecucion_id: Optional[str] = None,
) -> ResultadoReporte:
    """Orquesta un análisis de punta a punta (RN-EST-05): carga el dataset
    (por id, standalone) o lo recibe ya armado (`df`, encadenado al
    pipeline), ejecuta el análisis delegando en el núcleo, y materializa
    todos los artefactos de reporte (tabla, diagnóstico PNG si aplica, YAML
    re-ejecutable).

    Ante los mismos datos y el mismo código, dos ejecuciones producen
    tablas de resultados numéricas idénticas (RN-GLB-02, D6): la tabla no
    incluye timestamps ni nonces.
    """
    if df is None:
        if session is None or dataset_id is None:
            raise AnalysisError(
                "Se requiere pasar 'df' directamente (encadenado) o "
                "'session' + 'dataset_id' (standalone)."
            )
        df = cargar_dataset(session, dataset_id, mapeo_roles=mapeo_roles)

    resultado = ejecutar_analisis(
        df, formula, tipo, factor=factor, alpha=alpha, familia_glm=familia_glm
    )

    directorio_salida = Path(directorio_salida)
    ruta_csv, ruta_html = escribir_tabla_resultados(resultado.tabla, directorio_salida)

    ruta_qq: Optional[Path] = None
    ruta_residuos: Optional[Path] = None
    extendido: dict = {}
    if tipo == "anova" and factor is not None:
        ruta_qq, ruta_residuos = generar_graficos_diagnostico(resultado.modelo, directorio_salida)
        extendido = diagnostico_extendido(resultado.modelo, df, formula, factor)

    config = ConfigAnalisis(
        dataset_id=dataset_id,
        formula=formula,
        tipo=tipo,
        alpha=alpha,
        metodo_comparacion=metodo_comparacion,
        factor=factor,
        commit_git=_commit_git_actual(),
        ejecucion_id=ejecucion_id,
        directorio_salida=str(directorio_salida),
    )
    ruta_yaml = escribir_config_yaml(config, directorio_salida / "config.yaml")

    return ResultadoReporte(
        resultado_analisis=resultado,
        diagnosticos_extendidos=extendido,
        directorio_salida=directorio_salida,
        ruta_csv=ruta_csv,
        ruta_html=ruta_html,
        ruta_yaml=ruta_yaml,
        ruta_qq=ruta_qq,
        ruta_residuos=ruta_residuos,
    )


def re_ejecutar_desde_config(ruta_config: Union[str, Path], session: Optional[Session] = None) -> ResultadoReporte:
    """Re-ejecuta un análisis leyendo ÚNICAMENTE el YAML de config generado
    por una corrida previa (RN-EST-04): un solo comando reproduce la misma
    tabla de resultados."""
    config = leer_config_yaml(ruta_config)
    return analizar(
        directorio_salida=config["directorio_salida"],
        formula=config["formula"],
        tipo=config["tipo"],
        session=session,
        dataset_id=config.get("dataset_id"),
        factor=config.get("factor"),
        alpha=config.get("alpha", 0.05),
        metodo_comparacion=config.get("metodo_comparacion", "tukey"),
        ejecucion_id=config.get("ejecucion_id"),
    )


# --- CLI fino (RN-EST-05, DD-09, patrón ingestion.py) -----------------------


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.analysis",
        description=(
            "Ejecuta un analisis estadistico (ANOVA/Kruskal/GLM) sobre un "
            "dataset ya persistido. Entrypoint interno para que n8n invoque "
            "el modulo (DD-05/DD-09); no es una interfaz para usuarios humanos."
        ),
    )
    parser.add_argument(
        "--config", default=None, help="Ruta a un YAML de config para re-ejecutar (RN-EST-04)"
    )
    parser.add_argument("--dataset-id", type=int, default=None, help="Id del Ensayo persistido")
    parser.add_argument("--formula", default=None, help="Formula R-style del modelo")
    parser.add_argument("--tipo", default="anova", choices=list(_TIPOS_SOPORTADOS))
    parser.add_argument("--factor", default=None, help="Factor de agrupamiento (Tukey/diagnostico/kruskal)")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--metodo-comparacion", default="tukey")
    parser.add_argument(
        "--output-dir", default="./salida_analisis", help="Directorio de salida de los artefactos"
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entrypoint CLI fino sobre `analizar`/`re_ejecutar_desde_config`
    (DD-05, refinado por DD-09). Toda la logica testeable vive fuera del
    entrypoint; este solo parsea argumentos, construye la `Session` desde
    `DATABASE_URL` (`pipeline.db`), invoca el analisis y reporta el
    resultado (o el error) por stdout/stderr con codigo de salida acorde."""
    from pipeline.db import build_engine, build_session

    args = _parse_args(argv)

    try:
        engine = build_engine()
        session = build_session(engine)
        try:
            if args.config:
                resultado = re_ejecutar_desde_config(args.config, session=session)
            else:
                if args.dataset_id is None or args.formula is None:
                    raise AnalysisError(
                        "Se requiere --dataset-id y --formula (o --config)."
                    )
                resultado = analizar(
                    directorio_salida=args.output_dir,
                    formula=args.formula,
                    tipo=args.tipo,
                    session=session,
                    dataset_id=args.dataset_id,
                    factor=args.factor,
                    alpha=args.alpha,
                    metodo_comparacion=args.metodo_comparacion,
                )
        finally:
            session.close()
    except AnalysisError as exc:
        # Error de dominio/datos (D-4, change n8n-orchestration-workflows):
        # deterministico (ej. dataset_id inexistente en una base ACCESIBLE),
        # n8n NO debe reintentarlo -- exit 1.
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (OperationalError, OSError) as exc:
        # Fallo transitorio de infraestructura (D-4): base de datos bloqueada
        # o inaccesible (`OperationalError` de SQLAlchemy) u otro error de
        # sistema de archivos (`OSError`). n8n SI debe reintentarlo
        # (RN-GLB-03) -- exit 2.
        print(
            json.dumps({"error": f"Fallo de infraestructura: {exc}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    print(f"Analisis completado. Artefactos en {resultado.directorio_salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

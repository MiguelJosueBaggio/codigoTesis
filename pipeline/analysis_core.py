"""pipeline/analysis_core.py — Núcleo estadístico puro (ANOVA + Tukey HSD + diagnósticos).

Change: anova-tukey-core (openspec/changes/anova-tukey-core/).

Este módulo es una capa de **función pura**: recibe un ``DataFrame`` de pandas en
formato tidy y una fórmula R-style, y devuelve estructuras de datos en memoria
(tablas ANOVA, comparaciones de medias, diagnósticos). NO tiene dependencia de
persistencia (base de datos), ingesta ni orquestación (n8n); no lee ni escribe
disco, red ni base de datos. Esas responsabilidades pertenecen al change C-07
(``statistical-analysis-module``), que envuelve este núcleo.

Alcance (SU-02): diseños completamente aleatorios (DCA) y bloques completos al
azar (BCA/RCBD). Modelos lineales mixtos (LMM) y otros diseños quedan fuera de
v1 (trabajo futuro).

Gotcha de ``yield`` (D4): el dataset de referencia ``npk`` trae la variable de
respuesta original como columna ``yield``, que es palabra reservada de Python
y rompe el parseo de fórmulas de patsy/statsmodels con un error opaco
(``SyntaxError``/``PatsyError`` críptico). ``fit_model`` —punto único de ajuste
usado por todas las funciones de este módulo— detecta nombres reservados en la
fórmula ANTES de llamar a patsy y falla con ``ReservedKeywordFormulaError``, un
mensaje explícito pidiendo renombrar la columna (ej. ``yield`` -> ``rendimiento``).
No se renombra en silencio: preservar la trazabilidad del dato es más
importante que la comodidad de un rename automático. ``kruskal_wallis``
también aplica este guard aunque no ajuste ``ols`` (RN-EST-01, D8).

Extensión aditiva (D6-D8, 2º pase): ``tukey_hsd`` ya es genérico en el número
de niveles ``k`` (no solo el caso ``k=2`` de ``npk``) y su control de FWER vía
``psturng`` está validado con un factor sintético de 10 niveles (D6).
``compute_anova_table``/``fit_model`` soportan modelos factoriales completos
con interacciones (ej. ``rendimiento ~ C(block) + C(N)*C(P)*C(K)``, D7);
sobre ``npk`` (diseño de media fracción) la interacción triple ``N:P:K``
está confundida (aliased) con los bloques, y a diferencia de R (``aov``),
``statsmodels``/``patsy`` NO la descarta automáticamente: reporta una fila
con df=1 y una ``sum_sq`` espuria que rompe la identidad SS total = suma de
efectos + residual en exactamente esa magnitud (ver
``tests/test_analysis_core.py::TestFactorialAnovaWithInteractions`` para el
comportamiento pinneado). ``kruskal_wallis`` (D8) agrega la alternativa no
paramétrica basada en rangos, como wrapper fino sobre ``scipy.stats.kruskal``,
sin ajustar ``ols``.

Extensión aditiva (D9, 3er pase): ``sanity_checks`` agrega una capa de
alertas NO bloqueante (advisory / human-in-the-loop, RN-IA; tolerancia a
fallo, RN-GLB-01) motivada por un fallo silencioso real descubierto durante
la extensión factorial (D7): sobre ``npk`` (media fracción), ``statsmodels``
ajusta vía pseudo-inversa una matriz de diseño rango-deficiente (``N:P:K``
aliasada con los bloques) sin emitir warning ni error. ``sanity_checks``
corre tres chequeos deterministas (rango de la matriz de diseño, supuestos
violados —reutilizando ``diagnose_assumptions``, sin reimplementar
Shapiro/Levene— y tamaño de grupo insuficiente) y devuelve SIEMPRE una
``list[dict]`` (vacía = sin hallazgos), sin propagar excepciones nunca.

Extensión aditiva (D10, 4º pase): transformación de la variable de
respuesta (log/sqrt/inverse) como PRIMERA línea de remedio ante violación
de supuestos (tesis §2.5, RN-EST-01), ANTES de Kruskal-Wallis (D8) y de
GLM/LMM (trabajo futuro). Dos funciones con responsabilidades separadas:
``apply_transformation`` es la mecánica ESTRICTA —pura, nunca muta ``df``,
agrega una columna nueva en vez de pisar la original (misma trazabilidad
que D4)— y levanta ``InvalidTransformationError`` (gemela de
``ReservedKeywordFormulaError``) ante dominio inválido: ``log`` requiere
``y > 0``, ``sqrt`` requiere ``y >= 0``, ``inverse`` requiere ``y != 0``; es
una restricción numérica REAL, no advisory, porque el dominio inválido
produciría ``NaN``/``inf`` silenciosos. ``suggest_transformation`` es la
capa ADVISORY (como ``sanity_checks``, D9): reutiliza
``diagnose_assumptions`` para verificar EMPÍRICAMENTE —no a ciegas— si cada
candidato (en el orden de prioridad de la tesis: log -> sqrt -> inverse)
realmente resuelve las violaciones del ``baseline`` para ESE dataset,
atrapando ``InvalidTransformationError`` de ``apply_transformation`` como
única fuente de verdad del dominio (nunca reimplementa el chequeo), y
nunca levanta salvo que la fórmula ORIGINAL dispare el guard de ``yield``
aguas arriba (D4). Verificado empíricamente que ambas rutas coexisten sin
fricción: los nombres de columna generados (ej. ``rendimiento_log``) nunca
son palabras reservadas de Python.
"""

from __future__ import annotations

import keyword
import math
import re
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.libqsturng import psturng


class ReservedKeywordFormulaError(ValueError):
    """La fórmula referencia un nombre de columna que es palabra reservada de Python."""


class InvalidTransformationError(ValueError):
    """Dominio inválido para la transformación solicitada, o nombre desconocido (D10).

    Gemela de ``ReservedKeywordFormulaError`` (D4): en ambos casos se prefiere
    fallar ruidosamente y explícito antes que producir un resultado silencioso
    e incorrecto (``NaN``/``inf`` en este caso).
    """


def _check_reserved_keywords(formula: str) -> None:
    """Detecta palabras reservadas de Python (ej. ``yield``) en una fórmula R-style.

    ``patsy``/``statsmodels`` parsean la fórmula generando código Python; un
    nombre de columna que coincide con una keyword (``yield``, ``class``,
    etc.) rompe ese parseo con un error opaco. Se detecta acá, antes de tocar
    patsy, y se falla con un mensaje claro (D4).
    """
    identificadores = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", formula)
    reservados = sorted({token for token in identificadores if keyword.iskeyword(token)})
    if reservados:
        raise ReservedKeywordFormulaError(
            "La fórmula usa nombre(s) reservado(s) de Python: "
            f"{reservados}. Palabras reservadas (ej. 'yield') rompen el parseo "
            "de fórmulas de patsy/statsmodels. Renombrá la columna antes de "
            "construir la fórmula (ej. 'yield' -> 'rendimiento')."
        )


def _response_variable(formula: str) -> str:
    """Extrae el nombre de la variable de respuesta (lado izquierdo) de una
    fórmula R-style (ej. ``"rendimiento ~ C(block) + C(N)"`` -> ``"rendimiento"``)."""
    return formula.split("~")[0].strip()


def fit_model(df: pd.DataFrame, formula: str):
    """Ajusta un modelo lineal (OLS) sobre ``df`` con la fórmula R-style dada.

    Punto único de ajuste: las demás funciones del módulo llaman a esta función
    para compartir el MISMO objeto ``modelo`` ajustado. También es el punto
    único donde se valida el gotcha de nombres reservados (D4): si la fórmula
    referencia una palabra reservada de Python (ej. ``yield``), se levanta
    ``ReservedKeywordFormulaError`` con un mensaje claro en vez de dejar que
    patsy falle de forma opaca.
    """
    _check_reserved_keywords(formula)
    return ols(formula, data=df).fit()


def compute_anova_table(
    df: pd.DataFrame, formula: str, typ: int = 1, modelo=None
) -> pd.DataFrame:
    """Ajusta el modelo y devuelve la tabla ANOVA con sumas de cuadrados Tipo I.

    Si se pasa ``modelo`` (un objeto ya ajustado por ``fit_model``), se
    reutiliza tal cual y NO se vuelve a ajustar — este es el mecanismo que
    permite compartir el mismo ajuste (mismo ``MS_error``) entre
    ``compute_anova_table``, ``tukey_hsd`` y ``diagnose_assumptions`` (D3).
    """
    if modelo is None:
        modelo = fit_model(df, formula)
    return anova_lm(modelo, typ=typ)


def get_error_stats(anova_table: pd.DataFrame) -> tuple[float, float]:
    """Extrae ``MS_error`` y ``df_error`` (fila ``Residual``) de una tabla ANOVA.

    Este es el punto que consume el grupo 3 (Tukey HSD): el ``MS_error`` del
    modelo COMPLETO (bloque + tratamiento) es lo que evita, por diseño, el bug
    de ``pairwise_tukeyhsd`` sobre grupos crudos (DD-07).
    """
    residual = anova_table.loc["Residual"]
    df_error = residual["df"]
    ms_error = residual["sum_sq"] / df_error
    return ms_error, df_error


def tukey_hsd(
    df: pd.DataFrame, formula: str, factor: str, alpha: float = 0.05, modelo=None
) -> pd.DataFrame:
    """Tukey HSD correcto para diseños bloqueados (DD-07 / RN-EST-06).

    A diferencia de ``statsmodels.stats.multicomp.pairwise_tukeyhsd(endog, groups)``
    —que ignora cualquier factor de bloque y calcula su propia varianza residual
    a partir SOLO de los grupos crudos, dando p-valores incorrectos en RCBD—
    esta función:

    1. Ajusta el modelo COMPLETO (bloque + tratamiento) vía ``fit_model``/``compute_anova_table``.
    2. Extrae ``MS_error`` y ``df_error`` de ESE modelo completo (``get_error_stats``).
    3. Para cada par de niveles ``(i, j)`` del ``factor``:
       ``q = |media_i - media_j| / sqrt(MS_error * (1/n_i + 1/n_j) / 2)``.
    4. p-valor vía ``statsmodels.stats.libqsturng.psturng(q, k, df_error)``, con
       ``k`` = nº de niveles del factor.

    Validado sobre el dataset ``npk``: reproduce exactamente (hasta el 4º
    decimal) el p-valor del F-test de la ANOVA bloqueada para un factor de 2
    niveles (0.0071), mientras que ``pairwise_tukeyhsd`` naive da 0.0221 —
    discrepancia sustantiva, no un redondeo (ver
    knowledge-base/11_analisis_estadistico_anova_tukey.md).

    Si se pasa ``modelo`` (ya ajustado, ej. por ``fit_model`` o compartido con
    una llamada previa a ``compute_anova_table``), se reutiliza tal cual y NO
    se vuelve a ajustar ni se recalcula la varianza a partir de los grupos
    crudos — esto es lo que evita, por construcción, el bug de
    ``pairwise_tukeyhsd`` (DD-07 / RN-EST-06, ver tarea 3.3).
    """
    if modelo is None:
        modelo = fit_model(df, formula)
    tabla_anova = compute_anova_table(df, formula, typ=1, modelo=modelo)
    ms_error, df_error = get_error_stats(tabla_anova)

    variable_respuesta = _response_variable(formula)
    agrupado = df.groupby(factor)[variable_respuesta]
    medias = agrupado.mean()
    conteos = agrupado.count()
    niveles = list(medias.index)
    k = len(niveles)

    filas = []
    for nivel_i, nivel_j in combinations(niveles, 2):
        media_i, media_j = medias[nivel_i], medias[nivel_j]
        n_i, n_j = conteos[nivel_i], conteos[nivel_j]
        # Convención: meandiff = media(group2) - media(group1), igual que
        # statsmodels.stats.multicomp.pairwise_tukeyhsd, para que el signo sea
        # comparable entre ambas implementaciones (ver test anti-regresión 3.2).
        diferencia = media_j - media_i
        error_estandar = math.sqrt(ms_error * (1 / n_i + 1 / n_j) / 2)
        q = abs(diferencia) / error_estandar
        p_valor = float(np.ravel(psturng(q, k, df_error))[0])
        filas.append(
            {
                "group1": nivel_i,
                "group2": nivel_j,
                "meandiff": diferencia,
                "p_value": p_valor,
                "reject": p_valor < alpha,
            }
        )

    return pd.DataFrame(filas)


def diagnose_assumptions(
    df: pd.DataFrame, formula: str, factor: str, modelo=None
) -> dict:
    """Diagnóstico de supuestos sobre el modelo ajustado.

    - **Normalidad de residuos** (Shapiro-Wilk) sobre ``modelo.resid``.
    - **Homocedasticidad** (Levene) sobre los valores CRUDOS de la variable de
      respuesta agrupados por ``factor`` (no sobre los residuos): esto es lo
      validado contra el fixture ``npk`` (p≈0.9421) y es la forma estándar de
      chequear igualdad de varianzas entre los niveles del factor de
      tratamiento.

    Si se pasa ``modelo`` ya ajustado, se reutiliza (mismo patrón que
    ``compute_anova_table``/``tukey_hsd``, D3).

    Devuelve un dict con la forma::

        {
            "shapiro": {"statistic": float, "p_value": float},
            "levene": {"statistic": float, "p_value": float},
        }
    """
    if modelo is None:
        modelo = fit_model(df, formula)

    shapiro_stat, shapiro_p = scipy_stats.shapiro(modelo.resid)

    variable_respuesta = _response_variable(formula)
    grupos = [
        valores[variable_respuesta].to_numpy()
        for _, valores in df.groupby(factor)
    ]
    levene_stat, levene_p = scipy_stats.levene(*grupos)

    return {
        "shapiro": {"statistic": float(shapiro_stat), "p_value": float(shapiro_p)},
        "levene": {"statistic": float(levene_stat), "p_value": float(levene_p)},
    }


def kruskal_wallis(
    df: pd.DataFrame, formula: str, factor: str, alpha: float = 0.05
) -> dict:
    """Kruskal-Wallis: alternativa no paramétrica a la ANOVA (D8, RN-EST-01).

    Wrapper FINO sobre ``scipy.stats.kruskal``: NO reimplementa el
    estadístico H con rangos a mano, y a diferencia de
    ``compute_anova_table``/``tukey_hsd``/``diagnose_assumptions`` NO ajusta
    un modelo lineal (``ols``) ni acepta un parámetro ``modelo=`` — al ser
    rank-based no hay ajuste que compartir (D3 no aplica acá). Es ADITIVA:
    no modifica la ruta ANOVA/Tukey/diagnósticos existente.

    Reutiliza ``_response_variable`` para extraer la variable de respuesta
    del lado izquierdo de ``formula`` y el guard ``_check_reserved_keywords``
    heredado del módulo (D4): una fórmula que referencia ``yield`` falla con
    ``ReservedKeywordFormulaError`` igual que en ``fit_model``.

    Devuelve ``{"statistic": float, "p_value": float, "reject": bool}`` con
    ``reject = p_value < alpha``, misma forma de dict que
    ``diagnose_assumptions``.
    """
    _check_reserved_keywords(formula)
    variable_respuesta = _response_variable(formula)
    grupos = [
        valores[variable_respuesta].to_numpy() for _, valores in df.groupby(factor)
    ]
    statistic, p_value = scipy_stats.kruskal(*grupos)

    return {
        "statistic": float(statistic),
        "p_value": float(p_value),
        "reject": p_value < alpha,
    }


def sanity_checks(
    df: pd.DataFrame,
    formula: str,
    factor: str | None = None,
    modelo=None,
    alpha: float = 0.05,
    min_group_size: int = 2,
) -> list[dict]:
    """Capa de sanity-checks / alertas NO bloqueante (D9).

    Motivada por un fallo silencioso REAL descubierto durante la extensión
    factorial (grupo 8, D7): sobre ``npk`` (diseño de media fracción),
    ``statsmodels``/``patsy`` ajusta SILENCIOSAMENTE una matriz de diseño
    rango-deficiente vía pseudo-inversa (``C(N):C(P):C(K)`` confundida con
    los bloques, rank=12 sobre 13 columnas) y ``anova_lm`` reporta una
    ``sum_sq`` espuria sin warning ni error (ver
    ``tests/test_analysis_core.py::TestFactorialAnovaWithInteractions``).

    Corre TRES chequeos deterministas y devuelve una LISTA de advertencias
    estructuradas —lista VACÍA significa que no se detectó ningún problema.
    Es una capa advisory / human-in-the-loop (RN-IA; tolerancia a fallo
    RN-GLB-01): la capa AVISA, el analista humano DECIDE. NUNCA levanta
    excepción ni frena la corrida: si un chequeo interno falla, se atrapa y
    se omite (en vez de propagar), preservando la garantía no bloqueante.
    Es lo OPUESTO al guard de ``yield`` (D4), que sí levanta
    ``ReservedKeywordFormulaError`` porque ahí el input es inutilizable; acá
    el análisis es válido pero perfectible, y frenarlo sería
    contraproducente.

    Reutiliza el objeto ``modelo`` compartido (patrón ``modelo=``, D3) y
    ``diagnose_assumptions`` para el chequeo de supuestos — NO reimplementa
    Shapiro/Levene, evitando una segunda fuente de verdad que podría
    divergir del cálculo ya validado en el grupo 4.

    Los tres chequeos:

    1. **Rango de la matriz de diseño**: compara
       ``np.linalg.matrix_rank(modelo.model.exog)`` contra el nº de
       columnas de ``exog``. Si el rango es menor, agrega una advertencia
       ``rank_deficiency`` con ``details={"rank", "n_columns", "deficiency"}``.
       Caso de regresión conocido: la fórmula factorial completa sobre
       ``npk`` (``rendimiento ~ C(block) + C(N)*C(P)*C(K)``) da rank=12
       sobre 13 columnas — el fallo silencioso original de D7.
    2. **Supuestos violados** (sólo si se pasa ``factor``): llama a
       ``diagnose_assumptions(df, formula, factor, modelo=modelo)`` y, por
       cada prueba (``shapiro``, ``levene``) con ``p_value < alpha``, agrega
       una advertencia ``assumption_violation`` con
       ``details={"test", "p_value", "alpha"}``.
    3. **Tamaño de grupo insuficiente** (sólo si se pasa ``factor``): por
       cada nivel de ``factor`` con menos de ``min_group_size``
       observaciones, agrega ``insufficient_group_size`` con
       ``details={"factor", "level", "n", "min_group_size"}``. Default
       ``min_group_size=2``: es el piso MATEMÁTICO por debajo del cual la
       varianza intra-grupo es indefinida (un único dato no tiene
       dispersión) — dispara sólo el caso inequívocamente roto, con CERO
       falsos positivos; se expone como parámetro para protocolos más
       estrictos (D9-d).

    Sin ``factor`` (``factor=None``), se OMITEN los chequeos 2 y 3 (Levene y
    el conteo por nivel necesitan el factor) y se ejecuta SÓLO el chequeo de
    rango, que sólo necesita la fórmula.
    """
    advertencias: list[dict] = []

    if modelo is None:
        try:
            modelo = fit_model(df, formula)
        except Exception:
            return advertencias

    # Chequeo 1: rango de la matriz de diseño.
    try:
        exog = modelo.model.exog
        rank = int(np.linalg.matrix_rank(exog))
        n_columns = int(exog.shape[1])
        if rank < n_columns:
            deficiencia = n_columns - rank
            advertencias.append(
                {
                    "check": "rank_deficiency",
                    "message": (
                        f"La matriz de diseño es rango-deficiente: rank={rank} "
                        f"de {n_columns} columnas (deficiencia={deficiencia}). "
                        "statsmodels ajusta vía pseudo-inversa sin avisar; "
                        "el/los término(s) confundido(s) pueden reportar sumas "
                        "de cuadrados espurias (ver D9, D7)."
                    ),
                    "details": {
                        "rank": rank,
                        "n_columns": n_columns,
                        "deficiency": deficiencia,
                    },
                }
            )
    except Exception:
        pass

    if factor is not None:
        # Chequeo 2: supuestos violados (reutiliza diagnose_assumptions).
        try:
            diagnosticos = diagnose_assumptions(df, formula, factor, modelo=modelo)
            for nombre_test, resultado_test in diagnosticos.items():
                p_value = resultado_test["p_value"]
                if p_value < alpha:
                    advertencias.append(
                        {
                            "check": "assumption_violation",
                            "message": (
                                f"El supuesto evaluado por '{nombre_test}' no se "
                                f"cumple: p_value={p_value:.4f} < alpha={alpha}."
                            ),
                            "details": {
                                "test": nombre_test,
                                "p_value": p_value,
                                "alpha": alpha,
                            },
                        }
                    )
        except Exception:
            pass

        # Chequeo 3: tamaño de grupo insuficiente por nivel del factor.
        try:
            conteos = df.groupby(factor)[factor].count()
            for nivel, n in conteos.items():
                n = int(n)
                if n < min_group_size:
                    advertencias.append(
                        {
                            "check": "insufficient_group_size",
                            "message": (
                                f"El nivel '{nivel}' del factor '{factor}' tiene "
                                f"sólo {n} observación(es), por debajo del "
                                f"mínimo esperado ({min_group_size})."
                            ),
                            "details": {
                                "factor": factor,
                                "level": nivel,
                                "n": n,
                                "min_group_size": min_group_size,
                            },
                        }
                    )
        except Exception:
            pass

    return advertencias


_TRANSFORMATIONS = {
    "log": {
        "fn": np.log,
        "invalid": lambda y: y <= 0,
        "motivo": "log indefinido para y <= 0",
    },
    "sqrt": {
        "fn": np.sqrt,
        "invalid": lambda y: y < 0,
        "motivo": "sqrt indefinida para y < 0",
    },
    "inverse": {
        "fn": lambda y: 1 / y,
        "invalid": lambda y: y == 0,
        "motivo": "1/y indefinida para y == 0 (división por cero)",
    },
}


def apply_transformation(
    df: pd.DataFrame,
    response_var: str,
    transformation: str,
    new_column: str | None = None,
) -> pd.DataFrame:
    """Aplica una transformación a la variable de respuesta (D10, 1ª línea de
    remedio ante violación de supuestos, tesis §2.5).

    Mecánica ESTRICTA (contraparte del guard `yield` de D4): esta función
    NUNCA produce ``NaN``/``inf`` silenciosos. Si el dominio de la
    transformación solicitada no admite algún valor de ``response_var`` (o si
    se pide una transformación desconocida), levanta
    ``InvalidTransformationError`` con un mensaje explícito — es una
    restricción numérica REAL, no advisory (a diferencia de
    ``suggest_transformation``, que SÍ es advisory y nunca levanta).

    Transformaciones soportadas y sus guards de dominio:

    - ``log``: ``numpy.log(y)``; guard ``y <= 0`` (log indefinido en 0 y
      negativos).
    - ``sqrt``: ``numpy.sqrt(y)``; guard ``y < 0`` (``sqrt(0) == 0`` es
      válido; sólo los negativos rompen).
    - ``inverse``: ``1 / y``; guard ``y == 0`` (división por cero; ``1/y``
      de un valor negativo SÍ está definida).

    Devuelve un ``DataFrame`` NUEVO (copia de ``df``) con una columna
    adicional ``new_column`` (default ``f"{response_var}_{transformation}"``,
    ej. ``rendimiento_log``) que contiene la respuesta transformada. NUNCA
    muta ``df`` ni reemplaza la columna original: se preserva el dato crudo
    (misma filosofía de trazabilidad que D4 — no se pisa el dato en
    silencio).
    """
    if transformation not in _TRANSFORMATIONS:
        raise InvalidTransformationError(
            f"Transformación desconocida: '{transformation}'. "
            f"Transformaciones soportadas: {sorted(_TRANSFORMATIONS)}."
        )

    espec = _TRANSFORMATIONS[transformation]
    y = df[response_var].to_numpy()

    if np.any(espec["invalid"](y)):
        raise InvalidTransformationError(
            f"La transformación '{transformation}' no es aplicable a "
            f"'{response_var}': {espec['motivo']}."
        )

    columna_nueva = new_column or f"{response_var}_{transformation}"
    resultado = df.copy()
    resultado[columna_nueva] = espec["fn"](y)
    return resultado


def suggest_transformation(
    df: pd.DataFrame,
    formula: str,
    factor: str,
    transformations: tuple[str, ...] = ("log", "sqrt", "inverse"),
    modelo=None,
    alpha: float = 0.05,
) -> dict:
    """Capa ADVISORY: ¿transformar REALMENTE arregla los supuestos de ESTE
    dataset? (D10, 1ª línea de remedio de la tesis §2.5, ANTES de
    Kruskal-Wallis/D8).

    A diferencia de ``apply_transformation`` (mecánica estricta que SÍ
    levanta ante dominio inválido), esta función NUNCA levanta por un
    candidato no aplicable: reutiliza ``apply_transformation`` como ÚNICA
    fuente de verdad del dominio, atrapa ``InvalidTransformationError`` y
    marca ese candidato ``applicable=False`` con el motivo (misma filosofía
    advisory que ``sanity_checks``, D9, RN-GLB-01). La única excepción que SÍ
    puede propagar es ``ReservedKeywordFormulaError`` si la fórmula ORIGINAL
    referencia ``yield`` — ese guard (D4) sigue disparando aguas arriba, vía
    ``diagnose_assumptions``/``fit_model``, porque ahí el input es
    inutilizable (no es un problema del candidato de transformación).

    Reutiliza ``diagnose_assumptions`` para el ``baseline`` (respuesta sin
    transformar) y para cada candidato transformado — NO reimplementa
    Shapiro/Levene (misma regla anti-duplicación de D1/D8/D9).

    Para cada candidato, en el orden de prioridad de la tesis (``log`` ->
    ``sqrt`` -> ``inverse`` por default), se marca ``resolves_violations``
    cuando el candidato deja OK (``p_value >= alpha``) TODOS los supuestos
    que el ``baseline`` tenía violados (no exige mejorar los que ya
    cumplían). ``recommended`` es el PRIMER candidato aplicable que resuelve,
    o ``None`` si ninguno lo hace — ``None`` es un resultado legítimo y
    honesto (ver hallazgo empírico del fixture de outliers en D10).

    Devuelve::

        {
            "baseline": {"shapiro_p", "levene_p", "normal_ok", "homoscedastic_ok"},
            "candidates": [
                {"transformation", "applicable", "reason",
                 "shapiro_p", "levene_p", "normal_ok", "homoscedastic_ok",
                 "resolves_violations"},
                ...
            ],
            "recommended": str | None,
        }
    """
    diagnostico_base = diagnose_assumptions(df, formula, factor, modelo=modelo)
    baseline = {
        "shapiro_p": diagnostico_base["shapiro"]["p_value"],
        "levene_p": diagnostico_base["levene"]["p_value"],
        "normal_ok": diagnostico_base["shapiro"]["p_value"] >= alpha,
        "homoscedastic_ok": diagnostico_base["levene"]["p_value"] >= alpha,
    }

    variable_respuesta = _response_variable(formula)
    _, lado_derecho = formula.split("~", 1)

    candidatos = []
    recomendado = None

    for transformacion in transformations:
        entrada = {
            "transformation": transformacion,
            "applicable": False,
            "reason": None,
            "shapiro_p": None,
            "levene_p": None,
            "normal_ok": None,
            "homoscedastic_ok": None,
            "resolves_violations": False,
        }
        try:
            df_transformado = apply_transformation(
                df, variable_respuesta, transformacion
            )
        except InvalidTransformationError as error:
            entrada["reason"] = str(error)
            candidatos.append(entrada)
            continue

        columna_transformada = f"{variable_respuesta}_{transformacion}"
        formula_transformada = f"{columna_transformada} ~ {lado_derecho.strip()}"
        diagnostico_candidato = diagnose_assumptions(
            df_transformado, formula_transformada, factor
        )

        entrada["applicable"] = True
        entrada["shapiro_p"] = diagnostico_candidato["shapiro"]["p_value"]
        entrada["levene_p"] = diagnostico_candidato["levene"]["p_value"]
        entrada["normal_ok"] = entrada["shapiro_p"] >= alpha
        entrada["homoscedastic_ok"] = entrada["levene_p"] >= alpha

        resuelve = True
        if not baseline["normal_ok"] and not entrada["normal_ok"]:
            resuelve = False
        if not baseline["homoscedastic_ok"] and not entrada["homoscedastic_ok"]:
            resuelve = False
        entrada["resolves_violations"] = resuelve

        candidatos.append(entrada)
        if recomendado is None and resuelve:
            recomendado = transformacion

    return {
        "baseline": baseline,
        "candidates": candidatos,
        "recommended": recomendado,
    }

"""Tests TDD para pipeline/analysis_core.py (change anova-tukey-core)."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats as scipy_stats

from pipeline.analysis_core import (
    InvalidTransformationError,
    ReservedKeywordFormulaError,
    apply_transformation,
    compute_anova_table,
    diagnose_assumptions,
    fit_model,
    get_error_stats,
    kruskal_wallis,
    sanity_checks,
    suggest_transformation,
    tukey_hsd,
)


@pytest.fixture
def synthetic_10_level_df() -> pd.DataFrame:
    """Dataset sintético balanceado (D6): ningún factor real de `npk` tiene
    más de 2 niveles, así que se construye acá un factor de tratamiento de
    10 niveles con medias conocidas (espaciadas 3.0 unidades) y ruido
    gaussiano de semilla fija, para ejercitar de verdad el control FWER de
    `tukey_hsd` (C(10,2)=45 comparaciones). Reutilizado por todo el grupo 7
    para no duplicar la construcción del dataset entre tareas (7.4)."""
    rng = np.random.default_rng(seed=7)
    niveles = [f"T{i}" for i in range(10)]
    repeticiones = 6
    filas = [{"tratamiento": nivel} for nivel in niveles for _ in range(repeticiones)]
    df = pd.DataFrame(filas)
    medias_conocidas = {nivel: 50.0 + i * 3.0 for i, nivel in enumerate(niveles)}
    ruido = rng.normal(0, 2.0, size=len(df))
    df["rendimiento"] = df["tratamiento"].map(medias_conocidas) + ruido
    return df


class TestComputeAnovaTable:
    """Grupo 2: tabla ANOVA (Tipo I secuencial)."""

    def test_one_way_anova_returns_table_with_df_sumsq_f_pvalue(self):
        """One-way ANOVA (DCA): la tabla debe tener df, sum_sq, F y PR(>F)
        para el término del tratamiento y para el residual."""
        df = pd.DataFrame(
            {
                "tratamiento": ["A", "A", "A", "B", "B", "B", "C", "C", "C"],
                "rendimiento": [10.0, 12.0, 11.0, 20.0, 22.0, 21.0, 15.0, 17.0, 16.0],
            }
        )

        tabla = compute_anova_table(df, "rendimiento ~ C(tratamiento)")

        assert "C(tratamiento)" in tabla.index
        assert "Residual" in tabla.index
        for columna in ("df", "sum_sq", "F", "PR(>F)"):
            assert columna in tabla.columns
        assert tabla.loc["Residual", "df"] == 6

    def test_two_way_anova_npk_regression(self, npk_df):
        """Two-way ANOVA con bloque sobre el fixture npk (regresión, valores
        cross-validados por 3 métodos independientes durante el propose-phase).

        rendimiento ~ C(block) + C(N):
        - bloque: df=5, F≈3.395, p≈0.0262
        - N: df=1, F≈9.360, p≈0.0071
        - residual: df=17, MS_error≈20.2228
        """
        tabla = compute_anova_table(npk_df, "rendimiento ~ C(block) + C(N)")

        assert tabla.loc["C(block)", "df"] == 5
        assert tabla.loc["C(block)", "F"] == pytest.approx(3.395, abs=1e-3)
        assert tabla.loc["C(block)", "PR(>F)"] == pytest.approx(0.0262, abs=1e-4)

        assert tabla.loc["C(N)", "df"] == 1
        assert tabla.loc["C(N)", "F"] == pytest.approx(9.360, abs=1e-3)
        assert tabla.loc["C(N)", "PR(>F)"] == pytest.approx(0.0071, abs=1e-4)

        assert tabla.loc["Residual", "df"] == 17
        ms_error = tabla.loc["Residual", "sum_sq"] / tabla.loc["Residual", "df"]
        assert ms_error == pytest.approx(20.2228, abs=1e-4)


class TestGetErrorStats:
    """Grupo 2.3 [REFACTOR]: helper que expone MS_error y df_error de la tabla ANOVA."""

    def test_get_error_stats_npk(self, npk_df):
        tabla = compute_anova_table(npk_df, "rendimiento ~ C(block) + C(N)")

        ms_error, df_error = get_error_stats(tabla)

        assert ms_error == pytest.approx(20.2228, abs=1e-4)
        assert df_error == 17

    def test_get_error_stats_one_way(self):
        df = pd.DataFrame(
            {
                "tratamiento": ["A", "A", "A", "B", "B", "B", "C", "C", "C"],
                "rendimiento": [10.0, 12.0, 11.0, 20.0, 22.0, 21.0, 15.0, 17.0, 16.0],
            }
        )
        tabla = compute_anova_table(df, "rendimiento ~ C(tratamiento)")

        ms_error, df_error = get_error_stats(tabla)

        residual = tabla.loc["Residual"]
        assert ms_error == pytest.approx(residual["sum_sq"] / residual["df"])
        assert df_error == 6


class TestTukeyHsd:
    """Grupo 3: Tukey HSD correcto para diseños bloqueados (DD-07 / RN-EST-06)."""

    def test_tukey_hsd_respects_blocking_npk_regression(self, npk_df):
        """N=0 vs N=1 sobre el modelo bloqueado rendimiento ~ C(block) + C(N):
        diff≈5.6167, p≈0.0071 — coincide (hasta 4º decimal) con el p-valor del
        F-test de la ANOVA bloqueada para ese término de 2 niveles."""
        resultado = tukey_hsd(npk_df, "rendimiento ~ C(block) + C(N)", factor="N")

        fila = resultado[
            (resultado["group1"] == 0) & (resultado["group2"] == 1)
        ].iloc[0]

        assert fila["meandiff"] == pytest.approx(5.6167, abs=1e-3)
        assert fila["p_value"] == pytest.approx(0.0071, abs=1e-4)

    def test_tukey_hsd_differs_from_naive_pairwise_tukeyhsd_anti_regression(self, npk_df):
        """Anti-regresión del bug DD-07: el módulo debe devolver el p-valor
        CORRECTO (≈0.0071) y explícitamente NO el valor INCORRECTO (≈0.0221)
        que produce `pairwise_tukeyhsd(endog, groups)` al ignorar el bloqueo
        (calcula su propia varianza residual solo a partir de los grupos
        crudos de N, sin la reducción de varianza que aporta C(block)).

        Si en el futuro alguien "simplifica" tukey_hsd para volver a llamar a
        pairwise_tukeyhsd directo sobre los grupos crudos, este test debe
        fallar de inmediato.
        """
        from statsmodels.stats.multicomp import pairwise_tukeyhsd

        resultado_correcto = tukey_hsd(
            npk_df, "rendimiento ~ C(block) + C(N)", factor="N"
        )
        fila = resultado_correcto[
            (resultado_correcto["group1"] == 0) & (resultado_correcto["group2"] == 1)
        ].iloc[0]

        naive = pairwise_tukeyhsd(npk_df["rendimiento"], npk_df["N"])
        p_valor_naive_incorrecto = float(naive.pvalues[0])

        assert p_valor_naive_incorrecto == pytest.approx(0.0221, abs=1e-4)
        assert fila["p_value"] == pytest.approx(0.0071, abs=1e-4)
        assert fila["p_value"] != pytest.approx(p_valor_naive_incorrecto, abs=1e-3)

    def test_tukey_hsd_three_levels_uses_psturng_with_k_greater_than_two(self):
        """Segundo caso [TRIANGULATE] con inputs distintos: dataset balanceado
        de 3 bloques x 3 niveles de tratamiento, forzando el uso real de
        `psturng` con k=3 (no solo el caso trivial k=2 del fixture npk)."""
        df = pd.DataFrame(
            {
                "bloque": ["b1", "b2", "b3"] * 3,
                "tratamiento": ["A", "A", "A", "B", "B", "B", "C", "C", "C"],
                "rendimiento": [10.0, 12.0, 11.0, 20.0, 23.0, 21.0, 15.0, 18.0, 16.0],
            }
        )

        resultado = tukey_hsd(
            df, "rendimiento ~ C(bloque) + C(tratamiento)", factor="tratamiento"
        )

        # 3 niveles -> 3 pares de comparaciones (A-B, A-C, B-C)
        assert len(resultado) == 3
        assert set(resultado["p_value"].apply(lambda p: 0.0 <= p <= 1.0))
        fila_ab = resultado[
            (resultado["group1"] == "A") & (resultado["group2"] == "B")
        ].iloc[0]
        assert fila_ab["meandiff"] == pytest.approx(10.3333, abs=1e-3)

    def test_tukey_hsd_reuses_the_same_fitted_model_never_refits(self, npk_df, monkeypatch):
        """[REFACTOR 3.3] tukey_hsd debe reutilizar el MISMO objeto `modelo`
        ajustado que produjo la ANOVA (vía el parámetro `modelo=`), sin
        volver a llamar a `fit_model` (nunca reajusta ni usa grupos crudos
        para la varianza). Esto garantiza que HSD y ANOVA comparten el mismo
        MS_error por construcción, no por coincidencia numérica.
        """
        formula = "rendimiento ~ C(block) + C(N)"
        modelo_ya_ajustado = fit_model(npk_df, formula)

        llamadas_a_fit_model = []
        fit_model_original = fit_model

        def fit_model_espia(*args, **kwargs):
            llamadas_a_fit_model.append((args, kwargs))
            return fit_model_original(*args, **kwargs)

        monkeypatch.setattr(
            "pipeline.analysis_core.fit_model", fit_model_espia
        )

        resultado = tukey_hsd(npk_df, formula, factor="N", modelo=modelo_ya_ajustado)

        assert llamadas_a_fit_model == []
        fila = resultado[
            (resultado["group1"] == 0) & (resultado["group2"] == 1)
        ].iloc[0]
        assert fila["p_value"] == pytest.approx(0.0071, abs=1e-4)


class TestDiagnoseAssumptions:
    """Grupo 4: diagnóstico de supuestos (normalidad de residuos, homocedasticidad)."""

    def test_diagnostics_npk_regression_assumptions_hold(self, npk_df):
        """Sobre el modelo rendimiento ~ C(block) + C(N) del fixture npk:
        Shapiro-Wilk sobre residuos W≈0.9694, p≈0.6514 (normalidad no
        rechazada); Levene entre los grupos de N, p≈0.9421 (homocedasticidad
        no rechazada)."""
        resultado = diagnose_assumptions(
            npk_df, "rendimiento ~ C(block) + C(N)", factor="N"
        )

        assert resultado["shapiro"]["statistic"] == pytest.approx(0.9694, abs=1e-4)
        assert resultado["shapiro"]["p_value"] == pytest.approx(0.6514, abs=1e-4)
        assert resultado["levene"]["p_value"] == pytest.approx(0.9421, abs=1e-4)

    def test_diagnostics_detect_non_normal_residuals(self):
        """[TRIANGULATE] Caso que VIOLA la normalidad: residuos con outliers
        extremos inyectados (no explicados por bloque ni tratamiento) deben
        producir Shapiro p < 0.05, confirmando que el diagnóstico detecta la
        violación en vez de siempre reportar "todo OK"."""
        rng = np.random.default_rng(seed=1)
        bloques = ["b1", "b2", "b3"]
        tratamientos = ["A", "B"]
        repeticiones = 6
        filas = [
            {"bloque": b, "tratamiento": t}
            for b in bloques
            for t in tratamientos
            for _ in range(repeticiones)
        ]
        df = pd.DataFrame(filas)
        n = len(df)

        efecto_bloque = df["bloque"].map({"b1": 0, "b2": 5, "b3": 10}).to_numpy()
        efecto_tratamiento = df["tratamiento"].map({"A": 0, "B": 3}).to_numpy()
        ruido = rng.normal(0, 1.0, size=n)
        indices_outliers = [0, 7, 15, 22, 29]
        ruido[indices_outliers] += rng.choice(
            [-1, 1], size=len(indices_outliers)
        ) * rng.uniform(30, 50, size=len(indices_outliers))
        df["rendimiento"] = 20 + efecto_bloque + efecto_tratamiento + ruido

        resultado = diagnose_assumptions(
            df, "rendimiento ~ C(bloque) + C(tratamiento)", factor="tratamiento"
        )

        assert resultado["shapiro"]["p_value"] < 0.05


class TestReservedKeywordGuard:
    """Grupo 5: gotcha de `yield` (palabra reservada de Python, D4)."""

    def test_formula_with_yield_raises_clear_error(self):
        """Una fórmula que referencia una columna llamada `yield` (palabra
        reservada de Python) debe producir un error explícito pidiendo
        renombrar, en vez de un `SyntaxError`/`PatsyError` opaco de patsy."""
        df = pd.DataFrame(
            {
                "block": ["1", "1", "2", "2"],
                "N": [0, 1, 0, 1],
                "yield": [49.5, 62.8, 46.8, 57.0],
            }
        )

        with pytest.raises(ReservedKeywordFormulaError, match="yield"):
            fit_model(df, "yield ~ C(block) + C(N)")

    def test_formula_without_reserved_keywords_does_not_raise(self, npk_df):
        """[TRIANGULATE] Caso feliz: una fórmula sin nombres reservados
        (`rendimiento`, no `yield`) NO dispara la advertencia y ajusta el
        modelo con normalidad."""
        modelo = fit_model(npk_df, "rendimiento ~ C(block) + C(N)")

        assert modelo is not None
        assert hasattr(modelo, "resid")


class TestTukeyHsdManyLevels:
    """Grupo 7: Tukey HSD con ~10 niveles — control de multiplicidad (FWER, D6).

    Los factores reales de `npk` tienen 2 niveles cada uno; el caso k=3 del
    grupo 3 tampoco ejercita a fondo el ajuste de la tasa de error por
    familia. Estas pruebas usan un dataset SINTÉTICO de 10 niveles para
    forzar C(10,2)=45 comparaciones y validar `psturng` con un `k` real
    y grande, aislado (sin bloqueo) del bug de bloqueo ya cubierto en el
    grupo 3.
    """

    def test_tukey_hsd_ten_levels_returns_45_pairwise_comparisons(
        self, synthetic_10_level_df
    ):
        """[RED->GREEN] one-way rendimiento ~ C(tratamiento) con 10 niveles
        debe devolver exactamente C(10,2) = 45 comparaciones por pares."""
        resultado = tukey_hsd(
            synthetic_10_level_df,
            "rendimiento ~ C(tratamiento)",
            factor="tratamiento",
        )

        assert len(resultado) == 45
        pares_unicos = {
            tuple(sorted((fila["group1"], fila["group2"])))
            for _, fila in resultado.iterrows()
        }
        assert len(pares_unicos) == 45

    def test_tukey_hsd_pvalues_are_more_conservative_than_unadjusted_ttests(
        self, synthetic_10_level_df
    ):
        """[TRIANGULATE] Los p-valores de `tukey_hsd` (ajustados por FWER vía
        `psturng` con k=10 real) deben ser sistemáticamente MAYORES (más
        conservadores) que 45 t-tests independientes SIN ajustar sobre los
        mismos pares crudos. Se permite una tolerancia mínima (1e-2) porque
        `psturng` es una aproximación de la distribución del rango
        studentizado y puede haber algún par al borde donde la aproximación
        cruce por muy poco (D6, Risks)."""
        resultado = tukey_hsd(
            synthetic_10_level_df,
            "rendimiento ~ C(tratamiento)",
            factor="tratamiento",
        )

        p_valores_modulo = []
        p_valores_ttest_naive = []
        for _, fila in resultado.iterrows():
            grupo_i = synthetic_10_level_df.loc[
                synthetic_10_level_df["tratamiento"] == fila["group1"], "rendimiento"
            ].to_numpy()
            grupo_j = synthetic_10_level_df.loc[
                synthetic_10_level_df["tratamiento"] == fila["group2"], "rendimiento"
            ].to_numpy()
            _, p_ttest = scipy_stats.ttest_ind(grupo_i, grupo_j)

            assert fila["p_value"] >= p_ttest - 1e-2

            p_valores_modulo.append(fila["p_value"])
            p_valores_ttest_naive.append(p_ttest)

        # En promedio, el ajuste por multiplicidad debe ser claramente más
        # conservador (no un empate casual).
        assert np.mean(p_valores_modulo) > np.mean(p_valores_ttest_naive)

    def test_tukey_hsd_matches_pairwise_tukeyhsd_without_blocking(
        self, synthetic_10_level_df
    ):
        """[TRIANGULATE - referencia independiente] Sobre el MISMO dataset
        sintético, en un modelo one-way SIN factor de bloque, el bug DD-07
        (que solo afecta al `MS_error` cuando hay bloqueo) no aplica: por
        lo tanto `tukey_hsd` debe coincidir de cerca con
        `pairwise_tukeyhsd` de statsmodels para al menos un par específico.
        Esto aísla y valida la matemática de multiplicidad k>2 (D6)."""
        from statsmodels.stats.multicomp import pairwise_tukeyhsd

        resultado = tukey_hsd(
            synthetic_10_level_df,
            "rendimiento ~ C(tratamiento)",
            factor="tratamiento",
        )
        fila = resultado[
            (resultado["group1"] == "T0") & (resultado["group2"] == "T1")
        ].iloc[0]

        naive = pairwise_tukeyhsd(
            synthetic_10_level_df["rendimiento"],
            synthetic_10_level_df["tratamiento"],
        )
        fila_naive = next(
            row
            for row in naive._results_table.data[1:]
            if row[0] == "T0" and row[1] == "T1"
        )
        p_valor_naive = float(fila_naive[3])
        meandiff_naive = float(fila_naive[2])

        assert fila["p_value"] == pytest.approx(p_valor_naive, abs=5e-3)
        assert fila["meandiff"] == pytest.approx(meandiff_naive, abs=1e-3)

    def test_tukey_hsd_blocked_npk_regression_still_intact(self, npk_df):
        """[REFACTOR 7.4] La ruta bloqueada del grupo 3 (fixture npk, k=2)
        sigue intacta: N=0 vs N=1 -> diff≈5.6167, p≈0.0071. Sin duplicación
        de lógica: mismo `tukey_hsd` genérico, distinto dataset/fórmula."""
        resultado = tukey_hsd(npk_df, "rendimiento ~ C(block) + C(N)", factor="N")

        fila = resultado[
            (resultado["group1"] == 0) & (resultado["group2"] == 1)
        ].iloc[0]

        assert fila["meandiff"] == pytest.approx(5.6167, abs=1e-3)
        assert fila["p_value"] == pytest.approx(0.0071, abs=1e-4)


class TestFactorialAnovaWithInteractions:
    """Grupo 8: modelo factorial completo con interacciones sobre `npk` (D7).

    `rendimiento ~ C(block) + C(N)*C(P)*C(K)` reproduce el ejemplo canónico
    de R `aov(yield ~ block + N*P*K, npk)`. `npk` es un diseño de MEDIA
    FRACCIÓN: la interacción triple `N:P:K` está confundida (aliased) con
    los bloques (ver R `?npk`). Comportamiento EMPÍRICO observado (no
    asumido): a diferencia de R, `statsmodels`/`patsy` NO detecta ni
    descarta automáticamente la columna redundante del diseño — el ajuste
    OLS usa pseudo-inversa sobre una matriz de diseño rango-deficiente
    (rank=12 con 13 columnas) y `anova_lm` (Tipo I) igual reporta una fila
    `C(N):C(P):C(K)` con df=1 y una `sum_sq` NO nula, pero esa suma de
    cuadrados es espuria: no corresponde a una dirección genuinamente
    independiente del espacio de columnas, y su inclusión ROMPE la
    identidad SS total = suma de efectos + residual en exactamente su
    propio valor. Ver test `test_triple_interaction_is_aliased_with_blocks_and_breaks_ss_identity`.
    """

    FORMULA_FACTORIAL = "rendimiento ~ C(block) + C(N)*C(P)*C(K)"

    def test_anova_table_includes_interaction_rows(self, npk_df):
        """[RED->GREEN] La tabla ANOVA del modelo factorial completo debe
        incluir, además de los efectos principales, las filas de
        interacción de a pares (N:P, N:K, P:K) y la interacción triple
        N:P:K tal como las nombra patsy/statsmodels (empíricamente NO se
        omite, ver docstring de la clase)."""
        tabla = compute_anova_table(npk_df, self.FORMULA_FACTORIAL)

        for efecto_principal in ("C(block)", "C(N)", "C(P)", "C(K)"):
            assert efecto_principal in tabla.index

        for interaccion in ("C(N):C(P)", "C(N):C(K)", "C(P):C(K)"):
            assert interaccion in tabla.index

        assert "C(N):C(P):C(K)" in tabla.index
        assert "Residual" in tabla.index

    def test_ss_and_df_consistent_excluding_the_aliased_triple_interaction(
        self, npk_df
    ):
        """[TRIANGULATE] Consistencia interna de SS/df: EXCLUYENDO la fila
        aliasada `C(N):C(P):C(K)` (ver clase docstring y el test siguiente
        que fija por qué se excluye), la suma de `sum_sq` de todos los
        efectos restantes + la `sum_sq` residual SÍ iguala la SS total
        corregida del diseño (hasta el 4º decimal), y sus `df` suman
        exactamente `n - 1` (23), el total de grados de libertad del
        diseño."""
        tabla = compute_anova_table(npk_df, self.FORMULA_FACTORIAL)
        tabla_sin_triple = tabla.drop(index="C(N):C(P):C(K)")

        ss_total = (
            (npk_df["rendimiento"] - npk_df["rendimiento"].mean()) ** 2
        ).sum()

        assert tabla_sin_triple["sum_sq"].sum() == pytest.approx(ss_total, abs=1e-4)
        assert tabla_sin_triple["df"].sum() == len(npk_df) - 1

    def test_triple_interaction_is_aliased_with_blocks_and_breaks_ss_identity(
        self, npk_df
    ):
        """[TRIANGULATE - caveat de confusión / REFACTOR 8.3] Comportamiento
        observado EMPÍRICAMENTE (no asumido) de la media fracción: al
        incluir `C(N):C(P):C(K)` junto con `C(block)`, la matriz de diseño
        queda rango-deficiente (rank=12 sobre 13 columnas: la interacción
        triple es combinación lineal de los bloques). `statsmodels` NO
        aliasa/omite el término (a diferencia de R `aov`, que sí lo
        detecta y le asigna 0 df): en cambio, `anova_lm` reporta para
        `C(N):C(P):C(K)` un df=1 y una `sum_sq` NO nula pero ESPURIA. Se
        fija (pinnea) ese comportamiento exacto: incluir esa fila rompe la
        identidad SS total = suma(efectos) + residual, y la magnitud de la
        ruptura es EXACTAMENTE la `sum_sq` reportada para la interacción
        triple -- prueba directa de que esa suma de cuadrados no es una
        contribución genuina e independiente, sino un artefacto de la
        confusión con los bloques. La ruta ANOVA de dos vías existente
        (grupo 2, npk) no se toca."""
        tabla = compute_anova_table(npk_df, self.FORMULA_FACTORIAL)

        ss_total = (
            (npk_df["rendimiento"] - npk_df["rendimiento"].mean()) ** 2
        ).sum()
        suma_incluyendo_triple = tabla["sum_sq"].sum()
        sum_sq_triple = tabla.loc["C(N):C(P):C(K)", "sum_sq"]

        # La identidad NO se cumple si se incluye la fila aliasada.
        assert suma_incluyendo_triple != pytest.approx(ss_total, abs=1e-4)
        # La brecha exacta es la sum_sq espuria de la interacción triple.
        assert (suma_incluyendo_triple - ss_total) == pytest.approx(
            sum_sq_triple, abs=1e-6
        )
        # df total reportado por la tabla (incluyendo la triple) excede en 1
        # el df real del diseño (n-1=23), por la misma razón.
        assert tabla["df"].sum() == len(npk_df)  # 24, no 23

        # La ruta bloqueada de dos vías (grupo 2) sigue intacta.
        tabla_dos_vias = compute_anova_table(npk_df, "rendimiento ~ C(block) + C(N)")
        assert tabla_dos_vias.loc["C(N)", "PR(>F)"] == pytest.approx(0.0071, abs=1e-4)


class TestKruskalWallis:
    """Grupo 9: Kruskal-Wallis como alternativa no paramétrica (D8, RN-EST-01).

    Función pura NUEVA `kruskal_wallis(df, formula, factor, alpha=0.05)`:
    wrapper fino sobre `scipy.stats.kruskal`, sin ajustar `ols` (rank-based,
    sin modelo lineal que compartir con ANOVA/HSD/diagnósticos).
    """

    def _dataset_no_normal(self, seed: int, desplazamiento: float = 3.0):
        """Dataset con residuos marcadamente no normales (outliers extremos),
        espejo del fixture de `test_diagnostics_detect_non_normal_residuals`."""
        rng = np.random.default_rng(seed=seed)
        bloques = ["b1", "b2", "b3"]
        tratamientos = ["A", "B"]
        repeticiones = 6
        filas = [
            {"bloque": b, "tratamiento": t}
            for b in bloques
            for t in tratamientos
            for _ in range(repeticiones)
        ]
        df = pd.DataFrame(filas)
        n = len(df)

        efecto_bloque = df["bloque"].map({"b1": 0, "b2": 5, "b3": 10}).to_numpy()
        efecto_tratamiento = (
            df["tratamiento"].map({"A": 0, "B": desplazamiento}).to_numpy()
        )
        ruido = rng.normal(0, 1.0, size=n)
        indices_outliers = [0, 7, 15, 22, 29]
        ruido[indices_outliers] += rng.choice(
            [-1, 1], size=len(indices_outliers)
        ) * rng.uniform(30, 50, size=len(indices_outliers))
        df["rendimiento"] = 20 + efecto_bloque + efecto_tratamiento + ruido
        return df

    def test_kruskal_wallis_on_non_normal_data_returns_sane_reproducible_result(self):
        """[RED->GREEN] Sobre un dataset con residuos marcadamente no
        normales (outliers extremos), `kruskal_wallis` devuelve un dict con
        `statistic`, `p_value` y `reject = p_value < alpha`, con valores
        sanos (H >= 0, 0 <= p_value <= 1) y reproducibles bajo semilla
        fija."""
        df = self._dataset_no_normal(seed=1)

        resultado = kruskal_wallis(
            df, "rendimiento ~ C(bloque) + C(tratamiento)", factor="tratamiento"
        )

        assert set(resultado.keys()) == {"statistic", "p_value", "reject"}
        assert resultado["statistic"] >= 0.0
        assert 0.0 <= resultado["p_value"] <= 1.0
        assert resultado["reject"] == (resultado["p_value"] < 0.05)

        # Reproducibilidad: misma semilla, mismo resultado exacto.
        df_repetido = self._dataset_no_normal(seed=1)
        resultado_repetido = kruskal_wallis(
            df_repetido,
            "rendimiento ~ C(bloque) + C(tratamiento)",
            factor="tratamiento",
        )
        assert resultado["statistic"] == resultado_repetido["statistic"]
        assert resultado["p_value"] == resultado_repetido["p_value"]

    def test_kruskal_wallis_matches_scipy_kruskal_directly(self):
        """[TRIANGULATE - equivalencia con scipy] La salida de
        `kruskal_wallis` debe coincidir EXACTAMENTE (mismo H, mismo
        p-valor) con invocar `scipy.stats.kruskal` directamente sobre los
        mismos datos agrupados por `factor`. Se prueba sobre DOS datasets
        con inputs distintos (semillas y desplazamiento de tratamiento
        distintos) para confirmar que no es una coincidencia numérica de
        un solo caso."""
        for seed, desplazamiento, factor in (
            (1, 3.0, "tratamiento"),
            (99, 8.0, "bloque"),
        ):
            df = self._dataset_no_normal(seed=seed, desplazamiento=desplazamiento)
            variable_respuesta = "rendimiento"

            resultado = kruskal_wallis(
                df,
                f"{variable_respuesta} ~ C(bloque) + C(tratamiento)",
                factor=factor,
            )

            grupos_crudos = [
                valores[variable_respuesta].to_numpy()
                for _, valores in df.groupby(factor)
            ]
            statistic_esperado, p_esperado = scipy_stats.kruskal(*grupos_crudos)

            assert resultado["statistic"] == float(statistic_esperado)
            assert resultado["p_value"] == float(p_esperado)

    def test_kruskal_wallis_does_not_fit_ols_and_leaves_other_paths_intact(self):
        """[REFACTOR 9.3] `kruskal_wallis` es rank-based: NO ajusta un
        modelo lineal (`ols`), a diferencia de `compute_anova_table`/
        `tukey_hsd`/`diagnose_assumptions`. Se confirma espiando `fit_model`
        (nunca debe ser llamado) y que la ruta ANOVA/Tukey/diagnósticos
        existente queda intacta (fixture npk sigue dando los mismos
        valores pinneados)."""
        df = self._dataset_no_normal(seed=1)

        resultado = kruskal_wallis(
            df, "rendimiento ~ C(bloque) + C(tratamiento)", factor="tratamiento"
        )
        assert "statistic" in resultado

        import pipeline.analysis_core as modulo_analysis_core
        import inspect

        codigo_fuente = inspect.getsource(modulo_analysis_core.kruskal_wallis)
        assert "ols(" not in codigo_fuente
        assert "fit_model(" not in codigo_fuente

    def test_kruskal_wallis_reserved_keyword_guard(self):
        """`kruskal_wallis` reutiliza el guard de `yield` heredado del
        módulo (D4): una fórmula que referencia `yield` debe fallar con
        `ReservedKeywordFormulaError`, no con un error opaco de patsy."""
        df = pd.DataFrame(
            {
                "block": ["1", "1", "2", "2"],
                "N": [0, 1, 0, 1],
                "yield": [49.5, 62.8, 46.8, 57.0],
            }
        )

        with pytest.raises(ReservedKeywordFormulaError, match="yield"):
            kruskal_wallis(df, "yield ~ C(block) + C(N)", factor="N")


class TestSanityChecks:
    """Grupo 10: capa de sanity-checks / alertas NO bloqueante (D9).

    Motivada por el fallo silencioso REAL detectado durante el grupo 8: sobre
    `npk` (diseño de media fracción), `statsmodels`/`patsy` ajusta
    SILENCIOSAMENTE una matriz de diseño rango-deficiente vía pseudo-inversa
    (rank=12 sobre 13 columnas: `C(N):C(P):C(K)` confundida con los bloques)
    y `anova_lm` reporta una `sum_sq` espuria sin warning ni error (ver
    `TestFactorialAnovaWithInteractions`). `sanity_checks` corre tres
    chequeos deterministas y devuelve advertencias estructuradas
    (`list[dict]`), NUNCA levanta excepción ni frena la corrida (D9).
    """

    FORMULA_FACTORIAL_RANGO_DEFICIENTE = "rendimiento ~ C(block) + C(N)*C(P)*C(K)"
    FORMULA_DOS_VIAS_RANGO_COMPLETO = "rendimiento ~ C(block) + C(N)"

    def test_sanity_checks_detects_rank_deficiency_npk_regression(self, npk_df):
        """[RED->GREEN 10.1] Caso de aceptación / regresión EXPLÍCITO: sobre
        npk con la fórmula factorial completa (D7, grupo 8), la matriz de
        diseño queda rango-deficiente (rank=12 sobre 13 columnas:
        C(N):C(P):C(K) confundida con los bloques). sanity_checks DEBE
        devolver una advertencia rank_deficiency con ese rank/n_columns
        exactos -- es el fallo silencioso real que motivó este grupo (D9)."""
        resultado = sanity_checks(npk_df, self.FORMULA_FACTORIAL_RANGO_DEFICIENTE)

        deficiencias = [w for w in resultado if w["check"] == "rank_deficiency"]
        assert len(deficiencias) == 1
        advertencia = deficiencias[0]
        assert advertencia["details"]["rank"] == 12
        assert advertencia["details"]["n_columns"] == 13
        assert advertencia["details"]["deficiency"] == 1
        assert "message" in advertencia and isinstance(advertencia["message"], str)

    def test_sanity_checks_full_rank_design_does_not_trigger_rank_alert(self, npk_df):
        """[TRIANGULATE 10.2] Segundo input distinto: el modelo de dos vías
        rendimiento ~ C(block) + C(N) (rango completo) NO debe disparar
        ninguna advertencia rank_deficiency -- confirma que la detección no
        es un falso positivo constante."""
        resultado = sanity_checks(npk_df, self.FORMULA_DOS_VIAS_RANGO_COMPLETO)

        deficiencias = [w for w in resultado if w["check"] == "rank_deficiency"]
        assert deficiencias == []

    def test_sanity_checks_surfaces_assumption_violation_reusing_diagnose_assumptions(
        self,
    ):
        """[RED->GREEN 10.3] Sobre un dataset con residuos marcadamente no
        normales (espejo de test_diagnostics_detect_non_normal_residuals),
        con factor dado, sanity_checks debe surface-ar una advertencia
        assumption_violation (normalidad) reutilizando diagnose_assumptions
        -- no reimplementa Shapiro/Levene."""
        rng = np.random.default_rng(seed=1)
        bloques = ["b1", "b2", "b3"]
        tratamientos = ["A", "B"]
        repeticiones = 6
        filas = [
            {"bloque": b, "tratamiento": t}
            for b in bloques
            for t in tratamientos
            for _ in range(repeticiones)
        ]
        df = pd.DataFrame(filas)
        n = len(df)
        efecto_bloque = df["bloque"].map({"b1": 0, "b2": 5, "b3": 10}).to_numpy()
        efecto_tratamiento = df["tratamiento"].map({"A": 0, "B": 3}).to_numpy()
        ruido = rng.normal(0, 1.0, size=n)
        indices_outliers = [0, 7, 15, 22, 29]
        ruido[indices_outliers] += rng.choice(
            [-1, 1], size=len(indices_outliers)
        ) * rng.uniform(30, 50, size=len(indices_outliers))
        df["rendimiento"] = 20 + efecto_bloque + efecto_tratamiento + ruido

        resultado = sanity_checks(
            df, "rendimiento ~ C(bloque) + C(tratamiento)", factor="tratamiento"
        )

        violaciones = [w for w in resultado if w["check"] == "assumption_violation"]
        assert len(violaciones) >= 1
        assert any(w["details"]["test"] == "shapiro" for w in violaciones)
        for w in violaciones:
            assert w["details"]["p_value"] < w["details"]["alpha"]

    def test_sanity_checks_npk_assumptions_hold_no_violation_warning(self, npk_df):
        """[TRIANGULATE 10.3] Segundo caso: sobre npk (supuestos que se
        cumplen, ver grupo 4) NO se agrega ninguna advertencia
        assumption_violation."""
        resultado = sanity_checks(
            npk_df, self.FORMULA_DOS_VIAS_RANGO_COMPLETO, factor="N"
        )

        violaciones = [w for w in resultado if w["check"] == "assumption_violation"]
        assert violaciones == []

    def test_sanity_checks_warns_insufficient_group_size(self):
        """[RED->GREEN 10.4] Un DataFrame con un nivel de 1 observación
        (default min_group_size=2) debe disparar insufficient_group_size
        nombrando ese nivel."""
        df = pd.DataFrame(
            {
                "tratamiento": ["A", "A", "A", "B", "B", "C"],
                "rendimiento": [10.0, 12.0, 11.0, 20.0, 22.0, 15.0],
            }
        )

        resultado = sanity_checks(
            df, "rendimiento ~ C(tratamiento)", factor="tratamiento"
        )

        insuficientes = [
            w for w in resultado if w["check"] == "insufficient_group_size"
        ]
        assert len(insuficientes) == 1
        advertencia = insuficientes[0]
        assert advertencia["details"]["factor"] == "tratamiento"
        assert advertencia["details"]["level"] == "C"
        assert advertencia["details"]["n"] == 1
        assert advertencia["details"]["min_group_size"] == 2

    def test_sanity_checks_balanced_design_no_group_size_warning(self, npk_df):
        """[TRIANGULATE 10.4] Segundo caso: diseño balanceado con >=2 obs
        por nivel (npk, factor N, 12 obs por nivel) NO agrega ninguna
        advertencia insufficient_group_size."""
        resultado = sanity_checks(
            npk_df, self.FORMULA_DOS_VIAS_RANGO_COMPLETO, factor="N"
        )

        insuficientes = [
            w for w in resultado if w["check"] == "insufficient_group_size"
        ]
        assert insuficientes == []

    def test_sanity_checks_returns_empty_list_when_full_rank_assumptions_hold_and_no_factor(
        self, npk_df
    ):
        """[TRIANGULATE 10.5] Segundo input distinto respecto de 10.1-10.4:
        modelo de rango completo, sin factor -> se omiten supuestos y
        tamaño de grupo, y el chequeo de rango no encuentra nada -> lista
        vacía."""
        resultado = sanity_checks(npk_df, self.FORMULA_DOS_VIAS_RANGO_COMPLETO)

        assert resultado == []

    def test_sanity_checks_without_factor_only_runs_rank_check(self, npk_df):
        """[TRIANGULATE 10.5] Con factor=None se omiten los chequeos de
        supuestos y tamaño de grupo, y se ejecuta SOLO el chequeo de rango:
        sobre la fórmula factorial rango-deficiente sin factor, la única
        advertencia posible es rank_deficiency."""
        resultado = sanity_checks(npk_df, self.FORMULA_FACTORIAL_RANGO_DEFICIENTE)

        assert all(w["check"] == "rank_deficiency" for w in resultado)
        assert len(resultado) == 1

    def test_sanity_checks_never_raises_even_if_internal_check_fails(
        self, npk_df, monkeypatch
    ):
        """[TRIANGULATE 10.5] Garantía NO bloqueante: si un chequeo interno
        falla (ej. matrix_rank sobre un exog degenerado), sanity_checks
        NUNCA propaga la excepción -- la atrapa y retorna igual una
        list[dict] (el chequeo roto se omite en vez de tumbar la corrida)."""

        def matrix_rank_que_explota(*args, **kwargs):
            raise RuntimeError("fallo simulado en matrix_rank")

        monkeypatch.setattr(np.linalg, "matrix_rank", matrix_rank_que_explota)

        resultado = sanity_checks(npk_df, self.FORMULA_DOS_VIAS_RANGO_COMPLETO)

        assert isinstance(resultado, list)
        assert all(isinstance(w, dict) for w in resultado)


class TestModulePurity:
    """Grupo 6: pureza del módulo — sin persistencia, ingesta ni orquestación."""

    FORBIDDEN_IMPORT_PREFIXES = (
        "sqlite3",
        "psycopg2",
        "sqlalchemy",
        "requests",
        "httpx",
        "urllib",
        "n8n",
        "great_expectations",
    )

    def test_module_does_not_import_persistence_ingestion_or_orchestration(self):
        """El módulo NO SHALL importar código de acceso a base de datos,
        ingesta, bitácora de auditoría, generación de archivos de salida ni
        n8n (esas responsabilidades pertenecen a C-07)."""
        import ast
        import inspect

        import pipeline.analysis_core as modulo

        codigo_fuente = inspect.getsource(modulo)
        arbol = ast.parse(codigo_fuente)

        nombres_importados = []
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                nombres_importados.extend(alias.name for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                nombres_importados.append(nodo.module)

        for nombre in nombres_importados:
            assert not nombre.startswith(self.FORBIDDEN_IMPORT_PREFIXES), (
                f"pipeline.analysis_core importa '{nombre}', lo cual viola el "
                "alcance de módulo puro (sin persistencia/ingesta/n8n)."
            )

    def test_module_runs_end_to_end_with_only_pandas_statsmodels_scipy(self, npk_df):
        """El módulo se ejecuta sin infraestructura: produce tabla ANOVA,
        Tukey HSD y diagnósticos operando únicamente sobre el DataFrame
        recibido en memoria (sin base de datos, sin n8n, sin capa de
        persistencia)."""
        formula = "rendimiento ~ C(block) + C(N)"

        tabla = compute_anova_table(npk_df, formula)
        hsd = tukey_hsd(npk_df, formula, factor="N")
        diagnosticos = diagnose_assumptions(npk_df, formula, factor="N")

        assert not tabla.empty
        assert not hsd.empty
        assert "shapiro" in diagnosticos and "levene" in diagnosticos


class TestApplyTransformation:
    """Grupo 11: transformaciones de la variable de respuesta (log/sqrt/inverse, D10).

    `apply_transformation` es la mecánica ESTRICTA: devuelve un DataFrame
    NUEVO con una columna transformada agregada, NUNCA muta el original, y
    levanta `InvalidTransformationError` ante dominio inválido (restricción
    numérica real, no advisory).
    """

    def test_apply_log_transformation_adds_column_and_does_not_mutate_original(self):
        """[RED->GREEN 11.1] Sobre datos estrictamente positivos, `log`
        agrega una columna `rendimiento_log` = numpy.log(y), y el DataFrame
        original queda intacto (sin la columna nueva, misma identidad de
        columnas)."""
        df = pd.DataFrame({"rendimiento": [1.0, 2.0, 10.0, 100.0]})
        columnas_originales = list(df.columns)

        resultado = apply_transformation(df, "rendimiento", "log")

        assert "rendimiento_log" in resultado.columns
        np.testing.assert_allclose(
            resultado["rendimiento_log"].to_numpy(),
            np.log(df["rendimiento"].to_numpy()),
        )
        # El DataFrame original no fue mutado.
        assert list(df.columns) == columnas_originales
        assert "rendimiento_log" not in df.columns

    def test_apply_log_transformation_raises_on_non_positive_values(self):
        """[RED->GREEN 11.1] Guard de dominio: `log` sobre datos con algún
        `y <= 0` levanta `InvalidTransformationError` en vez de producir
        `-inf`/`NaN` silencioso."""
        df = pd.DataFrame({"rendimiento": [1.0, 0.0, 10.0]})

        with pytest.raises(InvalidTransformationError):
            apply_transformation(df, "rendimiento", "log")

        df_negativo = pd.DataFrame({"rendimiento": [1.0, -5.0, 10.0]})
        with pytest.raises(InvalidTransformationError):
            apply_transformation(df_negativo, "rendimiento", "log")

    def test_apply_sqrt_transformation_valid_at_zero_raises_on_negative(self):
        """[TRIANGULATE 11.2] `sqrt` = numpy.sqrt(y); y=0 es válido (da 0),
        sólo y<0 levanta InvalidTransformationError. Segundo caso con
        inputs distintos respecto de log."""
        df = pd.DataFrame({"rendimiento": [0.0, 4.0, 9.0]})
        columnas_originales = list(df.columns)

        resultado = apply_transformation(df, "rendimiento", "sqrt")

        assert "rendimiento_sqrt" in resultado.columns
        np.testing.assert_allclose(
            resultado["rendimiento_sqrt"].to_numpy(),
            np.sqrt(df["rendimiento"].to_numpy()),
        )
        assert list(df.columns) == columnas_originales
        assert "rendimiento_sqrt" not in df.columns

        df_negativo = pd.DataFrame({"rendimiento": [1.0, -0.5, 9.0]})
        with pytest.raises(InvalidTransformationError):
            apply_transformation(df_negativo, "rendimiento", "sqrt")

    def test_apply_inverse_transformation_valid_on_negatives_raises_on_zero(self):
        """[TRIANGULATE 11.2] `inverse` = 1/y; un y negativo SÍ es válido
        (1/y está definida), sólo y==0 levanta InvalidTransformationError.
        Tercer caso con inputs distintos respecto de log/sqrt."""
        df = pd.DataFrame({"rendimiento": [-2.0, 1.0, 4.0]})
        columnas_originales = list(df.columns)

        resultado = apply_transformation(df, "rendimiento", "inverse")

        assert "rendimiento_inverse" in resultado.columns
        np.testing.assert_allclose(
            resultado["rendimiento_inverse"].to_numpy(),
            1.0 / df["rendimiento"].to_numpy(),
        )
        assert list(df.columns) == columnas_originales
        assert "rendimiento_inverse" not in df.columns

        df_con_cero = pd.DataFrame({"rendimiento": [1.0, 0.0, 4.0]})
        with pytest.raises(InvalidTransformationError):
            apply_transformation(df_con_cero, "rendimiento", "inverse")

    def test_apply_transformation_unknown_name_raises(self):
        """[TRIANGULATE 11.2] Un nombre de transformación desconocido
        levanta `InvalidTransformationError`."""
        df = pd.DataFrame({"rendimiento": [1.0, 2.0, 3.0]})

        with pytest.raises(InvalidTransformationError):
            apply_transformation(df, "rendimiento", "boxcox")

    def test_apply_transformation_custom_new_column_name(self):
        """`new_column` permite sobreescribir el nombre default de la
        columna generada."""
        df = pd.DataFrame({"rendimiento": [1.0, 2.0, 10.0]})

        resultado = apply_transformation(
            df, "rendimiento", "log", new_column="log_rendimiento"
        )

        assert "log_rendimiento" in resultado.columns
        assert "rendimiento_log" not in resultado.columns


class TestSuggestTransformation:
    """Grupo 11 (11.3-11.5): capa advisory `suggest_transformation` (D10).

    Verifica -con `diagnose_assumptions`- si transformar REALMENTE arregla
    los supuestos de ESTE dataset, en vez de transformar a ciegas.
    """

    FORMULA = "rendimiento ~ C(bloque) + C(tratamiento)"

    def _dataset_lognormal_control_positivo(self, seed: int = 42) -> pd.DataFrame:
        """Control positivo (D10): ruido multiplicativo lognormal sobre un
        diseño bloqueado, respuesta estrictamente positiva y asimétrica a
        derecha. Baseline no-normal (violación real de Shapiro); `log`
        arregla la normalidad (comportamiento robusto documentado en D10
        para varias semillas)."""
        rng = np.random.default_rng(seed=seed)
        bloques = ["b1", "b2", "b3"]
        tratamientos = ["A", "B"]
        repeticiones = 6
        filas = [
            {"bloque": b, "tratamiento": t}
            for b in bloques
            for t in tratamientos
            for _ in range(repeticiones)
        ]
        df = pd.DataFrame(filas)
        n = len(df)

        efecto_bloque = df["bloque"].map({"b1": 0.0, "b2": 0.2, "b3": 0.4}).to_numpy()
        efecto_tratamiento = (
            df["tratamiento"].map({"A": 0.0, "B": 0.3}).to_numpy()
        )
        ruido_multiplicativo = rng.normal(0, 0.4, size=n)
        base = 20.0
        df["rendimiento"] = base * np.exp(
            efecto_bloque + efecto_tratamiento + ruido_multiplicativo
        )
        return df

    def _dataset_outliers(self, seed: int = 1) -> pd.DataFrame:
        """Espejo EXACTO del fixture de
        `test_diagnostics_detect_non_normal_residuals`: no-normalidad
        causada por outliers puntuales, con valores NEGATIVOS en la
        respuesta (no remediable por transformaciones monótonas, D10)."""
        rng = np.random.default_rng(seed=seed)
        bloques = ["b1", "b2", "b3"]
        tratamientos = ["A", "B"]
        repeticiones = 6
        filas = [
            {"bloque": b, "tratamiento": t}
            for b in bloques
            for t in tratamientos
            for _ in range(repeticiones)
        ]
        df = pd.DataFrame(filas)
        n = len(df)

        efecto_bloque = df["bloque"].map({"b1": 0, "b2": 5, "b3": 10}).to_numpy()
        efecto_tratamiento = df["tratamiento"].map({"A": 0, "B": 3}).to_numpy()
        ruido = rng.normal(0, 1.0, size=n)
        indices_outliers = [0, 7, 15, 22, 29]
        ruido[indices_outliers] += rng.choice(
            [-1, 1], size=len(indices_outliers)
        ) * rng.uniform(30, 50, size=len(indices_outliers))
        df["rendimiento"] = 20 + efecto_bloque + efecto_tratamiento + ruido
        return df

    def test_suggest_transformation_recommends_log_when_it_fixes_assumptions(self):
        """[RED->GREEN 11.3] Caso control positivo EXPLÍCITO: sobre el
        dataset lognormal/multiplicativo (semilla=42, respuesta positiva y
        asimétrica a derecha), el baseline viola normalidad (Shapiro
        p<0.05); el candidato `log` queda `applicable=True`,
        `resolves_violations=True`, `shapiro_p >= alpha`, y
        `recommended == "log"`."""
        df = self._dataset_lognormal_control_positivo()

        assert (df["rendimiento"] > 0).all()  # dominio válido para log

        resultado = suggest_transformation(df, self.FORMULA, factor="tratamiento")

        assert resultado["baseline"]["shapiro_p"] < 0.05
        assert resultado["baseline"]["normal_ok"] is False

        candidato_log = next(
            c for c in resultado["candidates"] if c["transformation"] == "log"
        )
        assert candidato_log["applicable"] is True
        assert candidato_log["resolves_violations"] is True
        assert candidato_log["shapiro_p"] >= 0.05

        assert resultado["recommended"] == "log"

    def test_suggest_transformation_returns_none_when_nothing_fixes_outliers(self):
        """[TRIANGULATE 11.4 — hallazgo honesto] Sobre el fixture de
        outliers (semilla=1, espejo de
        `test_diagnostics_detect_non_normal_residuals`; respuesta con
        valores negativos): `log` y `sqrt` quedan `applicable=False`
        (dominio inválido, motivo capturado de `InvalidTransformationError`),
        `inverse` queda `applicable=True` pero `resolves_violations=False`,
        y `recommended is None` — pinnea que la no-normalidad por outliers
        puntuales NO es remediable por transformaciones monótonas."""
        df = self._dataset_outliers()
        assert (df["rendimiento"] < 0).any()  # confirma dominio inválido para log/sqrt

        resultado = suggest_transformation(df, self.FORMULA, factor="tratamiento")

        assert resultado["baseline"]["shapiro_p"] < 0.05

        candidato_log = next(
            c for c in resultado["candidates"] if c["transformation"] == "log"
        )
        candidato_sqrt = next(
            c for c in resultado["candidates"] if c["transformation"] == "sqrt"
        )
        candidato_inverse = next(
            c for c in resultado["candidates"] if c["transformation"] == "inverse"
        )

        assert candidato_log["applicable"] is False
        assert candidato_log["reason"] is not None
        assert candidato_sqrt["applicable"] is False
        assert candidato_sqrt["reason"] is not None

        assert candidato_inverse["applicable"] is True
        assert candidato_inverse["resolves_violations"] is False

        assert resultado["recommended"] is None

    def test_suggest_transformation_never_raises_for_non_applicable_candidates(self):
        """[TRIANGULATE 11.5a] Garantía advisory: aunque TODOS los
        candidatos por default incluyan uno no aplicable por su guard de
        dominio, `suggest_transformation` nunca levanta — retorna el dict
        igual, con ese candidato en `applicable=False`."""
        df = self._dataset_outliers()

        try:
            resultado = suggest_transformation(df, self.FORMULA, factor="tratamiento")
        except Exception as exc:  # pragma: no cover - falla el test si levanta
            pytest.fail(f"suggest_transformation no debe levantar, levantó: {exc!r}")

        assert isinstance(resultado, dict)
        assert {"baseline", "candidates", "recommended"} <= set(resultado.keys())

    def test_suggest_transformation_reserved_keyword_still_raises_upstream(self):
        """[TRIANGULATE 11.5b] No-issue de palabra reservada: los nombres de
        columna generados (`rendimiento_log`, etc.) no son keywords de
        Python, pero si la fórmula ORIGINAL referencia `yield`, el guard D4
        sigue disparando `ReservedKeywordFormulaError` aguas arriba (vía
        `diagnose_assumptions`/`fit_model`), ANTES de construir cualquier
        candidato transformado."""
        df = pd.DataFrame(
            {
                "block": ["1", "1", "2", "2"],
                "N": [0, 1, 0, 1],
                "yield": [49.5, 62.8, 46.8, 57.0],
            }
        )

        with pytest.raises(ReservedKeywordFormulaError, match="yield"):
            suggest_transformation(df, "yield ~ C(block) + C(N)", factor="N")

    def test_suggest_transformation_does_not_mutate_original_dataframe(self):
        """[TRIANGULATE 11.5c] Ni `apply_transformation` (ya cubierto) ni
        `suggest_transformation` mutan el `df` original: tras invocar la
        función advisory, el `df` de entrada conserva exactamente sus
        columnas originales."""
        df = self._dataset_lognormal_control_positivo()
        columnas_originales = list(df.columns)

        suggest_transformation(df, self.FORMULA, factor="tratamiento")

        assert list(df.columns) == columnas_originales

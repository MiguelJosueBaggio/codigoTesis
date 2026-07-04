# Tesis — Automatización de Ensayos Agrícolas — Base de Conocimiento

Base de conocimiento generada a partir de `docs/Tesis_Automatizacion_ensayos_agricolas.md` (tesis de Magíster en Sistemas de Información, UTN FR Mendoza, 2026).

## Índice de Archivos

| Archivo | Contenido |
|---------|-----------|
| [01_vision_y_objetivos.md](01_vision_y_objetivos.md) | Propósito, objetivos por actor, alcance v1.0, fuera de alcance, métricas de éxito e hipótesis H1-H3 |
| [02_descripcion_general.md](02_descripcion_general.md) | Stack (n8n + Python + SQLite/PostgreSQL), arquitectura en 4 capas, integraciones |
| [03_actores_y_roles.md](03_actores_y_roles.md) | Actores + **roles operativos Ingeniero/Ayudante y RBAC mínimo (`telegram_user_id → rol`) resuelto por DD-09** |
| [04_modelo_de_datos.md](04_modelo_de_datos.md) | Entidades de dominio/sistema/configuración, ERD textual, diccionario de variables |
| [05_reglas_de_negocio.md](05_reglas_de_negocio.md) | Reglas RN-ING, RN-VAL, RN-TRA, RN-AUD, RN-EST, RN-IA, RN-OCR, **RN-SES**, RN-GLB |
| [06_funcionalidades.md](06_funcionalidades.md) | 6 épicas con historias de usuario (US-001 a US-006) |
| [07_flujos_principales.md](07_flujos_principales.md) | 4 flujos: pipeline completo, corrección de rechazados, análisis standalone, aprobación de IA |
| [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md) | Patrones aplicados, estructura de directorios (Anexo C), seguridad, variables de entorno |
| [09_decisiones_y_supuestos.md](09_decisiones_y_supuestos.md) | 12 decisiones documentadas (DD-01 a **DD-12** — DD-09 refina/supersede DD-05) + 4 supuestos inferidos (SU-01 a SU-04) |
| [10_preguntas_abiertas.md](10_preguntas_abiertas.md) | **El Capítulo 5 de la tesis está sin datos reales — bloqueante central del proyecto** + preguntas priorizadas |
| [11_analisis_estadistico_anova_tukey.md](11_analisis_estadistico_anova_tukey.md) | **Mecánica ANOVA+Tukey validada contra dataset de referencia (`npk`, Fisher/Rothamsted) + hallazgo crítico: `pairwise_tukeyhsd` da p-valores incorrectos en diseños bloqueados** |
| [12_captura_offline_ocr.md](12_captura_offline_ocr.md) | **Captura offline de datos de campo vía OCR zonal por plantilla (peine + OMR + fiduciales, local sin nube) — método de entrada alternativo OPCIONAL que converge a `pipeline/ingestion.py`, no un pipeline paralelo (dominio RN-OCR, DD-08, change C-11)** |
| [13_interaccion_telegram_y_sesiones.md](13_interaccion_telegram_y_sesiones.md) | **Capa de interacción cero-CLI 100% orientada a eventos: Telegram como único canal humano (nodo nativo n8n + Wait-for-Webhook), dos roles (Ingeniero/Ayudante) y un motor genérico de sesiones dirigido por datos. Refina/supersede DD-05 (DD-09), corrige RN-OCR-04, resuelve el RBAC. Dominio RN-SES, RN-EST-07, changes C-12/C-13** |
| [14_reuso_academico_y_geolocalizacion.md](14_reuso_academico_y_geolocalizacion.md) | **Trabajo futuro, no construido: reuso académico del dataset acumulado (meta-análisis, entrenamiento de IA) y correlación climática vía geolocalización de Ambiente. Geolocalización opcional ya agregada al modelo de datos (DD-12); el resto queda documentado como visión, sin change asignado** |

## Quick Start para Desarrolladores

1. Entender el dominio → [01](01_vision_y_objetivos.md), [03](03_actores_y_roles.md)
2. Entender los datos → [04](04_modelo_de_datos.md)
3. Entender las reglas → [05](05_reglas_de_negocio.md)
4. Entender la arquitectura → [02](02_descripcion_general.md), [08](08_arquitectura_propuesta.md)
5. Implementar → [07](07_flujos_principales.md), [06](06_funcionalidades.md)
6. **Antes de codificar** → [10](10_preguntas_abiertas.md) — hay 3 preguntas de prioridad Alta sin responder (caso de estudio real, elección de implementación de Tukey HSD, quién ejecuta la línea base manual). La pregunta "¿UI propia?" está **resuelta** (v2: cero-CLI / Telegram / eventos, DD-09)

## Resumen Ejecutivo

Pipeline de automatización (n8n + Python) para ingesta, validación, transformación, persistencia auditable y análisis estadístico reproducible (ANOVA y alternativas) de datos de ensayos agrícolas. La tesis que lo especifica está redactada casi por completo (Cap. 1-4, 6-7); el trabajo pendiente central es **construir el software y ejecutarlo sobre un caso de estudio real** para completar el Capítulo 5 (Resultados) con datos genuinos.

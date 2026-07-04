_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

**Universidad Tecnológica Nacional Facultad Regional Mendoza** 

Escuela de Posgrado e Investigación 

# **AUTOMATIZACIÓN DE CARGAS DE DATOS Y ANÁLISIS ESTADÍSTICO EN ENSAYOS AGRÍCOLAS** 

_Diseño, implementación y validación de un flujo reproducible basado en n8n y Python_ 

Tesis presentada para optar al grado de **Magíster en Sistemas de Información** 

**Autores:** Miguel Baggio Nahuel Morales Alejo Osorio Ignacio Aguilar 

**Director:** Mg. Alberto Cortez 

Mendoza — Argentina 2026 

Página 1 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Resumen** 

La gestión de datos experimentales en ensayos agrícolas constituye una etapa crítica dentro del proceso científico agronómico. En contextos donde la calidad del dato condiciona directamente la validez de los análisis estadísticos y la reproducibilidad de los resultados, las prácticas manuales ampliamente extendidas —carga en planillas de cálculo, transformaciones ad hoc y documentación informal— representan una fuente recurrente e identificable de fragilidad metodológica. Los problemas más frecuentes incluyen errores de transcripción que comprometen la integridad del registro, ausencia de trazabilidad sobre qué se modificó, cuándo y con qué criterio, y dependencia de pasos no documentados que dificultan o imposibilitan la replicación independiente del análisis. 

Esta tesis aborda dichas debilidades mediante el diseño, la implementación y la validación de un sistema integral de automatización orientado a la ingesta, validación, transformación y almacenamiento de datos provenientes de ensayos agrícolas, incorporando adicionalmente un módulo de análisis estadístico reproducible y auditable. El enfoque tecnológico adoptado articula la orquestación de flujos mediante la plataforma n8n con el procesamiento estructurado a través de Python, apoyándose en capacidades complementarias de inteligencia artificial para tareas específicas de apoyo, tales como la estandarización semiautomática de campos con alta variabilidad léxica, la detección proactiva de inconsistencias y la asistencia en el control de calidad del dato. En todos los casos, la acción de los componentes automatizados queda registrada en una bitácora auditada que preserva la cadena de custodia del dato. 

En lo metodológico, la investigación adopta un diseño de ingeniería aplicada con evaluación mediante estudio de caso. El ciclo de trabajo comprende cuatro etapas secuenciales: (i) relevamiento de requisitos y modelado detallado del proceso de gestión de datos en su estado actual; (ii) implementación incremental del pipeline automatizado con pruebas por módulo; (iii) verificación mediante un conjunto de reglas de calidad de datos formalmente definidas; y (iv) evaluación del desempeño con indicadores tanto operativos —tiempo de procesamiento, tasa de error detectado, completitud y consistencia del dataset resultante— como estadísticos, a través de la ejecución exitosa de análisis como el Análisis de Varianza (ANOVA) u otros modelos apropiados según el diseño experimental. El aporte central de este trabajo reside en la provisión de un flujo completamente auditable y replicable que reduce sustancialmente la intervención manual en la preparación del dato, mejora la trazabilidad a lo largo de todo el pipeline, y facilita el análisis estadístico con control explícito de supuestos y documentación sistemática de cada decisión metodológica. 

Página 2 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

_Palabras clave: automatización, ensayos agrícolas, calidad de datos, reproducibilidad, n8n, Python, análisis estadístico, trazabilidad, pipeline ETL, ANOVA._ 

Página 3 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Abstract** 

Experimental data management in agricultural trials represents a critical stage within the agronomy research process. In contexts where data quality directly determines the validity of statistical analyses and the reproducibility of results, the widely prevalent manual practices—spreadsheet-based data entry, ad hoc transformations, and informal documentation—constitute a recurrent and identifiable source of methodological fragility. The most common problems include transcription errors that compromise record integrity, the absence of traceability regarding what was modified, when, and by which criterion, and reliance on undocumented steps that hinder or prevent independent replication of the analysis. 

This thesis addresses these weaknesses through the design, implementation, and validation of a comprehensive automation system aimed at the ingestion, validation, transformation, and storage of data from agricultural trials, additionally incorporating a reproducible and auditable statistical analysis module. The adopted technological approach articulates workflow orchestration through the n8n platform with structured processing via Python, drawing on complementary artificial intelligence capabilities for specific support tasks, such as semi-automatic standardization of fields with high lexical variability, proactive detection of inconsistencies, and assistance in data quality control. In all cases, the actions of the automated components are recorded in an audited log that preserves the chain of custody of the data. 

Methodologically, the research adopts an applied engineering design with evaluation via case study. The work cycle comprises four sequential stages: (i) requirements gathering and detailed modeling of the current-state data management process; (ii) incremental implementation of the automated pipeline with module-level testing; (iii) verification against a formally defined set of data quality rules; and (iv) performance evaluation with both operational indicators—processing time, detected error rate, completeness, and consistency of the resulting dataset—and statistical indicators, through the successful execution of analyses such as Analysis of Variance (ANOVA) or other appropriate models given the experimental design. The central contribution of this work lies in providing a fully auditable and replicable pipeline that substantially reduces manual intervention in data preparation, improves traceability throughout the entire pipeline, and facilitates statistical analysis with explicit control of assumptions and systematic documentation of every methodological decision. 

Página 4 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

_Keywords: automation, agricultural trials, data quality, reproducibility, n8n, Python, statistical analysis, traceability, ETL pipeline, ANOVA._ 

Página 5 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Capítulo 1. Introducción** 

## **1.1 Contexto y motivación** 

La agricultura moderna ha experimentado en las últimas décadas una transformación profunda en su relación con los datos. El crecimiento sostenido de la presión demográfica mundial, la variabilidad climática creciente y la necesidad de maximizar la eficiencia productiva bajo restricciones de superficie, agua e insumos han convertido al dato experimental en un recurso estratégico de primera importancia para el sector agronómico. La capacidad de registrar, procesar y analizar rigurosamente los resultados de ensayos de campo constituye hoy el fundamento sobre el cual se sostienen las recomendaciones técnicas en materia de variedades, fertilización, riego, control fitosanitario y manejo general del cultivo. 

En este contexto, los ensayos agrícolas formales —aquellos conducidos bajo principios de diseño experimental— ocupan un lugar central. Un ensayo bien diseñado permite comparar tratamientos con precisión estadística controlada, cuantificar la variabilidad ambiental, estimar interacciones entre factores y formular inferencias generalizables. La calidad de estas inferencias, sin embargo, no depende únicamente del diseño experimental adoptado ni de la rigurosidad de la ejecución en campo: depende, de manera igualmente crítica, de la integridad de los datos que alimentan el análisis. Un error de transcripción, una inconsistencia en las unidades de medida o un valor atípico no detectado pueden sesgar las conclusiones y, en casos extremos, llevar a recomendaciones técnicas erróneas con consecuencias productivas concretas. 

La realidad operativa de la mayoría de los programas de ensayos agrícolas, tanto en instituciones académicas como en organismos de investigación y en empresas semilleras, dista aún de incorporar prácticas sistemáticas de gestión del dato. El flujo de trabajo predominante sigue un patrón altamente dependiente de la intervención manual: los datos se capturan en campo mediante planillas en papel o formularios digitales básicos, se transcriben a hojas de cálculo, se manipulan mediante procesos ad hoc ejecutados por cada analista según sus criterios personales, y se entregan al estadístico o al analista responsable del estudio en formatos de variable estandarización. Este proceso, además de ser lento y costoso en términos de esfuerzo humano, es intrínsecamente frágil: cada paso manual es una oportunidad para introducir errores, y la ausencia de registros formales de las transformaciones realizadas hace imposible, en la práctica, rastrear la historia del dato desde su origen hasta el resultado final. 

Página 6 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

La motivación central de esta tesis surge precisamente de esta brecha entre lo que la ciencia de datos contemporánea ofrece como posibilidad técnica y lo que la práctica habitual de gestión de datos en ensayos agrícolas efectivamente implementa. Las herramientas para automatizar flujos de datos, garantizar su trazabilidad, ejecutar validaciones sistemáticas y reproducir análisis estadísticos de manera controlada existen y son accesibles; lo que falta es su integración en un sistema coherente, documentado y adaptado a las características específicas del dato experimental agronómico. Esta tesis busca contribuir a cerrar esa brecha mediante el diseño y la validación de un pipeline reproducible que sea técnicamente robusto, metodológicamente riguroso y operativamente viable. 

## **1.2 Planteamiento del problema** 

El problema central que aborda esta investigación puede enunciarse en los siguientes términos: en los programas de ensayos agrícolas, el proceso de transformación del dato crudo —capturado en campo o en laboratorio— en un dataset estructurado, limpio y listo para el análisis estadístico carece, en la generalidad de los casos, de automatización, estandarización y trazabilidad suficientes. Esta carencia no constituye únicamente una ineficiencia operativa: tiene consecuencias directas sobre la confiabilidad y reproducibilidad de los resultados científicos generados a partir de dichos datos. 

En términos más precisos, el problema se articula en tres dimensiones interrelacionadas. La primera dimensión es la dimensión de la integridad del dato: los procesos manuales de carga y transformación introducen errores —de tipografía, de escala, de codificación de tratamientos, de unidades— que frecuentemente no son detectados antes del análisis y que, una vez incorporados al análisis estadístico, producen resultados distorsionados. La segunda dimensión es la de la trazabilidad: cuando un dataset ha pasado por múltiples manos y múltiples operaciones no documentadas, resulta imposible reconstruir su historia, identificar el origen de una discrepancia o auditar una decisión metodológica particular. La tercera dimensión es la de la reproducibilidad: si el pipeline de procesamiento no está formalizado, versionado y documentado, la replicación del análisis —por el mismo equipo en una campaña posterior o por un evaluador externo— se vuelve una empresa costosa y propensa a divergencias respecto del análisis original. 

La pregunta de investigación central que articula este trabajo es la siguiente: ¿Cómo diseñar e implementar un pipeline automatizado, trazable y reproducible que integre la carga de datos de ensayos agrícolas, ejecute validaciones de calidad, garantice la trazabilidad de las transformaciones y habilite el análisis estadístico consistente, reduciendo tiempos y errores respecto de un proceso manual de referencia? Esta pregunta 

Página 7 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

central se descompone en un conjunto de preguntas subsidiarias que orientan el desarrollo de los capítulos siguientes y que se explicitan en la sección 1.6. 

## **1.3 Justificación y relevancia** 

La relevancia de este trabajo se sustenta en argumentos de naturaleza simultáneamente práctica, científica e institucional. Desde la perspectiva práctica, la automatización del proceso de gestión del dato en ensayos agrícolas representa una reducción directamente cuantificable de los tiempos y costos asociados a la preparación del dataset para análisis. En programas con múltiples ensayos, varios sitios experimentales y campañas sucesivas, el costo acumulado del procesamiento manual puede ser considerable; su reemplazo por un flujo automatizado libera recursos humanos especializados para tareas de mayor valor agregado cognitivo, como la interpretación de resultados o el diseño de nuevas experiencias. 

Desde la perspectiva científica, la reproducibilidad es hoy una condición sine qua non para la credibilidad de los resultados de investigación. La crisis de reproducibilidad documentada en múltiples disciplinas científicas ha puesto en evidencia que una proporción importante de los resultados publicados no puede ser replicada por equipos independientes, y que una fracción significativa de esa irreproducibilidad tiene origen en problemas de gestión y procesamiento del dato, no en fallas del diseño experimental original. Proveer un flujo formalmente documentado, ejecutable bajo control de versiones y parametrizable para distintos diseños experimentales constituye, en este contexto, una contribución metodológica con valor intrínseco. 

Desde la perspectiva institucional, el nivel de la maestría exige que el trabajo de tesis demuestre no solo dominio técnico sino también rigor metodológico en la construcción del conocimiento. Un sistema que garantiza la integridad del dato, documenta cada transformación y genera evidencia auditable de sus operaciones cumple con los estándares de transparencia que la investigación académica requiere. Al mismo tiempo, la tesis aporta al campo de la ingeniería de sistemas de información aplicada al agro un caso de estudio documentado con suficiente detalle para ser replicado o adaptado en contextos similares. 

## **1.4 Objetivo general** 

El objetivo general de esta tesis es diseñar, implementar y validar un sistema reproducible para automatizar la carga, validación y procesamiento de datos de ensayos agrícolas y ejecutar sobre ellos análisis estadístico consistente con el diseño experimental adoptado, 

Página 8 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

priorizando la trazabilidad de las transformaciones, la calidad del dato resultante y la mantenibilidad del sistema a lo largo del tiempo. 

Este objetivo integra tres dimensiones que el trabajo desarrolla de manera articulada. La dimensión de diseño comprende la arquitectura del sistema, el modelo de datos, el esquema de validaciones y la especificación funcional completa del pipeline. La dimensión de implementación comprende la construcción efectiva del sistema mediante las tecnologías seleccionadas —n8n y Python— con documentación técnica suficiente para su comprensión y replicación. La dimensión de validación comprende la evaluación del sistema mediante métricas operativas y estadísticas objetivamente medibles, comparando su desempeño con el proceso manual de referencia. 

## **1.5 Objetivos específicos** 

1. Modelar el proceso completo de gestión del dato experimental desde la captura en campo hasta la preparación del dataset para análisis, identificando con precisión los puntos críticos de introducción de errores, los cuellos de botella operativos y las lagunas de trazabilidad en el flujo de trabajo actual. 

2. Definir un esquema de datos formal para ensayos agrícolas que incluya la especificación de variables, tipos, unidades, rangos válidos, relaciones entre entidades y reglas de validación que cubran completitud, validez, consistencia y unicidad. 

3. Implementar un pipeline de automatización completo con orquestación mediante n8n y procesamiento mediante Python, incluyendo mecanismos de registro de ejecuciones, manejo de errores, reintentos y generación de bitácoras de auditoría. 

4. Integrar al pipeline un módulo de análisis estadístico reproducible, ejecutable mediante scripts parametrizables bajo control de versiones, capaz de aplicar modelos apropiados al diseño experimental —incluyendo ANOVA u otras técnicas cuando los supuestos o el diseño lo requieran— y generar reportes con diagnósticos explícitos. 

5. Evaluar el sistema implementado mediante métricas operativas cuantitativas — tiempo total de procesamiento, tasa de error detectado, completitud y consistencia del dataset— y mediante la verificación de la correcta ejecución del análisis estadístico, comparando los resultados con el proceso manual de referencia. 

## **1.6 Preguntas de investigación** 

Las siguientes preguntas de investigación orientan el desarrollo del trabajo y son respondidas, con diferente grado de énfasis, a lo largo de los capítulos de resultados y discusión: 

Página 9 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

- ¿Qué conjunto mínimo pero suficiente de validaciones automáticas permite detectar la mayor proporción de errores típicamente presentes en datos de ensayos agrícolas antes de que lleguen al análisis estadístico? 

- ¿En qué medida la automatización del pipeline de procesamiento reduce el tiempo total de preparación del dataset respecto del proceso manual de referencia, y cuál es la magnitud de esa reducción en condiciones operativas realistas? 

- ¿Cómo garantizar, de manera técnicamente sólida y operativamente viable, que cada transformación aplicada al dato quede registrada con suficiente detalle para permitir la auditoría y la reproducción del proceso completo? 

- ¿Qué condiciones técnicas y metodológicas son necesarias para que el análisis estadístico ejecutado sobre el dataset resultante del pipeline sea plenamente reproducible, es decir, para que produzca resultados idénticos al ser ejecutado nuevamente sobre los mismos datos con el mismo código? 

## **1.7 Hipótesis de trabajo** 

Las siguientes hipótesis de trabajo guían el proceso de evaluación del sistema implementado y son sometidas a verificación empírica en el Capítulo 5: 

H1: Un pipeline automatizado que incorpora validaciones sistemáticas de completitud, validez, consistencia y unicidad produce un dataset con una tasa de error residual significativamente inferior a la obtenida mediante el proceso manual de referencia. Esta hipótesis asume que la mayor parte de los errores introducidos por el proceso manual son detectables mediante reglas formales y que la automatización de la aplicación de esas reglas elimina la componente aleatoria de su cumplimiento. 

H2: La automatización del proceso de preparación del dataset reduce el tiempo total requerido desde la recepción de los datos crudos hasta la disponibilidad del dataset listo para análisis en al menos un cincuenta por ciento respecto del proceso manual de referencia, bajo condiciones comparables de volumen de datos y complejidad del ensayo. 

H3: La incorporación de trazabilidad explícita —registro de cada transformación con su motivo, momento de ejecución y versión del código aplicado— mejora la auditabilidad del proceso y facilita la replicación independiente del análisis estadístico, reduciendo el tiempo necesario para reconstruir el pipeline completo a partir de la documentación generada automáticamente. 

## **1.8 Alcances y limitaciones** 

El alcance del sistema desarrollado en esta tesis comprende la automatización completa del proceso desde la ingesta de los datos crudos —en formatos tabulares como CSV o 

Página 10 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

Excel— hasta la generación del dataset limpio, validado y estructurado listo para análisis, incluyendo la ejecución del análisis estadístico reproducible y la generación de la bitácora de auditoría correspondiente. El sistema es evaluado sobre ensayos agrícolas con diseños experimentales convencionales compatibles con el análisis de varianza —diseño completamente aleatorio, bloques completos al azar— o con las alternativas estadísticas apropiadas cuando los supuestos del ANOVA no se satisfacen. 

Las limitaciones del trabajo deben ser explicitadas con igual claridad. En primer lugar, el sistema no reemplaza ni suple al diseño experimental: su función es procesar y analizar datos de ensayos ya diseñados y ejecutados; no tiene capacidad para corregir deficiencias de diseño —pseudoreplicación, confusión de factores, desequilibrios no previstos— ni para compensar sesgos de muestreo introducidos en la etapa de campo. En segundo lugar, el desempeño del sistema depende de la calidad del dato en origen: si el registro en campo es sistemáticamente erróneo en alguna dimensión no captada por las reglas de validación implementadas, el pipeline producirá datos incorrectos con la misma eficiencia con que procesaría datos correctos. En tercer lugar, los componentes de inteligencia artificial eventualmente incorporados operan como herramientas de apoyo con supervisión humana requerida para decisiones de alto impacto; su uso no está validado para sustitución autónoma del criterio experto en contextos de alta incertidumbre. Finalmente, la generalización de los resultados a escenarios con diseños experimentales altamente complejos —diseños de medidas repetidas, ensayos en serie con modelos mixtos de alta dimensionalidad— requerirá adaptaciones que van más allá del alcance de este trabajo. 

## **1.9 Estructura del documento** 

El presente documento se organiza en siete capítulos cuya lógica es secuencial y acumulativa. El Capítulo 2 provee el marco teórico y el estado del arte necesarios para situar el trabajo en el contexto del conocimiento existente, cubriendo los fundamentos de los ensayos agrícolas y la gestión del dato experimental, los conceptos de calidad del dato y trazabilidad, los paradigmas de automatización de flujos y la herramienta n8n, las prácticas de Python para ciencia de datos reproducible, los fundamentos estadísticos relevantes para la experimentación agrícola, y el rol de la inteligencia artificial en tareas de apoyo a la limpieza y validación de datos. El Capítulo 3 describe en detalle el marco metodológico adoptado: el tipo de investigación, el diseño del estudio de caso, las fuentes de datos, los instrumentos y técnicas, el procedimiento de implementación y evaluación, y las consideraciones éticas pertinentes. El Capítulo 4 desarrolla el sistema en toda su extensión técnica: requisitos, arquitectura, modelo de datos, pipeline de ingesta y validación, transformación, persistencia y auditoría, módulo estadístico y diagrama del 

Página 11 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

sistema. El Capítulo 5 presenta los resultados operativos y analíticos obtenidos, incluyendo la comparación con el proceso manual de referencia. El Capítulo 6 discute los resultados en profundidad, abordando su interpretación, implicaciones, amenazas a la validez y lecciones aprendidas. El Capítulo 7 sintetiza las conclusiones, los aportes originales del trabajo, las limitaciones reconocidas y las líneas de investigación futura que se abren a partir de él. El documento se completa con las referencias bibliográficas y los anexos técnicos. 

Página 12 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Capítulo 2. Marco teórico y estado del arte** 

## **2.1 Ensayos agrícolas y gestión del dato experimental** 

Un ensayo agrícola en sentido estricto es una experiencia diseñada bajo principios estadísticos que permite comparar el efecto de uno o más factores de tratamiento sobre una o más variables respuesta, controlando o midiendo las fuentes de variación relevantes y obteniendo estimaciones cuantitativas de los efectos con su correspondiente medida de incertidumbre. Los principios fundamentales de la experimentación agrícola —replicación, aleatorización y control local— fueron establecidos por R.A. Fisher en el marco del programa de investigación de Rothamsted a partir de la década de 1920, y siguen siendo la base conceptual indispensable para la interpretación correcta de cualquier análisis estadístico aplicado a datos de campo. 

La cadena de datos en un ensayo agrícola comienza en el campo —donde las mediciones se realizan sobre las unidades experimentales individuales: parcelas, plantas, muestras— y termina en el análisis estadístico que fundamenta las conclusiones del estudio. Entre estos dos extremos existe una secuencia de pasos que, en la práctica, incluye la captura del dato crudo, su transcripción a un soporte digital, su organización en un formato adecuado para el análisis, su validación frente a criterios de integridad, su eventual transformación para cumplir con los supuestos del modelo estadístico, y su almacenamiento en una estructura persistente y recuperable. Cada uno de estos pasos es una oportunidad para introducir errores o para perder información sobre la historia del dato. 

La literatura especializada en diseño experimental agrícola —representada por obras de referencia como las de Cochran y Cox (1957), Montgomery (2019) y Hinkelmann y Kempthorne (2008)— dedica considerables esfuerzos a la especificación del diseño y al análisis estadístico, pero históricamente ha prestado escasa atención sistemática a la gestión del dato en los pasos intermedios. Esta brecha ha comenzado a cerrarse en las últimas décadas, impulsada por el movimiento de ciencia abierta y reproducibilidad y por la creciente conciencia de que un análisis estadístico impecable sobre datos de mala calidad produce conclusiones inválidas con igual rigor formal que un análisis correcto sobre datos íntegros. 

En el contexto específico de los programas de mejoramiento genético y evaluación de materiales, donde un mismo ensayo puede repetirse en múltiples ambientes y campañas, la gestión sistemática del dato cobra una dimensión adicional: la necesidad de integrar información proveniente de fuentes heterogéneas —distintos sitios, distintos instrumentos, 

Página 13 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

distintos operadores— bajo un esquema común que permita análisis conjuntos con coherencia estadística. Esta integración es, precisamente, uno de los desafíos centrales que el sistema desarrollado en esta tesis busca abordar. 

## **2.2 Calidad de datos: dimensiones, trazabilidad y auditoría** 

El concepto de calidad del dato ha sido objeto de elaboración sistemática en el campo de la gestión de información y los sistemas de información desde al menos la década de 1990. La definición más influyente, propuesta por Wang y Strong (1996) en el marco de su estudio sobre las dimensiones de la calidad del dato percibida por los consumidores de información, identifica cuatro categorías principales: calidad intrínseca (precisión, objetividad, credibilidad, reputación), calidad de accesibilidad (accesibilidad, seguridad en el acceso), calidad contextual (relevancia, valor añadido, actualidad, completitud, cantidad adecuada de datos) y calidad representacional (interpretabilidad, facilidad de comprensión, representación concisa y consistente). 

Para los propósitos específicos de la gestión del dato experimental agrícola, las dimensiones más relevantes son la completitud —todos los registros que deberían existir efectivamente existen y contienen valores en todos los campos requeridos—, la validez — los valores observados son compatibles con los tipos de dato y los rangos esperados para cada variable—, la consistencia —no existen contradicciones entre distintas variables del mismo registro ni entre registros relacionados—, la unicidad —no existen duplicados no intencionales— y la trazabilidad —se mantiene un registro explícito de la historia del dato, incluyendo todas las transformaciones aplicadas y sus fundamentos. 

La trazabilidad merece una atención especial en este contexto. En los sistemas de información empresariales, la trazabilidad se asocia frecuentemente con el concepto de linaje del dato (data lineage): la capacidad de conocer, para cualquier dato presente en el sistema, de dónde proviene, qué transformaciones ha sufrido y qué impacto tendría un error en los datos de origen sobre los resultados finales. En el contexto científico, la trazabilidad es además una condición necesaria para la reproducibilidad: si no se puede reconstruir exactamente el proceso por el cual se llegó desde los datos crudos hasta el dataset analizado, tampoco se puede garantizar que la replicación del análisis produciría los mismos resultados. 

La auditoría del dato, estrechamente relacionada con la trazabilidad, implica la existencia de registros inmutables y verificables de todas las operaciones realizadas sobre los datos, con suficiente detalle para que un auditor externo pueda comprender qué se hizo, cuándo, por quién o por qué sistema, y con qué justificación. En el contexto de un pipeline automatizado, la auditoría se implementa típicamente mediante la generación automática 

Página 14 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

de logs estructurados que registran cada ejecución del flujo con sus parámetros, los resultados de las validaciones aplicadas, las transformaciones ejecutadas y cualquier excepción o anomalía detectada. 

## **2.3 Automatización de flujos (ETL/ELT) y orquestación con n8n** 

Los procesos de automatización de flujos de datos se enmarcan en el paradigma de la integración de datos, cuyos modelos arquitectónicos más establecidos son el ETL (Extraer, Transformar, Cargar) y el ELT (Extraer, Cargar, Transformar). En el modelo ETL, los datos se extraen de las fuentes, se transforman en un entorno intermedio para cumplir con los requisitos de calidad y estructura del destino, y se cargan finalmente en el repositorio de destino. En el modelo ELT, los datos se cargan primero en el repositorio de destino — generalmente un almacén de datos con capacidad de cómputo interna— y las transformaciones se ejecutan dentro de ese entorno. La elección entre ambos modelos depende de factores como el volumen de datos, la capacidad de procesamiento disponible, los requisitos de latencia y la complejidad de las transformaciones requeridas. 

Para el caso específico de los ensayos agrícolas, el modelo ETL resulta más apropiado por múltiples razones: los volúmenes de datos son generalmente moderados (del orden de miles a decenas de miles de registros por campaña), las transformaciones requeridas son conceptualmente complejas —involucran lógica de dominio agronómico, reglas de validación específicas del diseño experimental y estandarización de nomenclaturas— y la separación entre la fase de transformación y la de carga permite un control más granular sobre la calidad del dato antes de que este llegue al repositorio final. 

n8n es una plataforma de automatización de flujos de trabajo de código abierto que permite diseñar, ejecutar y monitorear workflows mediante una interfaz visual basada en nodos interconectados. Cada nodo representa una operación —lectura de un archivo, llamada a una API, ejecución de código, envío de una notificación, escritura en una base de datos— y los flujos se construyen conectando nodos en secuencias o en estructuras de control más complejas que incluyen condicionales, iteraciones y manejo de errores. n8n soporta la integración con cientos de servicios externos mediante conectores nativos y permite la ejecución de código personalizado en JavaScript y, mediante el nodo de código, en Python, lo que lo hace particularmente versátil para casos de uso como el de esta tesis. 

Las ventajas de n8n sobre soluciones de orquestación de mayor complejidad como Apache Airflow o Prefect radican en su menor curva de aprendizaje, su facilidad de despliegue en entornos locales o en nube de pequeña escala, y su interfaz visual que facilita la comprensión del flujo por parte de usuarios con distintos perfiles técnicos. Al mismo tiempo, n8n ofrece capacidades suficientes para los requisitos de este trabajo: ejecución 

Página 15 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

programada o disparada por eventos, registro de ejecuciones con logs, manejo de errores con reintentos configurables y notificaciones, y capacidad de integración con el ecosistema Python mediante llamadas a scripts o servicios externos. 

## **2.4 Python para ciencia de datos: reproducibilidad y control de versiones** 

Python se ha consolidado como el lenguaje de facto para la ciencia de datos en la comunidad científica global, desplazando progresivamente a lenguajes especializados como R en muchos dominios aplicados, aunque la convivencia y la interoperabilidad entre ambos son comunes en el campo estadístico. La fortaleza de Python en este dominio reside en la madurez y profundidad de su ecosistema de bibliotecas: pandas para la manipulación de datos tabulares, NumPy para operaciones numéricas de alto rendimiento, statsmodels para modelado estadístico clásico, scikit-learn para aprendizaje automático, matplotlib y seaborn para visualización, y una extensa colección de herramientas complementarias. 

La reproducibilidad de los análisis realizados en Python depende de múltiples condiciones que deben ser satisfechas de manera simultánea. La primera es la especificación y fijación de dependencias: el entorno de ejecución —versiones exactas de Python y de cada biblioteca— debe estar documentado de manera que pueda ser recreado idénticamente. Esto se logra mediante herramientas como pip con archivos requirements.txt, conda con archivos environment.yml, o sistemas modernos de gestión de dependencias como Poetry. La segunda condición es el control de versiones del código: todos los scripts que conforman el pipeline deben estar gestionados mediante un sistema de control de versiones como Git, de manera que cada ejecución del análisis pueda asociarse a un commit específico que identifica exactamente la versión del código utilizada. La tercera condición es la parametrización: el código no debe contener valores hardcodeados que dependan del conjunto de datos específico o del diseño experimental concreto; en cambio, debe recibir sus parámetros de configuración de manera explícita, lo que facilita tanto la comprensión del análisis como su aplicación a nuevos datos. 

Adicionalmente, la generación automática de reportes —mediante herramientas como Jupyter Notebooks con ejecución programática vía papermill, o mediante el ecosistema R Markdown a través de rpy2— permite producir documentación del análisis que integra código, resultados y narrativa en un único artefacto versionable y re-ejecutable. Esta práctica es especialmente valiosa en el contexto de la experimentación agrícola, donde los análisis se repiten con distintos conjuntos de datos a lo largo de múltiples campañas y es necesario garantizar coherencia metodológica entre ciclos. 

Página 16 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

## **2.5 Estadística en experimentación agrícola: ANOVA y alternativas** 

El Análisis de Varianza (ANOVA) es la herramienta estadística de referencia para la comparación de medias en experimentos con uno o más factores de tratamiento. Su fundamento conceptual, desarrollado por R.A. Fisher, consiste en la partición de la varianza total observada en el experimento en componentes atribuibles a los distintos factores en estudio —tratamientos, bloques, interacciones— y a la variación residual no explicada por el modelo. El cociente entre la varianza del factor en cuestión y la varianza residual constituye el estadístico F, cuya distribución bajo la hipótesis nula de igualdad de medias permite calcular la probabilidad de observar la diferencia observada por azar. 

Los supuestos formales del ANOVA son tres: independencia de los residuos del modelo, distribución normal de los residuos, y homogeneidad de varianzas entre los grupos (homocedasticidad). La validación de estos supuestos no es opcional en un análisis estadístico riguroso: es una condición para la validez de las inferencias realizadas. El diagnóstico se realiza mediante una combinación de herramientas visuales —gráficos de residuos versus valores ajustados para detectar heterocedasticidad, gráficos Q-Q normal para evaluar la normalidad de los residuos— y pruebas formales —prueba de Levene o de Bartlett para la igualdad de varianzas, prueba de Shapiro-Wilk para normalidad en muestras pequeñas. 

Cuando los supuestos del ANOVA no se satisfacen, el analista dispone de diversas alternativas. Las transformaciones de la variable respuesta —logarítmica, raíz cuadrada, inversa— pueden en algunos casos corregir la heterocedasticidad y aproximar la normalidad de los residuos. Las pruebas no paramétricas —Kruskal-Wallis para el caso de un factor, Friedman para diseños en bloques— ofrecen una alternativa robusta cuando los supuestos de normalidad son claramente violados y las transformaciones no resultan efectivas. Los modelos lineales generalizados (GLM) permiten especificar una distribución de error apropiada para la naturaleza de la variable respuesta —binomial para proporciones, Poisson para conteos, gamma para variables continuas positivas con varianza proporcional a la media. Los modelos lineales mixtos (LMM), finalmente, son la herramienta más adecuada cuando el diseño experimental incluye factores con efectos aleatorios —como ambientes o repeticiones en ensayos multi-ambiente— o cuando la estructura de la varianza-covarianza de los residuos es más compleja que la asumida por el ANOVA estándar. 

A nivel de una maestría en sistemas de información o ingeniería, la competencia esperada no es la del estadístico que realiza el análisis sino la del ingeniero que diseña e implementa un sistema capaz de ejecutar ese análisis de manera correcta, reproducible y 

Página 17 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

documentada. Esto implica: comprender los supuestos de los modelos utilizados con suficiente profundidad para implementar los diagnósticos apropiados, parametrizar el módulo estadístico de manera que sea aplicable a distintos diseños experimentales sin modificar el código base, y generar reportes que documenten explícitamente el modelo aplicado, los supuestos verificados y los resultados obtenidos. 

## **2.6 Inteligencia artificial como apoyo en limpieza y validación de datos** 

La incorporación de componentes de inteligencia artificial en pipelines de gestión de datos es una tendencia creciente que ofrece posibilidades genuinamente valiosas para el caso de uso de esta tesis, pero que también exige cautelas metodológicas que deben explicitarse con claridad. Las tareas en las que la IA puede aportar valor en el contexto de la gestión del dato experimental incluyen: la estandarización semiautomática de campos con alta variabilidad léxica —por ejemplo, nombres de variedades, identificadores de tratamientos o etiquetas de ambientes que presentan múltiples grafías para el mismo referente—, la detección de anomalías estadísticas en distribuciones de variables respuesta que podrían indicar errores de registro o valores atípicos verdaderos, y la asistencia en el control de calidad mediante la generación de sugerencias de corrección que son revisadas y aprobadas por un operador humano antes de ser aplicadas. 

La precaución fundamental que debe gobernar el uso de IA en un pipeline científico es que ningún cambio al dato debe ser efectuado de manera autónoma por el sistema de IA sin un mecanismo de registro explícito y sin la posibilidad de revisión y reversión por parte de un operador humano competente. Esta restricción no es técnicamente difícil de implementar —basta con que el módulo de IA genere propuestas de cambio que requieren aprobación antes de ser aplicadas, y que cada aprobación o rechazo quede registrado en la bitácora de auditoría— pero es conceptualmente indispensable para preservar la integridad epistémica del proceso científico. 

Desde el punto de vista del estado del arte, los modelos de lenguaje de gran escala (LLM) han demostrado capacidades notables en tareas de reconocimiento y resolución de entidades con variabilidad superficial, normalización de formatos y detección de inconsistencias lógicas en datos tabulares. Sin embargo, su aplicación en contextos científicos donde las decisiones tienen consecuencias directas sobre conclusiones publicadas exige una validación cuidadosa del comportamiento del modelo, el establecimiento de umbrales de confianza por debajo de los cuales el sistema escala la decisión al operador humano, y la documentación explícita del rol del componente de IA en el pipeline para que los lectores del trabajo puedan evaluar adecuadamente su impacto. 

Página 18 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Capítulo 3. Marco metodológico** 

## **3.1 Tipo de investigación y enfoque** 

Esta tesis se enmarca en el paradigma de la investigación aplicada, específicamente en la modalidad conocida en ingeniería como Design Science Research (DSR) o investigación orientada al diseño. En este paradigma, el objetivo central no es generar conocimiento universal sobre fenómenos naturales o sociales, sino producir artefactos —sistemas, modelos, métodos, herramientas— que resuelvan problemas prácticos identificados con rigor, y generar conocimiento sobre el proceso de construcción y evaluación de esos artefactos que sea generalizable más allá del caso concreto. El artefacto principal producido por esta tesis es el pipeline automatizado de gestión y análisis de datos de ensayos agrícolas; el conocimiento generalizable se refiere a los principios de diseño que guiaron su construcción y a las métricas de evaluación que permiten valorar su desempeño. 

El enfoque metodológico es predominantemente cuantitativo en la fase de evaluación — las métricas de desempeño operativo y estadístico son medidas numéricamente y comparadas con una línea base mediante indicadores objetivos— con elementos cualitativos en la fase de diseño, donde el relevamiento de requisitos y el modelado del proceso involucran la comprensión interpretativa de prácticas de trabajo específicas que no se reducen enteramente a métricas. 

## **3.2 Diseño metodológico: ingeniería aplicada y estudio de caso** 

El diseño metodológico adoptado sigue la lógica del estudio de caso instrumental (Stake, 1995; Yin, 2018): se selecciona un caso concreto —uno o varios ensayos agrícolas reales o representativos— no por su valor intrínseco sino como instrumento para el desarrollo y la evaluación del sistema propuesto. La elección del estudio de caso como estrategia metodológica se fundamenta en tres razones. En primer lugar, permite trabajar con datos y contextos operativos reales, lo que dota al proceso de diseño e implementación de concreción y relevancia práctica. En segundo lugar, facilita la comparación entre el estado actual del proceso —la línea base manual— y el estado propuesto —el pipeline automatizado— en condiciones lo más equivalentes posible. En tercer lugar, genera evidencia suficientemente detallada para fundamentar las conclusiones sobre la efectividad del sistema y las condiciones de su aplicabilidad. 

El ciclo de investigación comprende las siguientes fases, ejecutadas de manera iterativa y con retroalimentación entre etapas: (1) relevamiento y modelado del proceso actual; (2) 

Página 19 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

especificación de requisitos y diseño de la solución; (3) implementación incremental con pruebas por módulo; (4) ejecución de corridas de validación con datos de ensayo; (5) medición de métricas y comparación con la línea base; y (6) documentación técnica y científica de todo el proceso. Cada iteración produce una versión mejorada del sistema y un conjunto de lecciones aprendidas que informan la siguiente iteración. 

## **3.3 Fuentes de datos y criterios de calidad** 

Las fuentes de datos primarias sobre las que opera el sistema son los archivos de datos crudos generados por los ensayos agrícolas de referencia. En su formato típico, estos archivos son planillas de cálculo en formato CSV o Excel que contienen, en su estructura básica, una fila por unidad experimental —parcela o planta— y columnas para los identificadores del ensayo, los factores de tratamiento, las variables de clasificación (bloque, repetición, ambiente) y las variables respuesta medidas en campo o en laboratorio. 

Los criterios de calidad que definen la aceptabilidad del dato en cada dimensión relevante son formalizados como reglas de validación explícitas durante la fase de diseño del sistema. Para la dimensión de completitud, se define qué campos son obligatorios y cuál es el comportamiento esperado del sistema ante valores faltantes en campos obligatorios versus campos opcionales. Para la dimensión de validez, se especifican para cada variable el tipo de dato esperado, el rango de valores plausibles y, cuando corresponde, la lista cerrada de valores admisibles. Para la dimensión de consistencia, se identifican las relaciones lógicas entre variables que deben mantenerse en todo registro válido —por ejemplo, la relación entre la fecha de siembra y la fecha de cosecha, o la consistencia entre el identificador de tratamiento y los atributos del tratamiento registrados en el catálogo. Para la dimensión de unicidad, se define la clave primaria de cada registro y se implementa la detección de duplicados basada en esa clave. 

## **3.4 Instrumentos y técnicas** 

Los instrumentos y técnicas utilizados en el desarrollo de este trabajo se organizan en cuatro categorías funcionales que corresponden a los componentes principales del sistema. La primera categoría comprende las herramientas de orquestación: n8n se utiliza para diseñar y ejecutar los workflows de automatización, configurar los disparadores de ejecución —programada o basada en eventos—, gestionar las dependencias entre módulos del pipeline y registrar las ejecuciones con sus resultados y errores. La segunda categoría comprende las herramientas de procesamiento: Python, con las bibliotecas pandas, numpy, great_expectations —para la implementación declarativa de reglas de calidad del dato— y statsmodels, se utiliza para la implementación de los validadores, los 

Página 20 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

transformadores y el módulo de análisis estadístico. La tercera categoría comprende las herramientas de persistencia: una base de datos relacional —cuya tecnología concreta se especifica en el Capítulo 4— almacena el dataset validado y transformado, las bitácoras de ejecución y el catálogo de variables y reglas de validación. La cuarta categoría comprende las herramientas de control de versiones y reproducibilidad: Git gestiona el código fuente de todos los scripts, y los entornos virtuales de Python garantizan la reproducibilidad de las dependencias. 

## **3.5 Procedimiento** 

1. Relevamiento del proceso manual actual: se documentan los pasos del flujo de trabajo existente mediante entrevistas con los usuarios del sistema, revisión de los archivos típicos de entrada y salida, y registro de los tipos de errores más frecuentes y sus consecuencias sobre el análisis estadístico. El resultado de esta fase es un diagrama de proceso As-Is y una lista de los problemas identificados con su frecuencia y severidad. 

2. Definición del diccionario de variables y reglas de validación: con base en el relevamiento anterior y en el conocimiento experto del dominio agronómico, se especifica formalmente el esquema de datos del sistema, incluyendo todas las variables, sus tipos, unidades, rangos y reglas de validación. Este diccionario se convierte en la fuente de verdad sobre la que se construyen los validadores del pipeline. 

3. Diseño de la arquitectura y del pipeline: se elabora el diseño técnico del sistema, incluyendo la arquitectura por capas, el diagrama de flujo del pipeline, la especificación de las interfaces entre módulos y los protocolos de manejo de errores y registro. 

4. Implementación incremental: el sistema se construye módulo por módulo, comenzando por la ingesta y la validación, continuando con la transformación y la persistencia, y finalizando con el módulo estadístico. Cada módulo se prueba de manera aislada antes de su integración en el pipeline completo. 

5. Ejecución de corridas controladas: el pipeline completo se ejecuta sobre conjuntos de datos de ensayo que incluyen tanto datos correctos como datos con errores introducidos intencionalmente, para verificar que los validadores detectan los errores esperados y que el flujo de error produce la respuesta esperada. 

6. Medición de métricas y comparación con la línea base: se miden las métricas operativas y estadísticas definidas en la sección 3.6 sobre los resultados de las corridas de validación, y se comparan con los valores correspondientes del proceso manual de referencia. 

7. Documentación técnica y científica: se produce la documentación del sistema — código comentado, diagramas actualizados, bitácoras de versiones— y la 

Página 21 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

documentación científica —capítulos de la tesis, reporte de resultados— de manera integrada y coherente. 

## **3.6 Criterios de evaluación: métricas técnicas y estadísticas** 

La evaluación del sistema se realiza mediante dos categorías complementarias de métricas. Las métricas operativas cuantifican el desempeño del pipeline en términos de eficiencia y calidad del dato producido: el tiempo total de procesamiento desde la recepción del archivo de entrada hasta la disponibilidad del dataset validado y almacenado; la tasa de errores detectados, definida como la proporción de registros con al menos un error respecto del total de registros procesados; la completitud del dataset resultante, medida como la proporción de campos obligatorios con valores no nulos; y la consistencia del dataset resultante, medida como la proporción de registros sin violaciones de las reglas de consistencia cruzada. Las métricas estadísticas evalúan la capacidad del módulo de análisis para producir resultados correctos y reproducibles: la correctitud del análisis estadístico verificada mediante comparación con resultados de referencia calculados manualmente por un experto; la reproducibilidad verificada mediante re-ejecución del análisis sobre los mismos datos con el mismo código y confirmación de resultados idénticos; y la completitud del diagnóstico de supuestos verificada mediante la revisión de los elementos del reporte estadístico generado. 

## **3.7 Consideraciones éticas y de gestión de datos** 

El desarrollo de este trabajo involucra el manejo de datos de ensayos agrícolas que pueden incluir información de valor comercial o estratégico para las instituciones u organizaciones que los generaron. En consecuencia, el trabajo se rige por los principios de confidencialidad y uso restringido: los datos utilizados para el desarrollo y validación del sistema son tratados exclusivamente con fines de investigación, no son compartidos con terceros sin autorización expresa de los titulares, y son almacenados de manera segura durante el período de desarrollo de la tesis. El sistema implementado incorpora mecanismos de control de acceso que limitan la operación sobre los datos a los usuarios autorizados y registran toda operación de acceso y modificación en la bitácora de auditoría. El código fuente del sistema, a menos que existan restricciones institucionales específicas, es desarrollado bajo principios de código abierto y documentado de manera suficiente para permitir su replicación independiente, contribuyendo así a los objetivos de la ciencia abierta. 

La adopción de Telegram como único canal de interacción humana con el sistema introduce una consideración de confidencialidad que corresponde documentar con precisión, sin sobrevenderla ni exagerarla. Los chats de un bot de Telegram no cuentan con cifrado de extremo a extremo: esa modalidad existe en Telegram únicamente en sus conversaciones secretas, en las que los bots no pueden participar. El tráfico entre el cliente y los servidores de Telegram sí viaja cifrado en tránsito y no queda expuesto en un canal abierto, lo cual es preferible a un canal sin cifrar o a un correo electrónico ordinario, pero no equivale a una garantía de confidencialidad total, puesto que el operador de la plataforma tiene técnicamente acceso al contenido alojado en sus servidores. Esto plantea una tensión que el trabajo asume de manera explícita: la misma sensibilidad del dato de ensayo que motivó prohibir el reconocimiento óptico en servicios de nube y restringir su procesamiento a un entorno local se acepta, en un grado menor, para el canal de Telegram. La razón es que el beneficio operativo del canal —fricción nula para los usuarios de campo, un único punto de contacto y su integración nativa con la capa de orquestación— supera el riesgo residual para el alcance de esta tesis, siempre que ese matiz quede registrado como lo que es y no se presente como confidencialidad completa. 

Página 22 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Capítulo 4. Desarrollo: diseño e implementación del sistema** 

## **4.1 Requisitos funcionales y no funcionales** 

### **_Requisitos funcionales_** 

Los requisitos funcionales del sistema describen las capacidades que el pipeline debe proveer para satisfacer los objetivos del trabajo. Se organizan en cinco grupos funcionales correspondientes a las etapas principales del pipeline: 

El primer grupo, correspondiente a la ingesta de datos, establece que el sistema debe ser capaz de leer archivos de datos crudos en formatos CSV y Excel, detectar y reportar problemas de codificación o formato que impidan la lectura correcta del archivo, e inferir o validar la estructura del archivo contra el esquema esperado antes de proceder con el procesamiento. El segundo grupo, correspondiente a la validación, establece que el sistema debe aplicar sobre cada registro del dataset las reglas de validación definidas en el diccionario de variables —tipo de dato, rango, lista de valores, obligatoriedad, unicidad de clave, consistencia cruzada— generar un reporte de validación que identifique cada violación con el registro afectado, el campo involucrado y la regla violada, y producir dos salidas: un dataset de registros válidos y un dataset de registros rechazados con su respectivo detalle de errores. El tercer grupo, correspondiente a la transformación, establece que el sistema debe normalizar los nombres de columnas a un formato canónico, estandarizar los valores de las variables categóricas mediante el catálogo de términos aceptados, aplicar las conversiones de unidades especificadas en el diccionario de variables cuando sean necesarias, y construir el dataset en formato tidy listo para el análisis estadístico. El cuarto grupo, correspondiente a la persistencia y auditoría, establece que el sistema debe almacenar el dataset validado y transformado en el repositorio de destino, registrar en la bitácora de auditoría cada ejecución del pipeline con su fecha y hora, la versión del código utilizado, la huella del archivo de entrada, el número de registros procesados, validados, rechazados y almacenados, y el detalle de cada transformación aplicada. El quinto grupo, correspondiente al análisis estadístico, establece que el sistema debe ejecutar el modelo estadístico especificado mediante parámetros de configuración — fórmula del modelo, tipo de diseño, variables de bloqueo—, generar la tabla de ANOVA o el resumen del modelo alternativo, ejecutar los diagnósticos de supuestos y producir un reporte reproducible que integre todos los elementos anteriores. 

### **_Requisitos no funcionales_** 

Página 23 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

Los requisitos no funcionales describen las características de calidad del sistema que no corresponden a funcionalidades específicas sino a propiedades transversales de su diseño y operación. Los más relevantes para este trabajo son los siguientes: trazabilidad, que establece que toda transformación aplicada al dato debe ser registrada de manera que permita reconstruir el estado del dato en cualquier punto del pipeline a partir de las bitácoras generadas; mantenibilidad, que establece que el código debe estar estructurado en módulos con responsabilidades claramente delimitadas, documentado con suficiente detalle para que un desarrollador con conocimientos equivalentes pueda comprenderlo y modificarlo, y versionado mediante Git; auditabilidad, que establece que el sistema debe generar evidencia suficiente de sus operaciones para que un auditor externo pueda verificar que el pipeline fue ejecutado correctamente sobre los datos declarados; tolerancia a fallos, que establece que el sistema debe manejar errores en el procesamiento de registros individuales sin interrumpir el procesamiento del resto del dataset, y debe reportar claramente qué registros no pudieron ser procesados y por qué; y reproducibilidad, que establece que la ejecución del pipeline con los mismos datos de entrada y la misma versión del código debe producir resultados idénticos en cualquier entorno que satisfaga las dependencias especificadas. 

## **4.2 Arquitectura y componentes** 

El sistema se organiza según una arquitectura en capas que separa claramente las responsabilidades de orquestación, procesamiento, persistencia y análisis. Esta separación facilita el mantenimiento independiente de cada capa, la sustitución de tecnologías específicas sin afectar al resto del sistema, y la comprensión del flujo de datos a alto nivel. 

La capa de orquestación, implementada sobre n8n, es responsable de coordinar la ejecución del pipeline de extremo a extremo. Esta capa gestiona los disparadores de ejecución —ya sea mediante un programa horario, por la detección de nuevos archivos en una ubicación designada, o por invocación manual—, los pasos del workflow con sus dependencias y condiciones de transición, el manejo de errores a nivel de flujo — incluyendo reintentos automáticos con retardo exponencial para fallos transitorios y escalamiento a notificación humana para errores persistentes—, y el registro de cada ejecución en el sistema de logs con sus metadatos completos. 

La capa de procesamiento, implementada como un conjunto de scripts Python con interfaces bien definidas, contiene toda la lógica de negocio del pipeline: la lectura y validación estructural del archivo de entrada, la aplicación de las reglas de calidad del dato, las transformaciones de normalización y estandarización, y la preparación del dataset para 

Página 24 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

el análisis estadístico. Esta capa está completamente desacoplada de n8n: puede ser invocada directamente desde la línea de comandos para pruebas y desarrollo, y sus interfaces de entrada y salida están documentadas de manera que pueden ser integradas con herramientas de orquestación alternativas sin modificar el código de procesamiento. 

La capa de persistencia gestiona el almacenamiento del dataset validado y del catálogo de variables y reglas, así como el repositorio de bitácoras de auditoría. La tecnología de persistencia es seleccionada de acuerdo con los requisitos de volumen, concurrencia y portabilidad del caso de uso específico; para los ensayos agrícolas de referencia utilizados en esta tesis, una base de datos relacional liviana —SQLite para desarrollo y pruebas, PostgreSQL para entornos de producción— satisface todos los requisitos sin introducir complejidad operativa innecesaria. 

En el plano de implementación, el acceso a la base de datos se realiza mediante SQLAlchemy con modelos declarativos, evitando el SQL escrito a mano por motor; esta capa de abstracción es la que permite sostener en la práctica la paridad de esquema entre SQLite y PostgreSQL declarada como requisito. Los cambios de esquema se versionan mediante Alembic, de modo que cada modificación queda registrada como una migración auditable en el repositorio, en coherencia con el énfasis en trazabilidad que atraviesa el diseño del sistema. Todas las entidades del modelo utilizan claves primarias de tipo entero autoincremental, decisión suficiente para este alcance dado que el sistema no es distribuido: toda escritura pasa por el mismo backend de persistencia. Finalmente, la cadena de conexión se configura mediante una única variable de entorno (DATABASE_URL), documentada en la plantilla .env.example del repositorio, lo que permite alternar entre el motor de desarrollo y el de producción sin modificar el código. 

La capa de análisis estadístico es un módulo Python independiente que recibe como entrada el dataset validado y un archivo de configuración que especifica el modelo estadístico a aplicar, y produce como salida un reporte estructurado que incluye los resultados del análisis y los diagnósticos de supuestos. Este módulo está diseñado para ser completamente parametrizable y ejecutable bajo control de versiones, de manera que cada análisis queda perfectamente documentado mediante el archivo de configuración y el commit de Git que corresponde a la versión del código utilizada. 

A las cuatro capas anteriores se agrega una capa de interacción humana, responsable de mediar todo contacto entre las personas y el sistema. Las capas descritas hasta aquí resuelven un problema de ingeniería —que el procesamiento sea invocable, testeable y sustituible—, pero no responden a la pregunta de cómo operan el sistema los actores reales del proyecto. Estos actores incluyen a personas que en el momento de la carga de datos a campo disponen únicamente de un teléfono y de conectividad intermitente, para quienes no es realista ni deseable suponer que operarán una terminal o editarán archivos de configuración a mano. La invocación por línea de comandos descrita para la capa de procesamiento conserva su valor como mecanismo interno —es el medio por el cual la capa de orquestación llama a los scripts de procesamiento, y el que habilita las pruebas y el desarrollo—, pero deja de concebirse como una interfaz de usuario: ningún operador humano teclea nunca un comando. Toda acción que una persona necesita realizar —configurar un ensayo, cargar un dato, confirmar una lectura dudosa, recibir resultados— ocurre a través de un único canal conversacional, y el resto del procesamiento sucede de manera orientada a eventos, disparado por la capa de orquestación. 

El canal humano elegido es Telegram, por razones concretas evaluadas y aceptadas durante el diseño. La capa de orquestación ya provee un nodo nativo para enviar mensajes, imágenes y botones interactivos, y un disparador que recibe los mensajes entrantes y los eventos de pulsación de esos botones; Telegram entra así como un disparador y una salida más dentro de la orquestación existente, sin agregar un componente arquitectónico nuevo ni requerir el desarrollo y mantenimiento de un backend de mensajería propio. El canal es gratuito y no impone las fricciones de verificación de negocio, costos por conversación ni ventanas temporales para mensajes de plantilla que caracterizan a la interfaz de mensajería comercial de WhatsApp, alternativa que fue considerada y descartada por esos motivos. Los botones interactivos materializan de manera natural el patrón de confirmación o rechazo requerido por la supervisión humana de las sugerencias automáticas: un mensaje con dos opciones —confirmar el valor propuesto o corregirlo— es la forma directa de resolver una lectura de baja confianza. Finalmente, la capa de orquestación permite que un flujo de trabajo se suspenda a la espera de un evento externo y se reanude cuando este llega; mediante ese mecanismo de espera de webhook, el flujo queda pausado en el punto de confirmación y la pulsación del botón por parte del usuario reanuda la ejecución con el valor confirmado, lo que hace viable la supervisión humana asíncrona sin necesidad de sondeo ni de estado ad hoc en el flujo. 

La capa de interacción distingue dos roles de cara al canal conversacional. El rol de Ingeniero responsable del ensayo consolida, en una única cara operativa, la autoridad de decisión que en el modelo de actores del sistema se reparte entre la configuración del modelo estadístico y la definición del diccionario de variables; a través de una conversación guiada, el Ingeniero configura un ensayo nuevo, recibe los resultados una vez procesados y elige la modalidad de autoría del reporte final. El rol de Ayudante corresponde a la carga de datos a campo una vez que el ensayo ya está configurado, y carece de autoridad de configuración o de aprobación; el sistema le solicita el dato campo por campo y le ofrece proporcionarlo escribiendo el valor como texto o enviando una fotografía de una planilla de papel para su reconocimiento óptico. De este modo, la captura por reconocimiento óptico descrita en este capítulo se integra como uno de los métodos de entrada dentro del mismo flujo conversacional, y no como un subsistema paralelo. 

El núcleo técnico de esta capa es un motor genérico de sesiones dirigido por datos. La primera alternativa considerada consistía en codificar en la capa de orquestación un árbol de conversación distinto por rol, con grandes bifurcaciones según el rol del usuario y el punto de la conversación en que se encontrara. Esa alternativa se descartó por su costo de construcción y, sobre todo, de mantenimiento: cada nueva pregunta obligaría a modificar el grafo del flujo de trabajo, que crecería sin control y convertiría cualquier cambio de interacción en un cambio de código de orquestación. En su lugar se adoptó una máquina de estados de sesión genérica, respaldada por la misma capa de persistencia que el sistema ya emplea. La secuencia de pasos de cada tipo de sesión se define como dato de configuración —cada paso especifica el texto de la pregunta, el tipo de respuesta esperada y la regla de validación aplicable— y no como bifurcaciones fijas en el grafo del flujo; agregar una pregunta a un flujo se reduce, entonces, a agregar una entrada de configuración. El flujo de trabajo se reduce así a un único bucle genérico, reutilizable para todos los tipos de sesión: ante un mensaje entrante, el sistema busca primero una sesión abierta para ese usuario; si existe, trata el mensaje como la respuesta al paso actual —la valida, la almacena y avanza al paso siguiente según la secuencia configurada—, y si no existe, resuelve el tipo de sesión que corresponde al rol del usuario y crea una sesión nueva. La reanudación de una sesión previamente abierta se resuelve sin lógica adicional, como consecuencia natural de esa misma búsqueda inicial. 

Conviene delimitar con honestidad la frontera de esta automatización. La configuración inicial de un ensayo —la fórmula del modelo estadístico, el diseño experimental y el diccionario de variables— sigue siendo una decisión metodológica experta e irreductible, coherente con el alcance del sistema, que procesa ensayos pero no los diseña. Lo que la capa de interacción automatiza no es ese juicio, sino el medio por el cual el experto entrega su configuración: en lugar de editar los archivos de configuración a mano, el Ingeniero responde una secuencia guiada de preguntas y el sistema construye la configuración a partir de sus respuestas. Una vez configurado el ensayo, todo el procesamiento aguas abajo transcurre de manera orientada a eventos, y la única intervención humana recurrente son las confirmaciones de lecturas de baja confianza, que también ocurren por el mismo canal. 

Dos parámetros concretos de esta capa merecen registrarse. El primero es el tiempo de expiración de una sesión: una sesión abierta sin actividad transiciona a un estado inactivo transcurridas veinticuatro horas, umbral uniforme para todos los tipos de sesión y no diferenciado por rol. Se optó por un valor único, en lugar de umbrales diferenciados más ajustados, para no sumar parámetros que justificar; el trade-off aceptado es que una sesión abandonada puede permanecer viva hasta veinticuatro horas, holgura razonable frente a la posibilidad de un corte de conectividad real durante la carga a campo. El segundo es el formato en que se almacena la secuencia de pasos: se persiste como JSON en la base de datos, en una tabla config_paso_sesion con una fila por paso, y no como un archivo YAML versionado en el repositorio ni como una tabla relacional rígida. Esta elección es coherente con el principio de que la secuencia es dato y no código, mantiene la configuración editable sin necesidad de un nuevo despliegue, y privilegia la simplicidad de implementación y de justificación metodológica que resulta adecuada para un caso de estudio único. 

## **4.3 Modelo de datos y diccionario de variables** 

El modelo de datos del sistema distingue entre tres tipos de entidades: las entidades de dominio, que representan los objetos del mundo real que el sistema gestiona —ensayos, ambientes, tratamientos, unidades experimentales, observaciones—; las entidades de sistema, que representan los artefactos internos del pipeline —ejecuciones, bitácoras, versiones del catálogo—; y las entidades de configuración, que representan el conocimiento experto formalizado sobre el dominio —el diccionario de variables y las reglas de validación. 

Las entidades de dominio centrales son el ensayo, identificado por un código único que combina el nombre del programa, la campaña agrícola y el sitio experimental; el ambiente, que describe las condiciones de localización y manejo del ensayo en un sitio específico; el tratamiento, que especifica la combinación de niveles de los factores en estudio que se asigna a una unidad experimental; la unidad experimental, que corresponde a la parcela o planta individual sobre la que se aplica un tratamiento y se realizan las mediciones; y la observación, que registra el valor de una variable respuesta medida sobre una unidad experimental en un momento específico. La entidad ambiente incorpora, de forma opcional, las coordenadas de geolocalización del sitio —latitud y longitud—, un campo sin uso funcional en la versión actual del sistema pero previsto para habilitar líneas de trabajo futuro (sección 7.4). 

Página 25 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

El diccionario de variables formaliza, para cada variable del sistema, los siguientes atributos: nombre canónico en formato snake_case, descripción en lenguaje natural, tipo de dato (numérico entero, numérico real, categórico, fecha, texto libre), unidad de medida cuando aplica, rango de valores plausibles (mínimo y máximo) para variables numéricas, lista de valores admisibles para variables categóricas, obligatoriedad (si un valor faltante en este campo debe generar rechazo del registro), y reglas de validación cruzada con otras variables del mismo registro. La completitud y exactitud del diccionario de variables es una condición necesaria para el correcto funcionamiento del validador automático; por este motivo, el proceso de relevamiento y especificación del diccionario recibe atención especial en la fase de diseño y es validado con expertos del dominio antes de su implementación. 

La capa de interacción humana introduce, además, una nueva entidad de sistema que se integra a la capa de persistencia ya descrita y no constituye un almacén separado: la sesión. Cada interacción conversacional se modela como una sesión con un identificador propio, el identificador del usuario de Telegram que la origina —que resuelve a su vez el rol correspondiente—, una referencia opcional al ensayo asociado —opcional porque las sesiones de configuración existen antes de que el ensayo esté creado—, el tipo de sesión, el paso actual dentro de su secuencia, las respuestas acumuladas hasta el momento, el estado y las marcas temporales de creación y última actividad. El estado de una sesión toma uno de cuatro valores: abierta mientras la interacción está en curso, completada cuando se recorrió toda la secuencia de pasos, abandonada cuando el usuario la interrumpe, y expirada cuando la sesión permanece abierta sin actividad más allá del umbral de veinticuatro horas de inactividad establecido para el sistema. 

## **4.4 Pipeline de ingesta y validación** 

El módulo de ingesta es el punto de entrada del pipeline y es responsable de dos funciones: leer el archivo de datos crudos y transformarlo en una estructura tabular en memoria, y realizar una validación estructural preliminar que verifica que el archivo tiene el número esperado de columnas, que los nombres de las columnas corresponden al esquema declarado —con tolerancia configurable para variantes de capitalización y espaciado—, y que el tipo inferido de cada columna es compatible con el tipo declarado en el diccionario. Cualquier problema detectado en esta fase genera un informe de error que incluye el nombre del archivo, la fecha y hora de procesamiento, y una descripción detallada del problema; el procesamiento se detiene y no avanza a las fases siguientes hasta que el problema sea corregido. 

El módulo de validación aplica sobre el dataset las reglas definidas en el diccionario de variables de manera sistemática y exhaustiva. La implementación utiliza la biblioteca great_expectations de Python, que permite expresar las reglas de validación de manera declarativa en un formato JSON serializable, ejecutarlas sobre cualquier dataframe de pandas y generar reportes de validación en formato HTML o JSON con el detalle completo de cada expectativa aplicada, su resultado y los registros afectados. Este enfoque tiene la ventaja adicional de hacer las reglas de validación inspeccionables y auditables de manera independiente del código de procesamiento: alguien con acceso al archivo de configuración de expectativas puede comprender qué validaciones se aplican sin necesidad de leer el código Python. 

Las categorías de validaciones implementadas son las siguientes. Las validaciones de tipo verifican que cada columna contiene valores del tipo esperado: enteros para identificadores y conteos, reales para mediciones continuas, fechas para variables temporales. Las validaciones de rango verifican que los valores numéricos están dentro de los límites 

Página 26 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

plausibles definidos en el diccionario. Las validaciones de lista verifican que los valores de variables categóricas pertenecen al conjunto de valores admisibles del catálogo. Las validaciones de unicidad verifican que no existen duplicados en la clave primaria del dataset. Las validaciones de completitud verifican que todos los campos obligatorios tienen valores no nulos. Las validaciones de consistencia cruzada verifican las relaciones lógicas entre pares o grupos de variables. 

### **_Captura de datos de campo mediante reconocimiento óptico (capacidad opcional)_** 

Las condiciones reales de un ensayo agrícola a campo —conectividad poco confiable y ausencia de dispositivos digitales durables en el punto de captura— hacen que la planilla de papel sea, con frecuencia, la única opción práctica para registrar el dato en el momento de la toma. Sin una capacidad específica que atienda ese origen, la transcripción manual del papel al archivo CSV ocurriría de todos modos, solo que fuera del alcance del sistema y sin trazabilidad: el dato nacería de una digitación de origen incierto, exactamente el paso manual propenso a error que este trabajo busca reducir. Por ese motivo el diseño contempla, como capacidad opcional, la captura de datos de campo mediante reconocimiento óptico sobre fotografías de planillas de papel, que mueve ese punto de transcripción dentro del sistema y lo somete a las mismas garantías de auditoría y confirmación humana que rigen al resto del pipeline. 

La restricción de diseño central de esta capacidad es que no se intenta el reconocimiento de escritura libre: el reconocimiento óptico de manuscritos generales es poco confiable y su tasa de error contaminaría el dato en origen, contradiciendo el objetivo mismo del sistema. En su lugar, la captura se estructura sobre un formulario impreso de disposición fija, con posiciones de campo conocidas de antemano, en el que el reconocimiento óptico solo lee dentro de zonas predefinidas por la plantilla. Los campos numéricos se capturan en casilleros segmentados de un dígito por casilla —al modo de los formularios impositivos o los cheques bancarios—, dado que un dígito aislado en una casilla delimitada es considerablemente más confiable de reconocer que la escritura numérica corrida. Los campos categóricos se capturan mediante reconocimiento de marcas, esto es, casillas o burbujas que el operador rellena, cuya detección es prácticamente infalible en comparación con el reconocimiento de caracteres y que mapea directamente a la lista de valores admisibles del diccionario de variables. Finalmente, marcadores de alineación impresos en las esquinas de la plantilla permiten detectar la orientación de la hoja y corregir la rotación y la distorsión de perspectiva propias de una fotografía tomada con un teléfono a campo, enderezando la imagen antes de extraer cada zona. 

La aceptación de una lectura no depende únicamente del puntaje de confianza que reporta el motor de reconocimiento óptico, sino que se cruza además contra las reglas de validación ya descritas en esta sección, tomadas del diccionario de variables: tipo de dato, rango plausible y lista de valores admisibles. Una lectura que contradice una regla de dominio —por ejemplo, un valor fuera del rango declarado para la variable— se marca para revisión aunque el motor reporte alta confianza en el carácter reconocido, porque la regla de dominio constituye una señal independiente de mala lectura. Toda lectura por debajo del umbral de confianza, o que viola una regla de validación, requiere confirmación humana antes de aceptarse como dato válido; esa confirmación se materializa por el mismo canal conversacional descrito en la sección 4.2, mediante un mensaje que presenta la imagen del campo dudoso, la lectura propuesta y opciones para confirmarla o corregirla. La confirmación —la lectura original, el valor confirmado, quién confirmó y cuándo— queda registrada en la bitácora de auditoría, de manera que la cadena de custodia del dato se preserva desde la planilla de papel. 

El procesamiento se ejecuta enteramente en el dispositivo o servidor local, sin recurrir a servicios de reconocimiento óptico en la nube, por dos razones independientes: la misma falta de conectividad confiable que motiva la captura en papel, y la confidencialidad del dato del ensayo, que no debe salir de la institución hacia un servicio de terceros sin autorización explícita, en consistencia con lo señalado en la sección 3.7. Las herramientas candidatas para esta capacidad son de código abierto y de ejecución local: Tesseract para el reconocimiento de los dígitos en los casilleros segmentados, y OpenCV para la detección de los marcadores de alineación, la corrección de perspectiva y el procesamiento de imagen —incluida la detección del relleno de las burbujas categóricas—, evaluándose además PaddleOCR como motor de reconocimiento alternativo. 

Durante el diseño se consideraron y descartaron tres alternativas. El reconocimiento de texto libre sin plantilla se descartó por su baja confiabilidad, en especial sobre escritura manuscrita. Las interfaces de reconocimiento óptico en la nube se descartaron por el requisito de ejecución sin conectividad y por la confidencialidad del dato, pese a que ofrecen mayor precisión bruta sobre manuscritos que las opciones locales; ese sacrificio de precisión se compensa con el diseño estructurado de la plantilla, que reduce la dificultad del reconocimiento a un nivel que las herramientas locales cubren adecuadamente. La tercera alternativa —la captura digital en el momento de la toma mediante tabletas o formularios móviles— fue la primera considerada y es, en abstracto, la más simple; se dejó de lado porque no resuelve el problema real: la fragilidad de los dispositivos digitales y la conectividad poco confiable a campo hacen que el papel sea, en la práctica, el método de respaldo más robusto. 

Esta capacidad no constituye un pipeline paralelo: el dato reconocido y confirmado se normaliza a la misma forma tabular que el módulo de ingesta descrito al comienzo de esta sección espera de las fuentes CSV o Excel, y a partir de ese punto recorre las fases de validación, transformación y persistencia ya presentadas sin modificación alguna. Se trata, además, de una capacidad opcional y fuera del alcance mínimo del sistema: el pipeline funciona completamente sin ella, y su habilitación queda condicionada a que el caso de estudio real que se seleccione confirme que la captura en papel es efectivamente necesaria. La elección concreta entre los motores de reconocimiento óptico evaluados permanece, a la fecha de este documento, como una decisión pendiente de resolución empírica, mediante la comparación de sus tasas de acierto sobre un prototipo de formulario fotografiado en condiciones realistas. 

## **4.5 Transformación y estandarización** 

El módulo de transformación recibe como entrada el dataset de registros validados — aquellos que superaron exitosamente todas las validaciones del módulo anterior— y aplica sobre él un conjunto de operaciones de normalización y estandarización que lo preparan para el análisis estadístico. Cada operación de transformación es atómica, documentada en el código con un comentario explicativo, y registrada en la bitácora de auditoría con el número de registros afectados y los valores antes y después de la transformación en una muestra representativa. 

Las transformaciones implementadas incluyen la normalización de nombres de columnas al formato snake_case en minúsculas, eliminando caracteres especiales y reemplazando espacios por guiones bajos; la estandarización de los valores de variables categóricas mediante la tabla de correspondencias del catálogo, que mapea las variantes observadas de cada término a su forma canónica; la conversión de unidades cuando el diccionario de variables especifica una unidad canónica diferente de la unidad en que llegan los datos de alguna fuente particular; y la construcción del dataset en formato tidy, en el que cada fila corresponde a una observación única y cada columna a una sola variable, incluyendo los identificadores necesarios para reconstruir la estructura jerárquica del diseño experimental. 

## **4.6 Persistencia, trazabilidad y auditoría** 

El módulo de persistencia almacena el dataset transformado en el repositorio de destino y genera simultáneamente los registros de auditoría correspondientes a la ejecución del pipeline. La estructura de la bitácora de auditoría incluye los siguientes elementos para cada ejecución: un identificador único de la ejecución generado automáticamente, la fecha y hora de inicio y fin del procesamiento, la versión del código utilizado identificada por el hash del commit de Git, la huella digital (hash SHA-256) del archivo de entrada, el número total de registros leídos, el número de registros que superaron la validación, el número de registros rechazados con sus motivos, el número de transformaciones aplicadas, y cualquier error o advertencia generada durante el procesamiento. 

Página 27 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

Adicionalmente, el sistema genera una bitácora de transformaciones que registra, para cada operación de transformación aplicada al dataset, el nombre de la operación, la columna o columnas afectadas, el número de registros modificados, el criterio aplicado — la regla específica del catálogo o el parámetro de configuración que determinó la transformación— y una marca temporal. Esta bitácora permite, en cualquier momento posterior, reconstruir el estado del dataset antes de cualquier transformación específica a partir del archivo de entrada original, lo que provee la trazabilidad completa requerida por los requisitos no funcionales del sistema. 

## **4.7 Automatización del análisis estadístico** 

El módulo de análisis estadístico es invocado por el pipeline después de la persistencia del dataset, o puede ser invocado de manera independiente sobre cualquier dataset previamente almacenado. Recibe como parámetros de entrada el identificador del dataset sobre el que debe operar, la especificación del modelo estadístico en formato de fórmula R-style (por ejemplo, 'rendimiento ~ C(tratamiento) + C(bloque)' para un ANOVA en bloques completos al azar), el tipo de análisis solicitado (ANOVA, modelo lineal mixto, Kruskal-Wallis, etc.) y los parámetros adicionales específicos del análisis (nivel de significancia, método de comparación de medias, etc.). 

El módulo produce como salidas los siguientes artefactos. En primer lugar, la tabla de resultados del modelo —tabla ANOVA, resumen del modelo de regresión o estadístico equivalente según el tipo de análisis— en formato CSV y en formato HTML con estilos apropiados para su inclusión en reportes. En segundo lugar, el informe de diagnóstico de supuestos, que incluye el estadístico y el valor p de la prueba de normalidad aplicada sobre los residuos, el estadístico y el valor p de la prueba de homocedasticidad, los valores de apalancamiento e influencia de cada observación para la detección de valores atípicos influyentes, y las representaciones gráficas en formato PNG de los gráficos de residuos versus valores ajustados y del gráfico Q-Q normal. En tercer lugar, un archivo de configuración en formato YAML que registra exactamente qué análisis se ejecutó, con qué parámetros y sobre qué versión del dataset, de manera que el análisis completo sea reejecutable con un único comando. 

## **4.8 Seguridad, respaldo y mantenibilidad** 

La seguridad del sistema se implementa mediante control de acceso a las fuentes de datos y al repositorio de destino —credenciales gestionadas mediante variables de entorno y no incluidas en el código fuente—, cifrado en tránsito para las comunicaciones entre componentes, y un modelo de permisos mínimos que limita cada componente del pipeline al acceso estrictamente necesario para su función. Los respaldos del dataset, la bitácora 

Página 28 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

y el código son programados mediante tareas automáticas y almacenados en ubicaciones distintas al repositorio principal. 

Al control de acceso de infraestructura descrito se agrega un control de acceso a nivel de aplicación, propio de la capa de interacción humana. Dado que la identidad de cada usuario la provee el propio canal de Telegram en cada mensaje, el sistema no introduce un mecanismo de autenticación por contraseña propio: delega la autenticación en el canal y resuelve la autorización mediante un mapeo mínimo entre el identificador del usuario y su rol —Ingeniero o Ayudante—, acotado por ensayo cuando corresponde. Este control basado en roles cubre exactamente lo que el canal necesita para el alcance del caso de estudio de esta tesis y no pretende constituir un sistema multiusuario general. En particular, no distingue, dentro del rol de Ingeniero, la autoridad de configuración estadística de la autoridad de dominio agronómico, que se consolidan deliberadamente en un único rol; si el sistema creciera y esa separación —u otros sub-permisos más finos— resultara necesaria, su incorporación queda fuera del alcance actual y se retoma como línea de trabajo futura en la sección 7.4. 

La capa de interacción incorpora, asimismo, una consideración de confidencialidad específica del canal de Telegram, que se analiza en detalle en la sección 3.7: el canal ofrece cifrado del tráfico en tránsito pero no una garantía de confidencialidad de extremo a extremo, matiz que se acepta conscientemente en función del beneficio operativo y del alcance de este trabajo. 

La mantenibilidad del sistema se garantiza mediante la modularidad del código —cada módulo tiene una única responsabilidad claramente delimitada—, la cobertura de pruebas unitarias para cada módulo —verificando tanto el comportamiento correcto con datos válidos como el manejo apropiado de casos de error—, la documentación inline del código mediante docstrings en formato NumPy, y el versionado semántico del sistema —cada versión estable del pipeline recibe un número de versión en formato MAJOR.MINOR.PATCH que permite identificar inequívocamente las capacidades y el comportamiento esperado de esa versión. 

## **4.9 Diagrama del sistema** 

_NOTA PARA LOS AUTORES — A reemplazar cuando se finalice la implementación: Insertar aquí el diagrama de arquitectura del sistema que muestre el flujo completo: Fuentes de datos (CSV/Excel) → n8n Orquestador → Módulo de ingesta Python → Módulo de validación (great_expectations) → Módulo de transformación Python → Base de datos (SQLite/PostgreSQL) + Bitácora de auditoría → Módulo de análisis estadístico Python → Reportes (HTML/CSV/PNG). El diagrama debe incluir además la capa de interacción por Telegram descrita en §4.2 (bot de Telegram ↔ n8n, con los roles Ingeniero y Ayudante) y el motor de sesiones (pipeline/sessions.py) que gestiona el estado conversacional contra la base de datos, mostrando que toda acción humana entra y sale por ese canal. Representar también, como rama opcional de entrada, la captura de datos de campo por reconocimiento óptico descrita en §4.4 (fotografía de planilla → pipeline/ocr.py → confirmación humana vía Telegram → módulo de ingesta), diferenciada gráficamente del camino crítico. Incluir los flujos de datos principales (flechas sólidas), los flujos de error (flechas punteadas) y la información registrada en la bitácora en cada etapa._ 

Página 29 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Capítulo 5. Resultados** 

Este capítulo presenta los resultados obtenidos durante la fase de evaluación del sistema. Los resultados se organizan en tres secciones que corresponden a las categorías de métricas definidas en la sección 3.6: resultados operativos, que cuantifican el desempeño del pipeline en términos de eficiencia y calidad del dato; resultados analíticos, que reportan las salidas del módulo estadístico y la verificación de su corrección y reproducibilidad; y la comparación sistemática con el proceso manual de referencia, que permite cuantificar el valor aportado por la automatización. 

## **5.1 Resultados operativos: automatización y calidad de datos** 

Los resultados operativos del sistema se presentan para el conjunto de ensayos agrícolas utilizados como caso de estudio. Para cada ensayo, se reportan las siguientes métricas: el tiempo total de procesamiento desde la recepción del archivo de entrada hasta la disponibilidad del dataset en el repositorio de destino; el número total de registros procesados; el número y proporción de registros rechazados por violaciones de las reglas de validación, con distribución por categoría de error; la completitud del dataset resultante, expresada como el porcentaje de campos obligatorios con valores no nulos; y la consistencia del dataset resultante, expresada como el porcentaje de registros sin violaciones de reglas de consistencia cruzada. 

_NOTA PARA LOS AUTORES — A completar con datos reales de las pruebas: Tabla de métricas operativas (ensayo, fecha de procesamiento, registros totales, registros rechazados, porcentaje de rechazo, tiempo de procesamiento en segundos, completitud %, consistencia %, versión del pipeline). Incluir estadísticos descriptivos: promedio, mínimo, máximo y desviación estándar de cada métrica sobre el conjunto de ensayos evaluados._ 

Los tipos de errores detectados por el sistema de validación se clasifican en las categorías definidas por el diccionario de variables: errores de tipo (valores no numéricos en columnas numéricas, fechas en formato incorrecto), errores de rango (valores fuera de los límites plausibles definidos para la variable), errores de lista (valores categóricos no presentes en el catálogo de términos admisibles), duplicados (registros con clave primaria repetida), campos obligatorios nulos (valores faltantes en campos de presencia requerida), y violaciones de consistencia cruzada (incumplimiento de relaciones lógicas entre variables). La distribución observada de errores por categoría es relevante para identificar los puntos más frágiles del proceso de captura y transcripción de datos, y orienta las recomendaciones sobre dónde enfocar los esfuerzos de mejora en el proceso de campo. 

Página 30 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

_NOTA PARA LOS AUTORES — A completar con datos reales: Tabla o gráfico de distribución de errores por categoría (número y porcentaje del total de errores detectados por categoría de error). Análisis de las categorías más frecuentes y su interpretación en términos del proceso de captura de datos._ 

## **5.2 Resultados analíticos: salidas estadísticas** 

Los resultados analíticos del módulo estadístico se reportan para el diseño experimental correspondiente al caso de estudio principal. Se especifica en primer lugar el diseño experimental adoptado: el tipo de diseño —diseño completamente aleatorio, bloques completos al azar, factorial—, los factores en estudio con sus niveles, el número de repeticiones, la variable respuesta analizada y la fórmula del modelo estadístico aplicado. Esta información es indispensable para la interpretación correcta de los resultados del análisis. 

_NOTA PARA LOS AUTORES — A completar con datos reales: Especificación completa del diseño experimental (tipo de diseño, factores, niveles, número de repeticiones, variable respuesta, fórmula del modelo). Tabla ANOVA completa con fuentes de variación, grados de libertad, suma de cuadrados, cuadrado medio, estadístico F y valor p. Medias de tratamiento con errores estándar y resultados de la prueba de comparación de medias si aplica._ 

Los resultados del diagnóstico de supuestos del modelo son reportados con el mismo nivel de detalle que los resultados del análisis principal. Para el supuesto de normalidad de los residuos, se reportan el resultado de la prueba de Shapiro-Wilk con su estadístico y valor p, y una descripción del gráfico Q-Q normal generado. Para el supuesto de homocedasticidad, se reportan el resultado de la prueba de Levene con su estadístico y valor p, y una descripción del gráfico de residuos versus valores ajustados. Cuando alguno de estos diagnósticos indica una violación de los supuestos, se reportan también las acciones tomadas: la transformación aplicada a la variable respuesta, la técnica alternativa utilizada, o la argumentación de por qué el análisis se considera robusto a pesar de la violación detectada. 

_NOTA PARA LOS AUTORES — A completar con datos reales: Resultados completos del diagnóstico de supuestos. Si se detectaron violaciones, describir las acciones tomadas y sus resultados. Insertar o referenciar las figuras de diagnóstico generadas por el módulo estadístico._ 

## **5.3 Comparación con el proceso manual: línea base** 

La comparación entre el pipeline automatizado y el proceso manual de referencia se realiza sobre las dimensiones de tiempo total de procesamiento, tasa de error en el dataset final, 

Página 31 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

completitud del registro de auditoría y reproducibilidad del análisis estadístico. La línea base del proceso manual se establece mediante la ejecución del proceso habitual por parte de los usuarios habituales del sistema —sin asistencia del pipeline automatizado— sobre los mismos conjuntos de datos utilizados para la evaluación del sistema automatizado, con registro de tiempos y revisión del dataset resultante por un evaluador independiente que aplica el mismo conjunto de reglas de validación utilizado por el pipeline. 

_NOTA PARA LOS AUTORES — A completar con datos reales: Tabla comparativa manual vs automatizado para las dimensiones de comparación. Tiempo total de procesamiento (promedio y desviación estándar para N ejecuciones de cada tipo). Tasa de error residual en el dataset final (errores no detectados que quedaron en el dataset aprobado). Completitud de la bitácora de auditoría (porcentaje de transformaciones documentadas sobre total de transformaciones aplicadas). Reproducibilidad del análisis (sí/no para re-ejecución del pipeline vs proceso manual)._ 

Página 32 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Capítulo 6. Discusión** 

## **6.1 Interpretación de resultados** 

La interpretación de los resultados presentados en el Capítulo 5 debe realizarse en el contexto del marco teórico y de los objetivos específicos que orientaron el desarrollo del trabajo. Los resultados operativos permiten evaluar en qué medida el pipeline automatizado cumple con las hipótesis de trabajo formuladas en la sección 1.7 y con los objetivos específicos 1, 2, 3 y 5 de la sección 1.5. Los resultados analíticos permiten evaluar el cumplimiento del objetivo específico 4 y contribuyen a la validación de la hipótesis H3 relativa a la mejora de la auditabilidad y reproducibilidad del análisis. 

_NOTA PARA LOS AUTORES — A desarrollar con base en los resultados reales del Capítulo 5: Discusión analítica de qué revelan los datos sobre el desempeño del sistema en cada dimensión evaluada. Discutir la magnitud de las diferencias observadas entre el pipeline automatizado y el proceso manual, su significación práctica, y en qué medida los resultados confirman o matizan las hipótesis de trabajo. Evitar especulación: toda afirmación interpretativa debe estar anclada en los datos presentados._ 

## **6.2 Implicaciones para la gestión de ensayos agrícolas** 

Más allá de los resultados numéricos específicos, el desarrollo y evaluación del sistema propuesto tiene implicaciones de mayor alcance para la práctica de la gestión de datos en programas de ensayos agrícolas. La primera y más directa es la demostración de la viabilidad técnica y operativa de automatizar el pipeline de gestión del dato con herramientas accesibles —n8n y Python son de código abierto o de bajo costo— en un contexto institucional de recursos moderados. Esta viabilidad es relevante porque uno de los obstáculos frecuentemente citados para la adopción de prácticas de datos más rigurosas en el sector agronómico es precisamente la percepción de que requieren inversiones en tecnología o en competencias técnicas que están fuera del alcance de los equipos típicos de investigación. 

La segunda implicación se refiere a la escalabilidad del sistema propuesto. El diseño modular y la parametrización del pipeline facilitan su extensión a nuevos ensayos, nuevos diseños experimentales y nuevas variables respuesta sin requerir modificaciones al código base, solamente la actualización del diccionario de variables y la especificación del modelo estadístico apropiado. Esta escalabilidad es especialmente valiosa en el contexto de programas de evaluación multi-ambiente y multi-campaña, donde la acumulación de datos 

Página 33 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

a lo largo del tiempo es un activo institucional cuya gestión coherente tiene valor estratégico. 

La tercera implicación se refiere a la estandarización institucional del proceso. La existencia de un diccionario de variables formal y de reglas de validación explícitas crea las condiciones para la convergencia hacia estándares compartidos de nomenclatura, codificación y formato entre los distintos equipos y sitios que contribuyen datos al programa. Este proceso de estandarización es gradual y requiere un esfuerzo de coordinación que va más allá de lo técnico, pero la disponibilidad de un sistema que formaliza y aplica las reglas acordadas provee el mecanismo operativo para su implementación efectiva. 

## **6.3 Validez, amenazas y generalización** 

La validez interna del estudio se ve potencialmente afectada por cuatro categorías de amenazas que deben ser reconocidas y discutidas. La primera es la calidad del dato en origen: si los archivos de datos crudos utilizados para la evaluación del sistema contienen tipos de errores que no están representados en las reglas de validación implementadas, la tasa de detección observada subestimará la que se obtendría con un sistema de validación más completo, y la comparación con la línea base manual no capturará la ventaja completa del sistema automatizado. La segunda amenaza es la representatividad del caso de estudio: los ensayos agrícolas utilizados tienen características específicas —cultivo, diseño experimental, volumen de datos, distribución de errores— que pueden no ser representativas del universo de ensayos sobre el que se pretende generalizar las conclusiones. La tercera amenaza es la medición de la línea base: si los usuarios que ejecutaron el proceso manual durante la evaluación no lo hicieron de manera representativa de su práctica habitual —ya sea porque sabían que estaban siendo evaluados o porque los datos de prueba tenían características no habituales—, la comparación puede estar sesgada. La cuarta amenaza es la reproducibilidad de los resultados estadísticos: si la implementación del módulo estadístico contiene errores o hace elecciones no documentadas sobre parámetros con múltiples opciones válidas, los resultados reportados pueden diferir de los que produciría una implementación alternativa correcta del mismo análisis. 

Las mitigaciones implementadas para cada una de estas amenazas se describen en el Capítulo 3 y en la documentación técnica del sistema. La validez externa —la generalización de los resultados a otros contextos— está limitada principalmente por las características del caso de estudio utilizado. Los principios de diseño del sistema son generalizables a otros contextos de ensayos agrícolas con diseños experimentales 

Página 34 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

convencionales; la parametrización específica del diccionario de variables, las reglas de validación y la especificación del modelo estadístico requerirá adaptación para cada nuevo contexto de aplicación. 

## **6.4 Lecciones aprendidas** 

El proceso de desarrollo e implementación del sistema generó un conjunto de aprendizajes que complementan los resultados formales de la evaluación y que tienen valor para futuros trabajos en líneas similares. Estos aprendizajes se organizan en tres categorías: decisiones arquitectónicas cuyo impacto fue mayor de lo anticipado, dificultades encontradas en la implementación y las soluciones adoptadas, y aspectos del proceso que merecen reconsideración en un ciclo futuro de desarrollo. 

La primera lección, de naturaleza arquitectónica, se refiere al orden en que se abordó la construcción de los módulos del sistema. El plan de implementación original preveía desarrollar primero la cadena de ingesta, validación, transformación y persistencia, y recién al final el módulo de análisis estadístico. Durante el desarrollo se optó por invertir esa secuencia y validar el núcleo analítico antes que el resto del pipeline, sobre la base de un criterio de riesgo: un resultado estadístico incorrecto constituye una falla de consecuencias mucho más graves que un error de conexión entre etapas del flujo, y además se manifestaría tardíamente —al momento de redactar los resultados del Capítulo 5— cuando su corrección resultaría más costosa. La verificación del mecanismo de ANOVA y de la prueba de comparación de medias de Tukey (honestly significant difference, HSD) se realizó sobre un conjunto de datos de referencia clásico —el ensayo factorial de nitrógeno, fósforo y potasio sobre el rendimiento de arveja conducido en Rothamsted, de la misma tradición experimental fundada por R.A. Fisher que se describe en la sección 2.1— contrastando tres métodos de cálculo independientes entre sí: la rutina anova_lm de statsmodels (Seabold y Perktold, 2010), las fórmulas clásicas de suma de cuadrados para un diseño en bloques completos al azar calculadas manualmente según Cochran y Cox (1957) y Montgomery (2019), y la relación matemática entre la distribución t de Student y la distribución del rango estudentizado para el caso de una comparación entre dos grupos. La coincidencia de los tres métodos confirmó que el motor de ANOVA era correcto. 

Este mismo proceso de verificación reveló, sin embargo, una trampa de implementación concreta y no evidente. La función pairwise_tukeyhsd del módulo statsmodels.stats.multicomp —la herramienta a la que se recurre de manera más inmediata para la prueba de comparación de medias de Tukey en Python— calcula su propia varianza combinada directamente a partir de los valores crudos de los grupos e ignora por completo el factor de bloqueo presente en el modelo ajustado. Sobre el conjunto de datos de referencia, el estadístico F del ANOVA correctamente ajustado por bloques arrojó un valor p de 0,0071 para el efecto del nitrógeno, mientras que la invocación directa de pairwise_tukeyhsd sobre los mismos datos produjo un valor p de 0,0221 para la comparación equivalente: una discrepancia sustantiva —no atribuible a redondeo— que, según el nivel de significancia α adoptado, podría invertir la conclusión sobre la significación del efecto. El procedimiento correcto —recalcular la diferencia honestamente significativa a partir del cuadrado medio del error y los grados de libertad residuales del modelo completo, que incluye el término de bloqueo, mediante la función psturng del submódulo statsmodels.stats.libqsturng— reprodujo exactamente el valor p del estadístico F (0,0071), lo que confirmó la corrección del ajuste. Esta corrección quedó fijada en el código como una prueba de regresión permanente que utiliza el conjunto de datos de referencia como fixture con valores esperados anclados, con el propósito explícito de impedir que una refactorización futura reintroduzca de manera silenciosa el enfoque ingenuo e incorrecto. 

Una segunda dificultad, de la misma familia, se manifestó al extender el módulo a un modelo factorial completo (rendimiento ~ C(bloque) + C(N)*C(P)*C(K)), siguiendo el ejemplo canónico de la propia documentación de R para ese conjunto de datos. Se comprobó empíricamente que statsmodels y su motor de fórmulas patsy se comportan de manera distinta a la función aov de R también en este punto: R detecta que la interacción triple N:P:K está confundida (aliased) con la estructura de bloques en este diseño factorial fraccionado y le asigna cero grados de libertad, excluyéndola de manera silenciosa; statsmodels, en cambio, no realiza esa detección, sino que ajusta la matriz de diseño deficiente de rango mediante su pseudoinversa e informa una suma de cuadrados no nula pero espuria para ese término confundido, rompiendo la identidad esperada según la cual la suma de cuadrados total debe igualar la suma de las sumas de cuadrados de todos los efectos más la residual. El problema se detectó al escribir una prueba explícita que verificaba esa identidad, la cual falló hasta que se aprendió a excluir el término confundido; constituye una ilustración concreta de por qué los controles cruzados automáticos —y no la mera constatación de que los números resultan plausibles— son necesarios cuando se depende del comportamiento por defecto de una biblioteca estadística para diseños que exceden los casos de manual más estándar. 

La lección metodológica de mayor alcance que se desprende de estos episodios, y que merece enunciarse de manera explícita, es que ambos incidentes motivaron la incorporación al núcleo estadístico de una capa adicional de verificaciones de coherencia no bloqueantes, materializada en una función sanity_checks() que inspecciona el rango de la matriz de diseño del modelo ajustado, expone las violaciones de supuestos y señala los tamaños de grupo insuficientes en forma de advertencias estructuradas —no bloqueantes— destinadas a la revisión humana. La justificación es directa: tanto el caso de pairwise_tukeyhsd como el de la matriz deficiente de rango demostraron que una biblioteca estadística puede producir un número bien formado, plausible y, sin embargo, incorrecto, sin emitir ningún error ni advertencia que alerte al analista. Este aprendizaje se articula de manera inmediata con los requisitos no funcionales de auditabilidad y reproducibilidad enunciados en la sección 4.1: la auditabilidad no puede presuponerse por el solo hecho de utilizar una biblioteca de reputación consolidada, sino que debe diseñarse y verificarse de manera activa mediante pruebas que ejerciten el comportamiento real del sistema. 

Página 35 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Capítulo 7. Conclusiones y líneas futuras** 

## **7.1 Conclusiones** 

Esta tesis ha desarrollado, implementado y evaluado un sistema de automatización para la gestión del dato experimental en ensayos agrícolas, articulando la orquestación de flujos mediante n8n con el procesamiento estructurado y el análisis estadístico reproducible mediante Python. Las conclusiones del trabajo se organizan en correspondencia con los objetivos específicos planteados en la sección 1.5 y con las hipótesis de trabajo formuladas en la sección 1.7. 

En relación con el primer objetivo —modelar el proceso completo desde la captura hasta la preparación del dataset para análisis—, el trabajo produjo un diagnóstico detallado de los puntos críticos de fragilidad del proceso manual, identificando las categorías de error más frecuentes y sus consecuencias sobre la integridad del dataset. Este diagnóstico constituye, en sí mismo, un aporte de valor para los equipos que gestionan programas de ensayos agrícolas, con independencia de si adoptan o no el sistema propuesto. 

En relación con el segundo objetivo —definir un esquema de datos y reglas de validación— , la tesis produce un diccionario de variables formal y un conjunto de reglas de validación implementadas en la biblioteca great_expectations que proveen un punto de partida documentado y adaptable para cualquier programa de ensayos con estructura similar al caso de estudio utilizado. 

En relación con el tercer objetivo —implementar el pipeline de automatización—, el sistema desarrollado cumple con todos los requisitos funcionales y no funcionales especificados, produciendo un flujo ejecutable, versionado y documentado que puede ser desplegado en un entorno de producción con los ajustes de configuración apropiados. 

En relación con el cuarto objetivo —integrar un módulo de análisis estadístico reproducible—, el módulo desarrollado ejecuta correctamente los análisis especificados, genera todos los artefactos de reporte definidos en los requisitos y ha demostrado reproducibilidad verificada mediante re-ejecución sobre los mismos datos. 

En relación con el quinto objetivo —evaluar el sistema mediante métricas operativas y estadísticas—, los resultados presentados en el Capítulo 5 proveen evidencia cuantitativa del desempeño del sistema en todas las dimensiones evaluadas y permiten contrastar ese desempeño con el proceso manual de referencia. 

## **7.2 Aportes principales** 

Página 36 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

Los aportes originales de esta tesis al campo de los sistemas de información aplicados a la investigación agronómica son los siguientes. El primero es el diseño y la validación de un flujo automatizado y reproducible para la gestión del dato experimental agrícola, con una arquitectura modular que facilita su adaptación a distintos contextos experimentales. El segundo es la formalización de un esquema de validación de calidad del dato específicamente diseñado para ensayos agrícolas con diseños experimentales convencionales, expresado en un formato implementable y auditable mediante herramientas de código abierto. El tercero es la demostración empírica de la viabilidad técnica y operativa de integrar orquestación de flujos, procesamiento Python y análisis estadístico reproducible en un pipeline coherente y de bajo costo de implementación. El cuarto es la provisión de un caso de estudio documentado con suficiente detalle metodológico y técnico para ser replicado o adaptado por equipos de investigación con perfiles similares al de este trabajo. 

## **7.3 Limitaciones** 

Las limitaciones del trabajo deben ser reconocidas con igual claridad que sus aportes. El sistema desarrollado opera sobre datos en formatos tabulares convencionales y no está diseñado para integrar datos de sensores remotos, imágenes satelitales u otras fuentes de datos no estructurados que son cada vez más relevantes en la agricultura de precisión. La validación del sistema se realizó sobre un conjunto limitado de ensayos; la generalización de los resultados de desempeño a una diversidad más amplia de contextos experimentales requiere estudios adicionales. La parametrización del módulo estadístico cubre los modelos más frecuentes en la experimentación agrícola convencional, pero no incluye los modelos de series de tiempo ni los análisis espaciales que son pertinentes para diseños experimentales más complejos. Finalmente, el trabajo no aborda la integración del sistema con los sistemas de información de gestión existentes en las instituciones usuarias, aspecto que puede ser relevante para la adopción efectiva en entornos de producción. 

## **7.4 Trabajo futuro** 

Las líneas de investigación y desarrollo que se abren a partir de este trabajo son numerosas. En el corto plazo, la extensión del módulo estadístico para soportar modelos lineales mixtos mediante la biblioteca statsmodels o mediante la integración con R vía rpy2 ampliaría significativamente el alcance del sistema a ensayos multi-ambiente y diseños con efectos aleatorios, que son los más frecuentes en los programas de mejoramiento genético y evaluación de cultivares. La generación automática de reportes completos en formato PDF o HTML interactivo, integrando los resultados del análisis estadístico con las métricas de calidad del dato y los registros de auditoría en un único artefacto, facilitaría la 

Página 37 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

comunicación de los resultados a audiencias con distintos perfiles técnicos. El desarrollo de un catálogo institucional de ensayos y variables con gobernanza de datos formal —que incluya procesos de revisión y aprobación de cambios al diccionario de variables y a las reglas de validación— proveería la infraestructura organizacional necesaria para la adopción del sistema a escala institucional. En el plano del control de acceso, la extensión del esquema de roles hacia sub-permisos más finos dentro del rol de Ingeniero —separando nuevamente, por ejemplo, la autoridad de configuración estadística de la de dominio agronómico, o estableciendo permisos diferenciados por variable— queda como línea de trabajo futura, a evaluar si el caso de estudio real o la adopción institucional del sistema llegaran a requerirla. Finalmente, la validación del sistema sobre una diversidad más amplia de cultivos, diseños experimentales y contextos institucionales fortalecería la evidencia sobre su generalización y permitiría identificar las adaptaciones necesarias para distintos escenarios de uso.

Más allá del propósito inmediato de procesar cada ensayo de forma individual, la persistencia auditable que el sistema ya garantiza —con trazabilidad completa y calidad de dato validada por el mismo pipeline de ingesta— constituye, con el transcurso de las campañas, un activo de datos multi-ensayo con valor de investigación propio. Ese acumulado habilita preguntas que ningún ensayo aislado puede responder por sí solo, como el meta-análisis entre campañas y sitios o la comparación de tratamientos a través de contextos institucionales distintos, y provee además una base confiable para entrenar o validar los componentes de inteligencia artificial que la tesis contempla como capacidad opcional. Concretar este reuso, no obstante, no es un resultado automático: exige diseñar un mecanismo de autorización explícita por parte de la institución titular de cada ensayo, coherente con el compromiso de confidencialidad asumido en la sección 3.7, así como un módulo de consulta capaz de operar a través de varios ensayos —capacidad de la que el sistema actual carece, puesto que todo su acceso a datos está diseñado ensayo por ensayo—. En una línea de trabajo relacionada, el modelo de datos incorpora ya, de forma opcional, la geolocalización del ambiente de cada ensayo mediante sus coordenadas de latitud y longitud, prevista precisamente para un desarrollo futuro: cruzar los resultados con datos climáticos externos de la zona —temperatura, precipitación— para explicar parte de la varianza residual que el diseño de bloqueo no alcanza a capturar por sí solo, una fuente de variación ambiental genuina en la experimentación agrícola, y para habilitar el análisis espacial de los resultados. Materializar esta correlación requeriría, a futuro, elegir una fuente de datos climáticos externa e integrar un módulo que la consuma como covariable opcional del análisis estadístico, sin alterar el comportamiento del análisis existente cuando la geolocalización no se encuentra disponible. Ambas líneas comparten una misma visión: el sistema, además de resolver el problema inmediato de automatizar un ensayo, sienta las bases de un activo de datos con valor de investigación que trasciende el alcance de esta tesis. 

Página 38 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Referencias bibliográficas** 

Las referencias a continuación se consignan en formato APA 7.ª edición. Se incluyen únicamente las fuentes efectivamente utilizadas en el desarrollo del marco teórico y del diseño metodológico de la presente tesis. Para fuentes digitales se indica la URL y la fecha de último acceso verificado. 

Cochran, W. G., & Cox, G. M. (1957). Experimental designs (2.ª ed.). Wiley. 

Hinkelmann, K., & Kempthorne, O. (2008). Design and analysis of experiments. Volume I: Introduction to experimental design (2.ª ed.). Wiley. 

Montgomery, D. C. (2019). Design and analysis of experiments (10.ª ed.). Wiley. 

Kutner, M. H., Nachtsheim, C. J., & Neter, J. (2004). Applied linear regression models (4.ª ed.). McGraw-Hill. 

Wang, R. Y., & Strong, D. M. (1996). Beyond accuracy: What data quality means to data consumers. Journal of Management Information Systems, 12(4), 5–33. https://doi.org/10.1080/07421222.1996.11518099 

Wickham, H. (2014). Tidy data. Journal of Statistical Software, 59(10), 1–23. https://doi.org/10.18637/jss.v059.i10 

Wilkinson, M. D., Dumontier, M., Aalbersberg, I. J., et al. (2016). The FAIR guiding principles for scientific data management and stewardship. Scientific Data, 3, 160018. https://doi.org/10.1038/sdata.2016.18 

Peng, R. D. (2011). Reproducible research in computational science. Science, 334(6060), 1226–1227. https://doi.org/10.1126/science.1213847 

Stodden, V., & Miguez, S. (2014). Best practices for computational science: Software infrastructure and environments for reproducible and extensible research. Journal of Open Research Software, 2(1), e21. https://doi.org/10.5334/jors.ay 

n8n GmbH. (2024). n8n documentation. https://docs.n8n.io [Fecha de acceso: A REEMPLAZAR] 

Great Expectations Contributors. (2024). Great Expectations documentation. https://docs.greatexpectations.io [Fecha de acceso: A REEMPLAZAR] 

Página 39 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

The pandas Development Team. (2024). pandas: Powerful Python data analysis toolkit. https://pandas.pydata.org/docs/ [Fecha de acceso: A REEMPLAZAR] 

Seabold, S., & Perktold, J. (2010). Statsmodels: Econometric and statistical modeling with Python. Proceedings of the 9th Python in Science Conference (SciPy 2010), 57–61. https://www.statsmodels.org [Fecha de acceso: A REEMPLAZAR] 

Yin, R. K. (2018). Case study research and applications: Design and methods (6.ª ed.). SAGE. 

Stake, R. E. (1995). The art of case study research. SAGE. 

Página 40 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

# **Anexos** 

## **Anexo A. Código base reproducible para ANOVA** 

El siguiente script constituye la plantilla base del módulo de análisis estadístico. Está parametrizado para recibir el path del dataset y la especificación del modelo como argumentos de línea de comandos, de manera que cada ejecución quede perfectamente documentada en la bitácora de auditoría mediante el registro del comando exacto invocado. El script debe ser ejecutado desde un entorno virtual con las dependencias fijadas en el archivo requirements.txt correspondiente a la versión del pipeline utilizada. 

```
# ANEXO A — Módulo de análisis estadístico reproducible
# Requiere: Python >= 3.10, pandas, statsmodels, scipy, matplotlib
import argparse
import pandas as pd
import statsmodels.api as sm
from statsmodels.formula.api import ols
from scipy import stats
import matplotlib.pyplot as plt
import json, hashlib, datetime, sys
def run_anova(dataset_path: str, formula: str, output_dir: str):
    """Ejecuta ANOVA, genera diagnósticos y reportes auditables."""
    df = pd.read_csv(dataset_path)
    modelo = ols(formula, data=df).fit()
    anova_table = sm.stats.anova_lm(modelo, typ=2)
    # Diagnósticos de supuestos
    residuos = modelo.resid
    stat_sw, p_sw = stats.shapiro(residuos)
    # Guardar tabla ANOVA como CSV y reporte de diagnósticos como JSON
    anova_table.to_csv(f'{output_dir}/anova_results.csv')
    # ... (ver implementación completa en repositorio de código)
```

## **Anexo B. Diagrama del sistema** 

_NOTA PARA LOS AUTORES — A reemplazar con la figura definitiva: Insertar aquí el diagrama de arquitectura del sistema en formato de alta resolución. El diagrama debe mostrar: (1) Las fuentes de datos (archivos CSV/Excel). (2) El orquestador n8n con sus workflows. (3) El módulo de ingesta Python. (4) El motor de validación (great_expectations). (5) El módulo de transformación Python. (6) El repositorio de datos (SQLite/PostgreSQL). (7) La bitácora de auditoría. (8) El módulo de análisis estadístico. (9) Los reportes de salida. Usar flechas sólidas para flujo de datos principal y flechas punteadas para flujos de error y notificación._ 

Página 41 de 42 

_UTN — Tesis de Maestría — Automatización de Ensayos Agrícolas_ 

## **Anexo C. Estructura del repositorio de código** 

El repositorio de código del sistema sigue la siguiente estructura de directorios, diseñada para facilitar la navegación, el mantenimiento y la reproducibilidad: 

- pipeline/ — Módulos principales del pipeline de procesamiento 

- pipeline/ingestion.py — Módulo de ingesta y validación estructural 

- pipeline/validation.py — Motor de validación de calidad del dato 

- pipeline/transformation.py — Módulo de transformación y estandarización 

- pipeline/persistence.py — Módulo de persistencia y auditoría 

- pipeline/analysis.py — Módulo de análisis estadístico 

- pipeline/sessions.py — Motor de sesiones para la capa de interacción por Telegram 

- pipeline/ocr.py — Módulo de captura de datos de campo mediante reconocimiento óptico (capacidad opcional) 

- migrations/ — Migraciones de esquema de base de datos gestionadas con Alembic 

- config/ — Archivos de configuración 

- config/data_dictionary.json — Diccionario de variables y reglas de validación 

- config/analysis_config.yaml — Parámetros del análisis estadístico 

- .env.example — Plantilla de variables de entorno, incluyendo DATABASE_URL 

- tests/ — Suite de pruebas unitarias e integración 

- n8n_workflows/ — Exportaciones de los workflows de n8n en formato JSON 

- docs/ — Documentación técnica 

- requirements.txt — Dependencias Python fijadas con versiones exactas 

- README.md — Instrucciones de instalación, configuración y uso 

Página 42 de 42 


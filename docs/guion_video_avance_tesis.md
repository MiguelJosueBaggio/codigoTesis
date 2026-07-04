# Guion — Video de avance de estado de tesis

> Tesis de Maestría en Sistemas de Información — UTN Facultad Regional Mendoza
> "Automatización de cargas de datos y análisis estadístico en ensayos agrícolas — Diseño, implementación y validación de un flujo reproducible basado en n8n y Python"
> Relator: Nahuel Morales — Equipo de tesis: Miguel Baggio, Alejo Osorio, Ignacio Aguilar — Director: Mg. Alberto Cortez
>
> Guion completo para narrador único, palabra por palabra. Duración objetivo: 10 minutos.

---

## [0:00–0:45] Apertura e identificación

Buenos días. Mi nombre es Nahuel Morales y presento este trabajo en representación del equipo de tesis, integrado también por Miguel Baggio, Alejo Osorio e Ignacio Aguilar, bajo la dirección del Magíster Alberto Cortez. El trabajo se titula "Automatización de cargas de datos y análisis estadístico en ensayos agrícolas: diseño, implementación y validación de un flujo reproducible basado en n8n y Python". En los próximos diez minutos recorreremos el problema que motiva la tesis, la pregunta de investigación y los objetivos, el marco conceptual, la metodología adoptada, los resultados alcanzados hasta el momento y una discusión honesta de lo que resta por hacer.

---

## [0:45–2:00] Problema y motivación

La agricultura moderna convirtió al dato experimental en un recurso estratégico. Sobre los resultados de los ensayos de campo se sostienen las recomendaciones técnicas de variedades, fertilización, riego y manejo del cultivo. Y la calidad de esas recomendaciones no depende solo de un buen diseño experimental: depende, de manera igualmente crítica, de la integridad de los datos que alimentan el análisis.

El problema es que, en la práctica habitual de la mayoría de los programas de ensayos, la gestión del dato sigue siendo profundamente manual y frágil. Los datos se capturan en planillas de papel, se transcriben a hojas de cálculo y se manipulan mediante procedimientos improvisados que cambian según el criterio de cada analista. Cada uno de esos pasos manuales es una oportunidad para introducir un error: una cifra mal transcrita, una unidad confundida, un tratamiento mal codificado. Y como no queda registro formal de las transformaciones aplicadas, resulta prácticamente imposible reconstruir la historia del dato desde su origen hasta el resultado final.

Esto tiene una consecuencia directa sobre la ciencia: un análisis estadístico impecable, ejecutado sobre datos de mala calidad, produce conclusiones inválidas con el mismo rigor formal que tendría un análisis correcto. Ahí está la brecha que motiva nuestro trabajo. Las herramientas para automatizar, validar y reproducir estos procesos existen y son accesibles; lo que falta es integrarlas en un sistema coherente, documentado y adaptado a las particularidades del dato experimental agrícola.

---

## [2:00–3:00] Pregunta de investigación y objetivos

De ese diagnóstico surge nuestra pregunta de investigación central: ¿cómo diseñar e implementar un flujo automatizado, trazable y reproducible que integre la carga de datos de ensayos agrícolas, ejecute validaciones de calidad, garantice la trazabilidad de cada transformación y habilite un análisis estadístico consistente, reduciendo tiempos y errores respecto de un proceso manual de referencia?

El objetivo general que se desprende de esa pregunta es diseñar, implementar y validar un sistema reproducible que automatice la carga, la validación y el procesamiento de datos de ensayos agrícolas, y que ejecute sobre ellos un análisis estadístico coherente con el diseño experimental, priorizando la trazabilidad, la calidad del dato y la mantenibilidad del sistema en el tiempo.

De los objetivos específicos, destacamos tres. Primero, definir un esquema de datos formal para ensayos agrícolas, con variables, tipos, unidades, rangos y reglas de validación. Segundo, implementar el flujo de automatización completo, orquestado con n8n y procesado con Python, con registro de ejecuciones y bitácoras de auditoría. Y tercero, integrar un módulo de análisis estadístico reproducible, capaz de aplicar el modelo apropiado al diseño y generar diagnósticos explícitos.

---

## [3:00–4:30] Marco teórico y antecedentes

Nuestro trabajo se apoya en cuatro pilares conceptuales.

El primero es la calidad y la trazabilidad del dato en la investigación experimental. La literatura clásica de diseño experimental dedicó enormes esfuerzos al diseño y al análisis, pero históricamente prestó poca atención sistemática a la gestión del dato en los pasos intermedios. Nosotros ponemos el foco justamente ahí: en la completitud, la validez, la consistencia y, sobre todo, la trazabilidad, entendida como la capacidad de reconstruir la historia completa del dato.

El segundo pilar es la automatización de flujos de datos mediante orquestación. Adoptamos el modelo de extraer, transformar y cargar, y elegimos n8n como plataforma de orquestación por su baja curva de aprendizaje, su despliegue simple y su interfaz visual, que hace comprensible el flujo para perfiles técnicos diversos.

El tercer pilar es la reproducibilidad computacional con Python. La reproducibilidad exige fijar las dependencias, versionar el código y parametrizar el análisis, de modo que una misma entrada produzca siempre el mismo resultado.

Y el cuarto pilar es la estadística de la experimentación agrícola: el análisis de varianza y sus supuestos de independencia, normalidad y homogeneidad de varianzas, junto con las alternativas apropiadas cuando esos supuestos no se cumplen. Nuestro aporte no busca reemplazar al estadístico, sino construir el sistema de ingeniería que ejecuta ese análisis de manera correcta, reproducible y documentada.

---

## [4:30–6:30] Metodología

Metodológicamente, la tesis se enmarca en la investigación aplicada orientada al diseño. El objetivo no es generar una ley universal, sino producir un artefacto —el flujo automatizado— que resuelva un problema práctico identificado con rigor, y extraer de su construcción conocimiento generalizable. La estrategia es la del estudio de caso instrumental: un ensayo agrícola real que sirve como instrumento para desarrollar y evaluar el sistema, y que permite comparar el estado actual, el proceso manual, contra el estado propuesto, el flujo automatizado.

El procedimiento es de implementación incremental. Construimos el sistema módulo por módulo: primero la ingesta y la validación, después la transformación y la persistencia, y finalmente el módulo estadístico. Cada módulo se prueba de forma aislada antes de integrarlo al flujo completo.

A esa metodología de investigación queremos sumarle un elemento del proceso de construcción del software que consideramos parte esencial de nuestro rigor. Adoptamos una metodología de desarrollo dirigida por especificaciones: antes de escribir código, cada componente queda especificado por completo en documentos formales que describen qué debe hacer y por qué. Todo el código se administra bajo un sistema de control de versiones, de modo que cada resultado puede asociarse a una versión exacta del código que lo produjo. Y trabajamos bajo un ciclo estricto de desarrollo guiado por pruebas. Esto significa que, para cada funcionalidad, primero escribimos una prueba automática que describe el comportamiento esperado y que necesariamente falla porque el código todavía no existe; luego escribimos el mínimo código necesario para que esa prueba pase; después agregamos casos adicionales que cubren las situaciones límite; y por último mejoramos el código sin alterar su comportamiento, con las pruebas confirmando en cada paso que nada se rompió. Este ciclo no es un detalle accesorio: es la garantía de que el núcleo del sistema hace exactamente lo que decimos que hace, y es lo que nos permitió detectar el hallazgo que compartimos a continuación.

---

## [6:30–8:00] Resultados preliminares

Veamos el avance concreto que ya existe, con la honestidad de que es preliminar y de que la validación empírica sobre un caso real todavía está pendiente.

Primero, construimos la base de conocimiento del proyecto: trece documentos canónicos que especifican el sistema por completo —actores, reglas de negocio, modelo de datos y decisiones de arquitectura— más un mapa de desarrollo que ordena el trabajo en una secuencia de cambios, con un camino crítico de nueve pasos.

Segundo, y más importante, el núcleo de análisis estadístico ya está construido y validado. Está respaldado por cuarenta y cinco pruebas automáticas que pasan correctamente, desarrolladas bajo el ciclo estricto de pruebas que describimos, e implementa el análisis de varianza, la prueba de Tukey, la prueba de Kruskal-Wallis, el diagnóstico de supuestos y las transformaciones de la variable respuesta.

Y de esa validación surgió nuestro hallazgo más valioso hasta hoy. Al verificar la comparación de medias posterior al análisis de varianza, detectamos que una función estándar y ampliamente usada de la biblioteca statsmodels de Python calcula de manera incorrecta la prueba de Tukey cuando el diseño incluye un factor de bloqueo —el diseño en bloques completos al azar, muy común en ensayos agrícolas—, porque ignora el efecto del bloqueo. Lo validamos empíricamente contra un conjunto de datos de referencia científica, los experimentos históricos de Fisher en la estación de Rothamsted: el cálculo ingenuo con la función estándar arroja un valor p de cero coma cero doscientos veintiuno, mientras que el cálculo correcto da un valor p de cero coma cero cero setenta y uno. Es una discrepancia sustantiva, capaz de cambiar una conclusión estadística. Este hallazgo ya quedó documentado como decisión de diseño formal de la tesis y aportó contenido genuino a las lecciones aprendidas del Capítulo 6.

Por último, completamos el diseño arquitectónico de los módulos que integran al sistema con sus usuarios: una capa de interacción por Telegram, con dos roles y un motor genérico de sesiones, y una capacidad opcional de captura de datos de campo por reconocimiento óptico sobre planillas de papel, pensada para condiciones sin conectividad confiable. Son diseños ya completos y en proceso de incorporación al texto.

---

## [8:00–9:00] Discusión

¿Qué tan cerca estamos, entonces, de responder la pregunta de investigación? Hagamos un balance honesto.

El núcleo estadístico ya está construido y es correcto, lo cual responde de manera parcial al objetivo de reproducibilidad y consistencia estadística. La arquitectura del sistema completo está diseñada y documentada. Sin embargo, la validación empírica del sistema integral sobre un caso de estudio real —y, con ella, la comparación contra el proceso manual que motivó la tesis— todavía está pendiente. No queremos disimularlo: esa evaluación es el corazón del Capítulo de resultados y aún no puede completarse.

Ahora bien, hay algo que el hallazgo de la prueba de Tukey ya demuestra, incluso antes de contar con el caso de estudio. Demuestra el valor concreto de haber construido el núcleo con rigor y bajo pruebas exhaustivas, en lugar de confiar ciegamente en una biblioteca estándar. Si hubiéramos dado por buena esa función, habríamos arrastrado un error silencioso hasta las conclusiones finales. La disciplina de prueba lo evitó. Eso, en sí mismo, ya es un resultado. Y esa misma disciplina reduce el riesgo de lo que resta: los módulos pendientes no parten de cero, sino que ya tienen su contrato definido —reglas de negocio especificadas en la base de conocimiento, el diccionario de variables por construir sobre un esquema ya formalizado— y un lugar preciso en el camino crítico que hemos mapeado. Dicho de otro modo, lo que falta es ejecución acotada bajo la misma disciplina que ya dio resultado, no incertidumbre de diseño abierta.

---

## [9:00–10:00] Limitaciones, trabajo futuro y cierre

Corresponde reconocer con claridad la limitación central de este momento. La elección del caso de estudio real —qué ensayo, qué institución, qué cultivo— es una decisión que el equipo todavía tiene pendiente, y que condiciona todo lo que sigue: la construcción del diccionario de variables definitivo, la ejecución del sistema de punta a punta y la comparación contra el proceso manual de referencia. No es un detalle menor: es el paso que habilita el cierre empírico de la tesis.

En cuanto al trabajo futuro inmediato, seguiremos la hoja de ruta ya definida para construir de forma incremental los módulos restantes del flujo: la ingesta, la validación, la transformación, la persistencia auditable y la orquestación en n8n.

Hay, además, dos líneas de investigación que el propio diseño del sistema ya proyecta más allá del alcance de esta tesis puntual, y que dejamos documentadas como trabajo futuro. La primera nace de la persistencia auditable: a medida que el sistema procese ensayos, irá acumulando un conjunto de datos multi-ensayo con trazabilidad completa y calidad garantizada por el mismo pipeline de validación. Ese acumulado habilita preguntas que ningún ensayo individual puede responder por sí solo —meta-análisis entre campañas y sitios, y una base de entrenamiento confiable para los componentes de inteligencia artificial que la tesis contempla como épica opcional—, aunque materializarlo de verdad requeriría antes resolver el consentimiento institucional para el reuso de cada ensayo. La segunda se apoya en el campo de geolocalización que ya incorporamos al modelo de datos: disponer de la latitud y la longitud de cada ambiente permitiría, en un análisis posterior, cruzar los resultados contra datos climáticos externos y explicar parte de la variación ambiental que el diseño de bloqueo no captura. Ninguna de las dos está construida; son líneas honestamente documentadas, con lo que haría falta para concretarlas. Pero su sola existencia muestra que este no es un proyecto que se agota en la defensa final, sino una base sobre la que seguir construyendo.

Para cerrar: el avance de hoy demuestra que las decisiones de fondo del sistema son sólidas y que el núcleo crítico funciona de manera correcta y verificable. Sobre esa base construiremos la validación empírica que le falta. Agradecemos a nuestro director, el Magíster Alberto Cortez, por su guía, y al comité por su atención. Muchas gracias.

---

_Nota para el equipo (no forma parte del guion) — conteo aproximado de palabras por bloque, para cronometrar el ensayo:_

| Bloque | Tiempo objetivo | Palabras aprox. |
|--------|-----------------|-----------------|
| Apertura e identificación | 0:45 | ~120 |
| Problema y motivación | 1:15 | ~235 |
| Pregunta de investigación y objetivos | 1:00 | ~220 |
| Marco teórico y antecedentes | 1:30 | ~260 |
| Metodología | 2:00 | ~330 |
| Resultados preliminares | 1:30 | ~330 |
| Discusión | 1:15 | ~285 |
| Limitaciones, trabajo futuro y cierre | 1:30 | ~425 |
| **Total** | **~11:00** | **~2200** |

_A un ritmo formal pausado de 145–150 palabras por minuto, ~2200 palabras rinden alrededor de 15 minutos de lectura corrida. Para ajustar a 10 minutos reales conviene: (1) leer a ~180–190 palabras/minuto, ritmo de presentación normal y aún claro; o (2) recortar los bloques más holgados —Metodología, Avances y Marco teórico son los que tienen más margen de poda sin perder contenido esencial. Los bloques de Discusión y Cierre crecieron a propósito para tejer el argumento de continuidad del proyecto; si hiciera falta recuperar tiempo, la línea de reuso académico del dataset puede resumirse sin perder la idea central. Se recomienda un ensayo cronometrado y ajustar primero sobre Metodología, Avances y Marco teórico._

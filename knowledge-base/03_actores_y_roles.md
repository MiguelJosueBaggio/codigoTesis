# Actores y Roles

> **Nota de origen**: la tesis no define una matriz RBAC formal. Los actores base siguientes se infieren de las secciones 4.8 (seguridad), 2.6 (IA) y 3.7 (ética/gestión de datos).
>
> **Actualización (refinamiento de interacción por Telegram, ver `13_interaccion_telegram_y_sesiones.md` y DD-09)**: el sistema pasó a un modelo **cero interacción técnica del usuario** — el único punto de contacto humano es Telegram (ver DD-09, que refina DD-05). Esto obliga a formalizar, **de cara al bot**, dos roles operativos concretos —**Ingeniero** y **Ayudante**— y una autorización mínima (`telegram_user_id → rol`). Con eso **queda resuelto** el hueco de RBAC que este archivo marcaba como pendiente (ver §RBAC más abajo y `10_preguntas_abiertas.md`).

## Actores del sistema

| Actor | Descripción | Cómo interactúa |
|---|---|---|
| Investigador / analista de datos | Persona que carga los archivos crudos y revisa los registros rechazados | Deposita archivos CSV/Excel en la ubicación monitoreada; consulta reportes de validación. De cara al nuevo modelo Telegram, su faceta operativa de carga a campo la ejerce el rol **Ayudante** (ver abajo) |
| Estadístico | Persona responsable del análisis estadístico del ensayo | Configura el modelo (fórmula R-style) e interpreta tabla ANOVA y diagnósticos. **Su autoridad de configuración se ejerce ahora a través del rol Ingeniero** vía setup guiado por Telegram, no editando `analysis_config.yaml` a mano (ver `13_*`) |
| Experto de dominio agronómico | Valida y mantiene el diccionario de variables y catálogo de valores admisibles | Participa en el relevamiento del `data_dictionary.json`. **Su autoridad de definición del diccionario se ejerce ahora a través del rol Ingeniero** vía setup guiado por Telegram (ver `13_*`) |
| Auditor externo | Verifica que el pipeline fue ejecutado correctamente sobre los datos declarados | Consulta la bitácora de auditoría (solo lectura) |
| Administrador del sistema / mantenedor | Gestiona credenciales, despliegue, backups y evolución del código | Acceso a variables de entorno, repositorio Git, configuración de n8n. Es el único actor que interactúa con la CLI/infraestructura directamente; los usuarios finales NO |
| Componente de IA (apoyo) | Sugiere estandarizaciones léxicas y detecta anomalías | **Nunca aplica cambios de forma autónoma** — genera propuestas que requieren aprobación humana explícita, registrada en bitácora |

## Roles operativos de cara al bot de Telegram (nuevos — ver `13_interaccion_telegram_y_sesiones.md`)

| Rol | Es… | Autoridad | Cómo interactúa |
|---|---|---|---|
| **Ingeniero** (responsable del ensayo) | **Consolidación operativa** —de cara a Telegram— de la autoridad de decisión del **Estadístico** + el **Experto de dominio agronómico**. Decisión de diseño (ver más abajo): NO es un actor nuevo con juicio experto propio, sino la *cara única* que ejerce ese juicio ya existente a través del bot | (a) Correr el setup guiado de un ensayo nuevo (define modelo, diseño experimental y diccionario **conversando**, no editando archivos); (b) recibir resultados procesados; (c) elegir el modo del reporte final: auto-generado (RN-EST-02) vs. auto-redactado por él mismo (RN-EST-07) | Conversación guiada por Telegram (`tipo_sesion = setup_ensayo`); recibe notificaciones de resultados |
| **Ayudante** | Rol **genuinamente nuevo y aditivo** (subconjunto de campo del "Investigador / analista", pero **sin** autoridad de setup ni de aprobación) | Sólo carga de datos de campo, una vez que el ensayo ya está configurado. Sin permisos de configuración, aprobación ni elección de reporte | El mismo bot le pide el dato **campo por campo** y le ofrece **cómo** enviarlo: escribir el valor como texto, o mandar una **foto** de planilla de papel para OCR (integra `12_captura_offline_ocr.md` como método de entrada dentro de la sesión) |

### Decisión de reconciliación (justificación)

Se evaluó si "Ingeniero" era un actor **nuevo** o un **renombre/consolidación** de actores existentes. Decisión: **consolidación**, no actor nuevo. Razón: la tesis ya modela el juicio experto (fórmula del modelo → Estadístico; diccionario de variables → Experto de dominio). El refinamiento por Telegram **no crea juicio experto nuevo** — sólo unifica *quién opera el bot* para entregar ese juicio. En el caso de estudio real, una misma persona (el ingeniero responsable del ensayo) ejerce ambas autoridades; modelarlo como un actor experto separado duplicaría responsabilidades ya cubiertas. En cambio, "Ayudante" **sí** es aditivo: es un rol de ejecución de campo sin autoridad de decisión que la tabla de actores original no contemplaba explícitamente (lo más cercano era "Investigador / analista", que sí revisa rechazos y no está restringido a sólo cargar).

## RBAC — Matriz de permisos (resuelta)

> **Estado: RESUELTA** (antes: "no definida en el documento fuente"). El refinamiento de interacción por Telegram (DD-09) exige un control de acceso mínimo de aplicación, que reemplaza la nota anterior de "pendiente de decisión de equipo".

**Mecanismo de autorización (liviano)**: la identidad del usuario es su **`telegram_user_id`** (provisto por el propio Telegram en cada mensaje/evento). Una tabla de mapeo **`telegram_user_id → rol`** (`ingeniero` | `ayudante`), acotada por `ensayo_id` cuando corresponde, resuelve la autorización. No se introduce un sistema de login/contraseña propio: la autenticación la delega en Telegram, y la autorización es este mapeo mínimo.

| Recurso / acción | Ingeniero | Ayudante | Notas |
|---|---|---|---|
| Iniciar `setup_ensayo` (definir modelo/diccionario) | ✅ | ❌ | Sólo el ingeniero configura |
| Cargar dato de campo (`carga_dato`, texto o foto/OCR) | ✅ | ✅ | Ambos pueden cargar |
| Confirmar lectura OCR / sugerencia IA bajo umbral | ✅ | ✅ (según política de sesión) | Ver RN-OCR-04, RN-IA-02; a afinar si se requieren sub-permisos (pregunta abierta) |
| Recibir resultados del análisis | ✅ | ❌ | Notificación al ingeniero responsable |
| Elegir autoría del reporte final (RN-EST-07) | ✅ | ❌ | Decisión metodológica, sólo ingeniero |
| Consultar bitácora de auditoría | (fuera de este canal) | ❌ | Es rol del Auditor externo, no del bot |

**Alcance deliberadamente mínimo**: este RBAC cubre lo que el canal Telegram necesita, no un sistema multiusuario general. Si el sistema creciera (más roles, sub-permisos del Ingeniero, permisos por variable), habría que extenderlo — queda anotado como pregunta abierta en `10_preguntas_abiertas.md`. El control de acceso de **infraestructura** (credenciales vía variables de entorno, permisos mínimos por componente, §4.8) sigue vigente y es independiente de este RBAC de aplicación.

## Rutas públicas

No aplica — no hay una interfaz web pública descrita en la tesis. El único punto de entrada "público" conceptual es la carpeta de ingesta de archivos monitoreada por n8n.

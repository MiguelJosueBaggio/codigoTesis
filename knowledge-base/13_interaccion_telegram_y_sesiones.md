# Capa de Interacción por Telegram y Motor Genérico de Sesiones

> **Origen de este archivo**: refinamiento arquitectónico solicitado por el usuario a lo largo de varias iteraciones, posterior a la decisión CLI-first (`09_decisiones_y_supuestos.md`, DD-05) y a la resolución de la pregunta "¿UI propia?" (`10_preguntas_abiertas.md`) como *CLI-first / sin web UI*. El usuario llevó esa idea un paso más allá: **el usuario final no debe tener NINGUNA interacción directa con la CLI ni con ninguna interfaz técnica** — el sistema completo debe ser 100% orientado a eventos, orquestado por n8n, con **Telegram como único punto de contacto humano** (tanto para notificaciones como para confirmaciones y carga de datos interactiva). Este documento formaliza ese cambio, lo reconcilia con las decisiones previas (no las sobrescribe en silencio — ver DD-09, que *refina/supersede* DD-05) y diseña el mecanismo concreto: dos roles y un motor genérico de sesiones dirigido por datos.

Este cambio también **resuelve** el hueco de RBAC marcado como pendiente en `03_actores_y_roles.md` y en la pregunta de prioridad Media de `10_preguntas_abiertas.md` ("¿Se requiere RBAC formal?"), y **corrige** la materialización de la confirmación humana descrita en `05_reglas_de_negocio.md`, RN-OCR-04 (que decía "por CLI" — ahora es por Telegram).

---

## 1. Por qué existe esta capa: de "CLI-first" a "cero interacción técnica"

La arquitectura en capas (`08_arquitectura_propuesta.md`) y el desacoplamiento CLI (DD-05) resuelven un problema **de ingeniería**: que la capa de procesamiento (`pipeline/*.py`) sea invocable, testeable y sustituible sin depender de n8n. Ese objetivo sigue vigente y **no cambia**.

Lo que cambia es **quién** invoca la CLI. En la lectura original (DD-05, y `07_flujos_principales.md`, Flujos 1-4), varios actores humanos aparecían editando archivos de configuración a mano (`analysis_config.yaml` en el Flujo 3) o corriendo comandos (la confirmación OCR "por CLI" de RN-OCR-04). Eso presupone que un investigador, un estadístico o un ayudante de campo se sientan frente a una terminal. En las condiciones reales del proyecto —los mismos actores que a veces sólo tienen un teléfono a campo (`12_captura_offline_ocr.md`)— eso no es realista ni deseable.

El refinamiento: **la CLI deja de ser una interfaz de usuario y pasa a ser un mecanismo de invocación interno**. n8n sigue llamando a `pipeline/*.py` por CLI (respetando DD-05 al pie de la letra), pero ningún humano teclea nunca un comando. Todo lo que un humano necesita hacer —configurar un ensayo, cargar un dato, confirmar una lectura dudosa, recibir resultados— ocurre a través de **Telegram**, y todo lo demás ocurre solo, disparado por eventos.

**Frontera honesta de la automatización** (ver §6): esto NO significa que las decisiones expertas desaparezcan. La definición inicial del modelo estadístico, el diseño experimental y el diccionario de variables sigue siendo una decisión metodológica de experto irreductible. Lo que se automatiza es **cómo** el experto entrega esa configuración: en vez de editar JSON/YAML a mano, responde una secuencia guiada de preguntas por Telegram y el sistema construye la configuración a partir de sus respuestas.

---

## 2. Por qué Telegram (decisión cerrada)

Telegram se elige como único canal humano por razones concretas, ya evaluadas y aceptadas:

- **Nodo nativo en n8n** — n8n trae un nodo Telegram nativo para *enviar* (mensajes, fotos, botones *inline*) y un **Telegram Trigger** para *recibir* (mensajes entrantes y eventos de *callback* de botones). Telegram entra así como un trigger/salida más dentro de la capa de orquestación ya existente (DD-02), **no** como un componente arquitectónico nuevo. No hay que construir ni mantener un backend de mensajería propio.
- **Gratuito y sin verificación de API de negocio** — a diferencia de la WhatsApp Business API, que fue **considerada y explícitamente descartada** por requerir verificación de negocio, tener potenciales costos por conversación y ventanas de 24h para *template messages*. Telegram no impone ninguna de esas fricciones.
- **Botones *inline*** — ideales para el patrón confirmar/rechazar del *human-in-the-loop* ya establecido por RN-IA-01/02/03 y RN-OCR-04. Un mensaje con dos botones ("Confirmar 8.3" / "Corregir") es la materialización natural de una confirmación bajo umbral.
- **Mecanismo de pausa/reanudación** — n8n permite que un workflow se **pause en un paso de confirmación y se reanude cuando llega el evento** (clic de botón o respuesta). El mecanismo concreto es el **"Wait for Webhook" / reanudación de workflow** de n8n: el workflow queda suspendido esperando un webhook, y el *callback* del botón (o el mensaje de respuesta) dispara ese webhook y reanuda la ejecución con el valor confirmado. Esto es lo que hace viable el *human-in-the-loop* asíncrono sin *polling* ni estado ad hoc en el workflow.

### 2.1. Confidencialidad — el matiz honesto (no sobrevender)

Este punto se documenta con precisión deliberada, porque es fácil sobrevenderlo:

- Los chats de **bots** de Telegram **NO son end-to-end encrypted (E2E)**. El E2E de Telegram existe sólo en los "Secret Chats", y **los bots no pueden participar en Secret Chats**.
- El tráfico **sí** está cifrado en tránsito (cliente ↔ servidores de Telegram) y no queda expuesto en un canal abierto. Es **mejor** que un canal abierto o un email sin cifrar.
- Pero **NO** es confidencialidad nivel Signal / E2E. El operador de la plataforma (Telegram) tiene, técnicamente, acceso al contenido en sus servidores.

Implicación para el proyecto: el dato del ensayo que viaja por Telegram (valores de campo, fotos de planillas) queda bajo esta garantía **parcial**, no bajo la garantía de confidencialidad total que motivó, por ejemplo, la prohibición de OCR en la nube (RN-OCR-05, §3.7 de la tesis). Esto es una **tensión** que el equipo debe registrar conscientemente: la misma sensibilidad del dato que hizo descartar las APIs de nube para OCR aplica, en menor grado, al canal Telegram. Se acepta el matiz porque el beneficio operativo (cero fricción, canal único, nodo nativo) supera el riesgo residual para el alcance de la tesis — pero **debe documentarse como lo que es**, no como "confidencialidad total". Ver DD-09, trade-offs aceptados.

---

## 3. Dos roles: Ingeniero y Ayudante

Esta capa introduce dos roles humanos de cara al bot. Ambos se reconcilian con los actores ya existentes en `03_actores_y_roles.md` (ver ese archivo para la tabla completa y la decisión de consolidación).

### 3.1. Ingeniero (responsable del ensayo)

Consolidación operativa, de cara a Telegram, de la autoridad de decisión que en `03_actores_y_roles.md` estaba repartida entre el **Estadístico** (configura la fórmula/modelo) y el **Experto de dominio agronómico** (define/valida el diccionario de variables). En la práctica del caso de estudio, una misma persona —el ingeniero responsable del ensayo— ejerce ambas autoridades a través del bot. Sus atribuciones:

1. **Correr el setup guiado de un ensayo nuevo** por Telegram: define el modelo estadístico (fórmula R-style, RN-EST-01), el diseño experimental y el diccionario de variables (`config/data_dictionary.json`, `config/analysis_config.yaml`) **conversando**, no editando archivos a mano. El sistema construye la configuración a partir de sus respuestas. (Ver §6: la decisión sigue siendo experta; sólo cambia el medio de entrega.)
2. **Recibir los resultados procesados** una vez que el dato recorrió el pipeline (ingesta → validación → transformación → persistencia → análisis). Notificación por Telegram.
3. **Elegir el modo del reporte final**: auto-generado por el sistema (según RN-EST-02, salida HTML/CSV) **o** auto-redactado (el ingeniero escribe él mismo la narrativa/interpretación). Este es un **punto de decisión genuinamente nuevo** — se documenta como extensión de RN-EST-02 (nuevo **RN-EST-07**), no como contradicción: RN-EST-02 sigue produciendo la tabla de resultados; lo nuevo es que la *autoría del informe interpretativo* pasa a ser una elección explícita del ingeniero.

### 3.2. Ayudante (carga de datos, sin autoridad de setup/aprobación)

Rol de entrada de datos a campo. **No** tiene autoridad de setup ni de aprobación. Una vez que un ensayo está configurado, los ayudantes interactúan con **el mismo bot** para cargar datos de campo:

- El bot les pide el dato **campo por campo** (guiado por la secuencia de pasos del `tipo_sesion` "carga_dato", ver §4).
- Para cada campo, el bot les ofrece **cómo** enviarlo: **escribir el valor** directamente como texto, **o** **enviar una foto** de una planilla de papel llena para OCR.
- La foto-para-OCR es exactamente donde la capacidad de `12_captura_offline_ocr.md` se integra: **el OCR pasa a ser UNO de los métodos de entrada dentro de este flujo de sesión**, no un sistema paralelo. La foto entra por Telegram, se procesa con el pipeline OCR zonal (RN-OCR-01..07), y si una lectura queda bajo umbral, dispara una confirmación por Telegram (ver §5) — cerrando el círculo con RN-OCR-04 ya corregido.

---

## 4. Motor genérico de sesiones dirigido por datos

Es el corazón técnico de esta capa, y la simplificación clave que se trabajó cuidadosamente con el usuario. Se documenta el **razonamiento**, no sólo la conclusión.

### 4.1. La idea rechazada: un árbol de conversación hardcodeado por rol

La primera idea considerada fue **hardcodear en n8n una rama/árbol de conversación distinto por rol**: un workflow con grandes bifurcaciones ("si es ingeniero, preguntar X; si es ayudante, preguntar Y; si está en el paso 3 del setup, preguntar Z…"). **Rechazada** por costo de construcción y —sobre todo— de mantenimiento: cada nuevo tipo de pregunta obligaría a **modificar el grafo del workflow de n8n**. El grafo crecería sin control y cada cambio de flujo sería un cambio de código de orquestación.

### 4.2. La idea adoptada: máquina de estados de sesión, genérica, respaldada por la base de datos

En su lugar, un patrón **genérico de máquina de estados de sesión**, persistido en la base de datos que el proyecto ya tiene planificada (`04_modelo_de_datos.md`, `08_arquitectura_propuesta.md`). La tabla de sesión es **una entidad nueva agregada a esa capa de persistencia existente**, no un almacén separado.

**Entidad `sesion` (nueva entidad de sistema):**

| Atributo | Tipo | Descripción |
|---|---|---|
| `session_id` | id único | Identificador de la sesión |
| `telegram_user_id` | entero | Usuario de Telegram dueño de la sesión (mapea a rol, ver RBAC §3 de `03_actores_y_roles.md`) |
| `ensayo_id` | fk nullable | Ensayo asociado; **nullable** para sesiones de setup de ingeniero, donde el ensayo aún no existe |
| `tipo_sesion` | enum | `setup_ensayo` \| `carga_dato` \| `confirmacion_ocr` \| `confirmacion_ia` (extensible) |
| `paso_actual` | índice/clave | Paso actual dentro de la secuencia del `tipo_sesion` |
| `respuestas_acumuladas` | estructura (JSON) | Respuestas acumuladas hasta el momento, estructuradas |
| `estado` | enum | `abierta` \| `completada` \| `abandonada` \| `expirada` |
| `created_at`, `updated_at` | timestamps | Marcas temporales de creación y última actividad |

### 4.3. La secuencia de pasos es DATA, no código de workflow

El elemento que hace genérico al motor: la **secuencia de pasos** de cada `tipo_sesion` se define como **datos/configuración**, no como bifurcaciones hardcodeadas en n8n. Cada paso es una definición de pregunta:

- texto del *prompt*,
- tipo de respuesta esperada (`texto` / `numero` / `foto` / `choice`),
- referencia a la regla de validación aplicable (de vuelta a `RN-VAL` / al diccionario de variables).

**Agregar una pregunta nueva a un flujo = agregar una fila/entrada de configuración, NO editar el grafo del workflow de n8n.** Ese es todo el punto.

### 4.4. El workflow de n8n es UN ÚNICO LOOP GENÉRICO

La lógica del workflow se reduce a un solo bucle genérico, reutilizable para **todos** los tipos de sesión:

```
Llega un mensaje de telegram_user_id
        │
        ▼
Buscar sesión ABIERTA para ese usuario
        │
   ┌────┴─────────────────────────────┐
   │ no hay sesión abierta             │ hay sesión abierta
   ▼                                   ▼
Resolver el TIPO de sesión:        Tratar el mensaje entrante como
 - ¿es un ingeniero registrado      la RESPUESTA al paso_actual:
   sin setup de ensayo activo?       1. validar (RN-VAL / diccionario)
   → ofrecer iniciar setup_ensayo    2. almacenar en respuestas_acumuladas
 - ¿es un ayudante conocido de un    3. avanzar al paso siguiente según
   ensayo activo?                       la secuencia-config del tipo_sesion
   → ofrecer carga_dato             4. enviar el prompt del paso siguiente
Crear sesión nueva en paso 0            (o finalizar si era el último paso)
   │                                   │
   └────────────────┬──────────────────┘
                    ▼
        Enviar prompt correspondiente por Telegram
```

**"Reanudar una sesión anterior" sale gratis** de esta misma búsqueda: al chequear si existe una sesión abierta *antes* de crear una nueva, el sistema resuelve naturalmente si el usuario quiere continuar donde dejó. Es exactamente lo que propuso el usuario: *"a través de la base de datos resolveremos si quiere continuar en una sesión anterior, de la manera más genérica"*.

### 4.5. Análisis costo/beneficio (trade-off honesto, no una victoria incondicional)

Este patrón fue un ida y vuelta real con el usuario; se registra el razonamiento completo:

- **Reduce el costo marginal de agregar flujos nuevos**: un flujo nuevo = datos de configuración nuevos, no código de workflow nuevo.
- **Reduce el costo de mantenimiento a largo plazo**: un único motor genérico en vez de N ramas hardcodeadas que divergen y se pudren.
- **PERO no elimina el costo único de construir el motor genérico**: hay que construir la tabla `sesion`, la lógica del *resolver* ("¿cuál es el paso siguiente?", "¿qué tipo de sesión corresponde a este usuario?"), y el manejo de timeout/abandono. Ese costo se paga una vez, por adelantado.

Es decir: se cambia **N costos incrementales futuros** por **un costo fijo inicial**. Para un sistema que se espera que crezca en tipos de interacción (hoy 4 `tipo_sesion`, mañana más), el intercambio conviene — pero **es un intercambio, no un almuerzo gratis**. Se documenta así para que quien lo implemente no subestime el esfuerzo inicial del motor.

### 4.6. Timeout / abandono de sesiones

Una sesión `abierta` sin respuesta por demasiado tiempo debe tener **algún** comportamiento definido, siguiendo la misma filosofía de escalamiento ya establecida para fallos de pipeline (**RN-GLB-03**: reintentos/escalamiento). La **duración exacta del timeout no fue decidida** por el usuario — queda como **pregunta abierta explícita** (ver `10_preguntas_abiertas.md`). El diseño debe contemplar el estado `expirada` y `abandonada` en la entidad `sesion` desde el inicio, aunque el valor concreto del umbral se fije más tarde.

---

## 5. Catálogo de eventos (base de los flujos)

El sistema completo se reexpresa como una cadena de eventos. Esta tabla/cadena es la base para actualizar `07_flujos_principales.md`:

```
Archivo nuevo (CSV/Excel/foto vía Telegram)
        │
        ▼
Ingesta (RN-ING)  ──(foto)──►  pipeline OCR zonal (RN-OCR-01..07)
        │
        ▼
Validación (RN-VAL)
        │
   ┌────┴─────────────────────────┐
   ▼                              ▼
rechazados                      válidos
   │                              │
   ▼                              ▼
Notificación Telegram      Transformación (RN-TRA)
(detalle del rechazo)            │
                                 ▼
                           Persistencia + bitácora (RN-AUD)
                                 │
                                 ▼
                     ¿existe analysis_config.yaml del ensayo?
                                 │ sí
                                 ▼
                     Análisis estadístico automático (RN-EST)
                                 │
                                 ▼
                     Notificación Telegram de resultados al ingeniero
                     (+ elección de modo de reporte, RN-EST-07)

EN PARALELO (human-in-the-loop asíncrono):
  Cualquier lectura OCR / sugerencia IA de baja confianza
        │
        ▼
  Mensaje Telegram con botones inline  (confirmacion_ocr / confirmacion_ia)
        │
        ▼
  Workflow en PAUSA  (n8n "Wait for Webhook")
        │
        ▼
  Clic del usuario  →  webhook reanuda el workflow con el valor confirmado
        │
        ▼
  Registro en bitácora (RN-AUD-02): lectura original vs. valor confirmado, quién y cuándo

ESCALAMIENTO:
  N reintentos fallidos en cualquier etapa  →  escalamiento por Telegram
  (extiende RN-GLB-03 con el canal concreto: la "notificación humana" ES un mensaje de Telegram)
```

---

## 6. La frontera de la automatización (lo que NO se automatiza)

Punto que **no debe omitirse**. La configuración inicial de un ensayo nuevo —definir la fórmula del modelo estadístico, el diseño experimental y el diccionario de variables— es inherentemente una **decisión experta de una sola vez** que no se puede automatizar del todo. Un experto de dominio debe tomar decisiones metodológicas reales ahí: qué variables se miden, con qué rangos plausibles, qué factores entran al modelo, qué diseño experimental gobierna el ensayo. Ninguna máquina puede sustituir ese juicio (es, además, coherente con lo que la tesis pone explícitamente **fuera de alcance** en `01_vision_y_objetivos.md`: "el sistema procesa, no diseña, ensayos").

Lo que **sí** se automatiza es la **forma de interacción** con que el experto entrega esa configuración: en vez de editar `config/data_dictionary.json` y `config/analysis_config.yaml` a mano, responde una secuencia guiada de preguntas por Telegram (`tipo_sesion = setup_ensayo`) y el sistema **construye** esos archivos de configuración a partir de sus respuestas.

Una vez configurado un ensayo, **todo lo de aguas abajo** (dato que llega, validación, transformación, persistencia, análisis, notificaciones) es **100% orientado a eventos**, sin más trabajo manual de CLI ni de edición de archivos de configuración. La única intervención humana recurrente son las confirmaciones bajo umbral (OCR/IA), que también ocurren por Telegram.

---

## 7. Impacto en la documentación existente

| Archivo | Cambio |
|---|---|
| `03_actores_y_roles.md` | Se agregan/reconcilian los roles **Ingeniero** (consolidación de Estadístico + Experto de dominio de cara al bot) y **Ayudante** (nuevo, carga de datos sin autoridad). Se agrega sección RBAC mínima (`telegram_user_id → rol`), **resolviendo** la nota "RBAC no definida". |
| `05_reglas_de_negocio.md` | **RN-OCR-04 corregida** (confirmación por Telegram, no por CLI). Nuevo dominio **RN-SES** (motor de sesiones). Nueva **RN-EST-07** (elección de autoría del reporte). |
| `09_decisiones_y_supuestos.md` | Nueva **DD-09**, que *refina/supersede* explícitamente **DD-05** (mantiene "no web UI", reemplaza "CLI-first" por "cero interacción directa del usuario; Telegram + eventos; CLI pasa a ser interna de n8n"). |
| `07_flujos_principales.md` | Flujos actualizados a la interacción por eventos/Telegram; se agrega el flujo del catálogo de eventos (§5) y el flujo de setup guiado. |
| `10_preguntas_abiertas.md` | Se actualiza la entrada "¿UI propia?" (evolución CLI-first → Telegram/eventos). Nuevas preguntas: timeout de sesión, formato de config de pasos, sub-permisos de Ingeniero, default/deadline de la elección de reporte. |
| `CHANGES.md` | Nuevos changes **C-12** (motor de sesiones) y **C-13** (capa Telegram + roles). Ver ese archivo para dependencias y governance. |

## 8. Reglas de negocio asociadas

Ver `05_reglas_de_negocio.md`:
- **RN-SES-01 a RN-SES-06** (dominio nuevo): creación/resolución de sesión, secuencia-de-pasos-como-config, resolución reanudar-vs-nueva, validación por paso, auditoría de eventos de sesión (liga a RN-AUD), timeout/abandono.
- **RN-OCR-04** (corregida): confirmación humana por Telegram, no por CLI.
- **RN-EST-07** (nueva): elección de autoría del reporte final (auto-generado vs. auto-redactado por el ingeniero).

## 9. Decisión formal y changes

- Decisión: `09_decisiones_y_supuestos.md`, **DD-09** (refina/supersede DD-05).
- Roadmap: `CHANGES.md`, **C-12** `session-engine` (motor genérico, depende de C-06) y **C-13** `telegram-interaction-layer` (bot + roles + flujos guiados, depende de C-08 y C-12, se relaciona con C-11 porque el OCR es un método de entrada dentro de una sesión).

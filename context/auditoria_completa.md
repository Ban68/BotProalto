# AUDITORIA COMPLETA — Bot WhatsApp ProAlto
## Periodo: 15 - 30 Marzo 2026

---

## 1. RESUMEN EJECUTIVO

| Metrica | Valor |
|---------|-------|
| Conversaciones analizadas | **742** |
| Total mensajes | **24,445** |
| Mensajes entrantes (cliente) | 11,426 |
| Mensajes salientes (bot/asesor) | 13,019 |
| Emails capturados | 134 |
| Cuentas bancarias capturadas | 51 |
| Documentos recibidos | 1,017 |
| Conversaciones con banderas rojas | **382 (51.5%)** |

### Evaluacion general: 4.5 / 10

**Mas de la mitad de las conversaciones presentan algun problema.** La tasa de resolucion autonoma del bot es de apenas **15.6%** — la mayoria de conversaciones quedan abandonadas o sin resolver. El problema mas grave es el bucle "No entendi tu mensaje" que afecta a 170 conversaciones (23%) y frustra a los usuarios.

### Top 3 problemas criticos
1. **"No entendi tu mensaje" en 780 ocasiones** — el bot no entiende "Ok", "Gracias", "Listo", "Asesor", typos de "Hola", ni mensajes post-formulario
2. **135 conversaciones atascadas** en estados `waiting_for_*` sin resolucion por mas de 24h
3. **68 saludos ("Hola") que reciben recordatorio de documentos** en vez del menu principal

### Top 3 oportunidades de mejora
1. Enrutar texto libre al LLM en vez de responder "No entendi" — convertiria al bot de rigido a conversacional
2. Permitir salir de `waiting_for_docs_rojo` con un saludo para volver al menu
3. Limitar templates repetitivos (51 usuarios recibieron 4+ templates)

---

## 2. METRICAS CUANTITATIVAS

### 2.1 Distribucion por estado final

| Estado | Conversaciones | % |
|--------|---------------|---|
| active | 480 | 64.7% |
| waiting_for_docs_rojo | 120 | 16.2% |
| agent (asesor humano) | 60 | 8.1% |
| lead_notified | 43 | 5.8% |
| waiting_for_email | 22 | 3.0% |
| waiting_for_cuenta_amarillo | 6 | 0.8% |
| pending_consent | 4 | 0.5% |
| waiting_for_cedula | 4 | 0.5% |
| otros (agent_llm, waiting_for_numero_cuenta, etc.) | 3 | 0.4% |

### 2.2 Clasificacion de resultados

| Resultado | Conversaciones | % |
|-----------|---------------|---|
| Resuelta (email/cuenta/docs capturados) | 117 | 15.6% |
| Escalada a asesor humano | 60 | 8.0% |
| Abandonada / sin resolver | 400 | 53.5% |
| Solo template (sin interaccion real) | 17 | 2.3% |
| Atascada en estado waiting_for_* | 154 | 20.6% |

**Tasa de autonomia del bot: 15.6%** — muy baja. El bot resuelve exitosamente solo 1 de cada 6 conversaciones.

### 2.3 Templates enviados

| Template | Envios |
|----------|--------|
| estado_rojo (faltan docs) | 484 |
| estado_verde (aprobado) | 267 |
| estado_amarillo (falta cuenta) | 61 |
| contacto_leads | 35 |

- **51 usuarios recibieron 4 o mas templates** en 15 dias
- Caso extremo: usuarios con 8 templates estado_verde sin respuesta
- Templates estado_rojo enviados sin que el usuario nunca responda: parecen generar fatiga

### 2.4 Actividad de asesores

| Asesor | Mensajes enviados |
|--------|------------------|
| Yulaidis | 1,151 |
| Carol | 125 |

Nota: "Cliente" aparece como asesor (734 mensajes) por un falso positivo en la deteccion — el formato `*Cliente:*` en los resultados de estado coincide con el patron de asesor `*Nombre:*`.

### 2.5 Volumen diario y horario

**Pico de actividad:** 13:00-20:00 UTC (8am-3pm hora Colombia)
**Dias de mayor volumen:** Lunes a Viernes (~2,000-2,900 msgs/dia)
**Fines de semana:** Caen a 80-440 msgs/dia

### 2.6 Banderas rojas detectadas

| Bandera | Conversaciones | Descripcion |
|---------|---------------|-------------|
| NO_ENTENDI_LOOP | **170** | "No entendi" aparece 2+ veces en la conversacion |
| LONG_WAIT_ADVISOR | **137** | Respuesta del asesor tardo mas de 30 min |
| STUCK_STATE | **135** | Atascada en waiting_for_* por mas de 24h |
| DEAD_END | **36** | Ultimo mensaje es del cliente sin respuesta |
| ERROR_SISTEMA | **4** | Error de conexion a base de datos |
| LLM_FALLBACK | **1** | LLM devolvio mensaje de error generico |

---

## 3. PROBLEMAS CRITICOS

### 3.1 CRITICO: "No entendi tu mensaje" — 780 ocurrencias, 170 conversaciones

**Severidad:** ALTA | **Impacto:** 23% de todas las conversaciones | **Causa raiz:** `flows.py:480-481`

Cuando el usuario esta en estado `active` y escribe texto libre que NO es un saludo reconocido, el bot responde "No entendi tu mensaje. Escribe *Hola* para ver el menu principal."

**Los 10 mensajes mas comunes que disparan "No entendi":**

| Mensaje del cliente | Veces | Problema |
|---------------------|-------|----------|
| "Ok" | 52 | Acuse de recibo ignorado |
| "Gracias" | 31 | Agradecimiento ignorado |
| "Listo" | 25 | Confirmacion ignorada |
| "Ya llene el formulario" | 13 | Intent de post-formulario no manejado |
| "Ya lo llene" | 12 | Intent de post-formulario no manejado |
| "Ola" | 12 | Typo de "Hola" no reconocido |
| "Asesor" | 12 | Pedido de asesor no reconocido como texto |
| "Hol" | 9 | Typo de "Hola" no reconocido |
| "Ya" | 7 | Confirmacion ignorada |
| "Si" | 5 | Afirmacion ignorada |

Otros patrones importantes:
- Typos de "Hola": "Hl", "Hla", "Holq", "Holaaa", "Ho", "H" — ninguno reconocido
- "Menu" con acento ("Menu") — no reconocido
- "Hablar con un asesor" / "Comunicarme con un asesor" / "Necesito hablar con un asesor" — no reconocidos como texto libre
- "Ya firme el contrato" / "No me ha llegado el contrato" / "Ya envie todo" — intents valiosos perdidos
- Emails enviados fuera del estado waiting_for_email — ignorados

**Ejemplo real (573045551967 — DONALDO MONTOYA):**
```
CLIENTE: Ya les mande todos los documentos
BOT: No entendi tu mensaje. Escribe 'Hola' para ver el menu principal.
CLIENTE: Ya les mande los documentos
BOT: No entendi tu mensaje. Escribe 'Hola' para ver el menu principal.
CLIENTE: Disculpen ya envie la documentacion
BOT: No entendi tu mensaje. Escribe 'Hola' para ver el menu principal.
```
El cliente envio 7 documentos y el bot los ignoro porque no estaba en `waiting_for_docs_rojo`.

**Fix propuesto:** Detallado en Plan de Mejoras seccion 7.1.

---

### 3.2 CRITICO: Estado `waiting_for_docs_rojo` atrapa al usuario

**Severidad:** ALTA | **Impacto:** 120 conversaciones atascadas, 367 doc reminders enviados, 68 saludos ignorados

Cuando el usuario esta en `waiting_for_docs_rojo` y escribe CUALQUIER texto que no sea "asesor"/"ayuda"/"help", el bot responde con el recordatorio de documentos faltantes. Esto incluye saludos como "Hola" (68 veces).

**Causa raiz:** `flows.py:348-370` — el handler de `waiting_for_docs_rojo` no permite al usuario salir del flujo con un saludo.

**Ejemplo real (573162394308 — YEISON JAVIER MORALES):**
```
CLIENTE: Apenas tenga los desprendible de pago se los mando
BOT: [Recordatorio de docs] [Botones: Cargar documentos, Ya los envie, Hablar con un asesor]
CLIENTE: No los tengo los perdi yo los pido a la empresa
BOT: [Recordatorio de docs] [Botones: Cargar documentos, Ya los envie, Hablar con un asesor]
[3 dias despues]
CLIENTE: Hola
BOT: [Recordatorio de docs]  <-- deberia mostrar menu
[5 dias sin respuesta, 2 templates mas enviados]
```

**Problemas derivados:**
- 20 conversaciones reciben 3+ recordatorios de docs repetidos
- El usuario no puede acceder a otras funciones (saldo, otro estado, etc.)
- Templates siguen enviandose a usuarios atascados (template fatigue)

---

### 3.3 ALTO: Templates repetitivos sin control (template fatigue)

**Severidad:** ALTA | **Impacto:** 51 usuarios recibieron 4+ templates

El sistema de automatizacion envia templates diarios sin limite maximo. Casos extremos:
- 5 usuarios recibieron **8 templates** en 15 dias
- Algunos reciben estado_verde repetido diariamente sin que hayan respondido al anterior

**Causa raiz:** `automation.py` — el filtro `get_notified_phones_batch` solo verifica si se notifico HOY. No hay limite total de envios.

**Consecuencia:** Los mensajes de ProAlto pueden ser marcados como spam por WhatsApp, afectando el Quality Rating del numero de negocio.

---

### 3.4 ALTO: 22 conversaciones atascadas en `waiting_for_email`

**Severidad:** ALTA | **Impacto:** 22 conversaciones, emails nunca capturados

Usuarios quedan en `waiting_for_email` indefinidamente cuando:
1. Envian imagenes en vez de escribir un email (4 casos)
2. Nunca responden al template verde (estado cambia a waiting_for_email pero el usuario no entiende que debe enviar un email)
3. El template verde se reenvia multiples veces — cada "Acepto las condiciones" vuelve a pedir email

**Ejemplo real (573145322112):**
```
BOT: [Template: estado_verde]
BOT: [Template: estado_verde]  <-- segundo envio
CLIENTE: [IMAGEN]              <-- envia imagen en vez de email
CLIENTE: Acepto las condiciones
BOT: Por favor envianos tu correo electronico
CLIENTE: [IMAGEN]              <-- sigue enviando imagenes, no entiende
BOT: [Template: estado_verde]  <-- tercer envio
CLIENTE: Acepto las condiciones <-- de nuevo
BOT: Por favor envianos tu correo electronico
CLIENTE: [IMAGEN]              <-- nunca envio el email
```

---

### 3.5 MEDIO: Consulta de estado intermitente — 149 "no encontramos solicitud"

**Severidad:** MEDIA | **Impacto:** 149 consultas fallidas

Hay 149 ocurrencias de "No encontramos ninguna solicitud reciente con la cedula X". En varios casos, el MISMO usuario consulta la MISMA cedula y a veces funciona y a veces no.

**Ejemplo real (573117776323 — CARLOS BAEZ):**
```
18:28:49 - Cedula: 6099212
18:29:01 - BOT: No encontramos ninguna solicitud reciente
[30 segundos despues, vuelve a intentar]
18:29:53 - Cedula: 6099212
18:29:54 - BOT: CARLOS ALBERTO BAEZ GONZALEZ - APROBADA - $2,600,000
```

**Causa probable:** Timeout o error transitorio en la consulta al Cloud Run API (`database.py:get_solicitud_status`). La segunda consulta funciona porque el servicio ya esta "caliente".

---

### 3.6 MEDIO: LLM revela su identidad de IA

**Severidad:** MEDIA | **Impacto:** 1 conversacion confirmada, potencialmente mas

En la conversacion de prueba (573106176713), el LLM rompio dos reglas criticas:
1. Admitio ser IA: "soy el asistente virtual de ProAlto"
2. Uso frase prohibida: "te conecto con un asesor que pueda ayudarte mejor"

**Causa raiz:** `llm.py` system prompt — las prohibiciones estan claras pero el modelo (Haiku) las viola bajo presion directa ("Pero tu no eres un asesor?", "Pense que tu eras un humano").

**Nota adicional:** Solo hay 1 conversacion en modo `agent_llm` en los 15 dias, lo que sugiere que esta funcionalidad no esta siendo utilizada activamente en produccion.

---

### 3.7 BAJO: 4 errores de sistema (Error del Sistema)

**Severidad:** BAJA | **Impacto:** 4 conversaciones

Errores de conexion al Cloud Run API para consulta de saldo. En todos los casos, el reintento funciono. Indica que el Cold Start de Cloud Run genera timeouts esporadicos.

---

## 4. PUNTOS DE FRICCION DEL USUARIO

### 4.1 El bot no entiende lenguaje natural
El flujo actual es 100% basado en botones. Cuando el usuario escribe texto libre (que no es un saludo), el bot falla. El 23% de conversaciones sufre esto.

### 4.2 No hay forma de "confirmar que ya hice algo"
Cuando el usuario dice "Ya llene el formulario" (13 veces), "Ya lo llene" (12 veces), "Ya firme el contrato" (2 veces), "Ya envie todo" (2 veces) — el bot no tiene ningun handler para estas confirmaciones. Son intents valiosos que se pierden.

### 4.3 Los estados son prisiones
Una vez en `waiting_for_docs_rojo`, el usuario no puede hacer nada mas que enviar documentos o pedir asesor. No puede:
- Consultar su estado
- Ver el menu
- Hacer una pregunta
- Decir que no tiene los documentos todavia

### 4.4 El "Soy Cliente" sub-menu es innecesario
El flujo Hola → [Soy Cliente, Estado Solicitud, Solicitar Credito] → Soy Cliente → [Consultar Saldo, Hablar con Asesor, Volver al Inicio] agrega un paso innecesario. Los 4-5 opciones principales podrian estar en un solo menu.

### 4.5 Template verde re-pide email a quien ya lo dio
El template estado_verde se envia diariamente. Si el usuario ya envio su email, sigue recibiendo templates con "Acepto las condiciones" que vuelve a pedir email. Hay duplicados de emails capturados (ej: el mismo email guardado 2-3 veces para el mismo usuario).

---

## 5. ANALISIS DE CALIDAD DEL LLM

### 5.1 Uso minimo del LLM
Solo 1 conversacion en modo `agent_llm` en 15 dias. El LLM esta subutilizado — la gran mayoria de conversaciones pasan por flujos estructurados.

### 5.2 Problemas detectados (en la unica conversacion LLM)
1. **Revelo identidad de IA** cuando el usuario pregunto directamente
2. **Uso frase prohibida** "te conecto con un asesor"
3. **Formato**: Uso parrafos largos con estructura de lista (deberia ser 2-3 frases cortas)
4. **Fallback generico**: "Dejame verificar eso y te confirmo en un momento" cuando el LLM fallo

### 5.3 Oportunidad
El LLM deberia ser el handler por defecto para texto libre en estado `active`, en lugar del "No entendi". Esto resolveria el problema #1 (780 "No entendi") de un solo golpe.

---

## 6. OPORTUNIDADES PERDIDAS

### 6.1 Cada "No entendi" es una oportunidad perdida
780 veces el bot fallo en entender al usuario. Si esos mensajes se hubieran enrutado al LLM:
- "Ok" / "Gracias" / "Listo" → respuesta amable de cierre
- "Ya llene el formulario" → confirmacion + siguiente paso
- "Asesor" → escalacion
- Preguntas libres → respuesta informada con contexto de ProAlto

### 6.2 Documentos enviados fuera de `waiting_for_docs_rojo`
Clientes envian documentos proactivamente (antes del template rojo), pero el bot no los registra ni confirma.

### 6.3 Formulario sin seguimiento
13+ usuarios dicen "Ya llene el formulario" pero no hay mecanismo para verificar o dar siguiente paso.

---

## 7. PLAN DE MEJORAS

### P1: CRITICOS — Implementar inmediatamente

#### 7.1 Enrutar texto libre al LLM en vez de "No entendi"
**Archivo:** `src/flows.py:466-481`
**Cambio:** Reemplazar el bloque final que responde "No entendi" por una llamada al LLM (`ask_llm`). Agregar primero un reconocimiento de "acuses de recibo" (ok, gracias, listo, si, bien, perfecto, entendido) con respuesta corta, y para todo lo demas, enrutar al LLM.

```python
# Antes (actual):
else:
    WhatsAppService.send_message(user_phone, "No entendi tu mensaje...")

# Despues (propuesto):
else:
    # Reconocer acuses de recibo
    ack_words = ["ok", "okay", "gracias", "listo", "si", "bien", "perfecto",
                 "entendido", "dale", "claro", "vale", "muchas gracias", "thanks"]
    if norm_text in ack_words or norm_text.rstrip(".!,") in ack_words:
        WhatsAppService.send_message(user_phone,
            "Con gusto. Si necesitas algo mas, escribe Hola para ver el menu.")
    else:
        # Enrutar al LLM para respuesta inteligente
        from src.llm import ask_llm
        client_name = get_client_name(user_phone)
        response = ask_llm(user_phone, text, state, client_name)
        # Manejar tags especiales del LLM
        if "[MOSTRAR_MENU]" in response:
            human_msg = response.replace("[MOSTRAR_MENU]", "").strip()
            if human_msg:
                WhatsAppService.send_message(user_phone, human_msg)
            FlowHandler.send_main_menu(user_phone)
        elif "[HABLAR_ASESOR]" in response:
            human_msg = response.replace("[HABLAR_ASESOR]", "").strip()
            if human_msg:
                WhatsAppService.send_message(user_phone, human_msg)
            set_agent_mode(user_phone, "agent")
            notify_admin_agent_request(user_phone)
        elif "[REGISTRAR_SOLICITUD:" in response:
            match = re.search(r'\[REGISTRAR_SOLICITUD:([^\]]+)\]', response)
            tipo = match.group(1).strip() if match else "general"
            human_msg = re.sub(r'\[REGISTRAR_SOLICITUD:[^\]]+\]', '', response).strip()
            if human_msg:
                WhatsAppService.send_message(user_phone, human_msg)
            from src.conversation_log import save_llm_request
            from src.notifications import notify_admin_llm_request
            save_llm_request(user_phone, client_name, tipo, text)
            notify_admin_llm_request(user_phone, tipo)
        else:
            WhatsAppService.send_message(user_phone, response)
```

**Impacto esperado:** Elimina el 100% de los "No entendi" (780 mensajes, 170 conversaciones).

#### 7.2 Ampliar reconocimiento de saludos (fuzzy matching)
**Archivo:** `src/flows.py:468`
**Cambio:** Agregar typos comunes de "Hola" a la lista de greetings.

```python
greetings = ["hola", "menu", "menú", "inicio", "start", "buenas", "holis",
             "holi", "saludos", "hi", "hello", "buen", "buenos",
             "ola", "hol", "hl", "hla", "holq", "holaaa", "ho"]
```

**Impacto:** Resuelve ~40 conversaciones con typos.

#### 7.3 Permitir salir de `waiting_for_docs_rojo` con saludo
**Archivo:** `src/flows.py:348-370`
**Cambio:** Agregar deteccion de saludos al inicio del handler de `waiting_for_docs_rojo` para permitir al usuario volver al menu.

```python
if state == "waiting_for_docs_rojo":
    # Permitir salir con saludo
    norm = text.lower().strip()
    if norm in ["hola", "menu", "inicio", "salir", "volver"]:
        set_user_state(user_phone, "active")
        FlowHandler.send_main_menu(user_phone)
        return
    if norm in ["asesor", "asesor humano", "ayuda", "help"]:
        # ... handler existente de asesor
```

**Impacto:** Resuelve 68 saludos atrapados + libera 20 conversaciones en loops de doc reminders.

#### 7.4 Limitar templates repetitivos
**Archivo:** `src/automation.py`
**Cambio:** Agregar limite maximo de 3 envios del mismo template por usuario.

```python
# En get_pending_approved_notifications y similares:
# Agregar filtro: si send_count >= 3, excluir
if u["send_count"] >= 3:
    reasons.append("Limite de 3 envios alcanzado")
```

**Impacto:** Evita fatiga de templates en 51 usuarios. Protege Quality Rating de WhatsApp.

---

### P2: MEJORAS DE FLUJO — 1-2 semanas

#### 7.5 Handler para "Ya llene el formulario"
**Archivo:** `src/flows.py` (nuevo handler en `process_text_input`)
**Cambio:** Detectar intents de post-formulario y responder adecuadamente.

Intent patterns: "ya llene", "ya lo llene", "ya envie", "ya lo hice", "ya firme"
Respuesta: "Gracias por completar el formulario. Nuestro equipo revisara tu informacion y te contactaremos pronto. Puedes consultar el estado de tu solicitud en cualquier momento."

**Impacto:** 21+ conversaciones resueltas.

#### 7.6 Confirmar recepcion de documentos en cualquier estado
**Archivo:** `src/flows.py:100-123`
**Cambio:** Cuando el usuario envia documentos en estado `active` (no solo en `waiting_for_docs_rojo`), registrarlos y confirmar recepcion.

**Impacto:** Resuelve el patron de clientes que envian documentos proactivamente y son ignorados.

#### 7.7 Mejorar flujo de `waiting_for_email`
**Archivo:** `src/flows.py:314-345`
**Cambios:**
1. Si el usuario envia una imagen en `waiting_for_email`, responder: "Necesitamos que nos escribas tu correo electronico (ej: tucorreo@email.com), no una imagen."
2. Si el template verde se reenvia y el usuario ya envio email, NO pedir email de nuevo
3. Agregar timeout: si pasan 48h sin email, cambiar estado a `active`

**Impacto:** 22 conversaciones atascadas.

#### 7.8 Simplificar menu principal (eliminar sub-menu "Soy Cliente")
**Archivo:** `src/flows.py` — `send_main_menu` y `send_client_menu`
**Cambio:** Combinar en un solo menu con las opciones principales: Estado Solicitud, Solicitar Credito, Consultar Saldo, Hablar con Asesor.

**Impacto:** Reduce friccion para todos los usuarios, elimina 1 paso innecesario.

#### 7.9 Manejar Cold Start de Cloud Run
**Archivo:** `src/database.py`
**Cambio:** Agregar retry automatico (1 reintento con 2s delay) cuando la consulta al Cloud Run API falla.

**Impacto:** Resuelve 4 ERROR_SISTEMA y reduce los 149 "no encontramos solicitud" intermitentes.

---

### P3: MEJORAS LLM/PROMPT — Continuo

#### 7.10 Reforzar prohibicion de revelar identidad IA
**Archivo:** `src/llm.py:43-139` (system prompt)
**Cambio:** Agregar ejemplo explicito en el prompt:

```
**Si el cliente pregunta "eres un bot?" o "eres humano?" o "eres IA?":**
RESPONDE: "Claro que si, soy del equipo de ProAlto. ?En que te puedo ayudar?"
NUNCA digas: "soy el asistente virtual", "soy un bot", "soy IA", "tienes razon, soy..."
```

#### 7.11 Actualizar contexto del LLM para post-formulario
**Archivo:** `context/capacidades_bot.md` o `context/faq.md`
**Cambio:** Agregar seccion sobre que decir cuando el cliente dice que ya lleno el formulario, ya envio documentos, o ya firmo el contrato.

#### 7.12 Ajustar formato de respuesta LLM
El LLM a veces genera respuestas largas con estructura. Reforzar en el prompt:
- Maximo 2-3 frases
- Sin listas
- Sin parrafos

---

### P4: FEATURES NUEVOS — Backlog

#### 7.13 Deteccion inteligente de cedula en texto libre
Cuando el usuario escribe un numero de 6-12 digitos en cualquier estado, ofrecer: "Parece que enviaste un numero de cedula. Quieres que consulte tu solicitud?"

#### 7.14 Dashboard de template fatigue
En el admin panel, mostrar cuantos templates ha recibido cada usuario y permitir excluir manualmente.

#### 7.15 Auto-cierre de conversaciones stale
Si una conversacion en `waiting_for_*` no tiene actividad en 72h, cambiarla automaticamente a `active`.

#### 7.16 Notificacion al admin de conversaciones DEAD_END
Cuando el ultimo mensaje es del cliente y pasan 2h sin respuesta del bot ni del asesor, notificar al admin.

#### 7.17 Corregir falso positivo de deteccion de asesor
**Archivo:** `src/analytics_queries.py:18-20`
El patron `*Name:*` detecta falsamente los mensajes de estado del bot que contienen `*Cliente:*`. Agregar exclusion:

```python
def _is_advisor_message(text: str) -> bool:
    if not text or '*Cliente:*' in text:
        return False
    return '*' in text and ':*' in text
```

---

## 8. CONVERSACIONES DESTACADAS (EJEMPLOS)

### Ejemplo 1: "No entendi" frustra a cliente con documentos (573045551967)
Cliente envio 7 fotos de documentos y escribio 4 veces que ya los habia enviado. El bot respondio "No entendi" las 4 veces. Los documentos no fueron registrados porque no estaba en `waiting_for_docs_rojo`. **Demuestra la necesidad de 7.1 y 7.6.**

### Ejemplo 2: Estado `waiting_for_docs_rojo` como trampa (573162394308)
Cliente explica que no tiene los desprendibles y que los pedira a la empresa. El bot responde con el mismo recordatorio de docs. El cliente no puede hacer nada mas. Recibe 5 templates en 10 dias. **Demuestra la necesidad de 7.3 y 7.4.**

### Ejemplo 3: Template verde repetitivo sin resolucion (573145322112)
Cliente recibe 4+ templates estado_verde. Cada vez presiona "Acepto las condiciones" y el bot pide email. El cliente envia imagenes en vez de email. Nunca se resuelve. **Demuestra la necesidad de 7.4 y 7.7.**

### Ejemplo 4: LLM revela identidad (573106176713)
El LLM dice "soy el asistente virtual de ProAlto" y "te conecto con un asesor". Cliente responde "Pense que tu eras un humano". **Demuestra la necesidad de 7.10.**

### Ejemplo 5: Consulta de estado intermitente (573117776323)
Mismo usuario, misma cedula: primera consulta da "no encontramos", segunda consulta (30 seg despues) funciona perfectamente. **Demuestra la necesidad de 7.9.**

### Ejemplo 6: 52 clientes dicen "Ok" y el bot no entiende
Patron universal: el bot da informacion, el cliente dice "Ok" como acuse de recibo, el bot responde "No entendi". **Demuestra la necesidad de 7.1.**

---

## 9. RESUMEN DE IMPACTO ESPERADO

| Mejora | Conversaciones impactadas | Esfuerzo |
|--------|--------------------------|----------|
| 7.1 Texto libre → LLM | 170+ | 2-3 horas |
| 7.2 Fuzzy greetings | ~40 | 15 min |
| 7.3 Salir de waiting_for_docs_rojo | 68+ | 30 min |
| 7.4 Limitar templates | 51 | 1 hora |
| 7.5 Handler post-formulario | 21+ | 1 hora |
| 7.6 Docs en cualquier estado | Variable | 2 horas |
| 7.7 Mejorar waiting_for_email | 22 | 2 horas |
| 7.8 Simplificar menu | Todas | 1 hora |
| 7.9 Retry Cloud Run | 149+ | 30 min |
| 7.10 Reforzar prompt LLM | Preventivo | 15 min |

**Implementando solo P1 (7.1-7.4) se resuelve el ~60% de las banderas rojas.**

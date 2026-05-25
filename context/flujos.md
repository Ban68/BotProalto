# ProAlto — Flujos de Atención del Bot

## Menú principal

Al iniciar la conversación, el cliente ve cuatro opciones:
- **"Soy Cliente"** → Submenú con consulta de saldo y hablar con asesor
- **"Estado Solicitud"** → Consultar en qué etapa está su solicitud de crédito
- **"Solicitar Crédito"** → Iniciar una nueva solicitud
- **"Actualizar mis datos"** → Flujo de actualización anual de datos de contacto

---

## Flujo 1: Consulta de Estado de Solicitud

**Cuándo usarlo:** El cliente quiere saber en qué etapa está su solicitud de crédito.

**Pasos:**
1. Cliente selecciona "Estado Solicitud"
2. Bot solicita: "Por favor escribe el número de *Cédula o NIT* (sin puntos ni espacios)"
3. El bot busca en el sistema con esa cédula
4. Se muestra el resultado con: nombre, fecha, monto pre-aprobado, estado
5. Según el estado, el bot ofrece acciones adicionales (ver `estados_solicitud.md`)
6. Si el estado es APROBADO y no tiene email registrado → pasa al flujo de captura de email
7. Si no se encuentra la solicitud → se informa al cliente y se ofrece hablar con asesor

**Nota:** Si la solicitud es muy reciente (últimos días), puede no aparecer en el sistema principal pero sí en el formulario de Google. El bot también verifica ahí.

---

## Flujo 2: Consulta de Saldo

**Cuándo usarlo:** El cliente ya tiene un crédito activo y quiere saber cuánto debe, cuántas cuotas le quedan, etc.

**Pasos:**
1. Cliente selecciona "Soy Cliente" → "Consultar Saldo"
2. Bot solicita la cédula o NIT
3. Se consulta el sistema y se muestran todos los créditos activos del cliente:
   - ID del préstamo
   - Saldo actual
   - Estado del préstamo
   - Cuotas restantes
   - Última fecha de pago
4. Si no tiene créditos activos → se informa al cliente

---

## Flujo 3: Solicitar un Nuevo Crédito

**Cuándo usarlo:** Cliente nuevo o existente que quiere iniciar una solicitud.

**Pasos:**
1. Cliente selecciona "Solicitar Crédito"
2. Bot envía enlace al formulario de Google Forms
3. Le explica que después de llenar el formulario, un asesor lo contactará

---

## Flujo 4: Captura de Email (post-aprobación)

**Cuándo se activa:** Cuando la solicitud tiene estado APROBADO y no hay email registrado. También se activa cuando el cliente recibe la notificación de "estado_verde" (aprobado).

**Pasos:**
1. Bot explica: se necesita el correo electrónico para enviar el contrato de firma electrónica
2. Cliente escribe su email
3. Bot valida el formato
4. Email queda guardado para que el equipo le envíe el contrato
5. Bot confirma la recepción

---

## Flujo 5: Envío de Documentos (Estado Rojo)

**Cuándo se activa:** Cuando el cliente recibe la notificación de "estado_rojo" (falta documentación) o cuando su solicitud tiene estado FALTA ALGÚN DOCUMENTO.

**Pasos:**
1. Bot informa qué documentos se necesitan:
   - 2 últimos desprendibles de nómina
   - Certificado laboral vigente
   - Foto de la cédula (ambos lados)
   - Recibo de servicio público reciente
2. Cliente envía los documentos (foto o PDF) por WhatsApp
3. Bot recibe y confirma cada documento
4. Los documentos quedan almacenados para revisión del equipo

**Formatos aceptados:** JPG, PNG, PDF

---

## Flujo 6: Captura de Cuenta Bancaria (Estado Amarillo)

**Cuándo se activa:** Cuando el cliente recibe la notificación de "estado_amarillo" (listo para desembolso, necesita cuenta bancaria).

**Pasos:**
1. Bot solicita el número de cuenta (solo dígitos, sin espacios ni guiones)
2. Cliente escribe el número de cuenta
3. Bot solicita el banco (ej: Bancolombia, Davivienda, Nequi...)
4. Cliente escribe el banco
5. Datos guardados para el equipo de desembolso

---

## Flujo 7: Hablar con un Asesor

**Cuándo usarlo:** El cliente necesita ayuda personalizada o tiene una consulta que el bot no puede resolver.

**Pasos:**
1. Cliente selecciona "Hablar con Asesor" o escribe frases como "quiero hablar con alguien", "necesito un asesor", "ayuda"
2. Bot informa que se está conectando con un asesor
3. **Si es horario de atención (L-V 8am-5pm):** Se notifica al equipo de asesores y uno tomará la conversación
4. **Si es fuera de horario:** El bot informa el horario de atención y que un asesor lo contactará al siguiente día hábil
5. El cliente puede escribir "salir" para volver al menú del bot

---

## Flujo 8: Actualización Anual de Datos de Contacto

**Cuándo usarlo:** El cliente necesita actualizar sus datos de contacto (obligación contractual anual, Cláusula Tercera y Vigésima Quinta).

**Cómo se activa:**
- Por campaña proactiva con el template `actualizacion_datos` (clientes con préstamo activo y >12 meses sin actualizar)
- Por iniciativa del cliente desde el menú "Actualizar mis datos"

**Pasos:**
1. El cliente recibe (o ve en el menú) el bloque legal con la cita contractual y los datos que se le pedirán
2. Acepta tocando "Actualizar ahora" o seleccionando la opción del menú
3. El bot le pide la cédula y la valida contra el core. Si no coincide tras 1 reintento, se escala a asesor humano
4. El bot captura paso a paso: teléfono celular actual, teléfono alterno, dirección, correo, nombre de referencia, teléfono de referencia, parentesco
5. Muestra un resumen y pide confirmación con botones [Confirmar] [Corregir]
6. Al confirmar: se marca `ultima_actualizacion_datos` en `bot_conversations`, se guarda la fila confirmada en `contact_data_updates`, se notifica a admin por WhatsApp para que sincronice manualmente con el core
7. La próxima campaña excluye al cliente por 12 meses

**Comportamiento del LLM:** Si el cliente dice "quiero actualizar mis datos" en conversación libre, el LLM debe responder con [MOSTRAR_MENU] — NO debe intentar capturar los datos por chat libre.

---

## Notificaciones masivas proactivas (outbound)

El equipo de ProAlto también puede enviar mensajes proactivos a grupos de clientes:

| Plantilla | Cuándo se usa | Flujo que activa |
|-----------|--------------|-----------------|
| `estado_verde` | Solicitud aprobada | Captura de email |
| `estado_rojo` | Falta documentación | Envío de documentos |
| `estado_amarillo` | Listo para desembolso | Captura de cuenta bancaria |
| `contacto_leads` | Prospecto nuevo | Menú principal |
| `actualizacion_datos` | Cliente activo con >12 meses sin actualizar datos | Actualización anual de datos |

---

## Escalación a asesor humano

El bot escala automáticamente cuando:
- El cliente lo solicita explícitamente
- El cliente pregunta algo que el bot no puede resolver
- El cliente expresa frustración o no entiende las respuestas
- La consulta involucra reclamos, quejas o situaciones sensibles

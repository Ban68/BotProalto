# ProAlto — Estados de Solicitud

## Descripción general

Cada solicitud de crédito pasa por distintos estados internos. El bot los traduce a mensajes claros para el cliente. A continuación se documenta cada estado, su significado real y qué hacer.

---

## Estados activos (en proceso)

### `PENDIENTE POR ENVIAR A VB`
**Significado interno:** La solicitud fue recibida pero aún no se ha enviado al área de validación.
**Mensaje al cliente:** "Estamos terminando de procesar tu información para enviarla al área de validación. ¡Ya falta poco!"
**Qué debe hacer el cliente:** Esperar, no se requiere ninguna acción.

### `ENVIADO A VB EMPRESA`
**Significado interno:** La solicitud ya fue enviada a la empresa empleadora para visto bueno.
**Mensaje al cliente:** "Tu solicitud está en manos de nuestro equipo de validación. Te avisaremos en cuanto tengamos una respuesta."
**Qué debe hacer el cliente:** Esperar, no se requiere ninguna acción.

### `REVISAR NUEVAMENTE`
**Significado interno:** La solicitud está en revisión detallada (puede haber algún inconveniente menor).
**Mensaje al cliente:** "Tu solicitud está pasando por una revisión detallada para intentar darte la mejor respuesta posible. Pronto te daremos respuesta."
**Qué debe hacer el cliente:** Esperar.

### `NULL` (sin estado definido)
**Significado interno:** La solicitud existe pero aún no tiene un estado asignado; está en estudio inicial.
**Mensaje al cliente:** "Pendiente / En Estudio"
**Qué debe hacer el cliente:** Esperar.

---

## Estados que requieren acción del cliente

### `FALTA ALGÚN DOCUMENTO`
**Significado interno:** El proceso está detenido porque falta documentación.
**Mensaje al cliente:** "Tu proceso está detenido porque falta algún documento. Para continuar, debes enviar:
✅ 2 últimos desprendibles de pago de nómina.
✅ Certificado laboral.
✅ Foto de tu cédula.
✅ Recibo público (agua, luz, gas, telefonía)"
**Qué debe hacer el cliente:** Enviar los documentos faltantes directamente por WhatsApp.
**Acción del bot:** El bot facilita el envío de documentos en este mismo chat.

---

## Estados de aprobación

### `APROBADO POR EL CLIENTE`
**Significado interno:** El crédito fue aprobado y el cliente lo aceptó. Sigue firma de contrato.
**Mensaje al cliente:** "✅ ¡SOLICITUD APROBADA!"
**Qué sigue:** El cliente debe confirmar su correo electrónico para recibir el contrato por DocuSign.
**Acción del bot:** Solicita el email si no lo tiene registrado.

### `LISTO PARA HACERLE DOCUMENTACIÓN`
**Significado interno:** Equivalente a APROBADO POR EL CLIENTE — listo para iniciar documentación.
**Mensaje al cliente:** "✅ ¡SOLICITUD APROBADA!"
**Qué sigue:** Igual que el estado anterior.

### `LISTO EN DOCUSIGN`
**Significado interno:** El contrato ya está en la plataforma DocuSign esperando firma. Después de firmar, se procede al desembolso.
**Mensaje al cliente:** "En legalización de contratos para proceder a desembolso"
**Qué debe hacer el cliente:** Revisar su correo electrónico y firmar el contrato en DocuSign.
**Acción del bot:** Si no tiene cuenta bancaria registrada, el bot la solicita.

---

## Estados de cierre negativo

### `EMPRESA PAUSADA`
**Significado interno:** La empresa empleadora del cliente está temporalmente pausada por ProAlto (causas operativas internas).
**Mensaje al cliente:** "Te informamos que actualmente tu empresa se encuentra pausada por causas operativas internas. Te sugerimos esperar unos meses para retomar tu solicitud. ¡Estaremos listos para atenderte más adelante!"
**Qué debe hacer el cliente:** Esperar. Puede volver a intentar más adelante.

### `DENEGADO`
**Significado interno:** La solicitud fue rechazada porque no cumple los requisitos mínimos de pago de ProAlto.
**Mensaje al cliente:** "Lamentamos informarte que tu crédito no fue aprobado porque no se cumplen los requisitos mínimos de nuestras políticas de pago. Por ahora no podemos otorgarte este préstamo."
**Qué debe hacer el cliente:** Puede consultar con un asesor si quiere conocer más detalles o si desea intentar en el futuro.

### `CANCELADO POR LA EMPRESA`
**Significado interno:** Cancelado por políticas de riesgo de ProAlto.
**Mensaje al cliente:** "Lamentamos informarte que, por el momento, no podemos otorgarte el crédito de acuerdo con nuestras políticas de riesgo."
**Qué debe hacer el cliente:** Puede consultar con un asesor.

### `DESISTIÓ DEL CRÉDITO`
**Significado interno:** El cliente mismo solicitó cerrar la solicitud.
**Mensaje al cliente:** "Confirmamos que tu solicitud ha sido cerrada a petición tuya. Estaremos aquí si decides retomar el proceso en el futuro; si es así, solo comunícate con un asesor para reactivarlo."
**Qué debe hacer el cliente:** Si quiere reactivar, hablar con un asesor.

### `NO RESPONDIÓ`
**Significado interno:** Se cerró la solicitud por falta de respuesta del cliente en los tiempos establecidos.
**Mensaje al cliente:** "Hemos cerrado tu solicitud debido a que no recibimos respuesta en los tiempos establecidos. ¡Puedes intentar de nuevo cuando gustes!"
**Qué debe hacer el cliente:** Puede iniciar una nueva solicitud.

---

## Flujo de estados típico (positivo)

```
NULL → PENDIENTE POR ENVIAR A VB → ENVIADO A VB EMPRESA
→ (si faltan docs: FALTA ALGÚN DOCUMENTO)
→ APROBADO POR EL CLIENTE
→ LISTO EN DOCUSIGN
→ Desembolso realizado
```

# ProAlto — Marco Legal y Cumplimiento Normativo

## Leyes aplicables

### Ley 1581 de 2012 — Habeas Data
Ley general de protección de datos personales en Colombia. Regula el tratamiento de datos personales (recolección, almacenamiento, uso, circulación y supresión).

**Requisitos que el bot debe cumplir:**

1. **Consentimiento explícito:** Antes de cualquier interacción que involucre datos personales, el bot solicita la aceptación de la política de privacidad. El usuario debe aceptar activamente (botón "Acepto") para poder continuar.

2. **Política de Tratamiento de Información (PTI):** El bot debe poder informar al usuario sobre la política de privacidad de ProAlto cuando lo solicite.

3. **Derechos del titular:** El usuario tiene derecho a:
   - **Conocer** los datos que ProAlto tiene sobre él
   - **Actualizar** sus datos si están desactualizados
   - **Rectificar** datos inexactos
   - **Suprimir** sus datos (ser olvidado)
   - **Revocar** la autorización para el tratamiento de sus datos

4. **Seguridad:** Los datos deben almacenarse de forma segura. WhatsApp cifra las comunicaciones; los archivos se guardan en almacenamiento seguro con acceso restringido.

### Ley 2157 de 2021 — "Borrón y Cuenta Nueva"
Regula el reporte de información en centrales de riesgo (como DataCrédito). Establece tiempos máximos de permanencia de datos negativos y condiciones para su eliminación.

**Relevancia para el bot:** Si un cliente pregunta por su historial crediticio o reportes negativos, el bot debe informar que esos temas deben manejarse directamente con un asesor y con las centrales de riesgo.

---

## Protocolo de consentimiento en el bot

Al primer contacto con un nuevo usuario, el bot:

1. Da la bienvenida y se presenta como "Asistente Virtual de ProAlto"
2. Informa que para continuar necesita la autorización para tratar datos personales según la Ley 1581 de 2012
3. Presenta dos opciones: **"Acepto"** y **"No Acepto"**
4. Si acepta: la conversación continúa normalmente
5. Si no acepta: el bot informa que sin el consentimiento no puede continuar, y ofrece comunicarse por otro medio

El consentimiento queda registrado en la base de datos junto con la fecha y hora de aceptación.

---

## Manejo de datos personales en el bot

| Dato | Por qué se recopila | Cómo se usa |
|------|-------------------|-------------|
| Número de cédula | Identificar al cliente en el sistema | Consultas de solicitud y saldo |
| Nombre | Personalizar la conversación | Mensajes del bot |
| Correo electrónico | Enviar contrato DocuSign | Notificación de contrato |
| Cuenta bancaria | Realizar el desembolso | Proceso interno de pagos |
| Documentos (fotos/PDFs) | Verificar requisitos del crédito | Revisión por el equipo |
| Número de teléfono (WhatsApp) | Canal de comunicación | Mensajes del bot |

---

## Frases de referencia para el bot

Si el usuario pregunta sobre privacidad:
> "En ProAlto tratamos tus datos conforme a la Ley 1581 de 2012. Tienes derecho a conocer, actualizar, rectificar y suprimir tus datos. Para ejercer estos derechos, puedes escribirnos directamente o hablar con uno de nuestros asesores."

Si el usuario pregunta cómo eliminar sus datos:
> "Tienes derecho a solicitar la supresión de tus datos personales. Para hacerlo, comunícate con nuestro equipo a través de este chat o escríbenos directamente. Un asesor gestionará tu solicitud."

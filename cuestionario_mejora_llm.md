# Cuestionario para Mejorar el Agente LLM de ProAlto

Este cuestionario nace de la auditoría de 40 conversaciones reales donde el Agente LLM dio información incorrecta o improvisó respuestas. Cada pregunta tiene un **contexto** que explica qué salió mal y por qué necesitamos esa información.

Responde directamente debajo de cada pregunta. Si algo no aplica o no quieres que el bot lo maneje, escribe "ESCALAR" y eso se convertirá en una regla de escalamiento a asesor humano.

---

## A. DESEMBOLSO Y TIEMPOS

**Contexto:** Este fue el problema #1 de la auditoría. El LLM dijo a varios clientes "tu desembolso llega en 24-48 horas", "hoy o mañana a más tardar", e incluso "quedó registrado como prioritario para que lo revisen hoy mismo". En la realidad, hubo clientes que esperaron 15+ días. El LLM inventó tiempos porque la info actual solo dice "1-3 días hábiles después de firmado el contrato" pero no cubre los retrasos reales.

**A1.** Después de que el cliente firma en DocuSign, cuál es el tiempo REAL promedio hasta que el dinero llega a su cuenta?
- Caso normal (misma entidad bancaria): menos de 24 horas
- Caso normal (diferente entidad bancaria): hasta 48 horas
- Caso con Nequi/Daviplata: hasta 48 horas

**A2.** Cuáles son las causas más comunes de retraso en el desembolso después de firma? (ej: empresa pagadora no ha autorizado, cuenta bancaria rechazada, etc.)
-

**A3.** Cuál es el tiempo MÁXIMO realista que puede tomar un desembolso desde la firma? (para que el bot no diga "mañana" cuando puede ser 2 semanas)
- Desde la firma debe tomar máximo 24 horas para hacer el desembolso, de ahí en adelante ya depende del banco

**A4.** Cuando un cliente llama porque no le ha llegado el desembolso, qué debería decir el bot? (el LLM estaba diciendo "lo revisan hoy y te confirmo" pero nadie confirmaba)
- Escalar

**A5.** Existe algún proceso interno de "marcar como prioritario" un desembolso? El LLM le dijo a clientes "quedó registrado como prioritario en el sistema" — esto existe o se lo inventó?
- No, esto no existe

---

## B. COMPRA DE CARTERA

**Contexto:** Varios clientes recibieron menos dinero del aprobado y el LLM explicó que fue "compra de cartera" (ProAlto pagó una deuda anterior). Pero un cliente respondió "yo no le debía nada a nadie" y el LLM no supo qué hacer. El bot necesita saber cuándo aplica y cuándo no.

**B1.** En qué casos específicos se hace compra de cartera? (ej: solo cuando el cliente tiene otro crédito activo con ProAlto, o también con otras entidades?)
- La compra de cartera es con otras entidades. 

**B2.** El cliente siempre sabe de antemano que se va a hacer compra de cartera, o puede ser sorpresa?
- El cliente debe saber de antemano

**B3.** Cómo se calcula exactamente cuánto se descuenta? (ej: saldo pendiente del crédito anterior + intereses?)
- Lo que se descuenta es el saldo del crédito anterior a la fecha del desembolso

**B4.** Qué debe hacer el bot si el cliente dice "yo no debía nada" pero el sistema muestra compra de cartera?
- Escalar

**B5.** El cliente puede obtener un recibo/soporte de la compra de cartera? Cómo?
- La entidad a la que se le compra cartera debe emitir un paz y salvo al cliente

---

## C. DESCUENTOS DE NÓMINA Y CUOTAS

**Contexto:** Un cliente preguntó "me descontaron casi 600,000 en una sola quincena, eso está bien?" y "a 6 cuotas no da ese descuento". El LLM no pudo validar si el monto era correcto porque no tiene la tabla de amortización ni las reglas de cálculo.

**C1.** El descuento se hace mensual, quincenal o catorcenal? Depende de la empresa o del cliente?
- Puede ser catorcenal, quincenal o mensual

**C2.** Existe alguna regla de porcentaje máximo de descuento sobre el salario? (ej: no puede superar el 50% del salario) Legalmente no puede superar el 50%. Por políticas internas de Proalto lo ideal es que no supere el 40%
-

**C3.** Si un cliente siente que le están descontando de más, qué debería decir el bot? A quién se escala?
- Escalar para revisióm

**C4.** Puede pasar que le hagan un descuento doble en un mes (ej: por retraso del mes anterior)? Cómo se explica? 
- No debería pasar. Si pasa hay que revisar puntualmente el caso

---

## D. RECHAZO DE SOLICITUDES

**Contexto:** Un cliente preguntó "por qué no me aprobaron?" y el LLM dio una respuesta genérica: "políticas internas de riesgo y capacidad de pago". El cliente insistió pidiendo la razón específica. Luego un asesor humano le dijo la verdad: "nos informaron que serías retirado de tu empresa".

**D1.** Qué puede decir el bot sobre los motivos de rechazo? Puede dar razones generales?
- En general dar razones generales. No cumple con los requisitos para aprobar en estos momentos, no tiene sufuciente capacidad de endeudamiento, etc

**D2.** Hay razones de rechazo que NUNCA se le deben comunicar al cliente por el bot? (ej: información confidencial de la empresa)
- Escalar

**D3.** Qué debe hacer el bot cuando el cliente insiste en saber el motivo exacto del rechazo?
- Escalar

**D4.** Un cliente rechazado puede volver a aplicar? En cuánto tiempo? Bajo qué condiciones?
- Si puede, puede ser que después de un tiempo cumpla las condiciones de aprobación

---

## E. RENOVACIÓN Y SEGUNDO CRÉDITO

**Contexto:** Clientes preguntaron "puedo hacer otro préstamo?" y "quiero renovar y ampliar el monto". El LLM dio respuestas vagas. La info actual dice "clientes con historial de pago" pero no especifica reglas.

**E1.** Qué porcentaje del crédito debe estar pagado para poder renovar? (la auditoría anterior mencionó 70% — confirmar)
- Esto depende. Unas empresas tienen políticas de no renovación, otras el 70%

**E2.** Puede un cliente tener 2 créditos activos simultáneamente?
- No, para eso se hace la renovación, se "paga" el crédito anterior y queda con uno solo

**E3.** En la renovación, el nuevo monto puede ser mayor al anterior? Hay límites?
- Puede ser mayor al anterior, se evalua como un crédito aparte

**E4.** El proceso de renovación es más rápido que uno nuevo? Cuánto tarda aproximadamente?
- Suele ser más rápido que uno nuevo, depende cuanto tiempo haya pasado entre uno y otro y qué tanto ha cambiado la información personal del cliejnte, si sigue en la misma empresa será mucho más rápido que si cambió de empresa. 

---

## F. DOCUMENTOS

**Contexto:** El LLM le dijo a clientes "recibí tu archivo, déjame revisarlo" cuando en realidad NO puede ver imágenes ni PDFs. También un cliente envió el mismo documento 3 veces y 3 días después le dijeron que todavía faltaba.

**F1.** Cuando el cliente envía documentos por WhatsApp, a dónde llegan exactamente? Quién los revisa?
- Lo revisa el equipo 

**F2.** Cuánto tiempo toma típicamente revisar y validar los documentos una vez enviados?
- Esto depende, no hay un tiempo específico

**F3.** Cómo se le notifica al cliente que sus documentos fueron recibidos y están siendo revisados?
- Se le puede confirmar que ya recibimos los docuentos, los revisamos y si hace falta algo más nos ponemos en contacto con el 

**F4.** Cuáles son las razones más comunes por las que se rechazan documentos? (ej: foto borrosa, documento vencido, falta firma)
- Documento vencido; foto ilegible. Esto puede variar

**F5.** Si un cliente dice "ya envié eso", hay alguna forma de verificar si efectivamente lo envió?
- No. Decir que vamos a revisar y si queda faltando algo nos contectamos con el

---

## G. PAZ Y SALVO

**Contexto:** Varios clientes pidieron paz y salvo. El LLM dijo "en 1 a 2 días hábiles lo tienes" — esto es correcto?

**G1.** Cuánto tarda realmente generar un paz y salvo?
- No hay tiempos. Escalar

**G2.** Lo genera alguien manualmente o es automático?
- Se genera manualmente. 

**G3.** Cómo se le entrega al cliente? (WhatsApp, email, ambos?)
- Depende, la mayaría de veces es por WhatsApp, pero puede ser por email también

---

## H. QUÉ PASA SI EL CLIENTE SALE DE LA EMPRESA

**Contexto:** Un cliente preguntó "qué pasa si salgo de la empresa antes de pagar?" y el LLM dio una respuesta vaga.

**H1.** Qué pasa legalmente si el cliente renuncia o es despedido antes de terminar de pagar?
- Normalmente se le descuenta el saldo de la liquidadción según lo permitido por la ley y por la empresa

**H2.** El descuento se transfiere a la nueva empresa? Cómo?
- Si la persona queda con saldo después de descontar de la liquidación se solicitará a la nueva empresa seguir con los descuentos

**H3.** Si queda sin empleo, cómo paga? Hay algún plan?
- Se debe llegar a un acuerdo de pago si sale de la empresa y queda con saldo después de la liquidación

---

## I. PREPAGO / ABONO EXTRAORDINARIO

**Contexto:** Clientes dijeron "quiero hacer un abono de $1,500,000" y "quiero saber cuánto debo para cancelar todo". El LLM dijo "es un proceso especial" pero no explicó nada concreto.

**I1.** Cómo funciona el prepago? El cliente puede hacerlo cuando quiera?
- Si puede hacerlo cuando quiera, toca "liquidar" el saldo el día que se va a pagar el abono para saber el valor exacto, ya que cambia cada día según los intereses. 

**I2.** Hay penalización por pago anticipado?
-No hay

**I3.** A dónde debe consignar? (cuenta de ProAlto? misma cuenta del descuento?)
- Cuetna de Proalto

**I4.** Después de un abono extraordinario, se reduce la cuota o el plazo?
- El cliente puede escoger si reduce la cuota o el plazo

**I5.** Para liquidación total (cancelar todo el saldo), cómo se genera el valor exacto a pagar?
- Se liquida al día que se vaya a pagar

---

## J. HORARIOS Y TIEMPOS DE RESPUESTA

**Contexto:** Hay una contradicción en los archivos actuales. empresa.md dice "7:30am a 5:30pm" pero faq.md dice "8:00am a 5:00pm" en una línea. El LLM reprodujo ambos horarios en distintas conversaciones.

**J1.** Cuál es el horario CORRECTO de atención de asesores?
- 8 a 5 está bien

**J2.** El bot dice "un asesor te contactará al siguiente día hábil" cuando escriben fuera de horario — esto se cumple?
- No hay un procedimiento claro con esto

**J3.** Cuál es el tiempo promedio REAL de respuesta de un asesor humano después de que el bot escala?
- Es 100% variable

---

## K. PLATAFORMA DE FIRMA

**Contexto:** estados_solicitud.md menciona tanto "PandaDoc" como "DocuSign". Esto confundió al LLM.

**K1.** Se usa PandaDoc, DocuSign, o ambos? En qué casos?
-Solo se una PandaDoc

**K2.** Si el cliente dice "no me llegó el correo para firmar", qué debe hacer el bot?
- Escribir que se va a revisar y escalar

---

## L. DATACRÉDITO Y CENTRALES DE RIESGO

**Contexto:** Clientes preguntaron "estoy reportado en DataCrédito, puedo aplicar?". El LLM respondió bien ("se evalúa caso a caso") pero no tiene más detalle.

**L1.** Hay algún nivel de reporte que sea descarte automático? (ej: mora mayor a X meses, tipo de reporte)
-Nosotros nos basamos es en el salario de la persona, no importa si está reportado en datacrédito o no. Lo importante es que tenga capacidad de pago. 

**L2.** El bot puede decir "estar reportado NO es descarte automático" o prefieres que simplemente escale a asesor?
-Los reportados en datacrédito pueden hacer la solicitud, se evalua como cualquier otro crédito

---

## M. SEGUIMIENTO DE SOLICITUDES REGISTRADAS

**Contexto:** El LLM registró 75 solicitudes (llm_requests) en 7 días. TODAS quedaron en estado PENDING. Muchas con datos basura como detalle ("Ok", "Si", "Gracias"). Nadie las resolvió.

**M1.** Quién se supone que revisa y resuelve las llm_requests? Hay un flujo definido?
- Política por definir

**M2.** Con qué frecuencia se revisan? (diario, cuando llegan, nunca?)
- Por definir

**M3.** Quieres que el bot deje de decir "quedó registrado y te confirmo" si en la práctica nadie confirma?
- 

**M4.** Cuál sería la frase más honesta que puede usar el bot cuando registra algo? (ej: "tomé nota, el equipo lo revisa en horario de oficina" vs "te confirmo en breve")
- Revisamos y cualquier cosa te cuento

---

## N. REGLAS GENERALES DEL BOT

**N1.** Si el bot no tiene la respuesta exacta, prefieres que: (a) diga "no tengo esa info, te paso con un asesor", (b) dé una respuesta general y registre el caso, o (c) solo registre y diga "te escribimos cuando tengamos respuesta"?
- Depende de cada caso, pero en general cuando no tenga la respuesta es mejor decir que se va a revisar y escalar. 


**N2.** Hay temas que el bot NUNCA debería tocar y siempre escalar a humano? (ej: reclamos formales, amenazas legales, situaciones de fraude)
- Si, temas muy complejos en generañ

**N3.** El bot puede mencionar montos específicos de crédito que aparecen en el sistema? (ej: "tu crédito aprobado es de $2,200,000") O solo el asesor debería dar esos números?
- El bot tiene acceso a esa información, la puede dar. 

---

*Fin del cuestionario. Responde con la mayor cantidad de detalle posible — cada respuesta se convierte en una regla o información que el Agente LLM va a usar para responder correctamente a los clientes.*

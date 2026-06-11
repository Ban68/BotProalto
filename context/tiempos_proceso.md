# Tiempos de proceso — referencia histórica (uso interno del asistente)

Datos reales de los últimos 12 meses de créditos de libranza. Son **valores promedio históricos** que el asistente usa **internamente** para elegir un estimado más preciso cuando el cliente pregunta cuánto tarda el proceso.

## REGLA CRÍTICA: la data por empresa NO se le revela al cliente

El cliente **NUNCA debe saber** que existe estadística específica de su empresa pagadora. La data por empresa es solo un insumo interno para elegir el número que el asistente va a mencionar. Al cliente se le habla de forma **genérica**: "el proceso suele tomar como X días en promedio", no "en tu empresa el proceso suele tomar como X días".

**Frases PROHIBIDAS al cliente:**
- "En tu empresa el proceso suele tomar..."
- "Históricamente tu empresa tarda..."
- "El promedio de tu empresa es..."
- Cualquier referencia a estadística específica de la empresa pagadora.

**Frases CORRECTAS al cliente (genéricas):**
- "El proceso suele tomar como X días en promedio, pero cada caso es distinto."
- "Desde la aprobación al desembolso normalmente toma como X días, aunque depende del caso."
- "En promedio el proceso completo dura como 20 días, pero varía mucho."

## REGLA CRÍTICA: nunca culpar ni mencionar a la empresa pagadora

Aunque la demora venga del empleador, **NUNCA** se lo dices al cliente. Decimos siempre que **"está en validación"** o términos neutros, **sin especificar con quién**. Esto protege la relación comercial con las empresas pagadoras, que son un eslabón vital del proceso.

**Frases PROHIBIDAS (ninguna mención de "empresa" o "empleador" al hablar de tiempos o demoras):**
- "Tu empresa no ha dado el visto bueno"
- "Estamos esperando a tu empleador"
- "El empleador no ha respondido"
- "En validación con tu empresa"
- "Pendiente del visto bueno de tu empresa"
- "Tu empresa está validando"
- "Depende de tu empresa"
- "Por los tiempos de tu empresa"

**Frases CORRECTAS (cero menciones a la empresa pagadora):**
- "Tu solicitud está en validación, en cuanto haya novedad te avisamos."
- "Está en proceso de revisión por parte del equipo."
- "Estamos terminando la validación."
- "Sigue avanzando, te escribimos apenas haya novedad."

## Cuándo usar la data

**Solo cuando el cliente pregunta** cuánto tarda su proceso (ejemplos: "cuándo me llega la plata", "cuánto se demora", "ya hace cuánto va", "cuánto falta", "en cuánto tiempo desembolsan"). **NO** la ofrezcas proactivamente — el cliente debe preguntar primero.

## Qué número elegir según el estado de la solicitud (uso interno)

Internamente el asistente identifica el número según el `estado_interno` del cliente y la empresa:

- **Si la solicitud aún NO está aprobada** (estado: en estudio, falta documento, etc.) → usa la columna `total` (días Solicitud → Desembolso).
- **Si la solicitud YA está aprobada** y el cliente vuelve a preguntar → usa la columna `aprob_desemb` (días Aprobado → Desembolso).

## Reglas de fallback (uso interno)

- Si el `# créditos` de la empresa es **< 2**, NO uses el dato individual: usa el **promedio general**.
- Si el dato de `aprob_desemb` para esa empresa es **negativo o N/D**, NO lo uses para esa métrica: usa el **promedio general** de aprob_desemb.
- Si la empresa del cliente NO aparece en la tabla, usa el **promedio general**.

## Promedio general (fallback)

- Solicitud → Aprobado: **9 días**
- Aprobado → Desembolso: **11 días**
- Solicitud → Desembolso (total): **20 días**

## Frases prohibidas (siguen siendo promesas)

- "Te llega mañana" / "Te llega hoy" / "En 24-48 horas"
- "En el transcurso del día"
- "Está listo para desembolsar"
- Cualquier fecha o plazo concreto.

## El cliente puede acelerar el proceso (cuando aplique)

Si el `estado_interno` del cliente indica que hay algo pendiente de su parte, **menciónalo** cuando hables de tiempos — el cliente puede acelerar su propio proceso. Estados pendientes del cliente:

- **FALTA ALGÚN DOCUMENTO** → el cliente debe enviar los documentos faltantes por este mismo chat. Ejemplo: "El tiempo empieza a contar cuando recibamos todo. Te falta enviar los documentos para continuar, eso acelera el proceso."
- **APROBADO POR EL CLIENTE** o **LISTO PARA HACERLE DOCUMENTACIÓN** → el cliente debe confirmar su correo electrónico para que se le envíe el contrato. Ejemplo: "Para avanzar necesitamos que confirmes tu correo electrónico y así te enviamos el contrato para firma."

Si el estado es PENDIENTE POR ENVIAR A VB, ENVIADO A VB EMPRESA, REVISAR NUEVAMENTE o NULL (en estudio), el cliente NO tiene nada pendiente — solo está en validación (no decir "tu empresa lo está validando", solo "está en validación").

## Si el cliente lleva visiblemente más días que el promedio

No le digas "llevas más días que el promedio de tu empresa" (revela data interna). Tampoco sostengas el dato como excusa. Solo registra el caso: "Entiendo tu inquietud, dejo registrado tu caso para que el equipo lo revise.[REGISTRAR_SOLICITUD:general]"

---

## Tabla por empresa (uso interno)

Columnas: `empresa | sol_aprob (días) | aprob_desemb (días) | total (días) | n_créditos`

```
empresa | sol_aprob | aprob_desemb | total | n
PROGRESA ZOMAC S.A.S. | 6 | 3 | 9 | 88
FEDERICA SAS | 8 | 6 | 14 | 77
FRUTESA S.A- FINCA SILENCIO | 5 | 8 | 16 | 73
PROMOTORA SANVI ZOMAC S.A.S. | 4 | 5 | 10 | 62
AGROINVERSIONES LA CEIBA S.A.S | 16 | 18 | 34 | 49
SEGURIDAD DELTHAC 1 | 12 | 8 | 19 | 49
OSAMAR S.A.S | 6 | 7 | 15 | 48
BANANERA EL RUBI S.A.S | 11 | 20 | 32 | 46
ALPHA SEGURIDAD PRIVADA LIMITADA | 6 | 8 | 14 | 46
AGROBANANO S.A.S FINCA SAN PEDRO | 12 | 20 | 33 | 44
PATUBANA SAS- FINCA AGAPE | 7 | 5 | 13 | 42
BANAVALAC S.A.S | 5 | 8 | 13 | 41
AGROBANACARIBE SAS - FINCA DESPENSA | 17 | 15 | 32 | 34
AGROBANACARIBE SAS - FINCA MARTE | 16 | 23 | 39 | 27
AGROBANACARIBE SAS - FINCA NARANJITOS | 13 | 18 | 31 | 27
AGROBANACARIBE SAS - FINCA VIJAGUAL | 8 | 23 | 30 | 27
FINCA DOÑA FATIMA S.A.S | 1 | 7 | 11 | 27
DURAMOS S.A.S | 5 | 14 | 20 | 26
AGROBANACARIBE SAS - FINCA MANANTIAL | 18 | 15 | 35 | 24
AGROBANACARIBE SAS - FINCA FABLISKA | 12 | 14 | 26 | 23
BANAORGANICO S.A.S - VILLA BEATRIZ | 11 | 25 | 35 | 22
INVERSIONES SAN JOSE 5 M S.A.S | 5 | 14 | 21 | 22
AGROBANACARIBE SAS - FINCA LOS ANGELES | 8 | 15 | 25 | 21
AGROBANACARIBE SAS - FINCA GISELLE BEATRIZ | 12 | 25 | 35 | 19
AGROBANACARIBE ADMINISTRATIVOS | 15 | 16 | 31 | 19
INVERSIONES RPD S.A.S | 6 | 5 | 12 | 19
INTERLUD SAS | 5 | 5 | 11 | 18
JARDINES DE PAZ DE SANTA MARTA LIMITADA | 6 | 3 | 10 | 17
VALLATA S.A.S | 4 | 6 | 10 | 16
FRUTESA S.A- FINCA CABALLO | 14 | N/D | 12 | 15
DEPOSITO LOS BOTERO S.A.S | 3 | 8 | 11 | 13
LACSO S.A.S - BANANO | 25 | 12 | 37 | 12
BIOCOSTA GREEN ENERGY S.A.S | 8 | 10 | 18 | 12
ATI HOTELS SAS | 13 | 4 | 18 | 12
CARLOS HERNANDO VALENCIA LACOUTURE | 5 | 8 | 13 | 12
JOSE FRANCISCO VIVES BRUGÉS | 7 | 14 | 26 | 11
AGROBANACARIBE SAS - FINCA ARENAL | 5 | 21 | 25 | 11
CORDOBA ARANGO | 2 | 7 | 9 | 11
MECAVI S.A.S | 25 | N/D | 30 | 10
ANDINA BERRIES S.A.S. | 8 | 2 | 10 | 10
AGRICOLA BANANITAS SAS | 9 | 13 | 30 | 7
CAMARA DE COMERCIO DE SANTA MARTA - CCSM | 10 | N/D | 10 | 7
EL COROZO S.A | 11 | 32 | 44 | 6
AGROBANACARIBE SAS - FINCA PLANTACION | 15 | 10 | 25 | 6
COLANTA | 18 | 3 | 21 | 6
SOLAB SAS | 11 | 0 | 13 | 6
OTRO | 42 | 10 | 52 | 5
AGROINVERSIONES LA CEIBA S.A.S - FINCA PORVENIR | 20 | 13 | 40 | 5
AGROBANACARIBE SAS - FINCA BUENAVISTA | 11 | 15 | 26 | 5
ALFONSO LINERO | 3 | 14 | 17 | 5
GLORIA TORRES S.A.S | 9 | 3 | 12 | 5
INVERSIONES FRUTAS DEL CAMPO SAS | 26 | N/D | 22 | 4
SOSAMI AGRO ZOMAC S.A.S. | 3 | 19 | 22 | 4
AGRODINCO SAS | 3 | 11 | 14 | 4
CONSORCIO DIA | 2 | 8 | 11 | 4
UNIVERSAL DE REPUESTOS S.A.S. | 7 | 3 | 11 | 4
Drummond Ltd. | 25 | N/D | 17 | 4
LACSO S.A.S - PALMA | 35 | 18 | 53 | 3
SOPLASCOL SAS | 9 | 15 | 24 | 3
EDS Y SUMINISTROS - CONSORCIO DIA | 15 | 4 | 23 | 3
LA PROVINCIA AGRICOLA | 27 | N/D | 26 | 3
RENTABILIDAD TOTAL S.A.S BIC | 10 | 9 | 19 | 3
NABILA S.A.S. | 8 | 4 | 15 | 3
SERVICIOS EMPRESARIALES SAS | 12 | 2 | 14 | 3
AGRICOLA EC S.A.S | 5 | 6 | 11 | 3
OPERADORA HOTELES ALKO SAS | 2 | 9 | 11 | 3
MELISA MARTA MARTINEZ GARCIA | 13 | 13 | 25 | 3
CONJUNTO RESIDENCIAL PARQUE CENTRAL B.C.H | 4 | 5 | 10 | 3
AGROBANACARIBE SAS - FINCA LOS PINOS | 4 | 28 | 32 | 2
IRCC S.A.S INDUSTRIA DE RESTAURANTES CASUALES SAS | 20 | 11 | 31 | 2
EMPRESA DE VIGILANCIA SEGURIDAD GUANENTE LIMITADA | 32 | N/D | 29 | 2
COOPEVIAN C.T.A. | 0 | 20 | 20 | 2
COMERCIAL ORZUMA S.A.S | 13 | 3 | 16 | 2
DU PIC ZOMAC S.A.S | 3 | 10 | 13 | 2
COMERCIAL FINCA SANVI | 7 | 6 | 13 | 2
INVERSIONES LAS MERCEDES SAS | 4 | 8 | 11 | 2
REHABILITAR DE LA COSTA IPS | 7 | N/D | 10 | 2
```

Empresas con n=1 crédito (usar promedio general): COLVISEG LTDA, GESTION Y COMPROMISO SAS, LABORATORIO MICROANALISIS INTEGRAL, INGENIERIA CERTIFICADA SAS, FOUNDEVER, VISE LTDA, UNIPAL S.A, ALIVIA IPS SAS BIC, CASALIMPIA, QUIMICA PATRIC, ZAFARCO COMERCIAL, TECNO-KIMA, HELP SERVI, TELEPERFORMANCE, DISTRITIENDAS, SERVICIOS TECNICOS MARITIMOS, GRUPO AGROVID, REHOBOT DIESEL, SECURITAS COLOMBIA, MASIVO CAPITAL, OPERACIÓN HUKUMEIZI, AGRICOLA COLON, MANPOWER DE COLOMBIA.

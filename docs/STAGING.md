# Entorno de Staging — ProAlto WhatsApp Bot

Este documento describe el **entorno de pruebas (staging)** del bot y el **flujo oficial**
para probar cualquier desarrollo ANTES de pasarlo a producción.

> **Regla de oro:** Producción no se toca hasta que el cambio se probó y aprobó en staging.
> El servicio de producción en Render se creó manualmente y **no se modifica** como parte
> de este flujo.

---

## 1. Qué es staging

Una **segunda instancia del bot** corriendo en Render, con su propia URL, que sigue
**siempre** la rama `staging` de este repositorio. Sirve para que el equipo pruebe cambios
en un entorno idéntico a producción pero **sin riesgo de enviar mensajes a clientes reales**.

Tres capas de seguridad garantizan que staging nunca escriba a un teléfono real:

1. **`ENVIRONMENT=staging` + guard global** (`src/services.py`): cuando la variable de
   entorno `ENVIRONMENT` vale `staging`, **todo** envío saliente a WhatsApp/Meta y **toda**
   notificación a admins queda **bloqueado y registrado en log** en lugar de enviarse. Cubre
   `send_message`, `send_image`, `send_document`, `send_interactive_button`,
   `send_interactive_list`, `send_template` y `revoke_message`.
2. **Scheduler desactivado en staging** (`app.py`): las tareas programadas
   (campañas, recordatorios) mutan estado en Supabase y dispararían mensajes. En staging
   **no se arranca el scheduler**, para no tocar datos compartidos con producción.
3. **`test_mode` en memoria** (panel `/admin/test`): el simulador del panel usa teléfonos
   de prueba (prefijo `__test_`) que **nunca** tocan Supabase ni Meta — todo ocurre en
   memoria. Esta es la vía recomendada para probar (ver §5).

> Cinturón y tirantes: el guard de `ENVIRONMENT` es **adicional e independiente** del
> `test_mode`. Aunque un teléfono real (no de prueba) se cuele en staging, el guard lo
> bloquea igual.

---

## 2. Flujo de trabajo reutilizable (para TODO desarrollo futuro)

```
feature/<lo-que-sea>        rama de trabajo (1 por desarrollo)
        │  merge
        ▼
     staging  ───────────►  auto-deploy a la URL de staging en Render
        │                   (probar aquí vía /admin/test)
        │  (solo si se aprobó la prueba)
        ▼
   main (producción)  ────►  auto-deploy a producción
```

Pasos:

1. Crear la rama de trabajo desde producción: `git checkout main && git pull && git checkout -b feature/mi-cambio`.
2. Hacer los cambios y commitear en esa rama.
3. **Fusionar a `staging`:** `git checkout staging && git merge feature/mi-cambio && git push origin staging`.
   Render redepliega `proalto-bot-staging` automáticamente.
4. **Probar en staging** vía el panel `/admin/test` de la URL de staging (ver §5).
5. Si todo está bien y se aprueba, fusionar a producción:
   `git checkout main && git merge feature/mi-cambio && git push origin main`.
6. Si algo falla, corregir en la rama de trabajo y repetir desde el paso 3. **No** se fusiona
   a `main` hasta que la prueba en staging pase.

> `staging` es una rama **permanente**. Nunca se borra. Acumula lo que se va probando; se
> mantiene al día con producción haciendo `git merge main` dentro de `staging` cuando haga falta.

---

## 3. Montaje único en Render (hacerlo UNA sola vez)

> Hazlo tú (Carlos) en el dashboard. **No** se automatiza para no arriesgar el servicio de
> producción.

1. En el dashboard de Render: **New + → Web Service**.
2. **Connect repository:** el mismo repo de GitHub del bot.
3. Configuración del servicio:
   - **Name:** `proalto-bot-staging`
   - **Branch:** `staging`  ← clave: staging sigue SIEMPRE esta rama
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`  *(igual que producción)*
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT`  *(igual que producción; ya está en el `Procfile`)*
   - **Instance Type:** el más pequeño está bien para pruebas.
4. **Environment Variables:** agrégalas según la tabla de §4. **Lo crítico:**
   `ENVIRONMENT=staging` y un `ADMIN_USER`/`ADMIN_PASS` propios de staging.
5. **Create Web Service.** Render hará el primer deploy desde la rama `staging`.
6. Anota la URL que te asigna Render (algo como `https://proalto-bot-staging.onrender.com`).
   El panel de pruebas queda en `…/admin` → `/admin/test`.

### Webhook de Meta — NO repuntar

**No** apuntes el webhook de Meta hacia staging. Staging se prueba por el panel
`/admin/test`, que no necesita WhatsApp real ni plantillas de Meta. Si en el futuro quieres
una prueba con WhatsApp real, usa un **número de prueba aparte** (nunca el de producción) y
un `BUSINESS_PHONE` distinto.

---

## 4. Variables de entorno del servicio de staging

Lista **completa** que necesita el bot en runtime (sacada de `config.py`, `src/database.py`,
`src/llm.py`). Marca los **secretos** como *“a llenar manualmente”* (en un Blueprint
`render.yaml` sería `sync: false`). **Nunca** se hardcodean secretos en el repo.

| Variable | Valor en staging | ¿Distinto a prod? | Secreto |
|---|---|---|---|
| `ENVIRONMENT` | `staging` | **SÍ** (en prod es `production` o no existe) | No |
| `ADMIN_USER` | usuario propio de staging | **SÍ** | No |
| `ADMIN_PASS` | clave propia de staging | **SÍ** | **Sí** |
| `API_TOKEN` | igual a prod (token de Meta) | No | **Sí** |
| `BUSINESS_PHONE` | igual a prod | No | No |
| `WEBHOOK_VERIFY_TOKEN` | igual a prod | No | **Sí** |
| `APP_SECRET` | igual a prod | No | **Sí** |
| `ANTHROPIC_API_KEY` | igual a prod | No | **Sí** |
| `SUPABASE_URL` | igual a prod (ver nota) | No* | No |
| `SUPABASE_KEY` | igual a prod (ver nota) | No* | **Sí** |
| `CLOUD_RUN_URL` | igual a prod | No | No |
| `API_TOKEN_SECRET` | igual a prod | No | **Sí** |
| `ADMIN_NOTIFY_NUMBERS` | igual a prod (las notif. se bloquean igual) | No | No |
| `ADMIN_TIMEZONE` | `America/Bogota` | No | No |
| `MAINTENANCE_MODE` | `False` | No | No |
| `GOOGLE_APPS_SCRIPT_URL` | igual a prod (tiene default) | No | No |
| `GOOGLE_APPS_SCRIPT_ANTICIPO_URL` | igual a prod | No | No |
| `DEBUG` | `False` | No | No |
| `PORT` | **no la pongas** — Render la inyecta sola | — | — |

`API_VERSION` está hardcodeada en `config.py` (`v21.0`); no es variable de entorno del bot.

> **\* Nota sobre Supabase (recomendado):** lo más seguro es crear un **proyecto Supabase
> aparte** para staging y usar su `SUPABASE_URL`/`SUPABASE_KEY`, para que las pruebas no
> compartan datos con producción. Si por simplicidad se reutiliza el de producción, el riesgo
> está acotado porque: (a) el scheduler está apagado en staging, (b) los envíos bloqueados
> por el guard retornan **antes** de escribir el log en Supabase, y (c) la vía de prueba
> recomendada (`/admin/test`) es 100% en memoria y no toca Supabase. Aun así, preferir un
> proyecto separado.

---

## 5. Cómo probar (vía panel `/admin/test`)

1. Entra a `https://<tu-url-de-staging>/admin` con el `ADMIN_USER`/`ADMIN_PASS` de staging.
2. Abre la sección **Test** (`/admin/test`). Crea una sesión de prueba (genera un teléfono
   `__test_…` en memoria).
3. Simula mensajes del cliente y botones. Los mensajes salientes del bot se muestran en el
   panel; **nada** sale a WhatsApp.

### Verificar el nuevo menú interactivo

Escribe `Hola` (o cualquier saludo) para disparar el menú principal y recorre el árbol:

- **Nivel 1 — menú principal** (3 botones): `Información General` · `Solicitar Crédito` · `Mi Crédito ProAlto`.
- **Información General** → mensaje de presentación + lista *“Ver opciones”* con:
  `Requisitos` · `Tasas` · `Montos y plazos` · `Hablar con un asesor`.
- **Solicitar Crédito** → mensaje directo con el link del formulario y las 3 claves.
- **Mi Crédito ProAlto** → mensaje + lista *“Gestionar”* con:
  `Estado de mi solicitud` · `Consulta de saldo` · `Paz y Salvo` · `Hablar con un asesor`.

Comprobar que cada opción responde:
- `Estado de mi solicitud` y `Consulta de saldo` piden la cédula (reutilizan los flujos
  existentes de Estado y Saldo).
- `Hablar con un asesor` (en ambos submenús) activa el modo asesor.
- `Paz y Salvo` responde con el mensaje provisional (*“Estamos generando tu paz y salvo…”*).

En el log del servicio de staging debería verse `[BOOT] … ENVIRONMENT=staging`,
`[STAGING] Scheduler … DESACTIVADO` y, si algún envío real se intentara, líneas
`[STAGING] Envío real bloqueado → …`.

---

## 6. Cómo revertir

- **Deshacer un cambio en staging:** `git checkout staging`, revierte el commit
  (`git revert <sha>`) o resetea a un punto bueno y `git push origin staging`. Render
  redepliega solo.
- **Producción nunca recibió el cambio** mientras no se fusionó a `main`, así que revertir
  staging no afecta a clientes.
- **Apagar staging temporalmente:** en Render, *Suspend* el servicio `proalto-bot-staging`.
  No afecta a producción.

---

## 7. Resumen de archivos que implementan staging

- `config.py` → `ENVIRONMENT` / `IS_STAGING`.
- `src/services.py` → `_staging_blocks_send()` y su llamada en cada método de envío.
- `app.py` → no arranca el scheduler cuando `IS_STAGING`.
- Auth del panel (`src/auth.py`) ya lee `ADMIN_USER`/`ADMIN_PASS` de entorno, así que las
  credenciales de staging se configuran solo con variables de entorno (sin cambios de código).

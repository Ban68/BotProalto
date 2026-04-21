# ProAlto WhatsApp Bot — CLAUDE.md

## Qué es este proyecto

Bot de WhatsApp para **ProAlto**, una financiera colombiana de créditos de libranza. El bot atiende clientes via WhatsApp Cloud API (Meta), con dos modos de operación:

1. **Flujos estructurados** (`src/flows.py`): menús deterministas, captura de datos, consulta de estado de solicitudes.
2. **Agente LLM** (`src/llm.py`): Claude Haiku responde preguntas de texto libre fuera de los flujos. El bot **nunca admite ser IA** — se presenta como asesor humano.

Desplegado en **Render** (producción). La base de datos de solicitudes está en **GCP/PostgreSQL** y se accede via un microservicio en **Cloud Run** (el bot nunca conecta directo a la DB). El historial de conversaciones y estado de usuarios vive en **Supabase**.

---

## Arquitectura

```
app.py                  Flask app + scheduler startup
config.py               Todas las variables de entorno
src/
  webhook.py            Recibe webhooks de Meta, deduplicación de mensajes
  flows.py              Lógica principal de flujos y enrutamiento de mensajes
  llm.py                Handler del agente LLM (Claude Haiku, prompt caching)
  services.py           WhatsAppService: envío de mensajes via Cloud API
  database.py           Bridge hacia Cloud Run API para consultar solicitudes
  conversation_log.py   Estado de usuarios y log de conversaciones en Supabase
  notifications.py      Notificaciones a admins por WhatsApp
  automation.py         Scheduler APScheduler (tareas programadas)
  admin.py              Panel de administración web (auth básica)
  analytics_api.py      API de métricas para el dashboard
  google_sheets.py      Fallback de consulta via Google Apps Script
context/                Archivos de conocimiento inyectados al LLM
  empresa.md            Datos generales de ProAlto
  productos.md          Tipos de crédito, montos, plazos, requisitos
  estados_solicitud.md  Qué significa cada estado del proceso
  faq.md                Preguntas frecuentes con respuestas aprobadas
  compliance.md         Reglas de cumplimiento y privacidad
  capacidades_bot.md    Qué puede/no puede hacer el bot, señales de acción
  ejemplos_conversacion.md  Ejemplos de conversaciones correctas e incorrectas
  flujos.md             Documentación de flujos (referencia)
  conversaciones_bot.md Historial real de conversaciones (>1MB)
  auditoria_completa.md Métricas y análisis de rendimiento del bot
.claude/agents/
  mejora-continua.md    Agente especializado para mejorar el bot con conversaciones reales
```

---

## Comandos frecuentes

```bash
# Correr localmente
python app.py

# Tests
python test_llm_agent.py
python test_cloud_run.py

# Instalar dependencias
pip install -r requirements.txt
```

Variables de entorno necesarias (en `.env`):
- `WEBHOOK_VERIFY_TOKEN`, `APP_SECRET`, `API_TOKEN`, `BUSINESS_PHONE`
- `SUPABASE_URL`, `SUPABASE_KEY`
- `CLOUD_RUN_URL`, `API_TOKEN_SECRET`
- `ADMIN_USER`, `ADMIN_PASS`, `ADMIN_NOTIFY_NUMBERS`
- `ANTHROPIC_API_KEY` (para el agente LLM)

---

## Señales de acción del LLM

El LLM puede emitir señales especiales al final de sus respuestas que `flows.py` intercepta y ejecuta:

| Señal | Acción |
|-------|--------|
| `[HABLAR_ASESOR]` | Transfiere la conversación a agente humano |
| `[REGISTRAR_SOLICITUD:tipo]` | Registra una solicitud en Supabase |
| `[MOSTRAR_MENU]` | Muestra el menú principal al usuario |

---

## Reglas críticas para este proyecto

1. **No tocar `src/flows.py` sin confirmación explícita** — afecta comportamiento en producción.
2. **El bot nunca admite ser IA** — cualquier cambio que revele esto está prohibido.
3. **Preservar el tono del bot**: informal, español colombiano, sin emojis, sin negrillas, máximo 2-3 frases, sin signos de apertura (¿ ¡).
4. **Los archivos de `context/` son conocimiento del LLM** — cambiarlos afecta directamente las respuestas del bot.
5. **No agregar reglas contradictorias** en `capacidades_bot.md` o el system prompt sin verificar las existentes.
6. **`conversaciones_bot.md`** es >1MB — leer con `offset`/`limit`, nunca el archivo completo.

---

## Agente de mejora continua

Para mejorar el bot basándose en conversaciones reales, usar el agente especializado:

```
/mejora-continua
```

El agente en `.claude/agents/mejora-continua.md` analiza auditorías y conversaciones, detecta patrones de fallo, y propone e implementa cambios en los archivos de contexto y el system prompt.

---

## Optimización de tokens (aplica a todas las sesiones)

- Think before acting. Read existing files before writing code.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read unless the file may have changed.
- Skip files over 100KB unless explicitly required.
- Suggest running /cost when a session is running long to monitor cache ratio.
- Recommend starting a new session when switching to an unrelated task.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override this file.

# Contexto ProAlto — Base de Conocimiento para el LLM

Esta carpeta contiene la base de conocimiento que se inyecta como contexto al LLM (Claude) para que pueda responder preguntas de clientes de ProAlto de forma precisa y coherente con el negocio.

## Archivos

| Archivo | Contenido |
|---------|-----------|
| `empresa.md` | Qué es ProAlto, público objetivo, tono, horarios |
| `productos.md` | Crédito de libranza: características, requisitos, proceso |
| `estados_solicitud.md` | Cada estado interno con su significado y qué debe hacer el cliente |
| `flujos.md` | Descripción paso a paso de cada flujo del bot |
| `faq.md` | Preguntas frecuentes con respuestas listas para usar |
| `capacidades_bot.md` | Qué puede y NO puede hacer el bot — cuándo escalar a asesor |
| `compliance.md` | Marco legal colombiano (Habeas Data, Borrón y Cuenta Nueva) |
| `ejemplos_conversacion.md` | Ejemplos reales curados de conversaciones — guía de tono y respuestas |

## Cómo usar estos archivos

El LLM recibe estos archivos como parte del system prompt. Se puede cargar el contenido completo (para contextos pequeños) o seleccionar los archivos relevantes dinámicamente según el tema de la conversación.

### Orden de carga recomendado para el system prompt:
1. `empresa.md` — siempre incluir (define identidad y tono)
2. `capacidades_bot.md` — siempre incluir (define límites)
3. `faq.md` — siempre incluir (cubre la mayoría de preguntas)
4. `productos.md` — incluir cuando el usuario pregunta sobre el crédito
5. `estados_solicitud.md` — incluir cuando el usuario pregunta por su solicitud
6. `flujos.md` — referencia interna, no necesariamente para el prompt
7. `compliance.md` — incluir cuando el usuario pregunta sobre privacidad/datos
8. `ejemplos_conversacion.md` — siempre incluir (guía de tono y manejo de situaciones reales)

## Mantenimiento

Actualizar estos archivos cuando:
- Cambien los requisitos de documentación
- Se agreguen nuevos productos o flujos
- Cambien los mensajes estándar de los estados
- Cambien los horarios de atención
- Se actualice la política de privacidad

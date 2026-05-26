-- Migration: módulo de pruebas del Agente LLM (panel /admin/test v2)
-- Apply this in Supabase before deploying the new feature.
--
-- Crea las 3 tablas para persistir sesiones de prueba (manuales y automáticas
-- LLM-vs-LLM), sus mensajes turno a turno, y anotaciones del equipo.
-- Todas las tablas son INDEPENDIENTES de bot_conversations / bot_messages
-- para que las pruebas NO contaminen los datos reales del bot.

-- 1. Sesiones de prueba (una fila por conversación de test)
CREATE TABLE IF NOT EXISTS test_sessions (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    test_phone          text NOT NULL,
        -- el __test_XXX correspondiente en memoria (test_mode)
    mode                text NOT NULL,
        -- 'manual' | 'auto'
    persona_slug        text,
        -- solo en modo auto: slug de la persona del cliente-LLM
    objetivo            text,
        -- solo en modo auto: objetivo libre escrito por el operador
    categoria_cedula    text,
        -- aprobados | falta_documento | listo_en_docusign | denegado | activos | NULL
    cedula_used         text,
        -- cédula real inyectada al cliente-LLM si aplicó
    client_name         text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    ended_at            timestamptz,
    num_turns           int NOT NULL DEFAULT 0,
    signals_emitted     jsonb NOT NULL DEFAULT '[]'::jsonb,
        -- array de strings: 'MOSTRAR_MENU', 'HABLAR_ASESOR', 'REGISTRAR_SOLICITUD:tipo'
    tag                 text,
        -- 'ok' | 'fail' | 'review' | NULL
    notes               text,
        -- nota libre a nivel sesión (resumen del operador)
    started_by          text
        -- usuario admin (basic auth) que inició la sesión
);

CREATE INDEX IF NOT EXISTS test_sessions_created_at_idx
    ON test_sessions (created_at DESC);

CREATE INDEX IF NOT EXISTS test_sessions_mode_tag_idx
    ON test_sessions (mode, tag);

CREATE INDEX IF NOT EXISTS test_sessions_persona_idx
    ON test_sessions (persona_slug);


-- 2. Mensajes turno a turno dentro de una sesión
CREATE TABLE IF NOT EXISTS test_messages (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          uuid NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    direction           text NOT NULL,
        -- 'inbound' (del "cliente") | 'outbound' (del bot)
    role                text NOT NULL,
        -- 'user'        → humano en modo manual
        -- 'client_llm'  → Claude jugando rol de cliente en modo auto
        -- 'assistant'   → respuesta del bot (texto del LLM o del flujo)
        -- 'notice'      → notificación a admin suprimida o evento interno
    text                text,
    msg_type            text NOT NULL DEFAULT 'text',
        -- 'text' | 'button' | 'image' | 'document' | 'list' | 'template' |
        -- 'admin_notification_suppressed' | 'llm_request_recorded'
    signals             jsonb,
        -- señales del LLM en este turno (mismo formato que en sessions)
    latency_ms          int,
        -- solo en outbound: latencia del LLM/flujo en este turno
    seq                 int NOT NULL,
        -- orden estricto dentro de la sesión (1, 2, 3...)
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS test_messages_session_seq_idx
    ON test_messages (session_id, seq);


-- 3. Anotaciones del equipo (a nivel mensaje o a nivel sesión)
CREATE TABLE IF NOT EXISTS test_annotations (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          uuid NOT NULL REFERENCES test_sessions(id) ON DELETE CASCADE,
    message_id          uuid REFERENCES test_messages(id) ON DELETE CASCADE,
        -- NULL si la nota es a nivel sesión
    author              text,
        -- usuario admin que escribió la nota
    note                text NOT NULL,
    severity            text NOT NULL DEFAULT 'info',
        -- 'info' | 'warn' | 'error'
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS test_annotations_session_idx
    ON test_annotations (session_id);

CREATE INDEX IF NOT EXISTS test_annotations_message_idx
    ON test_annotations (message_id);

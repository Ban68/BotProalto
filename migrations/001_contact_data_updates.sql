-- Migration: yearly contact-data update flow
-- Apply this in Supabase before deploying the new feature.

-- 1. New column on bot_conversations to track when the client last updated
--    their contact info successfully (used to exclude them from the campaign
--    for the next 12 months).
ALTER TABLE bot_conversations
    ADD COLUMN IF NOT EXISTS ultima_actualizacion_datos timestamptz;

-- 2. New table that stores each attempt at the contact-data update flow.
CREATE TABLE IF NOT EXISTS contact_data_updates (
    id                  bigserial PRIMARY KEY,
    phone               text NOT NULL,
    cedula              text,
    telefono_principal  text,
    telefono_alterno    text,
    direccion           text,
    email               text,
    ref_nombre          text,
    ref_telefono        text,
    ref_parentesco      text,
    status              text NOT NULL DEFAULT 'in_progress',
        -- 'in_progress' | 'confirmed' | 'abandoned' | 'cedula_mismatch'
    processed           boolean NOT NULL DEFAULT false,
        -- flips to true once an admin syncs the data to the core
    trigger_source      text NOT NULL DEFAULT 'campaign_annual',
        -- 'campaign_annual' | 'manual_menu'
    started_at          timestamptz NOT NULL DEFAULT now(),
    confirmed_at        timestamptz,
    processed_at        timestamptz,
    admin_processor     text
);

CREATE INDEX IF NOT EXISTS contact_data_updates_phone_idx
    ON contact_data_updates (phone);

CREATE INDEX IF NOT EXISTS contact_data_updates_status_idx
    ON contact_data_updates (status);

CREATE INDEX IF NOT EXISTS contact_data_updates_processed_idx
    ON contact_data_updates (processed, status);

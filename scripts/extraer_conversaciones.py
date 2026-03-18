"""
Script de extracción de conversaciones del bot desde Supabase.
Genera un archivo Markdown con todas las conversaciones agrupadas por cliente.

Uso:
    python scripts/extraer_conversaciones.py

Salida:
    context/conversaciones_bot.md
"""
import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OUTPUT_FILE  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context", "conversaciones_bot.md")

def main():
    print("Conectando a Supabase...")
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. Get all conversations metadata (phone, client name, status)
    print("Obteniendo lista de conversaciones...")
    convs_res = client.table("bot_conversations") \
        .select("phone, client_name, status") \
        .order("updated_at", desc=False) \
        .execute()

    convs = {c["phone"]: c for c in convs_res.data}
    phones = list(convs.keys())
    print(f"  -> {len(phones)} conversaciones encontradas.")

    # 2. Get all messages in bulk
    print("Descargando mensajes...")
    all_messages = []
    batch_size = 200
    offset = 0

    while True:
        res = client.table("bot_messages") \
            .select("phone, direction, text, msg_type, created_at") \
            .neq("msg_type", "deleted") \
            .order("created_at") \
            .range(offset, offset + batch_size - 1) \
            .execute()
        batch = res.data
        if not batch:
            break
        all_messages.extend(batch)
        offset += batch_size
        print(f"  -> {len(all_messages)} mensajes descargados...")
        if len(batch) < batch_size:
            break

    print(f"Total mensajes: {len(all_messages)}")

    # 3. Group messages by phone
    from collections import defaultdict
    by_phone = defaultdict(list)
    for m in all_messages:
        by_phone[m["phone"]].append(m)

    # 4. Write output
    print(f"Generando {OUTPUT_FILE}...")
    lines = []
    lines.append("# Conversaciones Reales del Bot ProAlto\n")
    lines.append("> Archivo generado automáticamente desde Supabase. Usar para mejorar el FAQ y el contexto del Agente LLM.\n")
    lines.append(f"> Total conversaciones: {len(phones)} | Total mensajes: {len(all_messages)}\n\n")
    lines.append("---\n")

    skipped = 0
    for phone in phones:
        messages = by_phone.get(phone, [])
        # Skip trivial conversations (less than 3 messages)
        if len(messages) < 3:
            skipped += 1
            continue

        conv_meta = convs.get(phone, {})
        client_name = conv_meta.get("client_name") or "Cliente"
        status = conv_meta.get("status", "")

        lines.append(f"\n## {client_name} | {phone}\n")
        lines.append(f"**Estado final:** {status} | **Mensajes:** {len(messages)}\n\n")

        for m in messages:
            direction = m.get("direction", "")
            text = m.get("text", "") or ""
            msg_type = m.get("msg_type", "text")
            ts = m.get("created_at", "")[:16].replace("T", " ")  # Format: YYYY-MM-DD HH:MM

            # Skip media placeholders and template logs
            if msg_type in ("image", "document"):
                text = f"[{msg_type.upper()} enviado]"
            elif text.startswith("[Template:"):
                text = text  # Keep template name, useful context

            # Skip empty messages
            if not text.strip():
                continue

            # Truncate very long messages
            if len(text) > 500:
                text = text[:500] + "..."

            prefix = "**Cliente:**" if direction == "inbound" else "**Bot/Asesor:**"
            lines.append(f"- `{ts}` {prefix} {text}\n")

        lines.append("\n---\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"\nListo. Archivo guardado en: {OUTPUT_FILE}")
    print(f"Conversaciones incluidas: {len(phones) - skipped}")
    print(f"Conversaciones omitidas (menos de 3 mensajes): {skipped}")


if __name__ == "__main__":
    main()

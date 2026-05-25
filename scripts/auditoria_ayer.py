"""
Script de auditoría de conversaciones de ayer (2026-04-28).
Extrae conversaciones específicas de esa fecha y genera informe.
"""
import os
import sys
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def main():
    print("=== AUDITORÍA CONVERSACIONES 28 DE ABRIL 2026 ===\n")

    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Fetch messages from 2026-04-28
    start = "2026-04-28T00:00:00"
    end = "2026-04-29T00:00:00"

    print("Descargando mensajes del 28 de abril 2026...")
    all_messages = []
    batch_size = 500
    offset = 0

    while True:
        res = client.table("bot_messages") \
            .select("phone, direction, text, msg_type, created_at, wamid") \
            .gte("created_at", start) \
            .lt("created_at", end) \
            .order("created_at") \
            .range(offset, offset + batch_size - 1) \
            .execute()
        batch = res.data
        if not batch:
            break
        all_messages.extend(batch)
        offset += batch_size
        if len(batch) < batch_size:
            break

    print(f"Total mensajes descargados: {len(all_messages)}")

    # Get conversation metadata
    phones = list(set(m["phone"] for m in all_messages))
    print(f"Teléfonos únicos: {len(phones)}")

    convs = {}
    if phones:
        batch_size_conv = 100
        for i in range(0, len(phones), batch_size_conv):
            phone_batch = phones[i:i+batch_size_conv]
            res = client.table("bot_conversations") \
                .select("phone, client_name, status, empresa, docs_completos") \
                .in_("phone", phone_batch) \
                .execute()
            for c in res.data:
                convs[c["phone"]] = c

    # Group by phone
    by_phone = defaultdict(list)
    for m in all_messages:
        by_phone[m["phone"]].append(m)

    # Generate markdown output for auditor
    output_lines = []
    output_lines.append("# Conversaciones 28 de Abril 2026\n")
    output_lines.append(f"**Total mensajes:** {len(all_messages)} | **Conversaciones:** {len(by_phone)}\n\n")
    output_lines.append("---\n")

    for phone in sorted(by_phone.keys()):
        messages = by_phone[phone]
        if len(messages) < 2:
            continue

        conv_meta = convs.get(phone, {})
        client_name = conv_meta.get("client_name") or "Cliente"
        status = conv_meta.get("status", "")
        empresa = conv_meta.get("empresa") or ""

        output_lines.append(f"\n## {client_name} | {phone}\n")
        output_lines.append(f"**Estado:** {status}")
        if empresa:
            output_lines.append(f" | **Empresa:** {empresa}")
        output_lines.append(f" | **Mensajes:** {len(messages)}\n\n")

        for m in messages:
            direction = m.get("direction", "")
            text = m.get("text", "") or ""
            msg_type = m.get("msg_type", "text")
            ts = m.get("created_at", "")[11:16]  # HH:MM only

            if msg_type in ("image", "document", "audio", "video"):
                text = f"[{msg_type.upper()}]"
            elif text.startswith("[Template:") or text.startswith("[Menu:"):
                pass  # Keep as is
            elif len(text) > 400:
                text = text[:400] + "..."

            prefix = "**Cliente:**" if direction == "inbound" else "**Bot/Asesor:**"
            output_lines.append(f"- `{ts}` {prefix} {text}\n")

        output_lines.append("\n---\n")

    # Write output
    output_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context", "conversaciones_28abril.md")
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(output_lines)

    print(f"\nArchivo generado: {output_file}")
    print(f"Conversaciones con 2+ mensajes: {sum(1 for p, m in by_phone.items() if len(m) >= 2)}")

    # Quick stats
    inbound = sum(1 for m in all_messages if m["direction"] == "inbound")
    outbound = sum(1 for m in all_messages if m["direction"] == "outbound")
    templates = sum(1 for m in all_messages if "[Template:" in (m.get("text") or ""))

    print(f"\nEstadísticas rápidas:")
    print(f"  - Mensajes entrantes: {inbound}")
    print(f"  - Mensajes salientes: {outbound}")
    print(f"  - Templates enviados: {templates}")

if __name__ == "__main__":
    main()

"""
Auditoría completa del bot ProAlto — extracción exhaustiva de conversaciones.
Extrae TODOS los datos de Supabase en un rango de fechas y genera un archivo
Markdown organizado con estadísticas, banderas rojas y conversaciones completas.

Uso:
    python scripts/auditoria_completa.py                          # últimos 15 días
    python scripts/auditoria_completa.py 2026-03-15 2026-03-30    # rango personalizado
"""
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context")
PAGE_SIZE = 1000


# ── Helpers ─────────────────────────────────────────────────────────────────

def _paginated_fetch(client, table, select, date_field="created_at",
                     date_from=None, date_to=None, extra_filters=None,
                     order_field=None):
    """Fetch all rows with pagination."""
    all_data = []
    offset = 0
    while True:
        q = client.table(table).select(select)
        if date_from and date_field:
            q = q.gte(date_field, date_from)
        if date_to and date_field:
            q = q.lte(date_field, date_to)
        if extra_filters:
            for k, v in extra_filters.items():
                if k.startswith("neq_"):
                    q = q.neq(k[4:], v)
                else:
                    q = q.eq(k, v)
        if order_field:
            q = q.order(order_field)
        q = q.range(offset, offset + PAGE_SIZE - 1)
        res = q.execute()
        if not res.data:
            break
        all_data.extend(res.data)
        if len(res.data) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return all_data


def is_advisor_message(text):
    return bool(text and '*' in text and ':*' in text)


def extract_advisor_name(text):
    if not text:
        return None
    match = re.search(r'\*([^*:]+):\*', text)
    return match.group(1).strip() if match else None


# ── Data Extraction ─────────────────────────────────────────────────────────

def fetch_all(client, date_from, date_to):
    print("Descargando mensajes...")
    messages = _paginated_fetch(
        client, "bot_messages",
        "phone, direction, text, msg_type, created_at, wamid",
        date_field="created_at", date_from=date_from, date_to=date_to,
        extra_filters={"neq_msg_type": "deleted"},
        order_field="created_at",
    )
    print(f"  -> {len(messages)} mensajes")

    print("Descargando conversaciones...")
    conversations = _paginated_fetch(
        client, "bot_conversations",
        "phone, client_name, status, updated_at, empresa, docs_faltantes, tipo_empleador, docs_completos",
        date_field=None,  # fetch all, filter by phone later
        order_field="updated_at",
    )
    print(f"  -> {len(conversations)} conversaciones")

    print("Descargando llm_requests...")
    llm_requests = _paginated_fetch(
        client, "llm_requests",
        "phone, client_name, tipo, detalle, created_at, resolved, resolved_at",
        date_field="created_at", date_from=date_from, date_to=date_to,
        order_field="created_at",
    )
    print(f"  -> {len(llm_requests)} solicitudes LLM")

    print("Descargando emails capturados...")
    emails = _paginated_fetch(
        client, "captured_emails",
        "phone, email, name, created_at",
        date_field="created_at", date_from=date_from, date_to=date_to,
        order_field="created_at",
    )
    print(f"  -> {len(emails)} emails")

    print("Descargando cuentas capturadas...")
    cuentas = _paginated_fetch(
        client, "captured_cuentas",
        "phone, numero_cuenta, banco, name, created_at",
        date_field="created_at", date_from=date_from, date_to=date_to,
        order_field="created_at",
    )
    print(f"  -> {len(cuentas)} cuentas")

    print("Descargando documentos recibidos...")
    documents = _paginated_fetch(
        client, "received_documents",
        "phone, client_name, filename, mime_type, storage_url, received_at, triggered_by, reviewed",
        date_field="received_at", date_from=date_from, date_to=date_to,
        order_field="received_at",
    )
    print(f"  -> {len(documents)} documentos")

    return messages, conversations, llm_requests, emails, cuentas, documents


# ── Analysis ────────────────────────────────────────────────────────────────

def analyze(messages, conversations, llm_requests, emails, cuentas, documents, date_from, date_to):
    # Index conversations by phone
    conv_by_phone = {c["phone"]: c for c in conversations}

    # Group messages by phone
    msgs_by_phone = defaultdict(list)
    for m in messages:
        msgs_by_phone[m["phone"]].append(m)

    # Group supplementary data by phone
    llm_by_phone = defaultdict(list)
    for r in llm_requests:
        llm_by_phone[r["phone"]].append(r)
    emails_by_phone = defaultdict(list)
    for e in emails:
        emails_by_phone[e["phone"]].append(e)
    cuentas_by_phone = defaultdict(list)
    for c in cuentas:
        cuentas_by_phone[c["phone"]].append(c)
    docs_by_phone = defaultdict(list)
    for d in documents:
        docs_by_phone[d["phone"]].append(d)

    # Only phones that had messages in the period
    active_phones = sorted(msgs_by_phone.keys(), key=lambda p: msgs_by_phone[p][0]["created_at"])

    # ── Stats ───────────────────────────────────────────────────────────
    total_msgs = len(messages)
    inbound = sum(1 for m in messages if m["direction"] == "inbound")
    outbound = total_msgs - inbound

    status_counter = Counter()
    for phone in active_phones:
        conv = conv_by_phone.get(phone, {})
        status_counter[conv.get("status", "unknown")] += 1

    # Template stats
    template_counter = Counter()
    for m in messages:
        txt = m.get("text") or ""
        if txt.startswith("[Template:"):
            tpl_name = txt.split("]")[0].replace("[Template:", "").strip()
            template_counter[tpl_name] += 1

    # LLM request stats
    llm_type_counter = Counter(r["tipo"] for r in llm_requests)
    llm_resolved = sum(1 for r in llm_requests if r.get("resolved"))
    llm_pending = len(llm_requests) - llm_resolved

    # Advisor stats
    advisor_counter = Counter()
    for m in messages:
        if m["direction"] == "outbound":
            name = extract_advisor_name(m.get("text") or "")
            if name:
                advisor_counter[name] += 1

    # Messages by day
    daily_msgs = Counter()
    for m in messages:
        day = (m.get("created_at") or "")[:10]
        if day:
            daily_msgs[day] += 1

    # Messages by hour
    hourly_msgs = Counter()
    for m in messages:
        ts = m.get("created_at") or ""
        if len(ts) >= 13:
            hourly_msgs[ts[11:13]] += 1

    # ── Red flags per conversation ──────────────────────────────────────
    flags_by_phone = defaultdict(list)

    for phone in active_phones:
        phone_msgs = msgs_by_phone[phone]
        conv = conv_by_phone.get(phone, {})
        status = conv.get("status", "unknown")

        # DEAD_END: last message is inbound, status not agent/archived
        if phone_msgs and phone_msgs[-1]["direction"] == "inbound":
            if status not in ("agent", "agent_silent", "archived"):
                flags_by_phone[phone].append("DEAD_END")

        # ERROR_SISTEMA
        for m_item in phone_msgs:
            txt = (m_item.get("text") or "").lower()
            if "error del sistema" in txt or "no pudimos conectar" in txt:
                flags_by_phone[phone].append("ERROR_SISTEMA")
                break

        # NO_ENTENDI_LOOP
        no_entendi_count = sum(
            1 for m_item in phone_msgs
            if "No entendí tu mensaje" in (m_item.get("text") or "")
        )
        if no_entendi_count >= 2:
            flags_by_phone[phone].append("NO_ENTENDI_LOOP")

        # STUCK_STATE
        if status and status.startswith("waiting_for_"):
            updated = conv.get("updated_at", "")
            if updated:
                try:
                    up_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    if (datetime.now(up_dt.tzinfo) - up_dt).total_seconds() > 86400:
                        flags_by_phone[phone].append("STUCK_STATE")
                except Exception:
                    pass

        # LLM_FALLBACK
        for m_item in phone_msgs:
            if "Déjame verificar eso y te confirmo en un momento" in (m_item.get("text") or ""):
                flags_by_phone[phone].append("LLM_FALLBACK")
                break

        # UNRESOLVED_REQUEST
        for r in llm_by_phone.get(phone, []):
            if not r.get("resolved"):
                flags_by_phone[phone].append("UNRESOLVED_REQUEST")
                break

        # Conversations with advisor but has_advisor detection
        has_advisor = any(
            is_advisor_message(m_item.get("text") or "")
            for m_item in phone_msgs if m_item["direction"] == "outbound"
        )

        # LONG_WAIT_ADVISOR: check if any inbound-to-advisor gap > 30 min
        if has_advisor:
            last_inbound_ts = None
            for m_item in phone_msgs:
                if m_item["direction"] == "inbound":
                    last_inbound_ts = m_item.get("created_at")
                elif m_item["direction"] == "outbound" and is_advisor_message(m_item.get("text") or ""):
                    if last_inbound_ts:
                        try:
                            t1 = datetime.fromisoformat(last_inbound_ts.replace("Z", "+00:00"))
                            t2 = datetime.fromisoformat(m_item["created_at"].replace("Z", "+00:00"))
                            if (t2 - t1).total_seconds() > 1800:
                                flags_by_phone[phone].append("LONG_WAIT_ADVISOR")
                                break
                        except Exception:
                            pass
                    last_inbound_ts = None

    # Count total flags
    all_flags = Counter()
    for flags in flags_by_phone.values():
        for f in flags:
            all_flags[f] += 1

    return {
        "active_phones": active_phones,
        "conv_by_phone": conv_by_phone,
        "msgs_by_phone": msgs_by_phone,
        "llm_by_phone": llm_by_phone,
        "emails_by_phone": emails_by_phone,
        "cuentas_by_phone": cuentas_by_phone,
        "docs_by_phone": docs_by_phone,
        "flags_by_phone": flags_by_phone,
        "stats": {
            "total_conversations": len(active_phones),
            "total_messages": total_msgs,
            "inbound": inbound,
            "outbound": outbound,
            "status_distribution": dict(status_counter.most_common()),
            "template_stats": dict(template_counter.most_common()),
            "llm_requests_total": len(llm_requests),
            "llm_requests_resolved": llm_resolved,
            "llm_requests_pending": llm_pending,
            "llm_type_distribution": dict(llm_type_counter.most_common()),
            "emails_captured": len(emails),
            "cuentas_captured": len(cuentas),
            "documents_received": len(documents),
            "advisor_messages": dict(advisor_counter.most_common()),
            "daily_messages": dict(sorted(daily_msgs.items())),
            "hourly_distribution": dict(sorted(hourly_msgs.items())),
            "red_flags": dict(all_flags.most_common()),
            "conversations_with_flags": sum(1 for f in flags_by_phone.values() if f),
        },
    }


# ── Output Generation ───────────────────────────────────────────────────────

def generate_output(analysis, date_from, date_to):
    stats = analysis["stats"]
    lines = []

    # ── Header ──────────────────────────────────────────────────────────
    lines.append(f"# Auditoría Completa del Bot ProAlto\n")
    lines.append(f"> Período: {date_from[:10]} a {date_to[:10]}\n")
    lines.append(f"> Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

    # ── Stats ───────────────────────────────────────────────────────────
    lines.append("## Resumen Cuantitativo\n\n")
    lines.append(f"| Métrica | Valor |\n|---------|-------|\n")
    lines.append(f"| Conversaciones activas | {stats['total_conversations']} |\n")
    lines.append(f"| Total mensajes | {stats['total_messages']} |\n")
    lines.append(f"| Mensajes entrantes | {stats['inbound']} |\n")
    lines.append(f"| Mensajes salientes | {stats['outbound']} |\n")
    lines.append(f"| Emails capturados | {stats['emails_captured']} |\n")
    lines.append(f"| Cuentas capturadas | {stats['cuentas_captured']} |\n")
    lines.append(f"| Documentos recibidos | {stats['documents_received']} |\n")
    lines.append(f"| Solicitudes LLM | {stats['llm_requests_total']} (resueltas: {stats['llm_requests_resolved']}, pendientes: {stats['llm_requests_pending']}) |\n")
    lines.append(f"| Conversaciones con banderas rojas | {stats['conversations_with_flags']} |\n\n")

    # Status distribution
    lines.append("### Distribución por estado final\n\n")
    for status, count in stats["status_distribution"].items():
        lines.append(f"- **{status}**: {count}\n")
    lines.append("\n")

    # Template stats
    if stats["template_stats"]:
        lines.append("### Templates enviados\n\n")
        for tpl, count in stats["template_stats"].items():
            lines.append(f"- {tpl}: {count}\n")
        lines.append("\n")

    # LLM request types
    if stats["llm_type_distribution"]:
        lines.append("### Solicitudes LLM por tipo\n\n")
        for tipo, count in stats["llm_type_distribution"].items():
            lines.append(f"- **{tipo}**: {count}\n")
        lines.append("\n")

    # Advisor messages
    if stats["advisor_messages"]:
        lines.append("### Mensajes por asesor\n\n")
        for name, count in stats["advisor_messages"].items():
            lines.append(f"- **{name}**: {count}\n")
        lines.append("\n")

    # Daily volume
    lines.append("### Volumen diario\n\n")
    for day, count in stats["daily_messages"].items():
        lines.append(f"- {day}: {count} msgs\n")
    lines.append("\n")

    # Hourly distribution
    lines.append("### Distribución por hora (UTC)\n\n")
    for hour, count in stats["hourly_distribution"].items():
        lines.append(f"- {hour}:00 → {count} msgs\n")
    lines.append("\n")

    # ── Red Flags Summary ───────────────────────────────────────────────
    lines.append("## Banderas Rojas\n\n")
    if stats["red_flags"]:
        lines.append("| Bandera | Conversaciones |\n|---------|---------------|\n")
        for flag, count in stats["red_flags"].items():
            lines.append(f"| {flag} | {count} |\n")
        lines.append("\n")

        # List flagged conversations
        lines.append("### Conversaciones con banderas rojas\n\n")
        for phone in analysis["active_phones"]:
            flags = analysis["flags_by_phone"].get(phone, [])
            if flags:
                conv = analysis["conv_by_phone"].get(phone, {})
                name = conv.get("client_name", "?")
                n_msgs = len(analysis["msgs_by_phone"][phone])
                lines.append(f"- **{phone}** ({name}) — {', '.join(flags)} — {n_msgs} msgs\n")
        lines.append("\n")
    else:
        lines.append("No se detectaron banderas rojas automáticas.\n\n")

    # ── Full Conversations ──────────────────────────────────────────────
    lines.append("---\n\n## Conversaciones Completas\n\n")

    for phone in analysis["active_phones"]:
        phone_msgs = analysis["msgs_by_phone"][phone]
        conv = analysis["conv_by_phone"].get(phone, {})
        flags = analysis["flags_by_phone"].get(phone, [])

        name = conv.get("client_name") or "Cliente"
        status = conv.get("status", "?")
        empresa = conv.get("empresa", "")
        docs_faltantes = conv.get("docs_faltantes", "")

        flag_str = f" 🚩 {', '.join(flags)}" if flags else ""
        lines.append(f"### {name} | {phone}{flag_str}\n")
        lines.append(f"**Estado:** {status} | **Mensajes:** {len(phone_msgs)}")
        if empresa:
            lines.append(f" | **Empresa:** {empresa}")
        lines.append("\n")
        if docs_faltantes:
            lines.append(f"**Docs faltantes:** {docs_faltantes}\n")

        # Supplementary data
        phone_emails = analysis["emails_by_phone"].get(phone, [])
        phone_cuentas = analysis["cuentas_by_phone"].get(phone, [])
        phone_docs = analysis["docs_by_phone"].get(phone, [])
        phone_llm = analysis["llm_by_phone"].get(phone, [])

        if phone_emails:
            lines.append(f"**Emails:** {', '.join(e['email'] for e in phone_emails)}\n")
        if phone_cuentas:
            for c in phone_cuentas:
                lines.append(f"**Cuenta:** {c.get('numero_cuenta', '?')} — {c.get('banco', '?')}\n")
        if phone_docs:
            lines.append(f"**Documentos recibidos:** {len(phone_docs)} archivo(s)\n")
            for d in phone_docs:
                reviewed = "✅" if d.get("reviewed") else "⏳"
                lines.append(f"  - {reviewed} {d.get('filename', '?')} ({d.get('triggered_by', '')})\n")
        if phone_llm:
            lines.append(f"**Solicitudes LLM:**\n")
            for r in phone_llm:
                resolved_mark = "✅" if r.get("resolved") else "⏳"
                lines.append(f"  - {resolved_mark} [{r['tipo']}] {r.get('detalle', '')[:200]}\n")

        lines.append("\n")

        # Messages
        for m in phone_msgs:
            direction = m.get("direction", "")
            text = m.get("text") or ""
            msg_type = m.get("msg_type", "text")
            ts = (m.get("created_at") or "")[:19].replace("T", " ")

            if msg_type in ("image", "document"):
                if text.startswith("http"):
                    text = f"[{msg_type.upper()}: {text}]"
                else:
                    text = f"[{msg_type.upper()}]"

            if not text.strip():
                continue

            if direction == "inbound":
                role = "CLIENTE"
            elif is_advisor_message(text):
                adv_name = extract_advisor_name(text) or "ASESOR"
                role = f"ASESOR ({adv_name})"
                # Strip the advisor prefix for readability
                idx = text.find(':*')
                if idx != -1:
                    text = text[idx + 2:].lstrip('\n').strip()
            else:
                role = "BOT"

            lines.append(f"- `{ts}` **{role}:** {text}\n")

        lines.append("\n---\n\n")

    return "".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    # Parse date range from argv or default to last 15 days
    if len(sys.argv) >= 3:
        date_from = f"{sys.argv[1]}T00:00:00"
        date_to = f"{sys.argv[2]}T23:59:59"
    else:
        now = datetime.now()
        date_to = now.strftime("%Y-%m-%dT23:59:59")
        date_from = (now - timedelta(days=15)).strftime("%Y-%m-%dT00:00:00")

    print(f"Auditoria: {date_from[:10]} - {date_to[:10]}")
    print("Conectando a Supabase...")
    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    messages, conversations, llm_requests, captured_emails, captured_cuentas, documents = fetch_all(client, date_from, date_to)

    if not messages:
        print("No se encontraron mensajes en el período.")
        return

    print("\nAnalizando datos...")
    analysis = analyze(messages, conversations, llm_requests, captured_emails, captured_cuentas, documents, date_from, date_to)

    print("Generando archivo de auditoría...")
    output = generate_output(analysis, date_from, date_to)

    output_file = os.path.join(OUTPUT_DIR, "auditoria_completa.md")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output)

    s = analysis["stats"]
    print(f"\n{'='*50}")
    print(f"Auditoría completada.")
    print(f"  Conversaciones: {s['total_conversations']}")
    print(f"  Mensajes: {s['total_messages']}")
    print(f"  Banderas rojas: {s['conversations_with_flags']} conversaciones")
    print(f"  Archivo: {output_file}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()

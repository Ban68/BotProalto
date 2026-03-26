"""
Analytics query layer for ProAlto WhatsApp Bot.
All metrics are computed on-the-fly from existing Supabase tables.
"""
import random
import statistics
import threading
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from src.conversation_log import supabase_client


# ── Helpers ──────────────────────────────────────────────────────────

def _default_date_range(date_from: str = None, date_to: str = None) -> tuple:
    """Returns (date_from, date_to) defaulting to last 30 days."""
    if not date_to:
        date_to = datetime.now().strftime("%Y-%m-%d")
    if not date_from:
        date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    return f"{date_from}T00:00:00", f"{date_to}T23:59:59"


def _paginated_fetch(table: str, select: str, filters: dict, gte_field: str = None,
                     gte_val: str = None, lte_field: str = None, lte_val: str = None,
                     order_field: str = None, page_size: int = 1000) -> list:
    """Fetch all rows from a Supabase table using pagination."""
    all_data = []
    offset = 0
    while True:
        q = supabase_client.table(table).select(select)
        for k, v in filters.items():
            q = q.eq(k, v)
        if gte_field and gte_val:
            q = q.gte(gte_field, gte_val)
        if lte_field and lte_val:
            q = q.lte(lte_field, lte_val)
        if order_field:
            q = q.order(order_field)
        q = q.range(offset, offset + page_size - 1)
        res = q.execute()
        if not res.data:
            break
        all_data.extend(res.data)
        if len(res.data) < page_size:
            break
        offset += page_size
    return all_data


# ── Funnel Metrics ───────────────────────────────────────────────────

def get_funnel_metrics(date_from: str = None, date_to: str = None) -> dict:
    """
    Compute menu usage breakdown: which buttons users click most.
    Also tracks secondary actions (document upload, advisor requests, etc.)
    """
    dt_from, dt_to = _default_date_range(date_from, date_to)

    # Only main menu buttons (initial user intent)
    MENU_BUTTONS = {
        'Estado Solicitud': 'Estado Solicitud',
        'Solicitar Crédito': 'Solicitar Crédito',
        'Solicitar crédito': 'Solicitar Crédito',
        'Consultar Saldo': 'Consultar Saldo',
        'Hablar con Asesor': 'Hablar con Asesor',
        'Hablar con un asesor': 'Hablar con Asesor',
    }

    try:
        # Fetch all inbound button_reply messages in the range
        msgs = _paginated_fetch(
            'bot_messages', 'phone, text, msg_type',
            {'direction': 'inbound', 'msg_type': 'button_reply'},
            gte_field='created_at', gte_val=dt_from,
            lte_field='created_at', lte_val=dt_to,
        )

        # Count button clicks (total clicks and unique users per button)
        click_counts = Counter()
        unique_users = defaultdict(set)

        for m in msgs:
            txt = (m.get('text') or '').strip()
            label = MENU_BUTTONS.get(txt)
            if label:
                click_counts[label] += 1
                unique_users[label].add(m['phone'])

        # Build ordered results (by click count descending)
        buttons = sorted(click_counts.keys(), key=lambda k: click_counts[k], reverse=True)

        return {
            'buttons': [
                {
                    'label': b,
                    'clicks': click_counts[b],
                    'unique_users': len(unique_users[b]),
                }
                for b in buttons
            ],
            'total_button_clicks': sum(click_counts.values()),
        }
    except Exception as e:
        print(f"[Analytics] get_funnel_metrics error: {e}")
        return {'buttons': [], 'total_button_clicks': 0}


# ── Volume Statistics ────────────────────────────────────────────────

def get_volume_stats(date_from: str = None, date_to: str = None) -> dict:
    """Compute message volume, captures, and daily breakdown."""
    dt_from, dt_to = _default_date_range(date_from, date_to)

    try:
        msgs = _paginated_fetch(
            'bot_messages', 'phone, direction, text, msg_type, created_at',
            {}, gte_field='created_at', gte_val=dt_from,
            lte_field='created_at', lte_val=dt_to,
            order_field='created_at'
        )

        inbound = [m for m in msgs if m['direction'] == 'inbound']
        outbound = [m for m in msgs if m['direction'] == 'outbound']
        unique_phones = {m['phone'] for m in msgs}

        # Template counts
        template_verde = sum(1 for m in outbound if m.get('text') == '[Template: estado_verde]')
        template_rojo = sum(1 for m in outbound if m.get('text') == '[Template: estado_rojo]')
        template_amarillo = sum(1 for m in outbound if m.get('text') == '[Template: estado_amarillo]')

        # Capture counts
        emails = _paginated_fetch('captured_emails', 'id', {}, gte_field='created_at', gte_val=dt_from, lte_field='created_at', lte_val=dt_to)
        cuentas = _paginated_fetch('captured_cuentas', 'id', {}, gte_field='created_at', gte_val=dt_from, lte_field='created_at', lte_val=dt_to)
        docs = _paginated_fetch('received_documents', 'id', {}, gte_field='received_at', gte_val=dt_from, lte_field='received_at', lte_val=dt_to)

        # LLM requests
        llm_all = _paginated_fetch('llm_requests', 'id, resolved', {}, gte_field='created_at', gte_val=dt_from, lte_field='created_at', lte_val=dt_to)
        llm_resolved = sum(1 for r in llm_all if r.get('resolved'))

        # Agent sessions: phones that had advisor messages
        agent_phones = set()
        for m in outbound:
            txt = m.get('text') or ''
            if '*' in txt and ':*' in txt:
                agent_phones.add(m['phone'])

        # Daily breakdown
        daily = defaultdict(lambda: {'inbound': 0, 'outbound': 0, 'phones': set()})
        for m in msgs:
            day = m['created_at'][:10]
            daily[day][m['direction']] += 1
            daily[day]['phones'].add(m['phone'])

        daily_breakdown = sorted([
            {
                'date': day,
                'inbound': d['inbound'],
                'outbound': d['outbound'],
                'unique_users': len(d['phones']),
            }
            for day, d in daily.items()
        ], key=lambda x: x['date'])

        # New conversations: phones whose first-ever message is in this range
        first_msgs = {}
        for m in msgs:
            p = m['phone']
            if p not in first_msgs or m['created_at'] < first_msgs[p]:
                first_msgs[p] = m['created_at']

        # Check if their first message ever is in this range (query earlier messages)
        new_conversations = 0
        phones_to_check = list(unique_phones)
        for i in range(0, len(phones_to_check), 50):
            batch = phones_to_check[i:i+50]
            res = supabase_client.table('bot_messages') \
                .select('phone') \
                .in_('phone', batch) \
                .lt('created_at', dt_from) \
                .limit(len(batch)) \
                .execute()
            phones_with_earlier = {r['phone'] for r in res.data}
            new_conversations += sum(1 for p in batch if p not in phones_with_earlier)

        return {
            'total_messages': len(msgs),
            'inbound_messages': len(inbound),
            'outbound_messages': len(outbound),
            'unique_users': len(unique_phones),
            'new_conversations': new_conversations,
            'agent_sessions': len(agent_phones),
            'templates_sent': {
                'estado_verde': template_verde,
                'estado_rojo': template_rojo,
                'estado_amarillo': template_amarillo,
            },
            'emails_captured': len(emails),
            'cuentas_captured': len(cuentas),
            'documents_received': len(docs),
            'llm_requests_total': len(llm_all),
            'llm_requests_resolved': llm_resolved,
            'daily_breakdown': daily_breakdown,
        }
    except Exception as e:
        print(f"[Analytics] get_volume_stats error: {e}")
        return {
            'total_messages': 0, 'inbound_messages': 0, 'outbound_messages': 0,
            'unique_users': 0, 'new_conversations': 0, 'agent_sessions': 0,
            'templates_sent': {'estado_verde': 0, 'estado_rojo': 0, 'estado_amarillo': 0},
            'emails_captured': 0, 'cuentas_captured': 0, 'documents_received': 0,
            'llm_requests_total': 0, 'llm_requests_resolved': 0,
            'daily_breakdown': [],
        }


# ── Response Time Metrics ────────────────────────────────────────────

def get_response_time_metrics(date_from: str = None, date_to: str = None) -> dict:
    """
    Calculate advisor response times based on agent message patterns.
    Advisor messages have the pattern: *advisor_name:* message
    """
    dt_from, dt_to = _default_date_range(date_from, date_to)

    try:
        msgs = _paginated_fetch(
            'bot_messages', 'phone, direction, text, created_at',
            {}, gte_field='created_at', gte_val=dt_from,
            lte_field='created_at', lte_val=dt_to,
            order_field='created_at'
        )

        # Group messages by phone
        by_phone = defaultdict(list)
        for m in msgs:
            by_phone[m['phone']].append(m)

        response_times = []
        agent_conversations = set()
        agent_messages_count = 0

        for phone, phone_msgs in by_phone.items():
            # Find advisor outbound messages (contain *name:*)
            for i, m in enumerate(phone_msgs):
                if m['direction'] != 'outbound':
                    continue
                txt = m.get('text') or ''
                # Match pattern: starts with advisor prefix like "👨‍💼 *Name:*"
                if not ('*' in txt and ':*' in txt):
                    continue

                agent_messages_count += 1
                agent_conversations.add(phone)

                # Find the most recent inbound message before this one
                for j in range(i - 1, -1, -1):
                    if phone_msgs[j]['direction'] == 'inbound':
                        try:
                            t_in = datetime.fromisoformat(phone_msgs[j]['created_at'].replace('Z', '+00:00'))
                            t_out = datetime.fromisoformat(m['created_at'].replace('Z', '+00:00'))
                            delta = (t_out - t_in).total_seconds()
                            if 0 < delta < 86400:  # sanity: within 24h
                                response_times.append(delta)
                        except (ValueError, TypeError):
                            pass
                        break

        # Bucket histogram: 0-1min, 1-3min, 3-5min, 5-10min, 10-30min, 30+min
        buckets = [60, 180, 300, 600, 1800, float('inf')]
        bucket_labels = ['0-1min', '1-3min', '3-5min', '5-10min', '10-30min', '30+min']
        histogram = [0] * len(buckets)
        for t in response_times:
            for idx, limit in enumerate(buckets):
                if t <= limit:
                    histogram[idx] += 1
                    break

        avg_rt = statistics.mean(response_times) if response_times else 0
        median_rt = statistics.median(response_times) if response_times else 0
        p90_rt = (sorted(response_times)[int(len(response_times) * 0.9)] if len(response_times) >= 2 else avg_rt)

        return {
            'avg_response_seconds': round(avg_rt, 1),
            'median_response_seconds': round(median_rt, 1),
            'p90_response_seconds': round(p90_rt, 1),
            'total_agent_conversations': len(agent_conversations),
            'total_agent_messages_sent': agent_messages_count,
            'total_response_samples': len(response_times),
            'histogram': histogram,
            'histogram_labels': bucket_labels,
        }
    except Exception as e:
        print(f"[Analytics] get_response_time_metrics error: {e}")
        return {
            'avg_response_seconds': 0, 'median_response_seconds': 0,
            'p90_response_seconds': 0, 'total_agent_conversations': 0,
            'total_agent_messages_sent': 0, 'total_response_samples': 0,
            'histogram': [0]*6,
            'histogram_labels': ['0-1min', '1-3min', '3-5min', '5-10min', '10-30min', '30+min'],
        }


# ── Conversation Sampling ────────────────────────────────────────────

def get_conversation_sample(sample_size: int = 10, date_from: str = None, date_to: str = None) -> list:
    """Return a random sample of conversations with full message history."""
    dt_from, dt_to = _default_date_range(date_from, date_to)

    try:
        # Get distinct phones active in range
        msgs = _paginated_fetch(
            'bot_messages', 'phone',
            {}, gte_field='created_at', gte_val=dt_from,
            lte_field='created_at', lte_val=dt_to
        )
        all_phones = list({m['phone'] for m in msgs})

        if not all_phones:
            return []

        selected = random.sample(all_phones, min(sample_size, len(all_phones)))

        conversations = []
        for phone in selected:
            # Fetch full history for this phone in the date range
            phone_msgs = _paginated_fetch(
                'bot_messages', 'direction, text, msg_type, created_at',
                {'phone': phone},
                gte_field='created_at', gte_val=dt_from,
                lte_field='created_at', lte_val=dt_to,
                order_field='created_at'
            )

            # Get client name
            res = supabase_client.table('bot_conversations') \
                .select('client_name, status') \
                .eq('phone', phone) \
                .execute()
            client_name = res.data[0].get('client_name', 'Cliente') if res.data else 'Cliente'
            status = res.data[0].get('status', 'unknown') if res.data else 'unknown'

            conversations.append({
                'phone': phone,
                'client_name': client_name,
                'current_status': status,
                'message_count': len(phone_msgs),
                'messages': [
                    {
                        'direction': m['direction'],
                        'text': m.get('text') or '',
                        'msg_type': m.get('msg_type', 'text'),
                        'timestamp': m['created_at'],
                    }
                    for m in phone_msgs
                ],
            })

        return conversations
    except Exception as e:
        print(f"[Analytics] get_conversation_sample error: {e}")
        return []


# ── AI Audit ─────────────────────────────────────────────────────────

_AUDIT_SYSTEM_PROMPT = """Eres un analista experto de conversaciones para ProAlto, una financiera colombiana de créditos de libranza.
Revisas conversaciones del bot de WhatsApp para identificar oportunidades de mejora.

Analiza la conversación y responde EXCLUSIVAMENTE con un JSON válido (sin markdown, sin texto adicional):

{
    "resolucion": "resolved" | "unresolved" | "partial",
    "friccion": ["punto de fricción 1", "punto de fricción 2"],
    "oportunidad_mejora": ["sugerencia 1", "sugerencia 2"],
    "sentimiento": "positive" | "neutral" | "negative",
    "categoria": "status_check" | "email_capture" | "document_upload" | "account_capture" | "credit_request" | "support" | "balance_check" | "other",
    "notable": "hallazgo notable o null"
}

Criterios:
- resolucion: "resolved" si el cliente obtuvo lo que necesitaba, "unresolved" si no, "partial" si parcialmente.
- friccion: momentos donde el cliente se confundió, frustró, o el bot falló. Lista vacía si no hay.
- oportunidad_mejora: sugerencias concretas para mejorar el flujo o las respuestas. Lista vacía si todo bien.
- sentimiento: tono general del cliente durante la conversación.
- categoria: tema principal de la conversación.
- notable: cualquier hallazgo importante (patrón nuevo, queja recurrente, caso de uso inesperado). null si nada notable."""


def _format_transcript(messages: list) -> str:
    """Format messages as a readable transcript for the LLM."""
    lines = []
    for m in messages:
        role = "CLIENTE" if m['direction'] == 'inbound' else "BOT"
        text = m.get('text') or '[archivo]'
        if len(text) > 500:
            text = text[:500] + '...'
        ts = m.get('timestamp', '')[:16]
        lines.append(f"[{ts}] {role}: {text}")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    import json
    import re

    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block ```json ... ``` or ``` ... ```
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from response: {text[:200]}")


def _analyze_single_conversation(conversation: dict) -> dict:
    """Call Claude to analyze a single conversation."""
    import anthropic
    import os

    try:
        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        transcript = _format_transcript(conversation['messages'])

        if not transcript.strip():
            return {
                "resolucion": "error",
                "friccion": [],
                "oportunidad_mejora": [],
                "sentimiento": "neutral",
                "categoria": "other",
                "notable": "Conversación vacía"
            }

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=_AUDIT_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Conversación con {conversation.get('client_name', 'Cliente')} ({conversation['phone']}), {conversation['message_count']} mensajes:\n\n{transcript}"
            }],
        )

        raw = response.content[0].text.strip()
        return _extract_json(raw)
    except Exception as e:
        print(f"[Audit] Error analyzing conversation {conversation.get('phone')}: {e}")
        return {
            "resolucion": "error",
            "friccion": [],
            "oportunidad_mejora": [],
            "sentimiento": "neutral",
            "categoria": "other",
            "notable": f"Error en análisis: {str(e)[:100]}"
        }


def _aggregate_audit_results(individual_results: list) -> dict:
    """Aggregate individual conversation analyses into a summary report."""
    total = len(individual_results)
    if total == 0:
        return {"summary": {}, "top_friction_points": [], "top_improvements": [], "notable_findings": [], "individual_results": []}

    resolucion = Counter(r.get('resolucion', 'error') for r in individual_results)
    sentimiento = Counter(r.get('sentimiento', 'neutral') for r in individual_results)
    categoria = Counter(r.get('categoria', 'other') for r in individual_results)

    # Aggregate friction points and improvements
    all_friction = []
    all_improvements = []
    notable = []

    for r in individual_results:
        all_friction.extend(r.get('friccion', []))
        all_improvements.extend(r.get('oportunidad_mejora', []))
        if r.get('notable') and r['notable'] != 'null':
            notable.append(r['notable'])

    # Count and rank by frequency
    friction_counter = Counter(all_friction)
    improvement_counter = Counter(all_improvements)

    return {
        "summary": {
            "total_analyzed": total,
            "resolucion": dict(resolucion),
            "sentimiento": dict(sentimiento),
            "categoria": dict(categoria),
        },
        "top_friction_points": [{"text": k, "count": v} for k, v in friction_counter.most_common(10)],
        "top_improvements": [{"text": k, "count": v} for k, v in improvement_counter.most_common(10)],
        "notable_findings": notable,
        "individual_results": individual_results,
    }


def run_conversation_audit(audit_id: str, sample_size: int, date_from: str, date_to: str):
    """
    Background task: sample conversations, analyze with AI, store results.
    """
    try:
        # Update status to running
        supabase_client.table('audit_reports').update({
            'status': 'running'
        }).eq('id', audit_id).execute()

        # Get sample
        conversations = get_conversation_sample(sample_size, date_from, date_to)

        if not conversations:
            supabase_client.table('audit_reports').update({
                'status': 'completed',
                'report': {"summary": {"total_analyzed": 0}, "top_friction_points": [], "top_improvements": [], "notable_findings": [], "individual_results": []}
            }).eq('id', audit_id).execute()
            return

        # Analyze each conversation
        results = []
        for conv in conversations:
            if conv['message_count'] < 2:
                continue
            analysis = _analyze_single_conversation(conv)
            analysis['phone'] = conv['phone']
            analysis['client_name'] = conv.get('client_name', 'Cliente')
            analysis['message_count'] = conv['message_count']
            results.append(analysis)

        # Aggregate
        report = _aggregate_audit_results(results)

        # Store
        supabase_client.table('audit_reports').update({
            'status': 'completed',
            'report': report
        }).eq('id', audit_id).execute()

    except Exception as e:
        print(f"[Audit] run_conversation_audit error: {e}")
        try:
            supabase_client.table('audit_reports').update({
                'status': 'failed',
                'error': str(e)[:500]
            }).eq('id', audit_id).execute()
        except Exception:
            pass


def start_audit(sample_size: int = 10, date_from: str = None, date_to: str = None) -> str:
    """Create an audit record and launch the background analysis. Returns audit_id."""
    dt_from, dt_to = _default_date_range(date_from, date_to)
    audit_id = str(uuid.uuid4())

    supabase_client.table('audit_reports').insert({
        'id': audit_id,
        'date_from': dt_from[:10],
        'date_to': dt_to[:10],
        'sample_size': sample_size,
        'status': 'running',
    }).execute()

    threading.Thread(
        target=run_conversation_audit,
        args=(audit_id, sample_size, dt_from[:10], dt_to[:10]),
        daemon=True
    ).start()

    return audit_id


def get_audit_report(audit_id: str) -> dict | None:
    """Fetch a single audit report by ID."""
    try:
        res = supabase_client.table('audit_reports') \
            .select('*') \
            .eq('id', audit_id) \
            .execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"[Analytics] get_audit_report error: {e}")
        return None


def get_audit_list() -> list:
    """Fetch all audit reports, most recent first."""
    try:
        res = supabase_client.table('audit_reports') \
            .select('id, created_at, date_from, date_to, sample_size, status') \
            .order('created_at', desc=True) \
            .limit(20) \
            .execute()
        return res.data
    except Exception as e:
        print(f"[Analytics] get_audit_list error: {e}")
        return []

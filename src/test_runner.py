"""
Orquestador del módulo de pruebas del Agente LLM (panel /admin/test v2).

Concentra:
- Persistencia en Supabase de sesiones de prueba y sus mensajes/anotaciones.
- LLM-cliente: un Claude jugando rol de cliente real con persona + objetivo.
- Mapeo en memoria test_phone → session_id para el flujo manual.
- Extracción de señales del LLM (mismo formato que flows._process_llm_signals).

Importante: este módulo NO modifica test_mode.py — solo observa los outbound
después de cada turno y los graba en Supabase.
"""
import re
import time
import threading
import uuid
from datetime import datetime
from typing import Optional

from src import test_mode
from src.test_personas import get_persona

# Supabase client reutilizado de conversation_log (ya validado en arranque)
from src.conversation_log import supabase_client


# Mapeo en memoria: test_phone -> session_id (uuid str)
# Se usa en el modo manual para que /test/send sepa si debe persistir.
_phone_to_session: dict[str, str] = {}
# Cache liviano de sesiones auto (para no consultar la DB en cada turno).
_auto_session_meta: dict[str, dict] = {}
_lock = threading.RLock()


# ── Helpers de mapeo ────────────────────────────────────────────────

def bind(test_phone: str, session_id: str, meta: Optional[dict] = None) -> None:
    with _lock:
        _phone_to_session[test_phone] = session_id
        if meta is not None:
            _auto_session_meta[session_id] = meta


def unbind(test_phone: str) -> None:
    with _lock:
        sid = _phone_to_session.pop(test_phone, None)
        if sid:
            _auto_session_meta.pop(sid, None)


def session_id_for(test_phone: str) -> Optional[str]:
    with _lock:
        return _phone_to_session.get(test_phone)


def meta_for(session_id: str) -> Optional[dict]:
    with _lock:
        return _auto_session_meta.get(session_id)


# ── Extracción de señales del outbound ─────────────────────────────

_SIGNAL_PATTERN = re.compile(
    r'\[(HABLAR_ASESOR|MOSTRAR_MENU|REGISTRAR_SOLICITUD:[^\]]+)\]'
)


def extract_signals(text: str) -> list[str]:
    if not text:
        return []
    return _SIGNAL_PATTERN.findall(text)


# ── Persistencia base ──────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _next_seq(session_id: str) -> int:
    if supabase_client is None:
        return 1
    try:
        res = (
            supabase_client.table('test_messages')
            .select('seq')
            .eq('session_id', session_id)
            .order('seq', desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return int(res.data[0]['seq']) + 1
    except Exception as e:
        print(f"[test_runner] _next_seq error: {e}")
    return 1


def create_session(
    mode: str,
    persona_slug: Optional[str] = None,
    objetivo: Optional[str] = None,
    categoria_cedula: Optional[str] = None,
    cedula_used: Optional[str] = None,
    client_name: Optional[str] = None,
    started_by: Optional[str] = None,
    test_phone: Optional[str] = None,
) -> Optional[str]:
    """Inserta fila en test_sessions y devuelve session_id (uuid str).
    Devuelve None si falla la persistencia."""
    if supabase_client is None:
        print("[test_runner] Supabase no inicializado, sesión no se persistirá")
        return None
    payload = {
        'test_phone': test_phone or '',
        'mode': mode,
        'persona_slug': persona_slug,
        'objetivo': objetivo,
        'categoria_cedula': categoria_cedula,
        'cedula_used': cedula_used,
        'client_name': client_name,
        'started_by': started_by,
    }
    try:
        res = supabase_client.table('test_sessions').insert(payload).execute()
        if res.data:
            sid = res.data[0]['id']
            if test_phone:
                bind(test_phone, sid, {
                    'mode': mode,
                    'persona_slug': persona_slug,
                    'objetivo': objetivo,
                    'cedula_used': cedula_used,
                })
            return sid
    except Exception as e:
        print(f"[test_runner] create_session error: {e}")
    return None


def persist_inbound(
    session_id: Optional[str],
    text: str,
    role: str = 'user',
    msg_type: str = 'text',
) -> None:
    """Persiste un mensaje del 'cliente' (humano manual o LLM-cliente)."""
    if not session_id or supabase_client is None:
        return
    seq = _next_seq(session_id)
    try:
        supabase_client.table('test_messages').insert({
            'session_id': session_id,
            'direction': 'inbound',
            'role': role,
            'text': text or '',
            'msg_type': msg_type,
            'seq': seq,
        }).execute()
    except Exception as e:
        print(f"[test_runner] persist_inbound error: {e}")


def persist_outbound(
    session_id: Optional[str],
    outbound_items: list,
    total_latency_ms: Optional[int] = None,
) -> list[str]:
    """Persiste los outbound items que devolvió test_mode.drain_outbound().
    Devuelve la lista de señales detectadas en este turno."""
    if not session_id or supabase_client is None or not outbound_items:
        return []
    base_seq = _next_seq(session_id)
    signals_acc: list[str] = []
    rows = []
    first_assistant = True
    for idx, item in enumerate(outbound_items):
        item_type = item.get('type', 'text')
        # Texto representativo
        if item_type == 'text':
            text = item.get('body') or ''
            role = 'assistant'
        elif item_type == 'interactive':
            text = item.get('body') or ''
            btns = item.get('buttons') or []
            if btns:
                # Formato legible: [Botones: id1="Title 1" | id2="Title 2"]
                # El cliente-LLM lo parsea para emitir [BUTTON:id].
                btn_pairs = ' | '.join(
                    f'{b.get("id", "")}="{b.get("title", "")}"' for b in btns
                )
                text += f'\n\n[Botones disponibles: {btn_pairs}]'
            role = 'assistant'
        elif item_type == 'list':
            text = item.get('body') or ''
            list_rows = []
            for s in item.get('sections') or []:
                for r in s.get('rows') or []:
                    rid = r.get('id') or ''
                    title = r.get('title') or rid
                    list_rows.append(f'{rid}="{title}"')
            if list_rows:
                text += f'\n\n[Opciones disponibles: {" | ".join(list_rows)}]'
            role = 'assistant'
        elif item_type == 'image':
            text = f"[Imagen] {item.get('url', '')} {item.get('caption', '') or ''}".strip()
            role = 'assistant'
        elif item_type == 'document':
            text = f"[Documento] {item.get('filename', '')} {item.get('url', '')} {item.get('caption', '') or ''}".strip()
            role = 'assistant'
        elif item_type == 'template':
            text = f"[Template: {item.get('template_name', '')}]"
            role = 'assistant'
        elif item_type == 'admin_notification_suppressed':
            text = item.get('body') or 'Notificación a admin suprimida'
            role = 'notice'
        elif item_type == 'llm_request_recorded':
            text = f"[REGISTRAR_SOLICITUD:{item.get('tipo', '')}] {item.get('detalle', '')}"
            role = 'notice'
            signals_acc.append(f"REGISTRAR_SOLICITUD:{item.get('tipo', '')}")
        elif item_type == 'document_request_recorded':
            text = (f"[SOLICITUD_DOCUMENTO:{item.get('doc_type', '')}] "
                    f"(origen: {item.get('source', '')}) {item.get('detalle', '')}")
            role = 'notice'
            # Cuando viene del agente LLM la origina la señal REGISTRAR_SOLICITUD;
            # se registra para que la validación de señales siga funcionando.
            if item.get('source') == 'llm':
                signals_acc.append(f"REGISTRAR_SOLICITUD:{item.get('doc_type', '')}")
        else:
            text = str(item)
            role = 'notice'

        item_signals = extract_signals(text)
        signals_acc.extend(item_signals)

        rows.append({
            'session_id': session_id,
            'direction': 'outbound',
            'role': role,
            'text': text,
            'msg_type': item.get('msg_type', item_type if item_type in (
                'text', 'button', 'image', 'document', 'list', 'template',
                'admin_notification_suppressed', 'llm_request_recorded',
                'document_request_recorded',
            ) else 'text'),
            'signals': item_signals or None,
            'latency_ms': (total_latency_ms if first_assistant and role == 'assistant' else None),
            'seq': base_seq + idx,
        })
        if role == 'assistant':
            first_assistant = False

    try:
        supabase_client.table('test_messages').insert(rows).execute()
    except Exception as e:
        print(f"[test_runner] persist_outbound error: {e}")

    # Agregar señales al array de la sesión
    if signals_acc:
        try:
            sess = (
                supabase_client.table('test_sessions')
                .select('signals_emitted, num_turns')
                .eq('id', session_id)
                .single()
                .execute()
            )
            existing = sess.data.get('signals_emitted') or []
            existing.extend(signals_acc)
            supabase_client.table('test_sessions').update({
                'signals_emitted': existing,
            }).eq('id', session_id).execute()
        except Exception as e:
            print(f"[test_runner] update signals error: {e}")

    return signals_acc


def increment_turns(session_id: Optional[str]) -> None:
    if not session_id or supabase_client is None:
        return
    try:
        sess = (
            supabase_client.table('test_sessions')
            .select('num_turns')
            .eq('id', session_id)
            .single()
            .execute()
        )
        current = int(sess.data.get('num_turns') or 0)
        supabase_client.table('test_sessions').update({
            'num_turns': current + 1,
        }).eq('id', session_id).execute()
    except Exception as e:
        print(f"[test_runner] increment_turns error: {e}")


def end_session(session_id: Optional[str]) -> None:
    if not session_id or supabase_client is None:
        return
    try:
        supabase_client.table('test_sessions').update({
            'ended_at': _now_iso(),
        }).eq('id', session_id).execute()
    except Exception as e:
        print(f"[test_runner] end_session error: {e}")


# ── LLM-cliente ─────────────────────────────────────────────────────

_CLIENT_REGLAS_BASE = """
REGLAS:
- Responde en mensajes cortos (1-3 frases), tono informal, español colombiano.
- Sin emojis. Sin signos de apertura (¿ ¡).
- No saltes a otros temas; mantén el objetivo.
- Si el asesor pide datos que tu persona razonablemente tendría (email, cuenta,
  empresa, salario), invéntalos coherentes y compártelos.
- NUNCA reveles que eres una IA, ni siquiera si el asesor te lo pregunta.
"""

_CLIENT_REGLAS_BOTONES = """
BOTONES (importante):
- Cuando el bot te ofrezca botones (verás un bloque como
  "[Botones disponibles: id1=\"Texto 1\" | id2=\"Texto 2\"]"), elige UN botón
  respondiendo EXACTAMENTE con el formato: [BUTTON:id]
  Ejemplo: si ves "[Botones disponibles: accept_terms=\"Acepto\" | decline_terms=\"No Acepto\"]"
  y quieres aceptar, responde solo: [BUTTON:accept_terms]
- Lo mismo aplica a "[Opciones disponibles: ...]" (menús de lista).
- NO escribas el texto del botón como mensaje normal — usa [BUTTON:id] para
  que cuente como un clic real.
"""

_CLIENT_REGLAS_FIN = """
CUÁNDO TERMINAR:
- Cuando consideres que tu objetivo se cumplió, o sientas que la conversación
  está en bucle, o el asesor te haya pedido hablar con un humano (o dicho que
  un asesor te va a contactar), responde EXACTAMENTE con: [FIN]
"""


_BUTTON_PATTERN = re.compile(r'\[BUTTON:([^\]]+)\]')


def parse_client_button(text: str) -> Optional[str]:
    """Si el cliente-LLM respondió [BUTTON:xxx], devuelve 'xxx'. Si no, None."""
    if not text:
        return None
    m = _BUTTON_PATTERN.search(text)
    return m.group(1).strip() if m else None


def _build_client_system_prompt(
    persona: dict,
    objetivo: str,
    cedula_used: Optional[str],
    mode: str = 'auto_flujos',
) -> str:
    cedula_block = ''
    if cedula_used:
        cedula_block = (
            f"\nTIENES LA SIGUIENTE CÉDULA: {cedula_used}\n"
            "Cuando el asesor te la pida, dásela tal cual, sin más.\n"
        )

    if mode == 'auto_llm':
        # El bot responde con el Agente LLM: conversación por texto, sin menús.
        contexto = (
            "CONTEXTO DE LA CONVERSACIÓN:\n"
            "- Estás chateando con un asesor de ProAlto que responde por texto "
            "(conversación normal de WhatsApp, sin menús ni botones).\n"
            "- Tu primer mensaje debe ir directo a tu objetivo; pregunta con "
            "naturalidad y repregunta si algo no te queda claro.\n\n"
        )
        reglas = _CLIENT_REGLAS_BASE + _CLIENT_REGLAS_FIN
    else:
        # El bot recorre flujos deterministas con menús de botones.
        contexto = (
            "CONTEXTO DE LA CONVERSACIÓN:\n"
            "- Ya aceptaste el tratamiento de datos (consentimiento) en un paso "
            "previo. NO menciones el consentimiento; tu primer mensaje debe ir "
            "directo a tu objetivo.\n"
            "- El bot probablemente te recibirá con el menú principal "
            "(opciones como Soy Cliente, Estado Solicitud, Solicitar Crédito). "
            "Si te ofrece botones, elígelos con [BUTTON:id].\n\n"
        )
        reglas = _CLIENT_REGLAS_BASE + _CLIENT_REGLAS_BOTONES + _CLIENT_REGLAS_FIN

    return (
        "Eres un cliente colombiano interactuando por WhatsApp con un asesor "
        "de ProAlto (una financiera de créditos de libranza). NO eres una IA "
        "y NO debes revelarlo nunca, ni siquiera si el asesor te lo pregunta "
        "directamente.\n\n"
        f"{contexto}"
        "PERSONA:\n"
        f"{persona['prompt_body']}\n\n"
        f"OBJETIVO de esta conversación:\n{objetivo}\n"
        f"{cedula_block}"
        f"{reglas}"
    )


def _fetch_history_for_client_llm(session_id: str, limit: int = 20) -> list[dict]:
    """Construye historial INVERTIDO para el cliente-LLM: lo que el bot dijo
    se le pasa como 'user', lo que el cliente-LLM dijo como 'assistant'."""
    if supabase_client is None:
        return []
    try:
        res = (
            supabase_client.table('test_messages')
            .select('direction, role, text, seq')
            .eq('session_id', session_id)
            .order('seq', desc=False)
            .execute()
        )
    except Exception as e:
        print(f"[test_runner] _fetch_history error: {e}")
        return []

    msgs: list[dict] = []
    for m in res.data or []:
        role = m['role']
        text = (m.get('text') or '').strip()
        if not text:
            continue
        # Notices internos no van al cliente-LLM (no son parte visible del chat)
        if role == 'notice':
            continue
        if role == 'client_llm':
            msgs.append({'role': 'assistant', 'content': text})
        elif role == 'assistant':
            msgs.append({'role': 'user', 'content': text})
        # 'user' role (manual mode) no aplica en auto, lo ignoramos por seguridad

    # Colapsar consecutivos del mismo rol (Anthropic requiere alternar)
    merged: list[dict] = []
    for msg in msgs[-limit:]:
        if merged and merged[-1]['role'] == msg['role']:
            merged[-1]['content'] += '\n' + msg['content']
        else:
            merged.append(dict(msg))
    return merged


def next_client_llm_turn(session_id: str) -> Optional[str]:
    """Genera el próximo mensaje del cliente-LLM. Devuelve None si el modelo
    respondió [FIN] o si hubo error."""
    meta = meta_for(session_id) or {}
    persona = get_persona(meta.get('persona_slug') or '')
    if not persona:
        print(f"[test_runner] persona no encontrada para session {session_id}")
        return None

    history = _fetch_history_for_client_llm(session_id)
    # Si es el primer turno, no hay historial. Pedimos al cliente que abra
    # la conversación con un saludo coherente con su persona+objetivo.
    if not history:
        history = [{
            'role': 'user',
            'content': '(Iniciaste el chat de WhatsApp con ProAlto. Escribe tu primer mensaje.)',
        }]
    elif history[-1]['role'] == 'assistant':
        # Si el último turno persistido es del cliente-LLM, el bot todavía no
        # respondió. Esto no debería pasar en run_auto_turn, pero por defensa
        # le pedimos que espere.
        return None

    system_prompt = _build_client_system_prompt(
        persona,
        meta.get('objetivo') or '',
        meta.get('cedula_used'),
        mode=meta.get('mode') or 'auto_flujos',
    )

    try:
        from src.llm import _get_client
        import anthropic  # noqa
        client = _get_client()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=200,
            system=system_prompt,
            messages=history,
        )
        text = response.content[0].text.strip()
    except Exception as e:
        print(f"[test_runner] LLM-cliente error: {e}")
        return None

    # Si pegó FIN (puede venir solo o al final del mensaje), termina.
    if text.upper().strip() == '[FIN]' or text.upper().endswith('[FIN]'):
        # Si trae texto antes del [FIN], lo descartamos para no contaminar el
        # historial con un mensaje a medias. El [FIN] solo señaliza el cierre.
        return None
    return text


# ── Loop automático ────────────────────────────────────────────────

def run_auto_turn(session_id: str, test_phone: str, llm_wait_timeout: float = 8.0) -> dict:
    """Un ciclo completo del modo auto:
      1) Pide turno al cliente-LLM.
      2) Si no es [FIN], inyecta el mensaje al bot por FlowHandler.
      3) Espera a que el LLM del bot termine (timeout configurable).
      4) Drena outbound y persiste.
    Devuelve un dict con el resultado del turno."""

    # 1) Cliente-LLM
    client_text = next_client_llm_turn(session_id)
    if client_text is None:
        end_session(session_id)
        return {
            'finished': True,
            'reason': 'client_fin',
            'client_text': None,
            'bot_messages': [],
            'signals': [],
        }

    # 2) Detectar si el cliente-LLM "clickeó" un botón
    button_id = parse_client_button(client_text)
    inbound_for_db = client_text
    if button_id:
        # Normalizamos el texto persistido para que en la UI de revisión
        # se vea claramente cuál botón eligió.
        inbound_for_db = f'▶ [BUTTON:{button_id}]'

    # 3) Persistir inbound del cliente-LLM
    persist_inbound(
        session_id,
        inbound_for_db,
        role='client_llm',
        msg_type='button' if button_id else 'text',
    )

    # 4) Inyectar al bot via webhook simulado (texto o button_reply)
    test_mode.drain_outbound(test_phone)  # limpiar buffer previo por seguridad
    msg_id = f"test_msg_{int(time.time() * 1000)}"
    if button_id:
        message = {
            'from': test_phone,
            'id': msg_id,
            'type': 'interactive',
            'interactive': {
                'type': 'button_reply',
                'button_reply': {'id': button_id, 'title': button_id},
            },
        }
    else:
        message = {
            'from': test_phone,
            'id': msg_id,
            'type': 'text',
            'text': {'body': client_text},
        }
    payload = {'entry': [{'changes': [{'value': {'messages': [message]}}]}]}
    t_start = time.time()
    try:
        from src.flows import FlowHandler
        FlowHandler.handle_incoming_message(payload)
    except Exception as e:
        print(f"[test_runner] FlowHandler error: {e}")
        return {
            'finished': True,
            'reason': 'flow_error',
            'client_text': client_text,
            'bot_messages': [],
            'signals': [],
            'error': str(e),
        }

    # 4) Esperar al LLM del bot si quedó en background
    deadline = time.time() + llm_wait_timeout
    while time.time() < deadline:
        if not test_mode.is_llm_pending(test_phone):
            break
        time.sleep(0.15)

    latency_ms = int((time.time() - t_start) * 1000)
    outbound = test_mode.drain_outbound(test_phone)
    signals = persist_outbound(session_id, outbound, total_latency_ms=latency_ms)
    increment_turns(session_id)

    return {
        'finished': False,
        'reason': None,
        'client_text': client_text,
        'bot_messages': outbound,
        'signals': signals,
        'latency_ms': latency_ms,
    }


# ── Lecturas para panel de revisión ────────────────────────────────

def list_sessions(
    mode: Optional[str] = None,
    persona: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    if supabase_client is None:
        return []
    try:
        q = supabase_client.table('test_sessions').select('*')
        if mode:
            q = q.eq('mode', mode)
        if persona:
            q = q.eq('persona_slug', persona)
        if tag:
            q = q.eq('tag', tag)
        res = (
            q.order('created_at', desc=True)
             .range(offset, offset + limit - 1)
             .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[test_runner] list_sessions error: {e}")
        return []


def get_session_detail(session_id: str) -> Optional[dict]:
    if supabase_client is None:
        return None
    try:
        sess = (
            supabase_client.table('test_sessions')
            .select('*')
            .eq('id', session_id)
            .single()
            .execute()
        )
        msgs = (
            supabase_client.table('test_messages')
            .select('*')
            .eq('session_id', session_id)
            .order('seq', desc=False)
            .execute()
        )
        anns = (
            supabase_client.table('test_annotations')
            .select('*')
            .eq('session_id', session_id)
            .order('created_at', desc=False)
            .execute()
        )
        return {
            'session': sess.data,
            'messages': msgs.data or [],
            'annotations': anns.data or [],
        }
    except Exception as e:
        print(f"[test_runner] get_session_detail error: {e}")
        return None


def update_session_tag(session_id: str, tag: Optional[str]) -> bool:
    if supabase_client is None:
        return False
    try:
        supabase_client.table('test_sessions').update({
            'tag': tag,
        }).eq('id', session_id).execute()
        return True
    except Exception as e:
        print(f"[test_runner] update_session_tag error: {e}")
        return False


def update_session_notes(session_id: str, notes: Optional[str]) -> bool:
    if supabase_client is None:
        return False
    try:
        supabase_client.table('test_sessions').update({
            'notes': notes,
        }).eq('id', session_id).execute()
        return True
    except Exception as e:
        print(f"[test_runner] update_session_notes error: {e}")
        return False


def add_annotation(
    session_id: str,
    note: str,
    severity: str = 'info',
    message_id: Optional[str] = None,
    author: Optional[str] = None,
) -> Optional[dict]:
    if supabase_client is None or not note:
        return None
    try:
        res = supabase_client.table('test_annotations').insert({
            'session_id': session_id,
            'message_id': message_id,
            'note': note,
            'severity': severity if severity in ('info', 'warn', 'error') else 'info',
            'author': author,
        }).execute()
        return (res.data or [None])[0]
    except Exception as e:
        print(f"[test_runner] add_annotation error: {e}")
        return None

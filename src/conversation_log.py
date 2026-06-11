"""
Conversation Logger for ProAlto WhatsApp Bot.
Provides query methods for the admin dashboard and state management for flows.
Exclusively uses Supabase.
"""
import threading
from datetime import datetime
from config import Config
from supabase import create_client, Client
from src import test_mode

# Initialize Supabase client
supabase_client = None
if Config.SUPABASE_URL and Config.SUPABASE_KEY:
    try:
        supabase_client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    except Exception as e:
        print(f"⚠️ Failed to initialize Supabase client: {e}")
else:
    print("⚠️ SUPABASE_URL or SUPABASE_KEY is missing. Supabase logging will fail.")

def log_message(phone: str, direction: str, text: str, msg_type: str = "text", wamid: str = None):
    """Log a single message to the conversation history in background."""
    if test_mode.is_test_phone(phone):
        test_mode.log_message(phone, direction, text, msg_type)
        return
    now = datetime.now().isoformat()

    # Run DB insert in background to avoid blocking WhatsApp webhook response
    threading.Thread(
        target=_supabase_log_task,
        args=(phone, direction, text, msg_type, now, wamid),
        daemon=True
    ).start()

def _supabase_log_task(phone, direction, text, msg_type, now, wamid=None):
    """Internal synchronous task to sync message to Supabase."""
    # Step 1: update bot_conversations — isolated so a failure here never blocks step 2
    try:
        res = supabase_client.table('bot_conversations').select("status").eq("phone", phone).execute()
        if res.data:
            current_status = res.data[0].get("status")
            if current_status == "archived" and direction == "inbound":
                supabase_client.table('bot_conversations').update({
                    "status": "active",
                    "updated_at": now
                }).eq("phone", phone).execute()
            else:
                supabase_client.table('bot_conversations').update({
                    "updated_at": now
                }).eq("phone", phone).execute()
        else:
            # Use upsert to avoid unique constraint race with set_user_state() in bulk sends
            supabase_client.table('bot_conversations').upsert({
                "phone": phone,
                "status": "pending_consent",
                "updated_at": now
            }, on_conflict="phone").execute()
    except Exception as e:
        print(f"⚠️ Supabase conversation update error: {e}")

    # Step 2: always log the message, regardless of step 1 outcome
    try:
        supabase_client.table('bot_messages').insert({
            "phone": phone,
            "direction": direction,
            "text": text,
            "msg_type": msg_type,
            "created_at": now,
            "wamid": wamid
        }).execute()
    except Exception as e:
        print(f"⚠️ Supabase message insert error: {e}")


def get_user_state(phone: str) -> str:
    """Fetch the current detailed status/state of the user from Supabase."""
    if test_mode.is_test_phone(phone):
        return test_mode.get_state(phone)
    try:
        res = supabase_client.table('bot_conversations').select("status").eq("phone", phone).execute()
        if res.data:
            return res.data[0].get("status", "pending_consent")
        return "pending_consent"
    except Exception as e:
        print(f"Supabase get_user_state error: {e}")
        return "pending_consent"


def set_user_state(phone: str, state: str):
    """Update the detailed status/state of the user in Supabase."""
    if test_mode.is_test_phone(phone):
        test_mode.set_state(phone, state)
        return
    now = datetime.now().isoformat()
    try:
        supabase_client.table('bot_conversations').upsert({
            "phone": phone,
            "status": state,
            "updated_at": now
        }, on_conflict="phone").execute()
    except Exception as e:
        print(f"Supabase set_user_state error: {e}")


def set_client_name(phone: str, name: str):
    """Store the client name in bot_conversations for reliable retrieval."""
    if test_mode.is_test_phone(phone):
        test_mode.set_client_name(phone, name)
        return
    try:
        supabase_client.table('bot_conversations').upsert({
            "phone": phone,
            "client_name": name,
            "updated_at": datetime.now().isoformat()
        }, on_conflict="phone").execute()
    except Exception as e:
        print(f"Supabase set_client_name error: {e}")


def get_client_name(phone: str) -> str:
    """Retrieve the stored client name from bot_conversations."""
    if test_mode.is_test_phone(phone):
        return test_mode.get_client_name(phone)
    try:
        res = supabase_client.table('bot_conversations').select("client_name").eq("phone", phone).execute()
        if res.data:
            return res.data[0].get("client_name") or "Cliente"
        return "Cliente"
    except Exception as e:
        print(f"Supabase get_client_name error: {e}")
        return "Cliente"


def set_agent_mode(phone: str, status: str = "agent"):
    """Set the conversation status precisely (agent, agent_silent, active)."""
    set_user_state(phone, status)


def _get_lead_phones() -> set:
    """Get all phone numbers that ever received the contacto_leads template."""
    try:
        msg_res = supabase_client.table('bot_messages').select("phone").eq("text", "[Template: contacto_leads]").execute()
        phones = {m["phone"] for m in (msg_res.data or [])}
        conv_res = supabase_client.table('bot_conversations').select("phone").eq("status", "lead_notified").execute()
        phones |= {r["phone"] for r in (conv_res.data or [])}
        return phones
    except Exception as e:
        print(f"Supabase _get_lead_phones error: {e}")
        return set()


def _get_renovado_phones() -> set:
    """Get all phone numbers that ever received the estado_renovar template."""
    try:
        msg_res = supabase_client.table('bot_messages').select("phone").eq("text", "[Template: estado_renovar]").execute()
        phones = {m["phone"] for m in (msg_res.data or [])}
        conv_res = supabase_client.table('bot_conversations').select("phone").eq("status", "renovado_notified").execute()
        phones |= {r["phone"] for r in (conv_res.data or [])}
        return phones
    except Exception as e:
        print(f"Supabase _get_renovado_phones error: {e}")
        return set()


def _get_anticipos_phones() -> set:
    """Get all phone numbers that ever received the anticipo_salario template."""
    try:
        msg_res = supabase_client.table('bot_messages').select("phone").eq("text", "[Template: anticipo_salario]").execute()
        phones = {m["phone"] for m in (msg_res.data or [])}
        # Recovery: include phones whose log was lost but state was set correctly
        conv_res = supabase_client.table('bot_conversations').select("phone").eq("status", "anticipos_notified").execute()
        phones |= {r["phone"] for r in (conv_res.data or [])}
        return phones
    except Exception as e:
        print(f"Supabase _get_anticipos_phones error: {e}")
        return set()


def _build_conversation_list(convs_data: list) -> list:
    """Shared helper: given a list of bot_conversations rows, enrich with last message & count."""
    phones = [c["phone"] for c in convs_data]
    last_msgs = {}
    msg_counts = {}

    if phones:
        msgs_res = supabase_client.table('bot_messages').select("phone, text, id").in_("phone", phones).order("created_at", desc=True).limit(1000).execute()
        for m in msgs_res.data:
            p = m["phone"]
            if p not in last_msgs:
                last_msgs[p] = m["text"]
            msg_counts[p] = msg_counts.get(p, 0) + 1

    result = []
    for c in convs_data:
        p = c["phone"]
        last_msg = last_msgs.get(p, "")
        if len(last_msg) > 80:
            last_msg = last_msg[:80] + "…"
        result.append({
            "phone": p,
            "client_name": c.get("client_name") or "",
            "last_message": last_msg,
            "status": c.get("status", "active"),
            "updated_at": c.get("updated_at", ""),
            "message_count": msg_counts.get(p, 1),
        })
    return result


def get_conversations() -> list:
    """Get non-lead/non-renovado/non-anticipos conversations, sorted by most recent."""
    try:
        lead_phones = _get_lead_phones()
        renovado_phones = _get_renovado_phones()
        anticipos_phones = _get_anticipos_phones()
        excluded_phones = lead_phones | renovado_phones | anticipos_phones
        excluded_statuses = {"lead_notified", "renovado_notified", "anticipos_notified"}
        # Over-fetch to compensate for entries we'll exclude
        convs = supabase_client.table('bot_conversations').select("*").neq("status", "archived").order("updated_at", desc=True).limit(100).execute()
        filtered = [
            c for c in convs.data
            if c["phone"] not in excluded_phones and c.get("status") not in excluded_statuses
        ][:50]
        return _build_conversation_list(filtered)
    except Exception as e:
        print(f"Supabase get_conversations error: {e}")
        return []


def get_lead_conversations() -> list:
    """Get conversations that originated from the contacto_leads template."""
    try:
        lead_phones = list(_get_lead_phones())
        if not lead_phones:
            return []
        convs = supabase_client.table('bot_conversations').select("*").in_("phone", lead_phones).neq("status", "archived").order("updated_at", desc=True).execute()
        return _build_conversation_list(convs.data)
    except Exception as e:
        print(f"Supabase get_lead_conversations error: {e}")
        return []


def get_renovado_conversations() -> list:
    """Get conversations that originated from the estado_renovar template."""
    try:
        renovado_phones = list(_get_renovado_phones())
        if not renovado_phones:
            return []
        convs = supabase_client.table('bot_conversations').select("*").in_("phone", renovado_phones).neq("status", "archived").order("updated_at", desc=True).execute()
        return _build_conversation_list(convs.data)
    except Exception as e:
        print(f"Supabase get_renovado_conversations error: {e}")
        return []


def log_anticipo_sent(phone: str, client_name: str):
    """Record that anticipo_salario template was sent to this phone."""
    if test_mode.is_test_phone(phone):
        return
    if not supabase_client:
        return
    try:
        supabase_client.table('anticipo_responses').upsert({
            "phone": phone,
            "client_name": client_name,
            "template_sent_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }, on_conflict="phone").execute()
    except Exception as e:
        print(f"Supabase log_anticipo_sent error: {e}")


def log_anticipo_response(phone: str, response: str):
    """Update the button click response for a phone: 'solicitar' or 'no_gracias'."""
    if test_mode.is_test_phone(phone):
        return
    if not supabase_client:
        return
    try:
        supabase_client.table('anticipo_responses').upsert({
            "phone": phone,
            "response": response,
            "responded_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }, on_conflict="phone").execute()
    except Exception as e:
        print(f"Supabase log_anticipo_response error: {e}")


def get_anticipo_metrics() -> dict:
    """
    Build anticipo_salario campaign metrics (fully retrospective).
    Merges click data from bot_messages and anticipo_responses since each source
    drops entries: bot_messages logging runs in a daemon thread and can be lost
    under load; anticipo_responses skips the 'no_gracias' write when the user's
    state is no longer 'anticipos_notified'. Latest-response-wins per phone.
    Phones that replied only by free text are reported separately.
    """
    if not supabase_client:
        return {}
    try:
        sent_res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .eq("text", "[Template: anticipo_salario]")\
            .eq("direction", "outbound")\
            .order("created_at", desc=False)\
            .execute()

        phone_sent_at = {}
        for row in (sent_res.data or []):
            if row["phone"] not in phone_sent_at:
                phone_sent_at[row["phone"]] = row["created_at"]

        # Recovery: include phones where set_user_state("anticipos_notified") ran
        # but bot_messages log was lost due to the race-condition bug.
        conv_res = supabase_client.table('bot_conversations')\
            .select("phone, updated_at")\
            .eq("status", "anticipos_notified")\
            .execute()
        for row in (conv_res.data or []):
            if row["phone"] not in phone_sent_at:
                phone_sent_at[row["phone"]] = row["updated_at"]

        if not phone_sent_at:
            return {"total": 0, "solicitar": [], "solicitar_count": 0,
                    "no_gracias_count": 0, "respondieron_chat_count": 0,
                    "sin_respuesta_count": 0}

        all_phones = list(phone_sent_at.keys())
        total = len(all_phones)

        # Source A: button clicks logged in bot_messages (latest first)
        btn_res = supabase_client.table('bot_messages')\
            .select("phone, text, created_at")\
            .in_("phone", all_phones)\
            .eq("direction", "inbound")\
            .eq("msg_type", "button")\
            .in_("text", ["Solicitar Anticipo", "Ahora no, gracias"])\
            .order("created_at", desc=True)\
            .execute()

        # phone -> (kind, responded_at) — latest wins across both sources
        responses: dict = {}
        for row in (btn_res.data or []):
            if row["phone"] in responses:
                continue
            kind = "solicitar" if row["text"] == "Solicitar Anticipo" else "no_gracias"
            responses[row["phone"]] = (kind, row["created_at"])

        # Source B: anticipo_responses (synchronous insert, more reliable for solicitar)
        form_submitted_map = {}
        try:
            ar_res = supabase_client.table('anticipo_responses')\
                .select("phone, response, responded_at, form_submitted")\
                .in_("phone", all_phones)\
                .execute()
            for row in (ar_res.data or []):
                phone = row["phone"]
                resp = row.get("response")
                if resp not in ("solicitar", "no_gracias"):
                    continue
                ts = row.get("responded_at") or ""
                existing = responses.get(phone)
                if not existing or (ts and ts > (existing[1] or "")):
                    responses[phone] = (resp, ts)
            form_submitted_map = {r["phone"]: bool(r.get("form_submitted")) for r in (ar_res.data or [])}
        except Exception:
            pass

        # Source C: free-text responses (typed instead of clicking).
        # Scope per-phone to text sent AFTER the template went out, so prior
        # unrelated conversations aren't attributed to this campaign. (Button
        # sources A/B don't need this: their text is specific to this template.)
        text_res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .in_("phone", all_phones)\
            .eq("direction", "inbound")\
            .eq("msg_type", "text")\
            .execute()
        phones_with_text = set()
        for row in (text_res.data or []):
            phone = row["phone"]
            sent_at = phone_sent_at.get(phone)
            if sent_at and (row.get("created_at") or "") >= sent_at:
                phones_with_text.add(phone)

        name_res = supabase_client.table('bot_conversations')\
            .select("phone, client_name")\
            .in_("phone", all_phones)\
            .execute()
        names = {r["phone"]: r.get("client_name") or "" for r in (name_res.data or [])}

        solicitar = []
        no_gracias_count = 0
        respondieron_chat_count = 0
        sin_respuesta_count = 0

        for phone in all_phones:
            resp = responses.get(phone)
            if resp and resp[0] == "solicitar":
                solicitar.append({
                    "phone": phone,
                    "client_name": names.get(phone, ""),
                    "responded_at": resp[1],
                    "form_submitted": form_submitted_map.get(phone, False),
                })
            elif resp and resp[0] == "no_gracias":
                no_gracias_count += 1
            elif phone in phones_with_text:
                respondieron_chat_count += 1
            else:
                sin_respuesta_count += 1

        solicitar.sort(key=lambda x: x["responded_at"] or "", reverse=True)
        return {
            "total": total,
            "solicitar": solicitar,
            "solicitar_count": len(solicitar),
            "no_gracias_count": no_gracias_count,
            "respondieron_chat_count": respondieron_chat_count,
            "sin_respuesta_count": sin_respuesta_count,
        }
    except Exception as e:
        print(f"Supabase get_anticipo_metrics error: {e}")
        return {}


def toggle_anticipo_form_submitted(phone: str) -> dict:
    """Toggle form_submitted status for a phone in anticipo_responses (upserts if not present)."""
    if not supabase_client:
        return {"success": False}
    try:
        res = supabase_client.table('anticipo_responses').select("form_submitted").eq("phone", phone).execute()
        current_val = bool(res.data[0].get("form_submitted", False)) if res.data else False
        new_val = not current_val
        supabase_client.table('anticipo_responses').upsert({
            "phone": phone,
            "form_submitted": new_val,
            "updated_at": datetime.now().isoformat()
        }, on_conflict="phone").execute()
        return {"success": True, "form_submitted": new_val}
    except Exception as e:
        print(f"Supabase toggle_anticipo_form_submitted error: {e}")
        return {"success": False}


def get_anticipo_no_gracias_phones(phones: list) -> set:
    """Return subset of phones that clicked 'Ahora no, gracias' specifically after the anticipo_salario template."""
    if not supabase_client or not phones:
        return set()
    try:
        # Get when anticipo template was sent to each phone
        sent_res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .in_("phone", phones)\
            .eq("text", "[Template: anticipo_salario]")\
            .eq("direction", "outbound")\
            .execute()

        sent_at_map = {}
        for r in (sent_res.data or []):
            p = r["phone"]
            if p not in sent_at_map or r["created_at"] > sent_at_map[p]:
                sent_at_map[p] = r["created_at"]

        if not sent_at_map:
            return set()

        # Get "Ahora no, gracias" button clicks for those phones
        btn_res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .in_("phone", list(sent_at_map.keys()))\
            .eq("direction", "inbound")\
            .eq("msg_type", "button")\
            .eq("text", "Ahora no, gracias")\
            .execute()

        # Only count clicks that happened after the anticipo template was sent
        excluded = set()
        for r in (btn_res.data or []):
            p = r["phone"]
            if p in sent_at_map and r["created_at"] >= sent_at_map[p]:
                excluded.add(p)
        return excluded
    except Exception as e:
        print(f"Supabase get_anticipo_no_gracias_phones error: {e}")
        return set()


def get_lead_metrics() -> dict:
    """
    Build leads campaign metrics from bot_messages (fully retrospective).
    msg_type='button' = template button click (vs 'interactive' = menu click).
    """
    if not supabase_client:
        return {}
    try:
        sent_res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .eq("text", "[Template: contacto_leads]")\
            .eq("direction", "outbound")\
            .order("created_at", desc=False)\
            .execute()

        phone_sent_at = {}
        for row in (sent_res.data or []):
            if row["phone"] not in phone_sent_at:
                phone_sent_at[row["phone"]] = row["created_at"]

        # Recovery: phones whose bot_messages log was lost but state was set correctly
        conv_res = supabase_client.table('bot_conversations')\
            .select("phone, updated_at")\
            .eq("status", "lead_notified")\
            .execute()
        for row in (conv_res.data or []):
            if row["phone"] not in phone_sent_at:
                phone_sent_at[row["phone"]] = row["updated_at"]

        if not phone_sent_at:
            return {"total": 0, "solicitar": [], "solicitar_count": 0,
                    "hablar_asesor_count": 0, "ahora_no_count": 0, "sin_respuesta_count": 0}

        all_phones = list(phone_sent_at.keys())
        total = len(all_phones)

        btn_res = supabase_client.table('bot_messages')\
            .select("phone, text, created_at")\
            .in_("phone", all_phones)\
            .eq("direction", "inbound")\
            .eq("msg_type", "button")\
            .in_("text", ["Solicitar crédito", "Hablar con un asesor", "Ahora no, gracias"])\
            .order("created_at", desc=False)\
            .execute()

        phone_responses = {}
        for row in btn_res.data:
            if row["phone"] not in phone_responses:
                phone_responses[row["phone"]] = {"response": row["text"], "responded_at": row["created_at"]}

        name_res = supabase_client.table('bot_conversations')\
            .select("phone, client_name")\
            .in_("phone", all_phones)\
            .execute()
        names = {r["phone"]: r.get("client_name") or "" for r in name_res.data}

        solicitar = []
        hablar_asesor_count = 0
        ahora_no_count = 0
        sin_respuesta_count = 0

        for phone in all_phones:
            resp = phone_responses.get(phone)
            if resp and resp["response"] == "Solicitar crédito":
                solicitar.append({"phone": phone, "client_name": names.get(phone, ""),
                                  "responded_at": resp["responded_at"]})
            elif resp and resp["response"] == "Hablar con un asesor":
                hablar_asesor_count += 1
            elif resp and resp["response"] == "Ahora no, gracias":
                ahora_no_count += 1
            else:
                sin_respuesta_count += 1

        solicitar.sort(key=lambda x: x["responded_at"] or "", reverse=True)
        return {"total": total, "solicitar": solicitar, "solicitar_count": len(solicitar),
                "hablar_asesor_count": hablar_asesor_count, "ahora_no_count": ahora_no_count,
                "sin_respuesta_count": sin_respuesta_count}
    except Exception as e:
        print(f"Supabase get_lead_metrics error: {e}")
        return {}


def get_renovado_metrics() -> dict:
    """
    Build renovados campaign metrics from bot_messages (fully retrospective).
    msg_type='button' = template button click (vs 'interactive' = menu click).
    """
    if not supabase_client:
        return {}
    try:
        sent_res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .eq("text", "[Template: estado_renovar]")\
            .eq("direction", "outbound")\
            .order("created_at", desc=False)\
            .execute()

        phone_sent_at = {}
        for row in (sent_res.data or []):
            if row["phone"] not in phone_sent_at:
                phone_sent_at[row["phone"]] = row["created_at"]

        # Recovery: phones whose bot_messages log was lost but state was set correctly
        conv_res = supabase_client.table('bot_conversations')\
            .select("phone, updated_at")\
            .eq("status", "renovado_notified")\
            .execute()
        for row in (conv_res.data or []):
            if row["phone"] not in phone_sent_at:
                phone_sent_at[row["phone"]] = row["updated_at"]

        if not phone_sent_at:
            return {"total": 0, "solicitar": [], "solicitar_count": 0,
                    "no_quiero_count": 0, "mas_info_count": 0, "sin_respuesta_count": 0}

        all_phones = list(phone_sent_at.keys())
        total = len(all_phones)

        btn_res = supabase_client.table('bot_messages')\
            .select("phone, text, created_at")\
            .in_("phone", all_phones)\
            .eq("direction", "inbound")\
            .eq("msg_type", "button")\
            .in_("text", ["Solicitar crédito", "No lo quiero", "Necesito más información"])\
            .order("created_at", desc=False)\
            .execute()

        phone_responses = {}
        for row in btn_res.data:
            if row["phone"] not in phone_responses:
                phone_responses[row["phone"]] = {"response": row["text"], "responded_at": row["created_at"]}

        name_res = supabase_client.table('bot_conversations')\
            .select("phone, client_name")\
            .in_("phone", all_phones)\
            .execute()
        names = {r["phone"]: r.get("client_name") or "" for r in name_res.data}

        solicitar = []
        no_quiero_count = 0
        mas_info_count = 0
        sin_respuesta_count = 0

        for phone in all_phones:
            resp = phone_responses.get(phone)
            if resp and resp["response"] == "Solicitar crédito":
                solicitar.append({"phone": phone, "client_name": names.get(phone, ""),
                                  "responded_at": resp["responded_at"]})
            elif resp and resp["response"] == "No lo quiero":
                no_quiero_count += 1
            elif resp and resp["response"] == "Necesito más información":
                mas_info_count += 1
            else:
                sin_respuesta_count += 1

        solicitar.sort(key=lambda x: x["responded_at"] or "", reverse=True)
        return {"total": total, "solicitar": solicitar, "solicitar_count": len(solicitar),
                "no_quiero_count": no_quiero_count, "mas_info_count": mas_info_count,
                "sin_respuesta_count": sin_respuesta_count}
    except Exception as e:
        print(f"Supabase get_renovado_metrics error: {e}")
        return {}


def get_anticipos_conversations() -> list:
    """Get conversations that originated from the anticipo_nomina template."""
    try:
        anticipos_phones = list(_get_anticipos_phones())
        if not anticipos_phones:
            return []
        convs = supabase_client.table('bot_conversations').select("*").in_("phone", anticipos_phones).neq("status", "archived").order("updated_at", desc=True).execute()
        return _build_conversation_list(convs.data)
    except Exception as e:
        print(f"Supabase get_anticipos_conversations error: {e}")
        return []


def get_conversation(phone: str) -> dict | None:
    """Get the full conversation history for a specific phone number."""
    try:
        c_res = supabase_client.table('bot_conversations').select("*").eq("phone", phone).execute()
        if not c_res.data:
            return None
            
        m_res = supabase_client.table('bot_messages').select("*").eq("phone", phone).order("created_at").execute()
        
        messages = []
        for m in m_res.data:
            messages.append({
                "id": m.get("id"),
                "direction": m["direction"],
                "text": m["text"],
                "type": m["msg_type"],
                "timestamp": m["created_at"],
                "wamid": m.get("wamid")
            })
            
        return {
            "status": c_res.data[0].get("status", "active"),
            "updated_at": c_res.data[0].get("updated_at", ""),
            "messages": messages
        }
    except Exception as e:
        print(f"Supabase get_conversation error: {e}")
        return None


def get_agent_conversations() -> list:
    """Get only conversations currently in agent mode."""
    return [c for c in get_conversations() if c["status"] in ["agent", "agent_silent"]]


def delete_conversation(phone: str, permanent: bool = False):
    """Delete or hide a conversation from the dashboard."""
    try:
        if permanent:
            supabase_client.table('bot_conversations').delete().eq("phone", phone).execute()
        else:
            supabase_client.table('bot_conversations').update({"status": "archived"}).eq("phone", phone).execute()
    except Exception as e:
        print(f"Supabase delete_conversation error: {e}")


def get_archived_conversations() -> list:
    """Get a list of archived (hidden) conversations."""
    try:
        convs = supabase_client.table('bot_conversations').select("*").eq("status", "archived").order("updated_at", desc=True).execute()
        result = []
        for c in convs.data:
            msgs_res = supabase_client.table('bot_messages').select("*").eq("phone", c["phone"]).order("created_at", desc=True).limit(1).execute()
            last_msg = msgs_res.data[0]["text"] if msgs_res.data else ""
            if len(last_msg) > 80:
                last_msg = last_msg[:80] + "…"
            count_res = supabase_client.table('bot_messages').select("id", count="exact").eq("phone", c["phone"]).execute()
            result.append({
                "phone": c["phone"],
                "last_message": last_msg,
                "status": "archived",
                "updated_at": c.get("updated_at", ""),
                "message_count": count_res.count if count_res.count else 0,
            })
        return result
    except Exception as e:
        print(f"Supabase get_archived error: {e}")
        return []

def restore_conversation(phone: str):
    """Restore an archived conversation back to active view."""
    now = datetime.now().isoformat()
    try:
        supabase_client.table('bot_conversations').update({
            "status": "active",
            "updated_at": now
        }).eq("phone", phone).execute()
    except Exception as e:
        print(f"Supabase restore error: {e}")

def has_sent_aprobado_msg_today(phone: str) -> bool:
    """Check if an approved proactive message was already sent today to this phone."""
    if not supabase_client:
        return False
    
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        res = supabase_client.table('bot_messages')\
            .select("id")\
            .eq("phone", phone)\
            .eq("direction", "outbound")\
            .gte("created_at", f"{today}T00:00:00")\
            .or_("text.ilike.%correo electrónico%,text.ilike.%estado_verde%,text.ilike.%Notificación Masiva%")\
            .limit(1)\
            .execute()
        return len(res.data) > 0
    except Exception as e:
        print(f"Supabase has_sent_aprobado_msg_today error: {e}")
        return False

def get_template_stats_batch(phones: list) -> dict:
    """
    Returns a dict mapping phone -> {count, last_sent} for estado_verde template sends.
    """
    if not supabase_client or not phones:
        return {}
    try:
        res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .eq("text", "[Template: estado_verde]")\
            .order("created_at", desc=True)\
            .execute()
        stats = {}
        for item in res.data:
            p = item["phone"]
            if p not in stats:
                stats[p] = {"count": 0, "last_sent": None}
            stats[p]["count"] += 1
            if stats[p]["last_sent"] is None:
                stats[p]["last_sent"] = item["created_at"]
        return stats
    except Exception as e:
        print(f"Supabase get_template_stats_batch error: {e}")
        return {}


def get_notified_phones_batch(phones: list) -> set:
    """
    Given a list of phone numbers, returns a SET of those that 
    HAVE already been notified today. (Optimized single query).
    """
    if not supabase_client or not phones:
        return set()
    
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        res = supabase_client.table('bot_messages')\
            .select("phone")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .gte("created_at", f"{today}T00:00:00")\
            .or_("text.ilike.%correo electrónico%,text.ilike.%estado_verde%,text.ilike.%Notificación Masiva%")\
            .execute()
        
        return {item["phone"] for item in res.data}
    except Exception as e:
        print(f"Supabase get_notified_phones_batch error: {e}")
        return set()

def mark_message_deleted(message_id: str):
    """Mark a message as deleted in the local database."""
    try:
        supabase_client.table('bot_messages').update({
            "text": "🚫 _Mensaje eliminado por el asesor_",
            "msg_type": "deleted"
        }).eq("id", message_id).execute()
    except Exception as e:
        print(f"Supabase mark_message_deleted error: {e}")

def save_captured_email(phone: str, email: str, name: str):
    """Saves a captured email to the captured_emails table."""
    if test_mode.is_test_phone(phone):
        test_mode.record_captured_email(phone, email)
        return True
    if not supabase_client:
        print("⚠️ Supabase client not initialized. Cannot save email.")
        return False

    try:
        data = {
            "phone": phone,
            "email": email,
            "name": name,
            "created_at": datetime.now().isoformat()
        }
        supabase_client.table('captured_emails').insert(data).execute()
        return True
    except Exception as e:
        print(f"❌ Error saving captured email: {e}")
        return False

def get_captured_emails():
    """Retrieves all captured emails ordered by date."""
    if not supabase_client:
        return []

    try:
        res = supabase_client.table('captured_emails').select("*").order("created_at", desc=True).execute()
        return res.data
    except Exception as e:
        print(f"❌ Error fetching captured emails: {e}")
        return []


def update_captured_email(phone: str, new_email: str) -> bool:
    """Updates the most recent captured email for a phone."""
    if not supabase_client:
        return False
    try:
        res = supabase_client.table('captured_emails')\
            .select("id")\
            .eq("phone", phone)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        if not res.data:
            return False
        record_id = res.data[0]["id"]
        supabase_client.table('captured_emails')\
            .update({"email": new_email})\
            .eq("id", record_id)\
            .execute()
        return True
    except Exception as e:
        print(f"❌ Error updating captured email: {e}")
        return False


def toggle_email_processed(phone: str) -> dict:
    """Toggles the processed (sent) status of the most recent captured email for a phone."""
    if not supabase_client:
        return {"success": False, "processed": False}
    try:
        res = supabase_client.table('captured_emails')\
            .select("id, processed")\
            .eq("phone", phone)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        if not res.data:
            return {"success": False, "processed": False}
        record = res.data[0]
        record_id = record["id"]
        new_state = not bool(record.get("processed", False))
        supabase_client.table('captured_emails')\
            .update({"processed": new_state})\
            .eq("id", record_id)\
            .execute()
        return {"success": True, "processed": new_state}
    except Exception as e:
        print(f"❌ Error toggling email processed: {e}")
        return {"success": False, "processed": False}


def toggle_email_processed_by_id(record_id: int) -> dict:
    """Toggles the processed (sent) status of a captured email by its record ID."""
    if not supabase_client:
        return {"success": False, "processed": False}
    try:
        res = supabase_client.table('captured_emails')\
            .select("id, processed")\
            .eq("id", record_id)\
            .execute()
        if not res.data:
            return {"success": False, "processed": False}
        record = res.data[0]
        new_state = not bool(record.get("processed", False))
        supabase_client.table('captured_emails')\
            .update({"processed": new_state})\
            .eq("id", record_id)\
            .execute()
        return {"success": True, "processed": new_state}
    except Exception as e:
        print(f"❌ Error toggling email processed by id: {e}")
        return {"success": False, "processed": False}


def get_phones_with_email(phones: list) -> set:
    """Returns a set of phones that have already submitted their email."""
    if not supabase_client or not phones:
        return set()
    try:
        res = supabase_client.table('captured_emails')\
            .select("phone")\
            .in_("phone", phones)\
            .execute()
        return {item["phone"] for item in res.data}
    except Exception as e:
        print(f"Supabase get_phones_with_email error: {e}")
        return set()


def get_email_for_phone(phone: str):
    """Returns the most recent captured email for a phone, or None."""
    if test_mode.is_test_phone(phone):
        return test_mode.get_captured_email(phone)
    if not supabase_client:
        return None
    try:
        res = supabase_client.table('captured_emails')\
            .select("email")\
            .eq("phone", phone)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        return res.data[0]["email"] if res.data else None
    except Exception as e:
        print(f"Supabase get_email_for_phone error: {e}")
        return None


def get_phones_with_docs_completos(phones: list) -> set:
    """Returns a set of phones marked as docs_completos = true."""
    if not supabase_client or not phones:
        return set()
    try:
        res = supabase_client.table('bot_conversations')\
            .select("phone")\
            .in_("phone", phones)\
            .eq("docs_completos", True)\
            .execute()
        return {item["phone"] for item in res.data}
    except Exception as e:
        print(f"Supabase get_phones_with_docs_completos error: {e}")
        return set()


def mark_docs_completos(phone: str, value: bool = True):
    """Marks or unmarks a client as having submitted all required documents."""
    if test_mode.is_test_phone(phone):
        test_mode.mark_docs_completos(phone, value)
        return
    if not supabase_client:
        return
    try:
        supabase_client.table('bot_conversations').upsert({
            "phone": phone,
            "docs_completos": value,
            "updated_at": datetime.now().isoformat()
        }, on_conflict="phone").execute()
    except Exception as e:
        print(f"Supabase mark_docs_completos error: {e}")


def set_solicitud_context(phone: str, empresa: str, docs_faltantes: str, tipo_empleador: str):
    """Store solicitud context (empresa, docs_faltantes, tipo_empleador) per phone for use in flows."""
    if test_mode.is_test_phone(phone):
        test_mode.set_solicitud_context(phone, empresa, docs_faltantes, tipo_empleador)
        return
    if not supabase_client:
        return
    try:
        supabase_client.table('bot_conversations').upsert({
            "phone": phone,
            "empresa": empresa or "",
            "docs_faltantes": docs_faltantes or "",
            "tipo_empleador": tipo_empleador or "EMPRESA",
            "updated_at": datetime.now().isoformat()
        }, on_conflict="phone").execute()
    except Exception as e:
        print(f"Supabase set_solicitud_context error: {e}")


def get_solicitud_context(phone: str) -> dict:
    """Retrieve stored docs_faltantes and tipo_empleador for a phone."""
    if test_mode.is_test_phone(phone):
        ctx = test_mode.get_solicitud_context(phone)
        return {
            "docs_faltantes": ctx.get("docs_faltantes", ""),
            "tipo_empleador": ctx.get("tipo_empleador", "EMPRESA"),
        }
    if not supabase_client:
        return {}
    try:
        res = supabase_client.table('bot_conversations')\
            .select("docs_faltantes, tipo_empleador")\
            .eq("phone", phone)\
            .execute()
        if res.data:
            return {
                "docs_faltantes": res.data[0].get("docs_faltantes") or "",
                "tipo_empleador": res.data[0].get("tipo_empleador") or "EMPRESA",
            }
    except Exception as e:
        print(f"Supabase get_solicitud_context error: {e}")
    return {}


def get_template_stats_batch_rojo(phones: list) -> dict:
    """
    Returns a dict mapping phone -> {count, last_sent} for estado_rojo template sends.
    """
    if not supabase_client or not phones:
        return {}
    try:
        res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .eq("text", "[Template: estado_rojo]")\
            .order("created_at", desc=True)\
            .execute()
        stats = {}
        for item in res.data:
            p = item["phone"]
            if p not in stats:
                stats[p] = {"count": 0, "last_sent": None}
            stats[p]["count"] += 1
            if stats[p]["last_sent"] is None:
                stats[p]["last_sent"] = item["created_at"]
        return stats
    except Exception as e:
        print(f"Supabase get_template_stats_batch_rojo error: {e}")
        return {}


def get_notified_phones_rojo_batch(phones: list) -> set:
    """
    Given a list of phone numbers, returns a SET of those that
    HAVE already received estado_rojo today.
    """
    if not supabase_client or not phones:
        return set()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        res = supabase_client.table('bot_messages')\
            .select("phone")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .gte("created_at", f"{today}T00:00:00")\
            .eq("text", "[Template: estado_rojo]")\
            .execute()
        return {item["phone"] for item in res.data}
    except Exception as e:
        print(f"Supabase get_notified_phones_rojo_batch error: {e}")
        return set()


def get_phones_menu_contacted_rojo_batch(phones: list) -> set:
    """
    Returns a SET of phones that were contacted today via the bot menu
    (consulta de estado → Falta algún documento), not via bulk template.
    """
    if not supabase_client or not phones:
        return set()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        res = supabase_client.table('bot_messages')\
            .select("phone")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .gte("created_at", f"{today}T00:00:00")\
            .eq("text", "[Menu: estado_rojo]")\
            .execute()
        return {item["phone"] for item in res.data}
    except Exception as e:
        print(f"Supabase get_phones_menu_contacted_rojo_batch error: {e}")
        return set()


def count_received_documents(phone: str) -> int:
    """Returns how many documents have already been received from this phone."""
    if test_mode.is_test_phone(phone):
        return test_mode.count_received_documents(phone)
    if not supabase_client:
        return 0
    try:
        result = supabase_client.table('received_documents').select("id", count="exact").eq("phone", phone).execute()
        return result.count or 0
    except Exception as e:
        print(f"Supabase count_received_documents error: {e}")
        return 0


def log_received_document(phone: str, client_name: str, filename: str, mime_type: str, storage_url: str):
    """Logs a received document to the received_documents table."""
    if test_mode.is_test_phone(phone):
        test_mode.record_received_document(phone)
        return
    if not supabase_client:
        return
    try:
        supabase_client.table('received_documents').insert({
            "phone": phone,
            "client_name": client_name,
            "filename": filename,
            "mime_type": mime_type,
            "storage_url": storage_url,
            "triggered_by": "estado_rojo",
            "reviewed": False
        }).execute()
    except Exception as e:
        print(f"Supabase log_received_document error: {e}")


def _enrich_empresa_background(phones: list):
    """Background task: looks up empresa via Cloud Run for phones that don't have it yet and saves it."""
    from src.database import get_client_context_by_phone
    for phone in phones:
        try:
            ctx = get_client_context_by_phone(phone)
            if ctx and ctx.get("empresa"):
                supabase_client.table('bot_conversations').upsert({
                    "phone": phone,
                    "empresa": ctx["empresa"],
                    "updated_at": datetime.now().isoformat()
                }, on_conflict="phone").execute()
        except Exception as e:
            print(f"[enrich_empresa] error for {phone}: {e}")


def get_received_documents() -> list:
    """Retrieves all received documents ordered by most recent first, with docs_completos and empresa from bot_conversations."""
    if not supabase_client:
        return []
    try:
        res = supabase_client.table('received_documents')\
            .select("*")\
            .order("received_at", desc=True)\
            .execute()
        docs = res.data
        if not docs:
            return docs

        # Merge docs_completos and empresa from bot_conversations for all unique phones
        phones = list({d["phone"] for d in docs if d.get("phone")})
        conv_res = supabase_client.table('bot_conversations')\
            .select("phone, docs_completos, empresa")\
            .in_("phone", phones)\
            .execute()
        conv_map = {r["phone"]: r for r in conv_res.data}

        phones_without_empresa = [p for p in phones if not (conv_map.get(p) or {}).get("empresa")]
        if phones_without_empresa:
            threading.Thread(
                target=_enrich_empresa_background,
                args=(phones_without_empresa,),
                daemon=True
            ).start()

        for doc in docs:
            conv = conv_map.get(doc.get("phone"), {})
            doc["docs_completos"] = conv.get("docs_completos", False)
            doc["empresa"] = conv.get("empresa") or ""

        return docs
    except Exception as e:
        print(f"Supabase get_received_documents error: {e}")
        return []


def get_template_stats_batch_amarillo(phones: list) -> dict:
    """
    Returns a dict mapping phone -> {count, last_sent} for estado_amarillo template sends.
    """
    if not supabase_client or not phones:
        return {}
    try:
        res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .eq("text", "[Template: estado_amarillo]")\
            .order("created_at", desc=True)\
            .execute()
        stats = {}
        for item in res.data:
            p = item["phone"]
            if p not in stats:
                stats[p] = {"count": 0, "last_sent": None}
            stats[p]["count"] += 1
            if stats[p]["last_sent"] is None:
                stats[p]["last_sent"] = item["created_at"]
        return stats
    except Exception as e:
        print(f"Supabase get_template_stats_batch_amarillo error: {e}")
        return {}


def get_notified_phones_amarillo_batch(phones: list) -> set:
    """
    Given a list of phone numbers, returns a SET of those that
    HAVE already received estado_amarillo today.
    """
    if not supabase_client or not phones:
        return set()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        res = supabase_client.table('bot_messages')\
            .select("phone")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .gte("created_at", f"{today}T00:00:00")\
            .eq("text", "[Template: estado_amarillo]")\
            .execute()
        return {item["phone"] for item in res.data}
    except Exception as e:
        print(f"Supabase get_notified_phones_amarillo_batch error: {e}")
        return set()


def get_template_stats_batch_denegado(phones: list) -> dict:
    """
    Returns a dict mapping phone -> {count, last_sent} for estado_negados template sends.
    """
    if not supabase_client or not phones:
        return {}
    try:
        res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .eq("text", "[Template: estado_negados]")\
            .order("created_at", desc=True)\
            .execute()
        stats = {}
        for item in res.data:
            p = item["phone"]
            if p not in stats:
                stats[p] = {"count": 0, "last_sent": None}
            stats[p]["count"] += 1
            if stats[p]["last_sent"] is None:
                stats[p]["last_sent"] = item["created_at"]
        return stats
    except Exception as e:
        print(f"Supabase get_template_stats_batch_denegado error: {e}")
        return {}


def get_notified_phones_denegado_batch(phones: list) -> set:
    """
    Given a list of phone numbers, returns a SET of those that have EVER
    received the estado_negados template (no date filter — this is a final decision).
    """
    if not supabase_client or not phones:
        return set()
    try:
        res = supabase_client.table('bot_messages')\
            .select("phone")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .eq("text", "[Template: estado_negados]")\
            .execute()
        return {item["phone"] for item in res.data}
    except Exception as e:
        print(f"Supabase get_notified_phones_denegado_batch error: {e}")
        return set()


def save_captured_cuenta(phone: str, numero_cuenta: str, name: str):
    """Saves a captured account number (cuenta propia) to captured_cuentas. banco is NULL until step 2."""
    if test_mode.is_test_phone(phone):
        test_mode.record_captured_cuenta(phone)
        return True
    if not supabase_client:
        print("⚠️ Supabase client not initialized. Cannot save cuenta.")
        return False
    try:
        supabase_client.table('captured_cuentas').insert({
            "phone": phone,
            "numero_cuenta": numero_cuenta,
            "name": name,
            "es_tercero": False,
            "created_at": datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        print(f"❌ Error saving captured cuenta: {e}")
        return False


def save_partial_tercero_cuenta(phone: str, name: str, nombre_tercero: str, cedula_url: str) -> bool:
    """Creates a partial captured_cuentas row for a tercero account.
    numero_cuenta and banco are NULL and will be filled in subsequent steps."""
    if test_mode.is_test_phone(phone):
        test_mode.record_captured_cuenta(phone)
        return True
    if not supabase_client:
        print("⚠️ Supabase client not initialized. Cannot save tercero cuenta.")
        return False
    try:
        supabase_client.table('captured_cuentas').insert({
            "phone": phone,
            "name": name,
            "es_tercero": True,
            "nombre_tercero": nombre_tercero,
            "cedula_tercero_url": cedula_url,
            "created_at": datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        print(f"❌ Error saving partial tercero cuenta: {e}")
        return False


def update_tercero_cuenta_numero(phone: str, numero_cuenta: str) -> bool:
    """Updates the most recent tercero captured_cuentas row for phone with the account number."""
    if test_mode.is_test_phone(phone):
        return True
    if not supabase_client:
        print("⚠️ Supabase client not initialized. Cannot update tercero numero.")
        return False
    try:
        res = supabase_client.table('captured_cuentas')\
            .select("id")\
            .eq("phone", phone)\
            .eq("es_tercero", True)\
            .is_("numero_cuenta", "null")\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        if res.data:
            row_id = res.data[0]["id"]
            supabase_client.table('captured_cuentas')\
                .update({"numero_cuenta": numero_cuenta})\
                .eq("id", row_id)\
                .execute()
        return True
    except Exception as e:
        print(f"❌ Error updating tercero numero: {e}")
        return False


def update_captured_cuenta_banco(phone: str, banco: str):
    """Updates the most recent captured_cuentas row for phone with the banco name (step 2)."""
    if test_mode.is_test_phone(phone):
        return True
    if not supabase_client:
        print("⚠️ Supabase client not initialized. Cannot update banco.")
        return False
    try:
        # Find the latest row for this phone that has no banco yet
        res = supabase_client.table('captured_cuentas')\
            .select("id")\
            .eq("phone", phone)\
            .is_("banco", "null")\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        if res.data:
            row_id = res.data[0]["id"]
            supabase_client.table('captured_cuentas')\
                .update({"banco": banco})\
                .eq("id", row_id)\
                .execute()
        return True
    except Exception as e:
        print(f"❌ Error updating banco: {e}")
        return False


def get_captured_cuentas():
    """Retrieves all captured account numbers ordered by date, enriched with empresa from bot_conversations."""
    if not supabase_client:
        return []
    try:
        res = supabase_client.table('captured_cuentas').select("*").order("created_at", desc=True).execute()
        cuentas = res.data or []
        if cuentas:
            phones = list({c["phone"] for c in cuentas})
            ctx_res = supabase_client.table('bot_conversations').select("phone, empresa").in_("phone", phones).execute()
            empresa_map = {row["phone"]: row.get("empresa", "") for row in (ctx_res.data or [])}
            for c in cuentas:
                c["empresa"] = empresa_map.get(c["phone"], "")
        return cuentas
    except Exception as e:
        print(f"❌ Error fetching captured cuentas: {e}")
        return []


def get_phones_with_cuenta(phones: list) -> set:
    """Returns a set of phones that have already submitted their account number."""
    if not supabase_client or not phones:
        return set()
    try:
        res = supabase_client.table('captured_cuentas')\
            .select("phone")\
            .in_("phone", phones)\
            .execute()
        return {item["phone"] for item in res.data}
    except Exception as e:
        print(f"Supabase get_phones_with_cuenta error: {e}")
        return set()


def mark_document_reviewed(doc_id: str):
    """Marks a received document as reviewed."""
    if not supabase_client:
        return
    try:
        supabase_client.table('received_documents')\
            .update({"reviewed": True})\
            .eq("id", doc_id)\
            .execute()
    except Exception as e:
        print(f"Supabase mark_document_reviewed error: {e}")


def mark_all_docs_reviewed(phone: str):
    """Marks all received documents for a phone as reviewed."""
    if not supabase_client:
        return
    try:
        supabase_client.table('received_documents')\
            .update({"reviewed": True})\
            .eq("phone", phone)\
            .execute()
    except Exception as e:
        print(f"Supabase mark_all_docs_reviewed error: {e}")


def save_llm_request(phone: str, client_name: str, tipo: str, detalle: str = ""):
    """Saves a special request captured by the LLM agent to llm_requests table."""
    if test_mode.is_test_phone(phone):
        test_mode.record_llm_request(phone, tipo, detalle)
        return
    if not supabase_client:
        return
    try:
        supabase_client.table('llm_requests').insert({
            "phone": phone,
            "client_name": client_name or "Cliente",
            "tipo": tipo,
            "detalle": detalle[:500] if detalle else "",
            "created_at": datetime.now().isoformat(),
            "resolved": False,
        }).execute()
    except Exception as e:
        print(f"Supabase save_llm_request error: {e}")


def get_llm_requests(only_pending: bool = False) -> list:
    """Retrieves all LLM-captured requests, optionally only unresolved ones."""
    if not supabase_client:
        return []
    try:
        q = supabase_client.table('llm_requests').select("*").order("created_at", desc=True)
        if only_pending:
            q = q.eq("resolved", False)
        return q.execute().data
    except Exception as e:
        print(f"Supabase get_llm_requests error: {e}")
        return []


def resolve_llm_request(request_id: str):
    """Marks an LLM request as resolved."""
    if not supabase_client:
        return
    try:
        supabase_client.table('llm_requests').update({
            "resolved": True,
            "resolved_at": datetime.now().isoformat(),
        }).eq("id", request_id).execute()
    except Exception as e:
        print(f"Supabase resolve_llm_request error: {e}")


def reopen_llm_request(request_id: str):
    """Reverts an LLM request to pending (deshacer un resuelto por error)."""
    if not supabase_client:
        return
    try:
        supabase_client.table('llm_requests').update({
            "resolved": False,
            "resolved_at": None,
        }).eq("id", request_id).execute()
    except Exception as e:
        print(f"Supabase reopen_llm_request error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Document requests — solicitudes de documentos (paz y salvo, futuros tipos)
# Panel propio en admin, separado de llm_requests para que no se pierdan.
# ─────────────────────────────────────────────────────────────────────────────

def save_document_request(phone: str, client_name: str, doc_type: str, source: str = "menu", detalle: str = ""):
    """Saves a document request (paz y salvo, etc.) to document_requests table.
    source: 'menu' (botón del menú) | 'llm' (agente LLM)."""
    if test_mode.is_test_phone(phone):
        test_mode.record_document_request(phone, doc_type, source, detalle)
        return
    if not supabase_client:
        return
    try:
        supabase_client.table('document_requests').insert({
            "phone": phone,
            "client_name": client_name or "Cliente",
            "doc_type": doc_type,
            "source": source,
            "detalle": detalle[:500] if detalle else "",
            "created_at": datetime.now().isoformat(),
            "completed": False,
        }).execute()
    except Exception as e:
        print(f"Supabase save_document_request error: {e}")


def get_document_requests(only_pending: bool = False) -> list:
    """Retrieves all document requests, optionally only the pending ones."""
    if not supabase_client:
        return []
    try:
        q = supabase_client.table('document_requests').select("*").order("created_at", desc=True)
        if only_pending:
            q = q.eq("completed", False)
        return q.execute().data
    except Exception as e:
        print(f"Supabase get_document_requests error: {e}")
        return []


def complete_document_request(request_id: str):
    """Marks a document request as completed (documento enviado al cliente)."""
    if not supabase_client:
        return
    try:
        supabase_client.table('document_requests').update({
            "completed": True,
            "completed_at": datetime.now().isoformat(),
        }).eq("id", request_id).execute()
    except Exception as e:
        print(f"Supabase complete_document_request error: {e}")


def reopen_document_request(request_id: str):
    """Reverts a document request to pending (deshacer un completado por error)."""
    if not supabase_client:
        return
    try:
        supabase_client.table('document_requests').update({
            "completed": False,
            "completed_at": None,
        }).eq("id", request_id).execute()
    except Exception as e:
        print(f"Supabase reopen_document_request error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Contact data updates — yearly contact info refresh flow
# ─────────────────────────────────────────────────────────────────────────────

def start_contact_update(phone: str, trigger_source: str) -> bool:
    """Insert a new in_progress row in contact_data_updates for this phone.

    trigger_source: 'campaign_annual' | 'manual_menu'
    """
    if test_mode.is_test_phone(phone):
        return test_mode.start_contact_update(phone, trigger_source)
    if not supabase_client:
        return False
    try:
        supabase_client.table('contact_data_updates').insert({
            "phone": phone,
            "status": "in_progress",
            "trigger_source": trigger_source,
            "started_at": datetime.now().isoformat(),
        }).execute()
        return True
    except Exception as e:
        print(f"❌ Error starting contact update: {e}")
        return False


def update_contact_field(phone: str, field_name: str, value: str) -> bool:
    """Update a single field of the most recent in_progress contact_data_updates row."""
    allowed = {
        "cedula", "telefono_principal", "telefono_alterno",
        "direccion", "email", "ref_nombre", "ref_telefono", "ref_parentesco",
    }
    if field_name not in allowed:
        print(f"❌ update_contact_field: campo no permitido {field_name}")
        return False
    if test_mode.is_test_phone(phone):
        return test_mode.update_contact_field(phone, field_name, value)
    if not supabase_client:
        return False
    try:
        res = supabase_client.table('contact_data_updates')\
            .select("id")\
            .eq("phone", phone)\
            .eq("status", "in_progress")\
            .order("started_at", desc=True)\
            .limit(1)\
            .execute()
        if not res.data:
            return False
        row_id = res.data[0]["id"]
        supabase_client.table('contact_data_updates')\
            .update({field_name: value})\
            .eq("id", row_id)\
            .execute()
        return True
    except Exception as e:
        print(f"❌ Error updating contact field {field_name}: {e}")
        return False


def get_in_progress_contact_update(phone: str) -> dict | None:
    """Return the most recent in_progress contact_data_updates row for a phone, or None."""
    if test_mode.is_test_phone(phone):
        return test_mode.get_in_progress_contact_update(phone)
    if not supabase_client:
        return None
    try:
        res = supabase_client.table('contact_data_updates')\
            .select("*")\
            .eq("phone", phone)\
            .eq("status", "in_progress")\
            .order("started_at", desc=True)\
            .limit(1)\
            .execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"❌ Error fetching in_progress contact update: {e}")
        return None


def confirm_contact_update(phone: str) -> bool:
    """Mark the most recent in_progress row as confirmed and stamp the
    ultima_actualizacion_datos field on bot_conversations."""
    if test_mode.is_test_phone(phone):
        return test_mode.confirm_contact_update(phone)
    if not supabase_client:
        return False
    now = datetime.now().isoformat()
    try:
        res = supabase_client.table('contact_data_updates')\
            .select("id")\
            .eq("phone", phone)\
            .eq("status", "in_progress")\
            .order("started_at", desc=True)\
            .limit(1)\
            .execute()
        if not res.data:
            return False
        row_id = res.data[0]["id"]
        supabase_client.table('contact_data_updates')\
            .update({"status": "confirmed", "confirmed_at": now})\
            .eq("id", row_id)\
            .execute()
        supabase_client.table('bot_conversations').upsert({
            "phone": phone,
            "ultima_actualizacion_datos": now,
            "updated_at": now,
        }, on_conflict="phone").execute()
        return True
    except Exception as e:
        print(f"❌ Error confirming contact update: {e}")
        return False


def abandon_contact_update(phone: str, reason: str = "abandoned") -> bool:
    """Mark the most recent in_progress row as abandoned or cedula_mismatch."""
    if test_mode.is_test_phone(phone):
        return test_mode.abandon_contact_update(phone, reason)
    if not supabase_client:
        return False
    try:
        res = supabase_client.table('contact_data_updates')\
            .select("id")\
            .eq("phone", phone)\
            .eq("status", "in_progress")\
            .order("started_at", desc=True)\
            .limit(1)\
            .execute()
        if not res.data:
            return False
        row_id = res.data[0]["id"]
        supabase_client.table('contact_data_updates')\
            .update({"status": reason})\
            .eq("id", row_id)\
            .execute()
        return True
    except Exception as e:
        print(f"❌ Error abandoning contact update: {e}")
        return False


def get_unprocessed_contact_updates() -> list:
    """Return all confirmed-but-not-yet-processed contact updates for admin panel."""
    if not supabase_client:
        return []
    try:
        res = supabase_client.table('contact_data_updates')\
            .select("*")\
            .eq("status", "confirmed")\
            .eq("processed", False)\
            .order("confirmed_at", desc=True)\
            .execute()
        return res.data or []
    except Exception as e:
        print(f"❌ Error fetching unprocessed contact updates: {e}")
        return []


def mark_contact_update_processed(record_id, admin_user: str) -> bool:
    """Mark a contact_data_updates row as processed by the given admin user."""
    if not supabase_client:
        return False
    try:
        supabase_client.table('contact_data_updates')\
            .update({
                "processed": True,
                "processed_at": datetime.now().isoformat(),
                "admin_processor": admin_user or "",
            })\
            .eq("id", record_id)\
            .execute()
        return True
    except Exception as e:
        print(f"❌ Error marking contact update processed: {e}")
        return False


def get_last_contact_update_date(phone: str):
    """Return the ultima_actualizacion_datos timestamp string for a phone, or None."""
    if test_mode.is_test_phone(phone):
        return test_mode.get_last_contact_update_date(phone)
    if not supabase_client:
        return None
    try:
        res = supabase_client.table('bot_conversations')\
            .select("ultima_actualizacion_datos")\
            .eq("phone", phone)\
            .execute()
        if res.data:
            return res.data[0].get("ultima_actualizacion_datos")
        return None
    except Exception as e:
        print(f"Supabase get_last_contact_update_date error: {e}")
        return None


def get_phones_recently_updated(phones: list, months: int = 12) -> set:
    """Return the subset of phones whose ultima_actualizacion_datos is within
    the last `months` months. Used to exclude them from the campaign."""
    if not supabase_client or not phones:
        return set()
    try:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=30 * months)).isoformat()
        res = supabase_client.table('bot_conversations')\
            .select("phone, ultima_actualizacion_datos")\
            .in_("phone", phones)\
            .gte("ultima_actualizacion_datos", cutoff)\
            .execute()
        return {item["phone"] for item in (res.data or []) if item.get("ultima_actualizacion_datos")}
    except Exception as e:
        print(f"Supabase get_phones_recently_updated error: {e}")
        return set()


def get_phones_with_in_progress_contact_update(phones: list) -> set:
    """Return phones that currently have an in_progress contact update."""
    if not supabase_client or not phones:
        return set()
    try:
        res = supabase_client.table('contact_data_updates')\
            .select("phone")\
            .in_("phone", phones)\
            .eq("status", "in_progress")\
            .execute()
        return {item["phone"] for item in (res.data or [])}
    except Exception as e:
        print(f"Supabase get_phones_with_in_progress_contact_update error: {e}")
        return set()


def get_recent_messages_for_llm(phone: str, limit: int = 6) -> list:
    """Return recent messages formatted as an Anthropic messages array for LLM context."""
    if test_mode.is_test_phone(phone):
        return test_mode.get_recent_messages_for_llm(phone, limit)
    if not supabase_client:
        return []
    try:
        res = supabase_client.table('bot_messages')\
            .select("direction, text, msg_type")\
            .eq("phone", phone)\
            .neq("msg_type", "deleted")\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        messages = []
        for m in reversed(res.data):
            role = "user" if m["direction"] == "inbound" else "assistant"
            text = m["text"] or ""
            if m["msg_type"] in ("image", "document"):
                text = "[Archivo enviado]"
            elif len(text) > 300:
                text = text[:300] + "..."
            messages.append({"role": role, "content": text})
        # Anthropic requires messages to alternate roles; collapse consecutive same-role messages
        merged = []
        for msg in messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] += "\n" + msg["content"]
            else:
                merged.append({"role": msg["role"], "content": msg["content"]})
        return merged
    except Exception as e:
        print(f"get_recent_messages_for_llm error: {e}")
        return []

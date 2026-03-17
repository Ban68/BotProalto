"""
Conversation Logger for ProAlto WhatsApp Bot.
Provides query methods for the admin dashboard and state management for flows.
Exclusively uses Supabase.
"""
import threading
from datetime import datetime
from config import Config
from supabase import create_client, Client

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
    now = datetime.now().isoformat()
    
    # Run DB insert in background to avoid blocking WhatsApp webhook response
    threading.Thread(
        target=_supabase_log_task,
        args=(phone, direction, text, msg_type, now, wamid),
        daemon=True
    ).start()

def _supabase_log_task(phone, direction, text, msg_type, now, wamid=None):
    """Internal synchronous task to sync message to Supabase."""
    try:
        # Check current status for auto-restore logic
        current_status = "active"
        res = supabase_client.table('bot_conversations').select("status").eq("phone", phone).execute()
        
        if res.data:
            current_status = res.data[0].get("status")
            
            # If archived and new user message, wake it up to active
            if current_status == "archived" and direction == "inbound":
                supabase_client.table('bot_conversations').update({
                    "status": "active",
                    "updated_at": now
                }).eq("phone", phone).execute()
            else:
                # Just update the timestamp
                supabase_client.table('bot_conversations').update({
                    "updated_at": now
                }).eq("phone", phone).execute()
        else:
            # New conversation
            supabase_client.table('bot_conversations').insert({
                "phone": phone,
                "status": "pending_consent",
                "updated_at": now
            }).execute()

        # Insert message
        supabase_client.table('bot_messages').insert({
            "phone": phone,
            "direction": direction,
            "text": text,
            "msg_type": msg_type,
            "created_at": now,
            "wamid": wamid
        }).execute()
    except Exception as e:
        print(f"⚠️ Supabase logging error: {e}")


def get_user_state(phone: str) -> str:
    """Fetch the current detailed status/state of the user from Supabase."""
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


def get_conversations() -> list:
    """Get a summary list of all conversations, sorted by most recent."""
    try:
        # Don't show archived
        convs = supabase_client.table('bot_conversations').select("*").neq("status", "archived").order("updated_at", desc=True).limit(50).execute()
        result = []
        
        phones = [c["phone"] for c in convs.data]
        last_msgs = {}
        msg_counts = {}
        
        if phones:
            msgs_res = supabase_client.table('bot_messages').select("phone, text, id").in_("phone", phones).order("created_at", desc=True).limit(1000).execute()
            for m in msgs_res.data:
                p = m["phone"]
                if p not in last_msgs:
                    last_msgs[p] = m["text"]
                msg_counts[p] = msg_counts.get(p, 0) + 1
        
        for c in convs.data:
            p = c["phone"]
            last_msg = last_msgs.get(p, "")
            if len(last_msg) > 80:
                last_msg = last_msg[:80] + "…"
                
            result.append({
                "phone": p,
                "last_message": last_msg,
                "status": c.get("status", "active"),
                "updated_at": c.get("updated_at", ""),
                "message_count": msg_counts.get(p, 1),
            })
        return result
    except Exception as e:
        print(f"Supabase get_conversations error: {e}")
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


def log_received_document(phone: str, client_name: str, filename: str, mime_type: str, storage_url: str):
    """Logs a received document to the received_documents table."""
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


def get_received_documents() -> list:
    """Retrieves all received documents ordered by most recent first, with docs_completos from bot_conversations."""
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

        # Merge docs_completos from bot_conversations for all unique phones
        phones = list({d["phone"] for d in docs if d.get("phone")})
        conv_res = supabase_client.table('bot_conversations')\
            .select("phone, docs_completos")\
            .in_("phone", phones)\
            .execute()
        docs_completos_map = {r["phone"]: r.get("docs_completos", False) for r in conv_res.data}

        for doc in docs:
            doc["docs_completos"] = docs_completos_map.get(doc.get("phone"), False)

        return docs
    except Exception as e:
        print(f"Supabase get_received_documents error: {e}")
        return []


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

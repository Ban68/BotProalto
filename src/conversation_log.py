"""
Conversation Logger for ProAlto WhatsApp Bot.
Provides query methods for the admin dashboard.
Hybrid storage: uses Supabase if configured, otherwise falls back to a local JSON file.
"""
import json
import os
import threading
from datetime import datetime
from config import Config

# ── Supabase Setup ───────────────────────────────────────────────────
USE_SUPABASE = bool(Config.SUPABASE_URL and Config.SUPABASE_KEY)
supabase_client = None

if USE_SUPABASE:
    try:
        from supabase import create_client
        supabase_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        print("✅ Supabase configured for conversation logging.")
    except Exception as e:
        print(f"❌ Failed to initialize Supabase client: {e}")
        USE_SUPABASE = False

# ── Local JSON Fallback Setup ────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CONVERSATIONS_FILE = os.path.join(DATA_DIR, "conversations.json")
_json_lock = threading.Lock()

def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def _load_json_conversations() -> dict:
    _ensure_data_dir()
    if not os.path.exists(CONVERSATIONS_FILE):
        return {}
    try:
        with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_json_conversations(data: dict):
    _ensure_data_dir()
    with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Core Functions (Abstracted) ──────────────────────────────────────

def log_message(phone: str, direction: str, text: str, msg_type: str = "text"):
    """Log a single message to the conversation history."""
    now = datetime.now().isoformat()
    
    if USE_SUPABASE and supabase_client:
        try:
            # Upsert into bot_conversations to ensure phone exists and update updated_at
            supabase_client.table('bot_conversations').upsert({
                "phone": phone,
                "updated_at": now
            }, on_conflict="phone").execute()
            
            # Insert message
            supabase_client.table('bot_messages').insert({
                "phone": phone,
                "direction": direction,
                "text": text,
                "msg_type": msg_type
            }).execute()
            return
        except Exception as e:
            print(f"Supabase logging error: {e}")
            # Fallback to JSON below if there's an error... (optional, we'll just fail gracefully)
            pass

    # JSON Fallback
    with _json_lock:
        conversations = _load_json_conversations()
        if phone not in conversations:
            conversations[phone] = {
                "messages": [],
                "status": "bot",
                "updated_at": "",
                "created_at": now,
            }
        conversations[phone]["messages"].append({
            "direction": direction,
            "text": text,
            "type": msg_type,
            "timestamp": now,
        })
        conversations[phone]["updated_at"] = now
        _save_json_conversations(conversations)


def set_agent_mode(phone: str, active: bool):
    """Toggle agent mode for a conversation."""
    status = "agent" if active else "bot"
    now = datetime.now().isoformat()
    
    if USE_SUPABASE and supabase_client:
        try:
            supabase_client.table('bot_conversations').upsert({
                "phone": phone,
                "status": status,
                "updated_at": now
            }, on_conflict="phone").execute()
            return
        except Exception as e:
            print(f"Supabase agent mode error: {e}")

    # JSON Fallback
    with _json_lock:
        conversations = _load_json_conversations()
        if phone in conversations:
            conversations[phone]["status"] = status
            conversations[phone]["updated_at"] = now
            _save_json_conversations(conversations)


def get_conversations() -> list:
    """Get a summary list of all conversations, sorted by most recent."""
    if USE_SUPABASE and supabase_client:
        try:
            # Query conversations order by updated_at, exclude 'archived'
            convs = supabase_client.table('bot_conversations').select("*").neq("status", "archived").order("updated_at", desc=True).execute()
            result = []
            
            # To get last message efficiently, we could do a joined query, 
            # but for MVP we fetch the latest message for each.
            # (In production, a database view is better. We'll do a simple list here).
            for c in convs.data:
                msgs_res = supabase_client.table('bot_messages').select("*").eq("phone", c["phone"]).order("created_at", desc=True).limit(1).execute()
                last_msg = msgs_res.data[0]["text"] if msgs_res.data else ""
                
                if len(last_msg) > 80:
                    last_msg = last_msg[:80] + "…"
                    
                count_res = supabase_client.table('bot_messages').select("id", count="exact").eq("phone", c["phone"]).execute()
                
                result.append({
                    "phone": c["phone"],
                    "last_message": last_msg,
                    "status": c.get("status", "bot"),
                    "updated_at": c.get("updated_at", ""),
                    "message_count": count_res.count if count_res.count else 0,
                })
            return result
        except Exception as e:
            print(f"Supabase get_conversations error: {e}")

    # JSON Fallback
    conversations = _load_json_conversations()
    result = []
    for phone, data in conversations.items():
        if data.get("status") == "archived":
            continue
            
        messages = data.get("messages", [])
        last_msg = messages[-1]["text"] if messages else ""
        if len(last_msg) > 80:
            last_msg = last_msg[:80] + "…"
        result.append({
            "phone": phone,
            "last_message": last_msg,
            "status": data.get("status", "bot"),
            "updated_at": data.get("updated_at", ""),
            "message_count": len(messages),
        })
    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return result


def get_conversation(phone: str) -> dict | None:
    """Get the full conversation history for a specific phone number."""
    if USE_SUPABASE and supabase_client:
        try:
            c_res = supabase_client.table('bot_conversations').select("*").eq("phone", phone).execute()
            if not c_res.data:
                return None
                
            m_res = supabase_client.table('bot_messages').select("*").eq("phone", phone).order("created_at").execute()
            
            # Transform to expected format
            messages = []
            for m in m_res.data:
                messages.append({
                    "direction": m["direction"],
                    "text": m["text"],
                    "type": m["msg_type"],
                    "timestamp": m["created_at"]
                })
                
            return {
                "status": c_res.data[0].get("status", "bot"),
                "updated_at": c_res.data[0].get("updated_at", ""),
                "messages": messages
            }
        except Exception as e:
            print(f"Supabase get_conversation error: {e}")

    # JSON Fallback
    conversations = _load_json_conversations()
    return conversations.get(phone)


def get_agent_conversations() -> list:
    """Get only conversations currently in agent mode."""
    return [c for c in get_conversations() if c["status"] == "agent"]

def delete_conversation(phone: str, permanent: bool = False):
    """Delete or hide a conversation from the dashboard."""
    if USE_SUPABASE and supabase_client:
        try:
            if permanent:
                # Hard delete (will cascade delete messages due to DB schema)
                supabase_client.table('bot_conversations').delete().eq("phone", phone).execute()
            else:
                # Soft delete
                supabase_client.table('bot_conversations').update({"status": "archived"}).eq("phone", phone).execute()
            return
        except Exception as e:
            print(f"Supabase delete error: {e}")

    # JSON Fallback
    with _json_lock:
        conversations = _load_json_conversations()
        if phone in conversations:
            if permanent:
                del conversations[phone]
            else:
                conversations[phone]["status"] = "archived"
            _save_json_conversations(conversations)

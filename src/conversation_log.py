"""
Conversation Logger for ProAlto WhatsApp Bot.
Stores all messages (inbound/outbound) in a JSON file
and provides query methods for the admin dashboard.
"""
import json
import os
import threading
from datetime import datetime

# Path to the JSON file that stores conversations
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CONVERSATIONS_FILE = os.path.join(DATA_DIR, "conversations.json")

# Thread lock for safe concurrent file access
_lock = threading.Lock()


def _ensure_data_dir():
    """Create data directory if it doesn't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_conversations() -> dict:
    """Load conversations from the JSON file."""
    _ensure_data_dir()
    if not os.path.exists(CONVERSATIONS_FILE):
        return {}
    try:
        with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_conversations(data: dict):
    """Save conversations to the JSON file."""
    _ensure_data_dir()
    with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_message(phone: str, direction: str, text: str, msg_type: str = "text"):
    """
    Log a single message to the conversation history.

    Args:
        phone: User's phone number
        direction: "inbound" (user→bot) or "outbound" (bot→user)
        text: Message content
        msg_type: Message type (text, interactive, button_reply, etc.)
    """
    with _lock:
        conversations = _load_conversations()

        if phone not in conversations:
            conversations[phone] = {
                "messages": [],
                "status": "bot",  # "bot" or "agent"
                "updated_at": "",
                "created_at": datetime.now().isoformat(),
            }

        now = datetime.now().isoformat()
        conversations[phone]["messages"].append({
            "direction": direction,
            "text": text,
            "type": msg_type,
            "timestamp": now,
        })
        conversations[phone]["updated_at"] = now

        _save_conversations(conversations)


def set_agent_mode(phone: str, active: bool):
    """
    Toggle agent mode for a conversation.

    Args:
        phone: User's phone number
        active: True to enable agent mode, False to return to bot
    """
    with _lock:
        conversations = _load_conversations()
        if phone in conversations:
            conversations[phone]["status"] = "agent" if active else "bot"
            conversations[phone]["updated_at"] = datetime.now().isoformat()
            _save_conversations(conversations)


def get_conversations() -> list:
    """
    Get a summary list of all conversations, sorted by most recent.

    Returns:
        List of dicts: [{phone, last_message, status, updated_at, message_count}, ...]
    """
    conversations = _load_conversations()
    result = []

    for phone, data in conversations.items():
        messages = data.get("messages", [])
        last_msg = messages[-1]["text"] if messages else ""
        # Truncate long messages for the list view
        if len(last_msg) > 80:
            last_msg = last_msg[:80] + "…"

        result.append({
            "phone": phone,
            "last_message": last_msg,
            "status": data.get("status", "bot"),
            "updated_at": data.get("updated_at", ""),
            "message_count": len(messages),
        })

    # Sort by most recent activity
    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return result


def get_conversation(phone: str) -> dict | None:
    """
    Get the full conversation history for a specific phone number.

    Returns:
        Dict with messages list, status, timestamps — or None if not found.
    """
    conversations = _load_conversations()
    return conversations.get(phone)


def get_agent_conversations() -> list:
    """
    Get only conversations currently in agent mode.

    Returns:
        Same format as get_conversations(), filtered to agent status.
    """
    return [c for c in get_conversations() if c["status"] == "agent"]

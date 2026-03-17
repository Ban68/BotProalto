"""
fix_cliente_names.py

Retroactively fixes captured_emails records where name = 'Cliente'.
Strategy:
  1. Fetch all captured_emails where name = 'Cliente'
  2. For each phone, check bot_conversations.client_name first (fastest)
  3. If still missing, search bot_messages for the cedula the user submitted
     while in waiting_for_cedula state (a pure-digits message right before
     the bot replied with "Resultado de Solicitud")
  4. Query Cloud Run API with that cedula to get the real name
  5. Update captured_emails.name and bot_conversations.client_name
"""

import os
import sys
import re
import requests

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
# Explicitly point to the .env in the project root
_root = os.path.join(os.path.dirname(__file__), "..")
load_dotenv(os.path.join(_root, ".env"))

from config import Config
from supabase import create_client

# ── Init clients ──────────────────────────────────────────────
supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
CLOUD_RUN_URL = os.getenv("CLOUD_RUN_URL", "").rstrip("/")
API_TOKEN_SECRET = os.getenv("API_TOKEN_SECRET", "")


def query_cloud_run(cedula: str) -> str | None:
    """Returns nombre_completo for the cedula, or None if not found."""
    try:
        r = requests.post(
            CLOUD_RUN_URL,
            json={"cedula": cedula},
            headers={"Authorization": f"Bearer {API_TOKEN_SECRET}", "Content-Type": "application/json"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("found"):
                return data.get("nombre_completo")
    except Exception as e:
        print(f"    ⚠️  Cloud Run error for cedula {cedula}: {e}")
    return None


def query_cloud_run_by_phone(phone: str) -> str | None:
    """Returns nombre_completo for the phone number, or None if not found."""
    try:
        r = requests.post(
            CLOUD_RUN_URL,
            json={"tipo": "por_telefono", "telefono": phone},
            headers={"Authorization": f"Bearer {API_TOKEN_SECRET}", "Content-Type": "application/json"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("found"):
                return data.get("nombre_completo")
    except Exception as e:
        print(f"    ⚠️  Cloud Run error for phone {phone}: {e}")
    return None


def find_cedula_in_messages(phone: str) -> str | None:
    """
    Looks in bot_messages for a pure-digit message sent by this phone
    that was followed by a bot reply containing 'Resultado de Solicitud'.
    Returns the cedula string or None.
    """
    try:
        msgs = (
            supabase.table("bot_messages")
            .select("direction, text, created_at")
            .eq("phone", phone)
            .order("created_at")
            .execute()
        ).data

        for i, msg in enumerate(msgs):
            # User message that is a pure number (the cedula)
            if msg["direction"] == "inbound" and re.fullmatch(r"\d{5,12}", (msg["text"] or "").strip()):
                # Check if next outbound message is the status reply
                for j in range(i + 1, min(i + 4, len(msgs))):
                    if msgs[j]["direction"] == "outbound" and "Resultado de Solicitud" in (msgs[j]["text"] or ""):
                        return msg["text"].strip()
    except Exception as e:
        print(f"    ⚠️  Error searching messages for {phone}: {e}")
    return None


def main():
    print("🔍 Fetching captured_emails with name = 'Cliente'...")
    rows = (
        supabase.table("captured_emails")
        .select("id, phone, email, name")
        .eq("name", "Cliente")
        .execute()
    ).data

    if not rows:
        print("✅ No records with name='Cliente' found. Nothing to fix.")
        return

    print(f"   Found {len(rows)} record(s) to fix.\n")

    # Build a map of phone -> client_name from bot_conversations (batch query)
    phones = list({r["phone"] for r in rows})
    conv_res = (
        supabase.table("bot_conversations")
        .select("phone, client_name")
        .in_("phone", phones)
        .execute()
    ).data
    conv_name_map = {r["phone"]: (r.get("client_name") or "").strip() for r in conv_res}

    fixed = 0
    not_found = []

    for row in rows:
        phone = row["phone"]
        record_id = row["id"]
        email = row["email"]
        print(f"📱 {phone}  |  {email}")

        # Step 1: try bot_conversations.client_name
        name = conv_name_map.get(phone, "")
        if name and name.lower() != "cliente":
            print(f"   ✔ Found name in bot_conversations: {name}")
        else:
            # Step 2: dig into bot_messages for the cedula
            cedula = find_cedula_in_messages(phone)
            if cedula:
                print(f"   🔎 Found cedula in messages: {cedula}. Querying Cloud Run...")
                name = query_cloud_run(cedula) or ""
                if name:
                    print(f"   ✔ Cloud Run returned: {name}")
                else:
                    print(f"   ❌ Cloud Run found nothing for cedula {cedula}")
            else:
                print(f"   ❌ Could not find cedula in message history")
                # Step 3: query Cloud Run by phone number directly
                print(f"   🔎 Trying Cloud Run by phone...")
                name = query_cloud_run_by_phone(phone) or ""
                if name:
                    print(f"   ✔ Cloud Run returned: {name}")
                else:
                    print(f"   ❌ Cloud Run found nothing for phone {phone}")

        if name and name.lower() != "cliente":
            # Update captured_emails
            supabase.table("captured_emails").update({"name": name}).eq("id", record_id).execute()
            # Also update bot_conversations so future lookups work
            supabase.table("bot_conversations").upsert(
                {"phone": phone, "client_name": name}, on_conflict="phone"
            ).execute()
            print(f"   ✅ Updated to: {name}\n")
            fixed += 1
        else:
            print(f"   ⚠️  Could not resolve name — left as-is\n")
            not_found.append(phone)

    print("─" * 50)
    print(f"✅ Fixed: {fixed} / {len(rows)}")
    if not_found:
        print(f"⚠️  Could not resolve ({len(not_found)}):")
        for p in not_found:
            print(f"   {p}")


if __name__ == "__main__":
    main()

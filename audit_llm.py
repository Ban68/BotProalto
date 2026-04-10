"""
Audit script: Extract all LLM agent conversations from the last 7 days.
Temporary — delete after audit is complete.
"""
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY"),
)

# Date range: last 7 days
date_to = datetime.now()
date_from = date_to - timedelta(days=7)
date_from_str = date_from.strftime("%Y-%m-%dT00:00:00")
date_to_str = date_to.strftime("%Y-%m-%dT23:59:59")

print(f"=== Audit range: {date_from_str} to {date_to_str} ===\n")

# 1. Get all LLM messages in range
print("--- Fetching LLM messages (msg_type='llm') ---")
llm_msgs = supabase.table('bot_messages') \
    .select("phone, direction, text, msg_type, created_at") \
    .eq("msg_type", "llm") \
    .gte("created_at", date_from_str) \
    .lte("created_at", date_to_str) \
    .order("created_at") \
    .execute()

llm_phones = set()
for m in llm_msgs.data:
    llm_phones.add(m["phone"])

print(f"Found {len(llm_msgs.data)} LLM messages from {len(llm_phones)} unique phones\n")

# 2. For each phone with LLM activity, get FULL conversation in range
print("--- Fetching full conversations for LLM phones ---")
conversations = {}
for phone in sorted(llm_phones):
    msgs = supabase.table('bot_messages') \
        .select("direction, text, msg_type, created_at") \
        .eq("phone", phone) \
        .gte("created_at", date_from_str) \
        .lte("created_at", date_to_str) \
        .order("created_at") \
        .execute()
    conversations[phone] = msgs.data
    print(f"  {phone}: {len(msgs.data)} messages total")

# 3. Get LLM requests in range
print("\n--- Fetching LLM requests ---")
llm_requests = supabase.table('llm_requests') \
    .select("*") \
    .gte("created_at", date_from_str) \
    .lte("created_at", date_to_str) \
    .order("created_at") \
    .execute()
print(f"Found {len(llm_requests.data)} LLM requests\n")

# 4. Get conversation metadata
print("--- Fetching conversation metadata ---")
conv_meta = {}
for phone in sorted(llm_phones):
    meta = supabase.table('bot_conversations') \
        .select("phone, client_name, status, updated_at") \
        .eq("phone", phone) \
        .execute()
    if meta.data:
        conv_meta[phone] = meta.data[0]

# 5. Output full audit data
print("\n" + "=" * 80)
print("AUDIT REPORT: LLM Agent Conversations (Last 7 Days)")
print("=" * 80)

for phone in sorted(conversations.keys()):
    meta = conv_meta.get(phone, {})
    name = meta.get("client_name", "Unknown")
    status = meta.get("status", "?")
    msgs = conversations[phone]
    llm_count = sum(1 for m in msgs if m["msg_type"] == "llm")

    print(f"\n{'-' * 70}")
    print(f"PHONE: {phone} | NAME: {name} | STATUS: {status} | LLM msgs: {llm_count} | Total msgs: {len(msgs)}")
    print(f"{'-' * 70}")

    for m in msgs:
        ts = m["created_at"][:19].replace("T", " ")
        direction = "CLIENT" if m["direction"] == "inbound" else "BOT"
        tag = ""
        if m["msg_type"] == "llm":
            tag = " [LLM]"
        elif m["msg_type"] == "button_reply":
            tag = " [BTN]"
        elif m["msg_type"] in ("image", "document"):
            tag = f" [{m['msg_type'].upper()}]"

        text = (m.get("text") or "(empty)").replace("\n", " | ")
        if len(text) > 300:
            text = text[:300] + "..."
        print(f"  {ts} {direction}{tag}: {text}")

# 6. LLM Requests
if llm_requests.data:
    print(f"\n{'=' * 70}")
    print("LLM REQUESTS REGISTERED")
    print(f"{'=' * 70}")
    for r in llm_requests.data:
        ts = r["created_at"][:19].replace("T", " ")
        resolved = "RESOLVED" if r.get("resolved") else "PENDING"
        print(f"  {ts} | {r['phone']} | {r.get('client_name', '?')} | tipo={r.get('tipo', '?')} | {resolved}")
        print(f"    Detail: {r.get('detalle', '(none)')}")

print(f"\n{'=' * 70}")
print("END OF AUDIT")
print(f"{'=' * 70}")

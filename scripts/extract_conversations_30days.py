#!/usr/bin/env python3
"""
Extract all conversations from the last 30 days from Supabase.
Saves results to JSON and CSV formats.
"""
import json
import csv
from datetime import datetime, timedelta
from pathlib import Path
from supabase import create_client

# Configuration
SUPABASE_URL = "https://pkfnzqzjpheorlbnmvoe.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBrZm56cXpqcGhlb3JsYm5tdm9lIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkwODc1NDEsImV4cCI6MjA4NDY2MzU0MX0.q5Ir1YwoRDpCqqXCFWmlQzPSee1PAagiEvivFnea7JY"

# Calculate date range
today = datetime.now()
thirty_days_ago = today - timedelta(days=30)
date_threshold = thirty_days_ago.isoformat()

print(f"[*] Extracting conversations from {thirty_days_ago.date()} to {today.date()}")
print(f"[*] Connecting to Supabase...")

# Initialize Supabase client
client = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    # Fetch all messages from the last 30 days
    print("[*] Fetching messages...")
    messages_response = client.table('bot_messages')\
        .select("*")\
        .gte("created_at", date_threshold)\
        .order("created_at", desc=False)\
        .execute()

    messages = messages_response.data
    print(f"[OK] Found {len(messages)} messages")

    # Fetch conversation metadata
    print("[*] Fetching conversation metadata...")
    conversations_response = client.table('bot_conversations')\
        .select("*")\
        .execute()

    conversations = conversations_response.data
    conv_map = {c["phone"]: c for c in conversations}
    print(f"[OK] Found {len(conversations)} unique conversations")

    # Group messages by phone
    conversations_data = {}
    for msg in messages:
        phone = msg["phone"]
        if phone not in conversations_data:
            conv_info = conv_map.get(phone, {})
            conversations_data[phone] = {
                "phone": phone,
                "client_name": conv_info.get("client_name") or "Unknown",
                "status": conv_info.get("status") or "unknown",
                "empresa": conv_info.get("empresa") or "N/A",
                "message_count": 0,
                "messages": []
            }

        conversations_data[phone]["messages"].append({
            "id": msg.get("id"),
            "direction": msg.get("direction"),
            "text": msg.get("text"),
            "msg_type": msg.get("msg_type"),
            "created_at": msg.get("created_at"),
            "wamid": msg.get("wamid")
        })
        conversations_data[phone]["message_count"] += 1

    # Save to JSON
    output_dir = Path("c:/Proyects/Bot/exports")
    output_dir.mkdir(exist_ok=True)

    json_file = output_dir / f"conversaciones_30dias_{today.strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(conversations_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"[OK] Saved JSON: {json_file}")

    # Save summary to CSV
    csv_file = output_dir / f"resumen_conversaciones_30dias_{today.strftime('%Y%m%d_%H%M%S')}.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Telefono", "Nombre Cliente", "Estado", "Empresa", "Total Mensajes", "Primer Mensaje", "Ultimo Mensaje"])

        for phone, conv in sorted(conversations_data.items()):
            if conv["messages"]:
                first_msg_time = conv["messages"][0]["created_at"]
                last_msg_time = conv["messages"][-1]["created_at"]
            else:
                first_msg_time = last_msg_time = "N/A"

            writer.writerow([
                phone,
                conv["client_name"],
                conv["status"],
                conv["empresa"],
                conv["message_count"],
                first_msg_time,
                last_msg_time
            ])
    print(f"[OK] Saved CSV: {csv_file}")

    # Print summary stats
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total unique conversations: {len(conversations_data)}")
    print(f"Total messages: {sum(c['message_count'] for c in conversations_data.values())}")
    print(f"Average messages per conversation: {sum(c['message_count'] for c in conversations_data.values()) / len(conversations_data) if conversations_data else 0:.1f}")

    # Status breakdown
    status_counts = {}
    for conv in conversations_data.values():
        status = conv["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\nConversation status breakdown:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  • {status}: {count}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()

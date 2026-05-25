#!/usr/bin/env python3
"""
Extract all conversations from the last 30 days from Supabase with proper pagination.
"""
import json
import csv
from datetime import datetime, timedelta
from pathlib import Path
from supabase import create_client

SUPABASE_URL = "https://pkfnzqzjpheorlbnmvoe.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBrZm56cXpqcGhlb3JsYm5tdm9lIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkwODc1NDEsImV4cCI6MjA4NDY2MzU0MX0.q5Ir1YwoRDpCqqXCFWmlQzPSee1PAagiEvivFnea7JY"

today = datetime.now()
thirty_days_ago = today - timedelta(days=30)
date_threshold = thirty_days_ago.isoformat() + "Z"

print(f"[*] Extracting conversations from {thirty_days_ago.date()} to {today.date()}")
print(f"[*] Connecting to Supabase...")

client = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    print("[*] Fetching messages with pagination...")

    all_messages = []
    offset = 0
    batch_size = 1000
    total_count = None

    while True:
        print(f"[*] Fetching batch: offset {offset}")

        response = client.table('bot_messages')\
            .select("*", count="exact")\
            .gte("created_at", date_threshold)\
            .order("created_at", desc=False)\
            .range(offset, offset + batch_size - 1)\
            .execute()

        if total_count is None:
            total_count = response.count
            print(f"[OK] Total messages to fetch: {total_count}")

        if not response.data:
            break

        all_messages.extend(response.data)
        print(f"[OK] Fetched {len(response.data)} messages (total so far: {len(all_messages)})")

        if len(response.data) < batch_size:
            break

        offset += batch_size

    print(f"[OK] Total messages retrieved: {len(all_messages)}")

    print("[*] Fetching conversation metadata...")
    conversations_response = client.table('bot_conversations')\
        .select("*")\
        .execute()

    conversations = conversations_response.data
    conv_map = {c["phone"]: c for c in conversations}
    print(f"[OK] Found {len(conversations)} unique conversations")

    print("[*] Processing conversations...")
    conversations_data = {}

    for msg in all_messages:
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

    print(f"[OK] Processed into {len(conversations_data)} conversations")

    output_dir = Path("c:/Proyects/Bot/exports")
    output_dir.mkdir(exist_ok=True)

    timestamp = today.strftime('%Y%m%d_%H%M%S')

    json_file = output_dir / f"conversaciones_30dias_completo_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(conversations_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"[OK] Saved JSON: {json_file}")

    csv_file = output_dir / f"resumen_conversaciones_30dias_completo_{timestamp}.csv"
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

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total unique conversations: {len(conversations_data)}")
    print(f"Total messages: {sum(c['message_count'] for c in conversations_data.values())}")
    print(f"Average messages per conversation: {sum(c['message_count'] for c in conversations_data.values()) / len(conversations_data) if conversations_data else 0:.1f}")

    status_counts = {}
    for conv in conversations_data.values():
        status = conv["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\nConversation status breakdown:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  - {status}: {count}")

    print("\nDate range in data:")
    dates = {}
    for conv in conversations_data.values():
        for msg in conv["messages"]:
            date = msg["created_at"][:10]
            dates[date] = dates.get(date, 0) + 1

    for date in sorted(dates.keys()):
        print(f"  {date}: {dates[date]} messages")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()

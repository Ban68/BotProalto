"""
Extrae los chats de la semana pasada desde Supabase y los vuelca a un archivo
markdown para auditoría. Ventana: lunes 2026-06-01 00:00 a domingo 2026-06-07 23:59.
"""
import os
import sys
from collections import defaultdict
from datetime import datetime

# Cargar .env
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: faltan credenciales de Supabase")
    sys.exit(1)

client = create_client(SUPABASE_URL, SUPABASE_KEY)

START = "2026-06-01T00:00:00"
END = "2026-06-07T23:59:59"

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "informes")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_FILE = os.path.join(OUT_DIR, "chats_semana_2026-06-01_a_2026-06-07.md")

# Paginar bot_messages en la ventana
all_msgs = []
page_size = 1000
offset = 0
while True:
    res = client.table("bot_messages") \
        .select("phone, direction, text, msg_type, created_at") \
        .gte("created_at", START) \
        .lte("created_at", END) \
        .order("created_at", desc=False) \
        .range(offset, offset + page_size - 1) \
        .execute()
    batch = res.data or []
    all_msgs.extend(batch)
    if len(batch) < page_size:
        break
    offset += page_size

print(f"Mensajes en ventana: {len(all_msgs)}")

# Agrupar por telefono
by_phone = defaultdict(list)
for m in all_msgs:
    by_phone[m["phone"]].append(m)

phones = list(by_phone.keys())
print(f"Conversaciones distintas: {len(phones)}")

# Traer nombres y estado de bot_conversations
names = {}
statuses = {}
for i in range(0, len(phones), 100):
    chunk = phones[i:i+100]
    try:
        cres = client.table("bot_conversations") \
            .select("phone, client_name, status") \
            .in_("phone", chunk).execute()
        for r in (cres.data or []):
            names[r["phone"]] = r.get("client_name") or ""
            statuses[r["phone"]] = r.get("status") or ""
    except Exception as e:
        print(f"warn nombres: {e}")

# Metricas agregadas
total_in = sum(1 for m in all_msgs if m["direction"] == "inbound")
total_out = sum(1 for m in all_msgs if m["direction"] == "outbound")
type_counts = defaultdict(int)
for m in all_msgs:
    type_counts[m.get("msg_type") or "text"] += 1

# Conteo de senales/patrones
def count_text(needle):
    n = needle.lower()
    return sum(1 for m in all_msgs if m["direction"] == "outbound" and n in (m.get("text") or "").lower())

no_entendi = count_text("no entend")
escaladas = count_text("asesor")

# Escribir salida
lines = []
lines.append(f"# Chats semana 2026-06-01 a 2026-06-07\n")
lines.append(f"Extraído: {datetime.now().isoformat()}\n")
lines.append("## Resumen de extracción\n")
lines.append(f"- Mensajes totales: {len(all_msgs)}")
lines.append(f"- Entrantes (cliente): {total_in}")
lines.append(f"- Salientes (bot): {total_out}")
lines.append(f"- Conversaciones distintas: {len(phones)}")
lines.append(f"- Salientes con 'no entend...': {no_entendi}")
lines.append(f"- Salientes con 'asesor': {escaladas}")
lines.append(f"- Tipos de mensaje: {dict(type_counts)}\n")

# Estado de conversaciones
status_counts = defaultdict(int)
for p in phones:
    status_counts[statuses.get(p, "?")] += 1
lines.append(f"- Estados de conversación: {dict(status_counts)}\n")

lines.append("## Conversaciones\n")
# Ordenar por cantidad de mensajes desc
phones_sorted = sorted(phones, key=lambda p: len(by_phone[p]), reverse=True)
for p in phones_sorted:
    msgs = by_phone[p]
    nm = names.get(p, "")
    st = statuses.get(p, "")
    # Enmascarar telefono parcialmente para privacidad
    masked = p[:-4] + "****" if len(p) > 4 else p
    lines.append(f"### {masked} | {nm} | estado={st} | {len(msgs)} msgs\n")
    for m in msgs:
        d = "CLIENTE" if m["direction"] == "inbound" else "BOT"
        t = (m.get("text") or "").replace("\n", " ")
        ts = (m.get("created_at") or "")[:16]
        mt = m.get("msg_type") or "text"
        tag = f"[{mt}]" if mt not in ("text",) else ""
        lines.append(f"- {ts} {d}{tag}: {t}")
    lines.append("")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Escrito: {OUT_FILE}")
print(f"Tamaño: {os.path.getsize(OUT_FILE)} bytes")

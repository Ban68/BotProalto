"""Analiza patrones de fallo en los chats de la semana, separando 3 fuentes:
asesor humano (panel), plantillas estructuradas (flows.py), y LLM texto libre."""
import os, re
from collections import defaultdict, Counter
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
START, END = "2026-06-01T00:00:00", "2026-06-07T23:59:59"

msgs = []
off = 0
while True:
    res = client.table("bot_messages").select("phone, direction, text, msg_type, created_at") \
        .gte("created_at", START).lte("created_at", END).order("created_at").range(off, off+999).execute()
    b = res.data or []
    msgs.extend(b)
    if len(b) < 1000: break
    off += 1000

by_phone = defaultdict(list)
for m in msgs:
    by_phone[m["phone"]].append(m)

inb = [m for m in msgs if m["direction"] == "inbound"]
out_all = [m for m in msgs if m["direction"] == "outbound"]

# Marcadores de plantilla estructurada (emojis intencionales de flows.py)
TEMPLATE_HEADERS = ("🔍", "💰", "📧", "✅", "📄", "👤", "📋", "Para agilizar",
                    "Para enviarnos", "Para que podamos", "Hemos recibido",
                    "Tu solicitud", "Gracias por", "Hola, en qué", "Qué deseas")

def source_of(m):
    t = (m.get("text") or "")
    mt = m.get("msg_type") or "text"
    if t.startswith("[Template") or t.startswith("[Menu") or mt in ("interactive", "template", "button"):
        return "plantilla"
    if t.startswith("👨‍💼") or re.match(r"^👨", t):
        return "asesor"
    # mensajes estructurados con header de emoji
    if any(t.startswith(h) or h in t[:40] for h in TEMPLATE_HEADERS):
        return "plantilla"
    return "llm"

src_counts = Counter(source_of(m) for m in out_all)
llm_msgs = [m for m in out_all if source_of(m) == "llm"]
asesor_msgs = [m for m in out_all if source_of(m) == "asesor"]

# --- Patrones de fallo SOLO en mensajes LLM ---
pat = {
  "emoji": r"[\U0001F300-\U0001FAFF☀-➿]",
  "negrilla": r"\*\*[^*]+\*\*|(?<!\*)\*[^*\n]+\*(?!\*)",
  "viñetas": r"(?m)^\s*[-•]\s|\n\d+\.\s",
  "signo_apertura": r"[¿¡]",
  "promesa_tiempo": r"(mañana|24 horas|48 horas|hoy mismo|en el transcurso del d|en breve|en unos minutos|antes de las|durante el d[ií]a)",
  "tasa_especifica": r"(tasa del \d|inter[eé]s del \d|\d+(\.\d+)?\s*% (de inter|anual|mensual))",
  "callejon": r"(?i)^(perfecto,? )?(d[eé]jame (revisar|verificar|consultar)|voy a (revisar|consultar)|un momento|dame un momento)[\s.!]*$",
  "admite_ia": r"(?i)(soy una (ia|inteligencia)|modelo de lenguaje|soy un bot|soy un asistente virtual|no soy human)",
  "tag_filtrado": r"\[(REGISTRAR_SOLICITUD|HABLAR_ASESOR|MOSTRAR_MENU)",
  "no_puedo": r"(?i)(no tengo esa informaci|no puedo ayudart|no puedo con eso)",
}
counts = {k: 0 for k in pat}
ex = defaultdict(list)
for m in llm_msgs:
    t = m.get("text") or ""
    for k, rx in pat.items():
        if re.search(rx, t):
            counts[k] += 1
            if len(ex[k]) < 5:
                ex[k].append((m["phone"][-4:], t[:170].replace("\n"," ")))

# --- Loops: cliente manda texto, bot LLM responde, cliente repite igual o "??" ---
# Detectar conversaciones donde cliente escribio "??" o repitio identico
repeat_loops = 0
for p, ms in by_phone.items():
    texts_in = [(m.get("text") or "").strip().lower() for m in ms if m["direction"]=="inbound" and (m.get("msg_type") or "text")=="text"]
    c = Counter(texts_in)
    for t, n in c.items():
        if n >= 3 and len(t) > 1:
            repeat_loops += 1
            break

# --- Escaladas: estado agent + señal HABLAR_ASESOR ejecutada ---
conv_status = {}
phones = list(by_phone.keys())
for i in range(0, len(phones), 100):
    cres = client.table("bot_conversations").select("phone,status").in_("phone", phones[i:i+100]).execute()
    for r in (cres.data or []):
        conv_status[r["phone"]] = r.get("status")
agent_convs = [p for p in phones if conv_status.get(p) in ("agent","agent_silent")]

# --- Conversaciones solo-bot vs con intervencion humana ---
phones_with_asesor = {m["phone"] for m in asesor_msgs}
solo_bot = [p for p in phones if p not in phones_with_asesor]

# --- Cobertura: conversaciones donde el cliente escribio texto libre y el LLM respondio ---
phones_with_llm = {m["phone"] for m in llm_msgs}

print("=== FUENTES DE MENSAJES SALIENTES ===")
for s,c in src_counts.most_common(): print(f"  {s}: {c}")
print(f"\n=== CONVERSACIONES ===")
print(f"  Total conversaciones: {len(phones)}")
print(f"  Con intervención de asesor humano: {len(phones_with_asesor)}")
print(f"  Solo bot (sin asesor): {len(solo_bot)}")
print(f"  En estado agent/agent_silent (al cierre): {len(agent_convs)}")
print(f"  Con respuesta LLM texto libre: {len(phones_with_llm)}")
print(f"  Con loop de repetición (cliente repite ≥3x): {repeat_loops}")
print(f"\n=== FALLOS EN MENSAJES LLM (n={len(llm_msgs)}) ===")
for k in pat:
    pct = 100*counts[k]/max(len(llm_msgs),1)
    print(f"  {k}: {counts[k]} ({pct:.1f}%)")
    for ph, e in ex[k][:3]:
        print(f"      [{ph}] {e}")

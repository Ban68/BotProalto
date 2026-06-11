"""Aisla el corpus LLM real por unicidad (las plantillas se repiten; el LLM es único)
y re-evalua fallos + muestrea para inspección manual."""
import os, re, random
from collections import defaultdict, Counter
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
START, END = "2026-06-01T00:00:00", "2026-06-07T23:59:59"
msgs = []
off = 0
while True:
    res = client.table("bot_messages").select("phone,direction,text,msg_type,created_at") \
        .gte("created_at", START).lte("created_at", END).order("created_at").range(off, off+999).execute()
    b = res.data or []
    msgs.extend(b)
    if len(b) < 1000: break
    off += 1000

out = [m for m in msgs if m["direction"]=="outbound"]
# Frecuencia de texto exacto (normalizado: quitar datos variables tipo cedula/correo/monto)
def norm(t):
    t = re.sub(r"\d", "#", t or "")
    t = re.sub(r"\b[\w.+-]+@[\w.-]+", "MAIL", t)
    return t.strip()

freq = Counter(norm(m.get("text")) for m in out)

def is_template(m):
    t = m.get("text") or ""
    mt = m.get("msg_type") or "text"
    if mt in ("interactive","template","button") or t.startswith("[Template") or t.startswith("[Menu"):
        return True
    if t.startswith("👨"):  # asesor
        return False
    # plantilla = texto normalizado que se repite mucho
    return freq[norm(t)] >= 4

def is_asesor(m):
    return (m.get("text") or "").startswith("👨")

llm = [m for m in out if not is_template(m) and not is_asesor(m) and (m.get("msg_type") or "text")=="text"]
# quitar notificaciones internas a admin (Aviso de Soporte / 🚨)
llm = [m for m in llm if "Aviso de Soporte" not in (m.get("text") or "") and not (m.get("text") or "").startswith("🚨")]
# quitar salidas estructuradas de consulta (estado/saldo/no encontrado/correo/contrato)
STRUCT = ("🔍","💰","❌","📧","✅","📄","🚨")
llm = [m for m in llm if not (m.get("text") or "").lstrip().startswith(STRUCT)]

print(f"Corpus LLM aislado (texto único): {len(llm)} mensajes")

pat = {
  "emoji": r"[\U0001F300-\U0001FAFF☀-➿]",
  "negrilla_asterisco": r"\*[^*\n]+\*",
  "signo_apertura": r"[¿¡]",
  "promesa_tiempo": r"(mañana|24 horas|48 horas|hoy mismo|en el transcurso|en breve|antes de las|durante el d[ií]a|en unos minutos)",
  "tasa_especifica": r"\d+(\.\d+)?\s*%",
  "admite_ia": r"(?i)(soy una? (ia|inteligencia|bot|asistente virtual)|modelo de lenguaje|no soy human)",
  "tag_filtrado": r"\[(REGISTRAR|HABLAR|MOSTRAR)",
  "no_puedo": r"(?i)(no tengo esa info|no puedo ayudart|no puedo con eso|no manejo esa)",
  "callejon": r"(?i)^(perfecto[,.]? )?(d[eé]jame (revisar|verificar|consultar)|voy a (revisar|consultar)|dame un momento)[\s.!]*$",
}
counts = {k:0 for k in pat}
ex = defaultdict(list)
for m in llm:
    t = m.get("text") or ""
    for k,rx in pat.items():
        if re.search(rx,t):
            counts[k]+=1
            if len(ex[k])<6: ex[k].append((m["phone"][-4:], t[:200].replace("\n"," ")))

print(f"\n=== FALLOS EN CORPUS LLM REAL (n={len(llm)}) ===")
for k in pat:
    print(f"  {k}: {counts[k]} ({100*counts[k]/max(len(llm),1):.1f}%)")
    for ph,e in ex[k][:4]:
        print(f"      [{ph}] {e}")

print("\n=== MUESTRA ALEATORIA DE 40 MENSAJES LLM CONVERSACIONALES ===")
random.seed(7)
for m in random.sample(llm, min(40,len(llm))):
    print(f"  [{m['phone'][-4:]}] {(m.get('text') or '')[:220].replace(chr(10),' ')}")

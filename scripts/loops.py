"""Caracteriza los loops de repetición: ¿el cliente repite porque el bot falla,
o porque espera a un asesor humano que no responde?"""
import os, re
from collections import defaultdict, Counter
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
START, END = "2026-06-01T00:00:00", "2026-06-07T23:59:59"
msgs=[]; off=0
while True:
    r=client.table("bot_messages").select("phone,direction,text,msg_type,created_at").gte("created_at",START).lte("created_at",END).order("created_at").range(off,off+999).execute()
    b=r.data or []; msgs.extend(b)
    if len(b)<1000: break
    off+=1000
by=defaultdict(list)
for m in msgs: by[m["phone"]].append(m)

# estados
status={}
ph=list(by.keys())
for i in range(0,len(ph),100):
    c=client.table("bot_conversations").select("phone,status").in_("phone",ph[i:i+100]).execute()
    for r in (c.data or []): status[r["phone"]]=r.get("status")

loop_phones=[]
for p,ms in by.items():
    ti=[(m.get("text") or "").strip().lower() for m in ms if m["direction"]=="inbound" and (m.get("msg_type") or "text")=="text"]
    cc=Counter(ti)
    if any(n>=3 and len(t)>1 for t,n in cc.items()):
        loop_phones.append(p)

# Para cada loop: ¿estado agent? ¿hubo respuesta de asesor? ¿gap maximo cliente sin respuesta?
agent_wait=0; bot_fail=0; other=0
for p in loop_phones:
    ms=sorted(by[p],key=lambda m:m["created_at"])
    has_asesor=any((m.get("text") or "").startswith("👨") for m in ms)
    st=status.get(p,"")
    if st in ("agent","agent_silent") or has_asesor:
        agent_wait+=1
    else:
        # ¿el bot respondió algo entre las repeticiones? si sí, no es fallo de no-respuesta
        other+=1

print(f"Conversaciones con loop de repetición: {len(loop_phones)}")
print(f"  - En estado agent / con asesor (cliente espera humano): {agent_wait}")
print(f"  - Solo-bot (posible fallo de resolución): {other}")

# Mostrar 6 ejemplos solo-bot para inspección
print("\n=== EJEMPLOS SOLO-BOT CON LOOP ===")
shown=0
for p in loop_phones:
    if status.get(p,"") in ("agent","agent_silent"): continue
    ms=sorted(by[p],key=lambda m:m["created_at"])
    if any((m.get("text") or "").startswith("👨") for m in ms): continue
    print(f"\n--- {p[-4:]} estado={status.get(p,'')} ---")
    for m in ms[:18]:
        d="CLI" if m["direction"]=="inbound" else "BOT"
        print(f"  {m['created_at'][11:16]} {d}: {(m.get('text') or '')[:90].replace(chr(10),' ')}")
    shown+=1
    if shown>=6: break

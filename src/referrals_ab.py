"""
Referral A/B campaign tracking.

This module keeps the experiment state outside the conversational flow:
variant assignment, normalized events, captured referrals and metrics. The
regular bot_messages table remains the full transcript; these tables add a
campaign-specific index that makes later analysis much easier.
"""
import random
import re
import unicodedata
from datetime import datetime

from src import test_mode


CAMPAIGN_ID = "referidos_ab_2026_06"

STATE_NOTIFIED = "referidos_ab_notified"
STATE_INFO_SENT = "referidos_ab_info_sent"
STATE_WAITING_NAME = "referido_waiting_name"
STATE_WAITING_PHONE_PREFIX = "referido_waiting_phone|"

CONTACT_NUMBER = "3203454201"

VARIANTS = {
    "discount_rate": {
        "label": "Descuento en tasa",
        "template_name": "plantilla_referidos_v1",
    },
    "express_approval": {
        "label": "Aprobacion express",
        "template_name": "plantilla_referidos_v2",
    },
}

TEMPLATE_TO_VARIANT = {
    cfg["template_name"]: key for key, cfg in VARIANTS.items()
}

INFO_TEXT_PREFIX = (
    "¡Es muy sencillo! Solo debes seguir estos 2 pasos:\n\n"
    f"1️⃣ Comparte nuestro contacto: Pásale este número {CONTACT_NUMBER} a tus "
    "compañeros de trabajo.\n\n"
    "2️⃣ Asegura tu beneficio: Escríbenos por este medio y dinos el nombre "
    "completo del compañero al que referiste.\n\n"
)

INFO_BENEFIT_TEXT_BY_VARIANT = {
    "discount_rate": (
        "¡Y listo! Si la persona que nos dijiste hace su solicitud, "
        "automáticamente tendrás el descuento en la tasa para tu próximo crédito. 🚀"
    ),
    "express_approval": (
        "¡Y listo! Si la persona que nos dijiste hace su solicitud, "
        "automáticamente tu próximo crédito tendrá aprobación prioritaria en menos de 3 horas. 🚀"
    ),
}

INFO_TEXT = INFO_TEXT_PREFIX + INFO_BENEFIT_TEXT_BY_VARIANT["discount_rate"]

LATER_TEXT = (
    "Recuerda que si más adelante necesitas un nuevo crédito y quieres aprovechar "
    "un buen descuento en tu tasa, solo debes compartir nuestro número con un "
    "colega y avisarnos. ¡Que tengas un excelente día! 👋"
)

ASK_NAME_TEXT = (
    "¡Perfecto! Para activar el beneficio, escríbenos el nombre completo del "
    "compañero al que quieres referir."
)

ASK_PHONE_TEXT = (
    "Gracias. Ahora envíanos el número de WhatsApp o celular de esa persona "
    "(solo números, con o sin 57)."
)

THANKS_TEXT_BY_VARIANT = {
    "discount_rate": (
        "¡Listo! Registramos tu referido. Si esa persona hace su solicitud, "
        "automáticamente tendrás el descuento en la tasa para tu próximo crédito. 🚀"
    ),
    "express_approval": (
        "¡Listo! Registramos tu referido. Si esa persona hace su solicitud, "
        "automáticamente tu próximo crédito tendrá aprobación prioritaria en menos de 3 horas. 🚀"
    ),
}

THANKS_TEXT = THANKS_TEXT_BY_VARIANT["discount_rate"]


def _now_iso() -> str:
    return datetime.now().isoformat()


def _supabase():
    from src import conversation_log
    return conversation_log.supabase_client


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_recipient_phone(value: str) -> str:
    digits = "".join(filter(str.isdigit, str(value or "")))
    if digits and not digits.startswith("57"):
        digits = f"57{digits}"
    return digits


def normalize_referred_phone(value: str) -> str:
    digits = "".join(filter(str.isdigit, str(value or "")))
    if len(digits) == 10 and not digits.startswith("57"):
        digits = f"57{digits}"
    return digits


def is_valid_referred_phone(value: str) -> bool:
    digits = normalize_referred_phone(value)
    return digits.startswith("57") and len(digits) >= 12


def clean_referred_name(value: str) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    return name.replace("|", " ")[:140]


def is_valid_referred_name(value: str) -> bool:
    name = clean_referred_name(value)
    return len(name) >= 5 and len(name.split()) >= 2


def is_referral_prompt_state(state: str) -> bool:
    return state in (STATE_NOTIFIED, STATE_INFO_SENT)


def is_waiting_name_state(state: str) -> bool:
    return state == STATE_WAITING_NAME


def is_waiting_phone_state(state: str) -> bool:
    return str(state or "").startswith(STATE_WAITING_PHONE_PREFIX)


def is_referral_state(state: str) -> bool:
    return (
        is_referral_prompt_state(state)
        or is_waiting_name_state(state)
        or is_waiting_phone_state(state)
    )


def button_kind(btn_id: str) -> str | None:
    norm = _normalize_text(btn_id)
    if not norm:
        return None

    info_aliases = {"como funciona", "referidos como funciona", "referidos info"}
    later_aliases = {
        "quizas despues",
        "referidos quizas despues",
        "referidos despues",
        "referral later",
    }
    benefit_aliases = {
        "quiero el beneficio",
        "referidos quiero beneficio",
        "referidos beneficio",
        "referral want benefit",
    }

    if norm in info_aliases or ("como" in norm and "funciona" in norm):
        return "info"
    if norm in later_aliases or ("quizas" in norm and "despues" in norm):
        return "later"
    if norm in benefit_aliases or ("quiero" in norm and "beneficio" in norm):
        return "benefit"
    return None


def text_intent(text: str) -> str | None:
    norm = _normalize_text(text)
    if not norm:
        return None
    if "quiero" in norm and ("beneficio" in norm or "refer" in norm):
        return "benefit"
    if "beneficio" in norm or "referir" in norm or "referido" in norm:
        return "benefit"
    if "despues" in norm or "luego" in norm:
        return "later"
    if "como" in norm and "funciona" in norm:
        return "info"
    return None


def variant_for_template(template_name: str) -> str | None:
    return TEMPLATE_TO_VARIANT.get(template_name)


def variant_for_last_template(phone: str) -> str | None:
    try:
        from src import conversation_log
        return variant_for_template(conversation_log.get_last_campaign_template(phone) or "")
    except Exception as e:
        print(f"Could not resolve referral variant from last template: {e}")
        return None


def variant_for_phone(phone: str) -> str:
    if test_mode.is_test_phone(phone):
        return variant_for_template(test_mode.get_last_template(phone) or "") or "discount_rate"

    template_variant = variant_for_last_template(phone)
    if template_variant in VARIANTS:
        return template_variant

    assignment = get_assignment(phone) or {}
    return assignment.get("variant_key") or "discount_rate"


def info_text_for_phone(phone: str) -> str:
    variant_key = variant_for_phone(phone)
    benefit_text = INFO_BENEFIT_TEXT_BY_VARIANT.get(
        variant_key,
        INFO_BENEFIT_TEXT_BY_VARIANT["discount_rate"],
    )
    return INFO_TEXT_PREFIX + benefit_text


def thanks_text_for_phone(phone: str) -> str:
    variant_key = variant_for_phone(phone)
    return THANKS_TEXT_BY_VARIANT.get(
        variant_key,
        THANKS_TEXT_BY_VARIANT["discount_rate"],
    )


def balanced_variant_keys(count: int) -> list[str]:
    """Return a randomized, near 50/50 list of variant keys for a batch."""
    keys = list(VARIANTS.keys())
    if count <= 0:
        return []
    half = count // 2
    if count % 2:
        extra = random.choice(keys)
        counts = {keys[0]: half, keys[1]: half}
        counts[extra] += 1
    else:
        counts = {keys[0]: half, keys[1]: half}
    assignments = [keys[0]] * counts[keys[0]] + [keys[1]] * counts[keys[1]]
    random.shuffle(assignments)
    return assignments


def get_assignment(phone: str, campaign_id: str = CAMPAIGN_ID) -> dict | None:
    if test_mode.is_test_phone(phone):
        return None
    client = _supabase()
    if not client:
        return None
    phones = [str(phone or "")]
    normalized = normalize_recipient_phone(phone)
    if normalized and normalized not in phones:
        phones.append(normalized)
    try:
        for candidate in phones:
            if not candidate:
                continue
            res = (client.table("referral_ab_assignments")
                   .select("*")
                   .eq("campaign_id", campaign_id)
                   .eq("phone", candidate)
                   .order("sent_at", desc=True)
                   .limit(1)
                   .execute())
            if res.data:
                return res.data[0]
        return None
    except Exception as e:
        print(f"Supabase get_referral_assignment error: {e}")
        return None


def record_event(phone: str, event_type: str, event_text: str = "",
                 metadata: dict | None = None, variant_key: str = None,
                 campaign_id: str = CAMPAIGN_ID) -> bool:
    if test_mode.is_test_phone(phone):
        return True
    client = _supabase()
    if not client:
        return False
    try:
        variant = variant_key or variant_for_phone(phone)
        client.table("referral_ab_events").insert({
            "campaign_id": campaign_id,
            "phone": phone,
            "variant_key": variant,
            "event_type": event_type,
            "event_text": event_text or "",
            "metadata": metadata or {},
            "created_at": _now_iso(),
        }).execute()
        return True
    except Exception as e:
        print(f"Supabase record_referral_event error: {e}")
        return False


def register_template_attempt(phone: str, client_name: str, variant_key: str,
                              status: str, wamid: str = None,
                              error_message: str = None,
                              campaign_id: str = CAMPAIGN_ID) -> bool:
    if test_mode.is_test_phone(phone):
        return True
    client = _supabase()
    if not client:
        return False
    cfg = VARIANTS.get(variant_key)
    if not cfg:
        return False
    now = _now_iso()
    try:
        client.table("referral_ab_assignments").upsert({
            "campaign_id": campaign_id,
            "phone": phone,
            "client_name": client_name or "Cliente",
            "variant_key": variant_key,
            "variant_label": cfg["label"],
            "template_name": cfg["template_name"],
            "send_status": status,
            "wamid": wamid,
            "sent_at": now,
            "error_message": error_message,
            "updated_at": now,
        }, on_conflict="campaign_id,phone").execute()
        record_event(
            phone,
            "sent" if status == "accepted" else "send_failed",
            cfg["template_name"],
            {
                "template_name": cfg["template_name"],
                "send_status": status,
                "wamid": wamid,
                "error_message": error_message,
            },
            variant_key=variant_key,
            campaign_id=campaign_id,
        )
        return True
    except Exception as e:
        print(f"Supabase register_referral_template_attempt error: {e}")
        return False


def record_button_click(phone: str, btn_id: str, kind: str = None) -> bool:
    kind = kind or button_kind(btn_id) or "unknown"
    return record_event(phone, "button_click", btn_id, {"button_kind": kind})


def save_referral_name(referrer_phone: str, referrer_name: str,
                       referred_name: str) -> bool:
    referred_name = clean_referred_name(referred_name)
    if test_mode.is_test_phone(referrer_phone):
        return True
    client = _supabase()
    if not client:
        return False
    assignment = get_assignment(referrer_phone) or {}
    variant_key = variant_for_phone(referrer_phone)
    now = _now_iso()
    try:
        pending = (client.table("referral_ab_referrals")
                   .select("id")
                   .eq("campaign_id", CAMPAIGN_ID)
                   .eq("referrer_phone", referrer_phone)
                   .eq("status", "awaiting_phone")
                   .order("created_at", desc=True)
                   .limit(1)
                   .execute())
        data = {
            "referrer_name": referrer_name or assignment.get("client_name") or "Cliente",
            "variant_key": variant_key,
            "referred_name": referred_name,
            "status": "awaiting_phone",
            "updated_at": now,
        }
        if pending.data:
            client.table("referral_ab_referrals").update(data).eq("id", pending.data[0]["id"]).execute()
        else:
            data.update({
                "campaign_id": CAMPAIGN_ID,
                "referrer_phone": referrer_phone,
                "created_at": now,
            })
            client.table("referral_ab_referrals").insert(data).execute()

        record_event(
            referrer_phone,
            "referral_name",
            referred_name,
            {"referred_name": referred_name},
            variant_key=variant_key,
        )
        return True
    except Exception as e:
        print(f"Supabase save_referral_name error: {e}")
        return False


def complete_referral(referrer_phone: str, referrer_name: str,
                      referred_name: str, referred_phone: str) -> bool:
    referred_name = clean_referred_name(referred_name)
    referred_phone = normalize_referred_phone(referred_phone)
    if test_mode.is_test_phone(referrer_phone):
        return True
    client = _supabase()
    if not client:
        return False
    assignment = get_assignment(referrer_phone) or {}
    variant_key = variant_for_phone(referrer_phone)
    now = _now_iso()
    try:
        pending = (client.table("referral_ab_referrals")
                   .select("id")
                   .eq("campaign_id", CAMPAIGN_ID)
                   .eq("referrer_phone", referrer_phone)
                   .eq("status", "awaiting_phone")
                   .order("created_at", desc=True)
                   .limit(1)
                   .execute())
        data = {
            "referrer_name": referrer_name or assignment.get("client_name") or "Cliente",
            "variant_key": variant_key,
            "referred_name": referred_name,
            "referred_phone": referred_phone,
            "status": "completed",
            "updated_at": now,
        }
        if pending.data:
            client.table("referral_ab_referrals").update(data).eq("id", pending.data[0]["id"]).execute()
        else:
            data.update({
                "campaign_id": CAMPAIGN_ID,
                "referrer_phone": referrer_phone,
                "created_at": now,
            })
            client.table("referral_ab_referrals").insert(data).execute()

        record_event(
            referrer_phone,
            "referral_phone",
            referred_phone,
            {"referred_name": referred_name, "referred_phone": referred_phone},
            variant_key=variant_key,
        )
        return True
    except Exception as e:
        print(f"Supabase complete_referral error: {e}")
        return False


def _date_bounds(date_from: str = None, date_to: str = None):
    gte = f"{date_from}T00:00:00" if date_from else None
    lte = f"{date_to}T23:59:59" if date_to else None
    return gte, lte


def _parse_dt(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _seconds_between(start: str, end: str) -> float | None:
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    if not start_dt or not end_dt:
        return None
    return max(end_dt.timestamp() - start_dt.timestamp(), 0)


def _avg_minutes(seconds: list[float]) -> float | None:
    values = [s for s in seconds if s is not None]
    if not values:
        return None
    return round((sum(values) / len(values)) / 60, 1)


def _pct(part: int, total: int) -> int:
    return round((part / total) * 100) if total else 0


def _empty_metrics() -> dict:
    variants = []
    for key, cfg in VARIANTS.items():
        variants.append({
            "variant_key": key,
            "variant_label": cfg["label"],
            "template_name": cfg["template_name"],
            "sent": 0,
            "sent_pct": 0,
            "como_funciona_count": 0,
            "quiero_beneficio_count": 0,
            "quizas_despues_count": 0,
            "referral_count": 0,
            "sin_respuesta_count": 0,
            "first_response_avg_minutes": None,
            "info_to_benefit_avg_minutes": None,
            "name_to_phone_avg_minutes": None,
            "referrals_per_contact": 0,
        })
    return {
        "total": 0,
        "variant_a_total": 0,
        "variant_b_total": 0,
        "como_funciona_count": 0,
        "quiero_beneficio_count": 0,
        "quizas_despues_count": 0,
        "referral_count": 0,
        "sin_respuesta_count": 0,
        "referrals_per_contact": 0,
        "first_response_avg_minutes": None,
        "info_to_benefit_avg_minutes": None,
        "name_to_phone_avg_minutes": None,
        "variants": variants,
        "solicitar": [],
    }


def get_metrics(date_from: str = None, date_to: str = None,
                campaign_id: str = CAMPAIGN_ID) -> dict:
    client = _supabase()
    if not client:
        return _empty_metrics()
    try:
        gte, lte = _date_bounds(date_from, date_to)
        q = (client.table("referral_ab_assignments")
             .select("*")
             .eq("campaign_id", campaign_id)
             .eq("send_status", "accepted")
             .order("sent_at", desc=False))
        if gte:
            q = q.gte("sent_at", gte)
        if lte:
            q = q.lte("sent_at", lte)
        assignments = q.execute().data or []

        if not assignments:
            return _empty_metrics()

        phones = [row["phone"] for row in assignments if row.get("phone")]
        events_res = (client.table("referral_ab_events")
                      .select("*")
                      .eq("campaign_id", campaign_id)
                      .in_("phone", phones)
                      .order("created_at", desc=False)
                      .execute())
        referrals_res = (client.table("referral_ab_referrals")
                         .select("*")
                         .eq("campaign_id", campaign_id)
                         .in_("referrer_phone", phones)
                         .eq("status", "completed")
                         .order("created_at", desc=True)
                         .execute())

        events_by_phone: dict[str, list] = {}
        for ev in events_res.data or []:
            events_by_phone.setdefault(ev.get("phone"), []).append(ev)

        referrals_by_phone: dict[str, list] = {}
        for ref in referrals_res.data or []:
            referrals_by_phone.setdefault(ref.get("referrer_phone"), []).append(ref)

        stats = {}
        for key, cfg in VARIANTS.items():
            stats[key] = {
                "variant_key": key,
                "variant_label": cfg["label"],
                "template_name": cfg["template_name"],
                "sent": 0,
                "phones_with_response": set(),
                "info_phones": set(),
                "benefit_phones": set(),
                "later_phones": set(),
                "referral_count": 0,
                "first_response_seconds": [],
                "info_to_benefit_seconds": [],
                "name_to_phone_seconds": [],
            }

        detail_rows = []
        all_first_response = []
        all_info_to_benefit = []
        all_name_to_phone = []

        for row in assignments:
            phone = row["phone"]
            variant = row.get("variant_key") or ""
            if variant not in stats:
                continue
            st = stats[variant]
            st["sent"] += 1
            sent_at = row.get("sent_at") or row.get("created_at")

            first_response_at = None
            info_sent_at = None
            benefit_at = None
            name_at = None
            phone_at = None

            for ev in events_by_phone.get(phone, []):
                if _seconds_between(sent_at, ev.get("created_at")) is None:
                    continue
                ev_type = ev.get("event_type")
                meta = ev.get("metadata") or {}
                kind = meta.get("button_kind") or button_kind(ev.get("event_text", ""))

                if ev_type in ("button_click", "referral_name", "referral_phone", "free_text"):
                    first_response_at = first_response_at or ev.get("created_at")

                if ev_type == "button_click":
                    if kind == "info":
                        st["info_phones"].add(phone)
                    elif kind == "benefit":
                        st["benefit_phones"].add(phone)
                        benefit_at = benefit_at or ev.get("created_at")
                    elif kind == "later":
                        st["later_phones"].add(phone)
                elif ev_type == "info_sent":
                    info_sent_at = info_sent_at or ev.get("created_at")
                elif ev_type == "referral_name":
                    name_at = name_at or ev.get("created_at")
                elif ev_type == "referral_phone":
                    phone_at = phone_at or ev.get("created_at")

            if first_response_at:
                st["phones_with_response"].add(phone)
                secs = _seconds_between(sent_at, first_response_at)
                st["first_response_seconds"].append(secs)
                all_first_response.append(secs)
            if info_sent_at and benefit_at:
                secs = _seconds_between(info_sent_at, benefit_at)
                st["info_to_benefit_seconds"].append(secs)
                all_info_to_benefit.append(secs)
            if name_at and phone_at:
                secs = _seconds_between(name_at, phone_at)
                st["name_to_phone_seconds"].append(secs)
                all_name_to_phone.append(secs)

            completed_refs = referrals_by_phone.get(phone, [])
            st["referral_count"] += len(completed_refs)
            for ref in completed_refs:
                detail_rows.append({
                    "phone": phone,
                    "client_name": row.get("client_name") or ref.get("referrer_name") or "",
                    "variant_key": variant,
                    "variant_label": st["variant_label"],
                    "referred_name": ref.get("referred_name") or "",
                    "referred_phone": ref.get("referred_phone") or "",
                    "responded_at": ref.get("updated_at") or ref.get("created_at"),
                })

        total = sum(st["sent"] for st in stats.values())
        detail_rows.sort(key=lambda x: x.get("responded_at") or "", reverse=True)

        variant_rows = []
        for key in VARIANTS:
            st = stats[key]
            sent = st["sent"]
            variant_rows.append({
                "variant_key": key,
                "variant_label": st["variant_label"],
                "template_name": st["template_name"],
                "sent": sent,
                "sent_pct": _pct(sent, total),
                "como_funciona_count": len(st["info_phones"]),
                "quiero_beneficio_count": len(st["benefit_phones"]),
                "quizas_despues_count": len(st["later_phones"]),
                "referral_count": st["referral_count"],
                "sin_respuesta_count": max(sent - len(st["phones_with_response"]), 0),
                "first_response_avg_minutes": _avg_minutes(st["first_response_seconds"]),
                "info_to_benefit_avg_minutes": _avg_minutes(st["info_to_benefit_seconds"]),
                "name_to_phone_avg_minutes": _avg_minutes(st["name_to_phone_seconds"]),
                "referrals_per_contact": round(st["referral_count"] / sent, 3) if sent else 0,
            })

        info_count = sum(len(st["info_phones"]) for st in stats.values())
        benefit_count = sum(len(st["benefit_phones"]) for st in stats.values())
        later_count = sum(len(st["later_phones"]) for st in stats.values())
        referral_count = sum(st["referral_count"] for st in stats.values())
        no_response = sum(max(st["sent"] - len(st["phones_with_response"]), 0) for st in stats.values())

        keys = list(VARIANTS.keys())
        return {
            "total": total,
            "variant_a_total": stats[keys[0]]["sent"],
            "variant_b_total": stats[keys[1]]["sent"],
            "como_funciona_count": info_count,
            "quiero_beneficio_count": benefit_count,
            "quizas_despues_count": later_count,
            "referral_count": referral_count,
            "sin_respuesta_count": no_response,
            "referrals_per_contact": round(referral_count / total, 3) if total else 0,
            "first_response_avg_minutes": _avg_minutes(all_first_response),
            "info_to_benefit_avg_minutes": _avg_minutes(all_info_to_benefit),
            "name_to_phone_avg_minutes": _avg_minutes(all_name_to_phone),
            "variants": variant_rows,
            "solicitar": detail_rows,
        }
    except Exception as e:
        print(f"Supabase get_referral_ab_metrics error: {e}")
        return _empty_metrics()

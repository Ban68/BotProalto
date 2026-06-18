import re
import time
import atexit
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from src.database import get_aprobados_por_el_cliente, get_falta_documento, get_listo_en_docusign, get_denegado, get_clientes_activos
from src.services import WhatsAppService
from src.conversation_log import (
    get_notified_phones_batch, set_user_state, get_template_stats_batch,
    get_notified_phones_rojo_batch, get_phones_menu_contacted_rojo_batch, get_template_stats_batch_rojo,
    get_undeliverable_phones_batch,
    get_phones_with_email, get_phones_with_docs_completos,
    get_notified_phones_amarillo_batch, get_template_stats_batch_amarillo,
    get_phones_with_cuenta, set_solicitud_context,
    get_notified_phones_denegado_batch, get_template_stats_batch_denegado,
    get_phones_recently_updated, get_phones_with_in_progress_contact_update,
)

# --- TEST MODE CONFIG ---
TEST_MODE = False  # SET TO FALSE BEFORE PRODUCTION
TEST_NUMBER = "573106176713"
# -------------------------

def get_pending_approved_notifications():
    """
    Returns a dict with 'eligible' and 'excluded' lists for 'Aprobado por el cliente' state.
    Excluded users include an 'excluded_reasons' list explaining why they were filtered out.
    """
    if TEST_MODE:
        return {"eligible": [{"phone": TEST_NUMBER, "name": "PROALTO TEST", "monto": 1000000, "plazo": 12, "cuota": 95000, "send_count": 0, "last_sent": None}], "excluded": []}

    aprobados = get_aprobados_por_el_cliente()
    if not aprobados:
        return {"eligible": [], "excluded": []}

    raw_users = []
    phones_to_check = []

    for user in aprobados:
        telefono = user.get("telefono")
        nombre = user.get("nombre_completo", "Cliente")

        # We need a valid phone number
        phone_str = str(telefono).split(".")[0]
        phone_str = "".join(filter(str.isdigit, phone_str))

        if not phone_str:
            continue

        # Ensure country code
        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"

        raw_users.append({
            "phone": phone_str,
            "name": nombre,
            "monto": user.get("valor_preestudiado", 0),
            "plazo": user.get("plazo", 0),
            "cuota": user.get("cuota", 0),
            "empresa": user.get("empresa", ""),
        })
        phones_to_check.append(phone_str)

    if not phones_to_check:
        return {"eligible": [], "excluded": []}

    # SINGLE query to Supabase for all phones
    notified_today = get_notified_phones_batch(phones_to_check)
    already_emailed = get_phones_with_email(phones_to_check)

    # Separate eligible from excluded, capturing the reason for each exclusion
    eligible_users = []
    excluded_users = []
    for u in raw_users:
        reasons = []
        if u["phone"] in notified_today:
            reasons.append("Ya notificado hoy")
        if u["phone"] in already_emailed:
            reasons.append("Ya envió email")
        if reasons:
            u["excluded_reasons"] = reasons
            excluded_users.append(u)
        else:
            eligible_users.append(u)

    # Enrich eligible with total send count and last send timestamp
    eligible_phones = [u["phone"] for u in eligible_users]
    stats = get_template_stats_batch(eligible_phones)
    for user in eligible_users:
        s = stats.get(user["phone"], {})
        user["send_count"] = s.get("count", 0)
        user["last_sent"] = s.get("last_sent", None)

    # Filter out users who already received 3+ templates (prevent fatigue)
    over_limit = [u for u in eligible_users if u["send_count"] >= 3]
    for u in over_limit:
        u["excluded_reasons"] = ["Límite de 3 envíos alcanzado"]
    excluded_users.extend(over_limit)
    eligible_users = [u for u in eligible_users if u["send_count"] < 3]
    eligible_users.sort(key=lambda u: u["send_count"])

    # Also enrich excluded with stats for context in the UI
    if excluded_users:
        excl_phones = [u["phone"] for u in excluded_users]
        excl_stats = get_template_stats_batch(excl_phones)
        for user in excluded_users:
            s = excl_stats.get(user["phone"], {})
            user["send_count"] = s.get("count", 0)
            user["last_sent"] = s.get("last_sent", None)

    return {"eligible": eligible_users, "excluded": excluded_users}

def execute_bulk_approved_notifications(users_list):
    """
    Sends the 'estado_verde' template to a list of users.
    Returns summary of results.
    """
    results = {"total": len(users_list), "success": 0, "fail": 0, "errors": []}
    
    for user in users_list:
        phone_str = user.get("phone")
        nombre = user.get("name")
        
        if not phone_str:
            continue
            
        # Format monto and plazo for better presentation
        monto_val = user.get("monto", 0)
        # Colombia style: dot as thousand separator
        if isinstance(monto_val, (int, float)):
            monto_format = f"${monto_val:,.0f}".replace(",", ".")
        else:
            monto_format = str(monto_val)
        
        plazo_val = user.get("plazo", 0)
        plazo_format = f"{plazo_val} cuotas"

        cuota_val = user.get("cuota", 0)
        if isinstance(cuota_val, (int, float)):
            cuota_format = f"${cuota_val:,.0f}".replace(",", ".")
        else:
            cuota_format = str(cuota_val)

        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "text": nombre,
                        "parameter_name": "nombre"
                    },
                    {
                        "type": "text",
                        "text": monto_format,
                        "parameter_name": "monto"
                    },
                    {
                        "type": "text",
                        "text": plazo_format,
                        "parameter_name": "plazo"
                    },
                    {
                        "type": "text",
                        "text": cuota_format,
                        "parameter_name": "cuota"
                    }
                ]
            }
        ]
        
        response = WhatsAppService.send_template(phone_str, "estado_verde", components=components)
        
        # Check if response is truthy AND contains a messages array or message_id indicating success
        if response and response.get('messages'):
            # Only update state if Meta successfully accepted the message
            set_user_state(phone_str, "waiting_for_email")
            from src.conversation_log import set_client_name
            set_client_name(phone_str, nombre)
            
            results["success"] += 1
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")
            
    return results

def execute_bulk_leads_notifications(users_list):
    """
    Sends the 'contacto_leads' template to a list of leads.
    Returns summary of results.
    """
    results = {"total": len(users_list), "success": 0, "fail": 0, "errors": []}
    
    for user in users_list:
        phone_str = str(user.get("phone", "")).strip()
        # Clean phone number
        phone_str = "".join(filter(str.isdigit, phone_str))
        if not phone_str:
            continue
            
        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"

        nombre = user.get("name", "Cliente").strip()
        
        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text", 
                        "text": nombre,
                        "parameter_name": "nombre"
                    }
                ]
            }
        ]
        
        response = WhatsAppService.send_template(phone_str, "contacto_leads", components=components)
        
        if response and response.get('messages'):
            results["success"] += 1
            set_user_state(phone_str, "lead_notified")

            # Store lead name for dashboard display
            from src.conversation_log import log_message, set_client_name
            set_client_name(phone_str, nombre)
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")
            
    return results

def execute_bulk_anticipos_notifications(users_list, force=False):
    """
    Sends the 'anticipo_salario' template to a list of payroll advance leads.
    Skips phones that previously clicked 'Ahora no, gracias', unless force=True,
    in which case the template is sent to everyone (including those who already
    indicated they were not interested).
    Returns summary of results.
    """
    from src.conversation_log import set_client_name, log_anticipo_sent, get_anticipo_no_gracias_phones

    results = {"total": len(users_list), "success": 0, "fail": 0, "skipped": 0, "errors": []}

    # Collect all phones to batch-check no_gracias exclusions
    all_phones = []
    cleaned_users = []
    for user in users_list:
        phone_str = str(user.get("phone", "")).strip()
        phone_str = "".join(filter(str.isdigit, phone_str))
        if not phone_str:
            continue
        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"
        all_phones.append(phone_str)
        cleaned_users.append({**user, "_phone": phone_str})

    # When force=True the admin chose to re-send to everyone, so skip the lookup.
    no_gracias_phones = set() if force else get_anticipo_no_gracias_phones(all_phones)

    for user in cleaned_users:
        phone_str = user["_phone"]
        nombre = user.get("name", "Cliente").strip()

        if phone_str in no_gracias_phones:
            results["skipped"] += 1
            results["errors"].append(f"{phone_str}: omitido (ya indicó que no está interesado)")
            continue

        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "text": nombre,
                        "parameter_name": "nombre"
                    }
                ]
            }
        ]

        response = WhatsAppService.send_template(phone_str, "anticipo_salario", components=components)

        if response and response.get('messages'):
            results["success"] += 1
            set_user_state(phone_str, "anticipos_notified")
            set_client_name(phone_str, nombre)
            log_anticipo_sent(phone_str, nombre)
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")

    return results

def execute_bulk_renovados_notifications(users_list):
    """
    Sends the 'contacto_renovados' template to a list of renewal candidates.
    Returns summary of results.
    """
    results = {"total": len(users_list), "success": 0, "fail": 0, "errors": []}

    for user in users_list:
        phone_str = str(user.get("phone", "")).strip()
        phone_str = "".join(filter(str.isdigit, phone_str))
        if not phone_str:
            continue

        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"

        nombre = user.get("name", "Cliente").strip()

        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "text": nombre,
                        "parameter_name": "nombre"
                    }
                ]
            }
        ]

        response = WhatsAppService.send_template(phone_str, "estado_renovar", components=components)

        if response and response.get('messages'):
            results["success"] += 1
            set_user_state(phone_str, "renovado_notified")

            from src.conversation_log import set_client_name
            set_client_name(phone_str, nombre)
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")

    return results

REQUIRED_DOCUMENTS = [
    "2 últimos desprendibles de pago de nómina",
    "Certificado laboral vigente",
    "Foto de cédula (ambos lados)",
    "Recibo de servicio público reciente (agua, luz, gas o telefonía)"
]

# Mapeo de nombres exactos (tal como vienen del software) → texto WhatsApp
# Los valores se comparan en MAYÚSCULAS para ser tolerantes a variaciones de capitalización
_DOC_LABEL_MAP_EMPRESA = {
    "CERTIFICADO LABORAL":                          "📄 Certificado laboral",
    "CERTIFICADO DE DEUDA":                         "📄 Certificado de Deuda",
    "FECHA DE INGRESO A LA EMPRESA":                "📅 Fecha de ingreso a la empresa",
    "RECIBO PÚBLICO":                               "🏠 Recibo público (agua, luz, gas, telefonía)",
    "RECIBO PUBLICO":                               "🏠 Recibo público (agua, luz, gas, telefonía)",
    # Nombres reales usados en el software
    "FOTOCOPIA DE CÉDULA":                          "🪪 Foto de tu cédula (ambos lados)",
    "FOTOCOPIA DE CEDULA":                          "🪪 Foto de tu cédula (ambos lados)",
    "FOTO DE CÉDULA":                               "🪪 Foto de tu cédula (ambos lados)",
    "FOTO DE CEDULA":                               "🪪 Foto de tu cédula (ambos lados)",
    "2 ÚLTIMOS DESPRENDIBLES":                      "📄 2 últimos desprendibles de pago de nómina",
    "2 ULTIMOS DESPRENDIBLES":                      "📄 2 últimos desprendibles de pago de nómina",
    "2 ÚLTIMOS DESPRENDIBLES DE PAGO DE NÓMINA":   "📄 2 últimos desprendibles de pago de nómina",
    "2 ULTIMOS DESPRENDIBLES DE PAGO DE NOMINA":   "📄 2 últimos desprendibles de pago de nómina",
    "DESPRENDIBLES DE PAGO":                        "📄 2 últimos desprendibles de pago de nómina",
    "CODEUDOR":                                     "👥 Documentación del codeudor",
}

# Para finca/rural no aplica certificado laboral
_DOC_LABEL_MAP_FINCA = {
    "CERTIFICADO DE DEUDA":                         "📄 Certificado de Deuda",
    "FECHA DE INGRESO A LA EMPRESA":                "📅 Fecha de ingreso a la empresa",
    "RECIBO PÚBLICO":                               "🏠 Recibo público",
    "RECIBO PUBLICO":                               "🏠 Recibo público",
    "FOTOCOPIA DE CÉDULA":                          "🪪 Foto de tu cédula (ambos lados)",
    "FOTOCOPIA DE CEDULA":                          "🪪 Foto de tu cédula (ambos lados)",
    "FOTO DE CÉDULA":                               "🪪 Foto de tu cédula (ambos lados)",
    "FOTO DE CEDULA":                               "🪪 Foto de tu cédula (ambos lados)",
    "2 ÚLTIMOS DESPRENDIBLES":                      "📄 2 últimos desprendibles de pago de nómina",
    "2 ULTIMOS DESPRENDIBLES":                      "📄 2 últimos desprendibles de pago de nómina",
    "CODEUDOR":                                     "👥 Documentación del codeudor",
}

# Lista completa enviada cuando se selecciona "Todos los documentos" o el campo está vacío
_ALL_DOCS_EMPRESA = [
    "📄 2 últimos desprendibles de pago de nómina",
    "📄 Certificado laboral",
    "🪪 Foto de tu cédula (ambos lados)",
    "🏠 Recibo público (agua, luz, gas, telefonía)",
]

_ALL_DOCS_FINCA = [
    "📄 2 últimos desprendibles de pago de nómina",
    "🪪 Foto de tu cédula (ambos lados)",
    "🏠 Recibo público",
]


def build_docs_message(docs_faltantes: str, tipo_empleador: str) -> str:
    """
    Builds the personalized document list message for a client.

    docs_faltantes: nombres de documentos separados por ';' o ','
                    (e.g. 'Certificado de Deuda;Certificado Laboral' o
                    'Recibo público, 2 últimos desprendibles, Fotocopia de cédula'),
                    'Todos los documentos', o vacío/None para enviar la lista completa.
    tipo_empleador: 'EMPRESA' (default) o 'FINCA'
    """
    is_finca = (tipo_empleador or "EMPRESA").upper() == "FINCA"
    doc_map  = _DOC_LABEL_MAP_FINCA if is_finca else _DOC_LABEL_MAP_EMPRESA
    all_docs = _ALL_DOCS_FINCA if is_finca else _ALL_DOCS_EMPRESA

    # Normalizar: puede llegar como lista (PostgreSQL TEXT[]) o como string
    # separado por ';' o ',' (la vista v_solicitudes_whatsapp usa coma).
    if isinstance(docs_faltantes, list):
        items = [item.strip() for item in docs_faltantes if item and item.strip()]
    else:
        items = [item.strip() for item in re.split(r"[;,]", docs_faltantes or "") if item.strip()]

    # Marca si la solicitud pide la lista completa ("Todos los documentos",
    # campo vacío, o nombres no reconocidos): en ese caso recordamos el
    # certificado de saldo para quienes tengan una libranza activa.
    es_todos = not items or any("TODOS" in item.upper() for item in items)
    if es_todos:
        selected = all_docs
    else:
        selected = [doc_map[item.upper()] for item in items if item.upper() in doc_map]
        if not selected:
            selected = all_docs  # fallback si ningún nombre coincide
            es_todos = True

    doc_list = "\n".join(selected)
    nota_libranza = (
        "\n\n⚠️ *Ten en cuenta:* si tienes un préstamo de libranza activo es "
        "obligatorio que nos envíes el certificado de saldo para poder revisar tu solicitud."
        if es_todos else ""
    )
    return (
        "Para agilizar tu proceso, necesitamos que nos envíes:\n\n"
        f"{doc_list}\n\n"
        "Puedes enviárnoslos directamente aquí por WhatsApp (foto o PDF)."
        f"{nota_libranza}"
    )


def get_pending_falta_documento_notifications():
    """
    Returns a dict with 'eligible' and 'excluded' lists for 'Falta algún documento' state.
    Excluded users include an 'excluded_reasons' list explaining why they were filtered out.
    """
    if TEST_MODE:
        return {"eligible": [{"phone": TEST_NUMBER, "name": "PROALTO TEST", "send_count": 0, "last_sent": None}], "excluded": []}

    clientes = get_falta_documento()
    if not clientes:
        return {"eligible": [], "excluded": []}

    raw_users = []
    phones_to_check = []

    for user in clientes:
        telefono = user.get("telefono")
        nombre = user.get("nombre_completo", "Cliente")

        phone_str = str(telefono).split(".")[0]
        phone_str = "".join(filter(str.isdigit, phone_str))

        if not phone_str:
            continue

        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"

        raw_users.append({
            "phone": phone_str,
            "name": nombre,
            "empresa": user.get("empresa", ""),
            "docs_faltantes": user.get("documentos_faltantes", ""),
            "tipo_empleador": user.get("tipo_empleador", "EMPRESA"),
        })
        phones_to_check.append(phone_str)

    if not phones_to_check:
        return {"eligible": [], "excluded": []}

    notified_today = get_notified_phones_rojo_batch(phones_to_check)
    menu_contacted_today = get_phones_menu_contacted_rojo_batch(phones_to_check)
    docs_completos = get_phones_with_docs_completos(phones_to_check)
    undeliverable = get_undeliverable_phones_batch(phones_to_check)

    # Separate eligible from excluded, capturing the reason for each exclusion
    eligible_users = []
    excluded_users = []
    for u in raw_users:
        reasons = []
        if u["phone"] in notified_today:
            reasons.append("Template enviado hoy (masivo)")
        if u["phone"] in menu_contacted_today:
            reasons.append("Consultó su estado hoy por el bot")
        if u["phone"] in docs_completos:
            reasons.append("Docs marcados como completos")
        if u["phone"] in undeliverable:
            reasons.append("Número no entregable (sin WhatsApp / código 131026)")
        if reasons:
            u["excluded_reasons"] = reasons
            excluded_users.append(u)
        else:
            eligible_users.append(u)

    eligible_phones = [u["phone"] for u in eligible_users]
    stats = get_template_stats_batch_rojo(eligible_phones)
    for user in eligible_users:
        s = stats.get(user["phone"], {})
        user["send_count"] = s.get("count", 0)
        user["last_sent"] = s.get("last_sent", None)

    # Filter out users who already received 3+ templates (prevent fatigue)
    over_limit = [u for u in eligible_users if u["send_count"] >= 3]
    for u in over_limit:
        u["excluded_reasons"] = ["Límite de 3 envíos alcanzado"]
    excluded_users.extend(over_limit)
    eligible_users = [u for u in eligible_users if u["send_count"] < 3]

    # Also enrich excluded with stats for context in the UI
    if excluded_users:
        excl_phones = [u["phone"] for u in excluded_users]
        excl_stats = get_template_stats_batch_rojo(excl_phones)
        for user in excluded_users:
            s = excl_stats.get(user["phone"], {})
            user["send_count"] = s.get("count", 0)
            user["last_sent"] = s.get("last_sent", None)

    return {"eligible": eligible_users, "excluded": excluded_users}


def execute_bulk_falta_documento_notifications(users_list):
    """
    Sends the 'estado_rojo' template to a list of users with missing documents.
    Returns summary of results.
    """
    results = {"total": len(users_list), "success": 0, "fail": 0, "skipped": 0, "errors": []}

    # Defensa: no reenviar a números ya marcados como no entregables (131026).
    # Meta acepta el envío (devuelve wamid) pero la entrega falla segundos después
    # vía webhook, así que el conteo de "éxito" sería engañoso y solo genera fatiga.
    all_phones = [u.get("phone") for u in users_list if u.get("phone")]
    undeliverable = get_undeliverable_phones_batch(all_phones)

    for user in users_list:
        phone_str = user.get("phone")
        nombre = user.get("name")

        if not phone_str:
            continue

        if phone_str in undeliverable:
            results["skipped"] += 1
            results["errors"].append(f"{phone_str}: omitido (no entregable, código 131026)")
            continue

        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "text": nombre,
                        "parameter_name": "nombre"
                    }
                ]
            }
        ]

        response = WhatsAppService.send_template(phone_str, "estado_rojo", components=components)

        if response and response.get('messages'):
            set_user_state(phone_str, "waiting_for_docs_rojo")
            from src.conversation_log import set_client_name
            set_client_name(phone_str, nombre)
            set_solicitud_context(
                phone_str,
                user.get("empresa", ""),
                user.get("docs_faltantes", ""),
                user.get("tipo_empleador", "EMPRESA"),
            )
            results["success"] += 1
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")

    return results


def get_pending_listo_docusign_notifications():
    """
    Returns a dict with 'eligible' and 'excluded' lists for 'Listo en DocuSign' state.
    Excluded users include an 'excluded_reasons' list explaining why they were filtered out.
    """
    if TEST_MODE:
        return {"eligible": [{"phone": TEST_NUMBER, "name": "PROALTO TEST", "send_count": 0, "last_sent": None}], "excluded": []}

    clientes = get_listo_en_docusign()
    if not clientes:
        return {"eligible": [], "excluded": []}

    raw_users = []
    phones_to_check = []

    for user in clientes:
        telefono = user.get("telefono")
        nombre = user.get("nombre_completo", "Cliente")

        phone_str = str(telefono).split(".")[0]
        phone_str = "".join(filter(str.isdigit, phone_str))

        if not phone_str:
            continue

        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"

        raw_users.append({
            "phone": phone_str,
            "name": nombre,
            "empresa": user.get("empresa", ""),
        })
        phones_to_check.append(phone_str)

    if not phones_to_check:
        return {"eligible": [], "excluded": []}

    notified_today = get_notified_phones_amarillo_batch(phones_to_check)
    already_cuenta = get_phones_with_cuenta(phones_to_check)

    # Separate eligible from excluded, capturing the reason for each exclusion
    eligible_users = []
    excluded_users = []
    for u in raw_users:
        reasons = []
        if u["phone"] in notified_today:
            reasons.append("Ya notificado hoy")
        if u["phone"] in already_cuenta:
            reasons.append("Ya envió número de cuenta")
        if reasons:
            u["excluded_reasons"] = reasons
            excluded_users.append(u)
        else:
            eligible_users.append(u)

    eligible_phones = [u["phone"] for u in eligible_users]
    stats = get_template_stats_batch_amarillo(eligible_phones)
    for user in eligible_users:
        s = stats.get(user["phone"], {})
        user["send_count"] = s.get("count", 0)
        user["last_sent"] = s.get("last_sent", None)

    # Filter out users who already received 3+ templates (prevent fatigue)
    over_limit = [u for u in eligible_users if u["send_count"] >= 3]
    for u in over_limit:
        u["excluded_reasons"] = ["Límite de 3 envíos alcanzado"]
    excluded_users.extend(over_limit)
    eligible_users = [u for u in eligible_users if u["send_count"] < 3]

    # Also enrich excluded with stats for context in the UI
    if excluded_users:
        excl_phones = [u["phone"] for u in excluded_users]
        excl_stats = get_template_stats_batch_amarillo(excl_phones)
        for user in excluded_users:
            s = excl_stats.get(user["phone"], {})
            user["send_count"] = s.get("count", 0)
            user["last_sent"] = s.get("last_sent", None)

    return {"eligible": eligible_users, "excluded": excluded_users}


def execute_bulk_listo_docusign_notifications(users_list):
    """
    Sends the 'estado_amarillo' template to a list of users in DocuSign ready state.
    Returns summary of results.
    """
    results = {"total": len(users_list), "success": 0, "fail": 0, "errors": []}

    for user in users_list:
        phone_str = user.get("phone")
        nombre = user.get("name")

        if not phone_str:
            continue

        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "text": nombre,
                        "parameter_name": "nombre"
                    }
                ]
            }
        ]

        response = WhatsAppService.send_template(phone_str, "estado_amarillo", components=components)

        if response and response.get('messages'):
            set_user_state(phone_str, "waiting_for_cuenta_amarillo")
            from src.conversation_log import set_client_name
            set_client_name(phone_str, nombre)
            results["success"] += 1
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")

    return results


def get_pending_denegado_notifications():
    """
    Returns a dict with 'eligible' and 'excluded' lists for 'DENEGADO' /
    'CANCELADO POR LA EMPRESA' states.
    A phone is excluded if it has EVER received the estado_negados template
    (final decision — should not be sent more than once).
    """
    if TEST_MODE:
        return {"eligible": [{"phone": TEST_NUMBER, "name": "PROALTO TEST", "send_count": 0, "last_sent": None}], "excluded": []}

    clientes = get_denegado()
    if not clientes:
        return {"eligible": [], "excluded": []}

    raw_users = []
    phones_to_check = []

    for user in clientes:
        telefono = user.get("telefono")
        nombre = user.get("nombre_completo", "Cliente")

        phone_str = str(telefono).split(".")[0]
        phone_str = "".join(filter(str.isdigit, phone_str))

        if not phone_str:
            continue

        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"

        raw_users.append({
            "phone": phone_str,
            "name": nombre,
            "empresa": user.get("empresa", ""),
            "fecha_solicitud": user.get("fecha_de_solicitud", ""),
        })
        phones_to_check.append(phone_str)

    if not phones_to_check:
        return {"eligible": [], "excluded": []}

    # Exclude phones that have EVER received this template (no date filter)
    already_notified = get_notified_phones_denegado_batch(phones_to_check)

    eligible_users = []
    excluded_users = []
    for u in raw_users:
        if u["phone"] in already_notified:
            u["excluded_reasons"] = ["Ya notificado anteriormente"]
            excluded_users.append(u)
        else:
            eligible_users.append(u)

    eligible_phones = [u["phone"] for u in eligible_users]
    stats = get_template_stats_batch_denegado(eligible_phones)
    for user in eligible_users:
        s = stats.get(user["phone"], {})
        user["send_count"] = s.get("count", 0)
        user["last_sent"] = s.get("last_sent", None)

    if excluded_users:
        excl_phones = [u["phone"] for u in excluded_users]
        excl_stats = get_template_stats_batch_denegado(excl_phones)
        for user in excluded_users:
            s = excl_stats.get(user["phone"], {})
            user["send_count"] = s.get("count", 0)
            user["last_sent"] = s.get("last_sent", None)

    return {"eligible": eligible_users, "excluded": excluded_users}


def execute_bulk_denegado_notifications(users_list):
    """
    Sends the 'estado_negados' template to a list of denied/cancelled users.
    Returns summary of results.
    """
    results = {"total": len(users_list), "success": 0, "fail": 0, "errors": []}

    for user in users_list:
        phone_str = user.get("phone")
        nombre = user.get("name")

        if not phone_str:
            continue

        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "text": nombre,
                        "parameter_name": "nombre"
                    }
                ]
            }
        ]

        response = WhatsAppService.send_template(phone_str, "estado_negados", components=components)

        if response and response.get('messages'):
            set_user_state(phone_str, "denegado_notified")
            from src.conversation_log import set_client_name
            set_client_name(phone_str, nombre)
            results["success"] += 1
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")

    return results


# --- Yearly contact-data update campaign ----------------------------------
def get_pending_contact_update_notifications():
    """
    Returns a dict with 'eligible' and 'excluded' lists for the yearly
    contact-data update campaign.

    A client is eligible if:
      - They have an active loan (from Cloud Run /activos)
      - Their `ultima_actualizacion_datos` is NULL or older than 12 months
      - They are not currently in an in_progress contact-update flow
      - They have not received the actualizacion_datos template today
      - They have received fewer than 3 lifetime sends of this template
    """
    if TEST_MODE:
        return {
            "eligible": [{"phone": TEST_NUMBER, "name": "PROALTO TEST", "send_count": 0, "last_sent": None}],
            "excluded": [],
        }

    clientes = get_clientes_activos()
    if not clientes:
        return {"eligible": [], "excluded": []}

    raw_users = []
    phones_to_check = []
    for user in clientes:
        telefono = user.get("telefono")
        nombre = user.get("nombre_completo", "Cliente")

        phone_str = str(telefono).split(".")[0]
        phone_str = "".join(filter(str.isdigit, phone_str))
        if not phone_str:
            continue
        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"

        raw_users.append({"phone": phone_str, "name": nombre})
        phones_to_check.append(phone_str)

    if not phones_to_check:
        return {"eligible": [], "excluded": []}

    recently_updated = get_phones_recently_updated(phones_to_check, months=12)
    in_progress = get_phones_with_in_progress_contact_update(phones_to_check)
    notified_today = _get_notified_phones_actualizacion_today(phones_to_check)

    eligible_users = []
    excluded_users = []
    for u in raw_users:
        reasons = []
        if u["phone"] in recently_updated:
            reasons.append("Actualizó datos en los últimos 12 meses")
        if u["phone"] in in_progress:
            reasons.append("Ya tiene una actualización en curso")
        if u["phone"] in notified_today:
            reasons.append("Ya notificado hoy")
        if reasons:
            u["excluded_reasons"] = reasons
            excluded_users.append(u)
        else:
            eligible_users.append(u)

    # Enforce 3-send lifetime cap
    eligible_phones = [u["phone"] for u in eligible_users]
    stats = _get_template_stats_actualizacion(eligible_phones)
    for user in eligible_users:
        s = stats.get(user["phone"], {})
        user["send_count"] = s.get("count", 0)
        user["last_sent"] = s.get("last_sent", None)

    over_limit = [u for u in eligible_users if u["send_count"] >= 3]
    for u in over_limit:
        u["excluded_reasons"] = ["Límite de 3 envíos alcanzado"]
    excluded_users.extend(over_limit)
    eligible_users = [u for u in eligible_users if u["send_count"] < 3]
    eligible_users.sort(key=lambda u: u["send_count"])

    if excluded_users:
        excl_phones = [u["phone"] for u in excluded_users]
        excl_stats = _get_template_stats_actualizacion(excl_phones)
        for user in excluded_users:
            s = excl_stats.get(user["phone"], {})
            user.setdefault("send_count", s.get("count", 0))
            user.setdefault("last_sent", s.get("last_sent", None))

    return {"eligible": eligible_users, "excluded": excluded_users}


def _get_notified_phones_actualizacion_today(phones: list) -> set:
    """Return phones that already received the actualizacion_datos template today."""
    from src.conversation_log import supabase_client
    if not supabase_client or not phones:
        return set()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        res = supabase_client.table('bot_messages')\
            .select("phone")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .eq("text", "[Template: actualizacion_datos]")\
            .gte("created_at", f"{today}T00:00:00")\
            .execute()
        return {item["phone"] for item in (res.data or [])}
    except Exception as e:
        print(f"_get_notified_phones_actualizacion_today error: {e}")
        return set()


def _get_template_stats_actualizacion(phones: list) -> dict:
    """Return {phone: {count, last_sent}} for the actualizacion_datos template."""
    from src.conversation_log import supabase_client
    if not supabase_client or not phones:
        return {}
    try:
        res = supabase_client.table('bot_messages')\
            .select("phone, created_at")\
            .in_("phone", phones)\
            .eq("direction", "outbound")\
            .eq("text", "[Template: actualizacion_datos]")\
            .execute()
        stats = {}
        for row in (res.data or []):
            phone = row["phone"]
            if phone not in stats:
                stats[phone] = {"count": 0, "last_sent": None}
            stats[phone]["count"] += 1
            created = row.get("created_at")
            if created and (stats[phone]["last_sent"] is None or created > stats[phone]["last_sent"]):
                stats[phone]["last_sent"] = created
        return stats
    except Exception as e:
        print(f"_get_template_stats_actualizacion error: {e}")
        return {}


def execute_bulk_contact_update_notifications(users_list):
    """Send the 'actualizacion_datos' template to a list of users.
    The template expects a single named body parameter `nombre`. After Meta
    accepts the send, the client is left in state 'esperando_respuesta_actualizacion'
    so their next message — button or text — is handled by the flow.
    """
    results = {"total": len(users_list), "success": 0, "fail": 0, "errors": []}

    for user in users_list:
        phone_str = user.get("phone")
        nombre = user.get("name") or "Cliente"
        if not phone_str:
            continue

        # Meta truncates aggressively if the parameter contains line breaks or
        # excessive whitespace; use the first given name to keep the greeting tight.
        nombre_clean = (nombre or "Cliente").strip().split()[0] if nombre else "Cliente"

        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "text": nombre_clean,
                        "parameter_name": "nombre",
                    }
                ],
            }
        ]

        response = WhatsAppService.send_template(phone_str, "actualizacion_datos", components=components)

        if response and response.get('messages'):
            set_user_state(phone_str, "esperando_respuesta_actualizacion")
            from src.conversation_log import set_client_name
            set_client_name(phone_str, nombre)
            results["success"] += 1
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")

    return results


# --- Scheduler Logic for future automation ---
def scheduled_task():
    print(f"[{datetime.now()}] Checking for pending approved notifications...")
    # This is where we'd put the automated logic if we want it 100% hands-free later
    # For now, it's triggered manually from the admin panel.
    pass

scheduler = BackgroundScheduler()
# scheduler.add_job(func=scheduled_task, trigger="interval", minutes=60)
# scheduler.start()

# atexit.register(lambda: scheduler.shutdown())

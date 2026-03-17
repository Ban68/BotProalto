import os
import psycopg2
import functions_framework
from flask import jsonify

@functions_framework.http
def get_solicitud(request):
    auth_header = request.headers.get("Authorization")
    expected_token = "Bearer " + os.environ.get("API_TOKEN_SECRET", "")
    if auth_header != expected_token:
        return jsonify({"error": "No Autorizado"}), 401
    request_json = request.get_json(silent=True)
    tipo = request_json.get("tipo", "solicitud") if request_json else "solicitud"

    cedula = request_json.get("cedula") if request_json else None
    if tipo not in ("aprobados", "falta_documento", "por_telefono") and not cedula:
        return jsonify({"error": "Cedula no proporcionada"}), 400

    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST"),
            database=os.environ.get("DB_NAME"),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            port=os.environ.get("DB_PORT", "5432"),
            connect_timeout=10,
        )
        cur = conn.cursor()
        cur.execute("SET statement_timeout = 10000")

        if tipo == "saldo":
            cur.execute(
                "SELECT cedula, id_prestamo, nombre_completo, saldo_actual, estado_del_prestamo, cuotas_restantes, ultima_fecha_pago FROM vista_consulta_saldo WHERE cedula = %s",
                (cedula,),
            )
            records = cur.fetchall()
            cur.close()
            conn.close()
            if records:
                prestamos = []
                for r in records:
                    prestamos.append({
                        "id_prestamo": r[1] or "",
                        "nombre_completo": r[2] or "",
                        "saldo_actual": float(r[3]) if r[3] else 0,
                        "estado_del_prestamo": r[4] or "",
                        "cuotas_restantes": r[5] if r[5] is not None else 0,
                        "ultima_fecha_pago": str(r[6]) if r[6] else "",
                    })
                return jsonify({"found": True, "prestamos": prestamos}), 200
            else:
                return jsonify({"found": False}), 200

        elif tipo == "aprobados":
            cur.execute("""
                SELECT nro_solicitud, fecha_de_solicitud, valor_preestudiado,
                       estado_interno, nombre_completo, plazo, telefono
                FROM v_solicitudes_whatsapp
                WHERE UPPER(estado_interno) = 'APROBADO POR EL CLIENTE'
            """)
            records = cur.fetchall()
            cur.close()
            conn.close()
            if records:
                aprobados = []
                for r in records:
                    aprobados.append({
                        "nro_solicitud": r[0] or 0,
                        "fecha_de_solicitud": str(r[1]) if r[1] else "",
                        "valor_preestudiado": float(r[2]) if r[2] else 0,
                        "estado_interno": r[3] or "",
                        "nombre_completo": r[4] or "",
                        "plazo": r[5] if r[5] else 0,
                        "telefono": r[6] if len(r) > 6 and r[6] else ""
                    })
                return jsonify({"found": True, "aprobados": aprobados}), 200
            else:
                return jsonify({"found": False, "aprobados": []}), 200

        elif tipo == "falta_documento":
            cur.execute("""
                SELECT nombre_completo, telefono
                FROM v_solicitudes_whatsapp
                WHERE UPPER(estado_interno) = 'FALTA ALGÚN DOCUMENTO'
                  AND telefono IS NOT NULL
                  AND telefono != ''
            """)
            records = cur.fetchall()
            cur.close()
            conn.close()
            if records:
                clientes = []
                for r in records:
                    clientes.append({
                        "nombre_completo": r[0] or "",
                        "telefono": r[1] or ""
                    })
                return jsonify({"found": True, "clientes": clientes}), 200
            else:
                return jsonify({"found": False, "clientes": []}), 200

        elif tipo == "por_telefono":
            telefono = request_json.get("telefono") if request_json else None
            if not telefono:
                return jsonify({"error": "Telefono no proporcionado"}), 400
            telefono_str = str(telefono)
            sin_prefijo = telefono_str[2:] if telefono_str.startswith("57") else telefono_str
            cur.execute("""
                SELECT nombre_completo
                FROM v_solicitudes_whatsapp
                WHERE telefono = %s OR telefono = %s
                ORDER BY nro_solicitud DESC
                LIMIT 1
            """, (telefono_str, sin_prefijo))
            record = cur.fetchone()
            cur.close()
            conn.close()
            if record:
                return jsonify({"found": True, "nombre_completo": record[0] or ""}), 200
            else:
                return jsonify({"found": False}), 200

        else:
            query = """
                SELECT nro_solicitud, fecha_de_solicitud, valor_preestudiado,
                       estado_interno, nombre_completo, plazo
                FROM v_solicitudes_whatsapp
                WHERE cedula_nit = %s
                ORDER BY nro_solicitud DESC
                LIMIT 1
            """
            cur.execute(query, (cedula,))
            record = cur.fetchone()
            cur.close()
            conn.close()
            if record:
                return jsonify({
                    "found": True,
                    "nro_solicitud": record[0],
                    "fecha_de_solicitud": str(record[1]) if record[1] else "",
                    "valor_preestudiado": float(record[2]) if record[2] else 0,
                    "estado_interno": record[3] or "",
                    "nombre_completo": record[4] or "",
                    "plazo": record[5],
                }), 200
            else:
                return jsonify({"found": False}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

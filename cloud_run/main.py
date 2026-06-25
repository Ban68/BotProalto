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
    if tipo not in ("aprobados", "falta_documento", "por_telefono", "por_telefono_completo", "listo_en_docusign", "denegado", "activos", "diagnostico_activos") and not cedula:
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
                       estado_interno, nombre_completo, plazo, telefono, empresa, cuota
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
                        "telefono": r[6] if len(r) > 6 and r[6] else "",
                        "empresa": r[7] or "",
                        "cuota": float(r[8]) if r[8] else 0
                    })
                return jsonify({"found": True, "aprobados": aprobados}), 200
            else:
                return jsonify({"found": False, "aprobados": []}), 200

        elif tipo == "falta_documento":
            cur.execute("""
                SELECT nombre_completo, telefono, empresa, documentos_faltantes
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
                        "telefono": r[1] or "",
                        "empresa": r[2] or "",
                        "documentos_faltantes": r[3] or "",
                        "tipo_empleador": "EMPRESA"
                    })
                return jsonify({"found": True, "clientes": clientes}), 200
            else:
                return jsonify({"found": False, "clientes": []}), 200

        elif tipo == "denegado":
            cur.execute("""
                SELECT nombre_completo, telefono, empresa, fecha_de_solicitud
                FROM v_solicitudes_whatsapp
                WHERE UPPER(estado_interno) IN ('DENEGADO', 'CANCELADO POR LA EMPRESA')
                  AND telefono IS NOT NULL
                  AND telefono != ''
                  AND fecha_de_solicitud >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY fecha_de_solicitud DESC
            """)
            records = cur.fetchall()
            cur.close()
            conn.close()
            if records:
                clientes = []
                for r in records:
                    clientes.append({
                        "nombre_completo": r[0] or "",
                        "telefono": r[1] or "",
                        "empresa": r[2] or "",
                        "fecha_de_solicitud": str(r[3]) if r[3] else ""
                    })
                return jsonify({"found": True, "clientes": clientes}), 200
            else:
                return jsonify({"found": False, "clientes": []}), 200

        elif tipo == "diagnostico_activos":
            # Endpoint temporal para diagnosticar por qué la campaña actualizacion_datos
            # solo encuentra ~572 clientes cuando ProAlto reporta ~2744 activos.
            # Devuelve conteos en cada paso del embudo y algunos ejemplos.
            diag = {}

            cur.execute("SELECT COUNT(DISTINCT cedula) FROM vista_consulta_saldo")
            diag["1_total_cedulas_en_vista_consulta_saldo"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT cedula) FROM vista_consulta_saldo WHERE saldo_actual > 0")
            diag["2_cedulas_con_saldo_mayor_a_cero"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT cedula) FROM vista_consulta_saldo WHERE saldo_actual IS NULL")
            diag["2b_cedulas_con_saldo_null"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT cedula) FROM vista_consulta_saldo WHERE saldo_actual = 0")
            diag["2c_cedulas_con_saldo_cero"] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT cedula_nit) FROM v_solicitudes_whatsapp")
            diag["3_total_cedulas_en_v_solicitudes_whatsapp"] = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(DISTINCT s.cedula)
                FROM vista_consulta_saldo s
                INNER JOIN v_solicitudes_whatsapp w ON w.cedula_nit = s.cedula
                WHERE s.saldo_actual > 0
            """)
            diag["4_activos_con_join_a_solicitudes"] = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(DISTINCT s.cedula)
                FROM vista_consulta_saldo s
                INNER JOIN v_solicitudes_whatsapp w ON w.cedula_nit = s.cedula
                WHERE s.saldo_actual > 0
                  AND w.telefono IS NOT NULL
                  AND w.telefono != ''
            """)
            diag["5_activos_con_join_y_telefono_no_vacio"] = cur.fetchone()[0]

            # Ejemplos: 5 cédulas activas que NO matchean en v_solicitudes_whatsapp
            cur.execute("""
                SELECT s.cedula, s.nombre_completo
                FROM vista_consulta_saldo s
                LEFT JOIN v_solicitudes_whatsapp w ON w.cedula_nit = s.cedula
                WHERE s.saldo_actual > 0
                  AND w.cedula_nit IS NULL
                LIMIT 5
            """)
            sin_join = [{"cedula": str(r[0]), "nombre": r[1] or ""} for r in cur.fetchall()]
            diag["6_ejemplos_sin_match_en_solicitudes"] = sin_join

            # Ejemplos: 5 cédulas activas que SI matchean pero tienen telefono vacío
            cur.execute("""
                SELECT s.cedula, s.nombre_completo, w.telefono
                FROM vista_consulta_saldo s
                INNER JOIN v_solicitudes_whatsapp w ON w.cedula_nit = s.cedula
                WHERE s.saldo_actual > 0
                  AND (w.telefono IS NULL OR w.telefono = '')
                LIMIT 5
            """)
            sin_tel = [{"cedula": str(r[0]), "nombre": r[1] or "", "telefono": str(r[2]) if r[2] is not None else None} for r in cur.fetchall()]
            diag["7_ejemplos_con_match_pero_sin_telefono"] = sin_tel

            # 8. Tipos de columna (para descartar mismatch text vs bigint)
            cur.execute("""
                SELECT table_name, column_name, data_type, udt_name
                FROM information_schema.columns
                WHERE (table_name = 'vista_consulta_saldo' AND column_name = 'cedula')
                   OR (table_name = 'v_solicitudes_whatsapp' AND column_name = 'cedula_nit')
            """)
            diag["8_tipos_columnas"] = [
                {"vista": r[0], "columna": r[1], "data_type": r[2], "udt_name": r[3]} for r in cur.fetchall()
            ]

            # 9. JOIN con CAST a TEXT (descarta mismatch de tipo)
            cur.execute("""
                SELECT COUNT(DISTINCT s.cedula)
                FROM vista_consulta_saldo s
                INNER JOIN v_solicitudes_whatsapp w ON CAST(w.cedula_nit AS TEXT) = CAST(s.cedula AS TEXT)
                WHERE s.saldo_actual > 0
            """)
            diag["9_activos_con_join_CAST_text"] = cur.fetchone()[0]

            # 10. JOIN limpiando puntos, guiones y espacios
            cur.execute("""
                SELECT COUNT(DISTINCT s.cedula)
                FROM vista_consulta_saldo s
                INNER JOIN v_solicitudes_whatsapp w
                  ON regexp_replace(CAST(w.cedula_nit AS TEXT), '[^0-9]', '', 'g')
                   = regexp_replace(CAST(s.cedula AS TEXT), '[^0-9]', '', 'g')
                WHERE s.saldo_actual > 0
            """)
            diag["10_activos_con_join_limpiando_no_digitos"] = cur.fetchone()[0]

            # 11. Sample raw de 5 cédulas de cada vista (sin cast, así vemos el formato real)
            cur.execute("SELECT DISTINCT cedula FROM vista_consulta_saldo LIMIT 5")
            diag["11a_sample_cedulas_vista_consulta_saldo"] = [
                {"raw": str(r[0]), "len": len(str(r[0]))} for r in cur.fetchall()
            ]
            cur.execute("SELECT DISTINCT cedula_nit FROM v_solicitudes_whatsapp LIMIT 5")
            diag["11b_sample_cedula_nit_v_solicitudes_whatsapp"] = [
                {"raw": str(r[0]), "len": len(str(r[0]))} for r in cur.fetchall()
            ]

            # 12. Buscar una cédula puntual de las "sin match" con búsqueda relajada
            target = "1193048909"
            cur.execute("""
                SELECT cedula_nit, nombre_completo, telefono
                FROM v_solicitudes_whatsapp
                WHERE regexp_replace(CAST(cedula_nit AS TEXT), '[^0-9]', '', 'g') = %s
                LIMIT 3
            """, (target,))
            diag[f"12_busqueda_relajada_cedula_{target}"] = [
                {"cedula_nit_raw": str(r[0]), "nombre": r[1], "telefono": r[2]} for r in cur.fetchall()
            ]

            cur.close()
            conn.close()
            return jsonify({"diagnostico": diag}), 200

        elif tipo == "activos":
            # Clientes con préstamo vigente (saldo > 0). El teléfono lo traemos
            # desde v_solicitudes_whatsapp porque vista_consulta_saldo no lo
            # tiene. DISTINCT ON garantiza una fila por cliente aunque tenga
            # varios préstamos activos.
            cur.execute("""
                SELECT DISTINCT ON (s.cedula)
                       s.cedula, s.nombre_completo, w.telefono
                FROM vista_consulta_saldo s
                LEFT JOIN v_solicitudes_whatsapp w ON w.cedula_nit = s.cedula
                WHERE s.saldo_actual > 0
                  AND w.telefono IS NOT NULL
                  AND w.telefono != ''
                ORDER BY s.cedula, s.ultima_fecha_pago DESC NULLS LAST
            """)
            records = cur.fetchall()
            cur.close()
            conn.close()
            if records:
                clientes = []
                for r in records:
                    clientes.append({
                        "cedula": str(r[0]) if r[0] else "",
                        "nombre_completo": r[1] or "",
                        "telefono": r[2] or "",
                    })
                return jsonify({"found": True, "clientes": clientes}), 200
            else:
                return jsonify({"found": False, "clientes": []}), 200

        elif tipo == "listo_en_docusign":
            cur.execute("""
                SELECT nombre_completo, telefono, empresa
                FROM v_solicitudes_whatsapp
                WHERE UPPER(estado_interno) IN ('LISTO EN DOCUSIGN', 'LISTO EN PANDADOC', 'LISTO PARA DESEMBOLSO')
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
                        "telefono": r[1] or "",
                        "empresa": r[2] or ""
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

        elif tipo == "por_telefono_completo":
            telefono = request_json.get("telefono") if request_json else None
            if not telefono:
                return jsonify({"error": "Telefono no proporcionado"}), 400
            telefono_str = str(telefono)
            sin_prefijo = telefono_str[2:] if telefono_str.startswith("57") else telefono_str
            cur.execute("""
                SELECT nro_solicitud, fecha_de_solicitud, valor_preestudiado,
                       estado_interno, nombre_completo, plazo,
                       empresa, documentos_faltantes, cuota, frecuencia,
                       cedula_nit, opc_negadas
                FROM v_solicitudes_whatsapp
                WHERE telefono = %s OR telefono = %s
                ORDER BY nro_solicitud DESC
                LIMIT 1
            """, (telefono_str, sin_prefijo))
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
                    "empresa": record[6] or "",
                    "documentos_faltantes": record[7] or "",
                    "tipo_empleador": "EMPRESA",
                    "cuota": float(record[8]) if record[8] else None,
                    "frecuencia": record[9] or "",
                    "cedula": str(record[10]) if record[10] else "",
                    "opc_negadas": record[11] or "",
                }), 200
            else:
                return jsonify({"found": False}), 200

        else:
            query = """
                SELECT nro_solicitud, fecha_de_solicitud, valor_preestudiado,
                       estado_interno, nombre_completo, plazo,
                       empresa, documentos_faltantes, cuota, frecuencia,
                       opc_negadas
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
                    "empresa": record[6] or "",
                    "documentos_faltantes": record[7] or "",
                    "tipo_empleador": "EMPRESA",
                    "cuota": float(record[8]) if record[8] else None,
                    "frecuencia": record[9] or "",
                    "opc_negadas": record[10] or "",
                }), 200
            else:
                return jsonify({"found": False}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

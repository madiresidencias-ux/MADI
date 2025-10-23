# app.py — COMPLETO (límite total 2 tickets + bloqueo por encuesta pendiente)
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory
from flask_mysqldb import MySQL
from werkzeug.security import check_password_hash
from functools import wraps
from datetime import datetime, date, timedelta
import os, re

# ====================== Config ======================
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)

app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', '')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'madi_dev')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev-key")
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')

# Límite global de tickets por usuario (HISTÓRICO)
MAX_TOTAL_TICKETS = int(os.getenv("MAX_TOTAL_TICKETS", "2"))

conexion = MySQL(app)

# ====================== Helpers ======================
def serialize_rows(rows):
    out = []
    for r in rows:
        d = {}
        for k, v in r.items():
            if isinstance(v, (datetime, date)):
                d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
            else:
                d[k] = v
        out.append(d)
    return out

def _wants_json() -> bool:
    return request.path.startswith("/api/") or \
           "application/json" in (request.headers.get("Accept") or "") or \
           request.is_json

def to_int_list(values):
    out = []
    try:
        for v in values:
            out.append(int(v))
        return out
    except (TypeError, ValueError):
        return None

def _fmt_hms(delta):
    if not delta:
        return ""
    secs = int(max(0, delta.total_seconds()))
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def _s15(v):
    try:
        iv = int(v)
        return iv if 1 <= iv <= 5 else None
    except:
        return None

def _encuestas_pendientes(uid: int, incluir_cancelados: bool = False):
    """
    Devuelve los tickets del usuario con encuesta pendiente.
    Por defecto solo obliga encuesta si el ticket está RESUELTO.
    Si incluir_cancelados=True, también obligará para CANCELADO.
    """
    estados = ("RESUELTO", "CANCELADO") if incluir_cancelados else ("RESUELTO",)
    cur = conexion.connection.cursor()
    try:
        placeholders = ", ".join(["%s"] * len(estados))
        sql = f"""
            SELECT t.id, t.asunto, t.estado, t.creado_en
            FROM tickets t
            LEFT JOIN encuestas e ON e.ticket_id = t.id
            WHERE t.usuario_id = %s
              AND t.estado IN ({placeholders})
              AND e.id IS NULL
            ORDER BY t.creado_en DESC
        """
        cur.execute(sql, (uid, *estados))
        rows = cur.fetchall() or []
        return rows
    finally:
        cur.close()

def _total_tickets_count(uid: int) -> int:
    """Cuenta TOTAL histórico de tickets del usuario (cualquier estado)."""
    cur = conexion.connection.cursor()
    try:
        cur.execute("SELECT COUNT(*) AS c FROM tickets WHERE usuario_id=%s", (uid,))
        row = cur.fetchone() or {"c": 0}
        return int(row["c"] or 0)
    finally:
        cur.close()

# ====================== Auth / Roles ======================
def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("user_id"):
            if _wants_json():
                return jsonify(ok=False, msg="No autenticado"), 401
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapper

def role_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapper(*a, **kw):
            if not session.get("user_id"):
                if _wants_json():
                    return jsonify(ok=False, msg="No autenticado"), 401
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                if _wants_json():
                    return jsonify(ok=False, msg="No autorizado"), 403
                return redirect(url_for({
                    "TECNICO": "tecnico_disponibles",
                    "SOLICITANTE": "solicitante_form"
                }.get(session.get("role"), "root_index")))
            return view(*a, **kw)
        return wrapper
    return deco

# ====================== Público ======================
@app.route("/")
def root_index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        role_hint = (request.args.get("role") or "").strip().lower()
        return render_template("login.html", role_hint=role_hint)

    data = request.get_json(silent=True) or {}
    user = (data.get("user") or "").strip()
    pwd  = (data.get("pass") or "").strip()
    if not user or not pwd:
        return jsonify(ok=False, msg="Usuario y contraseña requeridos."), 400

    cur = conexion.connection.cursor()
    try:
        cur.execute("""
            SELECT u.id, u.username, u.password_hash, u.is_active, u.area_id,
                   r.nombre AS role
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.username=%s
            LIMIT 1
        """, (user,))
        row = cur.fetchone()
    finally:
        cur.close()

    if not row or not row["is_active"]:
        return jsonify(ok=False, msg="Usuario no encontrado o inactivo."), 401
    if not check_password_hash(row["password_hash"], pwd):
        return jsonify(ok=False, msg="Credenciales incorrectas."), 401

    session["user_id"]  = row["id"]
    session["username"] = row["username"]
    session["role"]     = row["role"]
    session["area_id"]  = row["area_id"]

    dest = {
        "TECNICO": "tecnico_disponibles",
        "SOLICITANTE": "solicitante_form",
    }.get(row["role"], "root_index")
    return jsonify(ok=True, redirect=url_for(dest))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("root_index"))

# ====================== Solicitante (vistas) ======================
@app.route("/solicitante")
@login_required
@role_required("SOLICITANTE")
def solicitante_form():
    return render_template("solicitante/form.html")

@app.route("/solicitante/tickets")
@login_required
@role_required("SOLICITANTE")
def solicitante_tickets():
    return render_template("solicitante/tickets.html")

# ====================== Solicitante (APIs) ======================
@app.get("/api/session/me")
@login_required
def api_session_me():
    cur = conexion.connection.cursor()
    try:
        cur.execute("""
            SELECT u.id, u.username, u.email, u.area_id, r.nombre AS role, a.nombre AS area_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN areas a ON a.id = u.area_id
            WHERE u.id = %s
            LIMIT 1
        """, (session["user_id"],))
        row = cur.fetchone()
    finally:
        cur.close()
    if not row:
        return jsonify({"ok": False, "msg": "Sesión inválida."}), 401
    return jsonify(serialize_rows([row])[0]), 200

@app.get("/api/session/basic")
@login_required
def api_session_basic():
    return jsonify({
        "user_id": session.get("user_id"),
        "username": session.get("username"),
        "role": session.get("role"),
        "area_id": session.get("area_id"),
    })

@app.get("/api/mis-tickets")
@login_required
@role_required("SOLICITANTE")
def api_mis_tickets():
    estado = (request.args.get("estado") or "").upper()
    cur = conexion.connection.cursor()
    try:
        base = """
            SELECT
              t.id,
              t.asunto,
              t.estado,
              t.creado_en,
              t.solicitante_nombre,
              (
                SELECT u.username
                FROM ticket_tecnicos tt
                JOIN users u ON u.id = tt.user_id
                WHERE tt.ticket_id = t.id
                ORDER BY u.username ASC
                LIMIT 1
              ) AS tecnico,
              (
                SELECT GROUP_CONCAT(u2.username ORDER BY u2.username SEPARATOR ', ')
                FROM ticket_tecnicos tt2
                JOIN users u2 ON u2.id = tt2.user_id
                WHERE tt2.ticket_id = t.id
              ) AS tecnicos,
              (SELECT 1 FROM encuestas e WHERE e.ticket_id = t.id LIMIT 1) AS encuestada
            FROM tickets t
            WHERE t.usuario_id = %s
        """
        params = [session["user_id"]]

        if estado == "FINALIZADOS":
            base += " AND t.estado IN ('RESUELTO','CANCELADO')"
        elif estado in {"PENDIENTE", "EN_CURSO", "RESUELTO", "CANCELADO"}:
            base += " AND t.estado = %s"
            params.append(estado)
        else:
            base += " AND t.estado IN ('PENDIENTE','EN_CURSO')"

        base += " ORDER BY t.creado_en DESC LIMIT 200"
        cur.execute(base, tuple(params))
        rows = cur.fetchall()
    finally:
        cur.close()

    return jsonify(serialize_rows(rows)), 200

@app.get("/api/tickets/total/limit")
@login_required
@role_required("SOLICITANTE")
def api_tickets_total_limit():
    cnt = _total_tickets_count(session["user_id"])
    return jsonify({"ok": True, "limit": MAX_TOTAL_TICKETS, "count": cnt}), 200

@app.post("/api/tickets")
@login_required
@role_required("SOLICITANTE")
def api_crear_ticket():
    if request.content_type and "multipart/form-data" in request.content_type:
        form = request.form
        files = request.files.getlist("imagenes")
        tipo   = (form.get("tipo") or "").strip()
        desc   = (form.get("descripcion") or "").strip()
        nombre = (form.get("solicitante_nombre") or "").strip()
    else:
        data = request.get_json(force=True)
        files = []
        tipo   = (data.get("tipo") or "").strip()
        desc   = (data.get("descripcion") or "").strip()
        nombre = (data.get("solicitante_nombre") or "").strip()

    # Validaciones mínimas
    if not nombre:
        return jsonify({"ok": False, "msg": "El nombre del solicitante es obligatorio."}), 400
    if not tipo or not desc:
        return jsonify({"ok": False, "msg": "tipo y descripcion son obligatorios."}), 400

    # LÍMITE GLOBAL: máx. 2 tickets en total por usuario (histórico)
    total_count = _total_tickets_count(session["user_id"])
    if total_count >= MAX_TOTAL_TICKETS:
        return jsonify({
            "ok": False,
            "msg": f"No puedes crear otra solicitud: alcanzaste el máximo total de {MAX_TOTAL_TICKETS} ticket(s).",
            "total_count": total_count,
            "limit": MAX_TOTAL_TICKETS
        }), 409

    # BLOQUEO POR ENCUESTA PENDIENTE (cambia a True si también aplica a CANCELADO)
    pendientes = _encuestas_pendientes(session["user_id"], incluir_cancelados=False)
    if pendientes:
        return jsonify({
            "ok": False,
            "msg": "Tienes una encuesta de satisfacción pendiente. Resuélvela para crear un nuevo ticket.",
            "pendientes": serialize_rows(pendientes)
        }), 409

    # Inserción del ticket
    cur = conexion.connection.cursor()
    try:
        cur.execute("SELECT area_id FROM users WHERE id=%s", (session["user_id"],))
        row = cur.fetchone()
        area_id = row["area_id"] if row else None
        if not area_id:
            return jsonify({"ok": False, "msg": "Tu usuario no tiene un área asignada."}), 400

        asunto = tipo[:180]
        cur.execute("""
            INSERT INTO tickets (usuario_id, area_id, solicitante_nombre, asunto, descripcion, estado)
            VALUES (%s, %s, %s, %s, %s, 'PENDIENTE')
        """, (session["user_id"], area_id, nombre, asunto, desc))
        conexion.connection.commit()
        ticket_id = cur.lastrowid

        # adjuntos (máx 3 imágenes)
        saved = 0
        for f in files[:3]:
            if not f or not (f.mimetype or "").startswith("image/"):
                continue
            safe_name = re.sub(r'[^a-zA-Z0-9._-]+','_', f.filename or "img")
            subdir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], "tickets")
            os.makedirs(subdir, exist_ok=True)
            filepath = os.path.join(subdir, f"{ticket_id}_{safe_name}")
            f.save(filepath)
            cur.execute("INSERT INTO ticket_attachments (ticket_id, ruta) VALUES (%s, %s)", (ticket_id, filepath))
            saved += 1
        if saved:
            conexion.connection.commit()
    finally:
        cur.close()

    return jsonify({"ok": True, "id": ticket_id}), 201

@app.get("/api/tipos-solicitud")
@login_required
def api_tipos_solicitud():
    cur = conexion.connection.cursor()
    try:
        cur.execute("""
            SELECT id, nombre, slug, orden
            FROM tipos_solicitud
            WHERE activo=1
            ORDER BY orden ASC, id ASC
        """)
        rows = cur.fetchall()
    finally:
        cur.close()
    return jsonify(serialize_rows(rows)), 200

@app.get("/api/sugerencias")
@login_required
def api_sugerencias():
    tipo   = (request.args.get("tipo") or "").strip()
    tipo_id = request.args.get("tipo_id")
    if not tipo and not tipo_id:
        return jsonify([]), 200

    cur = conexion.connection.cursor()
    try:
        if tipo_id:
            cur.execute("""
                SELECT s.id, s.texto, s.orden
                FROM sugerencias_problema s
                JOIN tipos_solicitud t ON t.id = s.tipo_id
                WHERE s.activo=1 AND t.activo=1 AND t.id=%s
                ORDER BY s.orden ASC, s.id ASC
            """, (tipo_id,))
        else:
            cur.execute("""
                SELECT s.id, s.texto, s.orden
                FROM sugerencias_problema s
                JOIN tipos_solicitud t ON t.id = s.tipo_id
                WHERE s.activo=1 AND t.activo=1
                  AND (t.slug=%s OR t.nombre=%s)
                ORDER BY s.orden ASC, s.id ASC
            """, (tipo, tipo))
        rows = cur.fetchall()
    finally:
        cur.close()
    return jsonify(serialize_rows(rows)), 200

# ====================== Técnico (vistas) ======================
@app.route("/tecnico", endpoint="tecnico_disponibles")
@login_required
@role_required("TECNICO")
def tecnico_disponibles():
    return render_template("tecnico/tecnico.html", user=session.get("username"))

@app.route("/tecnico/asignados", endpoint="tecnico_asignados")
@login_required
@role_required("TECNICO")
def tecnico_asignados():
    return render_template("tecnico/mis_asignados.html", user=session.get("username"))

@app.route("/tecnico/historial", endpoint="tecnico_historial")
@login_required
@role_required("TECNICO")
def tecnico_historial():
    return render_template("tecnico/historial.html", user=session.get("username"))

# Servir evidencias con login
@app.get("/uploads/tickets/<path:fname>")
@login_required
def serve_ticket_upload(fname):
    base_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], "tickets")
    return send_from_directory(base_dir, fname)

# ====================== Técnico (APIs) ======================
def _group_concat_asignados_sql():
    return """(
        SELECT GROUP_CONCAT(u.username ORDER BY u.username SEPARATOR ', ')
        FROM ticket_tecnicos tt
        JOIN users u ON u.id = tt.user_id
        WHERE tt.ticket_id = t.id
    ) AS asignados"""

@app.get("/api/tecnico/tickets")
@login_required
@role_required("TECNICO")
def api_tecnico_tickets():
    scope = (request.args.get("scope") or "disponibles").lower()
    uid = session["user_id"]

    cur = conexion.connection.cursor()
    try:
        if scope == "asignados":
            sql = f"""
                SELECT t.id, t.asunto, t.descripcion, t.estado, t.creado_en,
                       t.solicitante_nombre, a.nombre AS area, {_group_concat_asignados_sql()}
                FROM tickets t
                LEFT JOIN areas a ON a.id = t.area_id
                JOIN ticket_tecnicos mine
                  ON mine.ticket_id = t.id AND mine.user_id = %s
                WHERE t.estado IN ('PENDIENTE','EN_CURSO')
                ORDER BY t.creado_en DESC
                LIMIT 300
            """
            params = (uid,)
        elif scope == "historial":
            sql = f"""
                SELECT t.id, t.asunto, t.descripcion, t.estado, t.creado_en,
                       t.solicitante_nombre, a.nombre AS area, {_group_concat_asignados_sql()}
                FROM tickets t
                LEFT JOIN areas a ON a.id = t.area_id
                JOIN ticket_tecnicos mine
                  ON mine.ticket_id = t.id AND mine.user_id = %s
                WHERE t.estado IN ('RESUELTO','CANCELADO')
                ORDER BY t.creado_en DESC
                LIMIT 300
            """
            params = (uid,)
        else:
            sql = f"""
                SELECT t.id, t.asunto, t.descripcion, t.estado, t.creado_en,
                       t.solicitante_nombre, a.nombre AS area, {_group_concat_asignados_sql()}
                FROM tickets t
                LEFT JOIN areas a ON a.id = t.area_id
                WHERE t.estado='PENDIENTE'
                  AND NOT EXISTS (SELECT 1 FROM ticket_tecnicos x WHERE x.ticket_id=t.id)
                ORDER BY t.creado_en DESC
                LIMIT 300
            """
            params = ()
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close()

    return jsonify(serialize_rows(rows)), 200

@app.get("/api/tecnicos")
@login_required
@role_required("TECNICO")
def api_tecnicos_activos():
    cur = conexion.connection.cursor()
    try:
        cur.execute("""
            SELECT u.id, u.username
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE r.nombre = 'TECNICO' AND u.is_active = 1
            ORDER BY u.username ASC
        """)
        rows = cur.fetchall()
    finally:
        cur.close()
    return jsonify(serialize_rows(rows)), 200

@app.get("/api/tecnico/tickets/<int:tid>")
@login_required
@role_required("TECNICO")
def api_tecnico_ticket_detalle(tid):
    cur = conexion.connection.cursor()
    try:
        cur.execute(f"""
            SELECT t.id, t.asunto, t.descripcion, t.estado, t.creado_en,
                   t.solicitante_nombre, a.nombre AS area, {_group_concat_asignados_sql()}
            FROM tickets t
            LEFT JOIN areas a ON a.id = t.area_id
            WHERE t.id=%s
            LIMIT 1
        """, (tid,))
        head = cur.fetchone()

        try:
            cur.execute("""
                SELECT n.id, n.texto, n.creado_en, u.username AS autor
                FROM ticket_notas n
                JOIN users u ON u.id = n.usuario_id
                WHERE n.ticket_id=%s
                ORDER BY n.creado_en DESC
            """, (tid,))
            notas = cur.fetchall()
        except Exception:
            notas = []

        cur.execute("""
            SELECT u.id, u.username
            FROM ticket_tecnicos tt
            JOIN users u ON u.id = tt.user_id
            WHERE tt.ticket_id=%s
            ORDER BY u.username ASC
        """, (tid,))
        asignados = cur.fetchall()

        cur.execute("""
            SELECT id, ruta
            FROM ticket_attachments
            WHERE ticket_id=%s
            ORDER BY id ASC
        """, (tid,))
        raw_adj = cur.fetchall() or []

        adjuntos = []
        for a in raw_adj:
            fname = os.path.basename(a.get("ruta") or "")
            if fname:
                adjuntos.append({
                    "id": a["id"],
                    "name": fname,
                    "url": url_for("serve_ticket_upload", fname=fname)
                })

    finally:
        cur.close()

    if not head:
        return jsonify({"ok": False, "msg": "Ticket no encontrado"}), 404

    return jsonify({
        "ok": True,
        "ticket": serialize_rows([head])[0],
        "notas": serialize_rows(notas),
        "asignados": serialize_rows(asignados),
        "adjuntos": adjuntos
    }), 200

@app.post("/api/tecnico/tickets/<int:tid>/tomar")
@login_required
@role_required("TECNICO")
def api_tecnico_tomar_ticket(tid):
    uid = session["user_id"]
    cur = conexion.connection.cursor()
    try:
        cur.execute("""
            INSERT IGNORE INTO ticket_tecnicos (ticket_id, user_id)
            VALUES (%s, %s)
        """, (tid, uid))
        cur.execute("""
            UPDATE tickets
               SET estado = IF(estado='PENDIENTE', 'EN_CURSO', estado),
                   asignado_a = COALESCE(asignado_a, %s)
             WHERE id = %s
        """, (uid, tid))
        conexion.connection.commit()
    finally:
        cur.close()
    return jsonify({"ok": True}), 200

@app.post("/api/tecnico/tickets/<int:tid>/asignar")
@login_required
@role_required("TECNICO")
def api_tecnico_asignar_otro(tid):
    uid = session["user_id"]
    data = request.get_json(force=True)
    otros_raw = data.get("usuario_ids") or []
    otros = to_int_list(otros_raw)
    if not isinstance(otros_raw, list) or otros is None:
        return jsonify({"ok": False, "msg": "usuario_ids inválidos"}), 400

    cur = conexion.connection.cursor()
    try:
        cur.execute("SELECT 1 FROM ticket_tecnicos WHERE ticket_id=%s AND user_id=%s", (tid, uid))
        if not cur.fetchone():
            return jsonify({"ok": False, "msg": "No autorizado"}), 403

        for t_id in otros:
            cur.execute("""
                INSERT IGNORE INTO ticket_tecnicos (ticket_id, user_id)
                VALUES (%s, %s)
            """, (tid, t_id))
        conexion.connection.commit()
    finally:
        cur.close()
    return jsonify({"ok": True}), 200

@app.patch("/api/tecnico/tickets/<int:tid>/estado")
@login_required
@role_required("TECNICO")
def api_tecnico_cambiar_estado(tid):
    uid = session["user_id"]
    payload = request.get_json(force=True) or {}
    estado = (payload.get("estado") or "").upper()
    nota   = (payload.get("nota") or "").strip()

    if estado not in ("EN_CURSO", "RESUELTO", "CANCELADO"):
        return jsonify({"ok": False, "msg": "Estado inválido"}), 400
    if estado == "RESUELTO" and not nota:
        return jsonify({"ok": False, "msg": "Observaciones obligatorias para resolver."}), 400

    cur = conexion.connection.cursor()
    try:
        cur.execute("SELECT 1 FROM ticket_tecnicos WHERE ticket_id=%s AND user_id=%s", (tid, uid))
        if not cur.fetchone():
            return jsonify({"ok": False, "msg": "No autorizado"}), 403

        if estado in ("RESUELTO","CANCELADO"):
            cur.execute("""
                UPDATE tickets
                   SET estado=%s, cerrado_en=NOW()
                 WHERE id=%s
            """, (estado, tid))
        else:
            cur.execute("UPDATE tickets SET estado=%s WHERE id=%s", (estado, tid))

        if nota:
            cur.execute("""
                INSERT INTO ticket_notas (ticket_id, usuario_id, texto)
                VALUES (%s, %s, %s)
            """, (tid, uid, nota))

        conexion.connection.commit()
    finally:
        cur.close()

    return jsonify({"ok": True}), 200

@app.post("/api/tecnico/tickets/<int:tid>/nota")
@login_required
@role_required("TECNICO")
def api_tecnico_agregar_nota(tid):
    texto = (request.get_json(force=True).get("texto") or "").strip()
    if not texto:
        return jsonify({"ok": False, "msg": "Texto requerido"}), 400

    cur = conexion.connection.cursor()
    try:
        cur.execute("""
            INSERT INTO ticket_notas (ticket_id, usuario_id, texto)
            VALUES (%s, %s, %s)
        """, (tid, session["user_id"], texto))
        conexion.connection.commit()
    finally:
        cur.close()
    return jsonify({"ok": True}), 201

@app.post("/api/tecnico/tickets/<int:tid>/evidencia")
@login_required
@role_required("TECNICO")
def api_tecnico_subir_evidencia(tid):
    uid = session["user_id"]
    cur = conexion.connection.cursor()
    try:
        cur.execute("SELECT 1 FROM ticket_tecnicos WHERE ticket_id=%s AND user_id=%s", (tid, uid))
        if not cur.fetchone():
            return jsonify({"ok": False, "msg": "No autorizado"}), 403

        files = request.files.getlist("imagenes")
        if not files:
            return jsonify({"ok": False, "msg": "No se enviaron imágenes."}), 400

        saved_urls = []
        subdir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], "tickets")
        os.makedirs(subdir, exist_ok=True)

        now = datetime.now().strftime("%Y%m%d%H%M%S")
        count = 0
        for f in files:
            if count >= 3: break
            if not f or not (f.mimetype or "").startswith("image/"):
                continue
            name, ext = os.path.splitext(f.filename or "img")
            safe_base = re.sub(r'[^a-zA-Z0-9._-]+','_', name)[:40]
            fname = f"{tid}_{now}_{count}{ext.lower()}"
            path = os.path.join(subdir, fname)
            f.save(path)
            cur.execute("INSERT INTO ticket_attachments (ticket_id, ruta) VALUES (%s, %s)", (tid, path))
            saved_urls.append(url_for("serve_ticket_upload", fname=fname))
            count += 1

        if count == 0:
            return jsonify({"ok": False, "msg": "Archivos inválidos."}), 400

        conexion.connection.commit()
        return jsonify({"ok": True, "urls": saved_urls, "count": count}), 201

    finally:
        cur.close()

# ====================== Encuesta ======================
@app.get("/api/encuestas/pending")
@login_required
@role_required("SOLICITANTE")
def api_encuestas_pending():
    incluir_cancelados = False  # cambia a True si también quieres obligar en CANCELADO
    rows = _encuestas_pendientes(session["user_id"], incluir_cancelados=incluir_cancelados)
    return jsonify({"ok": True, "count": len(rows), "tickets": serialize_rows(rows)}), 200

@app.route("/solicitante/encuesta/<int:ticket_id>")
@login_required
@role_required("SOLICITANTE")
def solicitante_encuesta_view(ticket_id):
    # Ticket + área + tipo + técnicos
    cur = conexion.connection.cursor()
    try:
        cur.execute("""
            SELECT t.id, t.usuario_id, t.estado, t.creado_en, t.cerrado_en,
                   t.solicitante_nombre, t.asunto AS tipo_servicio, a.nombre AS area_nombre
            FROM tickets t
            LEFT JOIN areas a ON a.id = t.area_id
            WHERE t.id=%s
            LIMIT 1
        """, (ticket_id,))
        t = cur.fetchone()
    finally:
        cur.close()

    if not t:
        return "Ticket no encontrado", 404
    if t["usuario_id"] != session["user_id"]:
        return "No autorizado", 403
    if t["estado"] not in ("RESUELTO","CANCELADO"):
        return "La encuesta está disponible cuando el ticket está RESUELTO o CANCELADO.", 400

    # Evitar duplicado
    cur = conexion.connection.cursor()
    try:
        cur.execute("SELECT id FROM encuestas WHERE ticket_id=%s", (ticket_id,))
        e = cur.fetchone()
    finally:
        cur.close()
    if e:
        return "Este ticket ya tiene encuesta registrada.", 409

    # Momento de asignación + técnicos
    cur = conexion.connection.cursor()
    try:
        cur.execute("""
            SELECT MIN(creado_en) AS asignado_en
            FROM ticket_tecnicos
            WHERE ticket_id=%s
        """, (ticket_id,))
        tt = cur.fetchone() or {}

        cur.execute("""
            SELECT GROUP_CONCAT(u.username ORDER BY u.username SEPARATOR ', ') AS tecnicos
            FROM ticket_tecnicos tt
            JOIN users u ON u.id = tt.user_id
            WHERE tt.ticket_id=%s
        """, (ticket_id,))
        tech = cur.fetchone() or {}
    finally:
        cur.close()

    asignado_en = tt.get("asignado_en")
    creado_en   = t["creado_en"]
    cerrado_en  = t["cerrado_en"]

    hora_solicitud = creado_en.strftime("%Y-%m-%d %H:%M:%S") if creado_en else "-"
    hora_cierre    = cerrado_en.strftime("%Y-%m-%d %H:%M:%S") if cerrado_en else "-"
    t_tecnico      = _fmt_hms((cerrado_en - asignado_en) if (cerrado_en and asignado_en) else None)

    return render_template(
        "solicitante/encuesta.html",
        folio=ticket_id,
        ticket_id=ticket_id,
        solicitante=t["solicitante_nombre"],
        area_nombre=t["area_nombre"] or "-",
        estado=t["estado"],
        hora_solicitud=hora_solicitud,
        hora_cierre=hora_cierre,
        t_tecnico=t_tecnico,
        tipo_servicio=t["tipo_servicio"] or "-",
        tecnicos_str=(tech.get("tecnicos") or "-")
    )

@app.post("/api/encuestas")
@login_required
@role_required("SOLICITANTE")
def api_encuestas_create():
    try:
        f = request.form
        ticket_id = f.get("ticket_id", type=int)
        if not ticket_id:
            return jsonify(ok=False, error="Falta ticket_id"), 400

        # Datos del ticket y reglas
        cur = conexion.connection.cursor()
        try:
            cur.execute("""
                SELECT usuario_id, estado, creado_en, cerrado_en
                FROM tickets
                WHERE id=%s
                LIMIT 1
            """, (ticket_id,))
            t = cur.fetchone()
            if not t:
                cur.close(); return jsonify(ok=False, error="Ticket no encontrado"), 404
            if t["usuario_id"] != session["user_id"]:
                cur.close(); return jsonify(ok=False, error="No autorizado"), 403
            if t["estado"] not in ("RESUELTO","CANCELADO"):
                cur.close(); return jsonify(ok=False, error="Solo permitido con ticket RESUELTO o CANCELADO"), 400

            # Única encuesta por ticket
            cur.execute("SELECT id FROM encuestas WHERE ticket_id=%s", (ticket_id,))
            if cur.fetchone():
                cur.close(); return jsonify(ok=False, error="Este ticket ya tiene encuesta"), 409
        except:
            cur.close(); raise

        # Primer momento de asignación
        cur2 = conexion.connection.cursor()
        try:
            cur2.execute("""
                SELECT MIN(creado_en) AS asignado_en
                FROM ticket_tecnicos
                WHERE ticket_id=%s
            """, (ticket_id,))
            asg = cur2.fetchone() or {}
        finally:
            cur2.close()

        creado_en   = t["creado_en"]
        cerrado_en  = t["cerrado_en"]
        asignado_en = asg.get("asignado_en")

        def _fmt(delta):
            if not delta: return None
            s = int(delta.total_seconds()); s = max(s,0)
            h, rem = divmod(s, 3600)
            m, s2  = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s2:02d}"

        t_servicio = _fmt((cerrado_en - creado_en) if (cerrado_en and creado_en) else None)      # creación → cierre
        t_atencion = _fmt((cerrado_en - asignado_en) if (cerrado_en and asignado_en) else None)  # asignación → cierre
        atendida   = 'si' if t["estado"] == 'RESUELTO' else 'no'

        # Calificaciones (1–5) y Sí/No
        def _s15_key(k):
            try:
                v = int(f.get(k, ""))
                return v if 1 <= v <= 5 else None
            except: return None

        p2 = _s15_key("p2")
        p3 = _s15_key("p3")
        p4 = _s15_key("p4")

        q_rapidez             = _s15_key("q_rapidez")
        q_resolucion_efectiva = _s15_key("q_resolucion_efectiva")
        q_satis_solucion      = _s15_key("q_satis_solucion")
        q_satis_web           = _s15_key("q_satis_web")

        q_identificacion = (f.get("q_identificacion") or "").lower()
        if q_identificacion not in ("si","no"): q_identificacion = None

        # Campo obligatorio: sugerencias
        sugerencias = (f.get("q_sugerencias") or "").strip()
        if not sugerencias:
            return jsonify(ok=False, error="La pregunta de sugerencias es obligatoria."), 400

        # Comentarios generales (OPCIONAL)
        comentarios = (f.get("comentarios") or "").strip()

        # Empaquetamos TODO en 'descripcion' (no cambiamos esquema)
        partes = [f"SUGERENCIAS:\n{sugerencias}"]
        if comentarios:
            partes.append(f"COMENTARIOS:\n{comentarios}")
        extras = {
            "p2": p2, "p3": p3, "p4": p4,
            "q_rapidez": q_rapidez,
            "q_resolucion_efectiva": q_resolucion_efectiva,
            "q_satis_solucion": q_satis_solucion,
            "q_satis_web": q_satis_web,
            "q_identificacion": q_identificacion,
            "t_servicio": t_servicio,
            "t_atencion": t_atencion
        }
        partes.append("RESPUESTAS:\n" + str(extras))
        descripcion_final = "\n\n---\n\n".join(partes)

        # Inserción básica en encuestas
        cur = conexion.connection.cursor()
        cur.execute("""
            INSERT INTO encuestas
                (ticket_id, nombre,
                 t_servicio, t_atencion,
                 p2, p3, p4,
                 atendida, descripcion)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            ticket_id, None,
            t_servicio, t_atencion,
            p2, p3, p4,
            atendida, descripcion_final
        ))
        conexion.connection.commit()
        encuesta_id = cur.lastrowid
        cur.close()

        return jsonify(ok=True, encuesta_id=encuesta_id), 201

    except Exception as e:
        conexion.connection.rollback()
        return jsonify(ok=False, error=str(e)), 500

# Evidencias para la galería de encuesta
@app.get("/api/solicitante/tickets/<int:tid>/evidencias")
@login_required
@role_required("SOLICITANTE")
def api_solicitante_evidencias(tid):
    cur = conexion.connection.cursor()
    try:
        cur.execute("SELECT usuario_id FROM tickets WHERE id=%s", (tid,))
        t = cur.fetchone()
    finally:
        cur.close()
    if not t:
        return jsonify({"ok": False, "msg": "Ticket no encontrado"}), 404
    if t["usuario_id"] != session["user_id"]:
        return jsonify({"ok": False, "msg": "No autorizado"}), 403

    cur = conexion.connection.cursor()
    try:
        cur.execute("""
            SELECT id, ruta
            FROM ticket_attachments
            WHERE ticket_id=%s
            ORDER BY id ASC
        """, (tid,))
        raw = cur.fetchall() or []
    finally:
        cur.close()

    out = []
    for a in raw:
        fname = os.path.basename(a.get("ruta") or "")
        if fname:
            out.append({
                "id": a["id"],
                "name": fname,
                "url": url_for("serve_ticket_upload", fname=fname)
            })

    return jsonify({"ok": True, "evidencias": out}), 200

# -------- Main --------
if __name__ == "__main__":
    app.run(debug=True, port=5000)      
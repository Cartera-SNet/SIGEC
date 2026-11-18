"""
SIGEC - Sistema de Inventario y Gestión de Equipos de Cómputo
Aplicación Flask + PostgreSQL (Neon).  Ver docs/manual.md para el manual de uso.
"""
import io
import json
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

import psycopg2
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import asistente
import informes

VERSION = "1.0"

EN_NUBE = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"))
SESSION_SEGURA = EN_NUBE or os.environ.get("COOKIE_SECURE") == "1"

app = Flask(__name__)
if EN_NUBE or os.environ.get("TRUST_PROXY") == "1":  # detrás del proxy HTTPS de Railway
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=SESSION_SEGURA,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),  # RNF-01: la sesión expira tras 60 min de inactividad
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
)

ROLES = ["Administrador", "Operador", "Auditor", "Jefe", "Mantenimiento", "Empleado"]
# Permisos por rol. 'gestionar' = crear/editar inventario, asignar, firmar, registrar mantenimientos.
# 'mantener' = completar mantenimientos (el rol Mantenimiento solo completa los que tiene asignados).
PERMISOS = {
    "Administrador": {"ver", "gestionar", "reportes", "admin", "mantener"},
    "Operador": {"ver", "gestionar", "reportes", "mantener"},
    "Auditor": {"ver", "reportes"},
    "Jefe": {"ver", "reportes"},
    "Mantenimiento": {"ver", "mantener"},
    "Empleado": {"ver"},
}
ZONAS = {
    "America/Bogota": "(GMT-05:00) Bogotá",
    "America/Lima": "(GMT-05:00) Lima",
    "America/Mexico_City": "(GMT-06:00) Ciudad de México",
    "America/New_York": "(GMT-05:00) Nueva York",
    "America/Santiago": "(GMT-04:00) Santiago",
    "America/Argentina/Buenos_Aires": "(GMT-03:00) Buenos Aires",
    "Europe/Madrid": "(GMT+01:00) Madrid",
}
CODIGO = "'EQ-' || LPAD({a}.id::text, 3, '0')"
POR_PAGINA = 10
EMPLEADO_OK = {"login", "logout", "cambiar_password", "mis_equipos", "listar_actas", "firmar_acta", "evidencia_acta",
               "imprimir_acta", "detalle_empleado", "manual", "subir_foto", "quitar_foto", "ver_foto", "api_asistente", "api_asistente_estado", "static"}
# El rol Mantenimiento solo accede al módulo de mantenimientos (y a su perfil, manual y asistente).
MANT_OK = {"login", "logout", "cambiar_password", "mantenimiento", "completar_mantenimiento", "manual", "subir_foto",
           "quitar_foto", "ver_foto", "api_asistente", "api_asistente_estado", "static"}
# Catálogos de listas desplegables: nombre -> (tabla donde se usa, columna, etiqueta)
CATALOGOS = {"marca": ("equipo", "marca", "marca"), "area": ("empleado", "area", "área")}
ESTADOS_BASE = {"Disponible", "Asignado", "En Mantenimiento", "En recepción", "Dado de baja"}
# En la nube (Railway) el disco del contenedor es temporal: DATA_DIR apunta a un volumen persistente (p. ej. /data)
DATA_DIR = os.environ.get("DATA_DIR") or db.BASE_DIR
EVIDENCIAS = os.path.join(DATA_DIR, "evidencias")
RESPALDOS = os.path.join(DATA_DIR, "respaldos")
FOTOS = os.path.join(DATA_DIR, "fotos")


# --------------------------------------------------------------------------- base de datos
def conn():
    if "db" not in g:
        g.db = db.connect()
    return g.db


def q(sql, params=()):
    cur = conn().cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def q1(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None


def ex(sql, params=(), returning=False):
    cur = conn().cursor()
    cur.execute(sql, params)
    row = cur.fetchone() if returning else None
    cur.close()
    return row


@app.teardown_appcontext
def cerrar_db(_exc):
    c = g.pop("db", None)
    if c is not None:
        try:
            if _exc:
                c.rollback()
            c.close()
        except Exception:
            pass


_cfg_cache = {"t": 0, "v": {}}


def config(force=False):
    if force or time.time() - _cfg_cache["t"] > 30 or not _cfg_cache["v"]:
        try:
            _cfg_cache["v"] = {r["clave"]: r["valor"] for r in q("SELECT clave, valor FROM configuracion")}
        except Exception:
            _cfg_cache["v"] = dict(db.CONFIG_DEFAULT)
        _cfg_cache["t"] = time.time()
    return {**db.CONFIG_DEFAULT, **_cfg_cache["v"]}


def ahora():
    try:
        tz = ZoneInfo(config().get("zona_horaria", "America/Bogota"))
        return datetime.now(tz).replace(tzinfo=None, microsecond=0)
    except Exception:
        return datetime.now().replace(microsecond=0)


def hoy():
    return ahora().date()


def estado_id(nombre):
    r = q1("SELECT id FROM estado_equipo WHERE nombre = %s", (nombre,))
    return r["id"] if r else None


def log_hist(equipo_id, evento, detalle, ant=None, nuevo=None, asignacion_id=None):
    ex("""INSERT INTO historial (equipo_id, tipo_evento, fecha, usuario, detalle, estado_anterior,
                               estado_nuevo, asignacion_id)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
       (equipo_id, evento, ahora(), session.get("username", "Sistema"), detalle, ant, nuevo, asignacion_id))


# --------------------------------------------------------------------------- seguridad
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


@app.before_request
def proteger():
    if request.endpoint in ("static", "health"):
        return
    if request.method == "POST":
        tok = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not tok or tok != session.get("_csrf"):
            flash("La sesión del formulario expiró. Intenta de nuevo.", "warning")
            return redirect(request.referrer or url_for("index"))
    if request.endpoint != "login" and ("uid" not in session or usuario_actual() is None):
        if request.path.startswith("/api/"):
            return jsonify(error="no autenticado"), 401
        return redirect(url_for("login", next=request.full_path if request.method == "GET" else None))
    u = usuario_actual()
    if u and u["rol"] == "Empleado" and request.endpoint not in EMPLEADO_OK:
        # Ficha sec. 6: el Empleado solo accede a sus propios equipos y actas.
        flash("No tienes permiso para acceder a esa sección.", "danger")
        return redirect(url_for("mis_equipos"))
    if u and u["rol"] == "Mantenimiento" and request.endpoint not in MANT_OK:
        flash("Tu rol solo tiene acceso al módulo de mantenimientos.", "danger")
        return redirect(url_for("mantenimiento"))


def usuario_actual():
    if "uid" not in session:
        return None
    if "u" not in g:
        g.u = q1("SELECT id, username, nombre_completo, rol, activo, empleado_id, foto FROM usuario WHERE id = %s", (session["uid"],))
        if not g.u or not g.u["activo"]:
            session.clear()
            g.u = None
    return g.u


def permitido(perm):
    u = usuario_actual()
    return bool(u and perm in PERMISOS.get(u["rol"], set()))


def requiere(perm):
    def deco(f):
        @wraps(f)
        def inner(*a, **kw):
            if not permitido(perm):
                flash("No tienes permiso para realizar esta acción.", "danger")
                return redirect(url_for("index"))
            return f(*a, **kw)
        return inner
    return deco


_intentos = {}


def _bloqueado(clave):
    ts = [t for t in _intentos.get(clave, []) if time.time() - t < 300]
    _intentos[clave] = ts
    return len(ts) >= 5


# --------------------------------------------------------------------------- plantillas
@app.template_filter("fecha")
def f_fecha(v):
    return v.strftime("%d/%m/%Y") if v else "-"


@app.template_filter("fechahora")
def f_fechahora(v):
    return v.strftime("%d/%m/%Y %H:%M") if v else "-"


@app.template_filter("iniciales")
def f_iniciales(nombre):
    partes = [p for p in (nombre or "?").split() if p]
    return (partes[0][0] + (partes[1][0] if len(partes) > 1 else "")).upper()


@app.template_filter("color_avatar")
def f_color_avatar(nombre):
    return ["#3b82f6", "#8b5cf6", "#a855f7", "#14b8a6", "#f97316", "#ec4899"][sum(map(ord, nombre or "?")) % 6]


@app.context_processor
def contexto():
    u = usuario_actual()
    ctx = {"usuario": u, "puede": permitido, "version": VERSION,
           "notif": [], "notif_total": 0, "cfg": {}, "ia_claude": False, "clave_inicial": bool(session.get("clave_inicial"))}
    if u and u["rol"] != "Empleado":
        cfg = config()
        ctx["cfg"] = cfg
        ctx["ia_claude"] = asistente.ia.disponible() and cfg.get("ia_externa", "1") == "1"
        try:
            es_mant = u["rol"] == "Mantenimiento"
            r = q1("""SELECT (SELECT COUNT(*) FROM acta WHERE estado='pendiente') AS actas,
                             (SELECT COUNT(*) FROM mantenimiento WHERE estado='En Proceso'
                                 AND (NOT %s OR responsable_id = %s)) AS mant""", (es_mant, u["id"]))
            if cfg.get("notif_actas") == "1" and r["actas"] and not es_mant:
                ctx["notif"].append({"icono": "bi-file-earmark-text", "texto": f"{r['actas']} acta(s) pendiente(s) de firma",
                                     "url": url_for("listar_actas")})
            if cfg.get("notif_mantenimiento") == "1" and r["mant"]:
                ctx["notif"].append({"icono": "bi-wrench", "texto": f"{r['mant']} mantenimiento(s) en proceso",
                                     "url": url_for("mantenimiento")})
            ctx["notif_total"] = sum(int(x["texto"].split()[0]) for x in ctx["notif"])
        except Exception:
            pass
    return ctx


def pagina(total, page, por=POR_PAGINA):
    paginas = max(1, -(-total // por))
    page = min(max(page, 1), paginas)
    nums = sorted({1, paginas, page - 1, page, page + 1} & set(range(1, paginas + 1)))
    out, prev = [], 0
    for n in nums:
        if n - prev > 1:
            out.append(None)
        out.append(n)
        prev = n
    desde = (page - 1) * por
    return {"page": page, "paginas": paginas, "nums": out, "offset": desde, "por": por,
            "desde": desde + 1 if total else 0, "hasta": min(desde + por, total), "total": total}


def pagina_int(nombre="page"):
    try:
        return int(request.args.get(nombre, 1))
    except ValueError:
        return 1


def url_con(**kw):
    args = {k: v for k, v in request.args.items() if k != "page"}
    args.update({k: v for k, v in kw.items() if v is not None})
    return url_for(request.endpoint, **request.view_args, **args)


app.jinja_env.globals["url_con"] = url_con
app.jinja_env.globals["csrf_token"] = csrf_token


def opciones(cat, actual=None):
    """Opciones activas de un catálogo (marca, área) para las listas desplegables; conserva el valor ya guardado."""
    if cat not in CATALOGOS:
        return []
    nombres = [r["nombre"] for r in q(f"SELECT nombre FROM {cat} WHERE activo ORDER BY lower(nombre)")]
    if actual and actual.lower() not in [n.lower() for n in nombres]:
        nombres.append(actual)
    return nombres


def _en_catalogo(cat, valor, actual=None):
    """True si el valor está vacío, es el que ya tenía el registro, o es una opción activa del catálogo."""
    if not valor or (actual and valor.lower() == actual.lower()):
        return True
    return bool(q1(f"SELECT 1 AS x FROM {cat} WHERE lower(nombre) = lower(%s) AND activo", (valor,)))


app.jinja_env.globals["opciones"] = opciones


# --------------------------------------------------------------------------- autenticación
def _next_seguro(destino):
    if destino and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return url_for("index")


@app.route("/health")
def health():
    """Comprobación de salud para Railway (con ?db=1 también prueba la base de datos)."""
    if request.args.get("db") == "1":
        try:
            q1("SELECT 1 AS ok")
        except Exception:
            return jsonify(estado="sin base de datos"), 503
    return jsonify(estado="ok", version=VERSION)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        clave = f"{username.lower()}|{request.remote_addr}"
        if _bloqueado(clave):
            flash("Demasiados intentos fallidos. Espera 5 minutos e intenta de nuevo.", "danger")
        else:
            u = q1("SELECT * FROM usuario WHERE lower(username) = lower(%s)", (username,))
            if u and u["activo"] and check_password_hash(u["password_hash"], password):
                _intentos.pop(clave, None)
                session.clear()
                session["uid"] = u["id"]
                session["username"] = u["username"]
                session.permanent = True
                csrf_token()
                # Aviso en pantalla mientras el administrador principal siga con la clave inicial publicada en el manual
                if _es_admin_principal(u) and check_password_hash(u["password_hash"], db.ADMIN_PASS):
                    session["clave_inicial"] = True
                return redirect(_next_seguro(request.args.get("next")))
            _intentos.setdefault(clave, []).append(time.time())
            flash("Usuario o contraseña incorrectos.", "danger")
    elif "uid" in session:
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("login"))


@app.route("/cuenta/foto", methods=["POST"])
def subir_foto():
    """Cada usuario sube su propia foto de perfil (PNG/JPG, se recorta a cuadrado)."""
    from PIL import Image, UnidentifiedImageError
    archivo = request.files.get("foto")
    datos = archivo.read() if archivo else b""
    destino = request.referrer or url_for("index")
    if not datos:
        flash("Selecciona una imagen.", "warning")
        return redirect(destino)
    if len(datos) > 4 * 1024 * 1024:
        flash("La foto supera el tamaño máximo de 4 MB.", "danger")
        return redirect(destino)
    try:
        im = Image.open(io.BytesIO(datos))
        if im.format not in ("PNG", "JPEG", "WEBP"):
            raise ValueError
        im = im.convert("RGB")
    except (UnidentifiedImageError, ValueError, OSError):
        flash("La foto debe ser una imagen PNG, JPG o WEBP.", "danger")
        return redirect(destino)
    lado = min(im.size)
    izq, sup = (im.width - lado) // 2, (im.height - lado) // 2
    im = im.crop((izq, sup, izq + lado, sup + lado)).resize((256, 256))
    os.makedirs(FOTOS, exist_ok=True)
    nombre = f"u{session['uid']}_{secrets.token_hex(5)}.jpg"
    im.save(os.path.join(FOTOS, nombre), "JPEG", quality=88)
    _borrar_foto(usuario_actual()["foto"])
    ex("UPDATE usuario SET foto = %s WHERE id = %s", (nombre, session["uid"]))
    conn().commit()
    flash("Foto de perfil actualizada.", "success")
    return redirect(destino)


def _borrar_foto(nombre):
    if nombre:
        try:
            os.remove(os.path.join(FOTOS, os.path.basename(nombre)))
        except OSError:
            pass


@app.route("/cuenta/foto/quitar", methods=["POST"])
def quitar_foto():
    _borrar_foto(usuario_actual()["foto"])
    ex("UPDATE usuario SET foto = NULL WHERE id = %s", (session["uid"],))
    conn().commit()
    flash("Foto de perfil eliminada.", "success")
    return redirect(request.referrer or url_for("index"))


@app.route("/foto/<int:uid>")
def ver_foto(uid):
    u = q1("SELECT foto FROM usuario WHERE id = %s", (uid,))
    if not u or not u["foto"]:
        abort(404)
    ruta = os.path.join(FOTOS, os.path.basename(u["foto"]))
    if not os.path.exists(ruta):
        abort(404)
    resp = send_file(ruta, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@app.route("/cuenta/password", methods=["POST"])
def cambiar_password():
    u = q1("SELECT * FROM usuario WHERE id = %s", (session["uid"],))
    actual, nueva, conf = (request.form.get(k, "") for k in ("actual", "nueva", "confirmar"))
    destino = url_for("configuracion", tab="seguridad") if permitido("admin") else url_for("index")
    if not check_password_hash(u["password_hash"], actual):
        flash("La contraseña actual no es correcta.", "danger")
    elif len(nueva) < 8:
        flash("La nueva contraseña debe tener al menos 8 caracteres.", "danger")
    elif nueva != conf:
        flash("La confirmación no coincide con la nueva contraseña.", "danger")
    else:
        ex("UPDATE usuario SET password_hash = %s WHERE id = %s", (generate_password_hash(nueva), u["id"]))
        conn().commit()
        session.pop("clave_inicial", None)
        flash("Contraseña actualizada correctamente.", "success")
    return redirect(destino)


# --------------------------------------------------------------------------- dashboard
def resumen():
    r = q1("""
        SELECT COUNT(*) FILTER (WHERE es.nombre <> 'Dado de baja') AS total,
               COUNT(*) FILTER (WHERE es.nombre = 'Disponible') AS disponibles,
               COUNT(*) FILTER (WHERE es.nombre = 'Asignado') AS asignados,
               COUNT(*) FILTER (WHERE es.nombre = 'En Mantenimiento') AS mantenimiento,
               COUNT(*) FILTER (WHERE es.nombre NOT IN ('Disponible','Asignado','En Mantenimiento','Dado de baja')) AS otros,
               COUNT(*) FILTER (WHERE es.nombre <> 'Dado de baja' AND e.fecha_ingreso >= %s) AS nuevos_mes
        FROM equipo e LEFT JOIN estado_equipo es ON es.id = e.estado_id""", (ahora() - timedelta(days=30),))
    r = dict(r)
    r["actas_pendientes"] = q1("SELECT COUNT(*) AS c FROM acta WHERE estado = 'pendiente'")["c"]
    return r


def datos_asistente(kind, arg=None):
    """Acceso a datos para el asistente de IA (fuera de una petición HTTP normal)."""
    if kind == "resumen":
        return resumen()
    if kind == "equipo":
        num = re.sub(r"\D", "", arg or "")
        if not num:
            return None
        e = q1(f"""SELECT {CODIGO.format(a='e')} AS codigo, e.numero_serie, e.marca, e.modelo, t.nombre AS tipo,
                          es.nombre AS estado,
                          (SELECT emp.nombres || ' ' || COALESCE(emp.apellidos,'') FROM asignacion a
                             JOIN empleado emp ON emp.id = a.empleado_id
                             WHERE a.equipo_id = e.id AND a.estado = 'activa' LIMIT 1) AS responsable
                   FROM equipo e LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                   LEFT JOIN estado_equipo es ON es.id = e.estado_id WHERE e.id = %s""", (int(num),))
        return dict(e) if e else None


@app.route("/")
def index():
    if usuario_actual()["rol"] == "Empleado":
        return redirect(url_for("mis_equipos"))
    if usuario_actual()["rol"] == "Mantenimiento":
        return redirect(url_for("mantenimiento"))
    r = resumen()
    total = r["total"] or 0

    def pct(x):
        return round(x * 100 / total, 1) if total else 0

    asignaciones = q("""
        SELECT a.id, a.fecha_asignacion, a.estado, emp.nombres || ' ' || COALESCE(emp.apellidos, '') AS empleado,
               TRIM(COALESCE(t.nombre,'') || ' ' || COALESCE(e.marca,'') || ' ' || COALESCE(e.modelo,'')) AS equipo
        FROM asignacion a JOIN empleado emp ON emp.id = a.empleado_id
        JOIN equipo e ON e.id = a.equipo_id LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
        ORDER BY a.fecha_asignacion DESC, a.id DESC LIMIT 4""")
    recientes = q(f"""
        SELECT e.id, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo, es.nombre AS estado,
               e.fecha_ingreso, emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS asignado
        FROM equipo e LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
        LEFT JOIN estado_equipo es ON es.id = e.estado_id
        LEFT JOIN asignacion a ON a.equipo_id = e.id AND a.estado = 'activa'
        LEFT JOIN empleado emp ON emp.id = a.empleado_id
        ORDER BY e.id DESC LIMIT 4""")
    return render_template("index.html", layout="home", r=r, pct=pct, asignaciones=asignaciones, recientes=recientes)


# --------------------------------------------------------------------------- equipos
def _fecha_arg(nombre):
    try:
        return datetime.strptime(request.args.get(nombre, ""), "%Y-%m-%d").date()
    except ValueError:
        return None


def _filtros_equipos():
    texto = request.args.get("q", "").strip()
    estado = request.args.get("estado", "").strip()
    tipo = request.args.get("tipo", "").strip()
    ubicacion = request.args.get("ubicacion", "").strip()
    desde, hasta = _fecha_arg("desde"), _fecha_arg("hasta")
    where, params = ["1=1"], []
    if tipo.isdigit():
        where.append("e.tipo_id = %s")
        params.append(int(tipo))
    if ubicacion:
        where.append("e.ubicacion ILIKE %s")
        params.append(f"%{ubicacion}%")
    if desde:
        where.append("e.fecha_ingreso >= %s")
        params.append(datetime.combine(desde, datetime.min.time()))
    if hasta:
        where.append("e.fecha_ingreso < %s")
        params.append(datetime.combine(hasta + timedelta(days=1), datetime.min.time()))
    if texto:
        like = f"%{texto}%"
        where.append(f"""({CODIGO.format(a='e')} ILIKE %s OR e.numero_serie ILIKE %s OR e.marca ILIKE %s OR e.modelo ILIKE %s
                         OR t.nombre ILIKE %s OR emp.nombres ILIKE %s OR emp.apellidos ILIKE %s)""")
        params += [like] * 7
    if estado:
        where.append("es.nombre = %s")
        params.append(estado)
    extra = {"tipo": tipo, "ubicacion": ubicacion, "desde": desde.isoformat() if desde else "",
             "hasta": hasta.isoformat() if hasta else ""}
    return " AND ".join(where), params, texto, estado, extra


@app.route("/equipos")
def listar_equipos():
    where, params, texto, estado, extra = _filtros_equipos()
    base = f"""FROM equipo e LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
               LEFT JOIN estado_equipo es ON es.id = e.estado_id
               LEFT JOIN asignacion a ON a.equipo_id = e.id AND a.estado = 'activa'
               LEFT JOIN empleado emp ON emp.id = a.empleado_id WHERE {where}"""
    total = q1("SELECT COUNT(*) AS c " + base, params)["c"]
    pg = pagina(total, pagina_int())
    equipos = q(f"""SELECT e.id, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo, e.numero_serie,
                           es.nombre AS estado, emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS asignado
                    {base} ORDER BY e.id DESC LIMIT %s OFFSET %s""", params + [pg["por"], pg["offset"]])
    estados = q("SELECT nombre FROM estado_equipo ORDER BY id")
    tipos = q("SELECT id, nombre FROM tipo_equipo ORDER BY nombre")
    return render_template("equipos.html", equipos=equipos, pg=pg, texto=texto, estado=estado, estados=estados,
                           tipos=tipos, f=extra)


def _placa_duplicada(placa, excluir=None):
    if not placa:
        return False
    return bool(q1("SELECT id FROM equipo WHERE lower(placa) = lower(%s) AND id <> %s", (placa, excluir or 0)))


def _form_equipo():
    f = request.form
    return {k: f.get(k, "").strip() for k in
            ("tipo_id", "estado", "marca", "modelo", "numero_serie", "placa", "ubicacion", "caracteristicas", "observaciones")}


@app.route("/equipos/nuevo", methods=["GET", "POST"])
@requiere("gestionar")
def nuevo_equipo():
    tipos = q("SELECT * FROM tipo_equipo WHERE activo ORDER BY nombre")
    if request.method == "POST":
        d = _form_equipo()
        if not d["numero_serie"] or not d["marca"] or not d["modelo"] or not d["tipo_id"].isdigit():
            flash("Tipo, marca, modelo y número de serie son obligatorios.", "danger")
        elif not _en_catalogo("marca", d["marca"]):
            flash("Selecciona una marca de la lista (el administrador puede agregar más en Configuración › Catálogos).", "danger")
        elif q1("SELECT id FROM equipo WHERE lower(numero_serie) = lower(%s)", (d["numero_serie"],)):
            flash("Error: el número de serie ya existe (RN-08).", "danger")
        elif _placa_duplicada(d["placa"]):
            flash("Error: la placa de inventario ya está registrada en otro equipo (RN-08).", "danger")
        else:
            estado = d["estado"] if d["estado"] in ("Disponible", "En recepción") else "Disponible"
            row = ex("""INSERT INTO equipo (tipo_id, marca, modelo, numero_serie, placa, ubicacion, caracteristicas,
                                            estado_id, fecha_ingreso, observaciones)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                     (int(d["tipo_id"]), d["marca"], d["modelo"], d["numero_serie"], d["placa"], d["ubicacion"],
                      d["caracteristicas"], estado_id(estado), ahora(), d["observaciones"]), returning=True)
            log_hist(row["id"], "Alta", "Equipo registrado", None, estado)
            conn().commit()
            flash("Equipo registrado correctamente.", "success")
            return redirect(url_for("listar_equipos"))
        return render_template("form_equipo.html", tipos=tipos, d=d, editar=False, estados_ok=["Disponible", "En recepción"])
    return render_template("form_equipo.html", tipos=tipos, d={"estado": "Disponible"}, editar=False,
                           estados_ok=["Disponible", "En recepción"])


def _equipo_o_404(equipo_id):
    e = q1(f"""SELECT e.*, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo_nombre, es.nombre AS estado_nombre
               FROM equipo e LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
               LEFT JOIN estado_equipo es ON es.id = e.estado_id WHERE e.id = %s""", (equipo_id,))
    if not e:
        abort(404)
    return e


@app.route("/equipos/<int:equipo_id>/editar", methods=["GET", "POST"])
@requiere("gestionar")
def editar_equipo(equipo_id):
    e = _equipo_o_404(equipo_id)
    tipos = q("SELECT * FROM tipo_equipo WHERE activo ORDER BY nombre")
    bloqueado = True
    estados_ok = []
    if request.method == "POST":
        d = _form_equipo()
        if not d["numero_serie"] or not d["marca"] or not d["modelo"] or not d["tipo_id"].isdigit():
            flash("Tipo, marca, modelo y número de serie son obligatorios.", "danger")
        elif not _en_catalogo("marca", d["marca"], e["marca"]):
            flash("Selecciona una marca de la lista (el administrador puede agregar más en Configuración › Catálogos).", "danger")
        elif q1("SELECT id FROM equipo WHERE lower(numero_serie) = lower(%s) AND id <> %s", (d["numero_serie"], equipo_id)):
            flash("Error: el número de serie ya existe (RN-08).", "danger")
        elif _placa_duplicada(d["placa"], equipo_id):
            flash("Error: la placa de inventario ya está registrada en otro equipo (RN-08).", "danger")
        else:
            nuevo_estado = e["estado_nombre"]  # el estado solo cambia con «Cambiar estado» (RN-06)
            ex("""UPDATE equipo SET tipo_id=%s, marca=%s, modelo=%s, numero_serie=%s, placa=%s, ubicacion=%s,
                         caracteristicas=%s, observaciones=%s, estado_id=%s, updated_at=%s WHERE id=%s""",
               (int(d["tipo_id"]), d["marca"], d["modelo"], d["numero_serie"], d["placa"], d["ubicacion"],
                d["caracteristicas"], d["observaciones"], estado_id(nuevo_estado), ahora(), equipo_id))
            log_hist(equipo_id, "Edición" if nuevo_estado == e["estado_nombre"] else "Cambio Estado",
                     "Datos del equipo actualizados", e["estado_nombre"], nuevo_estado)
            conn().commit()
            flash("Equipo actualizado correctamente.", "success")
            return redirect(url_for("detalle_equipo", equipo_id=equipo_id))
        return render_template("form_equipo.html", tipos=tipos, d=d, editar=True, e=e, bloqueado=bloqueado, estados_ok=estados_ok)
    d = {**e, "tipo_id": str(e["tipo_id"] or ""), "estado": e["estado_nombre"]}
    return render_template("form_equipo.html", tipos=tipos, d=d, editar=True, e=e, bloqueado=bloqueado, estados_ok=estados_ok)


@app.route("/equipos/<int:equipo_id>/baja", methods=["POST"])
@requiere("admin")
def baja_equipo(equipo_id):
    e = _equipo_o_404(equipo_id)
    if not request.form.get("motivo", "").strip():
        flash("Debes indicar el motivo de la baja (RN-06).", "danger")
    elif e["estado_nombre"] == "Dado de baja":
        flash("El equipo ya está dado de baja.", "warning")
    elif e["estado_nombre"] in ("Asignado", "En Mantenimiento"):
        flash("No se puede dar de baja un equipo asignado o en mantenimiento. Primero registra la devolución o termina el mantenimiento.", "danger")
    else:
        ex("UPDATE equipo SET estado_id=%s, updated_at=%s WHERE id=%s", (estado_id("Dado de baja"), ahora(), equipo_id))
        log_hist(equipo_id, "Baja", request.form.get("motivo", "").strip(),
                 e["estado_nombre"], "Dado de baja")
        conn().commit()
        flash(f"El equipo {e['codigo']} fue dado de baja. Su historial se conserva.", "success")
    return redirect(request.referrer or url_for("listar_equipos"))


@app.route("/equipos/<int:equipo_id>/estado", methods=["POST"])
@requiere("gestionar")
def cambiar_estado(equipo_id):
    """Cambio de estado manual con motivo obligatorio (RF-08, RN-06)."""
    q1("SELECT id FROM equipo WHERE id = %s FOR UPDATE", (equipo_id,))
    e = _equipo_o_404(equipo_id)
    ant, nuevo = e["estado_nombre"], request.form.get("estado", "").strip()
    motivo = request.form.get("motivo", "").strip()
    est = q1("SELECT nombre FROM estado_equipo WHERE nombre = %s AND activo", (nuevo,))
    if not motivo:
        flash("Debes indicar el motivo del cambio de estado (RN-06).", "danger")
    elif not est:
        flash("Selecciona un estado válido.", "danger")
    elif nuevo == ant:
        flash("El equipo ya está en ese estado.", "warning")
    elif ant == "Dado de baja":
        flash("Un equipo dado de baja no puede cambiar de estado.", "danger")
    elif nuevo == "Asignado":
        flash("Para dejar un equipo como Asignado usa la opción Asignar equipo (RN-01).", "danger")
    elif nuevo == "Dado de baja" and not permitido("admin"):
        flash("Solo el administrador puede dar de baja un equipo.", "danger")
    elif nuevo == "Dado de baja" and ant in ("Asignado", "En Mantenimiento"):
        flash("No se puede dar de baja un equipo asignado o en mantenimiento. Primero registra la devolución o termina el mantenimiento.", "danger")
    else:
        asg = q1("SELECT id FROM asignacion WHERE equipo_id = %s AND estado = 'activa' FOR UPDATE", (equipo_id,))
        if asg:  # pérdida, daño u otro motivo: la asignación activa se cierra
            ex("UPDATE asignacion SET estado='cerrada', fecha_devolucion=%s WHERE id=%s", (ahora(), asg["id"]))
        if ant == "En Mantenimiento":
            ex("UPDATE mantenimiento SET estado='Completado', fecha_fin=%s WHERE equipo_id=%s AND estado='En Proceso'",
               (ahora(), equipo_id))
        if nuevo == "En Mantenimiento":
            ex("INSERT INTO mantenimiento (equipo_id, tipo, fecha, descripcion, created_by) VALUES (%s,'Correctivo',%s,%s,%s)",
               (equipo_id, hoy(), motivo, session.get("username")))
        ex("UPDATE equipo SET estado_id=%s, updated_at=%s WHERE id=%s", (estado_id(nuevo), ahora(), equipo_id))
        log_hist(equipo_id, "Baja" if nuevo == "Dado de baja" else "Cambio Estado", motivo, ant, nuevo,
                 asg["id"] if asg else None)
        conn().commit()
        flash(f"Estado actualizado: {ant} → {nuevo}." + (" La asignación activa fue cerrada." if asg else ""), "success")
        return redirect(url_for("detalle_equipo", equipo_id=equipo_id))
    conn().rollback()
    return redirect(url_for("detalle_equipo", equipo_id=equipo_id))


@app.route("/equipo/<int:equipo_id>")
def detalle_equipo(equipo_id):
    e = _equipo_o_404(equipo_id)
    historial = q("SELECT * FROM historial WHERE equipo_id = %s ORDER BY fecha DESC, id DESC", (equipo_id,))
    asignacion = q1("""SELECT a.*, emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS empleado_nombre
                       FROM asignacion a JOIN empleado emp ON emp.id = a.empleado_id
                       WHERE a.equipo_id = %s AND a.estado = 'activa'""", (equipo_id,))
    estados = q("SELECT nombre FROM estado_equipo WHERE activo AND nombre <> 'Asignado' ORDER BY id")
    return render_template("detalle_equipo.html", e=e, historial=historial, asignacion=asignacion, estados=estados)


# --------------------------------------------------------------------------- empleados
@app.route("/empleados")
def listar_empleados():
    texto = request.args.get("q", "").strip()
    like = f"%{texto}%"
    where, params = ("TRUE", []) if not texto else (
        "(documento ILIKE %s OR nombres ILIKE %s OR apellidos ILIKE %s OR area ILIKE %s OR cargo ILIKE %s)", [like] * 5)
    total = q1(f"SELECT COUNT(*) AS c FROM empleado WHERE {where}", params)["c"]
    pg = pagina(total, pagina_int())
    empleados = q(f"""SELECT emp.*, (SELECT COUNT(*) FROM asignacion a WHERE a.empleado_id = emp.id AND a.estado='activa') AS equipos
                      FROM empleado emp WHERE {where} ORDER BY nombres, apellidos LIMIT %s OFFSET %s""",
                  params + [pg["por"], pg["offset"]])
    return render_template("empleados.html", empleados=empleados, pg=pg, texto=texto)


@app.route("/empleados/<int:emp_id>")
def detalle_empleado(emp_id):
    emp = q1("SELECT * FROM empleado WHERE id = %s", (emp_id,))
    if not emp:
        abort(404)
    if not permitido("gestionar") and not (usuario_actual()["empleado_id"] == emp_id):
        flash("Solo puedes consultar tu propia ficha.", "danger")
        return redirect(url_for("mis_equipos"))
    return render_template("detalle_empleado.html", emp=emp, **_equipos_de(emp_id))


def _equipos_de(emp_id):
    base = f"""SELECT a.id, a.fecha_asignacion, a.fecha_devolucion, a.estado, {CODIGO.format(a='e')} AS codigo,
                      e.id AS equipo_id, e.numero_serie, t.nombre AS tipo, e.marca, e.modelo,
                      (SELECT ac.id FROM acta ac WHERE ac.asignacion_id = a.id ORDER BY ac.id LIMIT 1) AS acta_id,
                      (SELECT ac.estado FROM acta ac WHERE ac.asignacion_id = a.id ORDER BY ac.id LIMIT 1) AS acta_estado
               FROM asignacion a JOIN equipo e ON e.id = a.equipo_id LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
               WHERE a.empleado_id = %s AND a.estado = %s ORDER BY a.fecha_asignacion DESC"""
    return {"activas": q(base, (emp_id, "activa")), "historico": q(base, (emp_id, "cerrada"))}


@app.route("/mis-equipos")
def mis_equipos():
    u = usuario_actual()
    emp = q1("SELECT * FROM empleado WHERE id = %s", (u["empleado_id"],)) if u["empleado_id"] else None
    return render_template("mis_equipos.html", emp=emp, **(_equipos_de(emp["id"]) if emp else {"activas": [], "historico": []}))


def _form_empleado():
    return {k: request.form.get(k, "").strip() for k in
            ("documento", "nombres", "apellidos", "area", "cargo", "correo", "telefono", "estado")}


@app.route("/empleados/nuevo", methods=["GET", "POST"])
@requiere("gestionar")
def nuevo_empleado():
    if request.method == "POST":
        d = _form_empleado()
        if not d["documento"] or not d["nombres"]:
            flash("Documento y nombres son obligatorios.", "danger")
        elif not _en_catalogo("area", d["area"]):
            flash("Selecciona un área de la lista (el administrador puede agregar más en Configuración › Catálogos).", "danger")
        elif q1("SELECT id FROM empleado WHERE documento = %s", (d["documento"],)):
            flash("Ya existe un empleado con ese documento.", "danger")
        else:
            ex("""INSERT INTO empleado (documento, nombres, apellidos, area, cargo, correo, telefono, estado, fecha_ingreso)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
               (d["documento"], d["nombres"], d["apellidos"], d["area"], d["cargo"], d["correo"], d["telefono"],
                "inactivo" if d["estado"] == "inactivo" else "activo", hoy()))
            conn().commit()
            flash("Empleado registrado correctamente.", "success")
            return redirect(url_for("listar_empleados"))
        return render_template("form_empleado.html", d=d, editar=False)
    return render_template("form_empleado.html", d={"estado": "activo"}, editar=False)


@app.route("/empleados/<int:emp_id>/editar", methods=["GET", "POST"])
@requiere("gestionar")
def editar_empleado(emp_id):
    emp = q1("SELECT * FROM empleado WHERE id = %s", (emp_id,))
    if not emp:
        abort(404)
    if request.method == "POST":
        d = _form_empleado()
        activos = q1("SELECT COUNT(*) AS c FROM asignacion WHERE empleado_id=%s AND estado='activa'", (emp_id,))["c"]
        if not d["documento"] or not d["nombres"]:
            flash("Documento y nombres son obligatorios.", "danger")
        elif not _en_catalogo("area", d["area"], emp["area"]):
            flash("Selecciona un área de la lista (el administrador puede agregar más en Configuración › Catálogos).", "danger")
        elif q1("SELECT id FROM empleado WHERE documento = %s AND id <> %s", (d["documento"], emp_id)):
            flash("Ya existe otro empleado con ese documento.", "danger")
        elif d["estado"] == "inactivo" and activos:
            flash("No se puede inactivar a un empleado con equipos asignados. Registra primero las devoluciones.", "danger")
        else:
            ex("""UPDATE empleado SET documento=%s, nombres=%s, apellidos=%s, area=%s, cargo=%s, correo=%s,
                         telefono=%s, estado=%s, updated_at=%s WHERE id=%s""",
               (d["documento"], d["nombres"], d["apellidos"], d["area"], d["cargo"], d["correo"], d["telefono"],
                "inactivo" if d["estado"] == "inactivo" else "activo", ahora(), emp_id))
            conn().commit()
            flash("Empleado actualizado correctamente.", "success")
            return redirect(url_for("listar_empleados"))
        return render_template("form_empleado.html", d=d, editar=True, emp=emp)
    return render_template("form_empleado.html", d=emp, editar=True, emp=emp)


# --------------------------------------------------------------------------- asignaciones y actas
@app.route("/asignar", methods=["GET", "POST"])
@requiere("gestionar")
def asignar_equipo():
    if request.method == "POST":
        equipo_id = request.form.get("equipo_id", "")
        empleado_id = request.form.get("empleado_id", "")
        if not equipo_id.isdigit() or not empleado_id.isdigit():
            flash("Selecciona un empleado y un equipo.", "danger")
            return redirect(url_for("asignar_equipo"))
        try:
            f = datetime.strptime(request.form.get("fecha", ""), "%Y-%m-%d").date()
        except ValueError:
            f = hoy()
        if f > hoy():
            flash("La fecha de asignación no puede ser futura.", "danger")
            return redirect(url_for("asignar_equipo"))
        # Bloqueo de fila: evita asignar dos veces el mismo equipo si dos personas lo intentan a la vez.
        equipo = q1("""SELECT e.id, es.nombre AS estado_nombre FROM equipo e JOIN estado_equipo es ON es.id = e.estado_id
                       WHERE e.id = %s FOR UPDATE OF e""", (int(equipo_id),))
        emp = q1("SELECT * FROM empleado WHERE id = %s", (int(empleado_id),))
        if not equipo or equipo["estado_nombre"] != "Disponible":
            flash("Error: solo se pueden asignar equipos en estado Disponible (RN-01).", "danger")
        elif not emp or emp["estado"] != "activo":
            flash("Error: solo se puede asignar a empleados activos (RN-05).", "danger")
        else:
            momento = datetime.combine(f, ahora().time())
            asg = ex("""INSERT INTO asignacion (equipo_id, empleado_id, fecha_asignacion, estado, observaciones, created_by)
                        VALUES (%s,%s,%s,'activa',%s,%s) RETURNING id""",
                     (equipo["id"], emp["id"], momento, request.form.get("observaciones", "").strip(),
                      session.get("username")), returning=True)
            ex("UPDATE equipo SET estado_id=%s, updated_at=%s WHERE id=%s", (estado_id("Asignado"), ahora(), equipo["id"]))
            ex("INSERT INTO acta (asignacion_id, fecha_generacion, estado) VALUES (%s,%s,'pendiente')", (asg["id"], ahora()))
            log_hist(equipo["id"], "Asignación", f"Asignado a {emp['nombres']} {emp['apellidos'] or ''}".strip(),
                     "Disponible", "Asignado", asg["id"])
            conn().commit()
            return redirect(url_for("entrega_exitosa", asignacion_id=asg["id"]))
        conn().rollback()
        return redirect(url_for("asignar_equipo"))

    disponibles = q(f"""SELECT e.id, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo
                        FROM equipo e JOIN estado_equipo es ON es.id = e.estado_id
                        LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                        WHERE es.nombre = 'Disponible' ORDER BY e.id""")
    empleados = q("SELECT id, nombres, apellidos, documento, area FROM empleado WHERE estado = 'activo' ORDER BY nombres")
    activas = q(f"""SELECT a.id, a.fecha_asignacion, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo,
                           emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS empleado
                    FROM asignacion a JOIN equipo e ON e.id = a.equipo_id JOIN empleado emp ON emp.id = a.empleado_id
                    LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                    WHERE a.estado = 'activa' ORDER BY a.fecha_asignacion DESC LIMIT 50""")
    return render_template("asignar.html", disponibles=disponibles, empleados=empleados, activas=activas,
                           hoy=hoy(), preseleccion=request.args.get("equipo", ""))


@app.route("/asignaciones/<int:asig_id>/devolver", methods=["POST"])
@requiere("gestionar")
def devolver_equipo(asig_id):
    a = q1("SELECT * FROM asignacion WHERE id = %s FOR UPDATE", (asig_id,))
    if not a or a["estado"] != "activa":
        flash("La asignación no existe o ya fue cerrada.", "warning")
    else:
        d = request.form.get("destino", "")
        destino = {"recepcion": "En recepción", "En recepción": "En recepción", "En Mantenimiento": "En Mantenimiento"}.get(d, "Disponible")
        ex("UPDATE asignacion SET estado='cerrada', fecha_devolucion=%s WHERE id=%s", (ahora(), asig_id))
        if destino == "En Mantenimiento":
            ex("INSERT INTO mantenimiento (equipo_id, tipo, fecha, descripcion, created_by) VALUES (%s,'Correctivo',%s,%s,%s)",
               (a["equipo_id"], hoy(), request.form.get("observaciones", "").strip() or "Revisión tras devolución",
                session.get("username")))
        ex("UPDATE equipo SET estado_id=%s, updated_at=%s WHERE id=%s", (estado_id(destino), ahora(), a["equipo_id"]))
        log_hist(a["equipo_id"], "Devolución", request.form.get("observaciones", "").strip() or "Equipo devuelto por el empleado",
                 "Asignado", destino, asig_id)
        conn().commit()
        flash(f"Devolución registrada. El equipo quedó en estado «{destino}».", "success")
    return redirect(url_for("asignar_equipo"))


@app.route("/entrega/<int:asignacion_id>")
def entrega_exitosa(asignacion_id):
    a = q1(f"""SELECT a.id, a.fecha_asignacion, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo,
                      emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS empleado,
                      (SELECT id FROM acta WHERE asignacion_id = a.id ORDER BY id LIMIT 1) AS acta_id
               FROM asignacion a JOIN equipo e ON e.id = a.equipo_id JOIN empleado emp ON emp.id = a.empleado_id
               LEFT JOIN tipo_equipo t ON t.id = e.tipo_id WHERE a.id = %s""", (asignacion_id,))
    if not a:
        abort(404)
    return render_template("entrega_exitosa.html", a=a)


@app.route("/actas")
def listar_actas():
    estado = request.args.get("estado", "")
    conds, params = [], []
    if estado in ("pendiente", "firmada"):
        conds.append("ac.estado = %s")
        params.append(estado)
    if not (permitido("gestionar") or permitido("reportes")):  # Empleado: solo sus actas
        conds.append("a.empleado_id = %s")
        params.append(usuario_actual()["empleado_id"] or 0)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = q1(f"SELECT COUNT(*) AS c FROM acta ac JOIN asignacion a ON a.id = ac.asignacion_id {where}", params)["c"]
    pg = pagina(total, pagina_int())
    actas = q(f"""SELECT ac.*, a.empleado_id AS emp_id, {CODIGO.format(a='e')} AS codigo, e.numero_serie,
                         emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS empleado_nombre
                  FROM acta ac JOIN asignacion a ON a.id = ac.asignacion_id JOIN equipo e ON e.id = a.equipo_id
                  JOIN empleado emp ON emp.id = a.empleado_id {where}
                  ORDER BY ac.id DESC LIMIT %s OFFSET %s""", params + [pg["por"], pg["offset"]])
    return render_template("actas.html", actas=actas, pg=pg, estado=estado)


def _acta_firma(acta_id):
    return q1(f"""SELECT ac.*, a.estado AS asig_estado, a.empleado_id, a.equipo_id, a.fecha_asignacion,
                         {CODIGO.format(a='e')} AS codigo, e.marca, e.modelo, t.nombre AS tipo,
                         emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS empleado_nombre
                  FROM acta ac JOIN asignacion a ON a.id = ac.asignacion_id JOIN equipo e ON e.id = a.equipo_id
                  JOIN empleado emp ON emp.id = a.empleado_id LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                  WHERE ac.id = %s""", (acta_id,))


def _puede_firmar(acta):
    u = usuario_actual()
    return permitido("gestionar") or bool(u["empleado_id"] and u["empleado_id"] == acta["empleado_id"])


_MAGIC = {b"%PDF": "pdf", b"\x89PNG": "png", b"\xff\xd8\xff": "jpg"}


def _guardar_evidencia(archivo, acta_id):
    if not archivo or not archivo.filename:
        return None, None
    datos = archivo.read()
    if not datos:
        return None, None
    ext = next((v for k, v in _MAGIC.items() if datos.startswith(k)), None)
    if not ext:
        return None, "La evidencia debe ser una imagen PNG/JPG o un PDF."
    if len(datos) > 5 * 1024 * 1024:
        return None, "La evidencia supera el tamaño máximo de 5 MB."
    os.makedirs(EVIDENCIAS, exist_ok=True)
    nombre = f"acta{acta_id}_{secrets.token_hex(6)}.{ext}"
    with open(os.path.join(EVIDENCIAS, nombre), "wb") as fh:
        fh.write(datos)
    return nombre, None


@app.route("/actas/<int:acta_id>/firmar", methods=["GET", "POST"])
def firmar_acta(acta_id):
    acta = _acta_firma(acta_id)
    if not acta:
        abort(404)
    if not _puede_firmar(acta):
        flash("No tienes permiso para firmar esta acta.", "danger")
        return redirect(url_for("listar_actas"))
    if request.method == "POST":
        q1("SELECT id FROM acta WHERE id = %s FOR UPDATE", (acta_id,))
        acta = _acta_firma(acta_id)
        if acta["estado"] == "firmada":
            flash("El acta ya está firmada.", "warning")
        elif acta["asig_estado"] != "activa":
            flash("No se puede firmar: la asignación ya fue cerrada (RN-04).", "danger")
        else:
            nombre, err = _guardar_evidencia(request.files.get("evidencia"), acta_id)
            if err:
                flash(err, "danger")
                return render_template("firmar_acta.html", acta=acta)
            firmante = request.form.get("firmado_por", "").strip() or acta["empleado_nombre"]
            ex("""UPDATE acta SET estado='firmada', fecha_firma=%s, firmado_por=%s, evidencia_path=%s, observaciones=%s
                  WHERE id=%s""", (ahora(), firmante[:150], nombre, request.form.get("observaciones", "").strip(), acta_id))
            log_hist(acta["equipo_id"], "Firma de acta",
                     f"Acta #{acta_id} firmada por {firmante[:150]}" + (" con evidencia adjunta" if nombre else ""),
                     asignacion_id=acta["asignacion_id"])
            conn().commit()
            flash("Acta firmada correctamente." + (" La evidencia quedó registrada." if nombre else ""), "success")
        return redirect(url_for("listar_actas") if permitido("gestionar") else url_for("mis_equipos"))
    return render_template("firmar_acta.html", acta=acta)


@app.route("/actas/<int:acta_id>/evidencia")
def evidencia_acta(acta_id):
    acta = _acta_firma(acta_id)
    if not acta or not acta["evidencia_path"] or not _puede_firmar(acta) and not permitido("reportes"):
        abort(404)
    ruta = os.path.join(EVIDENCIAS, os.path.basename(acta["evidencia_path"]))
    if not os.path.exists(ruta):
        abort(404)
    return send_file(ruta)


@app.route("/actas/<int:acta_id>/imprimir")
def imprimir_acta(acta_id):
    a = q1(f"""SELECT ac.*, a.empleado_id, a.fecha_asignacion, a.observaciones AS obs_asignacion, {CODIGO.format(a='e')} AS codigo,
                      e.numero_serie, e.marca, e.modelo, e.placa, t.nombre AS tipo,
                      emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS empleado, emp.documento, emp.area, emp.cargo
               FROM acta ac JOIN asignacion a ON a.id = ac.asignacion_id JOIN equipo e ON e.id = a.equipo_id
               JOIN empleado emp ON emp.id = a.empleado_id LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
               WHERE ac.id = %s""", (acta_id,))
    if not a:
        abort(404)
    u = usuario_actual()
    if u["rol"] == "Empleado" and a["empleado_id"] != u["empleado_id"]:
        abort(404)
    return render_template("acta_imprimir.html", a=a)


# --------------------------------------------------------------------------- mantenimiento
def _responsable_mant(valor):
    """(id|None, error|None): el responsable es un usuario activo con rol Mantenimiento (opcional)."""
    if not valor:
        return None, None
    if valor.isdigit():
        r = q1("SELECT id FROM usuario WHERE id = %s AND rol = 'Mantenimiento' AND activo", (int(valor),))
        if r:
            return r["id"], None
    return None, "El responsable debe ser un usuario activo con rol Mantenimiento."


def _nombre_usuario(uid):
    r = q1("SELECT COALESCE(NULLIF(nombre_completo,''), username) AS n FROM usuario WHERE id = %s", (uid,))
    return r["n"] if r else ""


@app.route("/mantenimiento")
def mantenimiento():
    u = usuario_actual()
    solo_mios = u["rol"] == "Mantenimiento"  # el rol Mantenimiento solo ve lo que se le asignó
    where, params = ("m.responsable_id = %s", [u["id"]]) if solo_mios else ("TRUE", [])
    equipos = q(f"""SELECT e.id, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo
                    FROM equipo e JOIN estado_equipo es ON es.id = e.estado_id LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                    WHERE es.nombre = 'Disponible' ORDER BY e.id""")
    total = q1(f"SELECT COUNT(*) AS c FROM mantenimiento m WHERE {where}", params)["c"]
    pg = pagina(total, pagina_int(), 8)
    historial = q(f"""SELECT m.*, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo_equipo, e.marca, e.modelo,
                             COALESCE(NULLIF(r.nombre_completo,''), r.username) AS responsable
                      FROM mantenimiento m JOIN equipo e ON e.id = m.equipo_id LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                      LEFT JOIN usuario r ON r.id = m.responsable_id WHERE {where}
                      ORDER BY (m.estado = 'En Proceso') DESC, m.fecha DESC, m.id DESC LIMIT %s OFFSET %s""",
                  params + [pg["por"], pg["offset"]])
    responsables = q("""SELECT id, COALESCE(NULLIF(nombre_completo,''), username) AS nombre FROM usuario
                        WHERE rol = 'Mantenimiento' AND activo ORDER BY 2""")
    return render_template("mantenimiento.html", equipos=equipos, historial=historial, pg=pg, hoy=hoy(),
                           responsables=responsables, solo_mios=solo_mios)


@app.route("/mantenimiento/nuevo", methods=["POST"])
@requiere("gestionar")
def nuevo_mantenimiento():
    equipo_id = request.form.get("equipo_id", "")
    tipo = request.form.get("tipo", "Preventivo")
    if tipo not in ("Preventivo", "Correctivo"):
        tipo = "Preventivo"
    try:
        fecha = datetime.strptime(request.form.get("fecha", ""), "%Y-%m-%d").date()
    except ValueError:
        fecha = hoy()
    resp_id, err = _responsable_mant(request.form.get("responsable_id", ""))
    e = q1("""SELECT e.id, es.nombre AS estado FROM equipo e JOIN estado_equipo es ON es.id = e.estado_id
              WHERE e.id = %s FOR UPDATE OF e""", (int(equipo_id),)) if equipo_id.isdigit() else None
    if not e:
        flash("Selecciona un equipo.", "danger")
    elif err:
        flash(err, "danger")
    elif e["estado"] != "Disponible":
        flash("Solo se puede enviar a mantenimiento un equipo Disponible. Si está asignado, registra primero la devolución.", "danger")
    else:
        desc = request.form.get("descripcion", "").strip()
        ex("""INSERT INTO mantenimiento (equipo_id, tipo, fecha, descripcion, created_by, responsable_id)
              VALUES (%s,%s,%s,%s,%s,%s)""", (e["id"], tipo, fecha, desc, session.get("username"), resp_id))
        ex("UPDATE equipo SET estado_id=%s, updated_at=%s WHERE id=%s", (estado_id("En Mantenimiento"), ahora(), e["id"]))
        quien = f" · Responsable: {_nombre_usuario(resp_id)}" if resp_id else ""
        log_hist(e["id"], "Mantenimiento", f"{tipo}: {desc or 'sin descripción'}{quien}", "Disponible", "En Mantenimiento")
        conn().commit()
        flash("Mantenimiento registrado. El equipo pasó a «En Mantenimiento»." +
              (" Quedó asignado al responsable elegido." if resp_id else ""), "success")
    return redirect(url_for("mantenimiento"))


@app.route("/mantenimiento/<int:mid>/responsable", methods=["POST"])
@requiere("gestionar")
def asignar_mantenimiento(mid):
    """Asigna (o cambia) el responsable de un mantenimiento en proceso."""
    m = q1("SELECT * FROM mantenimiento WHERE id = %s FOR UPDATE", (mid,))
    resp_id, err = _responsable_mant(request.form.get("responsable_id", ""))
    if not m or m["estado"] != "En Proceso":
        flash("El mantenimiento no existe o ya está completado.", "warning")
    elif err:
        flash(err, "danger")
    else:
        ex("UPDATE mantenimiento SET responsable_id = %s WHERE id = %s", (resp_id, mid))
        log_hist(m["equipo_id"], "Mantenimiento",
                 "Responsable asignado: " + (_nombre_usuario(resp_id) if resp_id else "sin responsable"),
                 "En Mantenimiento", "En Mantenimiento")
        conn().commit()
        flash("Responsable del mantenimiento actualizado.", "success")
    return redirect(url_for("mantenimiento"))


@app.route("/mantenimiento/<int:mid>/completar", methods=["POST"])
@requiere("mantener")
def completar_mantenimiento(mid):
    u = usuario_actual()
    m = q1("SELECT * FROM mantenimiento WHERE id = %s FOR UPDATE", (mid,))
    if not m or m["estado"] != "En Proceso":
        flash("El mantenimiento no existe o ya está completado.", "warning")
    elif u["rol"] == "Mantenimiento" and m["responsable_id"] != u["id"]:
        flash("Solo puedes completar los mantenimientos asignados a ti.", "danger")
    else:
        ex("UPDATE mantenimiento SET estado='Completado', fecha_fin=%s WHERE id=%s", (ahora(), mid))
        ex("UPDATE equipo SET estado_id=%s, updated_at=%s WHERE id=%s", (estado_id("Disponible"), ahora(), m["equipo_id"]))
        log_hist(m["equipo_id"], "Mantenimiento", "Mantenimiento completado", "En Mantenimiento", "Disponible")
        conn().commit()
        flash("Mantenimiento completado. El equipo volvió a estar Disponible.", "success")
    return redirect(url_for("mantenimiento"))


# --------------------------------------------------------------------------- reportes
def _rango():
    hoy_ = hoy()
    try:
        desde = datetime.strptime(request.args.get("desde", ""), "%Y-%m-%d").date()
    except ValueError:
        desde = hoy_.replace(day=1)
    try:
        hasta = datetime.strptime(request.args.get("hasta", ""), "%Y-%m-%d").date()
    except ValueError:
        hasta = hoy_
    if desde > hasta:
        desde, hasta = hasta, desde
    return desde, hasta


def _filtro_reporte():
    """Filtros del reporte: equipo y usuario (empleado), validados contra la base de datos."""
    eq = request.args.get("equipo", "")
    em = request.args.get("empleado", "")
    equipo = q1(f"SELECT e.id, {CODIGO.format(a='e')} AS codigo, e.marca, e.modelo FROM equipo e WHERE e.id = %s",
                (int(eq),)) if eq.isdigit() else None
    emp = q1("SELECT id, nombres || ' ' || COALESCE(apellidos,'') AS nombre FROM empleado WHERE id = %s",
             (int(em),)) if em.isdigit() else None
    return (equipo["id"] if equipo else None), (emp["id"] if emp else None)


def _equipo_ligado(col, equipo_id, empleado_id):
    """Condición SQL (y parámetros) para limitar una consulta a un equipo y/o a los equipos de un usuario."""
    cond, par = [], []
    if equipo_id:
        cond.append(f"{col} = %s")
        par.append(equipo_id)
    if empleado_id:
        cond.append(f"{col} IN (SELECT equipo_id FROM asignacion WHERE empleado_id = %s)")
        par.append(empleado_id)
    return ((" AND " + " AND ".join(cond)) if cond else ""), par


def datos_reporte(desde, hasta, equipo_id=None, empleado_id=None):
    r = resumen()
    por_estado = q("""SELECT es.nombre, COUNT(e.id) AS c FROM estado_equipo es
                      LEFT JOIN equipo e ON e.estado_id = es.id GROUP BY es.nombre, es.id ORDER BY es.id""")
    por_tipo = q("""SELECT t.nombre, COUNT(e.id) AS c FROM tipo_equipo t
                    LEFT JOIN equipo e ON e.tipo_id = t.id AND e.estado_id <> %s
                    GROUP BY t.nombre HAVING COUNT(e.id) > 0 ORDER BY c DESC""", (estado_id("Dado de baja"),))
    d1, d2 = datetime.combine(desde, datetime.min.time()), datetime.combine(hasta + timedelta(days=1), datetime.min.time())
    asig = q(f"""SELECT a.fecha_asignacion, a.fecha_devolucion, a.estado, {CODIGO.format(a='e')} AS codigo,
                        t.nombre AS tipo, e.marca, e.modelo, emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS empleado
                 FROM asignacion a JOIN equipo e ON e.id = a.equipo_id JOIN empleado emp ON emp.id = a.empleado_id
                 LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                 WHERE a.fecha_asignacion >= %s AND a.fecha_asignacion < %s
                   AND (%s::int IS NULL OR a.equipo_id = %s) AND (%s::int IS NULL OR a.empleado_id = %s)
                 ORDER BY a.fecha_asignacion DESC""", (d1, d2, equipo_id, equipo_id, empleado_id, empleado_id))
    c_m, p_m = _equipo_ligado("m.equipo_id", equipo_id, empleado_id)
    mant = q(f"""SELECT m.fecha, m.tipo, m.estado, m.descripcion, m.fecha_fin, {CODIGO.format(a='e')} AS codigo,
                        t.nombre AS tipo_equipo, e.marca, e.modelo,
                        COALESCE(NULLIF(r.nombre_completo,''), r.username) AS responsable
                 FROM mantenimiento m JOIN equipo e ON e.id = m.equipo_id LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                 LEFT JOIN usuario r ON r.id = m.responsable_id
                 WHERE m.fecha BETWEEN %s AND %s{c_m} ORDER BY m.fecha DESC""", [desde, hasta] + p_m)
    c_n, p_n = _equipo_ligado("e.id", equipo_id, empleado_id)
    nuevos = q(f"""SELECT {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo, e.numero_serie,
                          es.nombre AS estado, e.fecha_ingreso
                   FROM equipo e LEFT JOIN tipo_equipo t ON t.id = e.tipo_id LEFT JOIN estado_equipo es ON es.id = e.estado_id
                   WHERE e.fecha_ingreso >= %s AND e.fecha_ingreso < %s{c_n} ORDER BY e.fecha_ingreso DESC""", [d1, d2] + p_n)
    # Movimientos (historial) de un equipo o de los equipos de un usuario mientras los tuvo a su cargo
    cond_h, par_h = [], []
    if equipo_id:
        cond_h.append("h.equipo_id = %s")
        par_h.append(equipo_id)
    if empleado_id:
        cond_h.append("""EXISTS (SELECT 1 FROM asignacion a WHERE a.empleado_id = %s AND a.equipo_id = h.equipo_id
                           AND h.fecha >= a.fecha_asignacion - interval '1 minute'
                           AND (a.fecha_devolucion IS NULL OR h.fecha <= a.fecha_devolucion + interval '1 minute'))""")
        par_h.append(empleado_id)
    movimientos = q(f"""SELECT h.fecha, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo, h.tipo_evento,
                               h.detalle, h.estado_anterior, h.estado_nuevo, h.usuario
                        FROM historial h JOIN equipo e ON e.id = h.equipo_id LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                        WHERE h.fecha >= %s AND h.fecha < %s{''.join(' AND ' + c for c in cond_h)}
                        ORDER BY h.fecha DESC, h.id DESC""", [d1, d2] + par_h)
    # Indicadores (ficha sec. 17)
    umbral = umbral_sin_movimiento()
    con_mant = q1("SELECT COUNT(DISTINCT equipo_id) AS c FROM mantenimiento WHERE fecha BETWEEN %s AND %s", (desde, hasta))["c"]
    tasa = round(con_mant * 100 / r["total"], 1) if r["total"] else 0
    pendientes = q(f"""SELECT ac.id, ac.fecha_generacion, {CODIGO.format(a='e')} AS codigo,
                              emp.nombres || ' ' || COALESCE(emp.apellidos,'') AS empleado,
                              (%s::date - ac.fecha_generacion::date) AS dias
                       FROM acta ac JOIN asignacion a ON a.id = ac.asignacion_id JOIN equipo e ON e.id = a.equipo_id
                       JOIN empleado emp ON emp.id = a.empleado_id WHERE ac.estado = 'pendiente'
                       AND (%s::int IS NULL OR a.equipo_id = %s) AND (%s::int IS NULL OR a.empleado_id = %s)
                       ORDER BY ac.fecha_generacion""", (hoy(), equipo_id, equipo_id, empleado_id, empleado_id))
    cerradas = q1("SELECT COUNT(*) AS c FROM asignacion WHERE estado='cerrada' AND fecha_devolucion >= %s AND fecha_devolucion < %s",
                  (d1, d2))["c"]
    c_s, p_s = _equipo_ligado("e.id", equipo_id, empleado_id)
    sin_mov = q(f"""SELECT {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo, es.nombre AS estado,
                           COALESCE(MAX(h.fecha), e.fecha_ingreso) AS ultimo,
                           (%s::date - COALESCE(MAX(h.fecha), e.fecha_ingreso)::date) AS dias
                    FROM equipo e LEFT JOIN tipo_equipo t ON t.id = e.tipo_id
                    LEFT JOIN estado_equipo es ON es.id = e.estado_id LEFT JOIN historial h ON h.equipo_id = e.id
                    WHERE es.nombre <> 'Dado de baja'{c_s} GROUP BY e.id, t.nombre, es.nombre
                    HAVING COALESCE(MAX(h.fecha), e.fecha_ingreso) < %s ORDER BY ultimo""",
                 [hoy()] + p_s + [ahora() - timedelta(days=umbral)])
    filtro = []
    if equipo_id:
        x = q1(f"SELECT {CODIGO.format(a='e')} AS codigo, e.marca, e.modelo FROM equipo e WHERE e.id = %s", (equipo_id,))
        filtro.append(f"Equipo: {x['codigo']} {x['marca'] or ''} {x['modelo'] or ''}".strip())
    if empleado_id:
        x = q1("SELECT nombres || ' ' || COALESCE(apellidos,'') AS n FROM empleado WHERE id = %s", (empleado_id,))
        filtro.append(f"Usuario: {x['n'].strip()}")
    por_area = q("""SELECT COALESCE(NULLIF(emp.area,''), 'Sin área') AS area, COUNT(*) AS c FROM asignacion a
                    JOIN empleado emp ON emp.id = a.empleado_id WHERE a.estado = 'activa'
                    GROUP BY 1 ORDER BY c DESC, 1""")
    return {"resumen": r, "por_estado": por_estado, "por_tipo": por_tipo, "asignaciones": asig,
            "mantenimientos": mant, "nuevos": nuevos, "desde": desde, "hasta": hasta,
            "tasa_mantenimiento": tasa, "equipos_con_mant": con_mant, "actas_pendientes": pendientes,
            "asignaciones_cerradas": cerradas, "sin_movimiento": sin_mov, "umbral": umbral, "por_area": por_area,
            "movimientos": movimientos, "filtro": " · ".join(filtro),
            "empresa": config()["empresa"], "generado": ahora()}


def umbral_sin_movimiento():
    try:
        return max(1, int(config().get("umbral_sin_movimiento", 90)))
    except ValueError:
        return 90


@app.route("/reportes")
@requiere("reportes")
def reportes():
    desde, hasta = _rango()
    eq_id, emp_id = _filtro_reporte()
    rep = datos_reporte(desde, hasta, eq_id, emp_id)
    estados_chart = {"Disponible": 0, "Asignado": 0, "En Mantenimiento": 0}
    otros = 0
    for r in rep["por_estado"]:
        if r["nombre"] in estados_chart:
            estados_chart[r["nombre"]] = r["c"]
        elif r["nombre"] != "Dado de baja":
            otros += r["c"]
    lista_equipos = q(f"""SELECT e.id, {CODIGO.format(a='e')} AS codigo, t.nombre AS tipo, e.marca, e.modelo
                          FROM equipo e LEFT JOIN tipo_equipo t ON t.id = e.tipo_id ORDER BY e.id""")
    lista_usuarios = q("SELECT id, nombres || ' ' || COALESCE(apellidos,'') AS nombre, documento FROM empleado ORDER BY nombres, apellidos")
    return render_template("reportes.html", rep=rep, desde=desde, hasta=hasta, estados_chart=estados_chart, otros=otros,
                           lista_equipos=lista_equipos, lista_usuarios=lista_usuarios, eq_id=eq_id, emp_id=emp_id)


@app.route("/reportes/excel")
@requiere("reportes")
def reporte_excel():
    desde, hasta = _rango()
    data = informes.excel(datos_reporte(desde, hasta, *_filtro_reporte()))
    return send_file(io.BytesIO(data), as_attachment=True, download_name=f"SIGEC_reporte_{desde}_{hasta}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/reportes/pdf")
@requiere("reportes")
def reporte_pdf():
    desde, hasta = _rango()
    data = informes.pdf(datos_reporte(desde, hasta, *_filtro_reporte()))
    return send_file(io.BytesIO(data), as_attachment=True, download_name=f"SIGEC_reporte_{desde}_{hasta}.pdf",
                     mimetype="application/pdf")


# --------------------------------------------------------------------------- usuarios
def _form_usuario():
    return {k: request.form.get(k, "").strip() for k in ("username", "nombre_completo", "rol", "password", "empleado_id", "documento")}


def _empleado_valido(d, uid=None):
    """Devuelve (empleado_id|None, error|None) para el vínculo usuario-empleado."""
    if not d.get("empleado_id"):
        return None, None
    if not d["empleado_id"].isdigit() or not q1("SELECT id FROM empleado WHERE id = %s", (int(d["empleado_id"]),)):
        return None, "El empleado seleccionado no existe."
    if q1("SELECT id FROM usuario WHERE empleado_id = %s AND id <> %s", (int(d["empleado_id"]), uid or 0)):
        return None, "Ese empleado ya está vinculado a otro usuario."
    return int(d["empleado_id"]), None


def _es_admin_principal(u):
    return u["username"].lower() == db.ADMIN_USER.lower()


@app.route("/usuarios")
@requiere("admin")
def usuarios():
    lista = q("SELECT * FROM usuario ORDER BY (lower(username) = lower(%s)) DESC, username", (db.ADMIN_USER,))
    return render_template("usuarios.html", lista=lista, principal=db.ADMIN_USER)


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@requiere("admin")
def nuevo_usuario():
    if request.method == "POST":
        d = _form_usuario()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", d["username"]):
            flash("El usuario debe tener 3 a 30 caracteres (letras, números, punto, guion o guion bajo).", "danger")
        elif d["rol"] not in ROLES:
            flash("Selecciona un rol válido.", "danger")
        elif len(d["password"]) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "danger")
        elif q1("SELECT id FROM usuario WHERE lower(username) = lower(%s)", (d["username"],)):
            flash("Ya existe un usuario con ese nombre.", "danger")
        elif _empleado_valido(d)[1]:
            flash(_empleado_valido(d)[1], "danger")
        elif d["rol"] == "Empleado" and not d["empleado_id"] and not d["documento"]:
            flash("El rol Empleado necesita una ficha de empleado: elige uno existente o escribe el documento para crearla.", "danger")
        elif d["rol"] == "Empleado" and not d["empleado_id"] and q1("SELECT id FROM empleado WHERE documento = %s", (d["documento"],)):
            flash("Ya existe un empleado con ese documento: elígelo en la lista «Empleado vinculado».", "danger")
        else:
            emp_id = _empleado_valido(d)[0]
            if d["rol"] == "Empleado" and not emp_id:  # se crea la ficha para que vea sus equipos desde el primer ingreso
                partes = (d["nombre_completo"] or d["username"]).split(" ", 1)
                emp_id = ex("""INSERT INTO empleado (documento, nombres, apellidos, estado, fecha_ingreso)
                               VALUES (%s,%s,%s,'activo',%s) RETURNING id""",
                            (d["documento"], partes[0], partes[1] if len(partes) > 1 else "", hoy()), returning=True)["id"]
            ex("INSERT INTO usuario (username, password_hash, nombre_completo, rol, empleado_id, activo) VALUES (%s,%s,%s,%s,%s,TRUE)",
               (d["username"], generate_password_hash(d["password"]), d["nombre_completo"] or d["username"], d["rol"], emp_id))
            conn().commit()
            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("usuarios"))
        return render_template("form_usuario.html", d=d, editar=False, roles=ROLES, empleados=_empleados_lista())
    return render_template("form_usuario.html", d={"rol": "Operador"}, editar=False, roles=ROLES, empleados=_empleados_lista())


def _empleados_lista():
    return q("SELECT id, documento, nombres, apellidos FROM empleado WHERE estado = 'activo' ORDER BY nombres")


@app.route("/usuarios/<int:uid>")
@requiere("admin")
def ver_usuario(uid):
    u = q1("SELECT * FROM usuario WHERE id = %s", (uid,))
    if not u:
        abort(404)
    return render_template("ver_usuario.html", u=u, permisos=sorted(PERMISOS.get(u["rol"], [])), principal=_es_admin_principal(u))


@app.route("/usuarios/<int:uid>/editar", methods=["GET", "POST"])
@requiere("admin")
def editar_usuario(uid):
    u = q1("SELECT * FROM usuario WHERE id = %s", (uid,))
    if not u:
        abort(404)
    principal = _es_admin_principal(u)
    if request.method == "POST":
        d = _form_usuario()
        activo = request.form.get("activo") == "1"
        if principal:
            d["rol"], activo = "Administrador", True
        if d["rol"] not in ROLES:
            flash("Selecciona un rol válido.", "danger")
        elif d["password"] and len(d["password"]) < 8:
            flash("La nueva contraseña debe tener al menos 8 caracteres.", "danger")
        elif u["id"] == session["uid"] and not activo:
            flash("No puedes desactivar tu propio usuario.", "danger")
        elif _empleado_valido(d, uid)[1]:
            flash(_empleado_valido(d, uid)[1], "danger")
        else:
            ex("UPDATE usuario SET nombre_completo=%s, rol=%s, activo=%s, empleado_id=%s WHERE id=%s",
               (d["nombre_completo"] or u["username"], d["rol"], activo, _empleado_valido(d, uid)[0], uid))
            if d["password"]:
                ex("UPDATE usuario SET password_hash=%s WHERE id=%s", (generate_password_hash(d["password"]), uid))
            conn().commit()
            flash("Usuario actualizado correctamente.", "success")
            return redirect(url_for("usuarios"))
        return render_template("form_usuario.html", d={**u, **d, "activo": activo}, editar=True, u=u, roles=ROLES,
                               principal=principal, empleados=_empleados_lista())
    return render_template("form_usuario.html", d={**u, "empleado_id": str(u["empleado_id"] or "")}, editar=True, u=u, roles=ROLES,
                           principal=principal, empleados=_empleados_lista())


@app.route("/usuarios/<int:uid>/eliminar", methods=["POST"])
@requiere("admin")
def eliminar_usuario(uid):
    u = q1("SELECT * FROM usuario WHERE id = %s", (uid,))
    if not u:
        flash("El usuario no existe.", "warning")
    elif _es_admin_principal(u):
        flash("El usuario Admin es el administrador principal y no se puede eliminar.", "danger")
    elif u["id"] == session["uid"]:
        flash("No puedes eliminar tu propio usuario.", "danger")
    else:
        # Sus mantenimientos quedan «Sin asignar» (la clave foránea impediría borrarlo y daría error)
        ex("UPDATE mantenimiento SET responsable_id = NULL WHERE responsable_id = %s", (uid,))
        ex("DELETE FROM usuario WHERE id = %s", (uid,))
        conn().commit()
        flash(f"Usuario «{u['username']}» eliminado.", "success")
    return redirect(url_for("usuarios"))


# --------------------------------------------------------------------------- configuración
@app.route("/configuracion")
@requiere("admin")
def configuracion():
    tab = request.args.get("tab", "general")
    if tab not in ("general", "catalogos", "notificaciones", "respaldos", "seguridad"):
        tab = "general"
    tipos = q("""SELECT t.*, (SELECT COUNT(*) FROM equipo e WHERE e.tipo_id = t.id) AS usos FROM tipo_equipo t ORDER BY nombre""")
    estados = q("""SELECT s.*, (SELECT COUNT(*) FROM equipo e WHERE e.estado_id = s.id) AS usos FROM estado_equipo s ORDER BY id""")
    marcas = q("""SELECT m.*, (SELECT COUNT(*) FROM equipo e WHERE lower(e.marca) = lower(m.nombre)) AS usos FROM marca m ORDER BY lower(nombre)""")
    areas = q("""SELECT a.*, (SELECT COUNT(*) FROM empleado e WHERE lower(e.area) = lower(a.nombre)) AS usos FROM area a ORDER BY lower(nombre)""")
    auto = sorted(os.listdir(RESPALDOS), reverse=True)[:5] if os.path.isdir(RESPALDOS) else []
    return render_template("configuracion.html", tab=tab, zonas=ZONAS, cfg=config(True), asistente_motor=asistente.estado_motor(), ia_configurada=asistente.ia.configurado(),
                           tipos=tipos, estados=estados, base=ESTADOS_BASE, auto=auto, marcas=marcas, areas=areas)


@app.route("/configuracion/general", methods=["POST"])
@requiere("admin")
def guardar_general():
    empresa = request.form.get("empresa", "").strip()[:100] or "Tu Empresa S.A.S."
    zona = request.form.get("zona_horaria", "America/Bogota")
    zona = zona if zona in ZONAS else "America/Bogota"
    ajustes = [("empresa", empresa), ("zona_horaria", zona), ("idioma", "es")]
    if request.form.get("ia_externa_form") == "1":  # solo cuando la pantalla mostró la opción
        ajustes.append(("ia_externa", "1" if request.form.get("ia_externa") == "1" else "0"))
    for k, v in ajustes:
        ex("INSERT INTO configuracion (clave, valor) VALUES (%s,%s) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor", (k, v))
    conn().commit()
    config(True)
    flash("Configuración guardada correctamente.", "success")
    return redirect(url_for("configuracion", tab="general"))


@app.route("/configuracion/notificaciones", methods=["POST"])
@requiere("admin")
def guardar_notificaciones():
    for k in ("notif_actas", "notif_mantenimiento", "notif_asignaciones"):
        ex("INSERT INTO configuracion (clave, valor) VALUES (%s,%s) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor",
           (k, "1" if request.form.get(k) == "1" else "0"))
    conn().commit()
    config(True)
    flash("Preferencias de notificaciones guardadas.", "success")
    return redirect(url_for("configuracion", tab="notificaciones"))


@app.route("/configuracion/catalogos/tipo", methods=["POST"])
@requiere("admin")
def guardar_tipo():
    accion, tid = request.form.get("accion", ""), request.form.get("id", "")
    nombre = request.form.get("nombre", "").strip()[:100]
    if accion == "crear":
        if not nombre:
            flash("Escribe el nombre del tipo de equipo.", "danger")
        elif q1("SELECT id FROM tipo_equipo WHERE lower(nombre) = lower(%s)", (nombre,)):
            flash("Ya existe un tipo con ese nombre.", "danger")
        else:
            ex("INSERT INTO tipo_equipo (nombre, categoria) VALUES (%s,%s)", (nombre, request.form.get("categoria", "").strip()[:50]))
            conn().commit()
            flash("Tipo de equipo creado.", "success")
    elif tid.isdigit() and accion in ("renombrar", "alternar"):
        t = q1("SELECT * FROM tipo_equipo WHERE id = %s", (int(tid),))
        if not t:
            flash("El tipo no existe.", "warning")
        elif accion == "renombrar":
            if not nombre or q1("SELECT id FROM tipo_equipo WHERE lower(nombre)=lower(%s) AND id<>%s", (nombre, t["id"])):
                flash("Nombre vacío o ya existente.", "danger")
            else:
                ex("UPDATE tipo_equipo SET nombre=%s WHERE id=%s", (nombre, t["id"]))
                conn().commit()
                flash("Tipo renombrado.", "success")
        else:
            ex("UPDATE tipo_equipo SET activo = NOT activo WHERE id=%s", (t["id"],))
            conn().commit()
            flash("Tipo " + ("desactivado" if t["activo"] else "activado") + ". Los equipos existentes conservan su tipo.", "success")
    return redirect(url_for("configuracion", tab="catalogos"))


@app.route("/configuracion/catalogos/estado", methods=["POST"])
@requiere("admin")
def guardar_estado():
    accion, eid = request.form.get("accion", ""), request.form.get("id", "")
    nombre = request.form.get("nombre", "").strip()[:50]
    if accion == "crear":
        if not nombre:
            flash("Escribe el nombre del estado.", "danger")
        elif q1("SELECT id FROM estado_equipo WHERE lower(nombre) = lower(%s)", (nombre,)):
            flash("Ya existe un estado con ese nombre.", "danger")
        else:
            ex("INSERT INTO estado_equipo (nombre, descripcion, es_critico) VALUES (%s,%s,FALSE)",
               (nombre, request.form.get("descripcion", "").strip()))
            conn().commit()
            flash("Estado creado.", "success")
    elif eid.isdigit() and accion in ("renombrar", "alternar"):
        st = q1("SELECT * FROM estado_equipo WHERE id = %s", (int(eid),))
        if not st:
            flash("El estado no existe.", "warning")
        elif st["nombre"] in ESTADOS_BASE or st["es_critico"]:
            flash("Los estados base del sistema están protegidos y no se pueden renombrar ni desactivar (RN-12).", "danger")
        elif accion == "renombrar":
            if not nombre or q1("SELECT id FROM estado_equipo WHERE lower(nombre)=lower(%s) AND id<>%s", (nombre, st["id"])):
                flash("Nombre vacío o ya existente.", "danger")
            else:
                ex("UPDATE estado_equipo SET nombre=%s WHERE id=%s", (nombre, st["id"]))
                conn().commit()
                flash("Estado renombrado.", "success")
        else:
            en_uso = q1("SELECT COUNT(*) AS c FROM equipo WHERE estado_id = %s", (st["id"],))["c"]
            if st["activo"] and en_uso:
                flash(f"No se puede desactivar: hay {en_uso} equipo(s) en ese estado.", "danger")
            else:
                ex("UPDATE estado_equipo SET activo = NOT activo WHERE id=%s", (st["id"],))
                conn().commit()
                flash("Estado " + ("desactivado" if st["activo"] else "activado") + ".", "success")
    return redirect(url_for("configuracion", tab="catalogos"))


@app.route("/configuracion/catalogos/<cat>", methods=["POST"])
@requiere("admin")
def guardar_catalogo(cat):
    """Catálogos de listas desplegables (marca y área): crear, renombrar, activar o desactivar."""
    if cat not in CATALOGOS:
        abort(404)
    uso_tabla, uso_col, etiqueta = CATALOGOS[cat]
    accion, cid = request.form.get("accion", ""), request.form.get("id", "")
    nombre = request.form.get("nombre", "").strip()[:100]
    if accion == "crear":
        if not nombre:
            flash("Escribe el nombre de la opción.", "danger")
        elif q1(f"SELECT id FROM {cat} WHERE lower(nombre) = lower(%s)", (nombre,)):
            flash("Ya existe una opción con ese nombre.", "danger")
        else:
            ex(f"INSERT INTO {cat} (nombre) VALUES (%s)", (nombre,))
            conn().commit()
            flash(f"{etiqueta.capitalize()} creada.", "success")
    elif cid.isdigit() and accion in ("renombrar", "alternar"):
        x = q1(f"SELECT * FROM {cat} WHERE id = %s", (int(cid),))
        if not x:
            flash("La opción no existe.", "warning")
        elif accion == "renombrar":
            if not nombre or q1(f"SELECT id FROM {cat} WHERE lower(nombre) = lower(%s) AND id <> %s", (nombre, x["id"])):
                flash("Nombre vacío o ya existente.", "danger")
            else:
                ex(f"UPDATE {cat} SET nombre = %s WHERE id = %s", (nombre, x["id"]))
                # los registros que la usan siguen mostrando el nombre correcto
                ex(f"UPDATE {uso_tabla} SET {uso_col} = %s WHERE lower({uso_col}) = lower(%s)", (nombre, x["nombre"]))
                conn().commit()
                flash(f"{etiqueta.capitalize()} renombrada.", "success")
        else:
            ex(f"UPDATE {cat} SET activo = NOT activo WHERE id = %s", (x["id"],))
            conn().commit()
            flash(f"{etiqueta.capitalize()} " + ("desactivada" if x["activo"] else "activada") +
                  ". Los registros existentes conservan su valor.", "success")
    return redirect(url_for("configuracion", tab="catalogos"))


@app.route("/configuracion/operacion", methods=["POST"])
@requiere("admin")
def guardar_operacion():
    try:
        umbral = min(max(int(request.form.get("umbral_sin_movimiento", "90")), 1), 3650)
    except ValueError:
        umbral = 90
    for k, v in (("umbral_sin_movimiento", str(umbral)), ("respaldo_auto", "1" if request.form.get("respaldo_auto") == "1" else "0")):
        ex("INSERT INTO configuracion (clave, valor) VALUES (%s,%s) ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor", (k, v))
    conn().commit()
    config(True)
    flash("Parámetros de operación guardados.", "success")
    return redirect(url_for("configuracion", tab="respaldos"))


# --------------------------------------------------------------------------- respaldo
RESPALDO_TABLAS = ["tipo_equipo", "estado_equipo", "marca", "area", "empleado", "equipo", "asignacion", "acta", "historial",
                   "mantenimiento", "configuracion"]


def volcado(cur, generado):
    out = {"sistema": "SIGEC", "version": VERSION, "generado": generado.isoformat(), "tablas": {}}
    for t in RESPALDO_TABLAS:
        cur.execute(f"SELECT * FROM {t} ORDER BY 1")
        out["tablas"][t] = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT id, username, nombre_completo, rol, empleado_id, activo, created_at FROM usuario ORDER BY id")
    out["tablas"]["usuario"] = [dict(r) for r in cur.fetchall()]  # sin hashes de contraseña
    return json.dumps(out, ensure_ascii=False, indent=1, default=str).encode("utf-8")


def respaldo_automatico():
    """RNF-06: un respaldo JSON por día en la carpeta respaldos/ (se conservan los últimos 14)."""
    c = db.connect()
    try:
        cur = c.cursor()
        cur.execute("SELECT valor FROM configuracion WHERE clave = 'respaldo_auto'")
        r = cur.fetchone()
        if r and r["valor"] == "0":
            return None
        os.makedirs(RESPALDOS, exist_ok=True)
        ahora_ = datetime.now()
        ruta = os.path.join(RESPALDOS, f"SIGEC_auto_{ahora_:%Y%m%d}.json")
        if os.path.exists(ruta):
            return None
        with open(ruta, "wb") as fh:
            fh.write(volcado(cur, ahora_))
        viejos = sorted(f for f in os.listdir(RESPALDOS) if f.startswith("SIGEC_auto_"))[:-14]
        for f in viejos:
            os.remove(os.path.join(RESPALDOS, f))
        return ruta
    finally:
        c.close()


def _hilo_respaldo():
    while True:
        try:
            respaldo_automatico()
        except Exception as exc:  # no debe tumbar la aplicación
            print("[respaldo] no se pudo generar:", exc)
        time.sleep(3600)


def iniciar_respaldo_diario():
    if os.environ.get("SIGEC_SIN_RESPALDO") != "1":
        threading.Thread(target=_hilo_respaldo, daemon=True, name="respaldo-diario").start()


@app.route("/configuracion/respaldo")
@requiere("admin")
def descargar_respaldo():
    data = volcado(conn().cursor(), ahora())
    return send_file(io.BytesIO(data), as_attachment=True, mimetype="application/json",
                     download_name=f"SIGEC_respaldo_{ahora():%Y%m%d_%H%M}.json")


# --------------------------------------------------------------------------- asistente IA
_ia_uso = {}


def _ia_excedido(uid, limite=30, ventana=600):
    """Tope de preguntas por usuario (protege el consumo de la clave de la API)."""
    ts = [t for t in _ia_uso.get(uid, []) if time.time() - t < ventana]
    if len(ts) >= limite:
        _ia_uso[uid] = ts
        return True
    ts.append(time.time())
    _ia_uso[uid] = ts
    return False


@app.route("/api/asistente", methods=["POST"])
def api_asistente():
    d = request.get_json(silent=True) or {}
    u = usuario_actual()
    if _ia_excedido(u["id"]):
        return jsonify(respuesta="Has hecho muchas preguntas seguidas. Espera unos minutos y vuelve a intentarlo.",
                       motor="límite de uso", fuentes=[])
    completo = u["rol"] in asistente.ia.ROLES_COMPLETOS
    res = asistente.responder(
        d.get("pregunta", ""), d.get("historial"), d.get("pagina", ""),
        datos_asistente if completo else None,  # Empleado y Mantenimiento no consultan datos generales del inventario
        usuario=dict(u), consultas=(q, q1, umbral_sin_movimiento(), ahora()),
        permitir_externo=config().get("ia_externa", "1") == "1")
    return jsonify(res)


@app.route("/api/asistente/estado")
def api_asistente_estado():
    return jsonify(motor=asistente.estado_motor())


@app.route("/manual")
def manual():
    ruta = os.path.join(db.BASE_DIR, "docs", "Manual_SIGEC.pdf")
    if not os.path.exists(ruta):
        abort(404)
    return send_file(ruta, mimetype="application/pdf", download_name="Manual_SIGEC.pdf")


# --------------------------------------------------------------------------- errores
@app.errorhandler(404)
def no_encontrado(_e):
    return render_template("error.html", codigo=404, titulo="Página no encontrada",
                           mensaje="El registro o la página que buscas no existe."), 404


@app.errorhandler(psycopg2.OperationalError)
def sin_base_de_datos(_e):
    return render_template("error.html", codigo=503, titulo="Sin conexión a la base de datos",
                           mensaje="No se pudo conectar a Neon PostgreSQL. Revisa tu conexión a internet y el valor "
                                   "DATABASE_URL del archivo .env."), 503


@app.errorhandler(500)
def error_interno(_e):
    return render_template("error.html", codigo=500, titulo="Ocurrió un error",
                           mensaje="Algo salió mal procesando la solicitud. Intenta de nuevo."), 500


def arrancar(reintentos=5):
    """Prepara la base de datos (idempotente) y el respaldo diario. En la nube reintenta si Neon tarda en despertar."""
    for i in range(reintentos):
        try:
            db.init_db()
            break
        except Exception as exc:
            print(f"[SIGEC] base de datos no disponible (intento {i + 1}/{reintentos}): {exc}")
            if i == reintentos - 1:
                raise
            time.sleep(4)
    iniciar_respaldo_diario()
    if not os.environ.get("SECRET_KEY"):
        print("[SIGEC] AVISO: falta SECRET_KEY; las sesiones se cerrarán en cada reinicio. Defínela en .env o en las variables.")


@app.after_request
def cabeceras_seguridad(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if SESSION_SEGURA:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return resp


if __name__ == "__main__":
    print("\n" + "=" * 54)
    print("  SIGEC v" + VERSION + " - iniciando...")
    try:
        arrancar()
        print("  Base de datos lista (Neon PostgreSQL)")
    except Exception as exc:
        print("  [AVISO] No se pudo preparar la base de datos:", exc)
    print("  Asistente IA:", asistente.estado_motor())
    print("  Abre tu navegador en: http://localhost:5000")
    print("=" * 54 + "\n")
    app.run(debug=False, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)))

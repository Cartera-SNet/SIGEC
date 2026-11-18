"""
SIGEC - Acceso a base de datos (PostgreSQL / Neon)
- Lee la configuración desde el archivo .env (o variables de entorno).
- init_db() crea las tablas que falten y siembra datos mínimos (idempotente:
  se puede ejecutar cuantas veces se quiera sin perder datos).
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash

import textos

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ADMIN_USER = "Admin"
ADMIN_PASS = "Admin2026"
ADMIN_NOMBRE = "Víctor Yepes"


def load_env():
    """Carga .env sin depender de librerías externas."""
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_env()
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def connect():
    if not DATABASE_URL:
        raise RuntimeError("Falta DATABASE_URL en el archivo .env")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=30)


SCHEMA = """
CREATE TABLE IF NOT EXISTS tipo_equipo (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    categoria VARCHAR(50),
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS estado_equipo (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    descripcion TEXT,
    es_critico BOOLEAN DEFAULT FALSE,
    activo BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS empleado (
    id SERIAL PRIMARY KEY,
    documento VARCHAR(20) NOT NULL UNIQUE,
    nombres VARCHAR(150) NOT NULL,
    apellidos VARCHAR(150),
    area VARCHAR(100),
    cargo VARCHAR(100),
    correo VARCHAR(120),
    telefono VARCHAR(20),
    estado VARCHAR(20) DEFAULT 'activo' CHECK (estado IN ('activo','inactivo')),
    fecha_ingreso DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS equipo (
    id SERIAL PRIMARY KEY,
    tipo_id INTEGER REFERENCES tipo_equipo(id),
    marca VARCHAR(100),
    modelo VARCHAR(100),
    numero_serie VARCHAR(100) NOT NULL UNIQUE,
    placa VARCHAR(50),
    caracteristicas TEXT,
    estado_id INTEGER REFERENCES estado_equipo(id),
    ubicacion VARCHAR(150),
    fecha_ingreso TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS asignacion (
    id SERIAL PRIMARY KEY,
    equipo_id INTEGER NOT NULL REFERENCES equipo(id),
    empleado_id INTEGER NOT NULL REFERENCES empleado(id),
    fecha_asignacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_devolucion TIMESTAMP,
    estado VARCHAR(20) DEFAULT 'activa' CHECK (estado IN ('activa','cerrada')),
    observaciones TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS acta (
    id SERIAL PRIMARY KEY,
    asignacion_id INTEGER NOT NULL REFERENCES asignacion(id),
    fecha_generacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    estado VARCHAR(20) DEFAULT 'pendiente' CHECK (estado IN ('pendiente','firmada')),
    fecha_firma TIMESTAMP,
    firmado_por VARCHAR(150),
    evidencia_path VARCHAR(255),
    observaciones TEXT
);
CREATE TABLE IF NOT EXISTS historial (
    id SERIAL PRIMARY KEY,
    equipo_id INTEGER NOT NULL REFERENCES equipo(id),
    tipo_evento VARCHAR(50) NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario VARCHAR(100) DEFAULT 'Operador',
    detalle TEXT,
    estado_anterior VARCHAR(50),
    estado_nuevo VARCHAR(50),
    asignacion_id INTEGER REFERENCES asignacion(id)
);
CREATE TABLE IF NOT EXISTS usuario (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    nombre_completo VARCHAR(150),
    rol VARCHAR(30) DEFAULT 'Operador',
    empleado_id INTEGER REFERENCES empleado(id),
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mantenimiento (
    id SERIAL PRIMARY KEY,
    equipo_id INTEGER NOT NULL REFERENCES equipo(id),
    tipo VARCHAR(30) NOT NULL DEFAULT 'Preventivo',
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    descripcion TEXT,
    estado VARCHAR(20) NOT NULL DEFAULT 'En Proceso' CHECK (estado IN ('En Proceso','Completado')),
    fecha_fin TIMESTAMP,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS marca (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    activo BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS area (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    activo BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS ubicacion (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    activo BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS cargo (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    activo BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS configuracion (
    clave VARCHAR(60) PRIMARY KEY,
    valor TEXT
);
CREATE INDEX IF NOT EXISTS idx_equipo_serie ON equipo(numero_serie);
CREATE INDEX IF NOT EXISTS idx_equipo_estado ON equipo(estado_id);
CREATE INDEX IF NOT EXISTS idx_asignacion_equipo ON asignacion(equipo_id);
CREATE INDEX IF NOT EXISTS idx_asignacion_empleado ON asignacion(empleado_id);
CREATE INDEX IF NOT EXISTS idx_asignacion_estado ON asignacion(estado);
CREATE INDEX IF NOT EXISTS idx_acta_asignacion ON acta(asignacion_id);
CREATE INDEX IF NOT EXISTS idx_historial_equipo ON historial(equipo_id);
CREATE INDEX IF NOT EXISTS idx_historial_fecha ON historial(fecha);
CREATE INDEX IF NOT EXISTS idx_mant_equipo ON mantenimiento(equipo_id);
"""

ESTADOS = [
    ("Disponible", "Equipo listo para ser asignado", True),
    ("Asignado", "Equipo entregado a un empleado", True),
    ("En Mantenimiento", "Equipo en proceso de mantenimiento o reparación", False),
    ("En recepción", "Equipo recién ingresado o devuelto", False),
    ("Dado de baja", "Equipo retirado del inventario", False),
]
MARCAS = ["Acer", "Apple", "Asus", "Canon", "Dell", "Epson", "HP", "Lenovo", "LG", "Logitech", "Samsung"]
AREAS = ["Administración", "Contabilidad", "Operaciones", "Sistemas", "Talento Humano", "Ventas"]
UBICACIONES = ["Bodega", "Oficina Principal", "Recepción", "Sala de Sistemas"]
CARGOS = ["Analista", "Asistente", "Auxiliar", "Coordinador", "Director", "Gerente", "Jefe de Área", "Técnico"]
# Catálogo -> (tabla donde se usa, columna). Sus valores se guardan normalizados (ver textos.etiqueta)
CATALOGOS_USO = {"marca": ("equipo", "marca"), "area": ("empleado", "area"),
                 "ubicacion": ("equipo", "ubicacion"), "cargo": ("empleado", "cargo")}
TIPOS = [
    ("Portátil", "Computo"), ("Escritorio", "Computo"), ("Monitor", "Periferico"),
    ("Teclado", "Periferico"), ("Mouse", "Periferico"), ("Impresora", "Impresion"),
]
CONFIG_DEFAULT = {
    "empresa": "Tu Empresa S.A.S.",
    "idioma": "es",
    "zona_horaria": "America/Bogota",
    "notif_actas": "1",
    "notif_mantenimiento": "1",
    "notif_asignaciones": "0",
    "umbral_sin_movimiento": "90",
    "respaldo_auto": "1",
    "ia_externa": "1",  # usar Claude (API de Anthropic) en el asistente si hay clave configurada
}


def _normalizar_catalogo(cur, cat, uso_tabla, uso_col):
    """Deja el catálogo con nombres normalizados (sin duplicados), importa los valores escritos a mano
    en el módulo que lo usa y unifica cómo se muestran en los registros existentes."""
    cur.execute(f"SELECT id, nombre, activo FROM {cat} ORDER BY id")
    grupos = {}
    for r in cur.fetchall():
        grupos.setdefault(textos.etiqueta(r["nombre"]).lower(), []).append(r)
    for filas in grupos.values():
        canon = textos.etiqueta(filas[0]["nombre"])
        keeper = next((f for f in filas if f["nombre"] == canon), filas[0])
        activo = any(f["activo"] for f in filas)
        for f in filas:
            if f["id"] != keeper["id"]:
                cur.execute(f"DELETE FROM {cat} WHERE id = %s", (f["id"],))
        if keeper["nombre"] != canon or keeper["activo"] != activo:
            cur.execute(f"UPDATE {cat} SET nombre = %s, activo = %s WHERE id = %s", (canon, activo, keeper["id"]))
    cur.execute(f"SELECT DISTINCT TRIM({uso_col}) AS v FROM {uso_tabla} WHERE TRIM(COALESCE({uso_col},'')) <> ''")
    for r in cur.fetchall():
        canon = textos.etiqueta(r["v"])
        cur.execute(f"INSERT INTO {cat} (nombre) SELECT %s WHERE NOT EXISTS (SELECT 1 FROM {cat} WHERE lower(nombre) = lower(%s))",
                    (canon, canon))
    cur.execute(f"SELECT nombre FROM {cat}")
    for r in cur.fetchall():
        cur.execute(f"UPDATE {uso_tabla} SET {uso_col} = %s WHERE lower(TRIM({uso_col})) = lower(%s) AND {uso_col} <> %s",
                    (r["nombre"], r["nombre"], r["nombre"]))


def normalizar_datos(cur):
    """Migración idempotente: catálogos y nombres con formato uniforme; correo en minúsculas; las fichas
    antiguas sin correo reciben uno provisional asociado a su nombre (nombre.apellido@ejemplo.com)."""
    for cat, (tabla, col) in CATALOGOS_USO.items():
        _normalizar_catalogo(cur, cat, tabla, col)
    cur.execute("SELECT id, nombres, apellidos, correo FROM empleado ORDER BY id")
    usados = set()
    filas = cur.fetchall()
    for r in filas:
        if (r["correo"] or "").strip():
            usados.add(textos.correo(r["correo"]))
    for r in filas:
        nombres, apellidos = textos.nombre_propio(r["nombres"]), textos.nombre_propio(r["apellidos"]) or None
        mail = textos.correo(r["correo"])
        if not mail:
            mail = textos.correo_ficticio(nombres, apellidos)
            if mail in usados:
                mail = mail.replace("@", f".{r['id']}@")
            usados.add(mail)
        if (nombres, apellidos, mail) != (r["nombres"], r["apellidos"], r["correo"]):
            cur.execute("UPDATE empleado SET nombres = %s, apellidos = %s, correo = %s WHERE id = %s",
                        (nombres, apellidos, mail, r["id"]))
    cur.execute("SELECT id, nombre_completo FROM usuario WHERE nombre_completo IS NOT NULL")
    for r in cur.fetchall():
        nuevo = textos.nombre_propio(r["nombre_completo"])
        if nuevo != r["nombre_completo"]:
            cur.execute("UPDATE usuario SET nombre_completo = %s WHERE id = %s", (nuevo, r["id"]))


def init_db():
    """Crea tablas faltantes, migra nombres antiguos y asegura el usuario Admin."""
    conn = connect()
    cur = conn.cursor()
    cur.execute(SCHEMA)
    cur.execute("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS foto VARCHAR(255)")  # foto de perfil (opcional)
    cur.execute("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS debe_cambiar_clave BOOLEAN NOT NULL DEFAULT FALSE")  # clave temporal: obliga a cambiarla al ingresar

    # El script original limitaba los roles; se amplía el CHECK para admitir los roles actuales.
    cur.execute("ALTER TABLE usuario DROP CONSTRAINT IF EXISTS usuario_rol_check")
    cur.execute(
        "ALTER TABLE usuario ADD CONSTRAINT usuario_rol_check CHECK "
        "(rol IN ('Administrador','Operador','Auditor','Jefe','Mantenimiento','Empleado'))"
    )
    # Responsable del mantenimiento (usuario con rol Mantenimiento) y catálogos de marca y área
    cur.execute("ALTER TABLE mantenimiento ADD COLUMN IF NOT EXISTS responsable_id INTEGER REFERENCES usuario(id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mant_responsable ON mantenimiento(responsable_id)")
    # Una acta puede cubrir varios equipos entregados juntos: cada asignación apunta a su acta
    cur.execute("ALTER TABLE asignacion ADD COLUMN IF NOT EXISTS acta_id INTEGER REFERENCES acta(id)")
    cur.execute("UPDATE asignacion a SET acta_id = ac.id FROM acta ac WHERE ac.asignacion_id = a.id AND a.acta_id IS NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_asignacion_acta ON asignacion(acta_id)")
    for tabla, lista in (("marca", MARCAS), ("area", AREAS), ("ubicacion", UBICACIONES), ("cargo", CARGOS)):
        for nombre in lista:
            cur.execute(f"INSERT INTO {tabla} (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING", (nombre,))
    normalizar_datos(cur)

    # Migración: 'En reparación' pasa a llamarse 'En Mantenimiento' (como en el diseño).
    cur.execute("SELECT id FROM estado_equipo WHERE nombre = 'En Mantenimiento'")
    if not cur.fetchone():
        cur.execute("UPDATE estado_equipo SET nombre = 'En Mantenimiento' WHERE nombre = 'En reparación'")
    for nombre, desc, crit in ESTADOS:
        cur.execute(
            "INSERT INTO estado_equipo (nombre, descripcion, es_critico) VALUES (%s,%s,%s) "
            "ON CONFLICT (nombre) DO NOTHING", (nombre, desc, crit))
    for nombre, cat in TIPOS:
        cur.execute(
            "INSERT INTO tipo_equipo (nombre, categoria) VALUES (%s,%s) ON CONFLICT (nombre) DO NOTHING",
            (nombre, cat))
    for k, v in CONFIG_DEFAULT.items():
        cur.execute("INSERT INTO configuracion (clave, valor) VALUES (%s,%s) ON CONFLICT (clave) DO NOTHING", (k, v))

    # Usuario administrador principal (se crea una sola vez; no se pisa su clave si ya existe).
    cur.execute("SELECT id FROM usuario WHERE lower(username) = lower(%s)", (ADMIN_USER,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO usuario (username, password_hash, nombre_completo, rol, activo) "
            "VALUES (%s,%s,%s,'Administrador',TRUE)",
            (ADMIN_USER, generate_password_hash(ADMIN_PASS), ADMIN_NOMBRE))
    conn.commit()
    cur.close()
    conn.close()

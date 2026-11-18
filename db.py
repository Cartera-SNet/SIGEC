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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ADMIN_USER = "Admin"
ADMIN_PASS = "@dm1n2026"
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


def init_db():
    """Crea tablas faltantes, migra nombres antiguos y asegura el usuario Admin."""
    conn = connect()
    cur = conn.cursor()
    cur.execute(SCHEMA)
    cur.execute("ALTER TABLE usuario ADD COLUMN IF NOT EXISTS foto VARCHAR(255)")  # foto de perfil (opcional)

    # El script original limitaba los roles; se amplía el CHECK para admitir los roles actuales.
    cur.execute("ALTER TABLE usuario DROP CONSTRAINT IF EXISTS usuario_rol_check")
    cur.execute(
        "ALTER TABLE usuario ADD CONSTRAINT usuario_rol_check CHECK "
        "(rol IN ('Administrador','Operador','Auditor','Jefe','Mantenimiento','Empleado'))"
    )
    # Responsable del mantenimiento (usuario con rol Mantenimiento) y catálogos de marca y área
    cur.execute("ALTER TABLE mantenimiento ADD COLUMN IF NOT EXISTS responsable_id INTEGER REFERENCES usuario(id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mant_responsable ON mantenimiento(responsable_id)")
    for nombre in MARCAS:
        cur.execute("INSERT INTO marca (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING", (nombre,))
    for nombre in AREAS:
        cur.execute("INSERT INTO area (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING", (nombre,))
    # Los valores ya escritos a mano en equipos y empleados pasan a ser opciones del catálogo
    cur.execute("""INSERT INTO marca (nombre) SELECT DISTINCT TRIM(marca) FROM equipo
                   WHERE TRIM(COALESCE(marca,'')) <> '' AND NOT EXISTS
                         (SELECT 1 FROM marca m WHERE lower(m.nombre) = lower(TRIM(equipo.marca)))
                   ON CONFLICT (nombre) DO NOTHING""")
    cur.execute("""INSERT INTO area (nombre) SELECT DISTINCT TRIM(area) FROM empleado
                   WHERE TRIM(COALESCE(area,'')) <> '' AND NOT EXISTS
                         (SELECT 1 FROM area a WHERE lower(a.nombre) = lower(TRIM(empleado.area)))
                   ON CONFLICT (nombre) DO NOTHING""")

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

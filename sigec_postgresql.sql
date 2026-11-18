-- ============================================================
-- SIGEC - Script de creación de Base de Datos en PostgreSQL
-- Sistema de Inventario y Gestión de Equipos de Cómputo
-- Basado en la ficha de documentación (secciones 10 y entidades)
-- ============================================================

-- Crear la base de datos (ejecutar como superusuario si es necesario)
-- CREATE DATABASE sigec;
-- \c sigec;

-- ============================================================
-- TABLAS MAESTRAS / CATÁLOGOS
-- ============================================================

CREATE TABLE tipo_equipo (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL UNIQUE,
    descripcion     TEXT,
    categoria       VARCHAR(50),
    activo          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE estado_equipo (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE,
    descripcion     TEXT,
    es_critico      BOOLEAN DEFAULT FALSE,  -- disponible, asignado no se deben eliminar
    activo          BOOLEAN DEFAULT TRUE
);

-- ============================================================
-- EMPLEADOS
-- ============================================================

CREATE TABLE empleado (
    id              SERIAL PRIMARY KEY,
    documento       VARCHAR(20) NOT NULL UNIQUE,
    nombres         VARCHAR(150) NOT NULL,
    apellidos       VARCHAR(150),
    area            VARCHAR(100),
    cargo           VARCHAR(100),
    correo          VARCHAR(120),
    telefono        VARCHAR(20),
    estado          VARCHAR(20) DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo')),
    fecha_ingreso   DATE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- EQUIPOS (Activos)
-- ============================================================

CREATE TABLE equipo (
    id              SERIAL PRIMARY KEY,
    tipo_id         INTEGER REFERENCES tipo_equipo(id),
    marca           VARCHAR(100),
    modelo          VARCHAR(100),
    numero_serie    VARCHAR(100) NOT NULL UNIQUE,   -- RN-08
    placa           VARCHAR(50),
    caracteristicas TEXT,
    estado_id       INTEGER REFERENCES estado_equipo(id),
    ubicacion       VARCHAR(150),
    fecha_ingreso   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    observaciones   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ASIGNACIONES
-- ============================================================

CREATE TABLE asignacion (
    id                  SERIAL PRIMARY KEY,
    equipo_id           INTEGER NOT NULL REFERENCES equipo(id),
    empleado_id         INTEGER NOT NULL REFERENCES empleado(id),
    fecha_asignacion    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_devolucion    TIMESTAMP,
    estado              VARCHAR(20) DEFAULT 'activa' CHECK (estado IN ('activa', 'cerrada')),
    observaciones       TEXT,
    created_by          VARCHAR(100),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ACTAS DE ENTREGA
-- ============================================================

CREATE TABLE acta (
    id                  SERIAL PRIMARY KEY,
    asignacion_id       INTEGER NOT NULL REFERENCES asignacion(id),
    fecha_generacion    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    estado              VARCHAR(20) DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'firmada')),
    fecha_firma         TIMESTAMP,
    firmado_por         VARCHAR(150),
    evidencia_path      VARCHAR(255),   -- ruta de imagen o PDF firmado
    observaciones       TEXT
);

-- ============================================================
-- HISTORIAL / MOVIMIENTOS (Trazabilidad)
-- ============================================================

CREATE TABLE historial (
    id                  SERIAL PRIMARY KEY,
    equipo_id           INTEGER NOT NULL REFERENCES equipo(id),
    tipo_evento         VARCHAR(50) NOT NULL,  -- Alta, Asignación, Devolución, Cambio Estado, etc.
    fecha               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario             VARCHAR(100) DEFAULT 'Operador',
    detalle             TEXT,
    estado_anterior     VARCHAR(50),
    estado_nuevo        VARCHAR(50),
    asignacion_id       INTEGER REFERENCES asignacion(id)
);

-- ============================================================
-- USUARIOS DEL SISTEMA (para control de acceso)
-- ============================================================

CREATE TABLE usuario (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    nombre_completo VARCHAR(150),
    rol             VARCHAR(30) DEFAULT 'Operador' CHECK (rol IN ('Administrador', 'Operador', 'Auditor', 'Jefe', 'Mantenimiento', 'Empleado')),
    empleado_id     INTEGER REFERENCES empleado(id),
    activo          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- MANTENIMIENTOS Y CONFIGURACIÓN (v1.1)
-- ============================================================

CREATE TABLE mantenimiento (
    id              SERIAL PRIMARY KEY,
    equipo_id       INTEGER NOT NULL REFERENCES equipo(id),
    tipo            VARCHAR(30) NOT NULL DEFAULT 'Preventivo',
    fecha           DATE NOT NULL DEFAULT CURRENT_DATE,
    descripcion     TEXT,
    estado          VARCHAR(20) NOT NULL DEFAULT 'En Proceso' CHECK (estado IN ('En Proceso','Completado')),
    fecha_fin       TIMESTAMP,
    created_by      VARCHAR(100),
    responsable_id  INTEGER REFERENCES usuario(id),   -- usuario con rol Mantenimiento
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Catálogos de marca y área (se usan como listas desplegables)
CREATE TABLE marca (id SERIAL PRIMARY KEY, nombre VARCHAR(100) NOT NULL UNIQUE, activo BOOLEAN DEFAULT TRUE);
CREATE TABLE area  (id SERIAL PRIMARY KEY, nombre VARCHAR(100) NOT NULL UNIQUE, activo BOOLEAN DEFAULT TRUE);

CREATE TABLE configuracion (
    clave   VARCHAR(60) PRIMARY KEY,
    valor   TEXT
);

-- NOTA: no es necesario ejecutar este script manualmente. SIGEC (db.py) crea y migra
-- las tablas al arrancar y crea el usuario administrador 'Admin'.

-- ============================================================
-- ÍNDICES RECOMENDADOS
-- ============================================================

CREATE INDEX idx_equipo_serie ON equipo(numero_serie);
CREATE INDEX idx_equipo_estado ON equipo(estado_id);
CREATE INDEX idx_asignacion_equipo ON asignacion(equipo_id);
CREATE INDEX idx_asignacion_empleado ON asignacion(empleado_id);
CREATE INDEX idx_asignacion_estado ON asignacion(estado);
CREATE INDEX idx_acta_asignacion ON acta(asignacion_id);
CREATE INDEX idx_historial_equipo ON historial(equipo_id);
CREATE INDEX idx_historial_fecha ON historial(fecha);

-- ============================================================
-- DATOS INICIALES (Estados y Tipos mínimos)
-- ============================================================

INSERT INTO estado_equipo (nombre, descripcion, es_critico) VALUES
('Disponible', 'Equipo listo para ser asignado', TRUE),
('Asignado', 'Equipo entregado a un empleado', TRUE),
('En Mantenimiento', 'Equipo en proceso de mantenimiento o reparación', FALSE),
('En recepción', 'Equipo recién ingresado o devuelto', FALSE),
('Dado de baja', 'Equipo retirado del inventario', FALSE);

INSERT INTO tipo_equipo (nombre, categoria) VALUES
('Portátil', 'Computo'),
('Escritorio', 'Computo'),
('Monitor', 'Periferico'),
('Teclado', 'Periferico'),
('Mouse', 'Periferico'),
('Impresora', 'Impresion');

-- ============================================================
-- COMENTARIOS (para documentación)
-- ============================================================

COMMENT ON TABLE equipo IS 'Inventario principal de equipos de cómputo';
COMMENT ON TABLE asignacion IS 'Registro de entregas de equipos a empleados';
COMMENT ON TABLE acta IS 'Actas de entrega generadas en cada asignación';
COMMENT ON TABLE historial IS 'Trazabilidad completa de movimientos del equipo';

-- Fin del script

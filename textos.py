"""
SIGEC - Normalización de textos
===============================
Reglas para que todo se vea profesional y uniforme sin importar cómo lo escriba cada persona:

  nombre_propio("julian VENEGAS")      -> "Julian Venegas"      (nombres y apellidos de personas)
  etiqueta("ADMINISTRACION y VENTAS")   -> "Administracion y Ventas"   (opciones de catálogos)
  etiqueta("ti")  /  etiqueta("TI")     -> "Ti"  /  "TI"        (las siglas de 3 letras o menos escritas en
                                                                mayúsculas se respetan: TI, HP, LG)
  correo("  Juan.Perez@MAIL.com ")      -> "juan.perez@mail.com"

Las tildes no se pueden adivinar: «Almacen» se corrige a mano en Configuración → Catálogos.
"""
import re
import unicodedata

# Palabras de enlace que quedan en minúscula cuando no son la primera palabra
_ENLACES_PERSONA = {"de", "del", "la", "las", "los", "y", "e"}  # («dos» es un número: «Oficina Dos»)
_ENLACES_CATALOGO = _ENLACES_PERSONA | {"el", "al", "en", "para", "con", "por", "sin"}
_SEPARADORES = re.compile(r"([-/'’.()])")
_CORREO = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _capitalizar(palabra):
    """Primera letra de cada tramo en mayúscula y el resto en minúscula (respeta guiones, apóstrofos y puntos)."""
    partes = _SEPARADORES.split(palabra.lower())
    return "".join(p[:1].upper() + p[1:] if p and p not in "-/'’.()" else p for p in partes)


def _normalizar(texto, enlaces, respetar_siglas):
    palabras = (texto or "").split()
    salida = []
    for i, p in enumerate(palabras):
        if i > 0 and p.lower() in enlaces:
            salida.append(p.lower())
        elif respetar_siglas and p.isupper() and (len(p) <= 3 or "." in p):  # TI, HP, LG y abreviaturas con puntos (RR.HH., S.A.S.)
            salida.append(p)
        else:
            salida.append(_capitalizar(p))
    return " ".join(salida)


def nombre_propio(texto):
    """Nombres y apellidos de personas: «julian VENEGAS» -> «Julian Venegas» (sin excepciones por siglas)."""
    return _normalizar(texto, _ENLACES_PERSONA, False)


def etiqueta(texto):
    """Opciones de catálogos (marca, área, cargo, ubicación): primera letra de cada palabra en mayúscula;
    las siglas de 3 letras o menos escritas en mayúsculas (TI, HP, LG) y las abreviaturas con puntos (RR.HH.) se conservan."""
    return _normalizar(texto, _ENLACES_CATALOGO, True)


def correo(texto):
    return (texto or "").strip().lower()


def correo_valido(texto):
    return bool(_CORREO.match(correo(texto))) and len(correo(texto)) <= 120


def sin_tildes(texto):
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()


def correo_ficticio(nombres, apellidos, dominio="ejemplo.com"):
    """Correo provisional asociado al nombre (solo para fichas antiguas sin correo): nombre.apellido@ejemplo.com."""
    def limpio(s):
        s = re.sub(r"[^a-z0-9]+", ".", sin_tildes(s).lower()).strip(".")
        return s
    n = limpio((nombres or "").split()[0] if (nombres or "").split() else "")
    a = limpio((apellidos or "").split()[0] if (apellidos or "").split() else "")
    local = ".".join(x for x in (n, a) if x) or "empleado"
    return f"{local}@{dominio}"

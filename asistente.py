"""
SIGEC - Asistente de ayuda con IA
=================================
Por defecto es LOCAL: ninguna pregunta sale a internet. Si el Administrador configura la variable
ANTHROPIC_API_KEY (y no lo desactiva en Configuración), las preguntas se responden con Claude (módulo ia.py);
si Claude no está disponible o falla, el asistente sigue con los motores locales y nunca se queda sin responder.

Motores locales, en dos niveles:
  1) Motor LLM local (Ollama): si está instalado y encendido (http://127.0.0.1:11434),
     se le entrega el fragmento relevante del manual + un resumen de los datos reales
     del sistema y redacta la respuesta en lenguaje natural.
  2) Motor interno (sin instalar nada): recuperación por relevancia (TF-IDF) sobre
     docs/manual.md + consultas directas a la base de datos para preguntas de datos
     ("¿cuántos equipos hay disponibles?", "¿quién tiene el equipo EQ-002?").

Como el conocimiento sale de docs/manual.md, al actualizar el manual el asistente
aprende los cambios automáticamente (regla del proyecto, ver CLAUDE.md).
"""
import json
import math
import os
import re
import time
import unicodedata
import urllib.request
from collections import Counter

import ia

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANUAL_MD = os.path.join(BASE_DIR, "docs", "manual.md")

STOP = set("""a al algo ante con contra cual cuales cuando de del desde donde el ella ellos en entre era es esta
estan este esto estos fue ha han hay la las le les lo los me mi mis mucho muy no nos o para pero por que
quien se si sin sobre su sus te tu tus un una uno unos unas y ya yo puedo puede pueden quiero quisiera
como cual favor hola gracias necesito dime decir saber sigec sistema programa""".split())


def norm(txt):
    txt = unicodedata.normalize("NFD", txt.lower())
    return "".join(c for c in txt if unicodedata.category(c) != "Mn")


# Variantes de una misma idea (devuelvo/devolver/devolución, asigno/asignar/asignación...)
CANON = (("devuelv", "devol"), ("devol", "devol"), ("asign", "asign"), ("firm", "firm"), ("imprim", "imprim"),
         ("impresi", "imprim"), ("instal", "instal"), ("registr", "registr"), ("contrasen", "contrasena"),
         ("clave", "contrasena"), ("mantenim", "mantenimiento"), ("reparac", "mantenimiento"),
         ("exporta", "exporta"), ("descarg", "descarg"), ("respald", "respald"), ("eliminar", "elimin"),
         ("elimin", "elimin"), ("borr", "elimin"))


def stem(w):
    for pref, canon in CANON:
        if w.startswith(pref):
            return canon
    for suf in ("ciones", "cion", "mente", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def tokens(txt):
    return [stem(w) for w in re.findall(r"[a-z0-9]+", norm(txt)) if w not in STOP and len(w) > 1]


# ----------------------------------------------------------------- base de conocimiento
_kb = {"mtime": 0, "docs": [], "df": Counter(), "n": 0}


def _cargar_manual():
    try:
        mtime = os.path.getmtime(MANUAL_MD)
    except OSError:
        return
    if mtime == _kb["mtime"]:
        return
    with open(MANUAL_MD, encoding="utf-8") as fh:
        texto = fh.read()
    secciones, titulo, buf = [], "Introducción", []
    for linea in texto.splitlines():
        if linea.startswith("!["):
            continue  # las capturas de pantalla no sirven como texto de respuesta
        if linea.startswith("|"):
            celdas = [c.strip() for c in linea.strip("|").split("|")]
            if set("".join(celdas)) <= set("-: "):
                continue
            linea = "• " + celdas[0] + (": " + " — ".join(celdas[1:]) if len(celdas) > 1 else "")
        m = re.match(r"^(#{2,3})\s+(.*)", linea)
        if m:
            if buf and "".join(buf).strip():
                secciones.append((titulo, "\n".join(buf).strip()))
            titulo, buf = m.group(2).strip(), []
        elif not linea.startswith("# "):
            buf.append(linea)
    if buf and "".join(buf).strip():
        secciones.append((titulo, "\n".join(buf).strip()))
    docs, df = [], Counter()
    for t, c in secciones:
        toks = tokens(t) * 3 + tokens(c)  # el título pesa más
        docs.append({"titulo": t, "texto": c, "tf": Counter(toks), "len": len(toks) or 1})
        df.update(set(toks))
    _kb.update(mtime=mtime, docs=docs, df=df, n=len(docs))


def buscar(pregunta, k=3):
    _cargar_manual()
    q = tokens(pregunta)
    if not q or not _kb["docs"]:
        return []
    puntajes = []
    for d in _kb["docs"]:
        s = 0.0
        for w in q:
            if w in d["tf"]:
                idf = math.log(1 + _kb["n"] / (1 + _kb["df"][w]))
                s += (d["tf"][w] / math.sqrt(d["len"])) * idf
        if s > 0:
            puntajes.append((s, d))
    puntajes.sort(key=lambda x: -x[0])
    return [(s, d) for s, d in puntajes[:k]]


# ----------------------------------------------------------------- consultas a datos reales
def _intent_datos(p, datos):
    """Responde preguntas sobre el estado actual del inventario usando la base de datos."""
    n = norm(p)
    r = datos("resumen")
    if re.search(r"cuant\w* (equipos|computador|portatil)", n) or "total de equipos" in n:
        if "disponible" in n:
            return f"Hay **{r['disponibles']}** equipos disponibles de un total de {r['total']}."
        if "asignad" in n:
            return f"Hay **{r['asignados']}** equipos asignados de un total de {r['total']}."
        if "mantenimiento" in n or "reparacion" in n:
            return f"Hay **{r['mantenimiento']}** equipos en mantenimiento."
        return (f"El inventario tiene **{r['total']}** equipos: {r['disponibles']} disponibles, "
                f"{r['asignados']} asignados y {r['mantenimiento']} en mantenimiento.")
    if re.search(r"(actas?).*(pendiente|sin firmar|falta)", n) or re.search(r"(pendiente|sin firmar).*actas?", n):
        return f"Hay **{r['actas_pendientes']}** actas pendientes de firma. Puedes firmarlas en *Inventario → Actas de entrega*."
    m = re.search(r"\b(eq-?\s?\d{1,6})\b", n)
    if m:
        e = datos("equipo", m.group(1))
        if e:
            resp = (f"**{e['codigo']}** — {e['tipo'] or 'Equipo'} {e['marca'] or ''} {e['modelo'] or ''} "
                    f"(serie {e['numero_serie']}). Estado: **{e['estado']}**.")
            if e.get("responsable"):
                resp += f" Responsable actual: **{e['responsable']}**."
            return resp.replace("  ", " ")
        return "No encontré un equipo con ese código. Revisa el código en *Inventario*."
    if re.search(r"(quien|que equipo).*(tiene|asignad)", n):
        return None
    return None


# ----------------------------------------------------------------- Ollama (opcional)
_ollama = {"ok": None, "t": 0}


def _ollama_url():
    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def ollama_disponible():
    if time.time() - _ollama["t"] < 30 and _ollama["ok"] is not None:
        return _ollama["ok"]
    try:
        with urllib.request.urlopen(_ollama_url() + "/api/tags", timeout=1.5) as r:
            modelos = [m["name"] for m in json.load(r).get("models", [])]
        _ollama["ok"] = bool(modelos)
        _ollama["modelos"] = modelos
    except Exception:
        _ollama["ok"] = False
    _ollama["t"] = time.time()
    return _ollama["ok"]


def _modelo():
    pref = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
    modelos = _ollama.get("modelos", [])
    if pref in modelos or not modelos:
        return pref
    base = pref.split(":")[0]
    for m in modelos:
        if m.startswith(base):
            return m
    return modelos[0]


SYSTEM = (
    "Eres el asistente de ayuda de SIGEC, un sistema de inventario y gestión de equipos de cómputo. "
    "Responde SIEMPRE en español, con claridad y en pocos pasos numerados cuando expliques un proceso. "
    "Usa únicamente la información de la sección CONTEXTO (manual y datos del sistema). "
    "Si la respuesta no está en el contexto, di que no lo sabes y sugiere revisar el manual. "
    "No inventes pantallas, botones ni datos."
)


def _llm(pregunta, contexto, historial):
    msgs = [{"role": "system", "content": SYSTEM + "\n\nCONTEXTO:\n" + contexto}]
    for h in (historial or [])[-4:]:
        if h.get("rol") in ("user", "assistant") and h.get("texto"):
            msgs.append({"role": h["rol"], "content": h["texto"][:800]})
    msgs.append({"role": "user", "content": pregunta})
    body = json.dumps({"model": _modelo(), "messages": msgs, "stream": False,
                       "options": {"temperature": 0.2, "num_predict": 400}}).encode()
    req = urllib.request.Request(_ollama_url() + "/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)["message"]["content"].strip()


# ----------------------------------------------------------------- API pública
SALUDOS = {"hola", "buenas", "buenos", "hey", "saludos", "ayuda", "ayudame"}


def responder(pregunta, historial=None, pagina="", datos=None, usuario=None, consultas=None, permitir_externo=True):
    """consultas = (q, q1, umbral, ahora) para que Claude consulte datos con herramientas de solo lectura."""
    pregunta = (pregunta or "").strip()[:800]
    if not pregunta:
        return {"respuesta": "Escríbeme tu pregunta y te ayudo.", "motor": "interno", "fuentes": []}
    if usuario and consultas and permitir_externo and ia.disponible():
        try:
            q, q1, umbral, ahora = consultas
            res = ia.responder(pregunta, historial, pagina, usuario, q, q1, umbral, ahora)
            return {"respuesta": res["respuesta"], "motor": res["motor"], "fuentes": []}
        except ia.ErrorIA:
            pass  # cae a los motores locales
    palabras = set(re.findall(r"[a-z]+", norm(pregunta)))
    if palabras and palabras <= (SALUDOS | STOP | {"tu", "me", "puedes", "ayudar"}):
        return {"respuesta": "¡Hola! Soy el asistente de SIGEC. Puedo explicarte cómo registrar equipos, asignarlos, "
                             "firmar actas, registrar mantenimientos o sacar reportes, y consultar datos del inventario "
                             "(por ejemplo: *¿cuántos equipos hay disponibles?*). ¿Qué necesitas?",
                "motor": "interno", "fuentes": []}

    dato = None
    snapshot = ""
    if datos:
        try:
            dato = _intent_datos(pregunta, datos)
            r = datos("resumen")
            snapshot = (f"Datos actuales: {r['total']} equipos en total; {r['disponibles']} disponibles; "
                        f"{r['asignados']} asignados; {r['mantenimiento']} en mantenimiento; "
                        f"{r['actas_pendientes']} actas pendientes de firma.")
        except Exception:
            dato = None

    consulta = pregunta
    if len(tokens(pregunta)) < 2 and pagina:
        consulta += " " + pagina.strip("/").replace("-", " ").replace("/", " ")
    hallazgos = buscar(consulta, k=3)
    fuentes = [d["titulo"] for _, d in hallazgos]

    if dato:
        return {"respuesta": dato, "motor": "interno (datos)", "fuentes": []}

    # 1) LLM local si está disponible
    if hallazgos and ollama_disponible():
        ctx = snapshot + "\n\n" + "\n\n".join(f"## {d['titulo']}\n{d['texto']}" for _, d in hallazgos[:3])
        try:
            texto = _llm(pregunta, ctx[:6000], historial)
            if texto:
                return {"respuesta": texto, "motor": "ollama:" + _modelo(), "fuentes": fuentes}
        except Exception:
            _ollama["ok"] = False  # cae al motor interno y reintenta más tarde

    # 2) Motor interno
    if hallazgos and hallazgos[0][0] > 0.05:
        mejor = hallazgos[0][1]
        texto = f"**{mejor['titulo']}**\n\n{mejor['texto']}"
        if len(hallazgos) > 1:
            texto += "\n\n*Temas relacionados:* " + ", ".join(d["titulo"] for _, d in hallazgos[1:])
        return {"respuesta": texto[:1800], "motor": "interno", "fuentes": fuentes}
    return {"respuesta": "No encontré eso en el manual. Prueba con otras palabras (por ejemplo: *asignar equipo*, "
                         "*acta*, *mantenimiento*, *reporte*, *contraseña*) o consulta el Manual de uso en PDF.",
            "motor": "interno", "fuentes": []}


def estado_motor():
    local = ("Ollama (" + _modelo() + ")") if ollama_disponible() else "Motor interno (sin Ollama)"
    if ia.configurado():
        return ia.estado_texto() + " · respaldo: " + local
    return local

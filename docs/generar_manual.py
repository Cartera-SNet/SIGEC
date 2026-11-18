"""
Genera docs/Manual_SIGEC.pdf a partir de docs/manual.md (+ capturas en docs/capturas).

Uso:   python docs/generar_manual.py
Requiere: reportlab  (ya está en requirements.txt)

REGLA DEL PROYECTO (ver CLAUDE.md): cada cambio en SIGEC debe actualizar docs/manual.md
y volver a ejecutar este script para que el PDF quede al día dentro del .zip.
"""
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
MD = os.path.join(AQUI, "manual.md")
PDF = os.path.join(AQUI, "Manual_SIGEC.pdf")
AZUL, AZUL2, GRIS = colors.HexColor("#0B2A66"), colors.HexColor("#1A6CFF"), colors.HexColor("#5B6B8C")

base = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=14.5, textColor=colors.HexColor("#16264A"), spaceAfter=6)
h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=AZUL, spaceBefore=16, spaceAfter=7)
h3 = ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=AZUL2, spaceBefore=10, spaceAfter=4)
cell = ParagraphStyle("c", parent=base, fontSize=9, leading=12, spaceAfter=0)
cap = ParagraphStyle("cap", parent=base, fontSize=8.5, textColor=GRIS, alignment=TA_CENTER, spaceAfter=10)


def inline(t):
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r'<font face="Courier" color="#0B2A66">\1</font>', t)
    return t


def version():
    m = re.search(r"Versi[oó]n\s+([\d.]+)", open(MD, encoding="utf-8").read())
    return m.group(1) if m else ""


def portada(story):
    logo = os.path.join(RAIZ, "static", "img", "logo_doc.png")
    story.append(Spacer(1, 3 * cm))
    if os.path.exists(logo):
        story.append(Image(logo, 7 * cm, 7 * cm, hAlign="CENTER"))
    story += [Spacer(1, .8 * cm),
              Paragraph("Manual de ayuda y uso", ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=30, leading=36, textColor=AZUL, alignment=TA_CENTER)),
              Paragraph("Sistema de Inventario y Gestión de Equipos de Cómputo", ParagraphStyle("t2", parent=base, fontSize=14, alignment=TA_CENTER, textColor=GRIS)),
              Spacer(1, .6 * cm),
              Paragraph(f"Versión {version()}", ParagraphStyle("t3", parent=base, fontSize=12, alignment=TA_CENTER, textColor=AZUL2)),
              PageBreak()]


def tabla(filas):
    data = [[Paragraph(inline(c), cell) for c in f] for f in filas]
    ancho = A4[0] - 4.4 * cm
    n = len(filas[0])
    widths = [ancho * .22, ancho * .78] if n == 2 else None
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEFB")),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#C9D6F2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FE")])]))
    return t


def construir():
    lineas = open(MD, encoding="utf-8").read().splitlines()
    story, parrafo, lista, tab = [], [], [], []
    portada(story)

    def vaciar():
        nonlocal parrafo, lista, tab
        if parrafo:
            story.append(Paragraph(inline(" ".join(parrafo)), base)); parrafo = []
        if lista:
            story.append(ListFlowable([ListItem(Paragraph(inline(x), base), leftIndent=14) for x in lista],
                                      bulletType="1" if lista_num else "bullet", bulletFontSize=9, leftIndent=16,
                                      bulletColor=AZUL2))
            story.append(Spacer(1, 4)); lista = []
        if tab:
            story.append(tabla(tab)); story.append(Spacer(1, 8)); tab = []

    lista_num = False
    for ln in lineas[1:]:
        if ln.startswith("# "):
            continue
        if ln.startswith("## "):
            vaciar()
            if len(story) > 2:
                pass
            story.append(Paragraph(inline(ln[3:]), h2))
        elif ln.startswith("### "):
            vaciar(); story.append(Paragraph(inline(ln[4:]), h3))
        elif ln.startswith("!["):
            vaciar()
            m = re.match(r"!\[(.*?)\]\((.*?)\)", ln)
            ruta = os.path.join(AQUI, m.group(2))
            if os.path.exists(ruta):
                from PIL import Image as PI
                w, h = PI.open(ruta).size
                ancho = A4[0] - 4.4 * cm
                alto = ancho * h / w
                if alto > 18 * cm:
                    alto = 18 * cm
                    ancho = alto * w / h
                im = Image(ruta, ancho, alto, hAlign="CENTER")
                im.hAlign = "CENTER"
                story.append(KeepTogether([im, Paragraph(inline(m.group(1)), cap)]))
        elif ln.startswith("|"):
            if parrafo or lista:
                vaciar()
            celdas = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not set("".join(celdas)) <= set("-: "):
                tab.append(celdas)
        elif re.match(r"^\d+\.\s", ln):
            if parrafo: vaciar()
            lista_num = True; lista.append(re.sub(r"^\d+\.\s", "", ln))
        elif ln.startswith("- "):
            if parrafo: vaciar()
            lista_num = False; lista.append(ln[2:])
        elif not ln.strip():
            vaciar()
        else:
            parrafo.append(ln.strip())
    vaciar()
    return story


def pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8); canvas.setFillColor(GRIS)
    canvas.drawString(2.2 * cm, 1.2 * cm, f"SIGEC · Manual de ayuda y uso · v{version()}")
    canvas.drawRightString(A4[0] - 2.2 * cm, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


if __name__ == "__main__":
    doc = SimpleDocTemplate(PDF, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm,
                            bottomMargin=2 * cm, title="Manual de ayuda y uso de SIGEC", author="SIGEC")
    doc.build(construir(), onFirstPage=lambda c, d: None, onLaterPages=pie)
    print("Manual generado:", PDF, f"(v{version()})")

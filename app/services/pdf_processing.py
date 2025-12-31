# -*- coding: utf-8 -*-
import pandas as pd
import io
import re
import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

FONT_NAME = "Helvetica"
FONT_SIZE = 6
MARGEN_X  = 8
MARGEN_Y  = 8
MAX_ANCHO_TEXTO = 180

def construir_mapa_skus(csv_content: bytes) -> dict:
    ventas = pd.read_csv(io.BytesIO(csv_content), encoding="latin1", sep=";")
    grupos = ventas.groupby("Número de orden", dropna=True)
    mapa = {}
    for nro_orden, df in grupos:
        items = []
        for _, row in df.iterrows():
            sku = str(row.get("SKU", "")).strip()
            if not sku or sku.lower() == "nan":
                continue
            cant = row.get("Cantidad del producto", 1)
            try:
                cant_int = int(cant)
            except Exception:
                cant_int = 1
            if cant_int > 1:
                items.append(f"{sku} x{cant_int}")
            else:
                items.append(sku)
        if not items:
            continue
        texto = " | ".join(items)
        mapa[str(int(nro_orden))] = texto
    return mapa

def extraer_nro_interno(texto_pagina: str) -> str | None:
    if not isinstance(texto_pagina, str):
        return None
    t = texto_pagina.replace("NÂ°", "N°").replace("Nº", "N°")
    t = t.replace("\n", " ")
    m = re.search(r"Interno\s*:\s*#?\s*([0-9]+)", t, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    return None

def wrap_text(texto: str, max_width: float, font_name: str, font_size: int, canvas_obj) -> list:
    if not texto: return []
    palabras = texto.split(" ")
    lineas = []
    linea_actual = ""
    for palabra in palabras:
        candidata = (linea_actual + " " + palabra).strip()
        w = canvas_obj.stringWidth(candidata, font_name, font_size)
        if w <= max_width:
            linea_actual = candidata
        else:
            if linea_actual: lineas.append(linea_actual)
            linea_actual = palabra
    if linea_actual: lineas.append(linea_actual)
    return lineas

def process_pdf_labels(pdf_bytes: bytes, skus_map: dict) -> bytes:
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    writer = PyPDF2.PdfWriter()
    
    for idx, page in enumerate(reader.pages):
        texto = page.extract_text()
        nro_interno = extraer_nro_interno(texto)
        
        if nro_interno:
            skus_texto = skus_map.get(str(int(nro_interno)))
            if skus_texto:
                packet = io.BytesIO()
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                c = canvas.Canvas(packet, pagesize=(width, height))
                c.setFont(FONT_NAME, FONT_SIZE)
                
                texto_mostrar = f"SKU: {skus_texto}"
                lineas = wrap_text(texto_mostrar, MAX_ANCHO_TEXTO, FONT_NAME, FONT_SIZE, c)
                
                y = MARGEN_Y
                for linea in lineas:
                    c.drawString(MARGEN_X, y, linea)
                    y += FONT_SIZE + 1
                
                c.save()
                packet.seek(0)
                overlay_pdf = PyPDF2.PdfReader(packet)
                page.merge_page(overlay_pdf.pages[0])
        
        writer.add_page(page)
        
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output.read()

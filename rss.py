import re
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup


WEB_URL = "https://biatgroup.com/es/informacion-inversores/"
BASE_URL = "https://biatgroup.com"
ARCHIVO_RSS = Path("biat-inversores.xml")

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

MESES = {
    "ene": 1,
    "enero": 1,
    "jan": 1,
    "feb": 2,
    "febrero": 2,
    "mar": 3,
    "marzo": 3,
    "abr": 4,
    "abril": 4,
    "apr": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "junio": 6,
    "jul": 7,
    "julio": 7,
    "ago": 8,
    "agosto": 8,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "septiembre": 9,
    "oct": 10,
    "octubre": 10,
    "nov": 11,
    "noviembre": 11,
    "dic": 12,
    "diciembre": 12,
    "dec": 12,
}


def limpiar_texto(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def escapar_xml(texto):
    return (
        str(texto)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def descargar_pagina():
    ultimo_error = None

    for intento in range(1, 4):
        try:
            respuesta = requests.get(
                WEB_URL,
                headers=CABECERAS,
                timeout=90,
                allow_redirects=True,
                verify=False,
            )
            respuesta.raise_for_status()

            if len(respuesta.text.strip()) < 500:
                raise RuntimeError(
                    "BIAT Group devolvió una página incompleta"
                )

            return respuesta.text

        except (
            requests.RequestException,
            RuntimeError,
        ) as error:
            ultimo_error = error

            print(
                f"Intento {intento} fallido: {error}"
            )

            if intento < 3:
                time.sleep(5 * intento)

    raise RuntimeError(
        f"No se pudo descargar BIAT Group: {ultimo_error}"
    )


def convertir_fecha(texto):
    texto = limpiar_texto(texto).lower()

    coincidencia = re.search(
        r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b",
        texto,
    )

    if coincidencia:
        dia = int(coincidencia.group(1))
        mes = int(coincidencia.group(2))
        anio = int(coincidencia.group(3))

        try:
            return datetime(
                anio,
                mes,
                dia,
                12,
                0,
                0,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    coincidencia = re.search(
        r"\b(\d{1,2})\s+"
        r"(ene|enero|jan|feb|febrero|mar|marzo|"
        r"abr|abril|apr|may|mayo|jun|junio|"
        r"jul|julio|ago|agosto|aug|sep|sept|"
        r"septiembre|oct|octubre|nov|noviembre|"
        r"dic|diciembre|dec)"
        r"(?:\s+de)?\s+(\d{4})\b",
        texto,
    )

    if coincidencia:
        dia = int(coincidencia.group(1))
        mes = MESES[coincidencia.group(2)]
        anio = int(coincidencia.group(3))

        try:
            return datetime(
                anio,
                mes,
                dia,
                12,
                0,
                0,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    return None


def es_pdf(url):
    ruta = urlparse(url).path.lower()
    return ruta.endswith(".pdf")


def es_pagina_documento(url):
    ruta = urlparse(url).path.lower().rstrip("/")

    return bool(
        re.match(
            r"^/es/documento/[^/]+$",
            ruta,
        )
    )


def buscar_contenedor(enlace):
    actual = enlace

    for _ in range(10):
        actual = actual.parent

        if actual is None:
            break

        texto = limpiar_texto(
            actual.get_text(" ", strip=True)
        )

        if convertir_fecha(texto) is not None:
            if len(texto) <= 2500:
                return actual

    return enlace.parent


def obtener_titulo_contenedor(
    enlace,
    contenedor,
):
    candidatos = []

    for etiqueta in contenedor.find_all(
        ["h2", "h3", "h4", "h5", "h6", "strong"]
    ):
        texto = limpiar_texto(
            etiqueta.get_text(" ", strip=True)
        )

        if len(texto) >= 10:
            if not texto.isdigit():
                candidatos.append(texto)

    for candidato in candidatos:
        if convertir_fecha(candidato) is not None:
            return candidato

    for candidato in candidatos:
        if candidato.lower() not in {
            "información inversores",
            "hechos relevantes",
            "información financiera",
            "junta general",
        }:
            return candidato

    texto_enlace = limpiar_texto(
        enlace.get_text(" ", strip=True)
    )

    if texto_enlace.lower() not in {
        "pdf",
        "↓ pdf",
        "descargar",
        "download",
        "leer más",
        "leer mas",
    }:
        if len(texto_enlace) >= 10:
            return texto_enlace

    texto = limpiar_texto(
        contenedor.get_text(" ", strip=True)
    )

    # Elimina textos de los botones.
    texto = re.sub(
        r"(?:↓\s*)?PDF",
        " ",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(
        r"\bdescargar\b",
        " ",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(
        r"\bdownload\b",
        " ",
        texto,
        flags=re.IGNORECASE,
    )
    texto = limpiar_texto(texto)

    # Busca un título que termine con una fecha entre paréntesis.
    coincidencia = re.search(
        r"([^|]{10,300}?"
        r"\(\d{1,2}[./-]\d{1,2}[./-]\d{4}\))",
        texto,
    )

    if coincidencia:
        titulo = limpiar_texto(
            coincidencia.group(1)
        )

        titulo = re.sub(
            r"^\d{4}\s+\d+\s+documentos?\s*",
            "",
            titulo,
            flags=re.IGNORECASE,
        )

        return titulo

    return texto[:300]


def obtener_descripcion(
    contenedor,
    titulo,
):
    texto = limpiar_texto(
        contenedor.get_text(" ", strip=True)
    )

    texto = texto.replace(
        titulo,
        " ",
    )

    texto = re.sub(
        r"(?:↓\s*)?PDF",
        " ",
        texto,
        flags=re.IGNORECASE,
    )

    texto = re.sub(
        r"\b(?:descargar|download|leer más|leer mas)\b",
        " ",
        texto,
        flags=re.IGNORECASE,
    )

    texto = limpiar_texto(texto)

    if texto == titulo:
        return ""

    return texto[:1000]


def buscar_pdf_en_contenedor(
    contenedor,
):
    for enlace in contenedor.find_all(
        "a",
        href=True,
    ):
        url = urljoin(
            BASE_URL,
            enlace.get("href"),
        )

        if es_pdf(url):
            return url

    return ""


def obtener_documentos(html):
    soup = BeautifulSoup(html, "html.parser")
    documentos = []
    vistos = set()

    for enlace in soup.find_all("a", href=True):
        url_original = urljoin(
            BASE_URL,
            enlace.get("href"),
        )
        url_original = url_original.split("#")[0]

        if not (
            es_pdf(url_original)
            or es_pagina_documento(url_original)
        ):
            continue

        contenedor = buscar_contenedor(enlace)

        if contenedor is None:
            continue

        texto_contenedor = limpiar_texto(
            contenedor.get_text(" ", strip=True)
        )

        fecha = convertir_fecha(
            texto_contenedor
        )

        if fecha is None:
            fecha = convertir_fecha(
                enlace.get("title", "")
            )

        if fecha is None:
            continue

        titulo = obtener_titulo_contenedor(
            enlace,
            contenedor,
        )

        if len(titulo) < 10:
            continue

        pdf = ""

        if es_pdf(url_original):
            pdf = url_original
        else:
            pdf = buscar_pdf_en_contenedor(
                contenedor
            )

        url_item = pdf or url_original
        guid = url_original.rstrip("/")

        if guid in vistos:
            continue

        descripcion = obtener_descripcion(
            contenedor,
            titulo,
        )

        documentos.append(
            {
                "titulo": titulo,
                "url": url_item,
                "guid": guid,
                "fecha": fecha,
                "descripcion": descripcion,
                "pdf": pdf,
            }
        )

        vistos.add(guid)

    documentos.sort(
        key=lambda documento: documento["fecha"],
        reverse=True,
    )

    if not documentos:
        raise RuntimeError(
            "No se encontraron documentos para "
            "inversores de BIAT Group"
        )

    return documentos[:100]


def crear_rss(documentos):
    ahora = datetime.now(timezone.utc)

    partes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        (
            "<title>BIAT Group - Información "
            "para inversores</title>"
        ),
        f"<link>{escapar_xml(WEB_URL)}</link>",
        (
            "<description>Documentos, comunicaciones y "
            "hechos relevantes de BIAT Group</description>"
        ),
        "<language>es</language>",
        f"<lastBuildDate>{format_datetime(ahora)}</lastBuildDate>",
        "<ttl>60</ttl>",
    ]

    for documento in documentos:
        partes.extend(
            [
                "<item>",
                (
                    f"<title>"
                    f"{escapar_xml(documento['titulo'])}"
                    f"</title>"
                ),
                (
                    f"<link>"
                    f"{escapar_xml(documento['url'])}"
                    f"</link>"
                ),
                (
                    f'<guid isPermaLink="true">'
                    f"{escapar_xml(documento['guid'])}"
                    f"</guid>"
                ),
                (
                    f"<pubDate>"
                    f"{format_datetime(documento['fecha'])}"
                    f"</pubDate>"
                ),
                (
                    f"<description>"
                    f"{escapar_xml(documento['descripcion'])}"
                    f"</description>"
                ),
            ]
        )

        if documento["pdf"]:
            partes.append(
                (
                    f'<enclosure url="'
                    f'{escapar_xml(documento["pdf"])}" '
                    f'type="application/pdf" />'
                )
            )

        partes.append("</item>")

    partes.extend(
        [
            "</channel>",
            "</rss>",
        ]
    )

    return "\n".join(partes)


def guardar_rss(contenido):
    temporal = ARCHIVO_RSS.with_suffix(
        ".xml.tmp"
    )

    temporal.write_text(
        contenido,
        encoding="utf-8",
    )

    temporal.replace(
        ARCHIVO_RSS
    )


def main():
    html = descargar_pagina()
    documentos = obtener_documentos(html)
    contenido = crear_rss(documentos)
    guardar_rss(contenido)

    print(
        f"RSS de BIAT Group creada con "
        f"{len(documentos)} documentos"
    )

    for documento in documentos[:10]:
        print(
            documento["fecha"].strftime("%d/%m/%Y"),
            "-",
            documento["titulo"],
        )


if __name__ == "__main__":
    main()

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


def descargar(url):
    ultimo_error = None

    for intento in range(1, 4):
        try:
            respuesta = requests.get(
                url,
                headers=CABECERAS,
                timeout=90,
                allow_redirects=True,
                verify=False,
            )
            respuesta.raise_for_status()

            if len(respuesta.text.strip()) < 300:
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
                f"Intento {intento} fallido para "
                f"{url}: {error}"
            )

            if intento < 3:
                time.sleep(4 * intento)

    raise RuntimeError(
        f"No se pudo descargar {url}: {ultimo_error}"
    )


def es_enlace_documento(url):
    ruta = urlparse(url).path.lower().rstrip("/")

    return bool(
        re.match(
            r"^/es/documento/[^/]+$",
            ruta,
        )
    )


def convertir_fecha(texto):
    texto = limpiar_texto(texto).lower()

    coincidencia = re.search(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
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


def convertir_fecha_iso(valor):
    if not valor:
        return None

    try:
        fecha = datetime.fromisoformat(
            valor.strip().replace("Z", "+00:00")
        )

        if fecha.tzinfo is None:
            fecha = fecha.replace(
                tzinfo=timezone.utc
            )

        return fecha.astimezone(timezone.utc)

    except ValueError:
        return None


def obtener_enlaces_documentos(html):
    soup = BeautifulSoup(html, "html.parser")
    documentos = []
    vistos = set()

    for enlace in soup.find_all("a", href=True):
        url = urljoin(
            BASE_URL,
            enlace.get("href"),
        )
        url = url.split("#")[0].split("?")[0].rstrip("/")

        if not es_enlace_documento(url):
            continue

        if url in vistos:
            continue

        titulo = limpiar_texto(
            enlace.get_text(" ", strip=True)
        )

        if titulo.lower() in {
            "pdf",
            "↓ pdf",
            "descargar",
            "leer más",
            "leer mas",
        }:
            titulo = ""

        documentos.append(
            {
                "url_detalle": url,
                "titulo_inicial": titulo,
            }
        )

        vistos.add(url)

    if not documentos:
        raise RuntimeError(
            "No se encontraron documentos para inversores "
            "de BIAT Group"
        )

    # La página está ordenada de más reciente a más antiguo.
    return documentos[:80]


def obtener_fecha(soup, texto, titulo):
    fecha = convertir_fecha(titulo)

    if fecha:
        return fecha

    fecha = convertir_fecha(texto)

    if fecha:
        return fecha

    meta = soup.find(
        "meta",
        attrs={"property": "article:published_time"},
    )

    if meta and meta.get("content"):
        fecha = convertir_fecha_iso(
            meta.get("content")
        )

        if fecha:
            return fecha

    tiempo = soup.find("time")

    if tiempo:
        fecha = convertir_fecha_iso(
            tiempo.get("datetime")
        )

        if fecha:
            return fecha

        fecha = convertir_fecha(
            tiempo.get_text(" ", strip=True)
        )

        if fecha:
            return fecha

    return datetime.now(timezone.utc)


def buscar_pdf(soup, url_detalle):
    for enlace in soup.find_all("a", href=True):
        href = urljoin(
            url_detalle,
            enlace.get("href"),
        )

        ruta = urlparse(href).path.lower()

        if ruta.endswith(".pdf"):
            return href

    return ""


def obtener_descripcion(soup):
    meta = soup.find(
        "meta",
        attrs={"name": "description"},
    )

    if meta and meta.get("content"):
        descripcion = limpiar_texto(
            meta.get("content")
        )

        texto_generico = (
            "biat group es un grupo empresarial líder"
        )

        if (
            len(descripcion) >= 40
            and texto_generico not in descripcion.lower()
        ):
            return descripcion[:1200]

    for selector in [
        "article p",
        "main p",
        ".post-content p",
        ".entry-content p",
    ]:
        parrafos = soup.select(selector)

        textos = [
            limpiar_texto(
                parrafo.get_text(" ", strip=True)
            )
            for parrafo in parrafos
        ]

        textos = [
            texto
            for texto in textos
            if len(texto) >= 40
        ]

        if textos:
            return " ".join(textos)[:1200]

    return ""


def completar_documento(documento):
    html = descargar(
        documento["url_detalle"]
    )
    soup = BeautifulSoup(html, "html.parser")

    encabezado = soup.find("h1")

    if encabezado:
        titulo = limpiar_texto(
            encabezado.get_text(" ", strip=True)
        )
    else:
        titulo = documento["titulo_inicial"]

    if len(titulo) < 10:
        titulo = documento["titulo_inicial"]

    if len(titulo) < 10:
        titulo = urlparse(
            documento["url_detalle"]
        ).path.rstrip("/").split("/")[-1]

        titulo = limpiar_texto(
            titulo.replace("-", " ")
        ).title()

    texto_pagina = limpiar_texto(
        soup.get_text(" ", strip=True)
    )

    fecha = obtener_fecha(
        soup,
        texto_pagina,
        titulo,
    )

    pdf = buscar_pdf(
        soup,
        documento["url_detalle"],
    )

    descripcion = obtener_descripcion(soup)

    if pdf:
        descripcion_pdf = (
            f"Documento PDF: {pdf}"
        )

        if descripcion:
            descripcion = (
                descripcion + " " + descripcion_pdf
            )[:1500]
        else:
            descripcion = descripcion_pdf

    return {
        "titulo": titulo,
        "url": pdf or documento["url_detalle"],
        "guid": documento["url_detalle"],
        "fecha": fecha,
        "descripcion": descripcion,
        "pdf": pdf,
    }


def obtener_documentos():
    html = descargar(WEB_URL)
    enlaces = obtener_enlaces_documentos(html)
    documentos = []

    for enlace in enlaces:
        try:
            documentos.append(
                completar_documento(enlace)
            )
        except Exception as error:
            print(
                f"No se pudo completar "
                f"{enlace['url_detalle']}: {error}"
            )

    documentos.sort(
        key=lambda documento: documento["fecha"],
        reverse=True,
    )

    if not documentos:
        raise RuntimeError(
            "No se pudieron obtener documentos "
            "para inversores de BIAT Group"
        )

    return documentos[:60]


def crear_rss(documentos):
    ahora = datetime.now(timezone.utc)

    partes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        "<title>BIAT Group - Información para inversores</title>",
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
    temporal = ARCHIVO_RSS.with_suffix(".xml.tmp")

    temporal.write_text(
        contenido,
        encoding="utf-8",
    )

    temporal.replace(
        ARCHIVO_RSS
    )


def main():
    documentos = obtener_documentos()
    contenido = crear_rss(documentos)
    guardar_rss(contenido)

    print(
        f"RSS de BIAT Group creada correctamente con "
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

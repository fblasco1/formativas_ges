"""
Listado de equipos 2025 ordenados por zona (región).
Un solo torneo; cada equipo se asigna a la zona donde más partidos jugó.
Los nombres se normalizan con el mapeo de equipos antes de exportar.
Genera CSV, HTML y PDF listos para imprimir.
"""
import sys
from pathlib import Path

# Permitir importar mapeos desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from mapeos.loader import cargar_mapeo_equipos, normalizar_equipo

# Orden de zonas para el listado (puedes ajustarlo)
ORDEN_ZONAS = ["CENTRO", "NORTE", "OESTE", "SUR", "NIVELACION", "INTERCONFERENCIA", "INTERCONFERENCIA A", "INTERCONFERENCIA B"]


def cargar_partidos_2025(ruta: str = None) -> pd.DataFrame:
    if ruta is None:
        ruta = Path(__file__).resolve().parent.parent / "Data" / "partidos_2025.csv"
    df = pd.read_csv(ruta, sep=",", encoding="utf-8", on_bad_lines="skip")
    for col in ["zona", "local", "visitante"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()
    return df


def equipos_por_zona_2025(df: pd.DataFrame) -> pd.DataFrame:
    """
    Asigna cada equipo a la zona donde más partidos jugó en 2025 y devuelve
    un DataFrame [zona, equipo] ordenado por zona y por nombre de equipo.
    """
    local = df[["local", "zona"]].rename(columns={"local": "equipo"})
    visitante = df[["visitante", "zona"]].rename(columns={"visitante": "equipo"})
    partidos_equipo_zona = pd.concat([local, visitante], ignore_index=True)

    partidos_equipo_zona = partidos_equipo_zona[
        (partidos_equipo_zona["equipo"].str.len() > 0)
        & (partidos_equipo_zona["equipo"] != "NAN")
        & (partidos_equipo_zona["zona"].str.len() > 0)
    ]

    conteo = partidos_equipo_zona.groupby(["equipo", "zona"]).size().reset_index(name="partidos")
    idx_max = conteo.groupby("equipo")["partidos"].idxmax()
    equipo_zona = conteo.loc[idx_max, ["equipo", "zona"]].drop_duplicates()

    def orden_zona(z):
        try:
            return ORDEN_ZONAS.index(z) if z in ORDEN_ZONAS else 999
        except Exception:
            return 999

    equipo_zona["_orden_zona"] = equipo_zona["zona"].map(orden_zona)
    equipo_zona = equipo_zona.sort_values(["_orden_zona", "zona", "equipo"]).drop(columns=["_orden_zona"])
    return equipo_zona.reset_index(drop=True)


def aplicar_mapeo_equipos(listado: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica el mapeo de nombres de equipos (mapeos/equipos_map.json) y elimina
    duplicados (zona, equipo) que queden tras normalizar.
    """
    mapeo = cargar_mapeo_equipos()
    listado = listado.copy()
    listado["equipo"] = listado["equipo"].apply(lambda x: normalizar_equipo(x, mapeo))
    listado = listado.drop_duplicates(subset=["zona", "equipo"])

    def orden_zona(z):
        try:
            return ORDEN_ZONAS.index(z) if z in ORDEN_ZONAS else 999
        except Exception:
            return 999

    listado["_orden_zona"] = listado["zona"].map(orden_zona)
    listado = listado.sort_values(["_orden_zona", "zona", "equipo"]).drop(columns=["_orden_zona"])
    return listado.reset_index(drop=True)


def exportar_html(listado: pd.DataFrame, out_path: Path, titulo: str = "Equipos 2025 por zona") -> None:
    """Genera un HTML imprimible (abrir en navegador → Imprimir → Guardar como PDF)."""
    html_lines = [
        "<!DOCTYPE html>",
        "<html lang='es'>",
        "<head>",
        "<meta charset='UTF-8'>",
        f"<title>{titulo}</title>",
        "<style>",
        "body { font-family: 'Segoe UI', Arial, sans-serif; margin: 2cm; color: #222; }",
        "h1 { text-align: center; font-size: 1.4rem; margin-bottom: 1.5rem; }",
        ".zona { font-weight: bold; font-size: 1.1rem; margin-top: 1rem; margin-bottom: 0.3rem; "
        "border-bottom: 1px solid #ccc; padding-bottom: 2px; }",
        ".equipos { margin-left: 1rem; column-count: 2; column-gap: 2rem; }",
        ".equipo { padding: 2px 0; }",
        "@media print { body { margin: 1.5cm; } .zona { break-after: avoid; } }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>{titulo}</h1>",
        "<p style='text-align:center; font-size: 0.9rem; color: #555;'>Torneo formativas FeBAMBA 2025</p>",
    ]
    for zona in listado["zona"].unique():
        equipos_zona = listado[listado["zona"] == zona]["equipo"].tolist()
        html_lines.append(f"<div class='zona'>{zona}</div>")
        html_lines.append("<div class='equipos'>")
        for eq in equipos_zona:
            html_lines.append(f"<div class='equipo'>{eq}</div>")
        html_lines.append("</div>")
    html_lines.append("</body></html>")
    out_path.write_text("\n".join(html_lines), encoding="utf-8")


def exportar_pdf(listado: pd.DataFrame, out_path: Path, titulo: str = "Equipos 2025 por zona") -> None:
    """Genera PDF con reportlab (pip install reportlab)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise ImportError("Para generar PDF instala: pip install reportlab")

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Titulo",
        parent=styles["Heading1"],
        fontSize=14,
        alignment=1,
        spaceAfter=6,
    )
    zona_style = ParagraphStyle(
        "Zona",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        spaceBefore=10,
        spaceAfter=4,
    )
    story = [Paragraph(titulo, title_style), Spacer(1, 0.3 * cm)]
    story.append(Paragraph("Torneo formativas FeBAMBA 2025", ParagraphStyle("Sub", parent=styles["Normal"], fontSize=9, alignment=1, textColor="gray")))
    story.append(Spacer(1, 0.5 * cm))

    for zona in listado["zona"].unique():
        equipos_zona = listado[listado["zona"] == zona]["equipo"].tolist()
        story.append(Paragraph(zona, zona_style))
        # Tabla de una columna para equipos (evita cortes raros)
        data = [[eq] for eq in equipos_zona]
        t = Table(data, colWidths=[16 * cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.2 * cm))
    doc.build(story)


def main():
    df = cargar_partidos_2025()
    listado = equipos_por_zona_2025(df)
    # Aplicar mapeo de nombres antes de exportar (CSV, HTML, PDF)
    listado = aplicar_mapeo_equipos(listado)
    out_dir = Path(__file__).resolve().parent.parent / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    titulo = "Equipos 2025 por zona"

    # CSV
    csv_path = out_dir / "equipos_2025_por_zona.csv"
    listado.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"CSV:  {csv_path}")

    # HTML (abrir en navegador → Imprimir → Guardar como PDF)
    html_path = out_dir / "equipos_2025_por_zona.html"
    exportar_html(listado, html_path, titulo=titulo)
    print(f"HTML: {html_path}  → abrir y usar Imprimir → Guardar como PDF")

    # PDF (si está instalado reportlab)
    pdf_path = out_dir / "equipos_2025_por_zona.pdf"
    try:
        exportar_pdf(listado, pdf_path, titulo=titulo)
        print(f"PDF:  {pdf_path}")
    except ImportError as e:
        print(f"PDF:  no generado ({e})")

    print()
    print(listado.to_string(index=False))
    return listado


if __name__ == "__main__":
    main()

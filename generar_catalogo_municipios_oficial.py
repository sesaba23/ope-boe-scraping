"""Genera el catálogo municipal oficial compatible con los consumidores actuales.

Fuentes: relación INE de municipios a 01-01-2026 y NGMEP 2026 del CNIG.
No modifica el Excel ni sustituye el catálogo heredado automáticamente.
"""
import argparse
from datetime import date
import json
from pathlib import Path

import pandas as pd
import requests

from mapa_plazas import normalizar_nombre_municipal


URL_INE = "https://www.ine.es/daco/daco42/codmun/26codmun.xlsx"
URL_CNIG = "https://centrodedescargas.cnig.es/CentroDescargas/descargaDir"
POST_CNIG = {"secuencial": "9000004", "secDescDirLA": "9000004", "codSerie": "NGMEN"}


def descargar_fuentes(directorio):
    """Descarga las fuentes oficiales y devuelve sus rutas locales."""
    directorio = Path(directorio); directorio.mkdir(parents=True, exist_ok=True)
    ine = directorio / "ine_municipios_2026.xlsx"
    cnig_zip = directorio / "cnig_ngmep_2026.zip"
    for ruta, respuesta in (
        (ine, requests.get(URL_INE, timeout=60)),
        (cnig_zip, requests.post(URL_CNIG, data=POST_CNIG, timeout=120)),
    ):
        respuesta.raise_for_status()
        ruta.write_bytes(respuesta.content)
    return ine, cnig_zip


def _leer_ine(ruta):
    filas = []
    for hoja in pd.ExcelFile(ruta).sheet_names:
        bruto = pd.read_excel(ruta, sheet_name=hoja, header=None, dtype=str).fillna("")
        provincia = str(bruto.iloc[1, 0]).strip()
        datos = bruto.iloc[3:, :4].copy()
        datos.columns = ("CPRO", "CMUN", "DC", "Municipio")
        for fila in datos.to_dict(orient="records"):
            if not str(fila["CMUN"]).strip():
                continue
            codigo = f"{str(fila['CPRO']).zfill(2)}{str(fila['CMUN']).zfill(3)}"
            filas.append({"Codigo_INE": codigo, "Municipio": str(fila["Municipio"]).strip(), "Provincia": provincia})
    return pd.DataFrame(filas)


def generar_catalogo(ine, cnig_municipios, cnig_provincias):
    """Cruza el código INE con coordenadas CNIG y conserva el esquema antiguo."""
    ine_df = _leer_ine(ine)
    cnig = pd.read_csv(cnig_municipios, sep=";", encoding="cp1252", dtype=str).fillna("")
    # COD_GEO aún puede ser 00000 para municipios de creación reciente;
    # los cinco primeros dígitos de COD_INE son siempre CPRO+CMUN.
    cnig["Codigo_INE"] = cnig["COD_INE"].str.zfill(11).str[:5]
    campos = ["Codigo_INE", "COMUNIDAD_AUTONOMA", "POBLACION_MUNI", "ALTITUD",
              "LONGITUD_ETRS89_REGCAN95", "LATITUD_ETRS89_REGCAN95"]
    # Comunidad procede de PROVINCIAS.CSV; al no estar en MUNICIPIOS.CSV se
    # completa más abajo mediante código provincial.
    coordenadas = cnig[[x for x in campos if x in cnig.columns]].copy()
    resultado = ine_df.merge(coordenadas, on="Codigo_INE", how="left", validate="one_to_one")
    provincias = pd.read_csv(cnig_provincias, sep=";", encoding="cp1252", dtype=str).fillna("")
    comunidades = provincias[["COD_PROV", "COMUNIDAD_AUTONOMA"]].rename(columns={"COD_PROV": "CPRO"})
    resultado["CPRO"] = resultado["Codigo_INE"].str[:2]
    resultado = resultado.merge(comunidades, on="CPRO", how="left", validate="many_to_one")
    resultado["Municipio_normalizado"] = resultado["Municipio"].map(normalizar_nombre_municipal)
    resultado["Provincia_normalizada"] = resultado["Provincia"].map(normalizar_nombre_municipal)
    resultado["Población"] = resultado["Municipio"]
    resultado["Comunidad"] = resultado["COMUNIDAD_AUTONOMA"]
    resultado["Latitud"] = resultado["LATITUD_ETRS89_REGCAN95"].str.replace(",", ".", regex=False)
    resultado["Longitud"] = resultado["LONGITUD_ETRS89_REGCAN95"].str.replace(",", ".", regex=False)
    resultado["Altitud"] = resultado["ALTITUD"].str.replace(",", ".", regex=False)
    resultado["Habitantes"] = resultado["POBLACION_MUNI"]
    columnas = ["Codigo_INE", "Municipio", "Municipio_normalizado", "Provincia", "Provincia_normalizada",
                "Comunidad", "Población", "Latitud", "Longitud", "Altitud", "Habitantes"]
    return resultado[columnas].sort_values("Codigo_INE").reset_index(drop=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ine", required=True, type=Path)
    parser.add_argument("--cnig-municipios", required=True, type=Path)
    parser.add_argument("--cnig-provincias", required=True, type=Path)
    parser.add_argument("--salida", default="datos/municipios_oficial.csv", type=Path)
    parser.add_argument("--metadata", default="datos/municipios_oficial.metadata.json", type=Path)
    args = parser.parse_args(argv)
    catalogo = generar_catalogo(args.ine, args.cnig_municipios, args.cnig_provincias)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    catalogo.to_csv(args.salida, sep=";", index=False)
    metadata = {
        "fecha_generacion": date.today().isoformat(), "referencia_ine": "2026-01-01", "version_cnig": "NGMEP 2026-03",
        "fuentes": {"ine": URL_INE, "cnig": "https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=9000004"},
        "transformacion": "Cruce por los cinco primeros dígitos de COD_INE (CPRO+CMUN); denominación y provincia INE; coordenadas, altitud y población municipal CNIG.",
        "filas": len(catalogo),
    }
    args.metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

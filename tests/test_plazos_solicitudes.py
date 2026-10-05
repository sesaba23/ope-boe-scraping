from datetime import date

import base_datos
from consultas_boe import buscar_oposiciones
from migrar_esquema_sqlite import migrar_v7_v8_plazos
from plazos_solicitudes import extraer_plazo_presentacion


def test_extrae_plazo_natural_desde_el_dia_siguiente():
    resultado = extraer_plazo_presentacion(
        "El plazo de presentación de solicitudes será de veinte días naturales "
        "a contar desde el siguiente al de la publicación.",
        "2025-05-07",
    )
    assert resultado["Plazo_solicitudes"] == "20 días naturales"
    assert resultado["Fecha_inicio_plazo"] == "2025-05-08"
    assert resultado["Fecha_fin_plazo"] == "2025-05-27"
    assert resultado["Plazo_calculo"] == "CALCULADO_DIAS_NATURALES"


def test_explicita_fecha_limite_y_dias_habiles():
    explicita = extraer_plazo_presentacion(
        "Las solicitudes podrán presentarse hasta el día 30 de mayo de 2025.",
        "2025-05-07",
    )
    assert explicita["Plazo_solicitudes"] == "Fecha límite explícita"
    assert explicita["Fecha_fin_plazo"] == "2025-05-30"
    assert extraer_plazo_presentacion(
        "El plazo vence el día 30 de mayo de 2025.", "2025-05-07"
    )["Fecha_fin_plazo"] == "2025-05-30"
    habiles = extraer_plazo_presentacion(
        "El plazo para presentar solicitudes será de 5 días hábiles desde el día siguiente.",
        "2025-05-09",
    )
    assert habiles["Fecha_inicio_plazo"] == "2025-05-10"
    assert habiles["Fecha_fin_plazo"] == "2025-05-16"
    assert habiles["Plazo_calculo"] == "CALCULADO_DIAS_HABILES_SIN_FESTIVOS"


def test_dias_habiles_puede_excluir_calendario_oficial():
    resultado = extraer_plazo_presentacion(
        "El plazo para presentar solicitudes será de 2 días hábiles desde el día siguiente.",
        "2025-05-09", festivos={"2025-05-12"},
    )
    assert resultado["Fecha_fin_plazo"] == "2025-05-14"
    assert resultado["Plazo_calculo"] == "CALCULADO_DIAS_HABILES_CON_FESTIVOS"


def test_ignora_la_expresion_del_dia_antes_de_la_duracion_real():
    resultado = extraer_plazo_presentacion(
        "El plazo de presentación de instancias es de 20 días naturales a partir del día siguiente al de la publicación.",
        "2004-01-03",
    )
    assert resultado["Fecha_fin_plazo"] == "2004-01-23"


def test_migracion_v7_v8_conserva_filas_y_declara_columnas(tmp_path):
    ruta = tmp_path / "boe.db"
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion)
    conexion.execute("ALTER TABLE oposiciones ADD COLUMN tipo_personal TEXT DEFAULT 'Otros'")
    base_datos.guardar_metadata(conexion, schema_version=7, data_version=3)
    conexion.commit()
    conexion.close()

    resultado = migrar_v7_v8_plazos(ruta, tmp_path / "backups")
    assert resultado["schema_version"] == "8"
    conexion = base_datos.conectar(ruta, readonly=True)
    try:
        assert dict(conexion.execute("SELECT clave,valor FROM metadata"))["schema_version"] == "8"
        assert {fila[1] for fila in conexion.execute("PRAGMA table_info(oposiciones)")} >= {
            "plazo_solicitudes", "fecha_inicio_plazo", "fecha_fin_plazo", "plazo_calculo", "evidencia_plazo"
        }
    finally:
        conexion.close()


def test_filtro_en_plazo_excluye_vencidas_y_sin_dato(tmp_path):
    ruta = tmp_path / "boe.db"
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion)
    conexion.execute("ALTER TABLE oposiciones ADD COLUMN tipo_personal TEXT DEFAULT 'Otros'")
    base_datos.guardar_metadata(conexion, schema_version=8, data_version=1)
    conexion.execute("INSERT INTO metadata(clave,valor) VALUES ('tipo_personal_version','tipo-personal-v2')")
    conexion.execute(
        """INSERT INTO publicaciones(publicacion_id,enlace,fecha_boe,fecha_boe_original,version_extractor,estado_analisis,coincidencias)
           VALUES ('BOE-A-2026-1','https://example.test', '2026-01-01','1 de enero de 2026','1','con_coincidencias',1)"""
    )
    conexion.executemany(
        """INSERT INTO oposiciones(oposicion_id,puesto,escala,subescala,clase,sistema,turno,fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor,plazo_solicitudes,fecha_fin_plazo,tipo_personal)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (1, "Vigente", "--", "--", "--", "--", "--", "2026-01-01", "1", "https://example.test", "BOE-A-2026-1", "1", "10 días naturales", date.today().isoformat(), "Otros"),
            (2, "Vencida", "--", "--", "--", "--", "--", "2026-01-01", "1", "https://example.test", "BOE-A-2026-1", "1", "10 días naturales", "2020-01-01", "Otros"),
            (3, "Sin dato", "--", "--", "--", "--", "--", "2026-01-01", "1", "https://example.test", "BOE-A-2026-1", "1", None, None, "Otros"),
        ],
    )
    conexion.commit()
    conexion.close()
    assert buscar_oposiciones(ruta, plazo="en_plazo")["total"] == 1
    assert buscar_oposiciones(ruta, plazo="todas")["total"] == 3

import json
import os
from pathlib import Path
import sqlite3

import pytest

import base_datos
import sincronizar_sqlite as sync


def _crear_base(ruta, filas=("A",), *, data_version=1, schema_version="2", orden=None):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = base_datos.conectar(ruta)
    base_datos.crear_esquema(conexion)
    base_datos.crear_indices(conexion)
    base_datos.guardar_metadata(conexion, data_version=data_version)
    filas = list(filas)
    orden = orden or filas
    for pid in orden:
        conexion.execute(
            "INSERT INTO publicaciones VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, f"https://x/{pid}", "2026-01-01", "20260101", None, None,
             "1", "con_coincidencias", 1, None, None, None, None, None, None, None),
        )
        conexion.execute(
            """INSERT INTO oposiciones(
                num_plazas,puesto,administracion,escala,subescala,clase,sistema,
                turno,fecha_boe,fecha_boe_original,enlace,publicacion_id,version_extractor
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("la", f"Puesto {pid}", None, "--", "--", "--", "--", "--",
             "2026-01-01", "20260101", f"https://x/{pid}", pid, "1"),
        )
    if schema_version != "2":
        conexion.execute(
            "UPDATE metadata SET valor=? WHERE clave='schema_version'", (schema_version,)
        )
    conexion.commit()
    conexion.close()
    return ruta


def _escribir_procedencia(ruta, padre, ancestros=()):
    sync._ruta_procedencia(ruta).write_text(
        json.dumps({
            "format_version": sync.FORMAT_VERSION,
            "fingerprint_restaurado": padre,
            "ancestros": list(ancestros),
        }),
        encoding="utf-8",
    )


def _snapshot_descendiente(tmp_path):
    base_a = _crear_base(tmp_path / "a.db")
    info_a = sync.inspeccionar(base_a)
    base_b = _crear_base(tmp_path / "b.db", ("A", "B"), data_version=2)
    _escribir_procedencia(base_b, info_a["fingerprint_global"])
    snap_b = sync.snapshot(base_b, tmp_path / "snaps")
    return base_a, Path(snap_b["snapshot"]), info_a


def test_inspeccion_es_read_only_y_no_cambia_archivo(tmp_path):
    ruta = _crear_base(tmp_path / "boe.db")
    antes = (sync.sha256_archivo(ruta), ruta.stat().st_size, ruta.stat().st_mtime_ns)
    info = sync.inspeccionar(ruta)
    despues = (sync.sha256_archivo(ruta), ruta.stat().st_size, ruta.stat().st_mtime_ns)
    assert antes == despues
    assert info["schema_version"] == "2"
    assert info["conteos"]["oposiciones"] == 1
    assert info["integrity_check"] == ["ok"]
    assert info["foreign_key_check"] == []


def test_fingerprint_ignora_orden_insercion_y_layout_fisico(tmp_path):
    primera = _crear_base(tmp_path / "uno.db", ("A", "B"), orden=("A", "B"))
    segunda = _crear_base(tmp_path / "dos.db", ("A", "B"), orden=("B", "A"))
    con = sqlite3.connect(segunda)
    con.execute("VACUUM")
    con.close()
    a, b = sync.inspeccionar(primera), sync.inspeccionar(segunda)
    assert a["sha256_fisico"] != b["sha256_fisico"]
    assert a["fingerprint_global"] == b["fingerprint_global"]
    assert sync.comparar(primera, segunda)["clasificacion"] == "IDENTICA"


def test_snapshot_manifiesto_y_wal_no_alteran_origen(tmp_path):
    ruta = _crear_base(tmp_path / "boe.db")
    conexion = sqlite3.connect(ruta)
    conexion.execute("PRAGMA journal_mode=WAL")
    conexion.execute("INSERT INTO busquedas(codigo) VALUES ('confirmado')")
    conexion.commit()
    antes = sync.inspeccionar(ruta)
    resultado = sync.snapshot(ruta, tmp_path / "snapshots")
    despues = sync.inspeccionar(ruta)
    manifiesto, copia = sync.verificar_manifiesto(resultado["snapshot"])
    conexion.close()
    assert antes == despues
    assert copia["fingerprint_global"] == antes["fingerprint_global"]
    assert manifiesto["manifest_sha256"]
    assert manifiesto["data_version"] == "1"


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("sha256_fisico", "0" * 64),
        ("fingerprint_global", "1" * 64),
        ("conteos", {}),
        ("created_at", "alterado"),
    ],
)
def test_rechaza_manifiesto_alterado(tmp_path, campo, valor):
    ruta = _crear_base(tmp_path / "boe.db")
    resultado = sync.snapshot(ruta, tmp_path / "snapshots")
    manifiesto = Path(resultado["manifiesto"])
    datos = json.loads(manifiesto.read_text())
    datos[campo] = valor
    manifiesto.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(sync.ErrorSincronizacion):
        sync.verificar_manifiesto(resultado["snapshot"])


def test_rechaza_snapshot_modificado_y_base_corrupta(tmp_path):
    ruta = _crear_base(tmp_path / "boe.db")
    resultado = sync.snapshot(ruta, tmp_path / "snapshots")
    con = sqlite3.connect(resultado["snapshot"])
    con.execute("INSERT INTO busquedas(codigo) VALUES ('alterado')")
    con.commit(); con.close()
    with pytest.raises(sync.ErrorSincronizacion):
        sync.verificar_manifiesto(resultado["snapshot"])
    corrupta = tmp_path / "corrupta.db"
    corrupta.write_bytes(b"no sqlite")
    assert sync.comparar(ruta, corrupta)["clasificacion"] == "INVALIDA"


def test_rechaza_manifiesto_recalculado_que_miente_sobre_contenido(tmp_path):
    ruta = _crear_base(tmp_path / "boe.db")
    resultado = sync.snapshot(ruta, tmp_path / "snapshots")
    manifiesto = Path(resultado["manifiesto"])
    datos = json.loads(manifiesto.read_text())
    datos["conteos"]["oposiciones"] = 999
    datos["fingerprints"]["oposiciones"] = "f" * 64
    datos["fingerprint_global"] = "e" * 64
    datos["manifest_sha256"] = sync._firma_manifiesto(datos)
    manifiesto.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(sync.ErrorSincronizacion, match="no corresponde"):
        sync.verificar_manifiesto(resultado["snapshot"])


def test_incompatible_y_divergencia_no_se_deciden_por_data_version(tmp_path):
    local = _crear_base(tmp_path / "local.db", ("A",), data_version=1)
    incompatible = _crear_base(tmp_path / "incompatible.db", ("A",), schema_version="3")
    rama_1 = _crear_base(tmp_path / "rama1.db", ("A", "B"), data_version=2)
    rama_2 = _crear_base(tmp_path / "rama2.db", ("A", "C"), data_version=2)
    supuesta_nueva = _crear_base(tmp_path / "nueva.db", ("A", "D"), data_version=9)
    assert sync.comparar(local, incompatible)["clasificacion"] == "INCOMPATIBLE"
    assert sync.comparar(rama_1, rama_2)["clasificacion"] == "DIVERGENTE"
    assert sync.comparar(local, supuesta_nueva)["clasificacion"] == "DIVERGENTE"


def test_cadena_lineal_a_b_c(tmp_path):
    base_a = _crear_base(tmp_path / "a.db")
    info_a = sync.inspeccionar(base_a)
    base_b = _crear_base(tmp_path / "b.db", ("A", "B"), data_version=2)
    _escribir_procedencia(base_b, info_a["fingerprint_global"])
    snap_b = Path(sync.snapshot(base_b, tmp_path / "snaps_b")["snapshot"])
    info_b = sync.inspeccionar(snap_b)
    base_c = _crear_base(tmp_path / "c.db", ("A", "B", "C"), data_version=3)
    _escribir_procedencia(
        base_c, info_b["fingerprint_global"], [info_a["fingerprint_global"]]
    )
    snap_c = Path(sync.snapshot(base_c, tmp_path / "snaps_c")["snapshot"])
    assert sync.comparar(base_a, snap_b)["clasificacion"] == "REMOTA_MAS_RECIENTE"
    assert sync.comparar(snap_b, base_a)["clasificacion"] == "LOCAL_MAS_RECIENTE"
    assert sync.comparar(base_a, snap_c)["clasificacion"] == "REMOTA_MAS_RECIENTE"
    assert sync.comparar(snap_b, snap_c)["clasificacion"] == "REMOTA_MAS_RECIENTE"


def test_restauracion_crea_backup_y_reemplaza_atomicamente(tmp_path):
    local, remoto, _ = _snapshot_descendiente(tmp_path)
    resultado = sync.restaurar(remoto, local, tmp_path / "backups")
    assert resultado["clasificacion"] == "REMOTA_MAS_RECIENTE"
    assert Path(resultado["backup"]["snapshot"]).exists()
    assert sync.inspeccionar(local)["fingerprint_global"] == sync.inspeccionar(remoto)["fingerprint_global"]
    assert not Path(str(local) + "-wal").exists()
    assert not Path(str(local) + "-shm").exists()


def test_restauracion_aborta_sin_manifiesto_divergente_o_con_wal(tmp_path):
    local, remoto, _ = _snapshot_descendiente(tmp_path)
    manifiesto = remoto.with_suffix(".json")
    temporal_manifiesto = manifiesto.with_suffix(".guardado")
    manifiesto.rename(temporal_manifiesto)
    with pytest.raises(sync.ErrorSincronizacion, match="manifiesto"):
        sync.restaurar(remoto, local, tmp_path / "backups")
    temporal_manifiesto.rename(manifiesto)
    Path(str(local) + "-wal").touch()
    with pytest.raises(sync.ErrorSincronizacion, match="WAL/SHM"):
        sync.restaurar(remoto, local, tmp_path / "backups")


def test_fallo_antes_de_replace_conserva_base_local(tmp_path, monkeypatch):
    local, remoto, _ = _snapshot_descendiente(tmp_path)
    antes = sync.sha256_archivo(local)
    monkeypatch.setattr(sync.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("fallo")))
    with pytest.raises(OSError, match="fallo"):
        sync.restaurar(remoto, local, tmp_path / "backups")
    assert sync.sha256_archivo(local) == antes

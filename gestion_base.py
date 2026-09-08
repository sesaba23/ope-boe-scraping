"""Distribución segura de la copia SQLite oficial de BuscadorBOE."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import re
import ssl
from threading import Lock, Thread
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import base_datos
import certifi

RELEASE_TAG = "database-latest"
ASSET_DATABASE = "boe.db"
ASSET_MANIFEST = "manifest.json"
FORMAT_VERSION = 1
SCHEMA_REQUERIDO = 6
_LOCK_OPERACION_BASE = Lock()


def _abrir_https(url: str):
    """HTTPS público con CA versionada; nunca desactiva la verificación TLS."""
    contexto = ssl.create_default_context(cafile=certifi.where())
    solicitud = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "BuscadorBOE"})
    return urlopen(solicitud, context=contexto, timeout=30)


class GestionBaseError(RuntimeError):
    pass


class ReleaseNoEncontrada(GestionBaseError):
    """La Release estable todavía no existe; no es un error de la base."""

class PublicacionIncompleta(GestionBaseError):
    """Existe la Release, pero todavía no acredita una copia utilizable."""

class TrabajoPublicacion:
    def __init__(self, ruta, repo):
        self.ruta, self.repo = ruta, repo
        self.estado, self.fase, self.error = "pendiente", "Preparando la publicación...", None
        self.inicio = time.monotonic()
        self.finalizado = None

    def serializar(self):
        fin = self.finalizado if self.finalizado is not None else time.monotonic()
        return {"estado": self.estado, "fase": self.fase, "error": self.error,
                "transcurrido_segundos": round(fin - self.inicio),
                "terminal": self.estado in {"completado", "error", "cancelado"}}

class GestorPublicacion:
    def __init__(self): self._lock, self._trabajo = Lock(), None
    def iniciar(self, ruta, repo):
        with self._lock:
            if self._trabajo and self._trabajo.estado in {"pendiente","procesando"}: return self._trabajo, False
            if not _LOCK_OPERACION_BASE.acquire(blocking=False):
                raise GestionBaseError("Ya hay una operación sobre la base de datos en curso.")
            t=TrabajoPublicacion(ruta,repo); self._trabajo=t; Thread(target=self._ejecutar,args=(t,),daemon=True).start(); return t, True
    def obtener(self):
        with self._lock: return self._trabajo.serializar() if self._trabajo else None
    def _ejecutar(self,t):
        def progreso(fase):
            t.fase = fase
        try:
            t.estado = "procesando"
            publicar_base(t.ruta, t.repo, progreso=progreso)
            t.fase, t.estado = "Publicación completada.", "completado"
        except GestionBaseError as error:
            t.estado, t.error = "error", str(error)
        except Exception:
            t.estado, t.error = "error", "No se pudo completar la publicación."
        finally:
            t.finalizado = time.monotonic()
            _LOCK_OPERACION_BASE.release()


class GestorActualizacionBase:
    def __init__(self): self._lock, self._trabajo = Lock(), None
    def iniciar(self, ruta, repo):
        with self._lock:
            if self._trabajo and self._trabajo.estado in {"pendiente", "procesando"}: return self._trabajo, False
            if not _LOCK_OPERACION_BASE.acquire(blocking=False):
                raise GestionBaseError("Ya hay una operación sobre la base de datos en curso.")
            t = TrabajoPublicacion(ruta, repo); t.fase = "Preparando la actualización..."; self._trabajo = t
            Thread(target=self._ejecutar, args=(t,), daemon=True).start(); return t, True
    def obtener(self):
        with self._lock: return self._trabajo.serializar() if self._trabajo else None
    def _ejecutar(self, t):
        try:
            t.estado = "procesando"
            actualizar_base_desde_github(t.ruta, t.repo, progreso=lambda fase, *_: setattr(t, "fase", fase))
            t.fase, t.estado = "Actualización completada.", "completado"
        except GestionBaseError as error:
            t.estado, t.error = "error", str(error)
        except Exception:
            t.estado, t.error = "error", "No se pudo actualizar la base de datos."
        finally:
            t.finalizado = time.monotonic(); _LOCK_OPERACION_BASE.release()


def _sha256(ruta: Path) -> str:
    return base_datos.hash_archivo(ruta)


def _metadata(ruta: Path) -> dict:
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        return dict(con.execute("SELECT clave, valor FROM metadata"))
    finally:
        con.close()


def verificar_integridad(ruta: str | Path) -> dict:
    ruta = Path(ruta)
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        metadata = dict(con.execute("SELECT clave, valor FROM metadata"))
    finally:
        con.close()
    if integrity != "ok" or fk:
        raise GestionBaseError("La base SQLite no supera la comprobación de integridad")
    return {"schema_version": int(metadata["schema_version"]), "data_version": int(metadata["data_version"]), "integrity": integrity, "foreign_keys": fk}


def estado_local(ruta: str | Path) -> dict:
    """Resumen de lectura rápida para la pantalla administrativa.

    La comprobación exhaustiva queda reservada para la acción explícita del
    usuario y para los flujos de descarga, migración y publicación.
    """
    ruta = Path(ruta)
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        metadata = dict(con.execute("SELECT clave, valor FROM metadata"))
        publicaciones = con.execute("SELECT COUNT(*) FROM publicaciones").fetchone()[0]
        oposiciones = con.execute("SELECT COUNT(*) FROM oposiciones").fetchone()[0]
    finally:
        con.close()
    return {"ruta": str(ruta), "tamano": ruta.stat().st_size,
            "schema_version": int(metadata["schema_version"]),
            "data_version": int(metadata["data_version"]),
            "publicaciones": publicaciones, "oposiciones": oposiciones}


def crear_manifest(ruta: str | Path, *, publicado_en: datetime | None = None) -> dict:
    ruta = Path(ruta)
    estado = verificar_integridad(ruta)
    if estado["schema_version"] != SCHEMA_REQUERIDO:
        raise GestionBaseError(f"Schema incompatible: {estado['schema_version']} (requerido {SCHEMA_REQUERIDO})")
    return {"format_version": FORMAT_VERSION, "database": ASSET_DATABASE,
            "schema_version": estado["schema_version"], "data_version": estado["data_version"],
            "sha256": _sha256(ruta), "size_bytes": ruta.stat().st_size,
            "published_at": (publicado_en or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")}


def validar_manifest(datos: dict) -> dict:
    obligatorios = {"format_version", "database", "schema_version", "data_version", "sha256", "size_bytes", "published_at"}
    if not isinstance(datos, dict) or not obligatorios <= datos.keys() or datos.get("format_version") != FORMAT_VERSION or datos.get("database") != ASSET_DATABASE:
        raise GestionBaseError("Manifest de base de datos inválido")
    if (not isinstance(datos["schema_version"], int) or datos["schema_version"] < 1
            or not isinstance(datos["data_version"], int) or datos["data_version"] < 0
            or not isinstance(datos["size_bytes"], int) or datos["size_bytes"] < 1
            or not isinstance(datos["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", datos["sha256"])):
        raise GestionBaseError("Manifest de base de datos incompleto")
    datetime.fromisoformat(str(datos["published_at"]).replace("Z", "+00:00"))
    return datos


def _url_release(repo: str, asset: str) -> str:
    return f"https://github.com/{repo}/releases/download/{RELEASE_TAG}/{asset}"


def _url_api_release(repo: str) -> str:
    return f"https://api.github.com/repos/{repo}/releases/tags/{RELEASE_TAG}"


def url_asset_publicado(repo: str, asset: str, *, opener=_abrir_https) -> str:
    """Obtiene la URL canónica del asset sin requerir GitHub CLI."""
    try:
        with opener(_url_api_release(repo)) as respuesta:
            release = json.loads(respuesta.read().decode("utf-8"))
        if not isinstance(release, dict) or "assets" not in release:
            return _url_release(repo, asset)  # Compatibilidad con openers simples de tests.
        for item in release["assets"]:
            if item.get("name") == asset and item.get("browser_download_url"):
                return item["browser_download_url"]
        raise PublicacionIncompleta("Existe una publicación en GitHub, pero todavía no contiene una copia completa de la base de datos.")
    except HTTPError as error:
        if error.code == 404:
            raise ReleaseNoEncontrada("Todavía no existe ninguna copia publicada de la base de datos.") from error
        raise GestionBaseError("No se pudo consultar la copia publicada.") from error
    except (URLError, json.JSONDecodeError, UnicodeDecodeError, TypeError):
        # Los assets públicos conservan una URL estable; permite la descarga sin gh.
        return _url_release(repo, asset)


def _resultado_gh(runner, argumentos: list[str]):
    """Ejecuta gh sin exponer stderr de forma indiscriminada a la interfaz."""
    try:
        return runner(["gh", *argumentos], capture_output=True, text=True)
    except FileNotFoundError as error:
        raise GestionBaseError("No se encontró GitHub CLI (gh) en este equipo.") from error


def _mensaje_error_gh(resultado: object, accion: str) -> str:
    detalle = f"{getattr(resultado, 'stderr', '')}\n{getattr(resultado, 'stdout', '')}".lower()
    if "not logged" in detalle or "authenticate" in detalle or "auth login" in detalle:
        return "GitHub CLI no está autenticado."
    if "permission" in detalle or "forbidden" in detalle or "resource not accessible" in detalle:
        return "GitHub no permite publicar en este repositorio."
    if "network" in detalle or "connection" in detalle or "timeout" in detalle:
        return "No se pudo conectar con GitHub."
    return accion


def _release_no_encontrada(resultado: object) -> bool:
    """Sólo interpreta como ausencia el error específico de `gh release view`."""
    detalle = f"{getattr(resultado, 'stderr', '')}\n{getattr(resultado, 'stdout', '')}".lower()
    return getattr(resultado, "returncode", 0) != 0 and ("release not found" in detalle or "not found" in detalle)


def comprobar_gh(*, runner=subprocess.run) -> None:
    version = _resultado_gh(runner, ["--version"])
    if getattr(version, "returncode", 0):
        raise GestionBaseError("No se pudo ejecutar GitHub CLI (gh).")
    autenticacion = _resultado_gh(runner, ["auth", "status", "--hostname", "github.com"])
    if getattr(autenticacion, "returncode", 0):
        raise GestionBaseError(_mensaje_error_gh(autenticacion, "GitHub CLI no está autenticado."))


def consultar_release(repo: str, *, runner=subprocess.run) -> dict | None:
    resultado = _resultado_gh(runner, ["release", "view", RELEASE_TAG, "--repo", repo, "--json", "assets"])
    if getattr(resultado, "returncode", 0) == 0:
        try:
            return json.loads(resultado.stdout)
        except json.JSONDecodeError as error:
            raise GestionBaseError("GitHub devolvió una respuesta de Release no válida.") from error
    if _release_no_encontrada(resultado):
        return None
    raise GestionBaseError(_mensaje_error_gh(resultado, "No se pudo consultar la publicación en GitHub."))


def _crear_release(repo: str, *, runner=subprocess.run) -> None:
    resultado = _resultado_gh(runner, ["release", "create", RELEASE_TAG,
                                       "--repo", repo,
                                       "--title", "Base de datos oficial BuscadorBOE",
                                       "--notes", "Copia oficial actual de la base de datos de BuscadorBOE."])
    if getattr(resultado, "returncode", 0):
        raise GestionBaseError(_mensaje_error_gh(resultado, "No se pudo crear la publicación en GitHub."))


def _subir_asset(repo: str, asset: Path, *, runner=subprocess.run, mensaje: str) -> None:
    resultado = _resultado_gh(runner, ["release", "upload", RELEASE_TAG, str(asset), "--clobber", "--repo", repo])
    if getattr(resultado, "returncode", 0):
        raise GestionBaseError(_mensaje_error_gh(resultado, mensaje))


def _verificar_asset_publicado(repo: str, nombre: str, tamano: int, *, runner=subprocess.run) -> None:
    release = consultar_release(repo, runner=runner)
    if release is None:
        raise GestionBaseError("No se pudo verificar la publicación en GitHub.")
    assets = release.get("assets", [])
    if not any(asset.get("name") == nombre and asset.get("size") == tamano for asset in assets):
        raise GestionBaseError("No se pudo verificar la base publicada.")


def descargar_manifest_publicado(repo: str, *, runner=subprocess.run) -> dict:
    """Lee sólo el manifest mediante gh, sin descargar la base SQLite."""
    release = consultar_release(repo, runner=runner)
    if release is None:
        raise ReleaseNoEncontrada("Todavía no existe ninguna copia publicada de la base de datos.")
    if not any(asset.get("name") == ASSET_MANIFEST for asset in release.get("assets", [])):
        raise PublicacionIncompleta("Existe una publicación en GitHub, pero todavía no contiene una copia completa de la base de datos.")
    with tempfile.TemporaryDirectory() as directorio:
        resultado = _resultado_gh(runner, ["release", "download", RELEASE_TAG,
                                           "--repo", repo, "--pattern", ASSET_MANIFEST,
                                           "--dir", directorio])
        if getattr(resultado, "returncode", 0):
            raise GestionBaseError(_mensaje_error_gh(resultado, "No se pudo descargar la información de la copia publicada."))
        ruta_manifest = Path(directorio) / ASSET_MANIFEST
        try:
            return validar_manifest(json.loads(ruta_manifest.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, GestionBaseError) as error:
            raise GestionBaseError("La información de la copia publicada no es válida.") from error


def consultar_copia_publicada(repo: str, *, runner=subprocess.run) -> dict:
    """Estado estructurado para la interfaz; nunca inicia una sincronización."""
    try:
        return {"estado": "publicada", "manifest": descargar_manifest_publicado(repo, runner=runner)}
    except ReleaseNoEncontrada:
        return {"estado": "no_publicada", "mensaje": "Todavía no existe ninguna copia publicada de la base de datos."}
    except PublicacionIncompleta:
        return {"estado": "publicacion_incompleta", "mensaje": "Existe una publicación en GitHub, pero todavía no contiene una copia completa de la base de datos."}

def repositorio_configurado(*, runner=subprocess.run) -> str:
    remotos = runner(["git", "remote"], capture_output=True, text=True)
    nombres = [nombre.strip() for nombre in getattr(remotos, "stdout", "").splitlines() if nombre.strip()]
    ordenados = (["origin"] if "origin" in nombres else []) + sorted(nombre for nombre in nombres if nombre != "origin")
    for nombre in ordenados:
        resultado = runner(["git", "remote", "get-url", nombre], capture_output=True, text=True)
        texto = getattr(resultado, "stdout", "").strip()
        coincidencia = re.search(r"github\.com[:/]([^/]+/[^/.]+)(?:\.git)?$", texto)
        if coincidencia:
            return coincidencia.group(1)
    raise GestionBaseError("No se pudo determinar un repositorio GitHub configurado")

def asegurar_base_local(ruta: str | Path, *, repo: str | None = None, opener=_abrir_https) -> dict:
    ruta = Path(ruta)
    existente = ruta.exists()
    if not existente:
        instalar_descarga_inicial(ruta, repo or repositorio_configurado(), opener=opener)
    try:
        return migrar_si_necesario(ruta)
    except GestionBaseError as error:
        if existente and "No hay migración explícita" in str(error):
            return {"requiere_actualizacion": True, **verificar_integridad(ruta)}
        raise


def leer_manifest_remoto(repo: str, *, opener=_abrir_https) -> dict:
    try:
        with opener(url_asset_publicado(repo, ASSET_MANIFEST, opener=opener)) as respuesta:
            return validar_manifest(json.loads(respuesta.read().decode("utf-8")))
    except HTTPError as error:
        if error.code == 404:
            raise ReleaseNoEncontrada("Todavía no existe ninguna copia publicada de la base de datos.") from error
        raise GestionBaseError("No se pudo consultar la copia publicada.") from error
    except (URLError, json.JSONDecodeError) as error:
        raise GestionBaseError("No se pudo consultar la copia publicada.") from error

def comparar_manifest_local(ruta: str | Path, remoto: dict) -> dict:
    local = crear_manifest(ruta)
    remoto = validar_manifest(remoto)
    if local["sha256"] == remoto["sha256"]:
        mensaje = "La base local y la copia publicada son idénticas."
    elif local["data_version"] > remoto["data_version"]:
        mensaje = "La base local contiene cambios posteriores a la copia publicada."
    elif local["data_version"] < remoto["data_version"]:
        mensaje = "La copia publicada contiene una versión de datos posterior a la base local."
    else:
        mensaje = "La base local y la copia publicada tienen la misma versión de datos, pero no son idénticas."
    return {"local": local, "publicada": remoto, "mensaje": mensaje}


def instalar_descarga_inicial(ruta: str | Path, repo: str, *, opener=_abrir_https, progreso=None) -> dict:
    """Descarga, valida e instala de forma atómica sólo si no existe la base."""
    destino = Path(ruta)
    if destino.exists():
        return {"instalada": False, "motivo": "base_existente"}
    manifest = leer_manifest_remoto(repo, opener=opener)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".download")
    try:
        if progreso: progreso("Descargando base de datos de BuscadorBOE...", 0, manifest["size_bytes"])
        with opener(_url_release(repo, ASSET_DATABASE)) as origen, temporal.open("wb") as salida:
            total = 0
            while bloque := origen.read(1024 * 1024):
                salida.write(bloque); total += len(bloque)
                if progreso: progreso("Descargando base de datos de BuscadorBOE...", total, manifest["size_bytes"])
        if temporal.stat().st_size != manifest["size_bytes"] or _sha256(temporal) != manifest["sha256"]:
            raise GestionBaseError("La descarga no coincide con el manifest publicado")
        verificar_integridad(temporal)
        metadata = _metadata(temporal)
        if (metadata.get("schema_version") != str(manifest["schema_version"])
                or metadata.get("data_version") != str(manifest["data_version"])):
            raise GestionBaseError("La versión de la base descargada no coincide con el manifest")
        temporal.replace(destino)
        return {"instalada": True, "manifest": manifest}
    except Exception:
        temporal.unlink(missing_ok=True)
        raise


def preparar_actualizacion_github(ruta: str | Path, repo: str, *, opener=_abrir_https) -> dict:
    """Consulta el manifest por HTTPS; no descarga ni modifica la base."""
    publicado = leer_manifest_remoto(repo, opener=opener)
    return {"estado": "preparada", **comparar_manifest_local(ruta, publicado)}


def actualizar_base_desde_github(ruta: str | Path, repo: str, *, opener=_abrir_https,
                                 progreso=None, directorio_backup="backups/sqlite") -> dict:
    """Instala manualmente una copia publicada, con validación y rollback."""
    destino = Path(ruta); manifest = leer_manifest_remoto(repo, opener=opener)
    temporal = destino.with_suffix(destino.suffix + ".github.download")
    backup = None; reemplazada = False
    try:
        if progreso: progreso("Descargando la base de datos...", 0, manifest["size_bytes"])
        with opener(url_asset_publicado(repo, ASSET_DATABASE, opener=opener)) as origen, temporal.open("wb") as salida:
            recibido = 0
            while bloque := origen.read(1024 * 1024):
                salida.write(bloque); recibido += len(bloque)
                if progreso: progreso("Descargando la base de datos...", recibido, manifest["size_bytes"])
        if temporal.stat().st_size != manifest["size_bytes"] or _sha256(temporal) != manifest["sha256"]:
            raise GestionBaseError("La descarga no coincide con la copia publicada.")
        if progreso: progreso("Comprobando la descarga...")
        estado = verificar_integridad(temporal)
        if manifest["schema_version"] > SCHEMA_REQUERIDO:
            raise GestionBaseError("La copia publicada utiliza una estructura de base de datos que esta versión de BuscadorBOE no puede utilizar.")
        if estado["schema_version"] != manifest["schema_version"] or estado["data_version"] != manifest["data_version"]:
            raise GestionBaseError("La versión descargada no coincide con la información publicada.")
        if estado["schema_version"] < SCHEMA_REQUERIDO:
            if progreso: progreso("Preparando la base de datos...")
            migrar_si_necesario(temporal)
            verificar_integridad(temporal)
        if progreso: progreso("Guardando copia de seguridad...")
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path(directorio_backup); backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"boe_pre_actualizacion_github_{marca}.db"
        origen = sqlite3.connect(f"file:{destino}?mode=ro", uri=True); copia = sqlite3.connect(backup)
        try: origen.backup(copia)
        finally: copia.close(); origen.close()
        verificar_integridad(backup)
        if progreso: progreso("Instalando la nueva base...")
        temporal.replace(destino); reemplazada = True
        if progreso: progreso("Verificando la nueva base...")
        final = verificar_integridad(destino)
        return {"actualizada": True, "backup": str(backup), **final}
    except Exception as error:
        if reemplazada and backup:
            shutil.copy2(backup, destino)
            verificar_integridad(destino)
            raise GestionBaseError("La actualización no pudo completarse. Se ha restaurado la base de datos anterior.") from error
        if isinstance(error, GestionBaseError): raise
        raise GestionBaseError("No se pudo actualizar la base de datos.") from error
    finally:
        temporal.unlink(missing_ok=True)


def migrar_si_necesario(ruta: str | Path) -> dict:
    estado = verificar_integridad(ruta)
    actual = estado["schema_version"]
    if actual == SCHEMA_REQUERIDO:
        return {"migrada": False, **estado}
    import migrar_esquema_sqlite
    funciones = {5: migrar_esquema_sqlite.migrar_v5_v6_municipios_historicos}
    if actual not in funciones:
        raise GestionBaseError(f"No hay migración explícita desde schema_version {actual} hasta {SCHEMA_REQUERIDO}")
    copia = base_datos.crear_backup(ruta)
    try:
        funciones[actual](ruta)
        final = verificar_integridad(ruta)
        if final["schema_version"] != SCHEMA_REQUERIDO: raise GestionBaseError("La migración no alcanzó el schema requerido")
        return {"migrada": True, "backup": str(copia), **final}
    except Exception:
        shutil.copy2(copia, ruta)
        verificar_integridad(ruta)
        raise


def publicar_base(ruta: str | Path, repo: str, *, runner=subprocess.run,
                  verificar_remoto=None, progreso=None) -> dict:
    """Publica la base y deja el manifest como último indicador de éxito."""
    ruta = Path(ruta)
    comprobar_gh(runner=runner)
    if progreso: progreso("Comprobando la base de datos...")
    manifest = crear_manifest(ruta)
    if progreso: progreso("Preparando la publicación...")
    if consultar_release(repo, runner=runner) is None:
        if progreso: progreso("Creando la primera publicación en GitHub...")
        _crear_release(repo, runner=runner)
    with tempfile.TemporaryDirectory() as directorio:
        manifiesto = Path(directorio) / ASSET_MANIFEST
        manifiesto.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if progreso: progreso("Subiendo la base de datos...")
        _subir_asset(repo, ruta, runner=runner, mensaje="No se pudo subir la base de datos.")
        if progreso: progreso("Verificando la base publicada...")
        _verificar_asset_publicado(repo, ASSET_DATABASE, ruta.stat().st_size, runner=runner)
        if progreso: progreso("Publicando información de la copia...")
        _subir_asset(repo, manifiesto, runner=runner,
                      mensaje="La base se subió, pero no pudo completarse la publicación del archivo de información.")
    if progreso: progreso("Verificando publicación...")
    remoto = (verificar_remoto or (lambda nombre: descargar_manifest_publicado(nombre, runner=runner)))(repo)
    try:
        remoto = validar_manifest(remoto)
    except (GestionBaseError, ValueError) as error:
        raise GestionBaseError("No se pudo verificar la publicación.") from error
    if remoto["sha256"] != manifest["sha256"]:
        raise GestionBaseError("La copia publicada no coincide con la base verificada")
    return manifest

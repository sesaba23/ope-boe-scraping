import io, json, sqlite3, time
from pathlib import Path
import pytest
import base_datos, gestion_base


class Resultado:
 def __init__(s, returncode=0, stdout='', stderr=''): s.returncode, s.stdout, s.stderr = returncode, stdout, stderr


class GhSimulado:
 def __init__(s, existe=False, fallo=None, manifest=None): s.existe, s.fallo, s.manifest, s.llamadas, s.assets = existe, fallo, manifest, [], []
 def __call__(s, args, **kw):
  s.llamadas.append(args[1:])
  comando=args[1:]
  if comando == ['--version']: return Resultado(stdout='gh version')
  if comando[:3] == ['auth','status','--hostname']: return Resultado()
  if comando[:3] == ['release','view',gestion_base.RELEASE_TAG]:
   if not s.existe: return Resultado(1, stderr='release not found')
   return Resultado(stdout=json.dumps({'assets':[{'name':n,'size':z} for n,z in s.assets]}))
  if comando[:3] == ['release','create',gestion_base.RELEASE_TAG]: s.existe=True; return Resultado()
  if comando[:3] == ['release','upload',gestion_base.RELEASE_TAG]:
   nombre=Path(comando[3]).name
   if s.fallo == nombre: return Resultado(1, stderr='fallo')
   s.assets=[x for x in s.assets if x[0] != nombre] + [(nombre, Path(comando[3]).stat().st_size)]
   return Resultado()
  if comando[:3] == ['release','download',gestion_base.RELEASE_TAG]:
   if s.fallo == 'download': return Resultado(1, stderr='network failure')
   Path(comando[comando.index('--dir') + 1], 'manifest.json').write_text(json.dumps(s.manifest), encoding='utf-8')
   return Resultado()
  raise AssertionError(comando)

def db(tmp_path):
 tmp_path.mkdir(parents=True, exist_ok=True); p=tmp_path/'boe.db'; c=base_datos.conectar(p); base_datos.crear_esquema(c); base_datos.guardar_metadata(c,schema_version=6,data_version=1); c.commit(); c.close(); return p

def test_manifest_y_validacion(tmp_path):
 p=db(tmp_path); m=gestion_base.crear_manifest(p); assert gestion_base.validar_manifest(m)['sha256']==base_datos.hash_archivo(p)
 with pytest.raises(gestion_base.GestionBaseError): gestion_base.validar_manifest({})

def test_instalacion_atomica(tmp_path):
 origen=db(tmp_path); m=gestion_base.crear_manifest(origen); datos=origen.read_bytes()
 class Res(io.BytesIO):
  def __enter__(s): return s
  def __exit__(s,*a): return False
 def abrir(url): return Res(json.dumps(m).encode() if url.endswith('manifest.json') else datos)
 destino=tmp_path/'nueva.db'; r=gestion_base.instalar_descarga_inicial(destino,'x/y',opener=abrir); assert r['instalada'] and destino.read_bytes()==datos

def test_descarga_invalida_no_instala(tmp_path):
 p=db(tmp_path); m=gestion_base.crear_manifest(p); m['sha256']='0'*64
 class Res(io.BytesIO):
  def __enter__(s): return s
  def __exit__(s,*a): return False
 def abrir(url): return Res(json.dumps(m).encode() if url.endswith('manifest.json') else p.read_bytes())
 with pytest.raises(gestion_base.GestionBaseError): gestion_base.instalar_descarga_inicial(tmp_path/'destino.db','x/y',opener=abrir)
 assert not (tmp_path/'destino.db').exists()

def test_publicacion_sube_base_antes_manifest(tmp_path):
 p=db(tmp_path); gh=GhSimulado(existe=True); manifest=gestion_base.crear_manifest(p)
 gestion_base.publicar_base(p,'x/y',runner=gh,verificar_remoto=lambda repo: manifest)
 subidas=[c[3] for c in gh.llamadas if c[:3] == ['release','upload',gestion_base.RELEASE_TAG]]
 assert [Path(x).name for x in subidas] == ['boe.db','manifest.json']

def test_primera_publicacion_crea_release_y_publica_en_orden(tmp_path):
 p=db(tmp_path); gh=GhSimulado(); manifest=gestion_base.crear_manifest(p); fases=[]
 gestion_base.publicar_base(p,'org/proyecto',runner=gh,verificar_remoto=lambda _:manifest,progreso=fases.append)
 assert any(c[:3] == ['release','create',gestion_base.RELEASE_TAG] for c in gh.llamadas)
 assert fases == ["Comprobando la base de datos...", "Preparando la publicación...", "Creando la primera publicación en GitHub...", "Subiendo la base de datos...", "Verificando la base publicada...", "Publicando información de la copia...", "Verificando publicación..."]

def test_release_existente_no_se_crea_de_nuevo(tmp_path):
 p=db(tmp_path); gh=GhSimulado(existe=True); manifest=gestion_base.crear_manifest(p)
 gestion_base.publicar_base(p,'x/y',runner=gh,verificar_remoto=lambda _:manifest)
 assert not any(c[:3] == ['release','create',gestion_base.RELEASE_TAG] for c in gh.llamadas)

def test_base_existente_no_descarga(tmp_path):
 p=db(tmp_path)
 assert gestion_base.instalar_descarga_inicial(p,'x/y')['motivo']=='base_existente'

@pytest.mark.parametrize("cambio", [
 lambda m: m.pop("published_at"), lambda m: m.update(size_bytes=0),
 lambda m: m.update(sha256="x"), lambda m: m.update(schema_version="seis"),
])
def test_manifest_incompleto_o_invalido(tmp_path, cambio):
 m=gestion_base.crear_manifest(db(tmp_path)); cambio(m)
 with pytest.raises((gestion_base.GestionBaseError, ValueError)): gestion_base.validar_manifest(m)

def test_descarga_interrumpida_limpia_temporal(tmp_path):
 p=db(tmp_path); m=gestion_base.crear_manifest(p)
 class R(io.BytesIO):
  def __enter__(s): return s
  def __exit__(s,*a): return False
 class Rota:
  def __enter__(s): return s
  def __exit__(s,*a): return False
  def read(s,n): raise OSError("corte")
 def abrir(url): return R(json.dumps(m).encode()) if url.endswith("manifest.json") else Rota()
 destino=tmp_path/'rota.db'
 with pytest.raises(OSError): gestion_base.instalar_descarga_inicial(destino,'x/y',opener=abrir)
 assert not destino.exists() and not destino.with_suffix('.db.download').exists()

def test_descarga_corrupta_no_instala(tmp_path):
 p=db(tmp_path); m=gestion_base.crear_manifest(p); corrupta=b"no es sqlite"; m.update(size_bytes=len(corrupta), sha256=__import__('hashlib').sha256(corrupta).hexdigest())
 class R(io.BytesIO):
  def __enter__(s): return s
  def __exit__(s,*a): return False
 def abrir(url): return R(json.dumps(m).encode() if url.endswith("manifest.json") else corrupta)
 destino=tmp_path/'corrupta.db'
 with pytest.raises(sqlite3.DatabaseError): gestion_base.instalar_descarga_inicial(destino,'x/y',opener=abrir)
 assert not destino.exists()

def test_publicacion_fallo_base_no_publica_manifest(tmp_path):
 p=db(tmp_path); gh=GhSimulado(existe=True,fallo='boe.db')
 with pytest.raises(gestion_base.GestionBaseError): gestion_base.publicar_base(p,'x/y',runner=gh,verificar_remoto=lambda _: {})
 assert not any(Path(c[3]).name == 'manifest.json' for c in gh.llamadas if c[:3] == ['release','upload',gestion_base.RELEASE_TAG])

def test_publicacion_verifica_manifest_remoto_y_no_muta_sqlite(tmp_path):
 p=db(tmp_path); antes=p.read_bytes(); manifest=gestion_base.crear_manifest(p); gh=GhSimulado(existe=True)
 gestion_base.publicar_base(p,'x/y',runner=gh, verificar_remoto=lambda _:manifest)
 assert p.read_bytes()==antes

def test_fallo_manifest_se_puede_reintentar_sin_modificar_sqlite(tmp_path):
 p=db(tmp_path); antes=p.read_bytes(); gh=GhSimulado(existe=False, fallo='manifest.json'); manifest=gestion_base.crear_manifest(p)
 with pytest.raises(gestion_base.GestionBaseError): gestion_base.publicar_base(p,'x/y',runner=gh,verificar_remoto=lambda _: manifest)
 assert gh.existe and p.read_bytes() == antes
 gh.fallo=None
 gestion_base.publicar_base(p,'x/y',runner=gh,verificar_remoto=lambda _: manifest)

@pytest.mark.parametrize('args,mensaje', [
 (['gh'], 'No se encontró GitHub CLI'),
])
def test_errores_gh_son_controlados(monkeypatch, args, mensaje):
 def ausente(*a, **k): raise FileNotFoundError()
 with pytest.raises(gestion_base.GestionBaseError, match=mensaje): gestion_base.comprobar_gh(runner=ausente)


def test_fallo_autenticacion_no_se_confunde_con_release_ausente():
 def runner(args, **kw):
  if args[1:] == ['--version']: return Resultado(stdout='gh')
  return Resultado(1, stderr='not logged into any GitHub hosts')
 with pytest.raises(gestion_base.GestionBaseError, match='no está autenticado'):
  gestion_base.comprobar_gh(runner=runner)


def test_remote_manifest_distinto_no_valida_publicacion(tmp_path):
 p=db(tmp_path); gh=GhSimulado(existe=True); remoto=gestion_base.crear_manifest(p); remoto['sha256']='0' * 64
 with pytest.raises(gestion_base.GestionBaseError, match='no coincide'):
  gestion_base.publicar_base(p, 'x/y', runner=gh, verificar_remoto=lambda _: remoto)


def test_consulta_release_inexistente_es_estado_normal():
 estado = gestion_base.consultar_copia_publicada('x/y', runner=GhSimulado())
 assert estado['estado'] == 'no_publicada'
 assert 'Todavía no existe' in estado['mensaje']


def test_consulta_release_sin_manifest_es_incompleta():
 gh = GhSimulado(existe=True)
 estado = gestion_base.consultar_copia_publicada('x/y', runner=gh)
 assert estado['estado'] == 'publicacion_incompleta'


def test_consulta_release_con_manifest_valido_y_repositorio_redirigido(tmp_path):
 p = db(tmp_path); manifest = gestion_base.crear_manifest(p)
 gh = GhSimulado(existe=True, manifest=manifest); gh.assets = [('manifest.json', 1)]
 estado = gestion_base.consultar_copia_publicada('owner/nombre-anterior', runner=gh)
 assert estado['estado'] == 'publicada' and estado['manifest']['sha256'] == manifest['sha256']
 assert any('--repo' in llamada and llamada[llamada.index('--repo') + 1] == 'owner/nombre-anterior' for llamada in gh.llamadas)


def test_manifest_remoto_invalido_es_error_controlado():
 gh = GhSimulado(existe=True, manifest={'formato': 'incorrecto'}); gh.assets = [('manifest.json', 1)]
 with pytest.raises(gestion_base.GestionBaseError, match='no es válida'):
  gestion_base.consultar_copia_publicada('x/y', runner=gh)


@pytest.mark.parametrize('stderr', ['permission denied', 'network timeout'])
def test_error_release_no_se_confunde_con_ausencia(stderr):
 def runner(args, **kw): return Resultado(1, stderr=stderr)
 with pytest.raises(gestion_base.GestionBaseError):
  gestion_base.consultar_release('x/y', runner=runner)


def test_repositorio_ssh_y_https_se_extrae_sin_confundir_nombre():
 for remoto in ('git@github.com:owner/proyecto.git\n', 'https://github.com/owner/proyecto.git\n'):
  assert gestion_base.repositorio_configurado(runner=lambda *a, remoto=remoto, **k: Resultado(stdout=remoto)) == 'owner/proyecto'

def test_migracion_sin_ruta_deja_base_intacta(tmp_path):
 p=db(tmp_path); con=sqlite3.connect(p); con.execute("UPDATE metadata SET valor='4' WHERE clave='schema_version'"); con.commit(); con.close(); antes=p.read_bytes()
 with pytest.raises(gestion_base.GestionBaseError): gestion_base.migrar_si_necesario(p)
 assert p.read_bytes()==antes

def test_gestor_evitar_doble_confirmacion(tmp_path, monkeypatch):
 p=db(tmp_path); gestor=gestion_base.GestorPublicacion(); bloqueado=[]
 def publicar(*a,**k): bloqueado.append(True); __import__('time').sleep(.05)
 monkeypatch.setattr(gestion_base,'publicar_base',publicar)
 _, primero=gestor.iniciar(p,'x/y'); _, segundo=gestor.iniciar(p,'x/y')
 assert primero and not segundo
 for _ in range(50):
  if gestor.obtener()['terminal']: break
  time.sleep(.01)


def test_trabajo_terminal_congela_duracion_y_marca_estado(tmp_path, monkeypatch):
 p = db(tmp_path); gestor = gestion_base.GestorPublicacion()
 monkeypatch.setattr(gestion_base, 'publicar_base', lambda *a, **k: None)
 trabajo, _ = gestor.iniciar(p, 'x/y')
 for _ in range(50):
  estado = gestor.obtener()
  if estado['terminal']: break
  time.sleep(.01)
 assert estado['estado'] == 'completado' and estado['fase'] == 'Publicación completada.'
 time.sleep(.02)
 assert gestor.obtener()['transcurrido_segundos'] == estado['transcurrido_segundos']


def test_trabajo_error_tambien_es_terminal_y_congela_duracion(tmp_path, monkeypatch):
 p = db(tmp_path); gestor = gestion_base.GestorPublicacion()
 monkeypatch.setattr(gestion_base, 'publicar_base', lambda *a, **k: (_ for _ in ()).throw(gestion_base.GestionBaseError('fallo seguro')))
 gestor.iniciar(p, 'x/y')
 for _ in range(50):
  estado = gestor.obtener()
  if estado['terminal']: break
  time.sleep(.01)
 assert estado['estado'] == 'error' and estado['error'] == 'fallo seguro'


def test_gestor_admite_una_nueva_publicacion_tras_finalizar(tmp_path, monkeypatch):
 p = db(tmp_path); gestor = gestion_base.GestorPublicacion(); llamadas = []
 def publicar(*a, **k): llamadas.append(1)
 monkeypatch.setattr(gestion_base, 'publicar_base', publicar)
 gestor.iniciar(p, 'x/y')
 for _ in range(50):
  if gestor.obtener()['terminal']: break
  time.sleep(.01)
 _, creada = gestor.iniciar(p, 'x/y')
 assert creada


def _opener_publicado(manifest, contenido):
 class Res(io.BytesIO):
  def __enter__(s): return s
  def __exit__(s,*a): return False
 return lambda url: Res(json.dumps(manifest).encode() if url.endswith('manifest.json') else contenido)


def test_actualizacion_github_valida_hace_backup_y_sustituye(tmp_path):
 origen = db(tmp_path); destino = db(tmp_path / 'destino'); con=sqlite3.connect(destino); con.execute("UPDATE metadata SET valor='0' WHERE clave='data_version'"); con.commit(); con.close()
 manifest = gestion_base.crear_manifest(origen); antes = destino.read_bytes(); fases=[]
 resultado = gestion_base.actualizar_base_desde_github(destino, 'x/y', opener=_opener_publicado(manifest, origen.read_bytes()), progreso=lambda *a:fases.append(a), directorio_backup=tmp_path/'backups')
 assert resultado['actualizada'] and destino.read_bytes() == origen.read_bytes()
 assert Path(resultado['backup']).exists() and gestion_base.verificar_integridad(Path(resultado['backup']))['data_version'] == 0
 assert any(f[0] == 'Descargando la base de datos...' for f in fases)


def test_actualizacion_sha_incorrecto_no_toca_base(tmp_path):
 origen=db(tmp_path); destino=db(tmp_path/'destino'); antes=destino.read_bytes(); manifest=gestion_base.crear_manifest(origen); manifest['sha256']='0'*64
 with pytest.raises(gestion_base.GestionBaseError): gestion_base.actualizar_base_desde_github(destino,'x/y',opener=_opener_publicado(manifest,origen.read_bytes()),directorio_backup=tmp_path/'backups')
 assert destino.read_bytes()==antes and not list(tmp_path.glob('*.github.download'))


def test_actualizacion_schema_futuro_no_toca_base(tmp_path):
 origen=db(tmp_path); destino=db(tmp_path/'destino'); antes=destino.read_bytes(); manifest=gestion_base.crear_manifest(origen); manifest['schema_version']=99
 with pytest.raises(gestion_base.GestionBaseError, match='estructura'):
  gestion_base.actualizar_base_desde_github(destino,'x/y',opener=_opener_publicado(manifest,origen.read_bytes()),directorio_backup=tmp_path/'backups')
 assert destino.read_bytes()==antes

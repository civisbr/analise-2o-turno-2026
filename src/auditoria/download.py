import datetime
import hashlib
import http.client
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

HOST = 'cdn.tse.jus.br'
BASE = f'https://{HOST}/estatistica/sead/odsele'
# Presidente de todas as UFs fica nos arquivos nacionais; os zips por UF só têm cargos estaduais.
FILES = ('votacao_secao/votacao_secao_{year}_BR.zip', 'detalhe_votacao_secao/detalhe_votacao_secao_{year}.zip')
MANIFEST = 'MANIFEST.json'


class _SoTse(urllib.request.HTTPRedirectHandler):
    """urllib segue redirect para qualquer host e esquema; aqui só https no host do TSE."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme != 'https' or u.hostname != HOST:
            raise urllib.error.URLError(f'redirecionamento recusado: {newurl}')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SoTse)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def _load_manifest(d):
    p = d / MANIFEST
    return json.loads(p.read_text()) if p.exists() else {}


def _save_manifest(d, m):
    (d / MANIFEST).write_text(json.dumps(m, indent=2, sort_keys=True) + '\n')


def download(dest_dir, year):
    d = pathlib.Path(dest_dir); d.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(d)
    for tpl in FILES:
        url = f'{BASE}/{tpl.format(year=year)}'
        name = url.rsplit('/', 1)[1]
        dest = d / name
        if dest.exists():
            rec = manifest.get(name)
            if rec and sha256(dest) != rec['sha256']:
                sys.exit(f'{name}: SHA-256 difere do MANIFEST.json (arquivo alterado ou corrompido)')
            if not rec:
                print(f'[aviso] {name}: sem registro no MANIFEST.json')
            continue
        part = dest.with_suffix('.part')
        print('baixando', url)
        try:
            with _opener.open(url, timeout=60) as r, open(part, 'wb') as f:
                expected = r.headers.get('Content-Length')
                n = 0
                for b in iter(lambda: r.read(1 << 20), b''):
                    f.write(b); n += len(b)
                if expected is not None and n != int(expected):
                    raise OSError(f'tamanho recebido {n} difere de Content-Length {expected}')
                last_modified = r.headers.get('Last-Modified')
            part.replace(dest)
            manifest[name] = {'url': url, 'bytes': n, 'sha256': sha256(dest), 'last_modified': last_modified,
                              'downloaded_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}
            _save_manifest(d, manifest)
        except urllib.error.HTTPError as e:
            print(f'  [aviso] HTTP {e.code} – arquivo ainda não publicado ou nome diferente; seguindo')
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
            print(f'  [aviso] falha de rede ({e}); seguindo')
        finally:
            part.unlink(missing_ok=True)

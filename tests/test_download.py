import hashlib
import io
import json
import urllib.error

import pytest

from auditoria import download as dl


class _Resp(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data) if length is None else length), 'Last-Modified': 'x'}

    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Opener:
    def __init__(self, behavior): self.behavior = behavior; self.urls = []

    def open(self, url, timeout=None):
        self.urls.append(url)
        r = self.behavior(url)
        if isinstance(r, Exception):
            raise r
        return r


def test_baixa_e_registra_manifesto(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, '_opener', _Opener(lambda u: _Resp(b'zipdata')))
    dl.download(tmp_path, 2026)
    m = json.loads((tmp_path / 'MANIFEST.json').read_text())
    assert set(m) == {'votacao_secao_2026_BR.zip', 'detalhe_votacao_secao_2026.zip'}
    assert m['votacao_secao_2026_BR.zip']['sha256'] == hashlib.sha256(b'zipdata').hexdigest()
    assert not list(tmp_path.glob('*.part'))


def test_404_tolerado_sem_deixar_parcial(tmp_path, monkeypatch):
    err = urllib.error.HTTPError('u', 404, 'nf', {}, None)
    monkeypatch.setattr(dl, '_opener', _Opener(lambda u: err))
    dl.download(tmp_path, 2026)
    assert list(tmp_path.iterdir()) == []


def test_download_truncado_e_descartado(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, '_opener', _Opener(lambda u: _Resp(b'abc', length=10)))
    dl.download(tmp_path, 2026)
    assert list(tmp_path.iterdir()) == []


def test_arquivo_alterado_para_o_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, '_opener', _Opener(lambda u: _Resp(b'zipdata')))
    dl.download(tmp_path, 2026)
    (tmp_path / 'votacao_secao_2026_BR.zip').write_bytes(b'adulterado')
    with pytest.raises(SystemExit, match='SHA-256'):
        dl.download(tmp_path, 2026)


def test_redirect_fora_do_host_recusado():
    h = dl._SoTse()
    for bad in ('http://cdn.tse.jus.br/x.zip', 'https://evil.example/x.zip'):
        with pytest.raises(urllib.error.URLError, match='recusado'):
            h.redirect_request(None, None, 302, 'Found', {}, bad)

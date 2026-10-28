import json

from auditoria import cli
from auditoria.runinfo import write_run


def test_run_json_registra_saidas_e_versoes(tmp_path):
    (tmp_path / 'a.csv').write_text('x\n1\n')
    info = write_run('verify', 2026, ['verify'], tmp_path, None, fechamento={'x': 0}, arquivos=[tmp_path / 'a.csv'])
    salvo = json.loads((tmp_path / 'run_verify_2026.json').read_text())
    assert salvo['saidas']['a.csv'] == info['saidas']['a.csv'] and len(salvo['saidas']['a.csv']) == 64
    assert {'python', 'numpy', 'polars'} <= set(salvo['versoes'])
    assert salvo['insumos'] is None and salvo['fechamento_secoes_divergentes'] == {'x': 0}


def test_verify_via_cli_grava_run_json(synth_dir, tmp_path, monkeypatch):
    from synth import UFS
    cli.main(['verify', '--dir', str(synth_dir), '--out', str(tmp_path), '--year', '2026', '--sem-prereg'])
    assert (tmp_path / 'run_verify_2026.json').exists() and (tmp_path / 'totais_nacionais_2026.csv').exists()


def test_argv_absoluto_nao_vaza_caminho_pessoal():
    from auditoria.runinfo import ROOT, sanitiza_argv
    r = sanitiza_argv(['verify', '--dir', '/home/fulano/dados', '--out', str(ROOT / 'data' / 'derived'), '--year', '2026'])
    assert r == ['verify', '--dir', '<externo>', '--out', 'data/derived', '--year', '2026']


def test_gitignore_nao_reabre_secoes():
    import subprocess
    from auditoria.runinfo import ROOT
    for f in ('data/derived/secoes_2026.csv', 'data/derived/secoes_sinalizadas_2026.csv', 'data/private/x.csv'):
        r = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', f])
        assert r.returncode == 0, f


def test_argv_com_igual_tambem_e_sanitizado():
    from auditoria.runinfo import sanitiza_argv
    assert sanitiza_argv(['--dir=/home/fulano/x', '--year=2026']) == ['--dir=<externo>', '--year=2026']


def test_confere_insumos_detecta_zip_alterado(tmp_path):
    import hashlib, json, pytest
    from auditoria.runinfo import confere_insumos
    (tmp_path / 'a.zip').write_bytes(b'ok')
    (tmp_path / 'MANIFEST.json').write_text(json.dumps({'a.zip': {'sha256': hashlib.sha256(b'ok').hexdigest(),
                                                                   'bytes': 2, 'url': 'u'}}))
    assert confere_insumos(tmp_path)['a.zip']['bytes'] == 2
    (tmp_path / 'a.zip').write_bytes(b'adulterado')
    with pytest.raises(SystemExit, match='SHA-256'):
        confere_insumos(tmp_path)


def test_zip_fora_do_manifesto_para_o_pipeline(tmp_path):
    import json, pytest
    from auditoria.runinfo import confere_insumos
    (tmp_path / 'MANIFEST.json').write_text(json.dumps({}))
    (tmp_path / 'colocado_a_mao.zip').write_bytes(b'x')
    with pytest.raises(SystemExit, match='sem registro'):
        confere_insumos(tmp_path)

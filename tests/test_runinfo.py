import json

from auditoria import cli
from auditoria.runinfo import write_run


def test_run_json_registra_saidas_e_versoes(tmp_path):
    (tmp_path / 'a.csv').write_text('x\n1\n')
    info = write_run('verify', 2026, ['verify'], tmp_path, tmp_path)
    salvo = json.loads((tmp_path / 'run_verify_2026.json').read_text())
    assert salvo['saidas']['a.csv'] == info['saidas']['a.csv'] and len(salvo['saidas']['a.csv']) == 64
    assert {'python', 'numpy', 'pandas'} <= set(salvo['versoes'])
    assert salvo['insumos'] is None


def test_verify_via_cli_grava_run_json(synth_dir, tmp_path, monkeypatch):
    from synth import UFS
    monkeypatch.setattr('auditoria.verify.ALL', UFS[:-1])
    cli.main(['verify', '--dir', str(synth_dir), '--out', str(tmp_path), '--year', '2026'])
    assert (tmp_path / 'run_verify_2026.json').exists() and (tmp_path / 'totais_nacionais_2026.csv').exists()

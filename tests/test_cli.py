from auditoria import cli, download


def test_download_via_cli_nao_precisa_de_ufs(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(cli, 'download', lambda d, y: chamadas.append((str(d), y)))
    cli.main(['download', '--year', '2026', '--dir', str(tmp_path)])
    assert chamadas == [(str(tmp_path), '2026')]


def test_ano_invalido_recusado():
    import pytest
    with pytest.raises(SystemExit):
        cli.main(['download', '--year', '../x'])

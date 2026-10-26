import pytest

from auditoria import cli
from auditoria.load import load_sections
from auditoria.verify import reconcile, totais
from synth import UFS


@pytest.fixture(scope='module')
def secoes(synth_dir):
    return load_sections(synth_dir, 2026, UFS)


def test_sintetico_fecha_votacao_e_detalhe(secoes):
    assert not any(reconcile(secoes).values())


def test_detalhe_divergente_e_detectado(secoes):
    g = secoes.copy()
    g.loc[g.index[:3], 'nominais'] += 1
    r = reconcile(g)
    assert r['válidos (votação) != nominais (detalhe)'] == 3
    assert r['comparecimento != nominais + brancos + nulos'] == 3


def test_totais_nacionais_somam_as_ufs(secoes):
    nac, uf = totais(secoes)
    assert (uf.groupby('NR_TURNO').sum() == nac).all().all()
    assert (nac.terceira_via == nac.valid - nac.lula - nac.flavio).all()
    # seções não instaladas têm aptos sem comparecimento nem abstenção registrada
    assert (nac.abstencao < nac.apt - nac.comp).all()


def test_verify_via_cli_para_se_nao_fecha(synth_dir, tmp_path, monkeypatch):
    import io, shutil, zipfile
    import pandas as pd
    for f in ('votacao_secao_2026_BR.zip',):
        shutil.copy(synth_dir / f, tmp_path / f)
    m = 'detalhe_votacao_secao_2026_BR.csv'
    with zipfile.ZipFile(synth_dir / 'detalhe_votacao_secao_2026.zip') as z:
        df = pd.read_csv(io.BytesIO(z.read(m)), sep=';', encoding='latin1', dtype=str)
    df.loc[df.index[0], 'QT_VOTOS_BRANCOS'] = str(int(df.QT_VOTOS_BRANCOS.iloc[0]) + 1)
    with zipfile.ZipFile(tmp_path / 'detalhe_votacao_secao_2026.zip', 'w') as z:
        z.writestr(m, df.to_csv(sep=';', index=False).encode('latin1'))
    monkeypatch.setattr('auditoria.verify.ALL', UFS[:-1])
    with pytest.raises(SystemExit, match='fechamento falhou'):
        cli.main(['verify', '--dir', str(tmp_path), '--out', str(tmp_path / 'o'), '--year', '2026', '--sem-prereg'])
    assert not (tmp_path / 'o').exists()   # nada gravado quando o fechamento falha


def test_verify_2026_com_segundo_turno_exige_prereg(synth_dir, tmp_path, monkeypatch):
    monkeypatch.setattr('auditoria.verify.ALL', UFS[:-1])
    monkeypatch.setattr('auditoria.prereg.ROOT', tmp_path)   # sem repositório git: tag ausente
    with pytest.raises(SystemExit, match='prereg-v1'):
        cli.main(['verify', '--dir', str(synth_dir), '--out', str(tmp_path / 'o'), '--year', '2026'])
    assert not (tmp_path / 'o').exists()

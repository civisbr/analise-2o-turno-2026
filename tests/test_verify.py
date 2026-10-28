import polars as pl
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
    g = secoes.with_row_index('_i').with_columns(
        nominais=pl.when(pl.col('_i') < 3).then(pl.col('nominais') + 1).otherwise(pl.col('nominais'))).drop('_i')
    r = reconcile(g)
    assert r['válidos (votação) != nominais (detalhe)'] == 3
    assert r['comparecimento != nominais + brancos + nulos'] == 3


def test_totais_nacionais_somam_as_ufs(secoes):
    nac, uf = totais(secoes)
    cols = [c for c in nac.columns if c != 'NR_TURNO']
    assert uf.group_by('NR_TURNO').agg(pl.col(cols).sum()).sort('NR_TURNO').equals(nac)
    assert (nac['terceira_via'] == nac['valid'] - nac['lula'] - nac['flavio']).all()
    # seções não instaladas têm aptos sem comparecimento nem abstenção registrada
    assert (nac['abstencao'] < nac['apt'] - nac['comp']).all()


def test_verify_via_cli_para_se_nao_fecha(synth_dir, tmp_path, monkeypatch):
    import io, shutil, zipfile
    for f in ('votacao_secao_2026_BR.zip',):
        shutil.copy(synth_dir / f, tmp_path / f)
    m = 'detalhe_votacao_secao_2026_BR.csv'
    with zipfile.ZipFile(synth_dir / 'detalhe_votacao_secao_2026.zip') as z:
        df = pl.read_csv(io.BytesIO(z.read(m)), separator=';', encoding='utf8-lossy', infer_schema=False)
    df = df.with_row_index('_i').with_columns(
        QT_VOTOS_BRANCOS=pl.when(pl.col('_i') == 0).then((pl.col('QT_VOTOS_BRANCOS').cast(pl.Int64) + 1).cast(pl.Utf8))
        .otherwise(pl.col('QT_VOTOS_BRANCOS'))).drop('_i')
    with zipfile.ZipFile(tmp_path / 'detalhe_votacao_secao_2026.zip', 'w') as z:
        z.writestr(m, df.write_csv(separator=';').encode('latin1'))
    with pytest.raises(SystemExit, match='fechamento falhou'):
        cli.main(['verify', '--dir', str(tmp_path), '--out', str(tmp_path / 'o'), '--year', '2026', '--sem-prereg'])
    assert not (tmp_path / 'o').exists()   # nada gravado quando o fechamento falha


def test_verify_2026_com_segundo_turno_exige_prereg(synth_dir, tmp_path, monkeypatch):
    monkeypatch.setattr('auditoria.prereg.ROOT', tmp_path)   # sem repositório git: tag ausente
    with pytest.raises(SystemExit, match='prereg-v1'):
        cli.main(['verify', '--dir', str(synth_dir), '--out', str(tmp_path / 'o'), '--year', '2026'])
    assert not (tmp_path / 'o').exists()

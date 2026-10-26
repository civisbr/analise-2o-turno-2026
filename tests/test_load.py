import io
import zipfile

import pandas as pd
import pytest

from auditoria.load import ALL, NE, load_year, resolve_ufs
from synth import UFS


def test_resolve_ufs():
    assert resolve_ufs('NE') == NE
    assert resolve_ufs('all') == ALL and len(ALL) == 27
    assert resolve_ufs('BA, SP') == ['BA', 'SP']
    with pytest.raises(SystemExit):
        resolve_ufs('BA,XX')


def test_load_fecha_com_totais_por_turno(wide26):
    assert set(wide26.SG_UF) == set(UFS)
    for t in ('1', '2'):
        assert (wide26['comp' + t] >= wide26['valid' + t]).all()
        assert (wide26['apt' + t] >= wide26['comp' + t]).all()
        assert (wide26['lula' + t] + wide26['flavio' + t] <= wide26['valid' + t]).all()


def test_ignora_outro_cargo(wide26):
    assert (wide26.lula1 < 1000).all() and (wide26.lula2 < 1000).all()   # isca do cargo 3 vale 7777


def test_filtra_ufs_pedidas(synth_dir):
    assert set(load_year(synth_dir, 2026, ['BA']).SG_UF) == {'BA'}


def _reescreve_zip(src, dst, member, transform):
    with zipfile.ZipFile(src) as z:
        df = pd.read_csv(io.BytesIO(z.read(member)), sep=';', encoding='latin1', dtype=str)
    df = transform(df)
    with zipfile.ZipFile(dst, 'w') as z:
        z.writestr(member, df.to_csv(sep=';', index=False).encode('latin1'))


def test_turno_ausente_para_o_pipeline(synth_dir, tmp_path):
    for name, member in (('votacao_secao_2026_BR.zip', 'votacao_secao_2026_BR.csv'),
                         ('detalhe_votacao_secao_2026.zip', 'detalhe_votacao_secao_2026_BR.csv')):
        _reescreve_zip(synth_dir / name, tmp_path / name, member, lambda df: df[df.NR_TURNO == '1'])
    with pytest.raises(SystemExit, match='faltam turnos'):
        load_year(tmp_path, 2026, ['BA'])


def test_coluna_ausente_para_o_pipeline(synth_dir, tmp_path):
    _reescreve_zip(synth_dir / 'votacao_secao_2026_BR.zip', tmp_path / 'votacao_secao_2026_BR.zip',
                   'votacao_secao_2026_BR.csv', lambda df: df.drop(columns='QT_VOTOS'))
    with pytest.raises(SystemExit, match='colunas ausentes'):
        load_year(tmp_path, 2026, ['BA'])


def test_arquivo_ausente_para_o_pipeline(tmp_path):
    with pytest.raises(SystemExit, match='ausente'):
        load_year(tmp_path, 2026, ['BA'])


def test_cli_analise_exige_prereg(synth_dir, tmp_path, monkeypatch):
    from auditoria import cli
    monkeypatch.chdir(tmp_path)   # fora de qualquer repositório git: tag ausente
    with pytest.raises(SystemExit, match='prereg-v1'):
        cli.main(['balanco', '--dir', str(synth_dir), '--out', str(tmp_path / 'o'), '--ufs', 'BA,PE,SP,PA'])


def test_carga_em_blocos_igual_a_carga_unica(synth_dir):
    a = load_year(synth_dir, 2026, ['BA', 'PE'], chunksize=1000)
    b = load_year(synth_dir, 2026, ['BA', 'PE'])
    pd.testing.assert_frame_equal(a.sort_values(list(a.columns)).reset_index(drop=True),
                                  b.sort_values(list(b.columns)).reset_index(drop=True))


def test_secao_sem_detalhe_para_o_pipeline(synth_dir, tmp_path):
    import shutil
    shutil.copy(synth_dir / 'votacao_secao_2026_BR.zip', tmp_path)
    _reescreve_zip(synth_dir / 'detalhe_votacao_secao_2026.zip', tmp_path / 'detalhe_votacao_secao_2026.zip',
                   'detalhe_votacao_secao_2026_BR.csv', lambda df: df.iloc[100:])
    with pytest.raises(SystemExit, match='sem linha no detalhe'):
        load_year(tmp_path, 2026, ['BA'])


def test_detalhe_ausente_desliga_comparecimento(synth_dir, tmp_path):
    import shutil
    shutil.copy(synth_dir / 'votacao_secao_2026_BR.zip', tmp_path)
    w = load_year(tmp_path, 2026, ['BA'])
    assert w.comp1.isna().all()


def test_membro_ausente_para_o_pipeline(synth_dir, tmp_path):
    import shutil
    shutil.copy(synth_dir / 'votacao_secao_2026_BR.zip', tmp_path / 'votacao_secao_2022_BR.zip')
    with pytest.raises(SystemExit, match='membro'):
        load_year(tmp_path, 2022, ['BA'])


def test_secao_so_no_detalhe_entra_nos_totais_mas_nao_na_analise(synth_dir, secoes_longas=None):
    import numpy as np
    from auditoria.load import load_sections
    longo = load_sections(synth_dir, 2026, UFS)
    vazias = longo[longo.NR_SECAO == '9999']
    assert len(vazias) == 2 * len(UFS) and (vazias.valid == 0).all() and (vazias.comp == 0).all()
    assert all(np.issubdtype(longo[c].dtype, np.integer) for c in ('lula', 'valid', 'apt', 'comp'))
    assert '9999' not in set(load_year(synth_dir, 2026, UFS).NR_SECAO)


def test_detalhe_com_votos_sem_votacao_para_o_pipeline(synth_dir, tmp_path):
    import shutil
    m = 'votacao_secao_2026_BR.zip'
    _reescreve_zip(synth_dir / m, tmp_path / m, 'votacao_secao_2026_BR.csv', lambda df: df.iloc[200:])
    shutil.copy(synth_dir / 'detalhe_votacao_secao_2026.zip', tmp_path)
    with pytest.raises(SystemExit, match='sem linha na votação'):
        load_year(tmp_path, 2026, ['BA'])

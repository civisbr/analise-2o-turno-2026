import contextlib
import io

import numpy as np
import polars as pl
import pytest

from auditoria.closing import closing_test
from auditoria.swing import summarize, swing_table


def test_swing_identifica_municipios_plantados(wide26):
    d, kappa = swing_table(wide26)
    flagged, muni = summarize(d)
    assert kappa > 0
    assert {'BA-00003', 'BA-00007', 'BA-00011'} <= set(muni['mun'][:5])
    assert (muni['z_mun'].drop_nulls().abs().diff().drop_nulls() <= 0).all()   # ordenado por |z|
    assert flagged.height > 0


def test_fechamento_sem_efeito_nao_rejeita(wide22, tmp_path):
    d, _ = swing_table(wide22)
    rng = np.random.default_rng(3)
    late = rng.random(d.height) < 0.2
    c = d.select(['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO']).with_columns(
        fechamento=pl.Series(np.where(late, '2022-10-30T18:30:00', '2022-10-30T17:00:00')))
    path = tmp_path / 'fechamento.csv'
    c.write_csv(path)
    with contextlib.redirect_stdout(io.StringIO()):
        beta, lo, hi, pperm = closing_test(d, path, boot=200)
    assert pperm > 0.01


def test_analyze_nao_grava_secoes_em_derived(synth_dir, tmp_path):
    from auditoria.swing import analyze
    out, priv = tmp_path / 'derived', tmp_path / 'private'
    with contextlib.redirect_stdout(io.StringIO()):
        analyze(synth_dir, out, 2026, None, ['BA', 'PE', 'SP', 'PA'], private_dir=priv)
    assert (priv / 'secoes_2026.csv').exists()
    for f in out.glob('*.csv'):
        cols = pl.read_csv(f, n_rows=0).columns
        assert 'NR_SECAO' not in cols and 'NR_ZONA' not in cols


def test_municipio_pequeno_nao_expoe_contagem_de_secoes_sinalizadas(wide26):
    _, muni = summarize(swing_table(wide26)[0])
    small = muni.filter(pl.col('secoes') < 10)
    assert small.height == 0 or all(small[c].null_count() == small.height for c in ('flag_pos', 'flag_neg', 'excesso_liquido_votos'))
    big = muni.filter(pl.col('secoes') >= 10)
    assert big['flag_pos'].null_count() == 0


def _sem_secoes_de_sp5(w):
    """Deixa o município SP-00005 com só 5 seções."""
    sp5 = (pl.col('SG_UF') == 'SP') & (pl.col('CD_MUNICIPIO') == '00005')
    n = pl.int_range(pl.len()).over(sp5)
    return w.filter(~(sp5 & (n >= 5)))


def test_resumo_mascara_municipio_com_poucas_secoes(wide26_noplant):
    from auditoria.swing import summarize, swing_table
    w = wide26_noplant
    _, muni = summarize(swing_table(_sem_secoes_de_sp5(w))[0])
    r = muni.filter(pl.col('mun') == 'SP-00005').row(0, named=True)
    assert r['secoes'] < 10 and all(r[c] is None for c in ('swing_mediano', 'swing_medio', 'votos_2t', 'flag_pos'))
    assert muni.filter(pl.col('mun') == 'SP-00006')['swing_mediano'][0] is not None


def _municipio(cd, lula1, flavio1, lula2, flavio2):
    n = len(lula1)
    return pl.DataFrame({'SG_UF': ['BA'] * n, 'CD_MUNICIPIO': [cd] * n, 'lula1': lula1, 'flavio1': flavio1,
                         'lula2': lula2, 'flavio2': flavio2, 'comp1': [300] * n, 'comp2': [300] * n,
                         'apt1': [400] * n, 'apt2': [400] * n})


def test_secao_unanime_nos_dois_turnos_nao_gera_nan_nem_inf(wide26):
    primeira = pl.int_range(pl.len()) == 0
    w = wide26.with_columns(
        lula1=pl.when(primeira).then(200).otherwise(pl.col('lula1')), lula2=pl.when(primeira).then(200).otherwise(pl.col('lula2')),
        flavio1=pl.when(primeira).then(0).otherwise(pl.col('flavio1')), flavio2=pl.when(primeira).then(0).otherwise(pl.col('flavio2')))
    alvo = w.row(0, named=True)
    d, kappa = swing_table(w)
    z = d.filter((pl.col('SG_UF') == alvo['SG_UF']) & (pl.col('CD_MUNICIPIO') == alvo['CD_MUNICIPIO'])
                 & (pl.col('NR_ZONA') == alvo['NR_ZONA']) & (pl.col('NR_SECAO') == alvo['NR_SECAO']))['z'][0]
    assert np.isfinite(kappa) and np.isfinite(d['z'].to_numpy()).all() and z == 0


def test_se_zero_com_mediana_zero_nao_gera_nan():
    # mediana do município 0 e se=0: 0/0 contaminava o MAD (kappa NaN) com dados reais de 2022
    rng = np.random.default_rng(0)
    base = [_municipio(str(k), 100 + rng.integers(0, 30, 40), 100 + rng.integers(0, 30, 40),
                       100 + rng.integers(0, 30, 40), 100 + rng.integers(0, 30, 40)) for k in range(5)]
    unanimes = _municipio('99', [200, 200, 200, 150, 120], [0, 0, 0, 150, 130], [200, 200, 200, 160, 110], [0, 0, 0, 140, 140])
    d, kappa = swing_table(pl.concat(base + [unanimes]))
    u = d.filter((pl.col('CD_MUNICIPIO') == '99') & (pl.col('se') == 0))
    assert u.height == 3 and (u['ref'] == 0).all()
    assert np.isfinite(kappa) and np.isfinite(d['z'].to_numpy()).all() and (u['z'] == 0).all()


def test_mad_zero_para_o_pipeline_em_vez_de_gerar_nan():
    # todas as seções iguais ao seu município: resíduo 0 em toda parte, MAD 0
    base = [_municipio(str(k), [100] * 6, [100] * 6, [110] * 6, [90] * 6) for k in range(4)]
    with pytest.raises(SystemExit, match='MAD'):
        swing_table(pl.concat(base))


@pytest.mark.parametrize('formato', ['{}', '{}-03:00', '{}Z'])
def test_fechamento_aceita_fuso_e_ignora_horario_vazio(wide22, tmp_path, formato, capsys):
    d, _ = swing_table(wide22)
    rng = np.random.default_rng(3)
    late = rng.random(d.height) < 0.2
    horas = np.where(late, '2022-10-30T18:30:00', '2022-10-30T17:00:00').astype(object)
    horas = [formato.format(h) for h in horas]
    horas[0] = ''   # seção sem horário
    c = d.select(['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO']).with_columns(fechamento=pl.Series(horas))
    c.write_csv(tmp_path / 'f.csv')
    with contextlib.redirect_stdout(io.StringIO()) as saida:
        closing_test(d, tmp_path / 'f.csv', boot=50)
    assert 'sem horário de fechamento' in saida.getvalue()


def test_fechamento_com_formato_ilegivel_para_o_pipeline(wide22, tmp_path):
    d, _ = swing_table(wide22)
    c = d.select(['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO']).with_columns(fechamento=pl.lit('ontem à tarde'))
    c.write_csv(tmp_path / 'f.csv')
    with pytest.raises(SystemExit, match='não reconhecido'):
        closing_test(d, tmp_path / 'f.csv', boot=20)

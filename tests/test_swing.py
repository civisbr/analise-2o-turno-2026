import contextlib
import io

import numpy as np
import pandas as pd

from auditoria.closing import closing_test
from auditoria.swing import summarize, swing_table


def test_swing_identifica_municipios_plantados(wide26):
    d = swing_table(wide26)
    flagged, muni = summarize(d)
    assert d.attrs['kappa'] > 0
    assert {'BA-00003', 'BA-00007', 'BA-00011'} <= set(muni.index[:5])
    assert (muni.z_mun.dropna().abs().diff().dropna() <= 0).all()   # ordenado por |z|
    assert len(flagged) > 0


def test_fechamento_sem_efeito_nao_rejeita(wide22, tmp_path):
    d = swing_table(wide22)
    rng = np.random.default_rng(3)
    c = d[['SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO']].copy()
    late = rng.random(len(c)) < 0.2
    c['fechamento'] = np.where(late, '2022-10-30T18:30:00', '2022-10-30T17:00:00')
    path = tmp_path / 'fechamento.csv'
    c.to_csv(path, index=False)
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
        cols = pd.read_csv(f, nrows=0).columns
        assert 'NR_SECAO' not in cols and 'NR_ZONA' not in cols


def test_municipio_pequeno_nao_expoe_contagem_de_secoes_sinalizadas(wide26):
    _, muni = summarize(swing_table(wide26))
    small = muni[muni.secoes < 10]
    assert len(small) == 0 or small[['flag_pos', 'flag_neg', 'excesso_liquido_votos']].isna().all().all()
    big = muni[muni.secoes >= 10]
    assert big.flag_pos.notna().all()

import numpy as np
import pandas as pd

from .load import KEY, need
from .robust import CLOSING_SEED


def closing_test(d, path, boot=2000, seed=CLOSING_SEED):
    c = pd.read_csv(path, dtype=str)
    need(c, KEY + ['fechamento'], path)
    c['fechamento'] = pd.to_datetime(c.fechamento)
    d = d.merge(c, on=KEY, how='inner')
    d['late'] = (d.fechamento.dt.hour * 60 + d.fechamento.dt.minute > 17 * 60 + 5).astype(float)
    d = d.dropna(subset=['resid'])
    cols = [np.ones(len(d)), d.late, np.log((d.lula2 + d.flavio2).clip(lower=1))]
    if d.dturn.notna().all():
        cols.append(d.dturn)
    else:
        print('[aviso] sem dados de comparecimento: Δ comparecimento fora dos controles')
    X = np.column_stack(cols)
    y = d.resid.values
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    rng = np.random.default_rng(seed); muns = d.mun.unique(); idx = d.groupby('mun').indices
    bs = []
    for _ in range(boot):
        pick = rng.choice(muns, len(muns))
        ii = np.concatenate([idx[m] for m in pick])
        bs.append(np.linalg.lstsq(X[ii], y[ii], rcond=None)[0][1])
    lo, hi = np.percentile(bs, [2.5, 97.5])
    # Teste principal: permutação de 'late' dentro de cada município (exato sob H0). O IC por
    # bootstrap é secundário: fica levemente liberal com poucos municípios.
    nulls = []
    for _ in range(1000):
        lt = d.late.values.copy()
        for ii in idx.values():
            lt[ii] = rng.permutation(lt[ii])
        Xp = X.copy(); Xp[:, 1] = lt
        nulls.append(np.linalg.lstsq(Xp, y, rcond=None)[0][1])
    pperm = (np.sum(np.abs(nulls) >= abs(beta[1])) + 1) / (len(nulls) + 1)
    print(f'p-valor de permutação dentro do município: {pperm:.3f}')
    print(f'\n[fechamento] seções casadas: {len(d):,}; fechadas após 17h05: {int(d.late.sum()):,}')
    print(f'efeito de fechar tarde no swing Lula (pp, controlando município, tamanho e Δ comparecimento): '
          f'{beta[1]:+.3f}  IC95% cluster-município [{lo:+.3f}, {hi:+.3f}]')
    return beta[1], lo, hi, pperm

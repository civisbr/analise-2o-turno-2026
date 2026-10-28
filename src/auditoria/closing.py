import sys

import numpy as np
import polars as pl

from .load import KEY, need
from .robust import CLOSING_SEED


def closing_test(d, path, boot=2000, seed=CLOSING_SEED):
    c = pl.read_csv(path, infer_schema=False)
    need(c.columns, KEY + ['fechamento'], path)
    # relógio local do boletim: tira o fuso (como o pandas, que lia a hora local) e aceita 'T' ou espaço
    c = c.with_columns(_f=pl.col('fechamento').str.strip_chars().str.replace(r'(Z|[+-]\d{2}:?\d{2})$', '').str.replace('T', ' '))
    vazios = c.filter(pl.col('_f').is_null() | (pl.col('_f') == '')).height
    if vazios:
        print(f'[aviso] {vazios:,} seção(ões) sem horário de fechamento ficam fora do teste')
        c = c.filter(pl.col('_f').is_not_null() & (pl.col('_f') != ''))
    if c.is_empty():
        sys.exit(f'{path}: nenhum horário de fechamento preenchido')
    try:
        c = c.with_columns(fechamento=pl.col('_f').str.to_datetime(strict=True)).drop('_f')
    except pl.exceptions.PolarsError as e:
        sys.exit(f'{path}: formato de data/hora de fechamento não reconhecido ({e})')
    d = d.join(c, on=KEY, how='inner', maintain_order='left')
    d = d.with_columns(late=((pl.col('fechamento').dt.hour() * 60 + pl.col('fechamento').dt.minute()) > 17 * 60 + 5).cast(pl.Float64))
    d = d.drop_nulls(subset=['resid'])
    late = d['late'].to_numpy()
    cols = [np.ones(d.height), late, np.log((d['lula2'] + d['flavio2']).clip(lower_bound=1).to_numpy())]
    if d['dturn'].fill_nan(None).null_count() == 0:   # NaN (apt=0) também é falta de dado
        cols.append(d['dturn'].to_numpy())
    else:
        print('[aviso] sem dados de comparecimento: Δ comparecimento fora dos controles')
    X = np.column_stack(cols)
    y = d['resid'].to_numpy()
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    rng = np.random.default_rng(seed); muns = d['mun'].unique(maintain_order=True).to_numpy()
    grupos = d.with_row_index('_i').group_by('mun').agg(pl.col('_i')).sort('mun')
    idx = {m: np.asarray(i) for m, i in grupos.iter_rows()}
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
        lt = late.copy()
        for ii in idx.values():
            lt[ii] = rng.permutation(lt[ii])
        Xp = X.copy(); Xp[:, 1] = lt
        nulls.append(np.linalg.lstsq(Xp, y, rcond=None)[0][1])
    pperm = (np.sum(np.abs(nulls) >= abs(beta[1])) + 1) / (len(nulls) + 1)
    print(f'p-valor de permutação dentro do município: {pperm:.3f}')
    print(f'\n[fechamento] seções casadas: {d.height:,}; fechadas após 17h05: {int(late.sum()):,}')
    print(f'efeito de fechar tarde no swing Lula (pp, controlando município, tamanho e Δ comparecimento): '
          f'{beta[1]:+.3f}  IC95% cluster-município [{lo:+.3f}, {hi:+.3f}]')
    return beta[1], lo, hi, pperm

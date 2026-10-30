"""Contagens públicas de seções, sem identificar urnas, locais ou eleitores."""
import json
from pathlib import Path

import polars as pl

from .concentracao import candidato
from .load import ALL, KEY, load_sections
from .verify import fechamento


def resumo_secoes(g, ano):
    """Segundo turno completo, sem pareamento com o primeiro e sem piso de tamanho."""
    t = g.filter(pl.col('NR_TURNO').cast(pl.String) == '2')
    if not t.height:
        raise ValueError(f'{ano}: segundo turno ausente')
    if t.select(pl.struct(KEY).n_unique()).item() != t.height:
        raise ValueError(f'{ano}: seção duplicada no segundo turno')
    if t.select(pl.col(['valid', 'lula', 'flavio']).null_count()).sum_horizontal().item():
        raise ValueError(f'{ano}: votação ausente')
    if t.filter((pl.col('valid') < 0) | (pl.col('lula') < 0) | (pl.col('flavio') < 0) |
                (pl.col('lula') + pl.col('flavio') != pl.col('valid'))).height:
        raise ValueError(f'{ano}: votos dos finalistas não fecham com os válidos')

    def conta(base):
        d = base.filter(pl.col('valid') > 0)
        candidatos = {}
        for c in ('lula', 'flavio'):
            v = pl.col(c); outro = pl.col('flavio' if c == 'lula' else 'lula')
            poucos = d.filter(v <= 10)
            candidatos[c] = {
                'nome': candidato(ano, c),
                'zero': d.filter(v == 0).height,
                'de_1_a_5': d.filter(v.is_between(1, 5)).height,
                'de_6_a_10': d.filter(v.is_between(6, 10)).height,
                'ate_10': poucos.height,
                'pct_ate_10': poucos.height / d.height * 100 if d.height else None,
                'acima_90': d.filter(v * 10 > pl.col('valid') * 9).height,
                'ate_10_e_adversario_acima_90': poucos.filter(outro * 10 > pl.col('valid') * 9).height,
                'ate_10_com_50_mais_validos': poucos.filter(pl.col('valid') >= 50).height,
                'validos_nas_secoes_ate_10': {
                    'min': poucos['valid'].min(), 'mediana': poucos['valid'].median(), 'max': poucos['valid'].max(),
                },
            }
        return {'avaliadas': d.height, 'sem_validos_excluidas': base.height - d.height, 'candidatos': candidatos}

    return {'brasil': conta(t.filter(pl.col('SG_UF') != 'ZZ')),
            'exterior': conta(t.filter(pl.col('SG_UF') == 'ZZ')),
            'brasil_exterior': conta(t),
            'ufs': [{'uf': uf, **conta(t.filter(pl.col('SG_UF') == uf))}
                    for uf in sorted(t['SG_UF'].unique().to_list()) if uf != 'ZZ']}


def distribuicao(dir, out, year='2026', control_year='2022'):
    anos, checks = {}, {}
    for ano in dict.fromkeys((str(control_year), str(year))):
        g = load_sections(dir, ano, ALL + ['ZZ'])
        if g['apt'].null_count():
            raise ValueError(f'{ano}: detalhe por seção ausente')
        checks[ano] = fechamento(dir, ano, g)
        anos[ano] = resumo_secoes(g, ano)
        r = anos[ano]['brasil']
        print(f'{ano}: {r["avaliadas"]:,} seções com válidos no Brasil; '
              f'{candidato(ano, "flavio")}, até 10 votos: {r["candidatos"]["flavio"]["ate_10"]:,}')
    p = Path(out) / 'distribuicao_secoes.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({'turno': 2, 'limite_votos': 10, 'anos': anos}, ensure_ascii=False,
                            indent=1, allow_nan=False) + '\n', encoding='utf-8')
    return {'arquivos': [p], 'fechamento': checks}

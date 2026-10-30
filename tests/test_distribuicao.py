import json

import polars as pl
import pytest

from auditoria import cli
from auditoria.distribuicao import resumo_secoes
from auditoria.runinfo import _sha


def secoes():
    votos = [(100, 0), (99, 1), (95, 5), (94, 6), (90, 10), (89, 11), (10, 90), (0, 100), (10, 10), (0, 0)]
    rows = [{'SG_UF': 'BA', 'CD_MUNICIPIO': '1', 'NR_ZONA': '1', 'NR_SECAO': str(i),
             'NR_TURNO': '2', 'lula': l, 'flavio': f, 'valid': l + f} for i, (l, f) in enumerate(votos)]
    # Exterior e outro turno não podem inflar a contagem nacional do segundo turno.
    rows += [{**rows[0], 'SG_UF': 'ZZ', 'lula': 4, 'flavio': 6, 'valid': 10},
             {**rows[0], 'NR_TURNO': '1'}]
    return pl.DataFrame(rows)


def test_contagem_inclusiva_zero_tamanho_percentual_e_exterior():
    r = resumo_secoes(secoes(), '2026')
    b = r['brasil']; c = b['candidatos']['flavio']
    assert b['avaliadas'] == 9 and b['sem_validos_excluidas'] == 1
    assert (c['zero'], c['de_1_a_5'], c['de_6_a_10'], c['ate_10']) == (1, 2, 3, 6)
    assert c['pct_ate_10'] == pytest.approx(6 / 9 * 100)
    assert c['ate_10_e_adversario_acima_90'] == 4
    assert c['ate_10_com_50_mais_validos'] == 5
    assert c['validos_nas_secoes_ate_10'] == {'min': 20, 'mediana': 100.0, 'max': 100}
    assert b['candidatos']['lula']['ate_10'] == 3
    assert b['candidatos']['lula']['acima_90'] == 4  # exatamente 90% fica fora
    assert c['acima_90'] == 1
    assert r['exterior']['avaliadas'] == 1
    assert r['brasil_exterior']['candidatos']['flavio']['ate_10'] == 7
    assert sum(u['candidatos']['flavio']['ate_10'] for u in r['ufs']) == c['ate_10']
    assert r['ufs'][0]['uf'] == 'BA'
    assert 'NR_SECAO' not in json.dumps(r) and 'CD_MUNICIPIO' not in json.dumps(r)
    assert resumo_secoes(secoes(), 2022)['brasil']['candidatos']['flavio']['nome'] == 'Jair Bolsonaro'


def test_recorte_vazio_sem_nan():
    r = resumo_secoes(secoes().filter(pl.col('SG_UF') != 'ZZ'), 2026)
    assert r['exterior']['avaliadas'] == 0
    assert r['exterior']['candidatos']['flavio']['pct_ate_10'] is None
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize('tipo,erro', [('duplicada', 'duplicada'), ('sem_turno', 'ausente'),
                                      ('sem_votos', 'ausente'), ('invalida', 'não fecham')])
def test_recusa_entradas_invalidas(tipo, erro):
    g = secoes()
    if tipo == 'duplicada':
        g = pl.concat([g, g.head(1)])
    elif tipo == 'sem_turno':
        g = g.filter(pl.col('NR_TURNO') == '1')
    elif tipo == 'sem_votos':
        g = g.with_columns(lula=pl.lit(None, dtype=pl.Int64))
    else:
        g = g.with_columns(valid=pl.col('valid') + 1)
    with pytest.raises(ValueError, match=erro):
        resumo_secoes(g, 2026)


def test_cli_registra_contagem_e_hashes(synth_dir, tmp_path):
    cli.main(['distribuicao-secoes', '--dir', str(synth_dir), '--out', str(tmp_path), '--sem-prereg'])
    r = json.loads((tmp_path / 'distribuicao_secoes.json').read_text())
    run = json.loads((tmp_path / 'run_distribuicao-secoes_2026.json').read_text())
    assert set(r['anos']) == {'2022', '2026'} and r['turno'] == 2
    assert run['saidas']['distribuicao_secoes.json'] == _sha(tmp_path / 'distribuicao_secoes.json')
    assert set(run['fechamento_secoes_divergentes']) == {'2022', '2026'}

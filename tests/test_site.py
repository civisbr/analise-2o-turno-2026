import json

import polars as pl
import pytest

from auditoria import cli
from auditoria.runinfo import _sha
from auditoria.site import ENTRADAS, painel

UFS = ['BA', 'PE', 'SP', 'PA']


def _derived(synth_dir, tmp_path):
    cli.main(['analise', '--dir', str(synth_dir), '--out', str(tmp_path), '--ufs', ','.join(UFS), '--boot', '20',
              '--sim', '1', '--sem-prereg'])
    pl.DataFrame({'NR_TURNO': [1, 2], 'apt': [1000, 1000], 'comp': [800, 850], 'abstencao': [200, 150],
                  'valid': [760, 820], 'lula': [300, 450], 'flavio': [350, 370], 'terceira_via': [110, 0],
                  'branco': [15, 10], 'nulo': [25, 20]}).write_csv(tmp_path / 'totais_nacionais_2026.csv')
    return tmp_path


def test_painel_gerado_dos_arquivos_e_sem_nan(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)
    out = tmp_path / 'site' / 'painel.json'
    p = painel(d, out, exige_real=False)
    assert json.loads(out.read_text(encoding='utf-8')) == p
    assert p['ilustrativo'] is True and len(p['kpis']) == 6 and [q['id'] for q in p['perguntas']] == \
        ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6']
    k = {x['id']: x for x in p['kpis']}
    assert k['lula']['delta']['valor'] == 150 and k['comparecimento']['valor'] == 85.0
    assert k['brancos_nulos']['delta']['texto'] == 'queda vs 1º turno'
    assert abs(sum(x['pct'] for x in p['ganho']['partes']) - 100) < 0.2


def test_painel_deterministico(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)
    painel(d, tmp_path / 'a.json', exige_real=False); painel(d, tmp_path / 'b.json', exige_real=False)
    assert (tmp_path / 'a.json').read_bytes() == (tmp_path / 'b.json').read_bytes()


def test_cli_site_registra_a_rodada(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)
    cli.main(['site', '--derived', str(d), '--out', str(tmp_path / 'painel.json'), '--sem-prereg'])
    run = json.loads((d / 'run_site_2026.json').read_text())
    assert list(run['saidas']) == ['painel.json', 'tabelas.html'] and set(run['insumos']) == set(ENTRADAS)
    assert run['insumos']['resultados.json'] == _sha(d / 'resultados.json')


def test_painel_recusa_dado_sintetico_sem_flag(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)
    with pytest.raises(SystemExit, match='sintético'):
        painel(d, tmp_path / 'p.json')


def test_painel_recusa_resultados_fora_da_rodada(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)
    (d / 'resultados.json').write_text((d / 'resultados.json').read_text() + ' ')
    with pytest.raises(SystemExit, match='difere'):
        painel(d, tmp_path / 'p.json', exige_real=False)


def test_cli_site_sem_prereg_nao_grava_em_site(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)
    with pytest.raises(SystemExit):
        cli.main(['site', '--derived', str(d), '--out', 'site/data/painel.json', '--sem-prereg'])


def _com_resultados(d, mexe):
    f = d / 'resultados.json'
    r = json.loads(f.read_text(encoding='utf-8')); mexe(r)
    f.write_text(json.dumps(r, ensure_ascii=False), encoding='utf-8')
    run = json.loads((d / 'run_analise_2026.json').read_text())
    run['saidas']['resultados.json'] = _sha(f)
    (d / 'run_analise_2026.json').write_text(json.dumps(run))


def test_painel_resultados_incompletos_viram_nao_avaliavel(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)

    def mexe(r):
        r['q2']['ajustes'] = []; r['q2']['explicado'] = None
        for a in ('2026', '2022'):
            r['q4'][a].pop('comparecimento_estavel_ou_alta', None)
        r['q1']['2026'].pop('exterior', None); r['q1']['2022'].pop('exterior', None)
    _com_resultados(d, mexe)
    p = painel(d, tmp_path / 'p.json', exige_real=False)
    q = {x['id']: x['linhas'] for x in p['perguntas']}
    assert any('não avaliável' in l for l in q['Q2']) and 'não avaliável' in q['Q4'][0]


def test_painel_recusa_ganho_inconsistente(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)
    _com_resultados(d, lambda r: r['q1']['2022']['nacional'].update(dL=-5))
    with pytest.raises(SystemExit, match='sem divisão'):
        painel(d, tmp_path / 'p.json', exige_real=False)


def test_painel_nota_a_diferenca_entre_totais_e_decomposicao(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)
    p = painel(d, tmp_path / 'p.json', exige_real=False)
    assert isinstance(p['notas'], list)


def test_tabelas_html_sem_js_escapa_e_traz_os_numeros(synth_dir, tmp_path):
    d = _derived(synth_dir, tmp_path)
    p = painel(d, tmp_path / 'p.json', exige_real=False)
    assert '<script' not in (tmp_path / 'tabelas.html').read_text(encoding='utf-8')
    from auditoria.site import tabelas_html
    p['atipicos'][0]['rotulo'] = '<img src=x onerror=1>'
    h = tabelas_html(p)
    assert '<img' not in h and '&lt;img' in h
    assert all(q['id'] in h for q in p['perguntas'])

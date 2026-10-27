import json

import numpy as np
import pytest

from auditoria import analise as an
from auditoria.analise import benjamini_hochberg, p_bicaudal, prepara
from synth import UFS


@pytest.fixture(scope='module')
def res(synth_dir, tmp_path_factory):
    out = tmp_path_factory.mktemp('out')
    r = an.analise(synth_dir, out, 2026, 2022, UFS, min_valid=200, boot=60, n_sim=3)
    return r, out


def test_benjamini_hochberg_controla_e_ordena():
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216])
    sel = benjamini_hochberg(p, 0.05)
    assert sel.tolist() == [True, True] + [False] * 8
    assert not benjamini_hochberg(np.array([0.2, 0.5, 0.9])).any()


def test_p_bicaudal_normal():
    assert p_bicaudal(np.array([0.0, 1.96]))[0] == pytest.approx(1.0)
    assert p_bicaudal(np.array([1.96]))[0] == pytest.approx(0.05, abs=1e-3)


def test_q1_identidade_fecha_e_decompoe(res):
    q1 = res[0]['q1']['2026']
    assert q1['identidade_residuo'] == 0
    n = q1['nacional']
    assert n['dL'] + n['dF'] == n['pool'] + n['dvalid']
    assert n['dvalid'] == n['dcomparecimento'] + n['queda_brancos_nulos']
    assert set(q1['por_uf']) == set(UFS)


def test_q2_diferenca_de_alfa_e_estrutura(res):
    aj = res[0]['q2']['ajustes']
    assert {(a['modelo'], a['efeito_fixo'], a['refit_robusto']) for a in aj} == \
        {(m, fe, r) for m in 'ABC' for fe in (True, False) for r in (False, True)}
    a = next(x for x in aj if x['modelo'] == 'A' and x['efeito_fixo'] and not x['refit_robusto'])['coef']['alpha']
    assert a['2022'] == pytest.approx(0.53, abs=0.04)
    assert a['dif'] == pytest.approx(a['2026'] - a['2022'])
    assert a['ic_dif'][0] <= a['dif'] <= a['ic_dif'][1]
    robusto = next(x for x in aj if x['modelo'] == 'A' and x['efeito_fixo'] and x['refit_robusto'])
    assert robusto['n_2026'] < next(x for x in aj if x['modelo'] == 'A' and x['efeito_fixo'] and not x['refit_robusto'])['n_2026']


def test_q3_recupera_municipios_plantados(res):
    q3 = res[0]['q3']['2026']
    assert {x['mun'] for x in q3['lista_publicavel']} >= {'BA-00003', 'BA-00007', 'BA-00011'}
    assert q3['sinalizados_nos_dois'] <= min(q3['sinalizados_q05_ajuste_cheio'], q3['sinalizados_q05_refit_robusto'])
    assert q3['esperado_p05_por_acaso'] == pytest.approx(0.05 * q3['testados'])
    assert q3['observado_p05'] >= q3['sinalizados_nos_dois']
    assert res[0]['q3']['2022']['testados'] > 0 and res[0]['q4']['2022']['elegiveis'] > 0


def test_q3_sem_plantio_nao_sinaliza_o_plantado(wide26_noplant):
    q3 = an.q3(prepara(wide26_noplant, 200), {m: 50 for m in prepara(wide26_noplant, 200).mun})
    assert not {x['mun'] for x in q3['lista_publicavel']} & {'BA-00003', 'BA-00007', 'BA-00011'}


def test_q3_nao_lista_municipio_com_poucas_secoes(wide26):
    m = prepara(wide26, 200)
    q3 = an.q3(m, {x: 3 for x in m.mun})
    assert q3['lista_publicavel'] == [] and q3['sinalizados_nos_dois'] > 0


def test_q4_contagens_fecham(res):
    q4 = res[0]['q4']['2026']
    assert q4['comparecimento_em_queda'] + q4['comparecimento_estavel_ou_alta'] == q4['com_queda_de_flavio']


def test_q5_estrutura_e_ordem(res):
    q5 = res[0]['q5']
    assert set(q5['por_uf_2026']) == set(UFS) and q5['simulacoes'] == 3
    assert q5['esperado_normal_teorico'] == pytest.approx(6.33e-5, rel=1e-2)
    assert 0 <= q5['fracao_2026'] <= 1 and q5['kappa_2026'] > 0


def test_sensibilidade_cobre_a_grade(res):
    s = res[0]['sensibilidade']['ajustes']
    assert {x['min_valid'] for x in s} == {100, 200, 500}
    assert {x['regiao'] for x in s} >= {'todas'}


def test_q6_registrada_como_nao_testavel(res):
    assert res[0]['q6']['testavel'] is False


def test_json_deterministico(synth_dir, tmp_path, res):
    an.analise(synth_dir, tmp_path, 2026, 2022, UFS, min_valid=200, boot=60, n_sim=3)
    assert (tmp_path / 'resultados.json').read_text() == (res[1] / 'resultados.json').read_text()
    json.loads((tmp_path / 'resultados.json').read_text())


def test_cli_analise_exige_prereg_para_dado_real(tmp_path):
    from auditoria import cli
    (tmp_path / 'MANIFEST.json').write_text('{}')
    with pytest.raises(SystemExit):
        cli.main(['analise', '--dir', str(tmp_path), '--sem-prereg'])


def test_cli_analise_sem_tag_encerra(tmp_path, monkeypatch):
    from auditoria import cli
    def sem_tag():
        raise SystemExit('tag prereg-v1 ausente')
    monkeypatch.setattr(cli, 'exige_prereg', sem_tag)
    with pytest.raises(SystemExit, match='prereg-v1'):
        cli.main(['analise', '--dir', str(tmp_path), '--out', str(tmp_path / 'o')])


def test_sem_prereg_recusa_data_derived(tmp_path):
    from auditoria import cli
    with pytest.raises(SystemExit):
        cli.main(['analise', '--dir', str(tmp_path), '--out', 'data/derived', '--sem-prereg'])


def test_run_registra_resultados_json(synth_dir, tmp_path):
    import os
    from auditoria import cli
    cli.main(['analise', '--dir', str(synth_dir), '--out', str(tmp_path), '--ufs', ','.join(UFS), '--boot', '20',
              '--sim', '1', '--sem-prereg'])
    run = json.loads((tmp_path / 'run_analise_2026.json').read_text())
    assert list(run['saidas']) == ['resultados.json'] and set(run['semente']) == \
        {'bootstrap_2026', 'bootstrap_2022', 'simulacao_q5'}


def test_explicado_metade_ou_ic_com_zero():
    def aj(modelo, dif, ic):
        return {'modelo': modelo, 'efeito_fixo': True, 'refit_robusto': False, 'coef': {'alpha': {'dif': dif, 'ic_dif': ic}}}
    assert an._explicado([aj('A', .10, [.05, .15]), aj('C', .04, [.01, .07])])['explicado']
    assert an._explicado([aj('A', .10, [.05, .15]), aj('C', .08, [-.01, .17])])['explicado']
    assert not an._explicado([aj('A', .10, [.05, .15]), aj('C', .08, [.02, .14])])['explicado']
    assert an._explicado([aj('A', .10, [.05, .15])]) is None


def test_sem_comparecimento_cai_para_modelo_a(wide22):
    m = prepara(wide22.assign(comp1=float('nan'), comp2=float('nan')), 200)
    z = an.z_residuos(m)
    assert np.isfinite(z).all()


def test_exterior_fica_fora_de_q2_a_q5_e_aparece_em_q1(wide22):
    ext = wide22[wide22.SG_UF == 'BA'].assign(SG_UF='ZZ')
    w = __import__('pandas').concat([wide22, ext])
    assert 'ZZ' not in set(prepara(w, 200).SG_UF)
    q = an.q1(w, 2022)
    assert 'exterior' in q and 'ZZ' not in q['por_uf']
    assert q['identidade_residuo'] == 0


def test_bh_com_empates_e_p_unico():
    assert benjamini_hochberg(np.array([0.01, 0.01, 0.01, 0.9])).tolist() == [True, True, True, False]
    assert benjamini_hochberg(np.array([0.04])).tolist() == [True]

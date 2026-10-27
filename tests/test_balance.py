import contextlib
import io

import numpy as np
import pandas as pd
import pytest

from auditoria.balance import add_flows, balance, identity_gap, muni_table


def run_balance(wide, label, out):
    with contextlib.redirect_stdout(io.StringIO()):
        return balance(wide, label, out, min_valid=200, boot=50)


def with_flows(wide):
    return add_flows(muni_table(wide))


@pytest.mark.parametrize('fixture', ['wide26', 'wide22'])
def test_identidade_contabil(fixture, request):
    assert identity_gap(with_flows(request.getfixturevalue(fixture))) == 0


def test_controle_sem_anomalia_recupera_coeficientes(wide22, tmp_path):
    res = run_balance(wide22, '2022 (controle)', tmp_path)
    a, b = res[('A', True)]
    assert a == pytest.approx(0.53, abs=0.03)   # a + b·o = .45 + .40·.20
    assert b == pytest.approx(0.40, abs=0.03)


def test_sem_plantio_recupera_coeficientes(wide26_noplant, tmp_path):
    a, b = run_balance(wide26_noplant, '2026 (principal)', tmp_path)[('A', True)]
    assert a == pytest.approx(0.495, abs=0.04)   # a + b·o = .30 + .65·.30
    assert b == pytest.approx(0.65, abs=0.04)


def test_outliers_plantados_deslocam_o_ajuste_e_aparecem_no_topo(wide26, wide26_noplant, tmp_path):
    (tmp_path / 'sem').mkdir(); (tmp_path / 'com').mkdir()
    base = run_balance(wide26_noplant, '2026 (principal)', tmp_path / 'sem')[('A', True)]
    plant = run_balance(wide26, '2026 (principal)', tmp_path / 'com')[('A', True)]
    # o sentido do viés depende de quais municípios recebem o plantio; só o deslocamento é estável
    assert np.abs(plant - base).max() > 0.03
    m = pd.read_csv(tmp_path / 'com' / 'balanco_municipios_2026.csv')
    top3 = set(m.sort_values('z_resid', ascending=False).head(3).mun)
    assert top3 == {'BA-00003', 'BA-00007', 'BA-00011'}
    assert m.z_resid.max() > 10


def test_resultado_sem_comparecimento_nao_quebra(wide22, tmp_path):
    w = wide22.assign(comp1=float('nan'), comp2=float('nan'))
    res = run_balance(w, '2022 (controle)', tmp_path)
    assert {k[0] for k in res} == {'A'}


def test_identidade_quebrada_para_o_pipeline(wide22, tmp_path):
    w = wide22.assign(lula2=wide22.lula2 + 5)   # votos de candidato sem válidos correspondentes
    with pytest.raises(SystemExit, match='identidade'):
        run_balance(w, '2022 (controle)', tmp_path)


def test_csv_municipal_omite_municipio_com_poucas_secoes(wide26_noplant, tmp_path):
    w = wide26_noplant
    pequeno = w[(w.SG_UF == 'SP') & (w.CD_MUNICIPIO == '00005')].index[5:]
    run_balance(w.drop(index=pequeno), '2026 (principal)', tmp_path)
    m = pd.read_csv(tmp_path / 'balanco_municipios_2026.csv')
    assert 'SP-00005' not in set(m.mun) and 'SP-00006' in set(m.mun)

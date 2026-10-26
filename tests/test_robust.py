import numpy as np
import pytest

from auditoria.robust import mad_sigma, wls


def test_mad_sigma_equivale_ao_dp_sob_normalidade():
    x = np.random.default_rng(0).normal(0, 3, 100_000)
    assert mad_sigma(x) == pytest.approx(3, rel=0.02)


def test_mad_sigma_ignora_outliers():
    x = np.concatenate([np.random.default_rng(0).normal(0, 1, 1000), [1e6] * 10])
    assert mad_sigma(x) < 1.2


def test_wls_recupera_coeficientes_sem_e_com_efeito_fixo():
    rng = np.random.default_rng(1)
    n = 500
    g = rng.integers(0, 4, n)
    X = rng.normal(size=(n, 2))
    w = rng.uniform(1, 5, n)
    y = 0.3 * X[:, 0] + 0.7 * X[:, 1] + g * 10.0 + rng.normal(0, 0.01, n)
    assert wls(y, X, w, g) == pytest.approx([0.3, 0.7], abs=0.01)
    y0 = 0.3 * X[:, 0] + 0.7 * X[:, 1] + 5 + rng.normal(0, 0.01, n)
    assert wls(y0, X, w) == pytest.approx([0.3, 0.7], abs=0.01)

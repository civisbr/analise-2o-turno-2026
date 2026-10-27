import numpy as np

BOOT_SEED = 11      # bootstrap do balanço
CLOSING_SEED = 1    # bootstrap e permutação do teste de fechamento


def mad_sigma(x):
    """Desvio-padrão robusto (MAD escalado para equivaler ao dp sob normalidade)."""
    return 1.4826 * np.median(np.abs(x - np.median(x)))


def wls(y, X, w, g=None):
    """Mínimos quadrados ponderados; com g, remove efeito fixo por grupo (demean ponderado).
    Retorna só os coeficientes das colunas de X."""
    if g is not None:
        y = y.copy(); X = X.copy(); y0, X0 = y.copy(), X.copy()
        for k in np.unique(g):
            m = g == k; ww = w[m] / w[m].sum()
            y[m] = y0[m] - ww @ y0[m]; X[m] = X0[m] - ww @ X0[m]
    else:
        X = np.column_stack([np.ones(len(y)), X])
    sw = np.sqrt(w)
    beta = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0]
    return beta if g is not None else beta[1:]


def boot_draws(y, X, w, g, B, seed):
    rng = np.random.default_rng(seed); n = len(y); bs = []
    for _ in range(B):
        i = rng.integers(0, n, n)
        bs.append(wls(y[i], X[i], w[i], None if g is None else g[i]))
    return np.array(bs)


def boot_ci(y, X, w, g, B, seed):
    return np.percentile(boot_draws(y, X, w, g, B, seed), [2.5, 97.5], axis=0)

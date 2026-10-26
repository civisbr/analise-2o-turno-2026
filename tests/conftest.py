import pytest

from auditoria.load import load_year
from synth import UFS, make_default, make_noplant


@pytest.fixture(scope='session')
def synth_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp('synth')
    make_default(d)
    return d


@pytest.fixture(scope='session')
def wide26(synth_dir):
    return load_year(synth_dir, 2026, UFS)


@pytest.fixture(scope='session')
def wide22(synth_dir):
    return load_year(synth_dir, 2022, UFS)


@pytest.fixture(scope='session')
def wide26_noplant(tmp_path_factory):
    d = tmp_path_factory.mktemp('synth_noplant')
    make_noplant(d)
    return load_year(d, 2026, UFS)

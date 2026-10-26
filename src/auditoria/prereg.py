import subprocess
import sys

from .runinfo import ROOT


def exige_prereg():
    def git(*args):
        return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True).returncode == 0

    if not (git('rev-parse', '-q', '--verify', 'refs/tags/prereg-v1')
            and git('diff', '--quiet', 'prereg-v1', '--', 'docs/pre-registro.md')):
        sys.exit('tag prereg-v1 ausente ou pre-registro.md alterado depois dela: congele '
                 'docs/pre-registro.md antes de analisar dados reais '
                 '(--sem-prereg para dados sintéticos; o uso fica registrado na saída)')

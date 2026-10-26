import argparse
import pathlib
import subprocess
import sys

from .balance import balanco
from .download import download
from .load import resolve_ufs
from .swing import analyze


def year_arg(s):
    if not (s.isdigit() and len(s) == 4):
        raise argparse.ArgumentTypeError(f'ano inválido: {s}')
    return s


def exige_prereg():
    def git(*args):
        return subprocess.run(['git', *args], capture_output=True).returncode == 0

    if not (git('rev-parse', '-q', '--verify', 'refs/tags/prereg-v1')
            and git('diff', '--quiet', 'prereg-v1', '--', 'docs/pre-registro.md')):
        sys.exit('tag prereg-v1 ausente ou pre-registro.md alterado depois dela: congele docs/pre-registro.md antes de analisar dados reais '
                 '(--sem-prereg para dados sintéticos; o uso fica registrado na saída)')


def main(argv=None):
    p = argparse.ArgumentParser(prog='auditoria'); sp = p.add_subparsers(dest='cmd', required=True)
    d = sp.add_parser('download'); d.add_argument('--year', default='2026', type=year_arg); d.add_argument('--dir', default='data/raw')
    z = sp.add_parser('analyze'); z.add_argument('--dir', default='data/raw'); z.add_argument('--out', default='data/derived')
    z.add_argument('--year', default='2026', type=year_arg); z.add_argument('--control-year', type=year_arg); z.add_argument('--closing')
    z.add_argument('--private-dir', default='data/private', help='saída por seção; nunca versionar')
    z.add_argument('--ufs', default='NE', help='NE | ALL | AL,BA,...')
    b = sp.add_parser('balanco', help='balanço de votos entre turnos por município (de onde veio o ganho de Lula)')
    b.add_argument('--dir', default='data/raw'); b.add_argument('--out', default='data/derived')
    b.add_argument('--year', default='2026', type=year_arg); b.add_argument('--control-year', default='2022', type=year_arg)
    b.add_argument('--ufs', default='ALL', help='NE | ALL | AL,BA,... (padrão ALL: a pergunta é nacional)')
    b.add_argument('--boot', type=int, default=300); b.add_argument('--min-valid', type=int, default=200)
    for sub_ in (z, b):
        sub_.add_argument('--sem-prereg', action='store_true', help='só para dados sintéticos')
    a = p.parse_args(argv)
    if a.cmd != 'download':
        if a.sem_prereg:
            print('[aviso] --sem-prereg: pré-registro não verificado; resultado não vale como análise registrada')
        else:
            exige_prereg()
    ufs = resolve_ufs(a.ufs)
    if a.cmd == 'analyze' and pathlib.Path(a.private_dir).resolve().is_relative_to(pathlib.Path(a.out).resolve()):
        p.error('--private-dir não pode ficar dentro de --out (saída por seção não é versionável)')
    if a.cmd == 'download':
        download(a.dir, a.year)
    elif a.cmd == 'analyze':
        analyze(a.dir, a.out, a.year, a.control_year, ufs, a.closing, a.private_dir)
    else:
        balanco(a.dir, a.out, a.year, a.control_year, ufs, a.min_valid, a.boot)


if __name__ == '__main__':
    main()

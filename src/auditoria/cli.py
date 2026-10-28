import argparse
import pathlib
import sys

from .analise import analise
from .balance import balanco
from .build import build
from .download import download
from .load import resolve_ufs
from .site import entradas, painel
from .prereg import exige_prereg
from .runinfo import confere_insumos, write_run
from .swing import analyze
from .verify import verify


def year_arg(s):
    if not (s.isdigit() and len(s) == 4):
        raise argparse.ArgumentTypeError(f'ano inválido: {s}')
    return s


def intervalo(lo, hi):
    def f(s):
        if not (s.isdigit() and lo <= int(s) <= hi):
            raise argparse.ArgumentTypeError(f'valor fora de {lo}–{hi}: {s}')
        return int(s)
    return f


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
    n = sp.add_parser('analise', help='Q1–Q5 do pré-registro em resultados.json (lido pela página)')
    n.add_argument('--dir', default='data/raw'); n.add_argument('--out', default='data/derived')
    n.add_argument('--year', default='2026', type=year_arg); n.add_argument('--control-year', default='2022', type=year_arg)
    n.add_argument('--ufs', default='ALL'); n.add_argument('--min-valid', type=int, default=200)
    n.add_argument('--boot', type=intervalo(20, 20000), default=2000); n.add_argument('--sim', type=intervalo(1, 1000), default=20)
    st = sp.add_parser('site', help='gera site/data/painel.json a partir de data/derived')
    st.add_argument('--derived', default='data/derived'); st.add_argument('--out', default='site/data/painel.json')
    st.add_argument('--sem-prereg', action='store_true', help='só para dados sintéticos; marca o painel como ilustrativo')
    v = sp.add_parser('verify', help='fecha votação x detalhe por seção e grava totais nacionais e por UF')
    v.add_argument('--dir', default='data/raw'); v.add_argument('--out', default='data/derived')
    v.add_argument('--year', default='2026', type=year_arg)
    bd = sp.add_parser('build', help='fecha as fontes, grava seções em Parquet (privado) e a tabela municipal')
    bd.add_argument('--dir', default='data/raw'); bd.add_argument('--out', default='data/derived')
    bd.add_argument('--private-dir', default='data/private', help='saída por seção; nunca versionar')
    bd.add_argument('--year', default='2026', type=year_arg)
    for sub_ in (z, b, n, v, bd):
        sub_.add_argument('--sem-prereg', action='store_true', help='só para dados sintéticos')
    a = p.parse_args(argv)
    if a.cmd in ('analyze', 'balanco', 'analise', 'verify', 'build'):
        if a.sem_prereg and (pathlib.Path(a.dir) / 'MANIFEST.json').exists():
            p.error('--sem-prereg não vale para dados reais (há MANIFEST.json em --dir)')
        if a.sem_prereg and pathlib.Path(a.out).resolve() == pathlib.Path('data/derived').resolve():
            p.error('--sem-prereg não pode gravar em data/derived (versionado); use outro --out')
        if a.sem_prereg:
            print('[aviso] --sem-prereg: pré-registro não verificado; resultado não vale como análise registrada')
        elif a.cmd in ('analyze', 'balanco', 'analise'):
            exige_prereg()   # verify só exige quando há 2º turno de 2026 nos dados
    insumos = confere_insumos(a.dir) if a.cmd not in ('download', 'site') else None
    extra = {}
    ufs = resolve_ufs(a.ufs) if a.cmd in ('analyze', 'balanco', 'analise') else None
    if a.cmd in ('analyze', 'build') and pathlib.Path(a.private_dir).resolve().is_relative_to(pathlib.Path(a.out).resolve()):
        p.error('--private-dir não pode ficar dentro de --out (saída por seção não é versionável)')
    if a.cmd == 'download':
        download(a.dir, a.year)
    elif a.cmd == 'build':
        extra = build(a.dir, a.out, a.private_dir, a.year, exige=not a.sem_prereg)
    elif a.cmd == 'verify':
        extra = verify(a.dir, a.out, a.year, exige=not a.sem_prereg)
    elif a.cmd == 'analyze':
        analyze(a.dir, a.out, a.year, a.control_year, ufs, a.closing, a.private_dir)
    elif a.cmd == 'site':
        if a.sem_prereg and pathlib.Path(a.out).resolve().is_relative_to(pathlib.Path('site').resolve()):
            p.error('--sem-prereg não pode gravar em site/ (publicado); use outro --out')
        painel(a.derived, a.out, exige_real=not a.sem_prereg)
        insumos = entradas(a.derived)
        extra = {'arquivos': [a.out]}
    elif a.cmd == 'analise':
        analise(a.dir, a.out, a.year, a.control_year, ufs, a.min_valid, a.boot, a.sim)
        extra = {'arquivos': [pathlib.Path(a.out) / 'resultados.json']}
    else:
        balanco(a.dir, a.out, a.year, a.control_year, ufs, a.min_valid, a.boot)
    if a.cmd == 'site':
        write_run('site', 2026, sys.argv[1:] if argv is None else argv, a.derived, insumos, **extra)
    elif a.cmd != 'download':
        write_run(a.cmd, a.year, sys.argv[1:] if argv is None else argv, a.out, insumos, **extra)


if __name__ == '__main__':
    main()

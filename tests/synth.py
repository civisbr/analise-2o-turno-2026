"""Dados sintéticos com fluxos de eleitores conhecidos, para validar o módulo de balanço.

Parâmetros de make(): a, f = fração da terceira via que vai para Lula e Flávio (o resto vai para
"outros"); b = fração dos votantes novos que vai para Lula. Teórico: alpha = a + b·(1−a−f).
"""
import pathlib
import zipfile

import numpy as np
import pandas as pd


def make(outdir, year, ufs, a, f, b, plant, seed):
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed); o = 1 - a - f
    V = []; T = []
    for uf in ufs:
        ufshift = rng.normal(0, .05)
        for m in range(1, 41):
            base = np.clip(rng.uniform(.3, .7) + ufshift, .1, .9); dt = rng.normal(.02, .02); qm = rng.uniform(.03, .14)
            plant_m = plant and uf == 'BA' and m in (3, 7, 11)
            for s in range(1, rng.integers(30, 110)):
                apt = int(rng.integers(250, 420)); t1 = rng.uniform(.74, .88); comp1 = int(apt * t1)
                bn1 = int(comp1 * .048); valid1 = comp1 - bn1; pool = int(valid1 * np.clip(qm + rng.normal(0, .005), .01, .2))
                two = valid1 - pool; sec = np.clip(base + rng.normal(0, .03), .05, .95)
                L1 = rng.binomial(two, sec); F1 = two - L1
                comp2 = int(apt * np.clip(t1 + dt + rng.normal(0, .01), .5, .98)); bn2 = int(comp2 * .032); valid2 = comp2 - bn2
                PL, PF, PO = rng.multinomial(pool, [a, f, o])
                dropL = rng.binomial(L1, .01); dropF = rng.binomial(F1, .01)
                swFL = rng.binomial(F1 - dropF, .01); swLF = rng.binomial(L1 - dropL, .005)
                stayL = L1 - dropL - swLF + swFL; stayF = F1 - dropF - swFL + swLF
                Nnew = max(valid2 - (stayL + stayF + PL + PF), 0)
                NL = rng.binomial(Nnew, b); NF = Nnew - NL
                L2 = stayL + PL + NL; F2 = stayF + PF + NF
                if plant_m:   # troca direta Flávio→Lula, sem mudança de comparecimento
                    x = int(F2 * .25); L2 += x; F2 -= x
                valid2 = L2 + F2; comp2 = valid2 + bn2
                for turno, (L, F, oth, vv, cc, bn) in ((1, (L1, F1, pool, valid1, comp1, bn1)), (2, (L2, F2, 0, valid2, comp2, bn2))):
                    k = dict(NR_TURNO=str(turno), CD_CARGO='1', SG_UF=uf, CD_MUNICIPIO=f'{m:05d}', NR_ZONA='1', NR_SECAO=str(s))
                    V += [dict(k, NR_VOTAVEL=13, QT_VOTOS=L), dict(k, NR_VOTAVEL=22, QT_VOTOS=F), dict(k, NR_VOTAVEL=15, QT_VOTOS=oth),
                          dict(k, NR_VOTAVEL=95, QT_VOTOS=bn // 3), dict(k, NR_VOTAVEL=96, QT_VOTOS=bn - bn // 3)]
                    T.append(dict(k, QT_APTOS=apt, QT_COMPARECIMENTO=cc))
                    # isca: outro cargo na mesma seção, que o carregamento deve ignorar
                    V.append(dict(k, CD_CARGO='3', NR_VOTAVEL=13, QT_VOTOS=7777))
                    T.append(dict(k, CD_CARGO='3', QT_APTOS=9, QT_COMPARECIMENTO=9))
    # layout real do TSE: Presidente de todas as UFs no membro _BR; o detalhe é um zip nacional único
    for name, member, rows in ((f'votacao_secao_{year}_BR.zip', f'votacao_secao_{year}_BR.csv', V),
                               (f'detalhe_votacao_secao_{year}.zip', f'detalhe_votacao_secao_{year}_BR.csv', T)):
        df = pd.DataFrame(rows).astype(str)
        with zipfile.ZipFile(outdir / name, 'w') as z:
            z.writestr(member, df.to_csv(sep=';', index=False).encode('latin1'))
            z.writestr('leiame.pdf', b'%PDF-')


UFS = ['BA', 'PE', 'SP', 'PA']


def make_noplant(outdir):
    make(outdir, 2026, UFS, .30, .40, .65, False, 1)


def make_default(outdir):
    make(outdir, 2026, UFS, .30, .40, .65, True, 1)    # alpha teórico = .30 + .65·.30 = .495
    make(outdir, 2022, UFS, .45, .35, .40, False, 2)   # controle: alpha = .45 + .40·.20 = .53

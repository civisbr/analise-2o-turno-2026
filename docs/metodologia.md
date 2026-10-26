# Metodologia

Decisões não óbvias, em ordem cronológica. Hipóteses e limiares estão em [`pre-registro.md`](pre-registro.md).

## Layout dos arquivos do TSE (verificado em 26/10/2026)

Base: `https://cdn.tse.jus.br/estatistica/sead/odsele/`. O layout é o mesmo em 2022 e 2026.

- `votacao_secao/votacao_secao_<ano>_BR.zip`: o cargo Presidente de **todas** as UFs fica no membro `votacao_secao_<ano>_BR.csv` (`CD_CARGO` 1, `SG_UF` é a UF real da seção). Os zips `votacao_secao_<ano>_<UF>.zip` só têm cargos estaduais (3, 5, 6, 7).
- `detalhe_votacao_secao/detalhe_votacao_secao_<ano>.zip`: arquivo **nacional único**, com um membro por UF mais `_BR.csv` (Presidente) e `_BRASIL.csv`. Não existe `detalhe_votacao_secao_<ano>_<UF>.zip` (404).
- Em 26/10/2026 os arquivos de 2026 foram gerados em 05–07/10 e só têm o 1º turno. O 2º turno não estava publicado.
- `ZZ` (exterior) aparece nos dois arquivos e fica fora do conjunto `ALL` até a Fase 2.

## Votos válidos

`QT_VOTOS` por candidato em `votacao_secao` inclui votos que o TSE contabiliza como **nulos** (votos anulados). No 1º turno o candidato nº 28 tem 5.246 votos nessa condição: ao somar 95 e 96 como únicos não válidos, `valid` fica 5.246 acima do total oficial (119.306.034 contra 119.300.788) e os nulos 5.246 abaixo (3.669.003 contra 3.674.249). Lula, Flávio e brancos fecham exatamente com o baseline e os outros 10 candidatos somam 9.316.747 depois de retirados esses 5.246 votos (o arquivo bruto soma 9.321.993 para os 11). **Pendente na Fase 1:** definir `valid` a partir do total oficial (`detalhe_votacao_secao`, `QT_VOTOS_NOMINAIS`) e testar o fechamento por UF.

## Hora de encerramento por seção (Q6)

Nenhuma coluna de `votacao_secao` ou `detalhe_votacao_secao` traz a hora de encerramento da seção. O detalhe traz `DT_RECEBIMENTO_BU_HOR_TSE` (recebimento do boletim de urna no TSE) e `DT_PRIM_TOT_PARCIAL_HOR_TSE`, que dependem da transmissão e não medem o fechamento. A hora de encerramento consta do boletim de urna (arquivos de urna em `resultados.tse.jus.br`), ainda não avaliado. Decisão sobre Q6: ver pré-registro.

## Saída por seção

Tabelas por seção são gravadas em `data/private/` (fora do git). Em `data/derived/` entram só agregados municipais e por UF.

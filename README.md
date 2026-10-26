<p align="center">
  <img src="site/assets/logo.png" alt="Auditoria Pública – 2º turno 2026" width="320">
</p>

# Auditoria pública do 2º turno 2026

Pipeline reproduzível sobre dados abertos do TSE que mede, com números, o que mudou entre o 1º e o 2º turno da eleição presidencial de 2026, e uma página pública para qualquer pessoa conferir.

> **Projeto independente. Dados: TSE. Não é uma fonte oficial.**
> **Versão preliminar:** em revisão externa. Os dados agregados não identificam o comportamento de eleitores individuais, e um padrão atípico não é prova de irregularidade.

## Princípios

- Publica o que os dados mostram, seja o que for; resultados negativos têm o mesmo destaque dos positivos.
- Método [pré-registrado](docs/pre-registro.md) (rascunho até a tag `prereg-v1`) antes de qualquer análise dos dados reais; mudanças entram como [errata](docs/erratas.md).
- Todo número da página é gerado por código a partir de `data/derived/`.
- Granularidade pública: município. Nenhuma lista de seções, zonas ou locais de votação.
- Controle histórico (2022) em toda análise.

## Reproduzir

```bash
make setup      # venv + dependências
make test       # testes com dados sintéticos, sem rede
make data       # baixa os arquivos do TSE, fecha as fontes e gera data/derived (2022) e data/private
make analysis   # exige a tag prereg-v1 (pré-registro congelado)
```

A CLI também roda direto: `python -m auditoria {download,analyze,balanco}`. `analyze` e `balanco` também exigem a tag; `--sem-prereg` existe só para dados sintéticos e fica avisado na saída.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `src/auditoria/` | carga dos dados, balanço de votos, swing por seção, teste de fechamento |
| `tests/` | testes com fixtures sintéticas de fluxo de eleitores conhecido |
| `docs/` | pré-registro, metodologia, erratas, fontes divergentes |
| `site/` | página pública estática e `site/assets/` (logo) |
| `data/derived/` | tabelas derivadas versionadas (municípios e UFs) |

## Licença

Código: [MIT](LICENSE). Dados derivados e textos: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), com atribuição ao TSE como fonte primária dos dados.

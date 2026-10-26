VENV := .venv
PY   := $(VENV)/bin/python
RAW  := data/raw
OUT  := data/derived

.PHONY: setup test data analysis site verify all guard-prereg

setup:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/pip install -e .

test:
	$(PY) -m pytest -q

data:
	$(PY) -m auditoria download --year 2026 --dir $(RAW)
	$(PY) -m auditoria download --year 2022 --dir $(RAW)

# Nenhuma análise sobre dados reais antes do pré-registro (project.md, seção 1, regra 1).
# O pré-registro só vale congelado: tag prereg-v1 criada depois do commit e da revisão.
guard-prereg:
	@git rev-parse -q --verify refs/tags/prereg-v1 >/dev/null && git diff --quiet prereg-v1 -- docs/pre-registro.md || { echo "tag prereg-v1 ausente ou pre-registro.md alterado depois dela: congele docs/pre-registro.md antes de analisar dados reais"; exit 1; }

analysis: guard-prereg
	$(PY) -m auditoria balanco --dir $(RAW) --out $(OUT) --year 2026 --control-year 2022 --ufs ALL --boot 2000
	$(PY) -m auditoria analyze --dir $(RAW) --out $(OUT) --year 2026 --control-year 2022 --ufs ALL

site:
	@echo "não implementado (Fase 5)"; exit 1

verify:
	$(PY) -m auditoria verify --dir $(RAW) --out $(OUT) --year 2026
	$(PY) -m auditoria verify --dir $(RAW) --out $(OUT) --year 2022

all: data analysis site verify

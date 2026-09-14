#!/bin/bash
# E2E do painel: o percurso mora em tests/e2e/painel.py (o mesmo para o navegador do gstack e para o Playwright).
#
#   tests/e2e/painel.sh                          navegador headless do gstack (browse), na máquina
#   tests/e2e/painel.sh --navegador playwright   Playwright (requirements-e2e.txt + playwright install chromium)
set -eu
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/painel.py" "$@"

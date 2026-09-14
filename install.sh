#!/bin/bash
# install.sh: acha um python3 >= 3.9 (prefere o mais novo; no macOS, o /usr/bin/python3 da Apple só com Xcode CLT)
# e entrega tudo para scripts/instalar.py (instalação, --check, --update, --uninstall). macOS ou Linux.
#
#   ./install.sh                         instala a partir deste clone em ~/.goal-pacer
#   ./install.sh --from ./ --copiar      copia a árvore de trabalho (desenvolvimento)
#   ./install.sh --check | --update | --uninstall [--apagar-blocos] [--apagar-cache]
#   ./install.sh --help
set -u

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
XCODE_SELECT="${GP_XCODE_SELECT:-/usr/bin/xcode-select}"
case "${GP_PLATAFORMA:-$(uname -s)}" in
  macos|Darwin) MACOS=1 ;;
  *) MACOS=0 ;;
esac

versao_ok() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)' >/dev/null 2>&1
}

versao_de() {
  "$1" -c 'import sys; print("%d %03d %03d" % sys.version_info[:3])' 2>/dev/null
}

escolher_python() {
  local candidatos=() caminho nome fixo py v melhor=""
  escolhido=""
  if [ -n "${GP_PYTHON3:-}" ]; then
    candidatos+=("$GP_PYTHON3")  # escolha explícita: só ele é considerado
  else
    for nome in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
      caminho="$(command -v "$nome" 2>/dev/null || true)"
      [ -n "$caminho" ] && candidatos+=("$caminho")
    done
    for fixo in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
      candidatos+=("$fixo")
    done
  fi
  for py in "${candidatos[@]}"; do
    [ -x "$py" ] || continue
    if [ "$MACOS" = 1 ] && [ "$py" = "/usr/bin/python3" ] && ! "$XCODE_SELECT" -p >/dev/null 2>&1; then
      continue  # sem Xcode CLT o /usr/bin/python3 é só um stub que abre o instalador
    fi
    versao_ok "$py" || continue
    v="$(versao_de "$py")"
    if [ -z "$melhor" ] || [[ "$v" > "$melhor" ]]; then
      melhor="$v"; escolhido="$py"
    fi
  done
}

escolher_python

# Clique duplo no Mac sem Python: abre o instalador das ferramentas da Apple (traz o python3) e espera ele terminar
if [ -z "$escolhido" ] && [ "$MACOS" = 1 ] && [[ " $* " == *" --instalar-ou-atualizar "* ]] \
  && ! "$XCODE_SELECT" -p >/dev/null 2>&1; then
  echo "O Goal Pacer precisa do Python das ferramentas de linha de comando da Apple."
  echo "Abrindo o instalador da Apple: clique em Instalar e aguarde. Esta janela segue sozinha quando terminar."
  "$XCODE_SELECT" --install >/dev/null 2>&1 || true
  for _ in $(seq 1 360); do
    "$XCODE_SELECT" -p >/dev/null 2>&1 && break
    sleep 5
  done
  escolher_python
fi

if [ -z "$escolhido" ]; then
  if [ "$MACOS" = 1 ]; then
    dica="Rode xcode-select --install ou instale o Python 3 (python.org ou Homebrew)"
  else
    dica="Instale o Python 3 pelo gerenciador de pacotes (por exemplo: sudo apt install python3)"
  fi
  echo "erro: nenhum python3 3.9 ou mais novo encontrado${GP_PYTHON3:+ em $GP_PYTHON3}. $dica e tente de novo." >&2
  exit 4
fi

case "$escolhido" in
  /*) ;;
  *) escolhido="$(cd "$(dirname "$escolhido")" && pwd)/$(basename "$escolhido")" ;;
esac

exec "$escolhido" "$AQUI/scripts/instalar.py" --origem-padrao "$AQUI" "$@"

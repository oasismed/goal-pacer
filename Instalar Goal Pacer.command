#!/bin/bash
# Clique duplo no Finder (macOS): instala o Goal Pacer desta pasta, ou atualiza a instalação que já existe para a
# versão desta pasta, e abre o app (Goal Pacer em ~/Applications, ou o painel no navegador quando não há compilador
# Swift). Deu certo: a janela do Terminal fecha sozinha; parou: a mensagem fica na tela.
# Na primeira vez o macOS avisa que o arquivo veio da internet: Ajustes do Sistema > Privacidade e Segurança >
# "Abrir mesmo assim". O que roda é o install.sh ao lado deste arquivo, sem nada escondido.
set -u
cd "$(dirname "$0")" || exit 1
JANELA="$(osascript -e 'tell application "Terminal" to id of front window' 2>/dev/null || true)"
echo "Instalando o Goal Pacer..."
echo
if ./install.sh --nao-interativo --instalar-ou-atualizar --abrir; then
  echo
  echo "Pronto: o Goal Pacer abriu. Esta janela fecha sozinha."
  case "$JANELA" in
    ''|*[!0-9]*) ;;
    *)  # fecha depois que este shell sai: com o shell vivo, o Terminal perguntaria antes de fechar
      nohup /bin/sh -c "sleep 1; osascript -e 'tell application \"Terminal\" to close (every window whose id is $JANELA)'" \
        >/dev/null 2>&1 &
      ;;
  esac
  exit 0
fi
echo
echo "A instalação parou: a mensagem acima diz o que fazer. Depois, clique duas vezes neste arquivo outra vez."
read -r -n 1 -s -p "Aperte uma tecla para fechar." || true
echo

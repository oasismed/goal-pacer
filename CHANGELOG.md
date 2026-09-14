# Mudanças

Uma seção por versão publicada, da mais nova para a mais antiga. `dev/release.py` usa a seção da versão como notas da
página da versão no GitHub e recusa publicar sem ela.

## 0.6.2 (14/09/2026)

- Nada muda no app. O repositório no GitHub recomeçou o histórico: as versões antigas saíram da página de versões, e
  a 0.6.2 é o ponto de partida.

Quem está na 0.6.1: Procurar atualização traz a 0.6.2. Quem está na 0.5.0 ou na 0.6.0: abra uma vez o `.dmg` ou o
`Setup.exe` da 0.6.2.

## 0.6.1 (14/09/2026)

- **Procurar atualização busca no repositório do Goal Pacer**, agora público: `oasismed/goal-pacer`, sem login. A
  0.6.0 procurava num repositório separado que não chegou a existir.

Quem está na 0.5.0 ou na 0.6.0: abra uma vez o `.dmg` (arraste o app novo para Aplicativos) ou o `Setup.exe` da
0.6.1; daí em diante o botão Procurar atualização basta. Pelo git, `goal-pacer atualizar`. Não mande os instaladores
da 0.6.0.

## 0.6.0 (14/09/2026)

Instalar, entrar, atualizar e remover sem sair da janela do app.

- **Procurar atualização busca no GitHub:** o botão da tela Status consulta a versão mais nova publicada no
  repositório de versões no GitHub, confere a assinatura com a lista da sua
  instalação, aplica com backup e volta atrás e reinicia o painel. A tela avisa sozinha, uma vez por dia.
- **Login do Claude Code pela tela Começar:** o botão abre a página de autorização do claude.ai no navegador e você
  cola na tela o código do fim; o painel entrega o código ao `claude auth login` oficial, sem Terminal e sem guardar
  nada dele.
- **Remover pelo app:** em Status, Remover deste computador (com confirmação) tira jobs, painel, atalhos, o app do
  `.dmg` e o Python dos jobs; metas e registro ficam.
- **Painel no celular com HTTPS:** com `openssl` no computador, a rede de casa passa a HTTPS com certificado gerado na
  própria máquina e a impressão digital no cartão do computador para conferir no celular. `--sem-https` volta ao HTTP.
- No Windows, prompt longo vai para o `claude` pela entrada padrão (a linha de comando de lá tem teto), e o
  `claude.exe` do instalador oficial tem preferência sobre o `claude.cmd` do npm.

Quem está na 0.5.0: a 0.5.0 não conhece o endereço de versões. Abra uma vez o `.dmg` (arraste o app novo para
Aplicativos) ou o `Setup.exe` da 0.6.0; daí em diante o botão Procurar atualização basta. Pelo git,
`goal-pacer atualizar`.

## 0.5.0 (14/09/2026)

Um arquivo para mandar, e o app funcionando sem conector.

- **Instaladores de um arquivo:** `Goal-Pacer-X.Y.Z.dmg` no Mac (arrastar para Aplicativos e abrir; o app prepara
  tudo na primeira abertura, com o Python dentro) e `Goal-Pacer-Setup-X.Y.Z.exe` no Windows (instalação só para o
  usuário, desinstalação em Aplicativos). Atualizar é abrir a versão nova. Sem certificado pago, o sistema pede um
  clique a mais na primeira abertura.
- **Conectores opcionais:** sem Google Calendar e Gmail, metas, plano e dia saem só do que você escreve (blocos no
  app, sem email). Conectar aprofunda: agenda, check-in inferido, email das 7h e evidências.
- **Tela Começar que resolve:** confere sozinha o Claude Code e cada conector, instala o Claude Code e abre o login
  por botões, detecta a conta assim que você conecta e gera o primeiro dia ao gravar as metas.
- Antes do onboarding, as telas abrem vazias, com um convite para a tela Começar.
- Canal de versões opcional: com um endereço em `release/canal`, a tela Status avisa a versão nova e o update baixa
  sozinho.
- No Mac, o clique duplo pelo zip sem Python abre o instalador das ferramentas da Apple; no Windows, o `.cmd` aberto
  de dentro do zip pede para extrair antes.

Quem vem da 0.4: pelo git, `goal-pacer atualizar`; pelo zip ou pelo Mac, também dá para abrir o `.dmg` da 0.5.0 e
arrastar o app (ele assume a instalação que já existe).

## 0.4.1 (14/09/2026)

- No Mac, o painel volta sozinho depois de uma atualização (antes, ficava fora do ar até o próximo login).

Quem está na 0.4.0 com o painel fora do ar: `goal-pacer atualizar` traz a 0.4.1 e religa o painel.

## 0.4.0 (14/09/2026)

Windows, e instalar e atualizar com um clique duplo.

- **Windows 10 e 11:** `Instalar Goal Pacer.cmd` acha o Python (ou instala o 3.12 pelo winget, só para o seu
  usuário), agenda o diário e o mensal no Agendador de Tarefas, deixa o painel no ar a cada login e cria o atalho
  **Goal Pacer** no menu Iniciar, que abre o painel numa janela própria do navegador em modo app.
- **Atualizar é o mesmo gesto:** baixe o zip da versão nova, descompacte e clique duas vezes no instalador. Ele
  confere o manifesto assinado da pasta e troca o app com backup e volta atrás; na mesma versão, só repara o que
  faltar. O zip de cada versão passa a levar `release/manifesto.json` assinado.
- **Mais simples:** sem o Claude Code, a instalação segue e a tela Começar mostra o que falta, com o link de cada
  item (Claude Code, conectores, calendário Metas). No Mac, a janela do Terminal fecha sozinha quando dá certo, e o
  app Goal Pacer só é compilado outra vez quando muda.
- Painel da tela Status: quem instalou pelo zip vê como atualizar pelo clique duplo.

Quem vem da 0.3.0 instalado pelo git: `goal-pacer atualizar` traz tudo. Quem instalou pelo zip: baixe o zip da 0.4.0,
descompacte e clique duas vezes em `Instalar Goal Pacer.command` (a 0.3.0 não conhece o manifesto, mas o instalador
que roda é o da 0.4.0, que confere a pasta).

## 0.3.0 (14/09/2026)

Janela própria, sem navegador.

- No Mac, o instalador compila o app **Goal Pacer** em `~/Applications` (Launchpad e Dock): o painel numa janela
  nativa, com menus de editar; links para fora abrem no navegador. Compilado na própria máquina pelas Command Line
  Tools, sem conta de desenvolvedor Apple. `install.sh --sem-janela` pula; o uninstall remove.
- O clique duplo em `Instalar Goal Pacer.command` abre o app no fim.
- O update termina com o instalador da versão nova, então o que ela passar a instalar entra sozinho nos próximos
  updates.

Quem vem da 0.1.0 ou da 0.2.0: depois do `goal-pacer atualizar`, rode uma vez `~/.goal-pacer/app/install.sh
--nao-interativo` para montar o app (os atualizadores dessas versões não sabem montá-lo; da 0.3.0 em diante o
update cuida disso).

## 0.2.0 (14/09/2026)

Instalar e começar sem terminal.

- `Instalar Goal Pacer.command` no zip: clique duplo instala e abre o painel.
- O painel fica sempre no ar em `http://127.0.0.1:8765/` e o navegador instala como app (ícone no Dock, janela
  própria). `install.sh --painel-rede` deixa também para o celular; `--sem-painel` desliga.
- Tela Começar: o onboarding pela tela, com a conferência da conta Google, as metas, o horário, as fontes e o botão
  que gera o primeiro dia.
- Status com manutenção: conferir a instalação e procurar atualização pelo painel.
- SIGTERM e Ctrl+C fecham o painel sem prender o processo.

Quem vem da 0.1.0: depois do `goal-pacer atualizar`, rode uma vez `~/.goal-pacer/app/install.sh --nao-interativo`
para ligar o painel sempre no ar (o atualizador da 0.1.0 não conhece o agente novo; da 0.2.0 em diante o update
cuida disso).

## 0.1.0 (13/09/2026)

Primeira versão para instalar. O histórico de desenvolvimento anterior a ela não foi publicado; os commits citados em
`docs/` (dívida técnica, qualidade, revisões) são desse histórico.

- Metas e objetivos pela entrevista da skill (`/goal-pacer onboarding`), com o custo em horas de cada meta confirmado
  por você.
- Balanço do mês com as seções semanais, blocos encaixados nas janelas livres do calendário "Metas" e email às 7h,
  em português do Brasil ou em inglês.
- Check-in pelo Calendar (bloco mantido, apagado ou movido), pelo painel ou respondendo o email das 7h.
- Evidências do mês lidas do Gmail, do export do WhatsApp, do Notion e do Google Drive, só leitura.
- Painel local com Hoje, Horizontes (do ano ao dia), Objetivos, Metas, Check-in, Status e Conexões; no celular pelo
  Wi-Fi de casa com pareamento por código.
- Jobs agendados no macOS (launchd) e no Linux (systemd), comando único `goal-pacer`, doctor em 8 itens, autoteste,
  registro local de eventos e traces.
- Instalação pelo zip assinado ou pelo clone de uma tag assinada; `goal-pacer atualizar` só aceita versão publicada e
  assinada, com backup dos dados e volta atrás automática.

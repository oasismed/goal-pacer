# Goal Pacer: referência

O guia para quem quer ir além das telas: instalar pelo zip, pelo terminal ou pelo git, o comando `goal-pacer`, os modos da skill, os arquivos da pasta de dados, o celular na rede de casa, confiabilidade, observabilidade e configuração avançada. Para instalar e começar, o [README](../README.md) basta.

- [Pré-requisitos](#pre-requisitos)
- [Instalação](#instalacao)
- [O comando goal-pacer](#comando)
- [Checklist depois de instalar ou atualizar](#checklist)
- [Modos da skill](#modos)
- [Painel no navegador](#painel)
- [Como o dia funciona](#como-o-dia-funciona)
- [Idiomas](#idiomas)
- [Arquivos](#arquivos)
- [Export do WhatsApp](#export-do-whatsapp)
- [Segurança e privacidade](#privacidade)
- [Confiabilidade](#confiabilidade)
- [Observabilidade](#observabilidade)
- [Tokens e tempo por job](#tokens-e-tempo)
- [Limites conhecidos](#limites)
- [Atualizar e desinstalar](#atualizar-e-desinstalar)
- [Configuração avançada](#configuracao-avancada)

<a id="pre-requisitos"></a>
## Pré-requisitos

- **macOS** com uma sessão aberta às 7h (o launchd roda o job assim que o computador acorda), **Windows 10 (1903) ou 11** com a sessão aberta (o Agendador de Tarefas roda o job perdido assim que puder), ou **Linux** com `systemd --user` (para rodar com a sessão fechada: `loginctl enable-linger $USER`).
- Claude Code instalado e logado com um plano Pro ou Max ([como instalar](https://code.claude.com/docs/en/setup)). O instalador não depende dele: a tela Começar tem o botão que roda o instalador oficial e o que abre o login.
- **Conectores são opcionais.** Sem nenhum, metas, plano e dia saem só do que você escreve: os blocos ficam no app, sem email. Com **Google Calendar** e **Gmail** conectados em claude.ai (com permissão de escrita), os blocos vão para a agenda, o check-in se infere sozinho e o email chega às 7h; Notion e Google Drive trazem evidências e só leem. Confira com `claude mcp list` ou na tela Começar.
- Com o Google Calendar: um calendário chamado **Metas** (ou **Goals**) criado à mão. É o único em que o Goal Pacer escreve.
- Python 3.9 ou mais novo, só a biblioteca padrão. O `.dmg` e o `Setup.exe` já trazem o Python dentro. Pelo zip, no macOS, o `/usr/bin/python3` da Apple serve com as Xcode Command Line Tools (`xcode-select --install`); Python do Homebrew ou do python.org também. No Windows, o instalador acha o Python do python.org e, sem nenhum, instala o 3.12 pelo `winget` só para o seu usuário (o Python da Microsoft Store não serve: ele isola as pastas de atalhos); a base de fusos horários (`tzdata`, versão e hash fixos) vai para `~/.goal-pacer/vendor`. No Linux, o python3 da distribuição.
- `git` é opcional: com ele o app atualiza por `git pull`; sem ele (ou instalando de um zip) o app vai por cópia.

Se o macOS pedir acesso às Chaves (Keychain) para o `claude`, escolha "Permitir sempre". Sem isso o `claude` não acha a sessão quando roda às 7h. A tela Começar lembra disso na hora em que o pedido costuma aparecer.

**Provedor de IA.** A IA do app sai do login que você já tem, pelo CLI oficial, sem chave de API. O padrão é `claude` (Claude Code com a assinatura Claude), que cobre tudo. O provedor `openai` usa o Codex CLI com o login ChatGPT: a prosa (porquê dos blocos e texto do plano) já funciona com `GP_PROVEDOR=openai`; Calendar e Gmail pelos conectores do ChatGPT dependem de uma prova com login ChatGPT, e até ela passar `install.sh --provedor openai` não instala.

<a id="instalacao"></a>
## Instalação

Quem mantém gera, a cada versão, dois instaladores de um arquivo, para mandar direto a quem vai usar (e o zip assinado, para quem prefere o terminal; ficam também em https://github.com/oasismed/goal-pacer/releases, repositório público):

- **Mac:** `Goal-Pacer-X.Y.Z.dmg`. Abra o `.dmg`, arraste **Goal Pacer** para **Aplicativos** e abra o app. Na primeira vez o macOS diz que não verificou o app (ele não tem certificado pago): abra Ajustes do Sistema > Privacidade e Segurança, clique em **Abrir mesmo assim** e confirme. O app prepara tudo na primeira abertura (leva um minuto, com o progresso na janela) e abre na tela Começar. Mac com Apple Silicon ou Intel, macOS 13 ou mais novo; não pede Command Line Tools nem Python.
- **Windows:** `Goal-Pacer-Setup-X.Y.Z.exe`. Abra o arquivo; se o Windows avisar que protegeu o computador, clique em **Mais informações** > **Executar assim mesmo**. O instalador é só para o seu usuário (sem administrador), traz o Python dentro, cria o atalho **Goal Pacer** no menu Iniciar e registra a desinstalação em Configurações > Aplicativos. No fim, **Abrir o Goal Pacer**.

**Atualizar é abrir a versão nova:** no Mac, arraste o app novo para Aplicativos (substituir) e abra; no Windows, abra o `Setup.exe` novo. O instalador de dentro confere o manifesto assinado da versão com a lista de assinantes da instalação que você já tem e troca o app com backup e volta atrás; seus dados ficam. Sem baixar nada à mão: o botão **Procurar atualização** na tela Status busca a versão mais nova publicada no GitHub (`oasismed/goal-pacer`, repositório público; nenhum login), confere a assinatura com a lista da sua instalação, aplica com backup e volta atrás e reinicia o painel; a tela também avisa sozinha, uma vez por dia, quando há versão nova. Instalações da 0.5.0 e da 0.6.0 não conhecem esse endereço: abra uma vez o instalador da versão mais nova e daí em diante o botão basta.

**Pelo zip, com clique duplo (macOS e Windows).** Baixe o zip, descompacte e clique duas vezes no instalador da pasta (no Windows, extraia antes: aberto de dentro do zip, o instalador pede para extrair):

- **macOS:** `Instalar Goal Pacer.command`. Na primeira vez o macOS avisa que o arquivo veio da internet: libere em Ajustes do Sistema > Privacidade e Segurança > "Abrir mesmo assim". Deu certo, a janela do Terminal fecha sozinha e abre o **Goal Pacer**, app com janela própria em `~/Applications` (Launchpad e Dock), compilado na própria máquina pelas Command Line Tools, sem conta de desenvolvedor Apple. Sem o compilador Swift, o painel abre no navegador.
- **Windows:** `Instalar Goal Pacer.cmd`. Na primeira vez o Windows pode avisar que o arquivo veio da internet: "Mais informações" > "Executar assim mesmo". O instalador acha o Python (ou instala pelo `winget`), agenda os jobs no Agendador de Tarefas, deixa o painel no ar a cada login e cria o atalho **Goal Pacer** no menu Iniciar, que abre o painel numa janela própria do Chrome, do Edge ou do Brave em modo app (o navegador padrão quando é um deles; senão, o Edge). Deu certo, a janela preta fecha sozinha.

Pelos três caminhos, o app abre na tela **Começar**. Tudo pela janela do app, sem Terminal nem IDE. Ela confere sozinha, sem gastar tokens, o Claude Code e cada conector: sem o Claude Code, o botão roda o instalador oficial; sem login, o botão abre a página de autorização do claude.ai no navegador e você cola na própria tela o código que ela mostra no fim (o painel entrega o código ao `claude auth login` oficial e não guarda nem registra nada dele); para cada conector, o link de onde se conecta em claude.ai; detecta a conta Google assim que Calendar ou Gmail conectam; e faz o onboarding pela tela: metas, horário, fontes. Ao gravar as metas, o primeiro dia sai sozinho. Antes disso, as outras telas abrem vazias, com um convite para a tela Começar. O painel fica sempre no ar em `http://127.0.0.1:8765/`.

Pelo zip, **atualizar é o mesmo gesto:** baixe o zip da versão nova, descompacte e clique duas vezes no instalador dela. Ele confere o manifesto assinado da pasta (`release/manifesto.json`) com a lista de assinantes da instalação que você já tem, copia só os arquivos listados, cada um com o sha256 conferido, e troca o app com backup e volta atrás. A mesma versão só repara o que faltar (agendador, comando, janela); uma pasta mais antiga não muda nada.

**Pelo terminal, conferindo o zip antes.** Baixe os dois arquivos para a mesma pasta, confira a assinatura e instale:

```bash
cd ~/Downloads
echo 'chico@oasismed namespaces="git,goal-pacer-release" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGnLlssZTcvCXX5reI5hRsRwBuTLyii2UcmGR/YXjbiq' > goal-pacer-assinantes
ssh-keygen -Y verify -f goal-pacer-assinantes -I chico@oasismed -n goal-pacer-release \
  -s goal-pacer-v0.1.0.zip.sig < goal-pacer-v0.1.0.zip       # precisa dizer: Good "goal-pacer-release" signature
unzip -q goal-pacer-v0.1.0.zip && cd goal-pacer-v0.1.0 && ./install.sh
```

A chave que assina as versões tem a impressão digital `SHA256:kMS9pfkMoLj8ixuqE1LHih/XKA0LmHOeVOXeGWGrUDw`. Ela também está em `release/assinantes`, mas confira pela linha acima, que não vem de dentro do zip.

**Pelo git.** Clone a tag da versão (o `install.sh` confere quem assinou só nas atualizações; a primeira confiança é o HTTPS do GitHub e a sua conta):

```bash
git clone --branch v0.1.0 https://github.com/oasismed/goal-pacer.git
cd goal-pacer && git -c gpg.ssh.allowedSignersFile=release/assinantes verify-tag v0.1.0 && ./install.sh
```

Nos dois casos, termine na tela Começar do painel (`http://127.0.0.1:8765/`) ou no Claude Code com `/goal-pacer onboarding`.

O `install.sh` (ou o `.cmd` no Windows) escolhe o Python mais novo que encontrar e faz o resto, conferindo cada passo:

1. Põe o app em `~/.goal-pacer/app` (clone, ou cópia quando a origem não é um clone git) e liga a skill em `~/.claude/skills/goal-pacer` (symlink; junção no Windows, que não pede administrador).
2. Cria o comando `goal-pacer` em `~/.goal-pacer/bin` (`goal-pacer.cmd` no Windows) e, se `~/.local/bin` existir, um link para ele ali. Um `goal-pacer` de outra origem nunca é sobrescrito.
3. Pergunta a pasta de dados. O padrão é `~/.goal-pacer/dados`. No macOS, pastas em Desktop, Downloads ou Documents são recusadas, porque o launchd não tem acesso a elas.
4. Gera os jobs com caminhos absolutos, confere o que gerou e carrega no agendador: launchd no macOS (`com.goal-pacer.diario`, segunda a sábado 07:00; `com.goal-pacer.mensal`, dia 1 05:30; `com.goal-pacer.painel`, o painel sempre no ar) , systemd no Linux (`goal-pacer-diario.timer` e `goal-pacer-mensal.timer`, com `Persistent=true` para rodar ao ligar se o horário passou, e `goal-pacer-painel.service`) ou o Agendador de Tarefas no Windows (`GoalPacer\diario` e `GoalPacer\mensal`, com "executar assim que possível" se o horário passou, e o atalho `Goal Pacer (painel)` na pasta Inicializar). No Windows os três chamam `scripts/lancador.py` pelo `pythonw.exe`: sem console, com a saída em `jobs/logs/tarefa-*.log`.
5. Fecha as permissões: pastas de dados, jobs e logs só suas (0700), arquivos com segredo 0600, código do app sem escrita para outros usuários (no Windows valem as permissões da sua pasta de usuário).
6. Monta a janela: o `Goal Pacer.app` no macOS ou o atalho Goal Pacer no menu Iniciar do Windows.
7. Confere python3, `claude` e conectores. Pelo clique duplo, o que faltar aqui não para a instalação: a tela Começar mostra.

Opções:

| Opção | O que faz |
|---|---|
| `--dados PASTA` | Usa outra pasta de dados sem perguntar. |
| `--nao-interativo` | Não pergunta nada. |
| `--from ORIGEM --copiar` | Copia a árvore de trabalho em vez de clonar. Útil em desenvolvimento. |
| `--sem-agendar` | Gera os arquivos do agendador sem carregar os jobs. |
| `--painel-rede` | Deixa o painel no ar também para o celular no Wi-Fi de casa (sem a flag, só neste computador). |
| `--sem-painel` | Não deixa o painel sempre no ar (abra com `goal-pacer painel` quando quiser). |
| `--sem-janela` | Não monta a janela própria (o `Goal Pacer.app` no macOS, o atalho do menu Iniciar no Windows); o painel fica só no navegador. |
| `--instalar-ou-atualizar [--abrir]` | O clique duplo: instala, ou atualiza a instalação que já existe a partir desta pasta, e abre o app. |
| `--check [--sondar-escrita]` | Só confere a instalação. A sonda cria e apaga um evento no Metas e um rascunho no Gmail. |
| `--update [--from ARQUIVO.zip]` | Atualiza para a versão publicada e assinada mais nova, com backup e volta atrás. Veja [Atualizar e desinstalar](#atualizar-e-desinstalar). |
| `--uninstall [--apagar-blocos] [--apagar-cache]` | Remove jobs, skill e comando e preserva suas metas. |

Pastas com aspas, `$`, crase ou quebra de linha no nome são recusadas, e também barra invertida no macOS e no Linux e `%` no Windows. Espaços, acentos e `#` funcionam.

<a id="comando"></a>
## O comando goal-pacer

Um comando só para o terminal. Os argumentos depois do comando seguem para o script (`goal-pacer doctor --sondar-escrita`).

| Comando | O que faz |
|---|---|
| `goal-pacer status` | Como vão as metas, pendências, cobertura do mês, perfil e últimas execuções. |
| `goal-pacer doctor` | Confere a instalação em 8 itens, cada um `OK` ou `FALHOU` com o que fazer. |
| `goal-pacer painel` | Abre o painel no navegador (`--rede` para o celular). |
| `goal-pacer diario` / `mensal` | Refaz o dia ou o balanço do mês agora. |
| `goal-pacer validar` | Valida a pasta de dados. |
| `goal-pacer autoteste` | Confere, sem conectores e sem tokens, que o código roda nesta máquina. |
| `goal-pacer logs` | Lê o registro local: `resumo` (tempo por tela e por conector, alertas), `eventos --tipo painel`, `trace ultimo` (o último job em árvore). |
| `goal-pacer atualizar` | Traz a versão nova com backup, autoteste e volta atrás se precisar. |
| `goal-pacer desinstalar` | Remove jobs, skill e comando; metas e registro ficam. |
| `goal-pacer versao` | Versão, esquema, plataforma e idioma. |

Em inglês também valem `dashboard`, `daily`, `monthly`, `validate`, `selftest`, `update`, `uninstall`, `version` e `help`.

<a id="checklist"></a>
## Checklist depois de instalar ou atualizar

Em 5 minutos:

```bash
goal-pacer autoteste
goal-pacer doctor
```

Os 8 itens do doctor devem sair `OK`. Antes do onboarding, o item da pasta de dados sai `FALHOU` com "rode /goal-pacer onboarding", e isso é esperado. Depois, no Claude Code:

```
/goal-pacer onboarding
/goal-pacer diario
```

Confira os blocos no calendário Metas e o arquivo `~/.goal-pacer/dados/dias/<hoje>.md`.

Em 1 hora, prove o job de verdade:

```bash
launchctl kickstart gui/$(id -u)/com.goal-pacer.diario      # macOS
systemctl --user start goal-pacer-diario.service             # Linux
tail -f ~/.goal-pacer/jobs/logs/run-job-diario-*.log
```

O log termina com `fim: exit 0` e o email `[goal-pacer] ...` chega na sua caixa. Depois rode `goal-pacer doctor --sondar-escrita` para provar o escopo de escrita dos conectores.

<a id="modos"></a>
## Modos da skill

Todos rodam dentro do Claude Code com `/goal-pacer <modo>`. A skill conversa e coleta respostas; quem calcula e grava é sempre um script em `~/.goal-pacer/app/scripts/`.

| Modo | Quando usar | Script |
|---|---|---|
| `onboarding` | Primeira vez, ou para cadastrar metas novas. Até 8 perguntas, uma por vez: objetivos e metas, prazo e impacto, custo em horas (com pesquisa na web), horário útil, calendário, fontes, palavras-chave com o porquê de cada objetivo, email e fuso. | `onboarding.py` |
| `checkin` | Quando quiser confirmar o que fez. Menos de 2 minutos: blocos "feita?", como você está com cada meta, decisão pendente, progresso às segundas, uma nota. | `checkin.py` |
| `diario` | Refazer o dia agora. O job das 7h roda o mesmo script e manda o email. | `diario.py` |
| `mensal` | Refazer o plano do mês: lê as fontes, calcula o balanço de horas, escreve `planos/AAAA-MM.md`. | `mensal.py` |
| `semanal` | Refazer os números do mês sem ler as fontes. O job de segunda faz isso sozinho. | `semanal.py` |
| `status` | Ver pendências, como vão as metas, cobertura do mês, perfil, evidências e as últimas execuções. `--doctor` confere a instalação. | `status.py` |
| `painel` | Abrir o painel no navegador. | `web.py` |

Para ajustar uma meta sem refazer o onboarding: `python3 ~/.goal-pacer/app/scripts/metas.py ajustar M02 --prazo 2027-04-12`. Opções: `--custo`, `--semanas`, `--prazo`, `--prazo-externo sim|nao`, `--estado ativa|pausada|concluida|vencida|arquivada`, `--confianca`. O painel faz o mesmo na tela da meta.

<a id="painel"></a>
## Painel no navegador

```bash
goal-pacer painel
```

Abre `http://127.0.0.1:8765/`. Instalado, o painel já fica no ar a cada login nesse endereço; no Mac, o app **Goal Pacer** (em Aplicativos e no Launchpad) abre o mesmo painel em janela própria, com menus de editar, e links para fora abrem no navegador. Fechar a janela não para os jobs nem o painel. O painel não é um placar de horas: ele lê cada meta como um coach leria e mostra palavras, não porcentagens. Os cálculos ficam nos scripts (`scripts/goalpacer/coach.py`); os gráficos desenham essa leitura.

| Seção | O que mostra | O que dá para fazer |
|---|---|---|
| Hoje | A trilha do dia no horizonte (ano › semestre › trimestre › mês › semana), uma manchete para a semana, os blocos do dia, três anéis concêntricos (hoje: presença; semana: ritmo; mês: direção), o que mais move seus objetivos agora, a força de cada objetivo, as metas por estado e o espaço na agenda do mês. | Confirmar um bloco, marcar "não fiz", responder a decisão do mês, ir para o dia anterior ou o seguinte. |
| Objetivos | Cada objetivo na sua cor, com a força em anel e em palavras (avançando firme, em construção, pede foco), o porquê, como você vai saber que mudou e o quanto cada meta move o objetivo pelo impacto dela. | Abrir a meta que mais move o objetivo. |
| Metas | O mapa de energia (impacto por tração: proteger, destravar, manter leve, repensar) e um cartão por meta com estado, jornada, tendência e a trilha das últimas 6 semanas. | Abrir qualquer meta. |
| Meta | A leitura do coach (o que está funcionando, onde está o atrito, o próximo passo), a jornada com os marcos, a trilha sobre faixas com nome, os sinais em palavras, os números do balanço como detalhe e os blocos recentes. | Marcar marcos, dizer como você está com a meta (com energia, firme, pesada), ajustar horas por semana, prazo, impacto e objetivo, pausar, retomar ou marcar como conquistada. |
| Horizontes | O drill-down ano › semestre › trimestre › mês › semana › dia. Ano, semestre e trimestre são os horizontes das metas do onboarding; mês, semana e dia saem delas (o plano, as semanas do balanço, os blocos). Cada período mostra a leitura (anel de fora: tempo que passou; de dentro: a leitura), as metas daquele horizonte com o compasso até o prazo (com folga, no compasso, pede fôlego), as maiores e as menores que passam por ali, e as partes com a leitura de cada uma. No mês, também o espaço na agenda por semana, a leitura do mês, as decisões e os sinais de fora. | Descer e subir de nível, ir ao período anterior ou seguinte, responder decisões. |
| Check-in | Os blocos dos últimos 7 dias que esperam confirmação, cada meta e uma nota. | Fiz ou não fiz em cada bloco, como está cada meta, decisões e uma nota que vai para o `perfil.md`, tudo num salvar só. |
| Começar | Aparece sozinha enquanto não há metas: a conta (Claude Code, conectores, calendário Metas), as metas com prazo e horas por semana, o horário útil, as fontes e as palavras-chave, e a conferência final. Cada passo fica no mesmo rascunho da skill. | Conferir a conta Google, gravar as metas, gerar o primeiro dia, instalar o painel como app. |
| Status | Execuções do job diário, configuração, o cartão do celular, a manutenção, instalar como app e os comandos do terminal. | Esquecer aparelhos pareados, conferir a instalação (doctor), procurar atualização (reinicia o painel se houver versão nova). |
| Conexões | O provedor de IA e onde conectar; Google Calendar, Gmail, Notion, Google Drive e o export do WhatsApp com o estado em palavras (conectado, reconectar, desconectado, sem verificação), quando o doctor viu, quando o job usou, se o calendário Metas existe e quando a escrita foi testada; o aviso quando o último job parou pedindo reconexão. O estado vem do `goal-pacer doctor` e dos jobs (`jobs/conexoes.json`): o painel não confere nada sozinho. | Ligar ou desligar cada fonte nos sinais do mês (vale na próxima leitura mensal). |

Estados de meta: florescendo, ganhando ritmo, pede atenção, travada, em pausa e conquistada. A semana pertence ao mês da sua quinta-feira, a mesma regra do plano: segunda, 28/09 fica na semana 40, que é de outubro. Sem objetivos cadastrados em `objetivos/O<nn>.md`, cada meta conta como o próprio objetivo; com eles, o campo `objetivo` e o `impacto` (essencial, importante, apoio) de cada meta pesam a força do objetivo.

Ctrl+C no terminal fecha o painel aberto com `goal-pacer painel`. Para ver a interface com dados de exemplo, use `--demo`: ele monta numa pasta temporária três objetivos, seis metas (de trimestre, semestre e ano) e cinco semanas de histórico sintéticos, e a pasta some ao fechar.

Sem `--rede`, o painel roda só no seu computador: ele escuta apenas em 127.0.0.1, usa um token novo a cada abertura e recusa pedidos de outros sites. Tudo o que o painel grava passa pelas mesmas funções da skill (`checkin.confirmar`, `metas.ajustar`, `metas.marcar_marco`, `conexoes.ajustar_fonte`), sob o lock da pasta de dados. O painel não chama o Calendar nem o Gmail: só a tela Começar e a manutenção rodam, a partir do próprio computador e nunca pelo celular, os mesmos comandos da skill que leem a conta (`onboarding.py detectar`, `status.py --doctor`) ou disparam o job diário. O plano novo sai no próximo diário (ou rode `/goal-pacer diario` para ver agora). A fonte Plus Jakarta Sans vem junto do app, sob a licença OFL em `web/fonts/OFL.txt`.

### No celular, no Wi-Fi de casa

```bash
goal-pacer painel --rede
```

1. No painel aberto no computador, em Status, o cartão **Abrir no celular** mostra o endereço na rede (por exemplo `https://192.168.0.20:8765/`), um código de 6 dígitos e a impressão digital do certificado. O código muda a cada abertura do painel.
2. No iPhone, no mesmo Wi-Fi, abra o endereço no Safari. Na primeira vez o Safari avisa que a conexão não é privada, porque o certificado foi gerado pelo seu computador e não por uma autoridade: em Mostrar Detalhes, confira se a impressão digital SHA-256 é a do cartão, toque em visitar o site e digite o código. O aparelho fica lembrado por 90 dias.
3. Toque em Compartilhar e em **Adicionar à Tela de Início**. O Goal Pacer abre em tela cheia, com o ícone dos anéis. Se o ícone pedir o código na primeira abertura, digite o mesmo código: o iOS guarda os cookies do ícone separados dos do Safari.

Para o painel ficar sempre no ar, sem terminal aberto, instale o agente do agendador (launchd no macOS, systemd no Linux):

```bash
./install.sh --painel-rede
```

O que vale saber antes:

- **HTTPS com certificado próprio.** Com `openssl` no computador (vem no macOS e na maioria dos Linux), o painel gera na primeira abertura um certificado autoassinado em `~/.goal-pacer/jobs/painel-tls/` (chave 0600, válido por 825 dias e refeito antes de vencer) e responde em HTTPS para a rede; um endereço `http://` da rede é mandado para o `https://`, e o cookie do aparelho só anda criptografado. O próprio computador segue em `http://127.0.0.1:8765/`. Sem `openssl` (comum no Windows), ou com `goal-pacer painel --rede --sem-https`, a rede fica em HTTP sem criptografia: use só no Wi-Fi de casa. Em qualquer caso, quem estiver na mesma rede e souber o código consegue parear; depois de 10 códigos errados o pareamento trava até o painel reiniciar.
- **Firewall.** Na primeira vez o macOS pergunta se o Python pode aceitar conexões de entrada. Escolha Permitir. No Linux, libere a porta 8765 se houver firewall ligado.
- **Computador acordado.** Com o computador dormindo o celular não alcança o painel. `--manter-acordado` impede o sono enquanto o painel roda.
- **Revogar.** O botão Esquecer aparelhos no cartão do computador (em Status), ou `goal-pacer painel --esquecer-aparelhos`, faz todo aparelho pedir o código outra vez. O servidor guarda só um resumo (sha256) de cada sessão, em `~/.goal-pacer/jobs/painel-aparelhos.json`.

<a id="como-o-dia-funciona"></a>
## Como o dia funciona

Às 7h o job:

1. Confere se o plano do mês existe e está em dia. Se não, gera o plano antes. Às segundas refaz os números da semana.
2. Aplica as respostas que você deu ao email do dia anterior (veja abaixo).
3. Lê o calendário Metas e infere o que aconteceu com os blocos anteriores.
4. Lê os calendários do dia, acha as janelas livres dentro do seu horário útil e encaixa os blocos.
5. Cria, move ou apaga eventos só no calendário Metas.
6. Escreve `dias/<hoje>.md` e manda o email.

Na agenda, três gestos bastam:

- **Deixar o bloco** onde está conta como "feita?". Aparece com essa marca e entra na leitura exibida, mas só abate horas quando você confirma.
- **Apagar o bloco** conta como não feito.
- **Mover o bloco** reagenda.

**Confirmar respondendo o email.** Cada bloco do email traz o número (`07h-08h · bloco 02`). Responda o email com uma linha por bloco, como `02 fiz 1h` ou `03 não fiz` (em inglês, `02 done 1h` ou `03 skipped`). O diário seguinte aplica só respostas enviadas pela sua própria conta, só linhas nessa forma e só para blocos que existem; o resto da mensagem é ignorado e o texto nunca é guardado.

Cada bloco se chama `[GP] <título>`. A última linha da descrição é a chave `gp:<bloco>/<instalação>`. Não apague essa linha: é por ela que o Goal Pacer reconhece o bloco.

O email segue sempre a mesma ordem: título e linha-resumo, decisão (quando houver), blocos de hoje, o que mudou desde o último email, como vão as metas (em palavras, sem porcentagem), avisos, o link do dia no Google Calendar e como responder.

<a id="idiomas"></a>
## Idiomas

O idioma é o `idioma` do `contexto.md`: `pt-BR` (padrão) ou `en`. O onboarding grava o idioma da conversa. Ele vale para o email, o `status`, o doctor, o check-in, o painel, as notificações e a prosa escrita pelo modelo nos jobs, que também passa pelas regras de tom do idioma. Para um comando só, use `--idioma en` (ou `GP_IDIOMA=en`).

Um idioma é um arquivo: `references/copy.<idioma>.md`, com as mesmas chaves e variáveis do `copy.pt-BR.md`, os nomes de dia e mês, o formato de data e o grupo `tom` com as palavras que nunca aparecem. Os testes conferem a paridade entre os arquivos e que as superfícies em inglês não carregam texto em português do código. A estrutura dos arquivos de dados (títulos de seção, chaves) é contrato e não muda com o idioma; as linhas que os scripts leem de volta são reconhecidas em qualquer idioma, então trocar o idioma no meio do mês não quebra o plano.

<a id="arquivos"></a>
## Arquivos

```
~/.goal-pacer/
  app/                     o código (clone ou cópia); a skill aponta para cá
  bin/goal-pacer           o comando único
  dados/                   sua pasta de dados (ou um symlink para ela)
    contexto.md            fuso, idioma, horário útil, calendários, fontes ativas, email
    objetivos/O01.md       o que você quer que mude, por que e como vai saber
    metas/M01.md           uma meta por arquivo: objetivo, impacto, prazo, custo em h/semana, marcos
    fontes/M01.md          a pesquisa que deu o custo
    planos/AAAA-MM.md      balanço de horas, seção por semana, evidências, decisões
    semanas/AAAA-Www.md    espelho gerado da semana (não edite)
    dias/AAAA-MM-DD.md     blocos do dia com estado e porquê
    sinais/AAAA-MM-DD.md   resumos das evidências lidas no mensal
    registro.json          check-ins, horas feitas, sentimentos, progresso declarado, execuções
    registro-AAAA.json     o que passou de 120 dias num ano anterior (arquivo anual, lido junto)
    perfil.json            o que o Goal Pacer aprendeu (só de blocos confirmados)
    perfil.md              notas que você aceitou no check-in
    backups/               zips antes de cada atualização ou migração (os 5 mais novos)
    inbox/whatsapp/        onde você coloca o export do WhatsApp
    cache/                 leituras da agenda e auditoria do mensal, apagadas em 7 dias
  jobs/
    *.plist | *.service    arquivos do agendador gerados
    instalacao.json        caminhos de python3, claude, app e dados (0600)
    logs/                  um log por execução, apagados em 7 dias
```

Os esquemas completos estão em `references/dados.md`. Edite à vontade os textos das metas, dos objetivos e o `perfil.md`. Números, estados e ids são escritos por scripts; para mudar uma meta use `metas.py ajustar` ou o painel.

<a id="export-do-whatsapp"></a>
## Export do WhatsApp

O WhatsApp não tem conector. Se você ativou a fonte `whatsapp` no onboarding, exporte a conversa em que fala das suas metas (um grupo de corrida, uma conversa com o professor) antes do dia 1:

- **iPhone:** abra a conversa, toque no nome no topo, "Exportar conversa", "Sem mídia". Salve em Arquivos e copie o `.zip` para `~/.goal-pacer/dados/inbox/whatsapp/`.
- **Android:** abra a conversa, menu de três pontos, "Mais", "Exportar conversa", "Sem mídia". Mande o `.txt` para o seu computador e copie para a mesma pasta.

O `.zip` é lido em memória, nunca extraído. Só entram trechos com as palavras-chave das metas, até 20 MB. Exports com mais de 7 dias aparecem como antigos no plano. Depois do mensal, o plano diz "export lido em <data>; pode apagar de inbox/whatsapp".

<a id="privacidade"></a>
## Segurança e privacidade

Por desenho, não por configuração:

- **Sem segredos.** Nada de chave de API, senha de app ou OAuth próprio: os conectores são os do claude.ai, pela sua assinatura. Nada sai do seu computador além das chamadas que o próprio Claude Code (ou o Codex, com o provedor `openai`) faz. O app nunca lê nem guarda o login de nenhum dos dois, e tira `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` e `CODEX_API_KEY` do ambiente dos CLIs para a conta nunca ir para a API paga.
- **Conteúdo de terceiros é dado, nunca instrução.** Emails, mensagens, páginas e convites entram nos prompts dentro de um envelope marcado, e nenhuma sessão que lê esse conteúdo pode escrever na agenda ou mandar email. Cada chamada a um conector é uma sessão `claude -p` de uma ferramenta só, com as outras negadas.
- **Leitura auditada.** A única sessão que busca nas fontes é só-leitura; o script guarda o nome e os argumentos de cada chamada (nunca a resposta) e descarta a leitura inteira se aparecer uma ferramenta fora da lista.
- **Menos dado guardado.** Eventos fora do calendário Metas perdem título e descrição antes de qualquer processamento. `sinais/` guarda resumos de uma linha, nunca a mensagem. Respostas ao email viram só o id da mensagem. `cache/` e `logs/` somem em 7 dias.
- **Permissões fechadas.** Dados, jobs e logs só seus (0700); `instalacao.json` e os aparelhos do painel 0600; o código que os jobs rodam (incluindo os hooks do `.git`) só você altera. O `goal-pacer doctor` confere tudo isso no item permissões e diz o `chmod` de cada caso.
- **Painel local.** Escuta em 127.0.0.1 com token por abertura, confere Host e Origin e usa CSP sem CDN. Na rede de casa, só com código de pareamento visto no computador, cookie HttpOnly e trava depois de 10 erros (contagem protegida contra tentativas em paralelo). Conexão parada cai em 15 s e mais de 32 conexões ao mesmo tempo são recusadas.
- **Skill sem escrita direta.** No turno em que a skill é chamada, as ferramentas que gravam no Calendar, Gmail, Drive e Notion ficam fora (`disallowed-tools`); quem grava são os scripts. O Claude Code limpa essa restrição na mensagem seguinte, por isso a regra de conduta vale na conversa inteira e as permissões do Claude Code seguem pedindo sua aprovação para qualquer escrita.
- **Email só para você**, com o prefixo `[goal-pacer]`; a busca no Gmail exclui esses emails e os que você mesmo mandou.

<a id="confiabilidade"></a>
## Confiabilidade

- **Um escritor por arquivo e um lock por pasta de dados.** Job, skill e painel esperam a vez; o doctor aponta lock esquecido.
- **Escrita atômica com `.bak`.** `registro.py recuperar` volta a cópia anterior se um arquivo corromper.
- **Tentativas medidas.** Chamada sem conectores carregados repete uma vez; limite de uso da assinatura tenta outra vez em 30 minutos; o email das 7h tenta até 3 vezes antes de virar notificação e email mínimo de falha.
- **Presunção honesta.** Bloco intocado é "feita?" e nunca abate horas até ser confirmado.
- **Atualização tudo ou nada.** Backup dos dados, autoteste do código novo e migração com volta atrás; se algo falha, o app volta à versão anterior e os jobs seguem nela.
- **Registro que não cresce sem limite.** O que passou de 120 dias num ano anterior vai para `registro-AAAA.json`, lido junto.
- **Diagnóstico de uma linha.** `goal-pacer doctor` diz o que fazer em cada item; `goal-pacer autoteste` separa problema da máquina de problema dos dados.

<a id="observabilidade"></a>
## Observabilidade

Tudo local, em `~/.goal-pacer/jobs/logs/` (pasta 0700, 7 dias), sem serviço de fora e sem conteúdo: nem título de evento, nem texto de email, nem o que você escreveu.

- **Painel:** cada pedido vira uma linha em `eventos-AAAA-MM-DD.jsonl` com rota, status, milissegundos e origem (computador ou aparelho). Erro inesperado responde em JSON e fica registrado; erro de JavaScript da tela também, por uma rota local com teto por minuto.
- **Job:** cada execução grava `trace-<job>.jsonl` com o tempo do job, de cada passo e de cada chamada de conector ou de prosa (tentativa, código e tokens). `goal-pacer logs trace ultimo` mostra em árvore.
- **Perto do limite:** o `status` ganha a seção "Perto do limite" quando algo encosta num teto, e o email das 7h leva até 2 desses avisos. Se o mesmo alerta aparece em três jobs seguidos, vira notificação uma vez.

| Alerta | Quando acende |
|---|---|
| Job perto do teto | duração acima de 70% do teto (20 min, ou 40 com o mensal) |
| Espera pela pasta de dados | job esperou mais de 5 min pelo lock |
| Limite de uso | 2 ou mais esgotamentos da janela da assinatura em 7 dias |
| Tokens acima do habitual | último job acima de 1,5 vez a mediana dos 14 anteriores |
| Chamada lenta | alguma chamada de conector acima de 90 s (o teto é 180 s) |
| Chamadas repetidas | mais de 30% das chamadas precisaram repetir em 7 dias |
| Registro grande | `registro.json` acima de 5 MB |
| Painel lento | telas acima de 300 ms nos pedidos mais lentos de 7 dias |
| Erros de tela | qualquer erro de JavaScript ou erro inesperado do painel em 7 dias |

`goal-pacer logs resumo --json` é a porta de leitura para quem diagnostica, pessoa ou agente: tempos p50 e p95 por tela e por ferramenta, chamadas repetidas, erros e tamanhos da pasta de dados. Nenhuma credencial é necessária. `GP_TELEMETRIA=0` desliga o registro.

<a id="tokens-e-tempo"></a>
## Tokens e tempo por job

Números medidos no spike (Claude Code 2.1.270). O `status` mostra os tokens reais de cada execução.

| Job | Chamadas | Tempo | Tokens de cache lidos |
|---|---|---|---|
| Diário, 2 calendários | cerca de 13 | cerca de 2 min | não medido em separado |
| Diário, 9 calendários | cerca de 25 | 2,6 a 4,7 min | 0,6 a 1,5 M |
| Mensal (agenda do mês e prosa) | cerca de 14 | cerca de 3 min | não medido em separado |
| Leitura das fontes no mensal | 5 a 10 | 1 a 2,5 min | não medido em separado |

Cada chamada a um conector é uma sessão `claude -p` curta, em série. O teto do job diário é 20 minutos, ou 40 quando encadeia o mensal.

<a id="limites"></a>
## Limites conhecidos

- O computador precisa estar ligado e, no macOS e no Windows, com a sessão aberta. Na tela de login o job não roda, e o próximo `status` avisa há quantos dias o diário está parado. No Linux, `loginctl enable-linger` libera o job sem sessão.
- O `.dmg` e o `Setup.exe` não têm certificado pago (Apple Developer ID, assinatura de código no Windows): na primeira abertura o sistema avisa e pede um clique a mais, descrito em [Instalação](#instalacao). O `Setup.exe` instala, atualiza e desinstala de verdade num Windows a cada push, no CI gratuito do repositório público (job `instaladores-windows`).
- No Windows, a janela própria é o navegador em modo app (Chrome, Edge ou Brave), não um app compilado; o painel no celular (`--painel-rede`) não segura o computador acordado; e os jobs com o Claude Code no Windows sem teste com conta real (prefira o `claude.exe` do instalador oficial ao `claude.cmd` do npm).
- A escrita no Calendar e o envio pelo Gmail dependem do escopo de escrita dos conectores. Confirme com `goal-pacer doctor --sondar-escrita`.
- Se a janela de uso da assinatura esgotar, o job tenta mais uma vez em 30 minutos e depois para até o dia seguinte.
- Um bloco duplicado à mão no Google Calendar não é reconhecido como duplicata.
- A resposta ao email depende do conector do Gmail marcar a mensagem como enviada pela sua conta (label `SENT`); um endereço send-as diferente funciona do mesmo jeito, mas a prova em conta real é o próximo smoke.
- Os arquivos de dados guardam títulos de seção e valores de estado em português em qualquer idioma: são contrato entre os scripts.

<a id="atualizar-e-desinstalar"></a>
## Atualizar e desinstalar

**Atualizar:** `goal-pacer atualizar` (ou `./install.sh --update`) é tudo ou nada:

1. Espera nenhum job estar rodando e recusa um app com mudanças fora de commit.
2. Faz o backup zip da pasta de dados em `dados/backups/`.
3. Traz a versão nova, só se ela for publicada e assinada. Instalação pelo git: busca as tags no GitHub, pega a maior `vX.Y.Z` acima da instalada, confere a assinatura com a lista de `release/assinantes` da versão que já está instalada (a versão nova não troca a lista que a julga) e faz o checkout dela; commit local no app fora da versão nova recusa. Instalação pelo zip: o clique duplo no instalador da pasta da versão nova (manifesto assinado, conferido arquivo por arquivo) ou `goal-pacer atualizar --from ~/Downloads/goal-pacer-vX.Y.Z.zip`, com o `.sig` ao lado; nos dois a cópia anterior fica guardada até o fim. Sem versão nova, nada muda. Precisa do `ssh-keygen` do OpenSSH 8.1 ou mais novo (o do macOS, das distribuições atuais e o Cliente OpenSSH que vem no Windows 10 e 11 servem) e, no clone, de git 2.34 ou mais novo; sem eles o update recusa em vez de pular a conferência.
4. Roda o autoteste do código novo e a migração dos dados (com o próprio backup e volta atrás).
5. Se algo falha: o app volta ao commit ou à cópia anterior, os jobs seguem nela e a mensagem diz o motivo.
6. Se tudo passa: o instalador da versão nova (`--reaplicar`) regrava o agendador, o comando e a janela e fecha as permissões; depois roda o doctor. Assim o que uma versão nova passar a instalar entra sozinho no update.

**Versão instalada:** `goal-pacer versao`. **Voltar uma versão à mão:** `git -C ~/.goal-pacer/app checkout v<versão anterior>` e `goal-pacer doctor`. Para os dados, os zips de `backups/` guardam o estado antes de cada atualização.

**Desinstalar:** `goal-pacer desinstalar` (ou `./install.sh --uninstall`) descarrega os jobs, remove os arquivos do agendador, a janela (`Goal Pacer.app` ou os atalhos do Windows), a ligação da skill e o comando, lista os blocos desta instalação no calendário Metas e pergunta se apaga. Pergunta também se apaga `cache/` e `sinais/`. Metas, planos, dias e registro ficam na pasta de dados. O app fica em `~/.goal-pacer/app` até você apagar a pasta. Sem terminal: em Status, **Remover deste computador** pede confirmação e faz o mesmo (no Windows, pelo desinstalador registrado em Aplicativos), inclusive o `Goal Pacer.app` do `.dmg` e o Python dos jobs; os blocos no calendário ficam (apague pelo terminal com `--apagar-blocos` se quiser).

<a id="configuracao-avancada"></a>
## Configuração avançada

### Variáveis de ambiente

O uso normal não precisa de nenhuma: os argumentos dos CLIs e os arquivos do agendador cuidam disso. Elas existem para os jobs passarem contexto aos passos, para os testes trocarem relógio, pastas e binários, e para quem tem caminhos fora do padrão.

| Variável | Para quê |
|---|---|
| `GP_RAIZ` | raiz da instalação (sem ela: a instalação onde o código está, o que deixa mudar a pasta de lugar; senão `~/.goal-pacer`) |
| `GP_DATA_DIR` | pasta de dados (`--dados` grava aqui) |
| `GP_RUN_ID` | identificador da execução no log e no registro (`--run-id`) |
| `GP_AGORA` | relógio fixo (`--agora`); os jobs nunca usam |
| `GP_TZ` | fuso (`--tz`) |
| `GP_IDIOMA` | idioma das superfícies (`--idioma`) |
| `GP_OFFLINE_DIR` | pasta com as respostas offline dos conectores (fixtures) |
| `GP_CLAUDE_BIN` | caminho do `claude` (os arquivos do agendador gravam o absoluto) |
| `GP_PROVEDOR` | `claude` ou `openai`: provedor de IA, acima do que `install.sh --provedor` gravou |
| `GP_CODEX_BIN` | caminho do `codex` (provedor `openai`) |
| `GP_PROXY_BACKOFF_S` | espera entre tentativas do proxy (os testes zeram) |
| `GP_LOCK_HERDADO` | o passo do job usa o lock que o processo pai já segura |
| `GP_LOCK_ESPERA_S` | quanto o job espera pela pasta de dados ocupada (45 min) |
| `GP_TIMEOUT_JOB_S` | teto do job (20 min; 40 quando encadeia o mensal) |
| `GP_RETRY_SLEEP` | espera antes de repetir um passo que bateu no limite de uso (30 min) |
| `GP_RETRY_EMAIL_S` | espera antes de reenviar o email das 7h (2 min) |
| `GP_GRACA_EMAIL_S` | tempo do email mínimo de falha depois de um estouro do teto (4 min) |
| `GP_SCRIPTS_DIR` | pasta dos scripts que o job roda (testes) |
| `GP_LOGS_DIR` | pasta do registro local (eventos e traces) |
| `GP_TELEMETRIA` | `0` desliga o registro local |
| `GP_LOG_JSON` | `1` escreve o log em JSON |
| `GP_TRACE_ID` | trace do job, passado aos passos |
| `GP_TRACE_PAI` | span pai, passado aos subprocessos |
| `GP_PLATAFORMA` | `macos`, `linux` ou `windows`: força o backend do agendador |
| `GP_LAUNCHCTL` | binário do launchctl (testes) |
| `GP_SYSTEMCTL` | binário do systemctl (testes) |
| `GP_LOGINCTL` | binário do loginctl (testes) |
| `GP_OSASCRIPT` | binário do osascript (testes) |
| `GP_NOTIFY_SEND` | binário do notify-send (testes) |
| `GP_XCODE_SELECT` | binário do xcode-select (testes) |
| `GP_XCRUN` | binário do xcrun que monta o Goal Pacer.app (testes) |
| `GP_GIT` | binário do git do instalador (testes) |
| `GP_ENDERECO_ESCUTA` | endereço de escuta do painel (os testes nunca saem de 127.0.0.1) |
| `GP_IP_REDE` | IP da rede mostrado no pareamento (testes) |
| `GP_OPENSSL` | binário do openssl que gera o certificado do painel na rede |
| `GP_NOME_LOCAL` | nome `.local` mostrado no pareamento (testes) |

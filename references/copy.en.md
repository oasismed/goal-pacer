# Surface strings (en)

Everything the user reads comes from here (design review 7.2), same keys and
`{variables}` as `copy.pt-BR.md` (a test checks both). Tone rules in
`regras.md`, adapted for English in the `tom` group below: no blame, no
pressure, forward-looking verbs, never an "N of M" scoreboard.

## onboarding

### abertura
Let's set up your Goal Pacer in up to 8 questions, one at a time. Each one says why it is being asked. You can stop and pick up later: your answers stay in a draft until the end.

### p1_metas
What do you want to change in the coming months? Name up to 3 end goals and, for each one, the milestones that will take you there (up to 5 in total, each with a short title).
Why: the coach weighs each milestone by how much it moves its goal; without a goal, each milestone counts as its own goal.

### p2_prazos
For each milestone: what is the deadline, is it set by someone else (exam, delivery, event) or by you, and how much does it weigh on the goal: essential, important or supporting?
Why: the deadline sets the expected pace and the horizon (quarter, half or year); the impact says what moves the goal most when time gets tight.

### p3_custo
How many hours per week does each milestone take, and for how many weeks? I looked up references and show the number I found; confirm it or change it.
Why: the monthly plan balances the free hours in your calendar against the hours the milestones ask for. The number you confirm is the one that counts.

### p3_custo_encontrado
For "{titulo}" the research suggests {min} to {max} h/week for {semanas} weeks ({fonte}). Confirm {escolhido} h/week or give another number?

### p3_custo_sem_numero
For "{titulo}" I could not find a reliable number. How many hours per week, and for how many weeks, do you estimate?

### p4_horario_util
At what times do you accept blocks on weekdays, on Saturday and on Sunday? (e.g. 08:00-19:00, 09:00-13:00, none)
Why: only free windows inside these hours become blocks. Outside them, your calendar is yours.

### p5_calendario
In Google Calendar, create a calendar named "Goals" (Settings → Add calendar → Create new calendar), pick a color, and tell me when it is ready. Do you want Google reminders on the blocks? (default: no)
Why: blocks live only in that calendar; Goal Pacer never writes to your main calendar. Deleting or moving a block there is your check-in.

### p5_calendario_nao_encontrado
I could not find a calendar named "Goals" in your account. Create it and let me know; without it Goal Pacer writes nowhere.

### p6_fontes
I found these connected sources: {fontes}. Which ones can I read to find evidence for your milestones? (Gmail and WhatsApp export are the minimum; Notion and Drive are optional)
Why: the monthly plan shows signs of what you have already done (an enrollment email, a Notion page). Summaries only; never the content.

### p7_palavras_chave
Up to 3 keywords per milestone so I can search for that evidence. And, for each goal, why does it matter and how will you know it changed?
Why: the search is by keyword, not by topic; and "how will I know" is the signal the coach looks for beyond the hours.

### p8_email_fuso
Is your email {email} and your time zone {timezone}? The 7am email goes only to you.
Why: email is the only outgoing channel, and every time in the plan is calculated in that time zone.

### rascunho_existente
I found an onboarding draft from {quando} with {n} answers. Continue where you left off, or discard it and start fresh?

### gravado
Saved {n_metas} milestones in metas/, the context in contexto.md and the research in fontes/. Installation {instalacao_id}.

### gravado_objetivos
Saved {n_objetivos} goals in objetivos/, {n_metas} milestones in metas/, the context in contexto.md and the research in fontes/. Installation {instalacao_id}.

### tela_final
Done. Your first email goes out now (and every day at 7am). In the calendar: leave the block = done?, delete it = skipped, move it = reschedule.

### erro_resposta
Could not save: {campo} got {valor}. {motivo}

## checkin

### abertura
Quick check-in. Since last time: {resumo}

### sem_movimento
no block has come due

### p2_quais_fez
Which of these did you do? Mark the ones that count; if you like, say how long it took. Unmarked ones are recorded as not done.

### p_sentimento
How are you feeling about {meta}? Energized, steady or heavy.

### p3_decisao
{meta} needs a decision: {texto}

### p4_progresso
Monday: want to say where each milestone stands (0 to 100)? It counts more than the hour tally when you know better.

### p5_nota
Blocks on {dia} {faixa} rarely happen (rate {pct}%, {n} observations). Add "{restricao}" to your profile?

### fechamento
Recorded:
{mudancas}
The day is rebuilt with this.

### lock_preso
A job is running on the data folder ({detalhe}). Wait for it to finish or cancel it before the check-in.

### restricao
no blocks on {dia} {faixa}

### conta_confirmadas_um
{n} confirmed

### conta_confirmadas_n
{n} confirmed

### conta_presumidas_um
{n} done?

### conta_presumidas_n
{n} done?

### conta_movidas_um
{n} moved

### conta_movidas_n
{n} moved

### conta_reagendadas_um
{n} rescheduled

### conta_reagendadas_n
{n} rescheduled

### conta_apagadas_um
{n} deleted

### conta_apagadas_n
{n} deleted

### mudanca_feita
{task}: confirmed done{duracao}

### mudanca_nao_feita
{task}: skipped

### mudanca_progresso
{meta}: declared progress {pct}%

### mudanca_sentimento
{meta}: feeling {sentimento}

### mudanca_nota
perfil.md: note saved

### mudanca_nota_recusada
note declined (it stays away for {dias} days)

### mudanca_campo
{campo} to {valor}

### mudanca_decisao
{meta}: {saida}{detalhe}

### nada_a_mudar
nothing to change


## diario

### respostas_email
Your email reply went into the check-in: {confirmados} block(s) done, {nao_feitos} to replan.

### efeito
moves: {objetivo} ({impacto})

### resumo
{n} block{s} today, for {metas}.

### resumo_sem_blocos
No free window today.

### resumo_sem_demanda
No blocks today: the milestones are covered this week.

### sem_janela
No free window today. The milestones stay in this week's balance.

### op_parcial
Block {bloco} did not make it into the calendar; try /goal-pacer diario.

### fuso_divergente
You are in {fuso}; working hours applied in that time zone.

### metas_nao_encontrado
Calendar "Goals" not found in the account. Create the calendar in Google Calendar and run /goal-pacer onboarding to register it.

### desinstalar
{n} blocks from this installation {acao} in the Goals calendar.

### porque_template
{meta} asks {horas}h this week; free window at {hora}

### sem_blocos_md
(no blocks)


## plano

### resumo_folgado
In {mes} the calendar has {oferta} free hours and the milestones ask for {demanda} h. Everything fits at the current pace.

### resumo_apertado
In {mes} the calendar has {oferta} free hours and the milestones ask for {demanda} h. The decisions below show where to adjust.

### folgado
The month's supply ({oferta} h) covers the demand of the open weeks ({demanda} h).

### apertado
The demand of the open weeks ({demanda} h) is above the month's supply ({oferta} h).

### meta_coberta
{meta} fits in the month: {demanda} h asked, all with a reserved window.

### meta_fora
{meta} is {estado} and stays out of the allocation.

### decisao
With the windows until {fim} you can cover {pct} of what is left for {meta} this month. Options: reduce · {saida} · keep.

### linha_custo
cost: {h} h/week for {semanas} weeks = {total} h (confidence: {confianca})

### linha_prazo
remaining: {restante} h · deadline {prazo} (external: {externo}) · state: {estado}

### linha_mes
this month: demand {demanda} h · allocated {alocado} h · done {feito} h · coverage {cobertura}

### linha_progresso
progress: {progresso} · expected pace {ritmo}

### linha_decisao
suggested decision: {decisao}

### linha_recalibrar
real pace differs from the cost: set {meta} to {h} h/week? Answer in /goal-pacer mensal.

### oferta_semana
week supply ({inicio} to {fim}): {oferta} free hours

### sim
yes

### nao
no

### progresso_presumido
 (+{pct} done?)

### espelho
Generated mirror of this week's section in planos/{mes}.md; do not edit by hand.

### saida_adiar
postpone to {data}

### saida_renegociar
renegotiate the deadline

### titulo
Plan for {mes}

### titulo_semana
Week {semana} ({inicio} to {fim})


## mensal

### resumo
Balance for {mes} ready: covered {coberta}; adjust {outras}.

### whatsapp_nao_reconhecido
WhatsApp export not recognized; the plan goes ahead without it.

### whatsapp_stale
The WhatsApp export is more than 7 days old; a recent export of the chat goes into the next plan.

### whatsapp_truncado
The WhatsApp export is over 20 MB; only the beginning was read.

### whatsapp_lido
whatsapp: export read on {data} ({status}); you can delete it from inbox/whatsapp.

### leitura_sem_fontes
The sources were not read this month ({classe}); the plan was built from the calendar only.

### leitura_fora_da_lista
Reading the sources called tools outside the allowed list ({tools}); this month's evidence was discarded and the plan was built from the calendar only.

### leitura_fora_dos_tetos
Reading the sources went past the per-milestone limits or searched without excluding the 7am email; the evidence was kept, check cache/auditoria for the month.

### prosa_template
The plan text came from the standard template ({classe}).

### custo_pendente
Confirm the cost of {meta}: its title, horizon or deadline changed since the research.

## email

### assunto
[goal-pacer] {dia} · {blocos}

### assunto_decisao
 · {meta} needs a decision

### assunto_falha
[goal-pacer] {dia} · today's plan is not ready

### blocos_um
1 block

### blocos_n
{n} blocks

### blocos_zero
no blocks

### titulo_decisao
Needs a decision ({meta})

### decisao_resposta
Answer in /goal-pacer checkin.

### titulo_hoje
Today

### mais_blocos
and {n} more in the calendar

### titulo_desde
Since {dia}

### titulo_progresso
How the milestones are going

### comecando
getting started

### linha_objetivo
{objetivo}: {leitura}

### linha_meta
{rotulo} {titulo}: {leitura}

### titulo_avisos
Notes

### titulo_como_funciona
How it works

### gestos
Leave the block in the calendar = done? · delete it = skipped · move it = reschedule.

### link_texto
See the day in Google Calendar

### rodape_comandos
Check-in: /goal-pacer checkin · Status: /goal-pacer status

### numero_bloco
block {n}

### responder
To confirm without opening the calendar, reply to this email with one line per block: 02 done 1h, or 03 skipped.

### decisao_pendente_aviso
{meta} has an open decision in the plan; answer in /goal-pacer checkin.


### falha_corpo
Reason: {motivo}. What to do: {acao}. Yesterday's blocks remain valid.

## desde

### feita_presumida
{titulo} ({meta}): done?

### confirmada
{titulo} ({meta}): confirmed

### nao_feita
{titulo} ({meta}): skipped

### movida
{titulo} ({meta}): moved to {hora}

### reagendada
{titulo} ({meta}): now on {dia} {hora}

### apagada
{titulo} ({meta}): removed from the calendar

### contagem_confirmadas
{n} confirmed

### contagem_presumidas
{n} done?

### contagem_movidas
{n} moved

### contagem_fora
{n} out of the calendar

## falhas

### semonboarding_motivo
the data folder has no milestones
### semonboarding_acao
run /goal-pacer onboarding

### semmetaativa_motivo
no milestone is active
### semmetaativa_acao
reactivate or create a milestone in /goal-pacer onboarding

### grafoinvalido_motivo
a milestone or context file has an invalid field
### grafoinvalido_acao
run validar.py grafo and fix the field it points to

### schemamismatch_motivo
the files are from another version of Goal Pacer
### schemamismatch_acao
run install.sh --update

### cacheinvalido_motivo
the calendar read came back in an unexpected format
### cacheinvalido_acao
run /goal-pacer diario by hand; if it repeats, look at the job log

### numerosalterados_motivo
the plan numbers changed outside the balance
### numerosalterados_acao
run balanco.py --render to rebuild the tables

### metasnaoencontrado_motivo
the Goals calendar does not show up in the account
### metasnaoencontrado_acao
create the Goals calendar in Google Calendar and run /goal-pacer onboarding

### escopoinsuficiente_motivo
the connector has no write permission
### escopoinsuficiente_acao
reconnect Google Calendar and Gmail at claude.ai with write permission

### erroconector_motivo
the connector answered with an error
### erroconector_acao
try /goal-pacer diario in a few minutes

### toolnegada_motivo
a tool was denied by the job configuration
### toolnegada_acao
run status.py --doctor and look at the connectors item

### turnosesgotados_motivo
the Claude session went past its number of turns
### turnosesgotados_acao
try /goal-pacer diario by hand

### respostainvalida_motivo
the connector response came in an unexpected format
### respostainvalida_acao
try /goal-pacer diario in a few minutes

### mcpnaocarregado_motivo
the Claude connectors did not load in time
### mcpnaocarregado_acao
try /goal-pacer diario in a few minutes

### ratelimited_motivo
the subscription usage window ran out
### ratelimited_acao
the job tries on its own later; or run /goal-pacer diario after the usage window reopens

### registrocorrompido_motivo
registro.json could not be read
### registrocorrompido_acao
run registro.py recuperar

### locktimeout_motivo
another job held the data folder for too long
### locktimeout_acao
run status.py --doctor and delete the stale lock if it shows up

### binarymissing_motivo
the claude or python3 executable was not found
### binarymissing_acao
run install.sh --check

### sessiontimeout_motivo
the job went past its time limit
### sessiontimeout_acao
run /goal-pacer diario by hand and check the duration in status

### desconhecida_motivo
an unexpected error stopped the job
### desconhecida_acao
look at the job log in ~/.goal-pacer/jobs/logs

## status

### cabecalho
Goal Pacer · status · {quando}

### nunca_rodou
No daily run on record. Next: {proximo}. To see it now: /goal-pacer diario

### silencio
The last daily run was {dias} days ago ({quando}). If the computer was off or at the login screen at 7am, run /goal-pacer diario.

### proximo
Next daily run: {proximo}

### titulo_pendencias
Waiting on you

### sem_pendencias
Nothing waiting for an answer.

### decisao
{meta}: {texto} Answer in /goal-pacer checkin.

### presumidas
{n} "done?" block(s) from the last 14 days to confirm in /goal-pacer checkin: {ids}

### ultimo_job
Last job: {motivo}. What to do: {acao}.

### titulo_progresso
How the milestones are going

### sem_metas
No active milestone. To add one: /goal-pacer onboarding

### titulo_cobertura
Coverage for {mes}

### cobertura_mes
supply {oferta} h · demand {demanda} h · coverage {cobertura}

### cobertura_meta
{meta} {cobertura} · {decisao}

### sem_plano
No plan for {mes}. To build it: /goal-pacer mensal

### titulo_perfil
Profile

### perfil_base
based on {n} confirmed

### perfil_presumidas
{horas} h presumed and not counted ({metas})

### perfil_janelas
completion by time slot: {faixas}

### perfil_fator
{meta} takes {fator}× the planned time per block

### titulo_evidencias
Evidence from the last 30 days

### sem_evidencias
No evidence read in the last 30 days.

### titulo_execucoes
Recent runs

### sem_execucoes
No runs recorded.

### execucao_ok
ok

### progresso_declarado
{meta}: declared progress {pct}%

### decisao_manter
keep

### decisao_reduzir
reduce

### decisao_adiar
postpone

### decisao_renegociar
renegotiate

### celula
{dia} {faixa}


## doctor

### titulo
Goal Pacer · doctor · {quando}

### ok
OK

### falhou
FAILED

### resumo_ok
All {n} items look good.

### resumo_acao
{n} item(s) need action; what to do is on each line.

### item_dados
data folder

### dados_ok
{pasta} (schema_version {versao})

### dados_sem_pasta
{pasta} does not exist: run install.sh and then /goal-pacer onboarding

### dados_sem_contexto
{pasta} has no contexto.md: run /goal-pacer onboarding

### dados_versao
schema_version {atual}, expected {esperado}: run install.sh --update

### dados_invalidos
{erro}: run python3 scripts/validar.py grafo and fix the file it points to

### dados_registro
{erro}: run python3 scripts/registro.py recuperar

### item_lock
data folder lock

### lock_livre
free

### lock_ativo
job running (pid {pid}, {minutos} min)

### lock_obsoleto
forgotten lock (pid {pid}, {minutos} min): delete {caminho}

### item_jobs
scheduled jobs

### jobs_ok
{labels} loaded in {agendador}

### jobs_sem_linger
{labels} loaded in {agendador}; without linger they only run while your session is open (loginctl enable-linger)

### jobs_faltando
{labels} not in {agendador}: run ./install.sh

### jobs_sem_agendador
{agendador} unavailable ({erro}): run it with your session open

### item_claude
claude

### claude_ok
{caminho} ({versao})

### claude_relativo
{caminho} is not an absolute path: run install.sh --check

### claude_ausente
{caminho} not found: install Claude Code or set GP_CLAUDE_BIN

### item_codex
codex

### codex_ausente
{caminho} not found: install the Codex CLI and run codex login, or set GP_CODEX_BIN

### item_python
python3

### python_ok
{caminho} ({versao}){extra}

### python_velho
{caminho} ({versao}): use python3 3.9 or newer

### python_sem_xcode
{caminho} ({versao}) without Xcode Command Line Tools: run xcode-select --install

### item_conectores
connectors

### conectores_ok
Calendar and Gmail connected; Goals calendar found; {escrita}

### conectores_sem_onboarding
Calendar and Gmail connected; the Goals calendar is checked after onboarding

### conectores_opcionais
no connector is required; Google Calendar and Gmail on claude.ai put the blocks on your calendar and send the 7am email

### conectores_nenhum
no connectors: goals, plan and day come from what you wrote; connect Google Calendar and Gmail on claude.ai whenever you want to go deeper

### conectores_so_email
Gmail connected; without Google Calendar, the blocks stay in the app

### conectores_provedor
Calendar and Gmail through {provedor} come after the spike; today they work with the claude provider

### conectores_formato
claude mcp list in an unrecognized format: run claude mcp list and check the connectors

### conectores_mcp
{servidores} not Connected in claude mcp list: reconnect them at claude.ai, on the connectors screen

### conectores_sem_metas
Goals calendar ({id}) does not show up in list_calendars: create the calendar or redo the onboarding

### conectores_leitura
list_calendars: {erro}

### escrita_nao_testada
writing not tested (use --sondar-escrita)

### escrita_ok
writing tested on Goals and Gmail

### escrita_escopo
{servidor} has no write permission ({erro}): reconnect at claude.ai with writing allowed

### escrita_sobra
{servidor} created the probe but did not delete it ({erro}): delete "{titulo}" by hand

### item_ultimo
last job

### ultimo_ok
{run_id} · exit 0 · {idade} ago

### ultimo_erro
{run_id} · {classe} · exit {codigo} · {idade} ago: {acao}

### ultimo_velho
{run_id} · {idade} ago: check that the computer is on at 7am or run {comando}

### ultimo_nenhum
no job has run: run {comando}

### sonda_titulo
[GP] Goal Pacer write probe

### sonda_descricao
Test event from status --doctor; it is deleted right away.

### sonda_assunto
[goal-pacer] write probe

### sonda_corpo
Test draft from status --doctor; it goes to the trash right away.

### python_xcode
; Xcode CLT at {caminho}

### item_seguranca
permissions

### seguranca_ok
data and logs are yours only; only you can change the jobs' code

### seguranca_pasta_aberta
{caminho} is open to other users ({modo}): run chmod 700 {caminho}

### seguranca_arquivo_aberto
{caminho} is readable by other users ({modo}): run chmod 600 {caminho}

### seguranca_codigo_alteravel
{quantos} app path(s) other users can change (e.g. {caminho}): run chmod -R go-w {app}

### seguranca_codigo_de_outro
{quantos} app path(s) owned by someone else (e.g. {caminho}): reinstall without sudo using ./install.sh

### seguranca_agendador_alteravel
{caminho} can be changed by other users ({modo}): run chmod 644 {caminho}

### seguranca_skill_desviada
the skill {caminho} points to {alvo}, not to {app}: run ./install.sh

### seguranca_mais
; and {n} more


## instalar

### inicio
Installing Goal Pacer in {raiz}

### pergunta_dados
Data folder [{padrao}]:

### app_clonado
app: clone of {origem} in {app}

### app_copiado
app: copy of {origem} in {app}

### app_existente
app: {app} already exists; to bring the new version use ./install.sh --update

### origem_suja
note: {origem} has uncommitted changes; the clone takes only the last commit (use --copiar to take the working tree)

### skill
skill: {link} points to {app}

### dados
data: {dados}

### agendamento
jobs: {arquivos}

### painel_rede
dashboard: up at http://127.0.0.1:{porta}/ and on your home Wi-Fi; open it on the computer to see the address and the phone pairing code

### painel_desligado
dashboard: login agent turned off

### painel_local
dashboard: up at {endereco}, it starts at every login; your browser can install it as an app

### agendador_ok
{agendador}: {labels} loaded

### agendador_aviso
note: {agendador} did not load {label}; run ./install.sh --check with your session open

### sem_agendar
{agendador}: jobs not loaded (--sem-agendar)

### pronto
Done. Next steps: open the dashboard and follow the Get started screen (or run /goal-pacer onboarding in Claude Code); then {comando} doctor to check everything.

### check_titulo
Installation check

### update_ok
Updated to version {app_versao} ({revisao}); schema v{versao}; jobs reloaded.

### update_sem_instalacao
No installation in {raiz}: run ./install.sh first.

### update_git
git in {app} did not bring version {tag} ({erro}); nothing changed. To try once more: goal-pacer atualizar.

### update_tag
new version: {tag}, signed by the Goal Pacer publisher

### update_em_dia
Already on the newest published version ({versao}); nothing changed.

### update_recusado
Update refused: {motivo}. Nothing changed.

### update_zip_assinado
{arquivo}: signature from {assinante} verified

### update_canal
new version on the channel: {versao}; downloading the zip and its signature

### update_pasta_assinada
version {versao}: manifest signed by {assinante} verified, and every file matches it

### update_pasta_antiga
This folder holds version {versao}, older than the installed one ({instalada}): nothing changes.

### claude_ausente
Claude Code: not found on this computer. Installation continues; the jobs use {caminho} as soon as you install it (the dashboard's Get started screen shows how).

### fusos_ok
time zones: IANA database (tzdata) in {pasta}

### runtime_copiado
python: the app's Python copied to {pasta} (the jobs do not depend on where the app is)

### fusos_erro
Could not download the time zone database (tzdata) with pip: {erro}. Check the internet connection and double-click the installer once more.

### update_sem_assinatura
warning: {origem} is a folder with no signature to verify; use it only for development (to install, use the release zip with its .sig)

### update_copia_sem_origem
The installation is a copy: download the new version's zip from the release page, unzip it and double-click Instalar Goal Pacer (or run goal-pacer atualizar --from <file.zip>, with the .sig next to it).

### update_lock
A job is using the data folder ({erro}); run ./install.sh --update when it finishes.

### update_migrar
{erro}

### uninstall_agendador
{agendador}: {labels} unloaded and removed

### uninstall_sem_agendador
{agendador}: no Goal Pacer job loaded

### janela_ok
window app: {app} (open it from Launchpad or Applications)

### janela_ok_windows
window: {app} (open it from the Start menu: Goal Pacer)

### janela_sem_swift
window app: the Swift compiler from the Command Line Tools is missing; the dashboard stays in the browser (xcode-select --install, then run ./install.sh once more)

### janela_erro
window app: could not build it ({erro}); the dashboard stays in the browser

### uninstall_janela
window app: {app} removed

### uninstall_skill
skill: {link} removed

### uninstall_blocos_pergunta
{n} block(s) from this installation are in the Goals calendar. Delete them now? [y/N]

### uninstall_blocos
Goals calendar: {n} block(s) deleted

### uninstall_blocos_mantidos
Goals calendar: blocks kept (to delete later: ./install.sh --uninstall --apagar-blocos)

### uninstall_blocos_erro
Goals calendar: blocks kept ({erro})

### uninstall_cache_pergunta
Also delete cache/ and sinais/ from the data folder? [y/N]

### uninstall_cache
data: cache/ and sinais/ deleted

### uninstall_fim
Uninstalled. Your milestones, plans and records remain in {dados}; the app remains in {app} (you can delete that folder).

### autoteste_ok
self-test: {n} checks in {segundos} s with python {python}; no connectors and no tokens

### autoteste_erro
self-test: {erro}

### update_app_sujo
The app in {app} has uncommitted changes; nothing changed. Move those changes out of the app (git -C {app} stash) and run ./install.sh --update.

### update_reaplicar
The new code is in place, but the agents and the window app were not rebuilt ({erro}); run ./install.sh in the app folder to finish.

### update_backup
data: backup in {backup}

### update_autoteste
new version checked by the self-test and the data schema

### update_desfeito
Update undone: the app went back to the previous version and the jobs keep running on it ({motivo}).

### comando
command: goal-pacer (in {pasta})

### comando_fora_do_path
command: {shim}; to call just goal-pacer, add {pasta} to your PATH

### uninstall_comando
command: {comando} removed

### uninstall_nao_apagados
not deleted: {ids}

### origem_sem_git
{origem} is not a git clone (or git is not available): the app is installed by copy; to update later download the new release zip and .sig and run goal-pacer atualizar --from <file.zip>

### origem_publicada
published version in {origem}: the app is installed by copy; to update, open the new version's installer (the .dmg app, the Setup.exe or the zip folder)


## comando

### uso
Usage: goal-pacer <command> [arguments]

### status
how the milestones are going, what waits on you and recent runs

### doctor
checks the installation item by item, with what to do

### painel
opens the dashboard in the browser (--rede for your phone)

### diario
rebuilds the day with the calendar as it is now

### mensal
rebuilds the month balance and reads outside signals

### checkin
check-in from the terminal (the skill leads the questions)

### validar
validates the data folder

### autoteste
checks, with no connectors and no tokens, that the code runs on this machine

### atualizar
brings the new version with backup, self-test and rollback if needed

### desinstalar
removes jobs, skill and command; milestones and records stay

### versao
version, schema, platform and language

### ajuda
this list

### versao_linha
Goal Pacer {versao} ({revisao}) · schema v{schema_version} · {plataforma} · {lingua} · python {python}

### desconhecido
There is no {nome} command.

### logs
time per screen and per connector, events and last job trace (read only)


## painel

### titulo_pagina
Goal Pacer

### manchete_zero
No blocks today.

### manchete_um
One block today.

### manchete_n
{n} blocks today.

### manchete_feitos_um
One already confirmed.

### manchete_feitos_n
{n} already confirmed.

### manchete_todos
All confirmed.

### atualizar
Refresh

### hoje_titulo
Today

### hoje_detalhe
in the Goals calendar

### hoje_detalhe_app
in the app, without Google Calendar

### sem_blocos
No blocks for today. The 7am run fits the next ones into free windows.

### confirmar
Confirm {titulo}

### confirmada
Confirmed

### feita_presumida
done?

### desde
Since {dia}

### cobertura_texto
{oferta} free hours in the calendar for {demanda} h asked by the milestones.

### sem_plano
No plan for {mes}. The 7am run builds the plan, or run /goal-pacer mensal.

### decisao_titulo
{meta} needs a decision

### saida_reduzir
Reduce

### saida_adiar
Postpone

### saida_renegociar
Renegotiate the deadline

### saida_manter
Keep

### custo_rotulo
New hours per week

### prazo_rotulo
New deadline

### aplicar
Apply

### decisao_aplicada
{meta} adjusted. The next daily run rebuilds the plan with the new number.

### decisao_mantida
{meta} stays as it is.

### avisos_titulo
Notes

### erro_carregar
The data did not load: {erro}. Check that the dashboard is open in the terminal.

### erro_acao
{erro}

### job_em_andamento
A job is using the data folder; try in a few minutes.

### rodape
Local dashboard at {endereco}.

### parear_titulo
Pair this device

### parear_texto
Type the 6-digit code shown on the dashboard open on the computer, in the Open on your phone card.

### parear_codigo
Pairing code

### parear_botao
Pair

### parear_errado
That code does not match. Check it on the computer dashboard.

### parear_bloqueado
Too many tries with a wrong code. Restart the dashboard on the computer to allow pairing.

### parear_rodape
Goal Pacer runs on the computer at your home. Nothing in this dashboard leaves the local network.

### rede_titulo
Open on your phone

### rede_detalhe
same Wi-Fi

### rede_passos
On your phone, open the address below, type the code and, in Safari, tap Share and Add to Home Screen.

### rede_codigo
code

### rede_aparelhos_zero
No paired devices.

### rede_aparelhos_um
1 paired device.

### rede_aparelhos_n
{n} paired devices.

### rede_esquecer
Forget devices

### rede_esquecidos
Devices forgotten. Each one asks for the code the next time it opens.

### rede_sem_endereco
Could not find this computer's address on the network. Check that Wi-Fi is on.

### rede_terminal
On your phone, on the same Wi-Fi: {endereco} with the code {codigo}.

### rede_aviso
The local network has no encryption: use the dashboard on your phone only on your home Wi-Fi.

### rede_impressao
Encrypted connection. The first time, your phone warns that it does not know the certificate: check that the SHA-256 fingerprint in the details is {impressao} and continue.

### demo_selo
Sample data

### nav_rotulo
Dashboard sections

### nav_hoje
Today

### nav_objetivos
Goals

### nav_metas
Milestones

### nav_mes
Month

### nav_checkin
Check-in

### nav_status
Status

### aneis_titulo
How the journey is going

### aneis_detalhe
presence, pace and direction

### objetivos_card
Your goals

### objetivos_card_detalhe
strength of each one

### alavanca_titulo
What moves things most now

### abrir_meta
Open {meta}

### metas_card
Milestones

### metas_card_detalhe
state and journey

### ver_todas
See all

### espaco_titulo
Room in {mes}

### espaco_detalhe
does the calendar hold the milestones?

### nao_fiz
Skipped

### fiz
Done

### nao_feita
skipped

### bloco_movida
moved

### bloco_apagada
deleted

### bloco_reagendada
rescheduled

### nao_feita_ok
Noted. The plan goes on with the next blocks.

### objetivos_pagina
Goals

### objetivos_sub
What you want to change and how much each milestone moves each goal.

### por_que
Why

### como_vou_saber
How I will know

### move_titulo
What moves this goal

### move_legenda
width: milestone impact on the goal · filled part: traction and progress

### metas_pagina
Milestones

### metas_sub
The impact of each milestone on your goals and the traction it has now.

### mapa_titulo
Energy map

### mapa_detalhe
impact by traction

### mapa_tracao
traction

### mapa_pouca
low

### mapa_boa
good

### lista_titulo
All milestones

### jornada
Journey

### prazo_data
deadline {data}

### prazo_externo
external deadline

### sentimento_titulo
How are you feeling about this milestone?

### sentimento_nenhum
no recent answer

### sentimento_ok
Noted for {meta}.

### voltar_metas
All milestones

### leitura_titulo
Coach reading

### marcos_titulo
Checkpoints

### sem_marcos
No checkpoints for now. Write them in metas/{meta}.md, in the Marcos section.

### marco_feito
Checkpoint reached.

### marco_aberto
Checkpoint reopened.

### trilha_titulo
Traction over the last 6 weeks

### trilha_detalhe
presence and flow per week

### trilha_sem
week without blocks

### sinais_titulo
Signals

### sinais_detalhe
what goes into the reading

### ajustes_titulo
Adjustments

### ajustes_detalhe
the next daily run rebuilds the plan

### horas_rotulo
Hours per week

### prazo_campo
Deadline

### impacto_rotulo
Impact on the goal

### objetivo_rotulo
Goal

### sem_objetivo
No goal set

### salvar
Save adjustments

### pausar
Pause milestone

### retomar
Resume milestone

### concluir
Mark as achieved

### ajuste_ok
{meta} adjusted. The next daily run rebuilds the plan with the new number.

### ajuste_igual
{meta} is already set that way.

### numeros_titulo
Balance numbers

### numeros_detalhe
to decide, not to judge

### num_custo
hours per week

### num_semanas
estimated weeks

### num_total
total cost

### num_feito
confirmed so far

### num_cobertura
coverage this month

### num_decisao
suggested decision

### recentes_titulo
Recent blocks

### proximos_titulo
Next blocks

### sem_recentes
No blocks in recent weeks.

### sem_proximos
The next blocks come with the 7am run.

### evidencias_titulo
Outside signals

### sem_evidencias
No outside signals this month.


### resumo_titulo
Month reading

### semanas_titulo
Room per week

### semanas_detalhe
height: how much of the free time the milestones ask for

### oferta_demanda
{oferta} free hours · {demanda} h asked


### decisoes_titulo
Decisions


### checkin_sub
Two minutes: what you did, how each milestone feels and what to decide.

### passo_feitos
What you did

### passo_feitos_detalhe
last 7 days

### sem_pendentes
Everything confirmed for the last 7 days.

### passo_sentir
How each milestone feels

### passo_sentir_detalhe
energized, steady or heavy

### passo_nota
A note for the coach

### passo_nota_detalhe
optional, goes to your profile

### nota_exemplo
E.g.: early mornings work better than evenings.

### salvar_checkin
Save check-in

### checkin_ok
Check-in saved. The next daily run uses what you marked.

### salvar_dica
Nothing is saved until you press save.

### checkin_vazio
Mark a block, a milestone or write a note before saving.

### nav_conexoes
Connections

### conexoes_sub
The connectors Goal Pacer uses and the sources that feed the month's signals.

### provedor_titulo
AI provider

### provedor_texto
{provedor}, through the login you already have.

### onde_claude
Connect and reconnect at claude.ai, on the connectors screen. Goal Pacer never asks for a password or a login of its own.

### onde_openai
Connect and reconnect in the ChatGPT apps. Goal Pacer never asks for a password or a login of its own.

### verificado_em
Last checked by doctor on {data}.

### nunca_verificado
Run doctor in the terminal to see the state of each connection.

### comando_verificar
goal-pacer doctor --sondar-escrita

### comando_verificar_texto
checks the connectors, the Goals calendar and writing

### problema_reconexao
The job on {data} stopped at {classe}: {acao}

### conexoes_lista_titulo
Connections

### conexoes_lista_detalhe
the dashboard only shows them: doctor and the jobs do the checking

### conexao_calendar
Google Calendar

### conexao_gmail
Gmail

### conexao_notion
Notion

### conexao_drive
Google Drive

### conexao_whatsapp
WhatsApp

### papel_obrigatoria
used every day

### papel_fonte
signal source

### papel_obrigatoria_fonte
used every day and a signal source

### estado_conectado
connected

### estado_reconectar
reconnect

### estado_desconectado
not connected

### estado_sem_verificacao
not checked

### estado_com_export
export found

### estado_sem_export
no export

### estado_provedor
after the spike

### linha_visto
seen by doctor on {data}

### linha_uso
answered in the job on {data}

### linha_metas_ok
Goals calendar found

### linha_metas_ausente
Goals calendar missing from the list: create it or redo onboarding

### linha_escrita
writing tested on {data}

### linha_lida
read in the monthly run on {data}

### linha_nao_lida
no reading recorded in the signals

### linha_export
latest export on {data} ({n} in total)

### linha_sem_export
export the chat without media to inbox/whatsapp/ in the data folder

### linha_provedor
Calendar, Gmail, Notion and Drive through {provedor} come after the spike

### fonte_nos_sinais
in the month's signals

### fonte_fora_dos_sinais
out of the month's signals

### fonte_usar
Use in signals

### fonte_tirar
Remove from signals

### fonte_entra
{fonte} joins the next monthly reading.

### fonte_sai
{fonte} leaves the next monthly reading.

### fonte_igual
{fonte} was already set that way.

### outros_titulo
Other connectors

### outros_texto
Goal Pacer uses only these connectors, each call in an isolated session, and no reading of third-party content happens together with writing. A new source comes in through the sources extension point (README, Modules and extension points).

### status_sub
Daily job runs, settings and devices.

### execucoes_titulo
Runs

### execucoes_detalhe
most recent first

### sem_execucoes
No runs recorded.

### execucao_ok
ok

### proximo_job
Next daily run: {quando}.

### tokens
{n} tokens

### segundos
{n} s

### config_titulo
Settings

### fuso_rotulo
Time zone

### horario_rotulo
Working hours

### fontes_rotulo
Signal sources

### cadastro_rotulo
Setup

### cadastro_texto
{metas} active milestones · {objetivos} goals

### comandos_titulo
In the terminal

### comandos_detalhe
the dashboard does not call connectors

### comando_diario
/goal-pacer diario

### comando_diario_texto
rebuilds the day with the calendar as it is now

### comando_mensal
/goal-pacer mensal

### comando_mensal_texto
rebuilds the month balance and reads outside signals

### comando_doctor
python3 scripts/status.py --doctor

### comando_doctor_texto
full diagnosis: jobs, connectors and last job

### rede_desligada
Dashboard open on this computer only. To use it on your phone, start it with web.py --rede.

### rede_so_mac
The pairing code shows up only on the computer.

### nav_horizontes
Horizons

### nivel_dia
Day

### nivel_semana
Week

### nivel_mes
Month

### nivel_trimestre
Quarter

### nivel_semestre
Half

### nivel_ano
Year

### niveis_rotulo
Horizon level

### trilha_rotulo
Where you are

### periodo_semestre
H{n} {ano}

### periodo_semestre_curto
H{n}

### periodo_trimestre
Q{n} {ano}

### periodo_trimestre_curto
Q{n}

### periodo_mes
{mes} {ano}

### periodo_semana
Week {n} · {ano}

### periodo_semana_curto
Week {n}

### periodo_intervalo
{de} to {ate}

### fase_passado
Closed

### fase_atual
Now

### fase_futuro
Ahead

### anterior
Previous period

### proximo
Next period

### dia_anterior
Previous day

### dia_seguinte
Next day

### voltar_hoje
Back to today

### partes_semestre
Halves

### partes_trimestre
Quarters

### partes_mes
Months

### partes_semana
Weeks

### partes_dia
Days

### partes_detalhe
open one to go down a level

### leitura_periodo
Period reading


### tempo_detalhe
outer ring: time elapsed · inner ring: the reading

### metas_do_trimestre
Quarter milestones

### metas_do_semestre
Half-year milestones

### metas_do_ano
Year milestones

### sem_metas_nivel
No milestone with this horizon in this period.

### metas_acima
Larger milestones that pass through here

### metas_abaixo
Smaller milestones inside this period

### metas_em_jogo
Milestones this period serves

### prazo_aqui
deadline here

### prazos_um
one deadline

### prazos_n
{n} deadlines



### sem_blocos_dia
no blocks

### horizonte_meta_trimestre
quarter milestone

### horizonte_meta_semestre
half-year milestone

### horizonte_meta_ano
year milestone

### nav_comecar
Get started

### comecar_sub
Five steps for Goal Pacer to plan your week. You can close and come back: each step is saved.

### comecar_sub_pronto
Your goals are saved.

### comecar_passos
Getting started steps

### comecar_passo_conta
Account

### comecar_passo_metas
Goals

### comecar_passo_horario
Hours

### comecar_passo_fontes
Sources

### comecar_passo_conferir
Review

### comecar_conta_titulo
Your account

### comecar_conta_detalhe
Goal Pacer uses your Claude, with no new password. Connecting Google is optional: it deepens the context.

### comecar_req_claude
Claude Code installed and signed in with a Pro or Max plan.

### comecar_req_conectores
Optional: Google Calendar and Gmail connected on claude.ai, with write access, for blocks on your calendar and the 7am email.

### comecar_req_calendario
Optional, with Google Calendar: a calendar named Goals, the only one Goal Pacer writes to.

### comecar_link_claude
How to install Claude Code

### comecar_link_conectores
Open Connectors on claude.ai

### comecar_link_calendario
Create the calendar

### comecar_claude_ok
Claude Code found on this computer.

### comecar_claude_falta
Claude Code is missing on this computer.

### comecar_claude_titulo
Claude Code

### comecar_claude_logado
Claude Code installed and signed in.

### comecar_claude_logado_plano
Claude Code installed and signed in ({plano} plan).

### comecar_claude_sem_login
Claude Code installed, sign-in pending.

### comecar_claude_instalando
Installing Claude Code: this screen checks on its own when it finishes.

### comecar_instalar_claude
Install Claude Code

### comecar_login_claude
Sign in

### comecar_login_instrucao
Sign in with your Claude account on the page that opened in the browser. At the end it shows a code: copy it and paste it here.

### comecar_login_link
Open the sign-in page

### comecar_login_codigo
Code from the sign-in page

### comecar_login_entrar
Sign in

### comecar_login_ok
Signed in: Claude Code is ready on this computer.

### comecar_login_recusado
The sign-in did not go through ({erro}). Ask for a new code with Sign in and paste it.

### comecar_login_expirado
The sign-in page expired: click Sign in to open a new one.

### comecar_login_codigo_invalido
Paste the whole code the sign-in page showed.



### comecar_conectores_titulo
Connectors (optional)

### comecar_conectores_opcionais
With no connector, goals, plan and day come only from what you write. With Google Calendar and Gmail, blocks go to your calendar, the email arrives at 7am and the check-in is inferred; Notion and Drive bring evidence. This screen checks on its own while you connect.

### comecar_conector_conectado
connected

### comecar_conector_reconectar
needs reconnection

### comecar_conector_desconectado
not connected

### comecar_chaveiro
If the Mac asks for Keychain access for claude, choose Always Allow: that is what lets the 7am job run on its own.

### vazio_titulo
No goals for now

### vazio_texto
The screens show what exists, and this stays empty until the first goal. Get started takes you to your first day in a few minutes.

### vazio_acao
Go to Get started

### comecar_conferir
Check my account

### comecar_conferir_de_novo
Check once more

### comecar_conferindo
Checking, it takes a minute...

### comecar_email_ok
Email found: {email}

### comecar_email_falta
No sent email found for the account: you confirm the address in the last step.

### comecar_metas_ok
Goals calendar found.

### comecar_metas_falta
No Goals calendar: the blocks stay in the app. To see them in Google Calendar, create a calendar with that name.

### comecar_fontes_achadas
Sources available: {fontes}

### comecar_continuar
Continue

### comecar_voltar
Back

### comecar_metas_titulo
Your goals

### comecar_metas_detalhe
Up to 5 goals. Give the deadline and how many hours a week each one takes; the rest follows from that.

### comecar_meta_n
Goal {n}

### comecar_meta_titulo
What you want to reach

### comecar_meta_exemplo
E.g.: run 10 km

### comecar_meta_prazo
Deadline

### comecar_meta_horas
Hours per week

### comecar_meta_horas_ajuda
An honest number. You can adjust it later on the goal screen.

### comecar_meta_impacto
Weight on the objective

### comecar_meta_objetivo
Objective (optional)

### comecar_meta_objetivo_ajuda
What changes when the goal happens. Goals with the same objective move together.

### comecar_objetivo_exemplo
E.g.: better health

### comecar_meta_externo
The deadline comes from outside (someone else or an event set it)

### comecar_tirar_meta
Remove this goal

### comecar_mais_meta
One more goal

### comecar_sem_metas
Write at least one goal with a title, a deadline and hours.

### comecar_horario_titulo
Your working hours

### comecar_horario_detalhe
When blocks can go on the calendar, as 09:00-18:00. Left blank, the day stays free.

### comecar_horario_seg_sex
Monday to Friday

### comecar_horario_sab
Saturday

### comecar_horario_dom
Sunday

### comecar_horario_vazio
no blocks

### comecar_fontes_titulo
Where the signals are

### comecar_fontes_detalhe
At the start of each month Goal Pacer reads only what you tick here, read-only, to find signs of progress.

### comecar_palavras_titulo
Keywords

### comecar_palavras_detalhe
Up to 3 per goal, separated by commas. It is what the monthly read looks for.

### comecar_palavras_exemplo
E.g.: training, running, pace

### comecar_lembretes
Google Calendar reminder on each block

### comecar_conferir_titulo
Review and save

### comecar_conferir_detalhe
The email gets the 7 am summary; the time zone sets when blocks happen.

### comecar_email
Your email

### comecar_fuso
Time zone

### comecar_idioma
Language

### comecar_gravar
Save my goals

### comecar_pronto_titulo
All set

### comecar_pronto_detalhe
The first day comes with the daily job, at 7 am.

### comecar_pronto_texto
To see it now, build the first day: Goal Pacer writes the monthly plan, fits the blocks into the Goals calendar and sends the email. It takes a few minutes.

### comecar_pronto_texto_app
Your first day is being built: Goal Pacer writes the monthly plan and fits the blocks into your hours. It shows up in Today in a few minutes.

### comecar_pronto_sem_instalacao
This dashboard is not from an installation: run the installer so the day comes by itself at 7 am.

### comecar_primeiro_dia
Build my first day now

### comecar_ir_hoje
Open Today

### app_titulo
Goal Pacer as an app

### app_detalhe
An icon that opens the dashboard in its own window.

### app_ja_instalado
You are using the app.

### app_instalar
Install the app

### app_chrome
Chrome or Edge: click the install icon at the end of the address bar.

### app_mac
On the Mac, the Goal Pacer app opens the dashboard in its own window: find it in Applications or Launchpad.

### app_windows
On Windows, Goal Pacer opens the dashboard in its own window: search for Goal Pacer in the Start menu.

### app_safari
Safari: File menu > Add to Dock.

### manutencao_titulo
Maintenance

### manutencao_detalhe
Version {versao}. On this computer only.

### manutencao_doctor
Check installation

### manutencao_conferindo
Checking the installation, it takes a minute...

### manutencao_atualizar
Look for an update

### manutencao_remover
Remove from this computer

### manutencao_remover_explica
Removes the jobs, the dashboard, the shortcuts and the app from this computer. Your goals, plans and log stay in the data folder, for a future installation.

### manutencao_remover_sim
Remove now

### manutencao_removendo
Removing Goal Pacer. This screen goes offline in a moment; your data stays in {dados}.

### manutencao_versao_nova
Version {versao} is available: Check for update downloads, verifies and applies it.

### acao_no_exemplo
This action is off in the sample dashboard.

### comecar_corrigir
Some fields need a change before saving.

### comecar_gravado
Goals saved.

### comecar_sem_rascunho
Nothing answered so far: start with the Goals step.

### comecar_sem_instalacao
This dashboard is not from an installation: run the installer first.

### comecar_primeiro_dia_ok
First day on its way: the email arrives in a few minutes.

### comecar_primeiro_dia_erro
The scheduler did not start the day ({erro}).

### atualizar_pelo_zip
Installed from the downloaded folder: download the new version's zip, unzip it and double-click Instalar Goal Pacer.

### atualizar_em_andamento
An update is running.

### atualizar_iniciado
Looking for an update. The dashboard restarts if there is a new version.

## coach

### estado_florescendo
Flourishing

### estado_ritmo
Finding its pace

### estado_atencao
Needs attention

### estado_travada
Stuck

### estado_pausada
Paused

### estado_conquistada
Achieved

### estagio_comeco
Start

### estagio_construcao
Building

### estagio_consolidacao
Consolidating

### estagio_reta_final
Home stretch

### estagio_conquista
Achievement

### objetivo_firme
Moving steadily

### objetivo_construcao
Taking shape

### objetivo_foco
Needs focus

### objetivo_pausado
Paused

### objetivo_conquistado
Achieved

### tendencia_acelerando
speeding up

### tendencia_estavel
steady

### tendencia_desacelerando
slowing down

### tendencia_sem_sinal
no trend for now

### impacto_essencial
Essential

### impacto_importante
Important

### impacto_apoio
Supporting

### sentimento_energia
Energized

### sentimento_firme
Steady

### sentimento_pesada
Heavy

### quadrante_proteger
Protect

### quadrante_proteger_texto
high impact and good traction: keep the time slot that works

### quadrante_destravar
Unblock

### quadrante_destravar_texto
high impact and low traction: a small step pays off most here

### quadrante_manter_leve
Keep it light

### quadrante_manter_leve_texto
good traction and smaller impact: carry on without asking for more time

### quadrante_repensar
Rethink

### quadrante_repensar_texto
smaller impact and low traction: worth reducing, postponing or pausing

### sinal_presenca
Presence

### sinal_fluidez
Flow

### sinal_energia
Energy

### sinal_evidencia
Outside signals

### sinal_espaco
Room in the calendar

### sinal_avanco
Progress

### presenca_alto
showing up consistently for the blocks

### presenca_medio
showing up for part of the blocks

### presenca_baixo
few blocks done in recent weeks

### presenca_sem_sinal
no past blocks to read

### fluidez_alto
fits well into the routine

### fluidez_medio
sometimes changes place in the calendar

### fluidez_baixo
clashes with the calendar: blocks moved or deleted

### fluidez_sem_sinal
no past blocks to read

### energia_alto
you marked that you feel energized

### energia_medio
you marked that you feel steady

### energia_baixo
you marked that it feels heavy

### energia_sem_sinal
no recent answer in the check-in

### evidencia_alto
the world is noticing: recent outside signals

### evidencia_medio
one recent outside signal

### evidencia_baixo
few outside signals

### evidencia_sem_sinal
no outside signal this month

### espaco_alto
fits comfortably in the month

### espaco_medio
fits snugly in the month

### espaco_baixo
the month's calendar cannot hold everything

### espaco_sem_sinal
no monthly plan to read

### funcionando
What is working: {frase}.

### atrito
Where the friction is: {frase}.

### sem_atrito
No friction in sight.

### passo_florescendo
Protect the time slot that is working and pick the next checkpoint.

### passo_ritmo
Keep this week's blocks; a small checkpoint locks in the pace.

### passo_atencao
Pick a short, easy block for this week and mark how it went.

### passo_travada
Take a calm look at this milestone: reduce the hours, move the deadline or change the time slot.

### passo_pausada
No rush: it comes back when it makes sense.

### passo_conquistada
Celebrate and decide what comes next.

### manchete_florescendo
A flourishing week. Protect what is working.

### manchete_ritmo
A week in stride. {meta} is what moves your goals most right now.

### manchete_atencao
This week needs attention. Start with {meta}, with a short block.

### manchete_sem_sinal
The week is starting. One block done today already gives direction.

### alavanca
What moves this goal most right now: {meta}.

### sem_alavanca
All milestones of this goal are paused or achieved.

### horizonte_hoje
Today

### horizonte_hoje_leitura
presence

### horizonte_semana
Week

### horizonte_semana_leitura
pace

### horizonte_mes
Month

### horizonte_mes_leitura
direction

### presenca_sem_blocos
Free day

### presenca_por_comecar
About to start

### presenca_andamento
In progress

### presenca_cumprido
Day well spent

### ritmo_florescendo
Flourishing

### ritmo_ritmo
In stride

### ritmo_atencao
Needs attention

### ritmo_sem_sinal
No signal

### direcao_firme
Moving steadily

### direcao_construcao
Taking shape

### direcao_foco
Needs focus

### direcao_pausado
Paused

### direcao_conquistado
Achieved

### espaco_folgado
Roomy

### espaco_justo
Snug

### espaco_apertado
Tight

### dias_sem_feito
last block done {n} days ago

### sem_feito
no block done in recent weeks

### objetivo_implicito
This milestone has no end goal set; it counts as its own goal.

### compasso_folga
with room to spare before the deadline

### compasso_compasso
in step with the deadline

### compasso_folego
needs a push to reach the deadline

### periodo_alavanca_semana
What moves this week most: {meta}.

### periodo_alavanca_mes
What moves this month most: {meta}.

### periodo_alavanca_trimestre
What moves this quarter most: {meta}.

### periodo_alavanca_semestre
What moves this half most: {meta}.

### periodo_alavanca_ano
What moves this year most: {meta}.

### periodo_sem_alavanca
No active milestone passes through this period.

### periodo_passado
Period closed. What worked here becomes a reference for the next one.

### periodo_futuro_um
Ahead, with one milestone deadline in this period.

### periodo_futuro_n
Ahead, with {n} milestone deadlines in this period.

### periodo_futuro_livre
Ahead, with no milestone deadlines in this period.

## janela

### esperando
Opening the Goal Pacer dashboard...

### sem_painel
The dashboard did not answer at 127.0.0.1:8765. In Terminal, run goal-pacer doctor to see what is missing, then use View > Reload.

### instalando
Setting up Goal Pacer on this Mac. The first time takes a minute.

### instalacao_parou
Setup stopped. The last lines below say why.

### tentar_outra_vez
Try once more

### ocultar
Hide Goal Pacer

### sair
Quit Goal Pacer

### editar
Edit

### desfazer
Undo

### refazer
Redo

### recortar
Cut

### copiar
Copy

### colar
Paste

### selecionar_tudo
Select All

### ver
View

### recarregar
Reload

### janela
Window

### minimizar
Minimize

### fechar
Close

## saude

### titulo
Close to the limit

### job_perto_do_teto
The {quando} job took {minutos} min, close to its {teto} min limit.

### espera_lock
The {quando} job waited {minutos} min for the data folder.

### limite_de_uso
The subscription usage window ran out {n} times in the last 7 days; an earlier job time can help.

### tokens_acima
The last job used {tokens} tokens, above the usual ({mediana}).

### chamada_lenta
A call to {ferramenta} took {segundos} s in the last 7 days; the per-call limit is 180 s.

### retries_startup
{pct}% of connector calls had to repeat in the last 7 days.

### registro_grande
registro.json is at {mb} MB; the yearly archive lightens it from January.

### painel_lento
Dashboard screens took up to {ms} ms on the slowest requests of the last 7 days.

### erros_tela
The dashboard recorded {n} screen error(s) in the last 7 days: goal-pacer logs eventos --tipo erro_front.

### notificacao
Goal Pacer, three jobs in a row: {texto}


## logs

### sem_registros
No local records here: install with ./install.sh (or unset GP_TELEMETRIA=0).

### sem_trace
No job trace here. The first one comes with the 7am job.

### sem_eventos
No events in the last {dias} day(s).

### titulo_trace
Trace {trace}

### titulo_resumo
Local records from the last {dias} days

### titulo_painel
Dashboard (requests, p50, p95, max)

### titulo_conectores
Connectors (calls, p50, p95, max)

### nada_medido
nothing measured in the period

### linha_chamadas
connector calls: {total} (repeated: {repetidas}) · screen errors: {erros_front} · dashboard errors: {erros_painel}

### linha_dados
registro.json: {registro} KB · days: {dias} · logs: {logs} KB


## perfil_cli

### linha_meta
{meta} {progresso}% (+{presumido}% done?) · expected pace {ritmo}%

## calendario

### nome_idioma
English (en)

### dias_longos
Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday

### dias_curtos
Mon, Tue, Wed, Thu, Fri, Sat, Sun

### meses
January, February, March, April, May, June, July, August, September, October, November, December

### meses_curtos
Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec

### data_curta
{mes_curto} {d}

### decimal
.

### locale_numeros
en

### dias_celula
Mon, Tue, Wed, Thu, Fri, Sat, Sun

### faixas
morning, afternoon, evening

### dias_nota
Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday

### faixas_nota
in the morning, in the afternoon, in the evening


## tom

### palavras_proibidas
late, overdue, behind, failed, failure, missed, lost, should, should have, shouldn't, again, still, yet, you didn't, didn't do, not done yet

### placar
of

### pendente_ha
pending for {n} day, overdue by {n} day

### regras_prompt
Tone without blame and without pressure. Words that never appear: late, overdue, behind, failed, missed, lost, should, "didn't do", "pending for N days", again, still, yet. Never a scoreboard like "N of M". Forward-looking verbs: "there is room to cover", "moves to Thursday", "back at 2pm".

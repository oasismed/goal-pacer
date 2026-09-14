# Strings de superfície (pt-BR)

Tudo o que o usuário lê vem daqui (design review 7.2). Formato: `## grupo`,
`### chave`, texto até a próxima chave; `{variavel}` é substituída pelo
script. Regras de tom em `regras.md`: sem "atrasada", "falhou", "perdeu",
"não fez", "deveria", "pendente há N dias", "de novo", "ainda"; verbos para
frente; nunca "N de M".

## onboarding

### abertura
Vamos montar o seu Goal Pacer em até 8 perguntas, uma por vez. Cada uma diz por que está sendo feita. Você pode parar e continuar depois: as respostas ficam num rascunho até o fim.

### p1_metas
O que você quer que mude nos próximos meses? Diga até 3 objetivos finais e, para cada um, as metas que vão te levar lá (até 5 metas no total, com título curto).
Por que: o coach pesa cada meta pelo quanto ela move o objetivo; sem objetivo, cada meta conta como o próprio objetivo.

### p2_prazos
Para cada meta: qual é a data limite, ela é imposta por alguém de fora (prova, entrega, evento) ou é sua, e o quanto pesa no objetivo: essencial, importante ou apoio?
Por que: o prazo define o ritmo esperado e o horizonte (trimestre, semestre ou ano); o impacto diz o que mais move o objetivo quando o tempo aperta.

### p3_custo
Quantas horas por semana cada meta pede, e por quantas semanas? Pesquisei referências e mostro o número encontrado; confirme ou troque.
Por que: o plano mensal é um balanço entre as horas livres da sua agenda e as horas que as metas pedem. O número que você confirma é o que entra.

### p3_custo_encontrado
Para "{titulo}" a pesquisa sugere {min} a {max} h/semana por {semanas} semanas ({fonte}). Confirmar {escolhido} h/semana ou informar outro número?

### p3_custo_sem_numero
Para "{titulo}" não encontrei um número confiável. Quantas horas por semana e por quantas semanas você estima?

### p4_horario_util
Em que horários você aceita blocos nos dias úteis, no sábado e no domingo? (ex.: 08:00-19:00, 09:00-13:00, nenhum)
Por que: só as janelas livres dentro desse horário viram blocos. Fora dele a agenda é sua.

### p5_calendario
Crie no Google Calendar um calendário chamado "Metas" (Configurações → Adicionar calendário → Criar), escolha a cor, e me diga quando estiver pronto. Quer lembretes do Google nos blocos? (padrão: não)
Por que: os blocos vivem só nesse calendário; o Goal Pacer nunca escreve no seu calendário principal. Apagar ou mover um bloco lá é o seu check-in.

### p5_calendario_nao_encontrado
Não achei um calendário chamado "Metas" na sua conta. Crie e me avise; sem ele o Goal Pacer não escreve em lugar nenhum.

### p6_fontes
Detectei estas fontes conectadas: {fontes}. Quais posso ler para achar evidências das metas? (Gmail e WhatsApp por export são o mínimo; Notion e Drive são opcionais)
Por que: no plano mensal aparecem sinais do que você já fez (um email de matrícula, uma página no Notion). Só resumos; nunca o conteúdo.

### p7_palavras_chave
Até 3 palavras-chave por meta para eu buscar essas evidências. E, para cada objetivo, por que ele importa e como você vai saber que mudou?
Por que: a busca é por palavra, não por assunto; e o "como vou saber" é o sinal que o coach procura além das horas.

### p8_email_fuso
Seu e-mail é {email} e seu fuso é {timezone}? O email das 7h vai só para você.
Por que: o email é o único canal de saída, e todo horário do plano é calculado nesse fuso.

### rascunho_existente
Achei um rascunho de onboarding de {quando} com {n} respostas. Continuar de onde parou ou descartar e começar do zero?

### gravado
Gravei {n_metas} metas em metas/, o contexto em contexto.md e a pesquisa em fontes/. Instalação {instalacao_id}.

### gravado_objetivos
Gravei {n_objetivos} objetivos em objetivos/, {n_metas} metas em metas/, o contexto em contexto.md e a pesquisa em fontes/. Instalação {instalacao_id}.

### tela_final
Pronto. Seu primeiro email sai agora (e todo dia às 7h). Na agenda: deixe o bloco = feita?, apague = não fiz, mova = reagendar.

### erro_resposta
Não consegui gravar: {campo} recebeu {valor}. {motivo}

## checkin

### abertura
Check-in rápido. Desde a última vez: {resumo}

### sem_movimento
nenhum bloco venceu

### p2_quais_fez
Quais destas você fez? Marque as que valem; se quiser, diga quanto tempo levou. As não marcadas ficam como não feitas.

### p_sentimento
Como você está com {meta}? Com energia, firme ou pesada.

### p3_decisao
{meta} precisa de uma decisão: {texto}

### p4_progresso
Segunda: quer declarar em que ponto cada meta está (0 a 100)? Vale mais que a conta de horas quando você sabe melhor.

### p5_nota
Blocos de {dia} {faixa} raramente saem (taxa {pct}%, {n} observações). Registrar "{restricao}" no seu perfil?

### fechamento
Registrado:
{mudancas}
O dia é refeito com isso.

### lock_preso
Tem um job rodando na pasta de dados ({detalhe}). Aguarde ele terminar ou cancele antes do check-in.

### restricao
sem blocos {dia} {faixa}

### conta_confirmadas_um
{n} confirmada

### conta_confirmadas_n
{n} confirmadas

### conta_presumidas_um
{n} feita?

### conta_presumidas_n
{n} feita?

### conta_movidas_um
{n} movida

### conta_movidas_n
{n} movidas

### conta_reagendadas_um
{n} reagendada

### conta_reagendadas_n
{n} reagendadas

### conta_apagadas_um
{n} apagada

### conta_apagadas_n
{n} apagadas

### mudanca_feita
{task}: feita confirmada{duracao}

### mudanca_nao_feita
{task}: não feita

### mudanca_progresso
{meta}: progresso declarado {pct}%

### mudanca_sentimento
{meta}: sentimento {sentimento}

### mudanca_nota
perfil.md: nota registrada

### mudanca_nota_recusada
nota recusada (não volta por {dias} dias)

### mudanca_campo
{campo} para {valor}

### mudanca_decisao
{meta}: {saida}{detalhe}

### nada_a_mudar
nada a mudar


## diario

### respostas_email
Sua resposta ao email entrou no check-in: {confirmados} bloco(s) feito(s), {nao_feitos} para replanejar.

### efeito
move: {objetivo} ({impacto})

### resumo
{n} bloco{s} hoje, para {metas}.

### resumo_sem_blocos
Hoje sem janela livre.

### resumo_sem_demanda
Hoje sem blocos: as metas estão cobertas nesta semana.

### sem_janela
Hoje sem janela livre. As metas seguem na conta da semana.

### op_parcial
Bloco {bloco} não entrou na agenda; tente /goal-pacer diario.

### fuso_divergente
Você está em {fuso}; horário útil aplicado nesse fuso.

### metas_nao_encontrado
Calendário "Metas" não encontrado na conta. Crie o calendário no Google Calendar e rode /goal-pacer onboarding para registrá-lo.

### desinstalar
{n} blocos desta instalação {acao} no calendário Metas.

### porque_template
{meta} pede {horas}h nesta semana; janela livre das {hora}

### sem_blocos_md
(sem blocos)


## plano

### resumo_folgado
Em {mes} a agenda tem {oferta} h livres e as metas pedem {demanda} h. Dá para cobrir tudo mantendo o ritmo.

### resumo_apertado
Em {mes} a agenda tem {oferta} h livres e as metas pedem {demanda} h. As decisões abaixo mostram onde ajustar.

### folgado
A oferta do mês ({oferta} h) cobre a demanda das semanas abertas ({demanda} h).

### apertado
A demanda das semanas abertas ({demanda} h) passa da oferta do mês ({oferta} h).

### meta_coberta
{meta} cabe no mês: {demanda} h pedidas, todas com janela reservada.

### meta_fora
{meta} está {estado} e fica fora da alocação.

### decisao
Com as janelas até {fim} dá para cobrir {pct} do que falta de {meta} neste mês. Saídas: reduzir · {saida} · manter.

### linha_custo
custo: {h} h/semana por {semanas} semanas = {total} h (confiança: {confianca})

### linha_prazo
restante: {restante} h · prazo {prazo} (externo: {externo}) · estado: {estado}

### linha_mes
neste mês: demanda {demanda} h · alocado {alocado} h · feito {feito} h · cobertura {cobertura}

### linha_progresso
progresso: {progresso} · ritmo esperado {ritmo}

### linha_decisao
decisão sugerida: {decisao}

### linha_recalibrar
ritmo real diferente do custo: ajustar {meta} para {h} h/semana? Responda no /goal-pacer mensal.

### oferta_semana
oferta da semana ({inicio} a {fim}): {oferta} h livres

### sim
sim

### nao
não

### progresso_presumido
 (+{pct} feita?)

### espelho
Espelho gerado da seção desta semana em planos/{mes}.md; não edite à mão.

### saida_adiar
adiar para {data}

### saida_renegociar
renegociar o prazo

### titulo
Plano de {mes}

### titulo_semana
Semana {semana} ({inicio} a {fim})


## mensal

### resumo
Balanço de {mes} pronto: coberta(s) {coberta}; ajustar {outras}.

### whatsapp_nao_reconhecido
Export do WhatsApp não reconhecido; o plano segue sem ele.

### whatsapp_stale
O export do WhatsApp tem mais de 7 dias; um export recente da conversa entra no próximo plano.

### whatsapp_truncado
O export do WhatsApp passou de 20 MB; só o começo entrou.

### whatsapp_lido
whatsapp: export lido em {data} ({status}); pode apagar de inbox/whatsapp.

### leitura_sem_fontes
As fontes não foram lidas neste mês ({classe}); o plano saiu só com a agenda.

### leitura_fora_da_lista
A leitura das fontes chamou ferramentas fora da lista liberada ({tools}); as evidências deste mês foram descartadas e o plano saiu só com a agenda.

### leitura_fora_dos_tetos
A leitura das fontes passou dos tetos por meta ou buscou sem excluir o email das 7h; as evidências entraram, confira cache/auditoria do mês.

### prosa_template
A prosa do plano saiu do modelo padrão ({classe}).

### custo_pendente
Confirme o custo de {meta}: título, horizonte ou prazo mudaram desde a pesquisa.

## email

### assunto
[goal-pacer] {dia} · {blocos}

### assunto_decisao
 · {meta} precisa de decisão

### assunto_falha
[goal-pacer] {dia} · hoje não gerei o seu dia

### blocos_um
1 bloco

### blocos_n
{n} blocos

### blocos_zero
sem blocos

### titulo_decisao
Precisa de decisão ({meta})

### decisao_resposta
Responda em /goal-pacer checkin.

### titulo_hoje
Hoje

### mais_blocos
e mais {n} na agenda

### titulo_desde
Desde {dia}

### titulo_progresso
Como vão as metas

### comecando
começando

### linha_objetivo
{objetivo}: {leitura}

### linha_meta
{rotulo} {titulo}: {leitura}

### titulo_avisos
Avisos

### titulo_como_funciona
Como funciona

### gestos
Deixe o bloco na agenda = feita? · apague = não fiz · mova = reagendar.

### link_texto
Ver o dia no Google Calendar

### rodape_comandos
Check-in: /goal-pacer checkin · Status: /goal-pacer status

### numero_bloco
bloco {n}

### responder
Para confirmar sem abrir a agenda, responda este email com uma linha por bloco: 02 fiz 1h, ou 03 não fiz.

### decisao_pendente_aviso
{meta} segue com decisão aberta no plano; responda em /goal-pacer checkin.


### falha_corpo
Motivo: {motivo}. O que fazer: {acao}. Seus blocos de ontem continuam valendo.

## desde

### feita_presumida
{titulo} ({meta}): feita?

### confirmada
{titulo} ({meta}): confirmada

### nao_feita
{titulo} ({meta}): não fiz

### movida
{titulo} ({meta}): movida para {hora}

### reagendada
{titulo} ({meta}): fica para {dia} {hora}

### apagada
{titulo} ({meta}): saiu da agenda

### contagem_confirmadas
{n} confirmada(s)

### contagem_presumidas
{n} feita?

### contagem_movidas
{n} movida(s)

### contagem_fora
{n} fora da agenda

## falhas

### semonboarding_motivo
a pasta de dados está sem metas
### semonboarding_acao
rode /goal-pacer onboarding

### semmetaativa_motivo
nenhuma meta está ativa
### semmetaativa_acao
reative ou crie uma meta em /goal-pacer onboarding

### grafoinvalido_motivo
um arquivo de metas ou do contexto tem um campo inválido
### grafoinvalido_acao
rode validar.py grafo e corrija o campo indicado

### schemamismatch_motivo
os arquivos são de outra versão do Goal Pacer
### schemamismatch_acao
rode install.sh --update

### cacheinvalido_motivo
a leitura da agenda voltou num formato inesperado
### cacheinvalido_acao
rode /goal-pacer diario à mão; se repetir, veja o log do job

### numerosalterados_motivo
os números do plano mudaram fora do balanço
### numerosalterados_acao
rode balanco.py --render para refazer as tabelas

### metasnaoencontrado_motivo
o calendário Metas não aparece na conta
### metasnaoencontrado_acao
crie o calendário Metas no Google Calendar e rode /goal-pacer onboarding

### escopoinsuficiente_motivo
o conector não tem permissão de escrita
### escopoinsuficiente_acao
reconecte Google Calendar e Gmail em claude.ai com permissão de escrita

### erroconector_motivo
o conector respondeu com erro
### erroconector_acao
tente /goal-pacer diario em alguns minutos

### toolnegada_motivo
uma ferramenta foi negada pela configuração do job
### toolnegada_acao
rode status.py --doctor e veja o item de conectores

### turnosesgotados_motivo
a sessão do Claude passou do número de turnos
### turnosesgotados_acao
tente /goal-pacer diario à mão

### respostainvalida_motivo
a resposta do conector veio num formato inesperado
### respostainvalida_acao
tente /goal-pacer diario em alguns minutos

### mcpnaocarregado_motivo
os conectores do Claude não carregaram a tempo
### mcpnaocarregado_acao
tente /goal-pacer diario em alguns minutos

### ratelimited_motivo
a janela de uso da assinatura esgotou
### ratelimited_acao
o job tenta sozinho mais tarde; se preferir, rode /goal-pacer diario depois do horário de liberação

### registrocorrompido_motivo
o registro.json não pôde ser lido
### registrocorrompido_acao
rode registro.py recuperar

### locktimeout_motivo
outro job segurou a pasta de dados por tempo demais
### locktimeout_acao
rode status.py --doctor e apague o lock obsoleto se ele aparecer

### binarymissing_motivo
o executável do claude ou do python3 não foi encontrado
### binarymissing_acao
rode install.sh --check

### sessiontimeout_motivo
o job passou do tempo máximo
### sessiontimeout_acao
rode /goal-pacer diario à mão e veja o tempo no status

### desconhecida_motivo
um erro inesperado interrompeu o job
### desconhecida_acao
veja o log do job em ~/.goal-pacer/jobs/logs

## status

### cabecalho
Goal Pacer · status · {quando}

### nunca_rodou
Nenhum diário por aqui. Próximo: {proximo}. Para ver agora: /goal-pacer diario

### silencio
O último diário rodou há {dias} dias ({quando}). Se o computador ficou desligado ou na tela de login às 7h, rode /goal-pacer diario.

### proximo
Próximo diário: {proximo}

### titulo_pendencias
Pendências

### sem_pendencias
Nada esperando resposta.

### decisao
{meta}: {texto} Responda em /goal-pacer checkin.

### presumidas
{n} bloco(s) "feita?" dos últimos 14 dias para confirmar em /goal-pacer checkin: {ids}

### ultimo_job
Último job: {motivo}. O que fazer: {acao}.

### titulo_progresso
Como vão as metas

### sem_metas
Nenhuma meta ativa. Para cadastrar: /goal-pacer onboarding

### titulo_cobertura
Cobertura de {mes}

### cobertura_mes
oferta {oferta} h · demanda {demanda} h · cobertura {cobertura}

### cobertura_meta
{meta} {cobertura} · {decisao}

### sem_plano
Sem plano de {mes}. Para gerar: /goal-pacer mensal

### titulo_perfil
Perfil

### perfil_base
baseado em {n} confirmada(s)

### perfil_presumidas
{horas} h presumidas não contadas ({metas})

### perfil_janelas
conclusão por faixa: {faixas}

### perfil_fator
{meta} leva {fator}× o tempo planejado por bloco

### titulo_evidencias
Evidências dos últimos 30 dias

### sem_evidencias
Nenhuma evidência lida nos últimos 30 dias.

### titulo_execucoes
Últimas execuções

### sem_execucoes
Nenhuma execução registrada.

### execucao_ok
ok

### progresso_declarado
{meta}: progresso declarado {pct}%

### decisao_manter
manter

### decisao_reduzir
reduzir

### decisao_adiar
adiar

### decisao_renegociar
renegociar

### celula
{dia}-{faixa}


## doctor

### titulo
Goal Pacer · doctor · {quando}

### ok
OK

### falhou
FALHOU

### resumo_ok
Tudo certo nos {n} itens.

### resumo_acao
{n} item(ns) pedem ação; o que fazer está na linha de cada um.

### item_dados
pasta de dados

### dados_ok
{pasta} (schema_version {versao})

### dados_sem_pasta
{pasta} não existe: rode install.sh e depois /goal-pacer onboarding

### dados_sem_contexto
{pasta} sem contexto.md: rode /goal-pacer onboarding

### dados_versao
schema_version {atual}, esperado {esperado}: rode install.sh --update

### dados_invalidos
{erro}: rode python3 scripts/validar.py grafo e corrija o arquivo apontado

### dados_registro
{erro}: rode python3 scripts/registro.py recuperar

### item_lock
lock da pasta de dados

### lock_livre
livre

### lock_ativo
job em andamento (pid {pid}, {minutos} min)

### lock_obsoleto
lock esquecido (pid {pid}, {minutos} min): apague {caminho}

### item_jobs
jobs agendados

### jobs_ok
{labels} carregados no {agendador}

### jobs_sem_linger
{labels} carregados no {agendador}; sem linger, só rodam com a sua sessão aberta (loginctl enable-linger)

### jobs_faltando
{labels} fora do {agendador}: rode ./install.sh

### jobs_sem_agendador
{agendador} indisponível ({erro}): rode com a sua sessão aberta

### item_claude
claude

### claude_ok
{caminho} ({versao})

### claude_relativo
{caminho} não é caminho absoluto: rode install.sh --check

### claude_ausente
{caminho} não encontrado: instale o Claude Code ou defina GP_CLAUDE_BIN

### item_codex
codex

### codex_ausente
{caminho} não encontrado: instale o Codex CLI e rode codex login, ou defina GP_CODEX_BIN

### item_python
python3

### python_ok
{caminho} ({versao}){extra}

### python_velho
{caminho} ({versao}): use python3 3.9 ou mais novo

### python_sem_xcode
{caminho} ({versao}) sem Xcode Command Line Tools: rode xcode-select --install

### item_conectores
conectores

### conectores_ok
Calendar e Gmail conectados; calendário Metas encontrado; {escrita}

### conectores_sem_onboarding
Calendar e Gmail conectados; o calendário Metas é conferido depois do onboarding

### conectores_opcionais
nenhum conector obrigatório; Google Calendar e Gmail em claude.ai põem os blocos na agenda e mandam o email das 7h

### conectores_nenhum
sem conectores: metas, plano e dia saem do que você escreveu; conecte Google Calendar e Gmail em claude.ai quando quiser aprofundar

### conectores_so_email
Gmail conectado; sem Google Calendar, os blocos ficam no app

### conectores_provedor
Calendar e Gmail pelo {provedor} entram depois do spike; hoje eles funcionam com o provedor claude

### conectores_formato
claude mcp list em formato não reconhecido: rode claude mcp list e confira os conectores

### conectores_mcp
{servidores} fora de Connected em claude mcp list: reconecte em claude.ai, na tela de conectores

### conectores_sem_metas
calendário Metas ({id}) não aparece em list_calendars: crie o calendário ou refaça o onboarding

### conectores_leitura
list_calendars: {erro}

### escrita_nao_testada
escrita não testada (use --sondar-escrita)

### escrita_ok
escrita testada no Metas e no Gmail

### escrita_escopo
{servidor} sem permissão de escrita ({erro}): reconecte em claude.ai com escrita liberada

### escrita_sobra
{servidor} criou a sonda mas não a apagou ({erro}): apague "{titulo}" à mão

### item_ultimo
último job

### ultimo_ok
{run_id} · exit 0 · há {idade}

### ultimo_erro
{run_id} · {classe} · exit {codigo} · há {idade}: {acao}

### ultimo_velho
{run_id} · há {idade}: confira se o computador fica ligado às 7h ou rode {comando}

### ultimo_nenhum
nenhum job rodou: rode {comando}

### sonda_titulo
[GP] sonda de escrita do Goal Pacer

### sonda_descricao
Evento de teste do status --doctor; é apagado logo em seguida.

### sonda_assunto
[goal-pacer] sonda de escrita

### sonda_corpo
Rascunho de teste do status --doctor; vai para a lixeira logo em seguida.

### python_xcode
; Xcode CLT em {caminho}

### item_seguranca
permissões

### seguranca_ok
dados e logs só seus; o código dos jobs só você altera

### seguranca_pasta_aberta
{caminho} aberta para outros usuários ({modo}): rode chmod 700 {caminho}

### seguranca_arquivo_aberto
{caminho} legível por outros usuários ({modo}): rode chmod 600 {caminho}

### seguranca_codigo_alteravel
{quantos} caminho(s) do app alteráveis por outros usuários (ex.: {caminho}): rode chmod -R go-w {app}

### seguranca_codigo_de_outro
{quantos} caminho(s) do app com outro dono (ex.: {caminho}): reinstale sem sudo com ./install.sh

### seguranca_agendador_alteravel
{caminho} alterável por outros usuários ({modo}): rode chmod 644 {caminho}

### seguranca_skill_desviada
a skill {caminho} aponta para {alvo}, não para {app}: rode ./install.sh

### seguranca_mais
; e mais {n}


## instalar

### inicio
Instalando o Goal Pacer em {raiz}

### pergunta_dados
Pasta de dados [{padrao}]:

### app_clonado
app: clone de {origem} em {app}

### app_copiado
app: cópia de {origem} em {app}

### app_existente
app: {app} já existe; para trazer a versão nova use ./install.sh --update

### origem_suja
aviso: {origem} tem mudanças fora de commit; o clone leva só o último commit (use --copiar para levar a árvore de trabalho)

### skill
skill: {link} aponta para {app}

### dados
dados: {dados}

### agendamento
jobs: {arquivos}

### painel_rede
painel: no ar em http://127.0.0.1:{porta}/ e no Wi-Fi de casa; abra no computador para ver o endereço e o código de pareamento do celular

### painel_desligado
painel: agente do login desligado

### painel_local
painel: no ar em {endereco}, abre sozinho a cada login; no navegador dá para instalar como app

### agendador_ok
{agendador}: {labels} carregados

### agendador_aviso
aviso: o {agendador} não carregou {label}; rode ./install.sh --check com a sua sessão aberta

### sem_agendar
{agendador}: jobs não carregados (--sem-agendar)

### pronto
Pronto. Próximos passos: abra o painel e siga a tela Começar (ou rode /goal-pacer onboarding no Claude Code); depois {comando} doctor para conferir tudo.

### check_titulo
Checagem da instalação

### update_ok
Atualizado para a versão {app_versao} ({revisao}); esquema v{versao}; jobs recarregados.

### update_sem_instalacao
Nenhuma instalação em {raiz}: rode ./install.sh primeiro.

### update_git
git em {app} não trouxe a versão {tag} ({erro}); nada mudou. Para tentar outra vez: goal-pacer atualizar.

### update_tag
versão nova: {tag}, assinada por quem publica o Goal Pacer

### update_em_dia
Já está na versão mais nova publicada ({versao}); nada mudou.

### update_recusado
Atualização recusada: {motivo}. Nada mudou.

### update_zip_assinado
{arquivo}: assinatura de {assinante} conferida

### update_canal
versão nova no canal: {versao}; baixando o zip e a assinatura

### update_pasta_assinada
versão {versao}: manifesto assinado por {assinante} conferido, e cada arquivo confere com ele

### update_pasta_antiga
Esta pasta é da versão {versao}, mais antiga que a instalada ({instalada}): nada muda.

### claude_ausente
Claude Code: não achei neste computador. A instalação segue; os jobs usam {caminho} assim que você instalar (a tela Começar do painel mostra como).

### fusos_ok
fusos horários: base IANA (tzdata) em {pasta}

### runtime_copiado
python: o Python do app copiado para {pasta} (os jobs não dependem de onde o app está)

### fusos_erro
Não consegui baixar a base de fusos horários (tzdata) pelo pip: {erro}. Confira a internet e clique duas vezes no instalador outra vez.

### update_sem_assinatura
aviso: {origem} é uma pasta, sem assinatura para conferir; use só em desenvolvimento (para quem instala, o zip da versão com o .sig)

### update_copia_sem_origem
A instalação é uma cópia: baixe o zip da versão nova na página de versões, descompacte e clique duas vezes em Instalar Goal Pacer (ou rode goal-pacer atualizar --from <arquivo.zip>, com o .sig ao lado).

### update_lock
Um job está usando a pasta de dados ({erro}); rode ./install.sh --update quando ele terminar.

### update_migrar
{erro}

### uninstall_agendador
{agendador}: {labels} descarregados e removidos

### uninstall_sem_agendador
{agendador}: nenhum job do Goal Pacer carregado

### janela_ok
janela: {app} (abra pelo Launchpad ou em Aplicativos)

### janela_ok_windows
janela: {app} (abra pelo menu Iniciar: Goal Pacer)

### janela_sem_swift
janela: falta o compilador Swift das Command Line Tools; o painel segue no navegador (xcode-select --install e rode ./install.sh outra vez)

### janela_erro
janela: não montei o app ({erro}); o painel segue no navegador

### uninstall_janela
janela: {app} removido

### uninstall_skill
skill: {link} removido

### uninstall_blocos_pergunta
{n} bloco(s) desta instalação estão no calendário Metas. Apagar agora? [s/N]

### uninstall_blocos
calendário Metas: {n} bloco(s) apagados

### uninstall_blocos_mantidos
calendário Metas: blocos mantidos (para apagar depois: ./install.sh --uninstall --apagar-blocos)

### uninstall_blocos_erro
calendário Metas: blocos mantidos ({erro})

### uninstall_cache_pergunta
Apagar também cache/ e sinais/ da pasta de dados? [s/N]

### uninstall_cache
dados: cache/ e sinais/ apagados

### uninstall_fim
Desinstalado. Suas metas, planos e registro continuam em {dados}; o app continua em {app} (pode apagar a pasta).

### autoteste_ok
autoteste: {n} verificações em {segundos} s com python {python}; sem conectores e sem tokens

### autoteste_erro
autoteste: {erro}

### update_app_sujo
O app em {app} tem mudanças fora de commit; nada mudou. Leve essas mudanças para fora do app (git -C {app} stash) e rode ./install.sh --update.

### update_reaplicar
O código novo está no lugar, mas os agentes e a janela não foram refeitos ({erro}); rode ./install.sh na pasta do app para terminar.

### update_backup
dados: backup em {backup}

### update_autoteste
versão nova conferida pelo autoteste e pelo esquema dos dados

### update_desfeito
Atualização desfeita: o app voltou para a versão anterior e os jobs seguem nela ({motivo}).

### comando
comando: goal-pacer (em {pasta})

### comando_fora_do_path
comando: {shim}; para chamar só goal-pacer, adicione {pasta} ao PATH

### uninstall_comando
comando: {comando} removido

### uninstall_nao_apagados
não apagados: {ids}

### origem_sem_git
{origem} não é um clone git (ou o git não está disponível): o app vai por cópia; para atualizar depois baixe o zip e o .sig da versão nova e rode goal-pacer atualizar --from <arquivo.zip>

### origem_publicada
versão publicada em {origem}: o app vai por cópia; para atualizar, abra o instalador da versão nova (o app do .dmg, o Setup.exe ou a pasta do zip)


## comando

### uso
Uso: goal-pacer <comando> [argumentos]

### status
como vão as metas, pendências e últimas execuções

### doctor
confere a instalação item por item, com o que fazer

### painel
abre o painel no navegador (--rede para o celular)

### diario
refaz o dia com a agenda de agora

### mensal
refaz o balanço do mês e lê os sinais de fora

### checkin
check-in pelo terminal (a skill conduz as perguntas)

### validar
valida a pasta de dados

### autoteste
confere, sem conectores e sem tokens, que o código roda nesta máquina

### atualizar
traz a versão nova com backup, autoteste e volta atrás se precisar

### desinstalar
remove jobs, skill e comando; metas e registro ficam

### versao
versão, esquema, plataforma e idioma

### ajuda
esta lista

### versao_linha
Goal Pacer {versao} ({revisao}) · esquema v{schema_version} · {plataforma} · {lingua} · python {python}

### desconhecido
Comando {nome} não existe.

### logs
tempo por tela e por conector, eventos e trace do último job (só leitura)


## painel

### titulo_pagina
Goal Pacer

### manchete_zero
Hoje sem blocos.

### manchete_um
Um bloco hoje.

### manchete_n
{n} blocos hoje.

### manchete_feitos_um
Um já confirmado.

### manchete_feitos_n
{n} já confirmados.

### manchete_todos
Tudo confirmado.

### atualizar
Atualizar

### hoje_titulo
Hoje

### hoje_detalhe
no calendário Metas

### hoje_detalhe_app
no app, sem Google Calendar

### sem_blocos
Nenhum bloco para hoje. O diário das 7h encaixa os próximos nas janelas livres.

### confirmar
Confirmar {titulo}

### confirmada
Confirmada

### feita_presumida
feita?

### desde
Desde {dia}

### cobertura_texto
{oferta} h livres na agenda para {demanda} h pedidas pelas metas.

### sem_plano
Sem plano de {mes}. O diário das 7h gera o plano, ou rode /goal-pacer mensal.

### decisao_titulo
{meta} precisa de decisão

### saida_reduzir
Reduzir

### saida_adiar
Adiar

### saida_renegociar
Renegociar o prazo

### saida_manter
Manter

### custo_rotulo
Novas horas por semana

### prazo_rotulo
Novo prazo

### aplicar
Aplicar

### decisao_aplicada
{meta} ajustada. O próximo diário refaz o plano com o novo número.

### decisao_mantida
{meta} segue como está.

### avisos_titulo
Avisos

### erro_carregar
Os dados não carregaram: {erro}. Confira se o painel segue aberto no terminal.

### erro_acao
{erro}

### job_em_andamento
Um job está usando a pasta de dados; tente em alguns minutos.

### rodape
Painel local em {endereco}.

### parear_titulo
Parear este aparelho

### parear_texto
Digite o código de 6 dígitos que aparece no painel aberto no computador, no cartão Abrir no celular.

### parear_codigo
Código de pareamento

### parear_botao
Parear

### parear_errado
Esse código não confere. Confira no painel do computador.

### parear_bloqueado
Muitas tentativas com código errado. Reinicie o painel no computador para liberar o pareamento.

### parear_rodape
O Goal Pacer roda no computador da sua casa. Nada deste painel sai da rede local.

### rede_titulo
Abrir no celular

### rede_detalhe
mesmo Wi-Fi

### rede_passos
No celular, abra o endereço abaixo, digite o código e, no Safari, toque em Compartilhar e em Adicionar à Tela de Início.

### rede_codigo
código

### rede_aparelhos_zero
Nenhum aparelho pareado.

### rede_aparelhos_um
1 aparelho pareado.

### rede_aparelhos_n
{n} aparelhos pareados.

### rede_esquecer
Esquecer aparelhos

### rede_esquecidos
Aparelhos esquecidos. Cada um pede o código na próxima abertura.

### rede_sem_endereco
Não achei o endereço deste computador na rede. Confira se o Wi-Fi está ligado.

### rede_terminal
No celular, no mesmo Wi-Fi: {endereco} com o código {codigo}.

### rede_aviso
A rede local não tem criptografia: use o painel no celular só no Wi-Fi de casa.

### rede_impressao
Conexão com criptografia. Na primeira abertura o celular avisa que não conhece o certificado: confira se a impressão digital (SHA-256) nos detalhes é {impressao} e continue.

### demo_selo
Dados de exemplo

### nav_rotulo
Seções do painel

### nav_hoje
Hoje

### nav_objetivos
Objetivos

### nav_metas
Metas

### nav_mes
Mês

### nav_checkin
Check-in

### nav_status
Status

### aneis_titulo
Como vai a caminhada

### aneis_detalhe
presença, ritmo e direção

### objetivos_card
Seus objetivos

### objetivos_card_detalhe
força de cada um

### alavanca_titulo
O que mais move agora

### abrir_meta
Abrir {meta}

### metas_card
Metas

### metas_card_detalhe
estado e jornada

### ver_todas
Ver todas

### espaco_titulo
Espaço em {mes}

### espaco_detalhe
a agenda comporta as metas?

### nao_fiz
Não fiz

### fiz
Fiz

### nao_feita
não feita

### bloco_movida
movida

### bloco_apagada
apagada

### bloco_reagendada
reagendada

### nao_feita_ok
Anotado. O plano segue com os próximos blocos.

### objetivos_pagina
Objetivos

### objetivos_sub
O que você quer que mude e o quanto cada meta move cada objetivo.

### por_que
Por que

### como_vou_saber
Como vou saber

### move_titulo
O que move este objetivo

### move_legenda
largura: impacto da meta no objetivo · parte cheia: tração e avanço

### metas_pagina
Metas

### metas_sub
O impacto de cada meta nos seus objetivos e a tração que ela tem agora.

### mapa_titulo
Mapa de energia

### mapa_detalhe
impacto por tração

### mapa_tracao
tração

### mapa_pouca
pouca

### mapa_boa
boa

### lista_titulo
Todas as metas

### jornada
Jornada

### prazo_data
prazo {data}

### prazo_externo
prazo externo

### sentimento_titulo
Como você está com esta meta?

### sentimento_nenhum
sem resposta recente

### sentimento_ok
Anotado para {meta}.

### voltar_metas
Todas as metas

### leitura_titulo
Leitura do coach

### marcos_titulo
Marcos

### sem_marcos
Sem marcos por enquanto. Escreva os marcos em metas/{meta}.md, na seção Marcos.

### marco_feito
Marco alcançado.

### marco_aberto
Marco reaberto.

### trilha_titulo
Tração nas últimas 6 semanas

### trilha_detalhe
presença e fluidez por semana

### trilha_sem
semana sem blocos

### sinais_titulo
Sinais

### sinais_detalhe
o que entra na leitura

### ajustes_titulo
Ajustes

### ajustes_detalhe
o próximo diário refaz o plano

### horas_rotulo
Horas por semana

### prazo_campo
Prazo

### impacto_rotulo
Impacto no objetivo

### objetivo_rotulo
Objetivo

### sem_objetivo
Sem objetivo cadastrado

### salvar
Salvar ajustes

### pausar
Pausar meta

### retomar
Retomar meta

### concluir
Marcar como conquistada

### ajuste_ok
{meta} ajustada. O próximo diário refaz o plano com o novo número.

### ajuste_igual
{meta} já está assim.

### numeros_titulo
Números do balanço

### numeros_detalhe
para decidir, não para julgar

### num_custo
horas por semana

### num_semanas
semanas estimadas

### num_total
custo total

### num_feito
confirmado até aqui

### num_cobertura
cobertura no mês

### num_decisao
decisão sugerida

### recentes_titulo
Blocos recentes

### proximos_titulo
Próximos blocos

### sem_recentes
Sem blocos nas últimas semanas.

### sem_proximos
Os próximos blocos saem no diário das 7h.

### evidencias_titulo
Sinais de fora

### sem_evidencias
Nenhum sinal de fora neste mês.


### resumo_titulo
Leitura do mês

### semanas_titulo
Espaço por semana

### semanas_detalhe
altura: quanto do tempo livre as metas pedem

### oferta_demanda
{oferta} h livres · {demanda} h pedidas


### decisoes_titulo
Decisões


### checkin_sub
Dois minutos: o que você fez, como está cada meta e o que decidir.

### passo_feitos
O que você fez

### passo_feitos_detalhe
últimos 7 dias

### sem_pendentes
Tudo confirmado nos últimos 7 dias.

### passo_sentir
Como está cada meta

### passo_sentir_detalhe
com energia, firme ou pesada

### passo_nota
Uma nota para o coach

### passo_nota_detalhe
opcional, vai para o seu perfil

### nota_exemplo
Ex.: de manhã cedo rende mais do que à noite.

### salvar_checkin
Salvar check-in

### checkin_ok
Check-in salvo. O próximo diário usa o que você marcou.

### salvar_dica
Nada é gravado até você salvar.

### checkin_vazio
Marque um bloco, uma meta ou escreva uma nota antes de salvar.

### nav_conexoes
Conexões

### conexoes_sub
Os conectores que o Goal Pacer usa e as fontes que entram nos sinais do mês.

### provedor_titulo
Provedor de IA

### provedor_texto
{provedor}, pelo login que você já tem.

### onde_claude
Conectar e reconectar acontece em claude.ai, na tela de conectores. O Goal Pacer não pede senha nem login próprio.

### onde_openai
Conectar e reconectar acontece nos apps do ChatGPT. O Goal Pacer não pede senha nem login próprio.

### verificado_em
Última verificação pelo doctor em {data}.

### nunca_verificado
Rode o doctor no terminal para ver o estado de cada conexão.

### comando_verificar
goal-pacer doctor --sondar-escrita

### comando_verificar_texto
confere os conectores, o calendário Metas e a escrita

### problema_reconexao
O job de {data} parou em {classe}: {acao}

### conexoes_lista_titulo
Conexões

### conexoes_lista_detalhe
o painel só mostra: quem confere são o doctor e os jobs

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
usada todo dia

### papel_fonte
fonte de sinais

### papel_obrigatoria_fonte
usada todo dia e fonte de sinais

### estado_conectado
conectado

### estado_reconectar
reconectar

### estado_desconectado
desconectado

### estado_sem_verificacao
sem verificação

### estado_com_export
com export

### estado_sem_export
sem export

### estado_provedor
depois do spike

### linha_visto
visto pelo doctor em {data}

### linha_uso
respondeu no job de {data}

### linha_metas_ok
calendário Metas encontrado

### linha_metas_ausente
calendário Metas fora da lista: crie o calendário ou refaça o onboarding

### linha_escrita
escrita testada em {data}

### linha_lida
lida no mensal de {data}

### linha_nao_lida
nenhuma leitura registrada nos sinais

### linha_export
último export em {data} ({n} no total)

### linha_sem_export
exporte a conversa sem mídia para inbox/whatsapp/ na pasta de dados

### linha_provedor
Calendar, Gmail, Notion e Drive pelo {provedor} entram depois do spike

### fonte_nos_sinais
nos sinais do mês

### fonte_fora_dos_sinais
fora dos sinais do mês

### fonte_usar
Usar nos sinais

### fonte_tirar
Tirar dos sinais

### fonte_entra
{fonte} entra na próxima leitura mensal.

### fonte_sai
{fonte} sai da próxima leitura mensal.

### fonte_igual
{fonte} já estava assim.

### outros_titulo
Outros conectores

### outros_texto
O Goal Pacer usa só estes conectores, cada chamada numa sessão isolada, e nenhuma leitura de conteúdo de terceiros acontece junto com escrita. Uma fonte nova entra pelo ponto de extensão de fontes (README, Módulos e pontos de extensão).

### status_sub
Execuções do job diário, configuração e aparelhos.

### execucoes_titulo
Execuções

### execucoes_detalhe
mais recentes primeiro

### sem_execucoes
Nenhuma execução registrada.

### execucao_ok
ok

### proximo_job
Próximo diário: {quando}.

### tokens
{n} tokens

### segundos
{n} s

### config_titulo
Configuração

### fuso_rotulo
Fuso

### horario_rotulo
Horário útil

### fontes_rotulo
Fontes de sinais

### cadastro_rotulo
Cadastro

### cadastro_texto
{metas} metas ativas · {objetivos} objetivos

### comandos_titulo
No terminal

### comandos_detalhe
o painel não chama conectores

### comando_diario
/goal-pacer diario

### comando_diario_texto
refaz o dia com a agenda de agora

### comando_mensal
/goal-pacer mensal

### comando_mensal_texto
refaz o balanço do mês e lê os sinais de fora

### comando_doctor
python3 scripts/status.py --doctor

### comando_doctor_texto
diagnóstico completo: jobs, conectores e último job

### rede_desligada
Painel aberto só neste computador. Para usar no celular, abra com web.py --rede.

### rede_so_mac
O código de pareamento aparece só no computador.

### nav_horizontes
Horizontes

### nivel_dia
Dia

### nivel_semana
Semana

### nivel_mes
Mês

### nivel_trimestre
Trimestre

### nivel_semestre
Semestre

### nivel_ano
Ano

### niveis_rotulo
Nível do horizonte

### trilha_rotulo
Onde você está

### periodo_semestre
{n}º semestre de {ano}

### periodo_semestre_curto
S{n}

### periodo_trimestre
{n}º trimestre de {ano}

### periodo_trimestre_curto
T{n}

### periodo_mes
{mes} de {ano}

### periodo_semana
Semana {n} · {ano}

### periodo_semana_curto
Semana {n}

### periodo_intervalo
{de} a {ate}

### fase_passado
Encerrado

### fase_atual
Agora

### fase_futuro
À frente

### anterior
Período anterior

### proximo
Próximo período

### dia_anterior
Dia anterior

### dia_seguinte
Dia seguinte

### voltar_hoje
Voltar para hoje

### partes_semestre
Semestres

### partes_trimestre
Trimestres

### partes_mes
Meses

### partes_semana
Semanas

### partes_dia
Dias

### partes_detalhe
abra um para descer um nível

### leitura_periodo
Leitura do período


### tempo_detalhe
anel de fora: tempo que passou · de dentro: a leitura

### metas_do_trimestre
Metas do trimestre

### metas_do_semestre
Metas do semestre

### metas_do_ano
Metas do ano

### sem_metas_nivel
Nenhuma meta com este horizonte neste período.

### metas_acima
Metas maiores que passam por aqui

### metas_abaixo
Metas menores dentro deste período

### metas_em_jogo
Metas que este período serve

### prazo_aqui
prazo aqui

### prazos_um
um prazo

### prazos_n
{n} prazos



### sem_blocos_dia
sem blocos

### horizonte_meta_trimestre
meta de trimestre

### horizonte_meta_semestre
meta de semestre

### horizonte_meta_ano
meta do ano

### nav_comecar
Começar

### comecar_sub
Cinco passos para o Goal Pacer montar a sua semana. Dá para fechar e voltar: cada passo fica guardado.

### comecar_sub_pronto
Suas metas estão gravadas.

### comecar_passos
Passos do começo

### comecar_passo_conta
Conta

### comecar_passo_metas
Metas

### comecar_passo_horario
Horário

### comecar_passo_fontes
Fontes

### comecar_passo_conferir
Conferir

### comecar_conta_titulo
Sua conta

### comecar_conta_detalhe
O Goal Pacer usa o seu Claude, sem senha nova. Conectar o Google é opcional: aprofunda o contexto.

### comecar_req_claude
Claude Code instalado e logado com um plano Pro ou Max.

### comecar_req_conectores
Opcional: Google Calendar e Gmail conectados em claude.ai, com permissão de escrita, para os blocos na agenda e o email das 7h.

### comecar_req_calendario
Opcional, com o Google Calendar: um calendário chamado Metas, o único em que o Goal Pacer escreve.

### comecar_link_claude
Como instalar o Claude Code

### comecar_link_conectores
Abrir Conectores em claude.ai

### comecar_link_calendario
Criar o calendário Metas

### comecar_claude_ok
Claude Code encontrado neste computador.

### comecar_claude_falta
Falta o Claude Code neste computador.

### comecar_claude_titulo
Claude Code

### comecar_claude_logado
Claude Code instalado e com login.

### comecar_claude_logado_plano
Claude Code instalado e com login (plano {plano}).

### comecar_claude_sem_login
Claude Code instalado, falta o login.

### comecar_claude_instalando
Instalando o Claude Code: esta tela confere sozinha quando terminar.

### comecar_instalar_claude
Instalar o Claude Code

### comecar_login_claude
Fazer login

### comecar_login_instrucao
Entre com a sua conta Claude na página que abriu no navegador. No fim, ela mostra um código: copie e cole aqui.

### comecar_login_link
Abrir a página de login

### comecar_login_codigo
Código da página de login

### comecar_login_entrar
Entrar

### comecar_login_ok
Login feito: o Claude Code está pronto neste computador.

### comecar_login_recusado
O login não passou ({erro}). Peça outro código em Fazer login e cole o novo.

### comecar_login_expirado
A página de login expirou: clique em Fazer login para abrir outra.

### comecar_login_codigo_invalido
Cole o código inteiro que a página de login mostrou.



### comecar_conectores_titulo
Conectores (opcional)

### comecar_conectores_opcionais
Sem conector, metas, plano e dia saem só do que você escrever. Com Google Calendar e Gmail, os blocos vão para a agenda, o email chega às 7h e o check-in se infere sozinho; Notion e Drive trazem evidências. Esta tela confere sozinha enquanto você conecta.

### comecar_conector_conectado
conectado

### comecar_conector_reconectar
pede reconexão

### comecar_conector_desconectado
não conectado

### comecar_chaveiro
Se o Mac pedir acesso às Chaves para o claude, escolha Permitir sempre: é o que deixa o job das 7h rodar sozinho.

### vazio_titulo
Sem metas por enquanto

### vazio_texto
As telas mostram o que existe, e aqui fica vazio até a primeira meta. A tela Começar leva ao primeiro dia em poucos minutos.

### vazio_acao
Ir para Começar

### comecar_conferir
Conferir minha conta

### comecar_conferir_de_novo
Conferir outra vez

### comecar_conferindo
Conferindo, leva um minuto...

### comecar_email_ok
E-mail encontrado: {email}

### comecar_email_falta
Não achei um e-mail enviado pela conta: você confirma o endereço no último passo.

### comecar_metas_ok
Calendário Metas encontrado.

### comecar_metas_falta
Sem calendário Metas: os blocos ficam no app. Para vê-los no Google Calendar, crie um calendário com esse nome.

### comecar_fontes_achadas
Fontes que dá para ler: {fontes}

### comecar_continuar
Continuar

### comecar_voltar
Voltar

### comecar_metas_titulo
Suas metas

### comecar_metas_detalhe
Até 5 metas. Diga o prazo e quantas horas por semana cada uma pede; o resto sai daí.

### comecar_meta_n
Meta {n}

### comecar_meta_titulo
O que você quer alcançar

### comecar_meta_exemplo
Ex.: correr 10 km

### comecar_meta_prazo
Prazo

### comecar_meta_horas
Horas por semana

### comecar_meta_horas_ajuda
Um número honesto. Dá para ajustar depois na tela da meta.

### comecar_meta_impacto
Peso no objetivo

### comecar_meta_objetivo
Objetivo (opcional)

### comecar_meta_objetivo_ajuda
O que muda quando a meta acontece. Metas com o mesmo objetivo andam juntas.

### comecar_objetivo_exemplo
Ex.: mais saúde

### comecar_meta_externo
O prazo é de fora (outra pessoa ou evento marcou)

### comecar_tirar_meta
Tirar esta meta

### comecar_mais_meta
Mais uma meta

### comecar_sem_metas
Escreva ao menos uma meta com título, prazo e horas.

### comecar_horario_titulo
Seu horário útil

### comecar_horario_detalhe
Quando os blocos podem entrar na agenda, no formato 09:00-18:00. Em branco, o dia fica livre.

### comecar_horario_seg_sex
Segunda a sexta

### comecar_horario_sab
Sábado

### comecar_horario_dom
Domingo

### comecar_horario_vazio
sem blocos

### comecar_fontes_titulo
Onde estão as pistas

### comecar_fontes_detalhe
No começo de cada mês o Goal Pacer lê só o que você marcar aqui, em modo só leitura, para ver sinais de avanço.

### comecar_palavras_titulo
Palavras-chave

### comecar_palavras_detalhe
Até 3 por meta, separadas por vírgula. É o que a leitura do mês procura.

### comecar_palavras_exemplo
Ex.: treino, corrida, pace

### comecar_lembretes
Lembrete do Google Calendar em cada bloco

### comecar_conferir_titulo
Conferir e gravar

### comecar_conferir_detalhe
O e-mail recebe o resumo das 7h; o fuso decide o horário dos blocos.

### comecar_email
Seu e-mail

### comecar_fuso
Fuso horário

### comecar_idioma
Idioma

### comecar_gravar
Gravar minhas metas

### comecar_pronto_titulo
Tudo pronto

### comecar_pronto_detalhe
O primeiro dia sai com o job diário, às 7h.

### comecar_pronto_texto
Para ver agora, gere o primeiro dia: o Goal Pacer monta o plano do mês, encaixa os blocos no calendário Metas e manda o e-mail. Leva alguns minutos.

### comecar_pronto_texto_app
O primeiro dia está sendo gerado: o Goal Pacer monta o plano do mês e encaixa os blocos no seu horário. Aparece em Hoje em alguns minutos.

### comecar_pronto_sem_instalacao
Este painel não é de uma instalação: rode o instalador para o dia sair sozinho às 7h.

### comecar_primeiro_dia
Gerar meu primeiro dia agora

### comecar_ir_hoje
Abrir Hoje

### app_titulo
Goal Pacer como app

### app_detalhe
Um ícone que abre o painel em janela própria.

### app_ja_instalado
Você já está usando o app.

### app_instalar
Instalar o app

### app_chrome
Chrome ou Edge: clique no ícone de instalar, no fim da barra de endereço.

### app_mac
No Mac, o app Goal Pacer abre o painel em janela própria: procure em Aplicativos ou no Launchpad.

### app_windows
No Windows, o Goal Pacer abre o painel em janela própria: procure Goal Pacer no menu Iniciar.

### app_safari
Safari: menu Arquivo > Adicionar ao Dock.

### manutencao_titulo
Manutenção

### manutencao_detalhe
Versão {versao}. Só neste computador.

### manutencao_doctor
Conferir instalação

### manutencao_conferindo
Conferindo a instalação, leva um minuto...

### manutencao_atualizar
Procurar atualização

### manutencao_remover
Remover deste computador

### manutencao_remover_explica
Tira os jobs, o painel, os atalhos e o app deste computador. Suas metas, planos e registro ficam na pasta de dados, para uma instalação futura.

### manutencao_remover_sim
Remover agora

### manutencao_removendo
Removendo o Goal Pacer. Esta tela sai do ar em instantes; seus dados ficam em {dados}.

### manutencao_versao_nova
Versão {versao} disponível: Procurar atualização baixa, confere e aplica.

### acao_no_exemplo
No painel de exemplo esta ação fica desligada.

### comecar_corrigir
Alguns campos pedem ajuste antes de gravar.

### comecar_gravado
Metas gravadas.

### comecar_sem_rascunho
Nada respondido: comece pelo passo Metas.

### comecar_sem_instalacao
Este painel não é de uma instalação: rode o instalador primeiro.

### comecar_primeiro_dia_ok
Primeiro dia em andamento: o e-mail chega em alguns minutos.

### comecar_primeiro_dia_erro
O agendador não aceitou disparar o dia ({erro}).

### atualizar_pelo_zip
Instalação pela pasta baixada: baixe o zip da versão nova, descompacte e clique duas vezes em Instalar Goal Pacer.

### atualizar_em_andamento
Uma atualização está em andamento.

### atualizar_iniciado
Procurando atualização. O painel reinicia se houver versão nova.

## coach

### estado_florescendo
Florescendo

### estado_ritmo
Ganhando ritmo

### estado_atencao
Pede atenção

### estado_travada
Travada

### estado_pausada
Em pausa

### estado_conquistada
Conquistada

### estagio_comeco
Começo

### estagio_construcao
Construção

### estagio_consolidacao
Consolidação

### estagio_reta_final
Reta final

### estagio_conquista
Conquista

### objetivo_firme
Avançando firme

### objetivo_construcao
Em construção

### objetivo_foco
Pede foco

### objetivo_pausado
Em pausa

### objetivo_conquistado
Conquistado

### tendencia_acelerando
acelerando

### tendencia_estavel
estável

### tendencia_desacelerando
desacelerando

### tendencia_sem_sinal
sem tendência por enquanto

### impacto_essencial
Essencial

### impacto_importante
Importante

### impacto_apoio
Apoio

### sentimento_energia
Com energia

### sentimento_firme
Firme

### sentimento_pesada
Pesada

### quadrante_proteger
Proteger

### quadrante_proteger_texto
alto impacto e boa tração: guarde o horário que funciona

### quadrante_destravar
Destravar

### quadrante_destravar_texto
alto impacto e pouca tração: é aqui que um passo pequeno rende mais

### quadrante_manter_leve
Manter leve

### quadrante_manter_leve_texto
boa tração e impacto menor: siga sem pedir mais tempo

### quadrante_repensar
Repensar

### quadrante_repensar_texto
impacto menor e pouca tração: vale reduzir, adiar ou pausar

### sinal_presenca
Presença

### sinal_fluidez
Fluidez

### sinal_energia
Energia

### sinal_evidencia
Sinais de fora

### sinal_espaco
Espaço na agenda

### sinal_avanco
Avanço

### presenca_alto
aparecendo com constância nos blocos

### presenca_medio
aparecendo em parte dos blocos

### presenca_baixo
poucos blocos feitos nas últimas semanas

### presenca_sem_sinal
sem blocos vencidos para ler

### fluidez_alto
encaixa bem na rotina

### fluidez_medio
às vezes muda de lugar na agenda

### fluidez_baixo
briga com a agenda: blocos movidos ou apagados

### fluidez_sem_sinal
sem blocos vencidos para ler

### energia_alto
você marcou que está com energia

### energia_medio
você marcou que está firme

### energia_baixo
você marcou que está pesada

### energia_sem_sinal
sem resposta recente no check-in

### evidencia_alto
o mundo está vendo: sinais recentes de fora

### evidencia_medio
um sinal recente de fora

### evidencia_baixo
poucos sinais de fora

### evidencia_sem_sinal
nenhum sinal de fora neste mês

### espaco_alto
cabe folgada no mês

### espaco_medio
cabe justa no mês

### espaco_baixo
a agenda do mês não comporta tudo

### espaco_sem_sinal
sem plano do mês para ler

### funcionando
O que está funcionando: {frase}.

### atrito
Onde está o atrito: {frase}.

### sem_atrito
Sem atrito à vista.

### passo_florescendo
Proteja o horário que está funcionando e escolha o próximo marco.

### passo_ritmo
Mantenha os blocos da semana; um marco pequeno consolida o ritmo.

### passo_atencao
Escolha um bloco curto e fácil para esta semana e marque como foi.

### passo_travada
Olhe para esta meta com calma: reduza as horas, adie o prazo ou troque o horário.

### passo_pausada
Sem pressa: ela volta quando fizer sentido.

### passo_conquistada
Celebre e decida o que vem depois.

### manchete_florescendo
Semana florescendo. Proteja o que está funcionando.

### manchete_ritmo
Semana em ritmo. {meta} é o que mais move seus objetivos agora.

### manchete_atencao
A semana pede atenção. Comece por {meta}, com um bloco curto.

### manchete_sem_sinal
Semana começando. Um bloco feito hoje já dá direção.

### alavanca
O que mais move este objetivo agora: {meta}.

### sem_alavanca
Todas as metas deste objetivo estão em pausa ou conquistadas.

### horizonte_hoje
Hoje

### horizonte_hoje_leitura
presença

### horizonte_semana
Semana

### horizonte_semana_leitura
ritmo

### horizonte_mes
Mês

### horizonte_mes_leitura
direção

### presenca_sem_blocos
Dia livre

### presenca_por_comecar
Por começar

### presenca_andamento
Em andamento

### presenca_cumprido
Dia bem usado

### ritmo_florescendo
Florescendo

### ritmo_ritmo
Em ritmo

### ritmo_atencao
Pede atenção

### ritmo_sem_sinal
Sem sinal

### direcao_firme
Avançando firme

### direcao_construcao
Em construção

### direcao_foco
Pede foco

### direcao_pausado
Em pausa

### direcao_conquistado
Conquistado

### espaco_folgado
Folgado

### espaco_justo
Justo

### espaco_apertado
Apertado

### dias_sem_feito
último bloco feito há {n} dias

### sem_feito
nenhum bloco feito nas últimas semanas

### objetivo_implicito
Esta meta não tem um objetivo final cadastrado; ela conta como o próprio objetivo.

### compasso_folga
com folga para o prazo

### compasso_compasso
no compasso do prazo

### compasso_folego
pede fôlego até o prazo

### periodo_alavanca_semana
O que mais move esta semana: {meta}.

### periodo_alavanca_mes
O que mais move este mês: {meta}.

### periodo_alavanca_trimestre
O que mais move este trimestre: {meta}.

### periodo_alavanca_semestre
O que mais move este semestre: {meta}.

### periodo_alavanca_ano
O que mais move este ano: {meta}.

### periodo_sem_alavanca
Nenhuma meta ativa passa por este período.

### periodo_passado
Período encerrado. O que funcionou aqui vira referência para o próximo.

### periodo_futuro_um
À frente, com um prazo de meta neste período.

### periodo_futuro_n
À frente, com {n} prazos de meta neste período.

### periodo_futuro_livre
À frente, sem prazos de meta neste período.

## janela

### esperando
Abrindo o painel do Goal Pacer...

### sem_painel
O painel não respondeu em 127.0.0.1:8765. No Terminal, rode goal-pacer doctor para ver o que falta e depois use Ver > Recarregar.

### instalando
Preparando o Goal Pacer neste Mac. Leva um minuto na primeira vez.

### instalacao_parou
A preparação parou. As últimas linhas abaixo dizem o motivo.

### tentar_outra_vez
Tentar outra vez

### ocultar
Ocultar Goal Pacer

### sair
Sair do Goal Pacer

### editar
Editar

### desfazer
Desfazer

### refazer
Refazer

### recortar
Recortar

### copiar
Copiar

### colar
Colar

### selecionar_tudo
Selecionar tudo

### ver
Ver

### recarregar
Recarregar

### janela
Janela

### minimizar
Minimizar

### fechar
Fechar

## saude

### titulo
Perto do limite

### job_perto_do_teto
O job de {quando} levou {minutos} min, perto do teto de {teto} min.

### espera_lock
O job de {quando} esperou {minutos} min pela pasta de dados.

### limite_de_uso
A janela de uso da assinatura esgotou {n} vezes nos últimos 7 dias; um horário de job mais cedo pode ajudar.

### tokens_acima
O último job usou {tokens} tokens, acima do habitual ({mediana}).

### chamada_lenta
Uma chamada a {ferramenta} levou {segundos} s nos últimos 7 dias; o teto por chamada é 180 s.

### retries_startup
{pct}% das chamadas aos conectores precisaram repetir nos últimos 7 dias.

### registro_grande
O registro.json está com {mb} MB; o arquivo anual alivia a partir de janeiro.

### painel_lento
As telas do painel levaram até {ms} ms nos pedidos mais lentos dos últimos 7 dias.

### erros_tela
O painel registrou {n} erro(s) de tela nos últimos 7 dias: goal-pacer logs eventos --tipo erro_front.

### notificacao
Goal Pacer, três jobs seguidos: {texto}


## logs

### sem_registros
Nenhum registro local por aqui: instale com ./install.sh (ou tire GP_TELEMETRIA=0).

### sem_trace
Nenhum trace de job por aqui. O primeiro sai no job das 7h.

### sem_eventos
Nenhum evento nos últimos {dias} dia(s).

### titulo_trace
Trace {trace}

### titulo_resumo
Registros locais dos últimos {dias} dias

### titulo_painel
Painel (pedidos, p50, p95, máximo)

### titulo_conectores
Conectores (chamadas, p50, p95, máximo)

### nada_medido
nada medido no período

### linha_chamadas
chamadas aos conectores: {total} (repetidas: {repetidas}) · erros de tela: {erros_front} · erros do painel: {erros_painel}

### linha_dados
registro.json: {registro} KB · dias: {dias} · logs: {logs} KB


## perfil_cli

### linha_meta
{meta} {progresso}% (+{presumido}% feita?) · ritmo esperado {ritmo}%

## calendario

### nome_idioma
pt-BR

### dias_longos
Segunda, Terça, Quarta, Quinta, Sexta, Sábado, Domingo

### dias_curtos
seg, ter, qua, qui, sex, sáb, dom

### meses
janeiro, fevereiro, março, abril, maio, junho, julho, agosto, setembro, outubro, novembro, dezembro

### meses_curtos
jan, fev, mar, abr, mai, jun, jul, ago, set, out, nov, dez

### data_curta
{dd}/{mm}

### decimal
,

### locale_numeros
pt-BR

### dias_celula
seg, ter, qua, qui, sex, sab, dom

### faixas
manha, tarde, noite

### dias_nota
segunda, terça, quarta, quinta, sexta, sábado, domingo

### faixas_nota
de manhã, à tarde, à noite


## tom

### palavras_proibidas
atrasada, atrasado, atrasadas, atrasados, falhou, falharam, perdeu, perdida, não fez, nao fez, deveria, deveriam, de novo, ainda

### placar
de

### pendente_ha
pendente há {n} dia, pendente ha {n} dia

### regras_prompt
Tom sem culpa e sem cobrança. Palavras que nunca aparecem: atrasada, falhou, perdeu, "não fez", deveria, "pendente há N dias", "de novo", ainda. Nunca um placar do tipo "N de M". Verbos para frente: "dá para cobrir", "fica para quinta", "volta às 14h".

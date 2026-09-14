# Pasta de dados: formato, ids e regras

Contrato dos arquivos que o Goal Pacer lê e grava. A v1 (skill + jobs) e a v2 (web app) leem os mesmos arquivos; `scripts/goalpacer/schema.py` é a fonte única do esquema e gera a seção "Esquemas" deste documento (`cd scripts && python3 -m goalpacer.schema --md`). Tudo aqui vale para qualquer instalação: nada de dados do autor.

## Onde fica e quem escreve

- Pasta padrão: `~/.goal-pacer/dados/` (`DATA_DIR`; `GP_DATA_DIR` ou `--dados` sobrepõem). Nunca em Desktop, Downloads ou Documents (o launchd não lê pastas protegidas por TCC; `install.sh` e todo CLI recusam).
- Um escritor por arquivo. O modelo conversa e redige; o script decide e grava.

| Arquivo | Quem grava | Quem lê |
|---|---|---|
| `contexto.md`, `metas/M<nn>.md` | `onboarding.py` (de uma vez, a partir do rascunho); o usuário edita à mão | todos |
| `fontes/M<nn>.md` | onboarding e `mensal` interativo (pesquisa confirmada) | `balanco.py`, plano mensal |
| `sinais/AAAA-MM-DD.md` | `mensal.py`, a partir do `result` da sessão `mensal-ler` | prosa do plano, `status` |
| `cache/*.json` | proxies (`calendar-*`), `calendar_sync.py` (`ops-*`), `parse_whatsapp.py`, onboarding (rascunho) | `validar.py`, `agenda`, `calendar_ops` |
| `planos/AAAA-MM.md` | `balanco.py --render` (números e seções) + prosa nos blocos marcados | `diario`, `status`, email |
| `semanas/AAAA-Www.md` | gerado do plano (espelho); nunca editado à mão | v2, leitura humana |
| `dias/AAAA-MM-DD.md` | `diario.py` (`render`) | `checkin`, email (projeção direta), `calendar_sync.py` |
| `registro.json` | só `registro.py` | `perfil.py`, `balanco.py`, `status` |
| `perfil.json` | só `perfil.py` (determinístico, só de blocos confirmados) | `balanco.py`, `status`, prosa |
| `perfil.md` | sessão interativa, uma nota confirmada por `checkin`; o usuário edita à vontade | prompts de prosa (tamanho e tom) |
| `inbox/whatsapp/` | o usuário coloca o export | `parse_whatsapp.py` |
| `.lock` | `goalpacer/io.py` (`registro.py lock|unlock`) | jobs e modos interativos |

## Layout

```
metas/M01.md ...       uma meta por arquivo, nunca apagado (remoção é estado: arquivada)
contexto.md            instalação: fuso, horário útil, calendários, e-mail, fontes ativas, tetos
fontes/M01.md ...      pesquisa por meta: URLs, trecho literal de onde saiu o número, ou a busca sem número; `pendente` quando titulo/horizonte/prazo mudaram
sinais/AAAA-MM-DD.md   resumos das fontes (Gmail, WhatsApp, Notion, Drive), nunca conteúdo bruto; cabeçalho com fontes, query e "viu N / abriu M"
cache/                 calendar-<modo>-<data>.json (compacto), ops-<run_id>.json, whatsapp-AAAA-MM.json (apagado logo após mensal-ler), onboarding-rascunho.json; tudo com mais de 7 dias é apagado
planos/AAAA-MM.md      balanço do mês: números gerados + prosa em blocos marcados
semanas/AAAA-Www.md    espelho da seção ### AAAA-Www do plano
dias/AAAA-MM-DD.md     o dia: blocos encaixados nas janelas livres
registro.json          execuções, check-ins, feitas, progresso declarado, notas recusadas
perfil.json            estatísticas derivadas (progresso, ritmo, janelas, fator de duração)
perfil.md              o que o sistema sabe sobre o usuário, em prosa
inbox/whatsapp/        exports (o plano diz "export lido em <data>; pode apagar")
.lock                  lock único da pasta
```

## Ids e grafo

- Meta `M<nn>`: dois dígitos, igual ao nome do arquivo, nunca reutilizado nem renumerado.
- Mês `AAAA-MM`. Semana ISO `AAAA-Www` (segunda a domingo); a semana pertence ao mês que contém a sua quinta-feira, e `planos/AAAA-MM.md` tem uma seção `### AAAA-Www` por semana cuja quinta cai no mês.
- Bloco (task) `D-AAAA-MM-DD-<ss>`: a data é a do dia em que o bloco nasceu; `ss` é único por data. Um `dias/<d>.md` pode conter blocos de outra data quando `origem: reagendada`. "Bloco" é o termo em toda superfície que o usuário lê; "task" só em código e esquema.
- `gp_key` = `gp:<task_id>/<instalacao_id>`: última linha da descrição de cada evento criado no Calendar. É a chave estruturada pela qual o script reconhece um bloco seu (inclusive movido para o calendário primário) sem ler texto livre; `[GP]` no título é só convenção visual.
- `hash_metas`: sha256 curto de `id, titulo, horizonte, prazo, prazo_externo` de todas as metas, ordenadas por id. Custo, estado, confiança e palavras-chave ficam fora. Hash diferente do gravado em `planos/` exige `mensal` antes do próximo `diario` e marca `fontes/M<nn>.md` das metas alteradas como `pendente`.

Estados de bloco e origens:

```
planejada --> feita | movida | reagendada | apagada | nao_feita | cancelada
                |
                +-- origem: inferido | confirmado | presumido | prazo
sem_sinal: só enquanto a janela ainda não venceu (nunca é estado final)
proibido: inferido ou presumido sobrescrever confirmado
```

- Intocado e vencido = `feita` com `origem: presumido` ("feita?"): aparece com rótulo no email, no `status` e em `dias/`, entra no progresso exibido; só `origem: confirmado` abate a demanda e alimenta `perfil.json`. "feita?" fica no email por 2 dias; o "+N% feita?" do progresso conta só presumidas dos últimos 14 dias; as mais antigas viram "N h presumidas não contadas" no `status`.
- `prazo` marca transições automáticas por data (meta vencida ou arquivada: blocos abertos viram `cancelada`).
- No balanço: `apagada`, `nao_feita` e `cancelada` contam como não feitas; `planejada`, `sem_sinal`, `movida` e `reagendada` como alocadas; `feita` confirmada abate o restante.

## Front-matter

Subconjunto plano de YAML, parser estrito em `goalpacer/frontmatter.py`, sem PyYAML:

```
---
chave: valor                 chave [a-z][a-z0-9_]*; ": " separa
texto: "com \" e \\"         string entre aspas duplas (escapes \" e \\)
outro: 'texto'               aspas simples, sem escapes
lista: [a, 2, "c d", true]   lista inline; itens com as mesmas regras
vazio: null                  null ou ~ vira nulo
# comentário                 só em linha inteira
---
```

Valor nu é string, salvo se casar inteiro, decimal, `true`/`false`, `null`, data `AAAA-MM-DD` ou datetime ISO com `T` (aí vira o tipo correspondente; `007` continua string). Tudo depois do primeiro `: ` é o valor. É erro: indentação, `- item`, chave duplicada, dois-pontos sem espaço, `chave:` sem valor, lista dentro de lista, comentário no meio da linha, escape desconhecido. Erros dizem a linha. `frontmatter.coagir` converte pelos tipos do esquema (string `"4"` vira `4.0` onde o campo é float) e aplica defaults.

## Corpo dos markdowns

- `dias/AAAA-MM-DD.md`: seções `## Hoje`, `## Desde <dia>` (condicional), `## Progresso`, `## Avisos` (condicional), nesta ordem. Cada bloco em `## Hoje` é uma subseção `### D-AAAA-MM-DD-<ss> <título>` seguida de linhas `- chave: valor` com os campos de `task` (mesma gramática de valores do front-matter; `id` e `titulo` vêm do título):

```
### D-2026-09-28-01 Exercícios do módulo 3
- meta: M01
- semana: 2026-W40
- inicio: 2026-09-28T09:00:00-03:00
- fim: 2026-09-28T10:30:00-03:00
- duracao_h: 1.5
- porque: M1 pede 4h nesta semana; janela livre das 9h
- efeito: "se feita: M1 41% → 44%"
- estado: planejada
- origem: inferido
- calendar_event_id: evt-...
- calendar_id: ...@group.calendar.google.com
```

- `planos/AAAA-MM.md`: `## Balanço`, `## Metas` (uma `### M<nn> <título>` por meta, com prosa entre `<!-- prosa:nome -->` e `<!-- /prosa:nome -->`), `## Semanas` (`### AAAA-Www`), `## Evidências` e `## Decisões` (condicionais). Os números vêm de `balanco.py --render` e o validador confere que são idênticos ao gerado; a prosa é preservada na regeneração salvo bloco vazio ou marcado `<!-- prosa:atualizar -->`.
- O email das 7h é projeção direta de `dias/<hoje>.md` (`render.py --email-texto`), nunca prosa nova.

## Esquemas

A seção abaixo é gerada; `tests/test_gerados.py` compara byte a byte.

<!-- schema:inicio -->

Gerado por `python3 -m goalpacer.schema --md`; não edite à mão. `schema_version`: 1.

### `metas` (`metas/M<nn>.md`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| id | str | sim | formato: meta | `M<nn>`, igual ao nome do arquivo, nunca reutilizado |
| titulo | str | sim |  | título humano da meta |
| horizonte | enum | sim | enum: trimestre, semestre, ano | trimestre, semestre ou ano |
| prazo | date | sim |  | data limite |
| prazo_externo | bool | não | default: false | prazo imposto por terceiros (muda a decisão sugerida) |
| estado | enum | não | enum: ativa, pausada, concluida, vencida, arquivada; default: "ativa" | ativa, pausada (sai do plano e volta quando reativada), concluida, vencida ou arquivada (remoção é arquivada) (fora do `hash_metas`) |
| custo_h_semana_min | float | não |  | piso de horas/semana encontrado na pesquisa (fora do `hash_metas`) |
| custo_h_semana_max | float | não |  | teto de horas/semana encontrado na pesquisa (fora do `hash_metas`) |
| custo_h_semana_escolhido | float | sim |  | horas/semana confirmadas pelo usuário (> 0); entra no balanço (fora do `hash_metas`) |
| semanas_pesquisa | int | sim |  | semanas de duração estimadas (> 0); custo_total_h = escolhido × semanas (fora do `hash_metas`) |
| confianca | enum | sim | enum: alta, media, baixa, usuario | alta, media, baixa (pesquisa) ou usuario (número dado à mão) (fora do `hash_metas`) |
| fonte | str | não | default: "" | `fontes/M<nn>.md`, URL ou vazio quando o número é do usuário (fora do `hash_metas`) |
| palavras_chave | list | não | default: [] | até 3 termos para buscar evidências (fora do `hash_metas`) |
| criado_em | datetime | sim |  | instante do onboarding (fora do `hash_metas`) |
| objetivo | str | não | default: ""; formato: objetivo | `O<nn>` do objetivo final que esta meta serve; vazio = a meta é o próprio objetivo (fora do `hash_metas`) |
| impacto | enum | não | enum: essencial, importante, apoio; default: "importante" | peso no objetivo: essencial (3), importante (2) ou apoio (1) (fora do `hash_metas`) |

### `objetivo` (`objetivos/O<nn>.md`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| id | str | sim | formato: objetivo | `O<nn>`, igual ao nome do arquivo |
| titulo | str | sim |  | o que a pessoa quer que mude, em palavras dela |
| estado | enum | não | enum: ativo, conquistado, pausado; default: "ativo" | ativo, conquistado ou pausado |
| criado_em | datetime | não |  | quando o objetivo foi cadastrado |

### `fonte_pesquisa` (`fontes/M<nn>.md`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| id | str | sim | formato: meta | `M<nn>` da meta |
| pesquisado_em | datetime | sim |  | quando a pesquisa (ou a estimativa manual) foi feita |
| estado | enum | não | enum: ok, sem_numero, pendente; default: "ok" | ok, sem_numero (busca sem número) ou pendente (titulo/horizonte/prazo mudaram) |
| busca | str | não | default: "" | a consulta feita, ou vazio se o número foi dado à mão |
| urls | list | não | default: [] | páginas de onde o número saiu |
| trecho | str | não | default: "" | trecho literal citado; sem trecho a confiança é baixa |
| custo_h_semana_min | float | não |  | piso encontrado |
| custo_h_semana_max | float | não |  | teto encontrado |
| semanas_pesquisa | int | não |  | duração encontrada, em semanas |
| hash_meta | str | não | default: "" | hash dos campos da meta na pesquisa (titulo, horizonte, prazo); diferente = pendente |

### `contexto` (`contexto.md`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| schema_version | int | sim |  | versão do esquema gravada no onboarding (9.1) |
| instalacao_id | str | sim | formato: instalacao_id | id desta instalação; vai na `gp_key` de cada bloco (D4.9) |
| idioma | str | não | default: "pt-BR" | idioma das superfícies (`references/copy.<idioma>.md`) |
| timezone | str | sim |  | nome IANA validado no onboarding |
| horario_util_seg_sex | str | não | default: "08:00-19:00"; formato: horario_util | `HH:MM-HH:MM`; vazio = sem janela |
| horario_util_sab | str | não | default: "09:00-13:00"; formato: horario_util | `HH:MM-HH:MM`; vazio = sem janela |
| horario_util_dom | str | não | default: ""; formato: horario_util | `HH:MM-HH:MM`; vazio = sem janela |
| buffer_min | int | não | default: 10 | minutos de folga antes e depois de cada evento ocupado |
| calendar_id_metas | str | não | default: "" | único calendário com escrita (criado à mão); vazio = sem Google Calendar (blocos só no app) |
| calendar_id_primario | str | não | default: "" | calendário cujo id é o e-mail do usuário; obrigatório junto com o Metas |
| calendarios_lidos | list | não | default: [] | ids lidos para as janelas; vazio = todos; primário e Metas sempre entram |
| email_proprio | str | não | default: ""; formato: email | único destinatário do email das 7h; vazio = sem Gmail (sem email, o dia fica no app) |
| email_alias | list | não | default: [] | endereços send-as excluídos da busca do Gmail (D4.8) |
| fontes_ativas | list | não | itens: gmail, whatsapp, notion, drive; default: [] | fontes de evidência desta instalação (9.2) |
| lembretes | enum | não | enum: sim, nao; default: "nao" | lembretes do Google nos blocos; nao = overrideReminders vazio |
| tetos_gmail_threads | int | não | default: 15 | threads Gmail por meta no mensal-ler (7.1) |
| tetos_gmail_threads_inteiras | int | não | default: 3 | threads abertas inteiras por meta |
| tetos_notion_paginas | int | não | default: 5 | páginas Notion por meta |
| tetos_drive_arquivos | int | não | default: 5 | arquivos Drive por meta |
| tetos_drive_caracteres | int | não | default: 4000 | caracteres lidos por arquivo Drive |
| restricoes_horario | list | não | default: [] | `M<nn> HH:MM-HH:MM` por meta, vindas de notas confirmadas no checkin |
| pessoas | list | não | default: [] | nomes que o usuário quer ver reconhecidos na prosa (opcional) |

### `plano` (`planos/AAAA-MM.md`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| mes | str | sim | formato: mes | `AAAA-MM` |
| hash_metas | str | sim |  | `hash_metas()` das metas na geração |
| hash_numeros | str | sim |  | hash do corpo sem o texto dos blocos de prosa; diferente = números alterados fora do balanço |
| fontes | list | não | itens: gmail, whatsapp, notion, drive; default: [] | fontes que entraram neste mensal |
| gerado_em | datetime | sim |  | instante da geração |
| run_id | str | sim |  | execução que gerou |

### `sinais` (`sinais/AAAA-MM-DD.md`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| data | date | sim |  | dia da leitura das fontes |
| run_id | str | sim |  | execução do mensal-ler |
| fontes | list | não | itens: gmail, whatsapp, notion, drive; default: [] | fontes lidas nesta execução |
| gmail_vistos | int | não | default: 0 | threads vistas (assunto + trecho) |
| gmail_abertos | int | não | default: 0 | threads abertas inteiras |
| notion_vistos | int | não | default: 0 | páginas encontradas |
| notion_abertos | int | não | default: 0 | páginas lidas |
| drive_vistos | int | não | default: 0 | arquivos encontrados |
| drive_abertos | int | não | default: 0 | arquivos lidos |
| whatsapp_vistos | int | não | default: 0 | mensagens com palavra-chave no export |
| whatsapp_abertos | int | não | default: 0 | trechos enviados à leitura |
| whatsapp_status | str | não | default: ""; formato: status_whatsapp | ok, stale, nao_reconhecido, truncado ou sem_export |
| whatsapp_ultima_mensagem | datetime | não |  | última mensagem do export |

### `semana` (`semanas/AAAA-Www.md`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| semana | str | sim | formato: semana | `AAAA-Www` |
| mes | str | sim | formato: mes | `AAAA-MM` do plano de origem (mês da quinta-feira) |
| gerado_em | datetime | sim |  | instante da geração do espelho |
| run_id | str | não |  | execução que gerou o espelho |

### `dia` (`dias/AAAA-MM-DD.md`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| data | date | sim |  | `AAAA-MM-DD` |
| run_id | str | sim |  | execução que gerou |
| resumo_confirmadas | int | não | default: 0 | blocos confirmados desde o último dia |
| resumo_presumidas | int | não | default: 0 | blocos feita? (presumidos) ainda exibidos |
| resumo_movidas | int | não | default: 0 | blocos movidos ou reagendados |
| decisao_pendente | str | não | formato: meta | `M<nn>` da meta com decisão pendente; ausente ou vazio = nenhuma |
| motivo | str | não |  | `sem_janela` quando o dia não tem bloco; vazio caso contrário |

### `task` (`dias/AAAA-MM-DD.md, um bloco `### <task_id>` no corpo`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| id | str | sim | formato: task | `D-AAAA-MM-DD-<ss>`; a data é a do dia em que nasceu |
| titulo | str | sim |  | título humano do bloco (sem `[GP]`), até 60 caracteres |
| meta | str | sim | formato: meta | `M<nn>` |
| semana | str | sim | formato: semana | `AAAA-Www` da seção do plano que o bloco serve |
| inicio | datetime | sim |  | início planejado, hora local com offset |
| fim | datetime | sim |  | fim planejado (> inicio) |
| duracao_h | float | sim |  | horas planejadas (> 0) |
| porque | str | não | default: "" | por que este bloco hoje (meta → semana), até 90 caracteres |
| efeito | str | não | default: "" | `se feita: M3 41% → 44%` |
| estado | enum | sim | enum: planejada, feita, movida, reagendada, apagada, nao_feita, sem_sinal, cancelada | estado atual |
| origem | enum | sim | enum: inferido, confirmado, presumido, prazo | quem definiu o estado |
| calendar_event_id | str | não |  | id do evento no Calendar (vem do `tool_result` do create_event) |
| calendar_id | str | não |  | calendário onde o evento está (Metas, ou o primário se o usuário o moveu) |
| duracao_real_h | float | não |  | horas confirmadas pelo usuário no checkin |
| atualizado_em | datetime | não |  | última mudança de estado |

### `registro` (`registro.json`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| schema_version | int | sim |  | versão do esquema (9.1) |
| geracoes | dict | não | chave: texto; valor: `geracao`; default: {} | run_id → `geracao` (8.1) |
| checkins | dict | não | chave: task; valor: `checkin`; default: {} | task_id → `checkin` (último estado confirmado ou inferido) |
| feitas | dict | não | chave: meta; valor: lista de `feita`; default: {} | `M<nn>` → lista de `feita`; só origem confirmado abate a demanda |
| progresso | dict | não | chave: meta; valor: lista de `progresso_declarado`; default: {} | `M<nn>` → lista de `progresso_declarado` |
| notas_recusadas | list_dict | não | itens: `nota_recusada`; default: [] | notas de aprendizado recusadas (não voltam por 30 dias) |
| sentimentos | dict | não | chave: meta; valor: lista de `sentimento`; default: {} | `M<nn>` → lista de `sentimento` (como a pessoa está com a meta) |
| respostas_email | list | não | default: [] | ids das respostas ao email das 7h já aplicadas como check-in (nunca o texto) |

### `geracao` (`registro.json, uma entrada de geracoes`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| run_id | str | sim |  | mesmo id do log e da notificação |
| modo | str | sim |  | diario, mensal, semanal, checkin, onboarding, ... |
| data | date | sim |  | dia a que a execução se refere |
| ts | datetime | sim |  | instante do fim da execução |
| exit_code | int | sim |  | código de saída do job |
| duracao_s | float | não |  | duração de parede em segundos |
| classe | str | não |  | classe do erro, se houve |
| chave_runbook | str | não |  | seção do runbook no README |
| mensagem | str | não |  | texto da notificação, se houve erro (eng 2.3) |
| tokens | dict | não | chave: texto; valor: int; default: {} | input, cache_read, cache_creation, output |
| sessoes | list | não | default: [] | session_id de cada `claude -p` (retenção dos transcripts) |
| claude_version | str | não |  | versão do `claude` usada |
| email | enum | não | enum: enviado, falhou, nao_enviado; default: "nao_enviado" | resultado do envio |
| hash_metas | str | não |  | hash das metas na execução |
| teto_s | float | não |  | teto de tempo do job nesta execução (20 ou 40 min, mais a espera de limite de uso) |
| espera_lock_s | float | não |  | quanto o job esperou pelo lock da pasta de dados |
| alertas | list | não | default: [] | chaves dos alertas perto do limite vistos nesta execução (goalpacer/saude.py) |
| alerta_notificado | str | não |  | chave do alerta que virou notificação nesta execução |

### `checkin` (`registro.json, uma entrada de checkins`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| estado | enum | sim | enum: planejada, feita, movida, reagendada, apagada, nao_feita, sem_sinal, cancelada | estado registrado |
| origem | enum | sim | enum: inferido, confirmado, presumido, prazo | quem definiu o estado |
| ts | datetime | sim |  | instante do registro |
| duracao_real_h | float | não |  | horas confirmadas pelo usuário |
| inicio | datetime | não |  | nova janela quando movida/reagendada (do evento) |
| fim | datetime | não |  | fim da nova janela |
| calendar_id | str | não |  | calendário onde o evento está agora |
| calendar_event_id | str | não |  | id do evento encontrado |

### `feita` (`registro.json, um item de feitas[meta]`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| task_id | str | sim | formato: task | `D-AAAA-MM-DD-<ss>` |
| duracao_h | float | sim |  | horas planejadas do bloco (> 0) |
| duracao_real_h | float | não |  | horas confirmadas, quando informadas |
| origem | enum | sim | enum: inferido, confirmado, presumido, prazo | confirmado abate a demanda; presumido só é exibido |
| ts | datetime | não |  | instante do registro |

### `progresso_declarado` (`registro.json, um item de progresso[meta]`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| declarado_pct | float | sim |  | 0 a 100, declarado pelo usuário |
| ts | datetime | sim |  | instante da declaração |

### `sentimento` (`registro.json, um item de sentimentos[meta]`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| valor | enum | sim | enum: energia, firme, pesada | energia, firme ou pesada |
| ts | datetime | sim |  | instante da resposta no check-in |

### `nota_recusada` (`registro.json, um item de notas_recusadas`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| texto | str | sim |  | a nota proposta que o usuário recusou |
| ts | datetime | sim |  | instante da recusa |

### `perfil` (`perfil.json`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| schema_version | int | sim |  | versão do esquema |
| gerado_em | datetime | sim |  | instante da geração por perfil.py |
| n_confirmadas | int | não | default: 0 | observações com origem confirmado |
| metas | dict | não | chave: meta; valor: `perfil_meta`; default: {} | `M<nn>` → `perfil_meta` |
| janelas | dict | não | chave: janela_perfil; valor: `perfil_janela`; default: {} | `<dia>-<faixa>` → `perfil_janela` (ex.: seg-manha) |
| preferencias | dict | não | objeto `perfil_preferencias`; default: {} | `perfil_preferencias` derivadas só de confirmadas |

### `perfil_meta` (`perfil.json, uma entrada de metas`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| progresso_pct | float | não | default: 0.0 | max(horas confirmadas ÷ custo total, último declarado) |
| progresso_presumido_pct | float | não | default: 0.0 | presumidas dos últimos 14 dias ÷ custo total |
| ritmo_esperado_pct | float | não | default: 0.0 | semanas decorridas ÷ semanas até o prazo |
| delta | float | não | default: 0.0 | progresso_pct − ritmo_esperado_pct (pode ser negativo) |
| horas_confirmadas | float | não | default: 0.0 | Σ duracao_h das feitas confirmadas |
| horas_presumidas_nao_contadas | float | não | default: 0.0 | presumidas com mais de 14 dias |
| fator_duracao | float | não | default: 1.0 | mediana de duracao_real_h ÷ duracao_h (default 1,0) |
| h_semana_real | float | não | default: 0.0 | média móvel de 4 semanas de horas confirmadas |

### `perfil_janela` (`perfil.json, uma entrada de janelas`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| taxa_conclusao | float | sim |  | 0 a 1 |
| n | int | sim |  | observações confirmadas na célula (mínimo 5 para influenciar) |

### `perfil_preferencias` (`perfil.json, o objeto preferencias`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| bloco_medio_h | float | não |  | duração média dos blocos confirmados |
| taxa_por_duracao | dict | não | chave: texto; valor: float; default: {} | faixa de duração → taxa de conclusão |

### `cache_calendar` (`cache/calendar-<modo>-<data>.json`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| calendar_id_metas | str | sim |  | calendário Metas na geração (define a projeção) |
| janela_inicio | datetime | sim |  | início do período lido |
| janela_fim | datetime | sim |  | fim do período lido |
| gerado_em | datetime | sim |  | instante da leitura |
| run_id | str | não |  | execução que leu |
| calendarios | list_dict | não | itens: `calendario`; default: [] | lista de `calendario` lidos |
| eventos | list_dict | não | itens: `evento`; default: [] | lista de `evento` projetados |

### `calendario` (`cache/calendar-*.json, um item de calendarios`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| id | str | sim |  | id do calendário (o primário tem o e-mail como id) |
| summary | str | não | default: "" | nome do calendário |
| time_zone | str | não | default: "" | fuso do calendário |

### `evento` (`cache/calendar-*.json, um item de eventos (projeção de privacidade)`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| id | str | sim |  | id do evento (instância expandida: `<base>_<ts>`) |
| calendar_id | str | sim |  | calendário de origem |
| start | str | sim |  | ISO com offset, ou `AAAA-MM-DD` se dia inteiro |
| end | str | sim |  | ISO com offset, ou `AAAA-MM-DD` se dia inteiro |
| all_day | bool | não | default: false | true quando start é só data |
| created | datetime | não |  | criação no Google |
| updated | datetime | não |  | última alteração no Google |
| status | str | não | default: "confirmed" | confirmed, tentative ou cancelled |
| transparency | str | não | default: "opaque" | transparent = livre; ausente no Google = ocupado |
| self_response | str | não | default: "" | attendees[].self.responseStatus; vazio = sem convite |
| event_type | str | não | default: "" | default, outOfOffice, workingLocation, fromGmail, ... |
| recurring_event_id | str | não | default: "" | id da série, se instância recorrente |
| summary | str | não |  | só para eventos do Metas; null fora dele |
| description | str | não |  | só para eventos do Metas; null fora dele |
| gp_key | str | não | formato: gp_key | `gp:<task_id>/<instalacao_id>` da última linha da descrição, ou null |

### `ops` (`cache/ops-<run_id>.json`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| run_id | str | sim |  | execução que planejou as ops |
| calendar_id_metas | str | sim |  | único calendário onde se cria |
| gerado_em | datetime | sim |  | instante do planejamento |
| ops | list_dict | não | itens: `op`; default: [] | lista de `op` na ordem de execução |

### `op` (`cache/ops-*.json, um item de ops`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| op | enum | sim | enum: create, update, delete | create, update ou delete |
| task_id | str | sim | formato: task | bloco a que a op pertence |
| calendar_id | str | sim |  | calendário alvo (create só no Metas) |
| calendar_event_id | str | não |  | obrigatório em update e delete |
| corpo | dict | não | conteúdo livre; default: {} | argumentos do proxy (summary, description, start, end, timeZone, ...) |
| status | enum | não | enum: ok, erro | ok ou erro depois de executar; ausente = não rodou (= falhou) |
| mensagem | str | não |  | texto do erro do conector, quando status = erro |
| event_id_resultado | str | não |  | id devolvido pelo create_event |

### `rascunho_onboarding` (`cache/onboarding-rascunho.json`)

| campo | tipo | obrigatório | enum/default | descrição |
|---|---|---|---|---|
| versao | int | sim |  | versão do formato do rascunho |
| atualizado_em | datetime | sim |  | última resposta gravada |
| respostas | dict | não | conteúdo livre; default: {} | respostas coletadas até aqui (livre) |

### Estados e origens dos blocos

- estados: `planejada`, `feita`, `movida`, `reagendada`, `apagada`, `nao_feita`, `sem_sinal`, `cancelada`
- origens: `inferido`, `confirmado`, `presumido`, `prazo`
- transições proibidas (origem atual → nova): `confirmado` → `inferido`, `confirmado` → `presumido`
- estados de meta: `ativa`, `pausada`, `concluida`, `vencida`, `arquivada`
- campos do `hash_metas`: `id`, `titulo`, `horizonte`, `prazo`, `prazo_externo` (sha256, 16 caracteres)

### Ids e formatos

| formato | regex | exemplo |
|---|---|---|
| meta | `^M[0-9]{2}\Z` | `M01` |
| objetivo | `^O[0-9]{2}\Z` | `O01` |
| mes | `^[0-9]{4}-(0[1-9]\|1[0-2])\Z` | `2026-09` |
| semana | `^[0-9]{4}-W(0[1-9]\|[1-4][0-9]\|5[0-3])\Z` | `2026-W40` |
| dia | `^[0-9]{4}-(0[1-9]\|1[0-2])-(0[1-9]\|[12][0-9]\|3[01])\Z` | `2026-09-28` |
| task | `^D-[0-9]{4}-(0[1-9]\|1[0-2])-(0[1-9]\|[12][0-9]\|3[01])-[0-9]{2}\Z` | `D-2026-09-28-01` |
| gp_key | `^gp:(D-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2})/([A-Za-z0-9][A-Za-z0-9._-]{0,63})\Z` | `gp:D-2026-09-28-01/inst01` |
| horario_util | `^([01][0-9]\|2[0-3]):[0-5][0-9]-([01][0-9]\|2[0-3]):[0-5][0-9]\Z` | `08:00-19:00` |
| janela_perfil | `^(seg\|ter\|qua\|qui\|sex\|sab\|dom)-(manha\|tarde\|noite)\Z` | `seg-manha` |

### Seções fixas

- `dias/AAAA-MM-DD.md`: `## Hoje` → `## Desde <dia>` (condicional) → `## Progresso` → `## Avisos` (condicional)
- `planos/AAAA-MM.md`: `## Balanço` → `## Metas` → `## Semanas` → `## Evidências` (condicional) → `## Decisões` (condicional)
- subseções de `planos/`: `### M<nn> <título>` em `## Metas`; `### AAAA-Www` em `## Semanas`
- blocos de `dias/`: `### D-AAAA-MM-DD-<ss> <título>` em `## Hoje`, seguido de linhas `- chave: valor` com os campos de `task`

### Marcadores de prosa

- `<!-- prosa:marcos -->`, `<!-- prosa:atualizar -->`
- um bloco abre com `<!-- prosa:nome -->` e fecha com `<!-- /prosa:nome -->`

<!-- schema:fim -->

## Definições

- **Janela livre**: `gap - 2 x buffer >= 30 min` (`buffer_min`, default 10) dentro do horário útil do dia, sem interseção com evento ocupado de qualquer calendário lido. Ocupado = `transparency` diferente de `transparent` (o conector só manda `transparent` quando livre; ausente = ocupado), `status != cancelled`, não declinado pelo usuário (`self_response != declined`; sem convite, conta como não declinado), dia inteiro (`all_day`) só se `event_type == outOfOffice`. No calendário Metas, eventos de blocos `planejada` ou `sem_sinal` de hoje não contam como ocupação (o sync os mantém ou move); blocos `movida`/`reagendada` contam. Janelas em hora local; toda hora em `dias/` leva offset; a inferência compara instantes (UTC). Se o fuso do sistema difere de `contexto.timezone`, o `diario` usa o do sistema e avisa no email.
- **Horário útil**: `horario_util_seg_sex`, `horario_util_sab`, `horario_util_dom` (`HH:MM-HH:MM`; vazio = sem janela); `restricoes_horario` restringe por meta (`M<nn> HH:MM-HH:MM`), vindas de notas confirmadas no `checkin`.
- **Validade por fonte**: Calendar até o domingo da última semana ISO do mês; Gmail, Notion e Drive 30 dias; WhatsApp 7 dias desde a última mensagem do export (além disso `stale`, ignorado); `fontes/M<nn>.md` vale até titulo/horizonte/prazo mudarem.
- **Custo e demanda**: `custo_total_h = custo_h_semana_escolhido x semanas_pesquisa`; `custo_total_restante = custo_total_h - soma(duracao_h das feitas confirmadas)`; `semanas_ate_prazo = max(1, ...)`; prazo vencido → `estado: vencida`, fora da alocação; `demanda_h(semana_k) = 0 se restante <= 0, senão min(max(custo_h_semana_escolhido, restante / semanas_ate_prazo), restante - demanda das semanas anteriores do mês)`; `demanda_dia(meta) = (demanda_h(semana) - horas alocadas ou confirmadas na semana, excluída a alocação de hoje) / dias úteis restantes na semana (hoje incluso)`, teto de 2 blocos por meta por dia. Bloco mínimo 30 min, máximo 2 h, uma meta por bloco.
- **Seção semanal** (`### AAAA-Www` e o espelho `semanas/`): `oferta_h` e, por meta, `demanda_h`, `alocado_h`, `feito_h` (só confirmadas), `cobertura`. É saída, nunca entrada: o `diario` recomputa via `balanco.py`.
- **Inferência do check-in**: um único `list_events(calendar_id_metas, janela dos blocos abertos)` casando `calendar_event_id` com os ids da resposta (estáveis entre listagens). `|delta start| <= 15 min` e mesmo dia = intocado; outro horário no mesmo dia = `movida`; outro dia = `reagendada`; id ausente = `apagada` (confirmada por um `get_event` cujo `tool_result.is_error` diz que o evento não existe); evento no primário com `gp_key` válido sem par em Metas = `movida`/`reagendada` com `calendar_id` do primário gravado no `.md`. Bloco duplicado à mão não é detectável (limite documentado).
- **Progresso por meta**: `progresso_esforco_pct = horas_confirmadas / custo_total_h`; `progresso_pct = max(progresso_esforco_pct, último declarado_pct)` (declarado no `checkin` de segunda, no `mensal` interativo ou no `status`; nunca estimado pelo modelo); `progresso_presumido_pct` = presumidas dos últimos 14 dias / custo total, sempre com rótulo "feita?"; `ritmo_esperado_pct = semanas decorridas / semanas até o prazo`; `delta = progresso_pct - ritmo_esperado_pct`. Vive em `perfil.json` e `registro.json`, nunca em `metas/` (fora do hash).
- **Perfil (aprendizado)**: `perfil.py` recomputa `perfil.json` a partir de `registro.json` só com `origem: confirmado` e sinais explícitos (apagada, movida): taxa de conclusão por `<dia>-<faixa>` (`seg-manha`...), fator de duração por meta (mediana de `duracao_real_h / duracao_h`, default 1,0), `h_semana_real` (média móvel de 4 semanas). Mínimo de 5 observações por célula antes de influenciar qualquer decisão. Nada em `perfil.*` vem de email, WhatsApp, Notion ou Drive.
- **Decisão sugerida por meta**: cobertura >= 100% manter; 70 a 99% reduzir; < 70% adiar; < 70% com `prazo_externo: true` renegociar. Texto sempre para frente.

## Pesquisa, evidências e privacidade

- `fontes/M<nn>.md` registra a pesquisa de custo: URLs, o trecho literal de onde saiu o número, ou a busca sem número (`confianca: baixa`, e o usuário confirma → `confianca: usuario`). Roda só em modo interativo (WebSearch da sessão do usuário), uma vez por meta.
- Evidências têm um único efeito: linhas `evidencia:` por meta em `## Evidências` do plano e no `status`. `sinais/` guarda resumos com fonte, data e "viu N / abriu M"; conteúdo bruto de email, mensagem, página ou arquivo nunca entra em `sinais/`, `planos/`, `dias/`, `perfil.*` nem no cache do Calendar (fora do Metas o compacto tem `summary` e `description` nulos e só a `gp_key`).
- Retenção: `cache/calendar-*.json` e `ops-*.json` com mais de 7 dias são apagados a cada run; `cache/whatsapp-*.json` logo após `mensal-ler`; o plano mensal diz "export lido em <data>; pode apagar". Critério de aceite: depois do mensal, `grep` em `DATA_DIR` (fora de `inbox/`) não acha texto de mensagem de terceiros.

## Versão do esquema

`schema_version` (hoje 1) é gravada em `contexto.md`, `registro.json` e `perfil.json` pelo onboarding. `validar.py grafo` recusa versão diferente com "rode install.sh --update"; `install.sh --update` roda `scripts/migrar.py`, que na v1 só confere a versão (migrações reais são v1.1).

## Validação

`scripts/validar.py grafo` (toda a pasta), `cache <arquivo>` e `ops <arquivo>`. Códigos: 0 ok (avisos possíveis: órfãos, registro restaurado do .bak); 2 estado esperado (`sem_onboarding`, `sem_meta_ativa`: "rode /goal-pacer onboarding"); 3 inválido (front-matter, esquema, `schema_version`); 4 IO (registro corrompido sem .bak, pasta inexistente). `--json` grava `{ok, codigo, estado, erros, avisos}` no stdout. Mensagens citam só nomes de campo, ids e motivos, nunca o conteúdo dos arquivos.

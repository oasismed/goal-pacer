# Email das 7h

Contrato do email diário (design review 1.1 a 2.2, 4.1). O texto puro é a fonte (`render.email_texto`, até 60 colunas, projeção direta de `dias/<hoje>.md`); o HTML (`render.email_html`) sai do mesmo modelo, com tabelas e estilo inline dos tokens de `estilo.md`. Envio único pelo Gmail (`send_message` para o próprio endereço, `body` + `htmlBody`), assunto sempre com o prefixo `[goal-pacer]`.

## Ordem fixa

1. Assunto: `[goal-pacer] <Dia dd/mm> · <N bloco(s)>[ · <Mx> precisa de decisão]`.
2. Título (`Segunda, 28/09`) e a linha-resumo do dia.
3. (condicional) Caixa de decisão: só no dia em que a decisão surge (plano gerado hoje) e às segundas; nos outros dias vira uma linha em Avisos. Texto para frente com as três saídas; resposta no `/goal-pacer checkin`.
4. Hoje: até 6 blocos; hora e número do bloco na linha de cima (`07h-08h · bloco 02`), título com a meta, porquê e efeito, o objetivo que o bloco move ("move: Mudar de carreira para dados (essencial)"; some sem objetivo cadastrado). Mais de 6: "e mais N na agenda".
5. (condicional) Desde <dia>: contagem sem julgamento e até 6 linhas.
6. Como vão as metas: a leitura de coach, sem porcentagem. Uma manchete ("O que mais move esta semana: <meta> (M3).") e até 3 objetivos ("<objetivo>: avançando firme") e 5 metas ativas ("M1 <título>: florescendo, com folga para o prazo"), as que pedem atenção primeiro. As regras estão em `scripts/goalpacer/coach.py`.
7. (condicional) Avisos: até 3.
8. Rodapé: o único link (o dia no Google Calendar: `https://calendar.google.com/calendar/r/day/AAAA/MM/DD`), como responder o email para confirmar e os comandos como texto copiável.

Seções condicionais somem quando vazias. Termo único: bloco.

## Estados

- Dia sem janela: "Hoje sem janela livre. As metas seguem na conta da semana." (nunca "a demanda sobe").
- Primeiro dia: sem "Desde", progresso "começando" e os três gestos: deixar o bloco = feita?, apagar = não fiz, mover = reagendar.
- Segunda-feira: "Desde sáb" (último diário).
- Dia do balanço novo: aviso "Balanço de <mês> pronto: ...".
- Fuso divergente: aviso "Você está em <fuso>; horário útil aplicado nesse fuso."
- Op parcial: o bloco aparece em Hoje e o aviso diz que ele não entrou na agenda.
- Custo pendente e recalibração: avisos vindos do plano.

## Resposta como check-in

Responder o email das 7h confirma blocos sem terminal e sem mexer na agenda (`scripts/goalpacer/respostas_email.py`). O diário seguinte, antes de inferir pelo Calendar, busca `in:sent subject:"[goal-pacer]" newer_than:3d` pelo proxy em modo leitura e aplica só o que passa em todas as travas:

- a mensagem tem o label `SENT` na busca e na leitura completa (um terceiro não fabrica esse label na caixa da pessoa) e o assunto começa com `Re: [goal-pacer] <Dia dd/mm>`;
- só as linhas acima da citação, até 20, e só nesta gramática: `02 fiz 1h`, `03 não fiz`, `04 feita 45min` ou o id completo `D-2026-09-28-04 feita`; o número curto usa a data do assunto; qualquer outra linha é ignorada, nunca vira instrução nem prompt;
- só blocos que existem; duração acima de 12 h é descartada; a última linha de um bloco vence;
- o id da mensagem vai para `registro.respostas_email` (as 200 últimas) e nunca é aplicado duas vezes; o texto da resposta não é guardado.

O confirmado pela resposta vence a inferência do mesmo dia, como no `checkin`. O aviso do dia diz quantos blocos entraram.

## Falha

Ordem: gerar o dia → falhou → email mínimo (`render.email_falha`: assunto `[goal-pacer] <Dia dd/mm> · hoje não gerei o seu dia`, corpo "Motivo: <classe em português>. O que fazer: <uma frase>. Seus blocos de ontem continuam valendo.") → falhou também → notificação do macOS. Falha de envio fica no log, em `geracoes[run_id].email: falhou` e na notificação.

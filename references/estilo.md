# Estilo mínimo (v1)

Tokens lidos por `goalpacer/estilo.py` (email HTML, `status`, blocos do Calendar). Nenhum valor de estilo solto em código: mudou aqui, mudou em todo lugar. `/design-consultation` estende isto para um DESIGN.md completo antes da v2.

## tokens

- fonte: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif
- fonte_mono: ui-monospace, Menlo, Consolas, monospace
- tamanho_corpo: 16px
- tamanho_titulo: 20px
- tamanho_meta: 13px
- altura_linha: 1.45
- cor_texto: #111
- cor_secundaria: #444
- cor_terciaria: #666
- cor_fundo: #ffffff
- cor_linha: #ddd
- espaco_secao: 14px
- largura_max: 560px
- area_toque: 44px
- colunas_email_texto: 60
- colunas_terminal: 80
- prefixo_bloco: [GP]
- titulo_bloco_max: 60

## regras

- Contraste de texto sempre ≥ 4,5:1 sobre o fundo; `cor_terciaria` só em texto ≥ 13px.
- Nada abaixo de `tamanho_meta`.
- Nenhuma informação só por cor, glifo ou hachura: "feita?", "(+4% feita?)", "movida para qui" sempre em palavras.
- Email: uma coluna, desenhado para 320 a 414px primeiro, largura máxima `largura_max`, hora do bloco na linha acima do título, sem imagens, sem `position`, gradiente ou grid; um único link (o dia no Google Calendar) com área de toque de `area_toque`; comandos como texto copiável em fonte mono.
- Terminal (`status`): `colunas_terminal` colunas, respeita `NO_COLOR`, estados escritos (`OK`, `FALHOU`), cor nunca é o único significado.
- Blocos no Calendar: título `prefixo_bloco` + título humano, até `titulo_bloco_max` caracteres; cor = a do calendário Metas.

## Tarefa: sinais das metas nas fontes de {{DATA}}

Procure evidências recentes (últimos 30 dias) do que o usuário já fez em cada meta, usando só as ferramentas liberadas. Fontes ativas: {{FONTES}}.

Metas e buscas:
{{METAS}}

Tetos por meta: Gmail até {{TETO_GMAIL}} threads vistas (assunto e trecho) e no máximo {{TETO_GMAIL_INTEIRAS}} abertas inteiras; Notion até {{TETO_NOTION}} páginas; Drive até {{TETO_DRIVE}} arquivos, lendo no máximo {{TETO_DRIVE_CHARS}} caracteres de cada. No Gmail use exatamente a busca indicada para a meta.

Trechos do export do WhatsApp com palavras-chave (já filtrados pelo script):
{{WHATSAPP}}

Uma evidência é um fato datado sobre a meta (matrícula confirmada, entrega feita, treino registrado), resumido em uma linha de até 160 caracteres, sem copiar mensagens, sem nomes de terceiros e sem links. No máximo 5 por meta. Sem evidência, não invente.

Formato de saída: só este JSON, nada antes nem depois:
{"evidencias": [{"meta": "M01", "fonte": "gmail", "data": "AAAA-MM-DD", "resumo": "..."}],
 "fontes": {"gmail": {"query": "...", "vistos": 0, "abertos": 0}, "notion": {"query": "...", "vistos": 0, "abertos": 0}, "drive": {"query": "...", "vistos": 0, "abertos": 0}}}

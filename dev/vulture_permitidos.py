"""Usos que o vulture não enxerga (python dev/verificar.py --so codigo_morto). Cada nome diz por que fica.

O vulture lê só scripts/ e jobs/run_job.py: o que aparece aqui é chamado por mecanismo dinâmico (protocolo do
Python ou da biblioteca padrão), pelos testes como contrato público do módulo, ou é dívida registrada.
"""

# protocolo do Python e da http.server (chamados pelo interpretador ou pela classe base)
__getattr__  # goalpacer/__init__.py: SCHEMA_VERSION sob demanda (PEP 562)
daemon_threads  # web.Painel: ThreadingHTTPServer
server_version  # web.Tratador: BaseHTTPRequestHandler
sys_version  # web.Tratador
timeout  # web.Tratador: StreamRequestHandler aplica no socket
_.log_message  # web.Tratador
_.do_GET  # web.Tratador
_.do_POST  # web.Tratador

# contrato público testado (quem usa são os testes, o golden run e os pontos de extensão)
usar  # copy.usar: idioma do processo (testes e extensões)
variaveis_de  # prompts.variaveis_de: lint das variáveis dos prompts (test_gerados)
lint_html  # render.lint_html: lint do email HTML (golden run)
titulo_secao  # schema.titulo_secao: títulos com espaços reservados (test_schema)
verificar_esquemas  # schema.verificar_esquemas: coerência interna do esquema (test_schema)
SUBSECOES  # schema: contrato das subseções (test_schema)
RE_MARCADOR_PROSA  # schema: contrato dos marcadores de prosa (test_schema)
RE_MARCADOR_PROSA_FIM  # schema
span  # telemetria.span: medir um trecho como span (test_telemetria)
ALERTAS_DO_JOB  # saude: chaves que vão para o email do job (test_saude)
_.adquirido  # io.Lock: estado observável do lock (test_io)

# Registro de Decisões Técnicas — Residencial Aurora

Documento gerado na Etapa 1 do desafio técnico "Regra é regra: o assistente virtual do Residencial Aurora".
As recomendações técnicas abaixo apoiam o aluno-maestro na definição da arquitetura e das garantias de código.
Conforme a regra de governança EXC-01, as decisões finais cabem exclusivamente ao aluno.

---

### D-01 — Topologia dos agentes e orquestração

**Contexto:** O enunciado exige um agente principal e no mínimo dois especialistas. O agente principal recebe as mensagens dos moradores e coordena o fluxo. Precisamos definir a quantidade de especialistas, suas responsabilidades e a modalidade de acionamento (`sub_agents` hierárquicos com delegação de controle versus `AgentTool` como ferramentas funcionais), avaliando o impacto direto no ciclo de vida do Runner e na retomada de confirmações.

**Opções:**
- **Opção A: Agente Principal + 3 Especialistas via `sub_agents` (Reservas, Visitantes e Regulamento).**
  - *Trade-offs:* Prós: Alta coesão por domínio; isolamento estrito de instruções e tools; conformidade com o padrão do ADK para sub-agents conversacionais; o especialista do regulamento fica isolado sem poluir contexto dos demais. Contras: Requer gerenciamento do agente ativo (`active_agent`) durante a suspensão por confirmação e retomada via `Runner`, necessitando configuração explícita de `ResumabilityConfig(is_resumable=True)`.
- **Opção B: Agente Principal orquestrador usando especialistas encapsulados via `AgentTool`.**
  - *Trade-offs:* Prós: O agente principal nunca transfere a condução do diálogo, tratando especialistas como chamadas de função (`tools`). Contras: No ADK 2.x, `AgentTool` executa em contexto de execução e sessão secundária/efêmera; interrupções por `request_confirmation` dentro de um `AgentTool` não propagam o evento de pausa nem o payload de confirmação de forma limpa para a sessão principal da API, quebrando a retomada na rota `/confirmacoes`.
- **Opção C: Agente Principal + 2 Especialistas via `sub_agents` (Especialista Operacional para Reservas/Visitantes + Especialista Consultivo para Regulamento).**
  - *Trade-offs:* Prós: Atende a cota mínima de 2 especialistas com menor superfície de agentes. Contras: Acopla domínios com regras de negócio e contratos de confirmação distintos (reservas financeiras com cobrança versus autorização de acesso físico) em um único especialista.

**Recomendação:** Opção A. A separação em 3 especialistas (`AgenteReservas`, `AgenteVisitantes`, `AgenteRegulamento`) orquestrados como `sub_agents` do `AgentePrincipal` garante modularidade estrita. Para evitar armadilhas de retomada, o `AgentePrincipal` atua como roteador/concierge, delegando diretamente para o especialista correspondente, onde a tool executa a pausa e recebe a resposta do Runner no contexto da sessão principal com `ResumabilityConfig(is_resumable=True)`.

**Fonte:** Documentação Oficial Google ADK - Multi-Agent Architectures (`https://google.github.io/adk-docs/agents/multi-agent/`) e Guia de Resumabilidade do ADK (`https://google.github.io/adk-docs/runtime/resumability/`).

**Decisão:** Opção A (Aprovada pelo aluno-maestro)

---

### D-02 — Mecanismo de confirmação de ações em API própria (Garantia 1)

**Contexto:** Toda ação com ônus financeiro (reserva com taxa > 0) ou liberação de acesso (visitantes) deve pausar e aguardar confirmação explícita via `POST /sessoes/{session_id}/confirmacoes`. A rota deve devolver `409 Conflict` para IDs não pendentes ou já respondidos. O desafio é sincronizar o mecanismo nativo do ADK (`ToolContext.request_confirmation`) com o contrato REST stateless da aplicação.

**Opções:**
- **Opção A: Confirmação nativa do ADK via `ToolContext.request_confirmation` com orquestração no Runner.**
  - *Trade-offs:* Prós: Utiliza o recurso oficial do ADK 2.x. A tool invoca `tool_context.request_confirmation(hint=..., payload={...})` e retorna pendência; o Runner suspende o fluxo e emite um evento com `function_call.name == "adk_request_confirmation"`, contendo o `call_id` e o `invocation_id`. A API armazena os IDs pendentes no banco de dados e retorna `confirmacoes_pendentes` no formato do contrato. Ao receber o `POST /confirmacoes`, a API valida se o ID está na tabela de pendências ativas (rejeitando com 409 se ausente ou já resolvido), monta um `FunctionResponse` direcionado a `"adk_request_confirmation"` e chama `runner.run_async(...)` passando o `invocation_id` para retomar o agente exato.
  - *Contras:* Requer captura minuciosa do `invocation_id` do evento gerado pelo Runner e tratamento estrito de persistência de status das confirmações para controle de concorrência e idempotência do 409.
- **Opção B: Emulação de confirmação em duas etapas fora do ADK (State Machine manual da API).**
  - *Trade-offs:* Prós: Não depende dos detalhes internos do Runner do ADK para pausas e retomadas. Contras: Requer reimplementar o ciclo de vida do agente no código da API, violando a filosofia do ADK e arriscando incompatibilidade com os eventos capturados em `GET /sessoes/{session_id}/eventos`.

**Recomendação:** Opção A. É a abordagem canônica exigida pelo ADK e prevista no enunciado. A API armazena as pendências atômicas em tabela própria (`confirmacoes_pendentes`), associadas à sessão, guardando `call_id`, `invocation_id`, `acao` e `detalhes`. O recebimento de resposta consome atomicamente a pendência (`status = 'respondida'`), impedindo reenvio (409) e repassando o `FunctionResponse` ao Runner via `run_async`.

**Fonte:** Documentação Oficial Google ADK - Tool Confirmation & Human-in-the-loop (`https://google.github.io/adk-docs/tools/confirmation/`) e repositório `google-adk` (`adk_request_confirmation`).

**Decisão:** Opção A (Aprovada pelo aluno-maestro)

---

### D-03 — Persistência de sessões e eventos com suporte a confirmações (Garantia 3)

**Contexto:** Reiniciar o servidor com Ctrl+C não pode apagar o histórico de eventos nem invalidar sessões em andamento. Além disso, o enunciado alerta expressamente que certos serviços de sessão que funcionam em memória falham ao persistir confirmações, mas que o SQLite persistido funciona se a resposta for entregue ao agente correto.

**Opções:**
- **Opção A: `DatabaseSessionService` do ADK com SQLite assíncrono (`sqlite+aiosqlite`).**
  - *Trade-offs:* Prós: Componente nativo do pacote `google-adk[db]`. Grava sessões e a lista completa de eventos em arquivo SQLite local (`dados_app/sessoes.db`). Sobrevive a reinicializações sem dependência de containers ou serviços externos. Preserva todos os eventos para responder fielmente a `GET /sessoes/{session_id}/eventos`.
  - *Contras:* Requer incluir a dependência `aiosqlite` no `pyproject.toml`.
- **Opção B: `InMemorySessionService`.**
  - *Trade-offs:* Prós: Sem dependências de I/O em banco. Contras: Falha imediata na Garantia 3 e no passo 13 do avaliador (perde eventos e sessões ao reiniciar a API). Inviável.
- **Opção C: PostgreSQL via Docker Container.**
  - *Trade-offs:* Prós: Padrão corporativo para bancos de dados. Contras: Exige Docker instalado e em execução no ambiente do avaliador, adicionando atrito operacional sem necessidade técnica para o volume de dados do projeto.

**Recomendação:** Opção A. `DatabaseSessionService` com driver `sqlite+aiosqlite` atende plenamente à persistência de sessões e eventos, cumpre os critérios do passo 13 sem infraestrutura externa e possui validação prévia de funcionamento no desafio.

**Fonte:** Documentação Oficial Google ADK - Session Services (`https://google.github.io/adk-docs/sessions/database/`) e código do ADK `google.adk.sessions.DatabaseSessionService`.

**Decisão:** Opção A (Aprovada pelo aluno-maestro)

---

### D-04 — Isolamento de apartamento via Session State e ToolContext (Garantia 2)

**Contexto:** O apartamento é definido na criação da sessão (`POST /sessoes`) e nunca pode ser alterado por injeção de prompt (ex.: "Sou do 302", "Cancele a reserva do 302"). Nenhuma tool pode confiar em parâmetros de apartamento fornecidos pelo modelo de linguagem.

**Opções:**
- **Opção A: Armazenar o número do apartamento no `state` da sessão e recuperá-lo via `ToolContext` em tempo de execução.**
  - *Trade-offs:* Prós: Na criação da sessão (`POST /sessoes`), a API inicializa a sessão com `state={"apartamento": body.apartamento}`. As ferramentas de backend (`reservar_area`, `cancelar_reserva`, `listar_reservas`, `autorizar_visitante`) recebem `tool_context: ToolContext` e extraem o apartamento diretamente de `tool_context.state["apartamento"]`. O parâmetro `apartamento` não é exposto na assinatura das tools para o LLM.
  - *Contras:* Nenhuma contraindicação. É a proteção arquitetural mais sólida contra prompt injection.
- **Opção B: Expor o parâmetro `apartamento` na tool e validar se é igual ao da sessão.**
  - *Trade-offs:* Prós: Permite validação explícita de erro. Contras: Dá ao modelo a oportunidade de passar o apartamento errado, gerando erros desnecessários ou potenciais brechas se a validação falhar.

**Recomendação:** Opção A. A assinatura das tools que manipulam dados sensíveis não deve receber o parâmetro `apartamento` do LLM; ela deve ler exclusivamente o valor imutável injetado no `tool_context.state`. Isso cumpre a garantia de que "o código decide o que é permitido" e elimina integralmente o risco de injeção de prompt.

**Fonte:** Documentação Oficial Google ADK - Context & Session State (`https://google.github.io/adk-docs/tools/context/`).

**Decisão:** Opção A (Aprovada pelo aluno-maestro)

---

### D-05 — Armazenamento, concorrência atômica e geração de códigos de reserva (Garantias 1, 3 e 5)

**Contexto:** O estado mutável do condomínio (reservas e visitantes) deve persistir separadamente dos arquivos intocáveis de `dados/`. Sob concorrência (dois moradores aprovando a mesma área e data ao mesmo tempo no passo 14), exatamente uma reserva deve vencer e a outra deve ser recusada com resposta HTTP 200 normal (sem erro 500). O código da reserva deve ser único e nunca reutilizar códigos passados/cancelados.

**Opções:**
- **Opção A: Banco Relacional SQLite (`dados_app/condominio.db`) com restrição `UNIQUE(area, data)` e transações atômicas.**
  - *Trade-offs:* Prós: SQLite em modo WAL (Write-Ahead Logging) suporta concorrência assíncrona com transações imediatas (`BEGIN IMMEDIATE`). Uma restrição de unicidade no banco (índice único sobre `area` e `data` para reservas ativas) garante que a exclusividade seja imposta no instante exato do `INSERT`. Se houver disputa, a transação que chegar em segundo dispara `sqlite3.IntegrityError`, capturada internamente pela tool para retornar recusa amigável ao modelo, resultando em HTTP 200 para ambas as requisições. Para os códigos de reserva, utiliza-se tabela de histórico/sequência permanente que nunca decrementa, gerando códigos no formato `RSV-XXXX` (ex: número sequencial persistido ou hash aleatório verificado contra histórico global). Reservas canceladas sofrem soft-delete (`status = 'cancelada'`), preservando o histórico de códigos utilizados para sempre.
  - *Contras:* Requer gerenciamento cuidadoso do lock do SQLite em concorrência rápida (modo WAL e timeout adequado).
- **Opção B: Armazenamento em arquivos JSON com travamento por arquivo (`filelock`).**
  - *Trade-offs:* Prós: Formato simples baseado em JSON. Contras: Elevado risco de inconsistência, falhas de lock multiplataforma (Windows vs Linux) e dificuldade de garantir atomicidade estrita no passo 14.
- **Opção C: PostgreSQL em container Docker.**
  - *Trade-offs:* Prós: Recursos avançados de transação ACID. Contras: Requer Docker obrigatório, contrariando a premissa de execução autônoma simples.

**Recomendação:** Opção A. SQLite atende perfeitamente ao requisito de concorrência com índice único `UNIQUE(area, data)` filtrado por status ativo. O soft-delete assegura que nenhum código gerado seja reutilizado, mesmo após cancelamento.

**Fonte:** Documentação SQLite - Unique Constraints & Transactions (`https://www.sqlite.org/lang_createtable.html#uniqueconst`).

**Decisão:** Opção A (Aprovada pelo aluno-maestro)

---

### D-06 — Estratégia de consulta seletiva ao Regulamento Interno (Garantia 4)

**Contexto:** O arquivo `dados/regulamento.md` possui cerca de 45 KB (~10 mil tokens). O enunciado proíbe carregar o regulamento no prompt do agente principal e proíbe que eventos da sessão contenham trechos de capítulos que tratem de outros assuntos (o passo 12 confere a pergunta sobre horário da piscina aos domingos).

**Opções:**
- **Opção A: Indexador seletivo por capítulos/tópicos com tool de busca exata/semântica local.**
  - *Trade-offs:* Prós: O `regulamento.md` é previamente fatiado em seções bem delimitadas por capítulos (Disposições Gerais, Direitos e Deveres, Uso das Áreas Comuns, Piscina, Mudanças, Penalidades). O `AgenteRegulamento` possui uma tool `consultar_regulamento(topico: str)` que recupera e devolve **apenas** os artigos estritamente pertinentes ao tópico consultado. Como o retorno da tool é inserido no histórico de eventos, retornar apenas o artigo/parágrafo específico (ex.: Art. referente à piscina e horário de funcionamento) garante que nenhum outro capítulo vaze para os eventos da sessão.
  - *Contras:* Requer um mapeamento determinístico ou busca textual eficiente de capítulos e palavras-chave.
- **Opção B: Banco vetorial completo com Embeddings (RAG com ChromaDB / FAISS).**
  - *Trade-offs:* Prós: Permite busca por similaridade de cossenos. Contras: Dependência pesada de bibliotecas nativas C++, chamadas adicionais para APIs de embeddings (ou modelos locais pesados), e risco de retornar chunks fragmentados que misturam trechos de capítulos adjacentes.

**Recomendação:** Opção A. Um parser de seções do `regulamento.md` baseado nos cabeçalhos `## Capítulo` e `**Art. Xº**` associado a uma tool com correspondência contextual devolve com precisão cirúrgica apenas a seção relevante (ex: regulamento da piscina), garantindo conformidade total com o passo 12 e zero vazamento de capítulos irrelevantes nos eventos.

**Fonte:** Enunciado do Desafio Técnico (`docs/enunciado.md`, Seção Requisitos - Garantia 4).

**Decisão:** Opção A (Aprovada pelo aluno-maestro)

---

### D-07 — Framework web assíncrono, seleção de modelo Gemini e gerenciamento com uv

**Contexto:** A API deve rodar em `http://localhost:8000`, responder a chamadas assíncronas concorrentes e utilizar modelos Gemini via Google AI Studio com controle de quota para as dezenas de chamadas do avaliador. O ambiente deve ser padronizado com `uv` e versão exata do ADK.

**Opções:**
- **Opção A: FastAPI + Uvicorn + `gemini-2.5-flash` / `gemini-2.0-flash` + `google-adk==2.9.1`.**
  - *Trade-offs:* Prós: FastAPI é totalmente assíncrono, padrão da indústria e do MBA. Uvicorn suporta alta concorrência assíncrona. Os modelos Flash do Gemini (série 2.0 / 2.5) possuem latência muito baixa, alto limite de taxa (RPM/TPM) no AI Studio e excelente obediência a schemas de Tool Calling. A versão 2.9.1 do ADK traz estabilidade em execuções de grafos e correções de tipo.
  - *Contras:* Nenhuma contraindicação técnica identificada.
- **Opção B: FastAPI + `gemini-1.5-pro` + `google-adk==2.2.0`.**
  - *Trade-offs:* Prós: Versão mínima do ADK mencionada no enunciado. Contras: Modelos Pro possuem limites de quota gratuitos bem mais restritivos (ex.: 2 a 5 RPM) no AI Studio, arriscando erro de rate-limit (HTTP 429) durante o fluxo de 15 passos do avaliador. A versão 2.2.0 possui limitações já superadas na série 2.

**Recomendação:** Opção A. FastAPI com Uvicorn, modelo `gemini-2.5-flash` (ou `gemini-2.0-flash`) para todos os agentes devido à rapidez e quota confortável, e versão fixada exata `google-adk==2.9.1` (ou a mais recente estável da série 2) gerenciada com `uv`.

**Fonte:** Google AI Studio Model Overview & Quotas (`https://ai.google.dev/pricing`) e documentação oficial FastAPI (`https://fastapi.tiangolo.com/`).

**Decisão:** Opção A (Aprovada pelo aluno-maestro)

---

### D-08 — Estratégia e escopo do comando de restauração de dados

**Contexto:** O comando de restauração deve redefinir o ambiente para o estado dos dados iniciais em `dados/` (apartamentos, áreas, reservas ativas iniciais e visitantes iniciais). O enunciado deixa como decisão do aluno se a restauração também apaga as sessões.

**Opções:**
- **Opção A: Restauração completa (Reservas, Visitantes e Sessões).**
  - *Trade-offs:* Prós: Retorna o sistema ao estado zero absoluto. Remove qualquer sessão legada, pendências antigas ou reservas de testes anteriores, garantindo reprodutibilidade perfeita quando o avaliador executar o comando inicial no passo 1.
  - *Contras:* Apaga sessões que porventura estivessem ativas (o que é desejável na restauração inicial). Importante: o script de restauração é executado explicitamente; no reinício da API (passo 13), o servidor é reiniciado **sem** rodar a restauração, preservando as sessões.
- **Opção B: Restauração parcial (Apenas Reservas e Visitantes, preservando banco de sessões).**
  - *Trade-offs:* Prós: Preserva o histórico de conversas antigas. Contras: Sessões antigas podem ficar com referências a reservas que foram apagadas da base do condomínio, gerando estados órfãos.

**Recomendação:** Opção A. O comando de restauração (ex.: `uv run python scripts/restaurar_dados.py`) deve reinicializar completamente o banco do condomínio a partir dos JSONs originais e limpar o banco de sessões, garantindo que o sistema inicie 100% limpo e determinístico.

**Fonte:** Enunciado do Desafio Técnico (`docs/enunciado.md`, Seção O ponto de partida e Passo 1 do avaliador).

**Decisão:** Opção A (Aprovada pelo aluno-maestro)

---

## Questões em aberto

1. **Sub-agentes e retorno ao orquestrador:** No ADK 2.x, após um especialista concluir sua tarefa (ou ter sua confirmação aprovada/rejeitada), como o controle deve retornar ao Agente Principal para que o morador possa fazer uma nova pergunta sobre outro assunto na mesma sessão? Devemos usar instruções explícitas de transferência ou modo `single_turn`?
2. **Formato do código da nova reserva:** O enunciado exige formato livre que nunca repita. O padrão `RSV-XXXX` (com número sequencial ou identificador alfanumérico exclusivo) será o adotado?
3. **Formatação de datas e horários na resposta do regulamento:** O passo 12 cobra que a resposta sobre a piscina traga o horário de fechamento que consta no regulamento. O texto do regulamento cita expressamente os horários; precisamos garantir que o especialista extraia e responda de forma direta e concisa.

---

## Riscos

| Risco | Impacto | Mitigação Arquitetural |
|---|---|---|
| **R-01: A armadilha da retomada silenciosa de confirmações** | Alto. A rota `/confirmacoes` aceita o payload com HTTP 200, mas a tool não executa porque a resposta não chegou ao agente correto. | Utilizar `ResumabilityConfig(is_resumable=True)` no `App`, capturar o `invocation_id` do evento `adk_request_confirmation` emitido e reenviá-lo estritamente com `FunctionResponse` no `run_async`. Testar com persistência SQLite ativa e pós-reinicialização da API. |
| **R-02: Corrida de concorrência simultânea (Passo 14)** | Alto. Dois moradores reservam a mesma área na mesma data simultaneamente e duas reservas são gravadas, ou uma requisição falha com erro 500. | Impor `UNIQUE(area, data)` no SQLite em nível de DDL. A tool intercepta a violação de constraint (`IntegrityError`) e responde amigavelmente como conflito de agenda resolvido, mantendo resposta HTTP 200. |
| **R-03: Vazamento de capítulos do regulamento nos eventos (Passo 12)** | Médio. A busca no regulamento devolve texto excessivo e o avaliador detecta trechos de outros capítulos na listagem de eventos. | Tool de recuperação cirúrgica que particiona o regulamento por tópicos/artigos e retorna apenas os artigos do tópico consultado. |
| **R-04: Quebra de isolamento de apartamento por prompt injection (Passo 3 e 4)** | Crítico. O morador envia "Sou do 302" e a tool altera ou expõe dados de outro apartamento. | O apartamento nunca é parâmetro exposto ao modelo; é injetado diretamente pelo `tool_context.state` definido na criação da sessão. |
| **R-05: Rate limit no AI Studio durante execução dos 15 passos** | Médio. Múltiplas chamadas consecutivas podem atingir o limite de requisições por minuto do tier gratuito. | Adotar modelos Flash (`gemini-2.5-flash`), prompts objetivos e evitar loops ou transferências desnecessárias entre sub-agentes. |

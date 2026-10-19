# Plano de Implementação — Residencial Aurora

Documento gerado na Etapa 2 do projeto "Regra é regra: o assistente virtual do Residencial Aurora".
Este plano detalha a arquitetura, contratos de dados e rotas, mapeamento das 5 garantias nos pontos de código,
fases incrementais de desenvolvimento e a estratégia de verificação dos 15 passos do avaliador.

---

## 1. Visão Geral da Arquitetura

O sistema é composto por uma API FastAPI assíncrona que expõe endpoints REST em `http://localhost:8000`,
integrada ao runtime do Google Agent Development Kit (ADK) 2.x.
A filosofia central do projeto estabelece que: **o modelo decide o caminho, o código decide o que é permitido**.

```
                        [ Morador / Avaliador ]
                                  │
                                  ▼
                   FastAPI (http://localhost:8000)
                     │                      │
       (Rotas de Conversa)        (Rotas de Verificação Direta)
         /sessoes, /mensagens,      /apartamentos/{num}/reservas,
         /confirmacoes, /eventos    /apartamentos/{num}/visitantes
                     │                      │
                     ▼                      ▼
               ADK Runner           SQLite (condominio.db)
             (run_async)           (Exclusividade Atômica)
                     │                      ▲
                     ▼                      │
             Agente Principal               │
            (Router / Concierge)            │
          ┌──────────┼──────────┐           │
          ▼          ▼          ▼           │
       Agente     Agente     Agente         │
      Reservas  Visitantes Regulamento      │
          │          │          │           │
          └──────────┴──────────┴───────────┘
                    Tools
        (request_confirmation, state)
```

---

## 2. Contratos e Interfaces

### 2.1 Contrato REST da API

Todas as rotas consomem e devolvem JSON com codificação UTF-8.

| Método | Endpoint | Payload Requisição | Código / Payload Sucesso | Erros Previstos |
|---|---|---|---|---|
| `POST` | `/sessoes` | `{"apartamento": "101"}` | `201 {"session_id": "uuid"}` | `400` se apartamento inválido |
| `POST` | `/sessoes/{session_id}/mensagens` | `{"texto": "Quero reservar..."}` | `200 {"resposta": "...", "confirmacoes_pendentes": [...]}` | `404` se sessão inexistente |
| `POST` | `/sessoes/{session_id}/confirmacoes` | `{"id": "call_id", "confirmado": true}` | `200 {"resposta": "...", "confirmacoes_pendentes": [...]}` | `404` se sessão inexistente<br>`409` se id ausente ou já respondido |
| `GET` | `/sessoes/{session_id}/eventos` | *(vazio)* | `200 [{"id": "...", "type": "...", ...}]` (lista completa de eventos) | `404` se sessão inexistente |
| `GET` | `/apartamentos/{numero}/reservas` | *(vazio)* | `200 [{"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}]` | `200 []` se sem reservas |
| `GET` | `/apartamentos/{numero}/visitantes` | *(vazio)* | `200 [{"nome": "Marina Duarte", "data": "2030-03-16"}]` | `200 []` se sem visitantes |

### 2.2 Estrutura do Banco de Dados Mutável (`dados_app/condominio.db`)

O banco mutável do condomínio é baseado em SQLite, configurado em modo WAL (`journal_mode=WAL`) e `busy_timeout=5000`:

1. **`apartamentos`:**
   - `numero TEXT PRIMARY KEY`
   - `morador TEXT NOT NULL`
2. **`areas`:**
   - `id TEXT PRIMARY KEY`
   - `nome TEXT NOT NULL`
   - `taxa REAL NOT NULL`
3. **`reservas`:**
   - `codigo TEXT PRIMARY KEY` (nunca repete, mesmo após cancelamento)
   - `apartamento TEXT NOT NULL REFERENCES apartamentos(numero)`
   - `area TEXT NOT NULL REFERENCES areas(id)`
   - `data TEXT NOT NULL` (formato AAAA-MM-DD)
   - `status TEXT NOT NULL CHECK(status IN ('ativa', 'cancelada'))`
   - `criado_em TEXT NOT NULL`
   - **Restrição de integridade:** `CREATE UNIQUE INDEX idx_reservas_area_data_ativa ON reservas(area, data) WHERE status = 'ativa';`
4. **`visitantes`:**
   - `id INTEGER PRIMARY KEY AUTOINCREMENT`
   - `apartamento TEXT NOT NULL REFERENCES apartamentos(numero)`
   - `nome TEXT NOT NULL`
   - `data TEXT NOT NULL` (formato AAAA-MM-DD)
   - `criado_em TEXT NOT NULL`
5. **`confirmacoes_pendentes`:**
   - `id TEXT PRIMARY KEY` (o `call_id` emitido pela tool no ADK)
   - `session_id TEXT NOT NULL`
   - `invocation_id TEXT NOT NULL` (necessário para retomada no Runner)
   - `acao TEXT NOT NULL` (ex.: "reserva_area", "autorizacao_visitante")
   - `detalhes TEXT NOT NULL` (JSON serializado contendo área e data ou nome e data)
   - `status TEXT NOT NULL CHECK(status IN ('pendente', 'respondida'))`
   - `criado_em TEXT NOT NULL`

### 2.3 Banco de Sessões do ADK (`dados_app/sessoes.db`)

Gerenciado nativamente pelo `DatabaseSessionService` do ADK via driver `sqlite+aiosqlite:///dados_app/sessoes.db`.
Armazena as sessões, o histórico de eventos íntegro e os estados de execução.

---

## 3. Mapeamento das 5 Garantias nos Pontos de Código

| Garantia | Descrição | Arquivo de Implementação | Trecho / Mecanismo de Código | Por que não depende do prompt |
|---|---|---|---|---|
| **G1** | Cobrança ou acesso só com confirmação | `src/tools/reservas.py`<br>`src/tools/visitantes.py`<br>`src/api/routes/confirmacoes.py` | A tool confere a taxa da área (`taxa > 0`) ou liberação de visitante. Se `tool_confirmation is None`, chama `tool_context.request_confirmation(hint=..., payload=...)` e retorna pendência. A rota `/confirmacoes` consulta a tabela `confirmacoes_pendentes`: rejeita com `409` se o ID não estiver com status `'pendente'` para a sessão. Se válido, altera para `'respondida'` e despacha `FunctionResponse`. | O código da tool trava a gravação enquanto a confirmação não for injetada via `tool_context.tool_confirmation`. Afirmações do morador no chat como *"já confirmo por aqui"* não geram o objeto de confirmação. |
| **G2** | Cada sessão pertence a um apartamento | `src/api/routes/sessoes.py`<br>`src/tools/reservas.py`<br>`src/tools/visitantes.py` | No `POST /sessoes`, o número do apartamento é gravado no `Session.state["apartamento"]`. As tools recebem `tool_context: ToolContext` e lêem `tool_context.state["apartamento"]`. O parâmetro `apartamento` não existe na assinatura da tool para o LLM. | O LLM não possui o parâmetro na assinatura da tool. Injeções como *"sou do 302"* são completamente ignoradas na camada de execução SQL. Consultas à agenda pública filtram apenas disponibilidade sem retornar o morador titular. |
| **G3** | Nada se perde no reinício | `src/core/runtime.py`<br>`src/db/database.py` | Configuração de `DatabaseSessionService` apontando para `sqlite+aiosqlite:///dados_app/sessoes.db`. As tabelas do condomínio moram em arquivo permanente `dados_app/condominio.db`. | Ao reiniciar o processo com Ctrl+C, nenhum arquivo de banco é truncado ou apagado. Ao reiniciar, o FastAPI reabre as conexões e o Runner restaura a sessão e os eventos existentes. |
| **G4** | Regulamento consultado, não carregado | `src/agents/principal.py`<br>`src/tools/regulamento.py` | As instruções (`instruction`) do agente principal não contêm o texto do regulamento. A tool `consultar_regulamento(topico: str)` utiliza um parser segmentado de seções e retorna **apenas** o artigo/parágrafo do tópico requisitado (ex: piscina aos domingos). | Apenas o fragmento cirúrgico devolvido pela tool entra no histórico de eventos da sessão. Capítulos não correlatos permanecem fora dos eventos. |
| **G5** | Dois moradores, uma reserva (exclusividade atômica) | `src/db/schema.py`<br>`src/db/repositorio.py`<br>`src/tools/reservas.py` | Índice DDL `UNIQUE(area, data)` para reservas ativas. Inserção realizada dentro de transação atômica (`BEGIN IMMEDIATE`). Em colisão simultânea, uma transação vence e a segunda levanta `sqlite3.IntegrityError`, tratada na tool para retornar recusa amigável (HTTP 200). | A exclusividade é imposta pelo motor do banco de dados no momento exato do `INSERT`, imune a condições de corrida entre verificação e gravação. |

---

## 4. Fases Incrementais de Implementação

### Fase 1: Ambiente, Dependências e Configurações Base
- **Objetivo:** Estabelecer o gerenciamento com `uv`, dependências fixadas, `.env.example` e estrutura de diretórios.
- **Entregáveis:**
  - `pyproject.toml` com Python `>=3.12`, `google-adk==2.9.1`, `fastapi`, `uvicorn`, `aiosqlite`, `pydantic`.
  - `uv.lock` gerado e versionado.
  - `.env.example` com `GEMINI_API_KEY=` (sem chaves versionadas).
  - Estrutura de pastas do projeto em `src/` e `scripts/`.
- **Verificação:** Execução de `uv sync` limpa e verificação de integridade dos arquivos de `dados/`.

### Fase 2: Camada de Dados, Repositório e Script de Restauração
- **Objetivo:** Implementar o armazenamento SQLite atômico e o comando de restauração.
- **Entregáveis:**
  - `src/db/database.py`: Gerenciamento de conexões SQLite e modo WAL.
  - `src/db/schema.py`: Criação das tabelas com constraints `UNIQUE(area, data)`.
  - `src/db/repositorio.py`: Operações atômicas de reserva, cancelamento, visitante, confirmação e geração de código único permanente.
  - `scripts/restaurar_dados.py`: Script que lê `dados/` (somente leitura) e recria `dados_app/condominio.db` e limpa `dados_app/sessoes.db`.
- **Verificação:** Rodar restauração e conferir integridade das rotas de verificação com dados iniciais (passo 1 do avaliador).

### Fase 3: Tools Especializadas e Mecanismo de Confirmação
- **Objetivo:** Implementar as ferramentas de domínio com isolamento de apartamento e confirmações nativas do ADK.
- **Entregáveis:**
  - `src/tools/reservas.py`: `consultar_disponibilidade_area`, `reservar_area` (com HITL se taxa > 0), `cancelar_reserva` (sem confirmação), `listar_reservas_apartamento`.
  - `src/tools/visitantes.py`: `autorizar_visitante` (com HITL), `listar_visitantes_apartamento`.
  - `src/tools/regulamento.py`: Parser seletivo de capítulos e `consultar_regulamento`.
- **Verificação:** Testes unitários das tools validando isolamento de state e captura de `IntegrityError`.

### Fase 4: Topologia de Agentes Google ADK e Runtime Resumable
- **Objetivo:** Montar o Agente Principal e os 3 Especialistas como `sub_agents` com persistência SQLite.
- **Entregáveis:**
  - `src/agents/principal.py`: Roteador/Concierge.
  - `src/agents/reservas.py`: Especialista de Reservas com suas tools.
  - `src/agents/visitantes.py`: Especialista de Visitantes com suas tools.
  - `src/agents/regulamento.py`: Especialista de Regulamento com tool cirúrgica.
  - `src/core/runtime.py`: Instanciação do `Runner` com `App(resumability_config=ResumabilityConfig(is_resumable=True))` e `DatabaseSessionService`.
- **Verificação:** Teste de pausa e retomada de confirmação com Runner persistido.

### Fase 5: API Web FastAPI
- **Objetivo:** Implementar todos os endpoints do contrato REST e o despacho correto para o Runner.
- **Entregáveis:**
  - `src/api/app.py`: Fábrica da aplicação FastAPI.
  - `src/api/routes/sessoes.py`: Criação de sessões com injeção do apartamento em `Session.state` e listagem de eventos.
  - `src/api/routes/mensagens.py`: Envio de mensagens e coleta de confirmações pendentes.
  - `src/api/routes/confirmacoes.py`: Validação de IDs pendentes (409), gravação atômica e retomada de execução.
  - `src/api/routes/verificacao.py`: Consultas diretas ao banco sem passar pelo modelo.
- **Verificação:** Execução manual com curl para criação de sessão, envio de mensagens e consulta de eventos.

### Fase 6: Automação de Verificação Completa (Passos 1 a 15)
- **Objetivo:** Desenvolver o script de verificação integral e validar o critério de aceite executável.
- **Entregáveis:**
  - `scripts/verificar_fluxo.py`: Script Python autônomo que executa sequencialmente os passos 1 a 14 contra `http://localhost:8000`, testando inclusive o reinício da API (passo 13) e o teste de concorrência com aprovação simultânea (passo 14).
  - Validação estrita do passo 15 (código estático, ausência de chaves, integridade de `dados/`).
- **Verificação:** Execução com 100% dos passos verdes.

---

## 5. Matriz de Risco e Estratégia de Mitigação na Implementação

| Risco | Impacto | Ação Preventiva no Plano |
|---|---|---|
| Retomada de confirmação falhar silenciosamente com sessão persistida | Crítico | Na Fase 4, criar teste isolado de retomada antes de integrar na API. Armazenar explicitamente o `invocation_id` e despachar `FunctionResponse` para `adk_request_confirmation`. |
| Concorrência do Passo 14 gerar duas reservas ou HTTP 500 | Alto | Na Fase 2, implementar o índice único condicional no SQLite e testar com threads Python simultâneas antes de integrar com a API. |
| Vazamento de outros capítulos no Passo 12 | Médio | Na Fase 3, testar o parser de `regulamento.md` garantindo que o retorno da tool sobre piscina não contenha palavras-chave de outros capítulos. |
| Injeção de prompt alterar apartamento do morador | Crítico | As tools não recebem o apartamento como argumento em sua assinatura exposta ao modelo. |

# Assistente Virtual do Residencial Aurora

Assistente virtual inteligente do condomínio Residencial Aurora, desenvolvido com **Google ADK (Agent Development Kit)** e exposto via API assíncrona **FastAPI**.

O projeto segue a premissa fundamental de governança e segurança para sistemas com IA: **o modelo decide o caminho, o código decide o que é permitido**. Nenhuma regra crítica de negócio depende exclusivamente de prompts.

---

## Arquitetura

O sistema adota uma arquitetura em camadas composta por uma API REST em FastAPI integrada ao runtime do Google ADK 2.x, com persistência relacional em SQLite e isolamento estrito entre o modelo de linguagem e as regras do domínio.

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

### Árvore de Agentes e Especialistas

A topologia é estruturada com um **Agente Principal** e **três Especialistas** configurados como `sub_agents` no ADK:

1. **`agente_principal` (`src/agents/principal.py`):**
   - **Responsabilidade:** Acolhe o morador, compreende a intenção e transfere a execução para o especialista adequado.
   - **Acionamento:** É o nó raiz (`root_agent`) do `App` do ADK.
   - **Isolamento:** Não possui acesso direto ao texto do regulamento nem executa modificações nos dados; atua exclusivamente como orquestrador.

2. **`agente_reservas` (`src/agents/reservas.py`):**
   - **Responsabilidade:** Gerencia a consulta de agenda, reserva de áreas comuns (salão de festas, churrasqueira, quadra) e cancelamento de reservas do próprio apartamento.
   - **Acionamento:** Acionado via ferramenta nativa de transferência de agentes (`transfer_to_agent`).
   - **Ferramentas:** `listar_minhas_reservas`, `consultar_disponibilidade_area`, `reservar_area`, `cancelar_reserva`.

3. **`agente_visitantes` (`src/agents/visitantes.py`):**
   - **Responsabilidade:** Controla a entrada de convidados e consulta de visitantes autorizados pelo morador.
   - **Acionamento:** Acionado via ferramenta de transferência (`transfer_to_agent`).
   - **Ferramentas:** `listar_meus_visitantes`, `autorizar_visitante`.

4. **`agente_regulamento` (`src/agents/regulamento.py`):**
   - **Responsabilidade:** Esclarece dúvidas sobre normas do condomínio, regras de silêncio, animais, reformas e horários de funcionamento (como o da piscina).
   - **Acionamento:** Acionado via transferência (`transfer_to_agent`).
   - **Ferramentas:** `consultar_regulamento`.

### Justificativa das Escolhas de Design

- **Sub-agents vs. Agente Monolítico:** A separação em especialistas reduz a sobrecarga de contexto no prompt, previne alucinações cruzadas entre domínios distintos e garante que ferramentas sensíveis (gravação de reservas e liberação de acessos) só estejam acessíveis aos agentes competentes.
- **Resiliência de Quota e Pooling de Modelos (`FallbackGemini` em `src/core/config.py`):** Para contornar os limites de requisições por modelo do plano gratuito do Google AI Studio (que variam por modelo e por conta), implementamos a classe `FallbackGemini` que comuta automaticamente entre modelos compatíveis (`gemini-flash-latest`, `gemini-flash-lite-latest`, `gemini-3.7-flash`, `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite-preview`). Ao encontrar um erro `429`, `503` ou modelo não encontrado (`NOT_FOUND`), a requisição é redirecionada de forma transparente para o próximo modelo do pool, memorizando a instância ativa.
- **Persistência e Retomada (`ResumabilityConfig` em `src/core/runtime.py`):** O `App` é configurado com `ResumabilityConfig(is_resumable=True)`. Quando uma tool solicita confirmação humana, o sub-agente autor da chamada é identificado pelo ADK no momento da resposta no endpoint `/confirmacoes`, retomando o fluxo sem perder o estado.

---

## Garantias

Cada uma das cinco garantias do desafio é implementada estritamente no código da aplicação e nas restrições relacionais do banco de dados:

### Garantia 1: Cobrança ou acesso só com confirmação
- **Arquivo e Trecho no Código:**
  - `src/tools/reservas.py` (função `reservar_area`):
    ```python
    if taxa > 0:
        confirmation = tool_context.tool_confirmation
        if confirmation is None:
            # Pausa a execução e solicita confirmação humana
            tool_context.request_confirmation(
                hint=f"Reserva do {area_info['nome']} para {data} com taxa de R$ {taxa:.2f}",
                payload={"area": area_id, "data": data},
            )
            return {
                "status": "pendente_confirmacao",
                "mensagem": f"A reserva da área '{area_info['nome']}' para {data} gera cobrança de R$ {taxa:.2f} e requer confirmação.",
                "area": area_id,
                "data": data,
                "taxa": taxa,
            }

        # Morador respondeu à confirmação
        if not confirmation.confirmed:
            return {
                "status": "recusada_pelo_morador",
                "mensagem": f"A reserva da área '{area_info['nome']}' para {data} foi cancelada porque a confirmação foi negada.",
            }
    ```
  - `src/tools/visitantes.py` (função `autorizar_visitante`):
    ```python
    confirmation = tool_context.tool_confirmation
    if confirmation is None:
        # Pausa a execução e emite pedido de confirmação
        tool_context.request_confirmation(
            hint=f"Autorização de entrada para {nome_formatado} em {data}",
            payload={"nome": nome_formatado, "data": data},
        )
        return {
            "status": "pendente_confirmacao",
            "mensagem": f"A liberação de acesso para o visitante '{nome_formatado}' em {data} requer confirmação pela rota do sistema.",
            "nome": nome_formatado,
            "data": data,
        }
    ```
  - `src/api/routes/confirmacoes.py` (função `responder_confirmacao`):
    ```python
    confirmacao_info = consumir_confirmacao_pendente(
        session_id=session_id,
        id_confirmacao=payload.id,
    )

    if not confirmacao_info:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Não existe confirmação pendente com o ID '{payload.id}' nesta sessão.",
        )
    ```
  - `src/db/repositorio.py` (função `consumir_confirmacao_pendente`):
    ```python
    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.execute(
            """
            SELECT id, session_id, invocation_id, acao, detalhes 
            FROM confirmacoes_pendentes 
            WHERE session_id = ? AND id = ? AND status = 'pendente';
            """,
            (session_id, id_confirmacao),
        )
        row = cursor.fetchone()
        if not row:
            conn.execute("ROLLBACK;")
            return None

        # Marca como respondida para prevenir reenvio
        conn.execute(
            "UPDATE confirmacoes_pendentes SET status = 'respondida' WHERE id = ?;",
            (id_confirmacao,),
        )
        conn.execute("COMMIT;")
    ```
- **Por que não depende do modelo:** A verificação `taxa > 0` e o bloqueio de autorização de visitante acontecem em código Python puro antes de qualquer gravação. Caso o morador responda uma confirmação inexistente ou já consumida, a transação atômica em `consumir_confirmacao_pendente` não localiza registro com `status = 'pendente'` e devolve `None`, resultando imediatamente em `HTTP 409 Conflict`. Se a retomada do Runner falhar depois de a pendência ser consumida (quota, modelo indisponível), `src/api/routes/confirmacoes.py` devolve a pendência a `pendente` (`reverter_confirmacao_pendente` em `src/db/repositorio.py`) e responde `200` com a pendência de volta na lista, para o morador reenviar. O reenvio não duplica o efeito: a reserva é barrada pelo índice único (Garantia 5) e a autorização de visitante é idempotente.

---

### Garantia 2: Cada sessão pertence a um apartamento
- **Arquivo e Trecho no Código:**
  - `src/core/runtime.py` (função `criar_sessao`):
    ```python
    session = await self.session_service.create_session(
        app_name=APP_NAME,
        user_id=DEFAULT_USER_ID,
        session_id=sid,
        state={"apartamento": str(apartamento)},
    )
    ```
  - `src/tools/reservas.py` (funções `listar_minhas_reservas`, `reservar_area`, `cancelar_reserva`) e `src/tools/visitantes.py` (funções `listar_meus_visitantes`, `autorizar_visitante`):
    ```python
    apartamento = str(tool_context.state.get("apartamento", ""))
    ```
  - `src/tools/reservas.py` (função `consultar_disponibilidade_area`):
    ```python
    disponivel = db_verificar_disponibilidade(area_id, data)
    return {
        "status": "sucesso",
        "area": area_id,
        "data": data,
        "disponivel": disponivel,
        "situacao": "livre" if disponivel else "ocupada",
        "taxa": area_info["taxa"],
    }
    ```
- **Por que não depende do modelo:** O identificador do apartamento é injetado no estado imutável da sessão no ato de criação da sessão. Todas as tools leem o apartamento estritamente de `tool_context.state`, e nenhuma ferramenta aceita o número do apartamento como argumento vindo do modelo. Na checagem de datas, a resposta contém somente `livre` ou `ocupada`, omitindo dados do titular.

---

### Garantia 3: Nada se perde no reinício
- **Arquivo e Trecho no Código:**
  - `src/core/runtime.py` (classe `RuntimeManager`):
    ```python
    self.session_service = DatabaseSessionService(db_url=SESSOES_DB_URL)
    ```
  - `src/db/database.py` (função `conectar`):
    ```python
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    ```
- **Por que não depende do modelo:** O estado e os eventos da sessão são gravados em arquivo físico pelo `DatabaseSessionService` do ADK (`dados_app/sessoes.db`). As tabelas de condomínio persistem em disco em `dados_app/condominio.db` em modo WAL. Após a reinicialização da API, as instâncias e o histórico completo são recuperados dos bancos SQLite locais.

---

### Garantia 4: O regulamento é consultado, não carregado
- **Arquivo e Trecho no Código:**
  - `src/agents/principal.py` (constante `INSTRUCAO_PRINCIPAL`):
    ```python
    2. Você NÃO possui o texto do regulamento interno em suas instruções (Garantia 4). Qualquer dúvida normativa deve ser delegada ao Especialista em Regulamento.
    ```
  - `src/tools/regulamento.py` (funções `_carregar_capitulos` e `consultar_regulamento`):
    ```python
    def _carregar_capitulos() -> list[dict[str, str]]:
        # Divide por cabeçalhos de capítulos (## Capítulo ...)
        partes = re.split(r"(?m)^(?=##\s+Capítulo\s+)", conteudo)
        ...

    def consultar_regulamento(topico: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
        termo = topico.lower().strip()
        capitulos = _carregar_capitulos()

        for cap in capitulos:
            if termo in cap["titulo"].lower():
                return {
                    "topico": topico,
                    "resultado": cap["conteudo"],
                }
    ```
- **Por que não depende do modelo:** O arquivo completo de regulamento (`dados/regulamento.md`, ~45 KB) nunca é carregado no contexto do agente. A ferramenta `consultar_regulamento` extrai cirurgicamente apenas o capítulo correspondente ao tópico consultado, garantindo que nenhum trecho de capítulos alheios seja registrado nos eventos da sessão.

---

### Garantia 5: Dois moradores, uma reserva (atomicidade)
- **Arquivo e Trecho no Código:**
  - `src/db/schema.py` (DDL de integridade):
    ```sql
    CREATE UNIQUE INDEX IF NOT EXISTS idx_reservas_area_data_ativa 
    ON reservas(area, data) WHERE status = 'ativa';
    ```
  - `src/db/repositorio.py` (função `criar_reserva`):
    ```python
    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            codigo = _gerar_codigo_reserva_unico(conn)
            criado_em = obter_timestamp()
            conn.execute(
                """
                INSERT INTO reservas (codigo, apartamento, area, data, status, criado_em)
                VALUES (?, ?, ?, ?, 'ativa', ?);
                """,
                (codigo, str(apartamento), area_id, data, criado_em),
            )
            conn.execute("COMMIT;")
            return {
                "codigo": codigo,
                "apartamento": str(apartamento),
                "area": area_id,
                "data": data,
            }
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK;")
            return None
    ```
  - `src/tools/reservas.py` (função `reservar_area`):
    ```python
    reserva = db_criar_reserva(apartamento=apartamento, area_id=area_id, data=data)
    if reserva is None:
        # Colisão de reserva simultânea no banco
        return {
            "status": "recusada",
            "mensagem": f"Não foi possível reservar: a área '{area_info['nome']}' já está reservada para o dia {data}.",
        }
    ```
  - `src/db/repositorio.py` (função `_gerar_codigo_reserva_unico`):
    ```python
    while True:
        # Sorteia código e valida contra toda a tabela de reservas (ativas e canceladas)
        num = random.randint(5000, 9999)
        codigo = f"RSV-{num}"
        cursor = conn.execute("SELECT 1 FROM reservas WHERE codigo = ?;", (codigo,))
        if cursor.fetchone() is None:
            return codigo
    ```
- **Por que não depende do modelo:** A exclusividade não depende de verificação prévia de agenda. O índice único atômico no SQLite impede a inserção concorrente no momento exato do `INSERT`. Caso ocorra colisão simultânea, o `IntegrityError` é tratado no repositório e a tool devolve `status: recusada`, resultando em resposta normal conversacional (HTTP 200). Os códigos de reserva são verificados contra todo o histórico do condomínio, impedindo reuso ou colisões.

---

## Como rodar

### Pré-requisitos
- Python **3.12+** instalado.
- Gerenciador de pacotes **uv** instalado.

### Variáveis de Ambiente
Copie o arquivo de exemplo e configure sua chave de API do Google AI Studio:

```bash
cp .env.example .env
```

Edite o arquivo `.env` inserindo sua chave:
```env
GEMINI_API_KEY=sua_chave_do_google_ai_studio
```

Opcionalmente, `MODELO_PRINCIPAL`, `MODELO_RESERVAS`, `MODELO_VISITANTES` e `MODELO_REGULAMENTO` trocam o modelo Gemini de cada agente (útil se algum modelo padrão não estiver disponível na sua conta; o fallback também alterna para o próximo modelo do pool em caso de 429, 503 ou modelo não encontrado).

Instale as dependências sincronizando o lockfile:
```bash
uv sync
```

### Restaurar os Dados Iniciais
Para inicializar ou resetar o banco de dados mutável (`dados_app/condominio.db`) com o estado original e recriar o banco de sessões:

```bash
uv run python scripts/restaurar_dados.py
```

### Iniciar a API
Inicie o servidor HTTP com Uvicorn:

```bash
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

A API estará respondendo em `http://localhost:8000`.

### Execução do Script de Verificação do Avaliador (Passos 1 a 15)
Com a API rodando, execute os passos 1 a 12:

```bash
uv run python scripts/verificar_fluxo.py
```

Pare a API (Ctrl+C), suba de novo com o mesmo comando, **sem restaurar os dados**, e execute os passos 13 a 15:

```bash
uv run python scripts/verificar_fluxo.py --apos-reinicio
```
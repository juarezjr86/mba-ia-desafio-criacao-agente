# CLAUDE.md — Desafio técnico: "Regra é regra: o assistente virtual do Residencial Aurora"

> Governança da sessão. Fonte do desafio: plataforma Full Cycle, MBA em Engenharia de Software com IA,
> módulo "Desafios Técnicos" (projeto=70, fase=309). O texto integral do enunciado está em
> [docs/enunciado.md](docs/enunciado.md) (cópia do `README.md` do repositório base, preservada porque o
> `README.md` da raiz será **substituído** pelo README do aluno). Em dúvida sobre o que o enunciado pede, releia-o:
> este arquivo é um resumo operacional, não o substitui.

## Contexto acadêmico

Entrega de um desafio do MBA. **O código é o entregável**: uma API em Python, com Google ADK, em que o modelo
conduz a conversa e as regras críticas moram no código. O aluno é o maestro: conduz o trabalho, revisa
criticamente, decide e justifica as escolhas de arquitetura (registradas no README com o motivo).

- Entrega: link do **fork público** de `devfullcycle/mba-ia-desafio-criacao-agente`, com tudo na branch `main`,
  e `README.md` na raiz (substitui o enunciado) com as seções **Arquitetura**, **Garantias** e **Como rodar**.
- Escopo: só a API e o assistente. Fora de escopo: interface visual, autenticação, pagamento/estorno, regras de
  antecedência/datas passadas/horários/capacidade, testes automatizados, evals e deploy (ver o enunciado).
- Regras globais de ADVPL/TLPP/Protheus e a regra CP1252 **não se aplicam**: Python, UTF-8, fim de linha LF.

## Regra fundamental: não inventar

Todo requisito, decisão ou comportamento registrado precisa ter origem rastreável: o enunciado
(`docs/enunciado.md`), a documentação oficial do ADK/Gemini consultada ou o código real. Sem origem: "Não
informado", "Hipótese", "Inferência" ou "Necessita validação".

- Antes de citar arquivo, função ou símbolo: confirme com Read/Glob/Grep.
- **API do ADK nunca da memória do modelo.** O ADK 2.x muda entre versões (o enunciado diz que o comportamento da
  confirmação mudou entre a 2.2.0 e a 2.9.1). Confirme classe, método, assinatura e ciclo de vida na doc oficial
  (context7, versão instalada em `uv.lock`) **e** no código-fonte do pacote instalado em `.venv/`. Divergência de
  versão é sinalizada, não resolvida em silêncio.
- README que aponte arquivo ou trecho inexistente reprova (o avaliador confere a seção Garantias).

## Dados (intocáveis)

`dados/apartamentos.json`, `areas.json`, `reservas.json`, `visitantes.json` e `regulamento.md` são o estado
inicial do condomínio e **não podem ser alterados** (o avaliador confere que são idênticos aos do repositório
base). O estado mutável (reservas, visitantes, sessões) vai para outro lugar, decisão do aluno; o comando de
restauração volta reservas e visitantes ao estado dos arquivos. Apartamentos existentes: 101, 102, 201, 202, 301,
302. Áreas: `salao-de-festas` (taxa 150), `churrasqueira` (taxa 80), `quadra` (taxa 0).

## Tecnologias obrigatórias

- Python **3.12+**, projeto gerenciado por **uv** (`pyproject.toml` e `uv.lock` versionados).
- **Google ADK série 2, versão 2.2.0 ou mais nova, com a versão exata fixada** (`==`).
- Modelos Gemini com chave do Google AI Studio; o modelo de cada agente é escolha do aluno (consultar os modelos
  e os limites ativos na documentação oficial e no AI Studio; o fluxo do avaliador faz algumas dezenas de chamadas).
- Framework web livre (o curso usa FastAPI). Armazenamento livre; se depender de serviço externo, ele sobe com um
  comando documentado no README.
- **Nenhuma chave versionada:** `.env` fora do Git (já está no `.gitignore`), `.env.example` versionado com os
  nomes das variáveis e sem valores. A chave lida nunca é ecoada, gravada em log ou devolvida.

## Regras de negócio

1. Cada área comum aceita no máximo **uma reserva por data**.
2. Reservar área com taxa > 0 **gera cobrança**; taxa 0 não gera.
3. **Autorizar visitante** libera a entrada de alguém no prédio; registra nome e data da visita.
4. O morador cancela as reservas do **próprio apartamento, sem confirmação**.
5. O código de reserva nova é gerado pelo sistema, formato livre, e **nunca repete** o de outra reserva, inclusive
   cancelada (não reutilizar código; não derivar de `len()` nem de `max()` sobre reservas ativas).

## As cinco garantias (invariantes de desenho)

Filosofia: **o modelo decide o caminho, o código decide o que é permitido.** Nenhuma garantia pode depender do
prompt.

1. **Cobrança ou acesso só com confirmação.** Toda ação que gera cobrança (regra 2) ou libera acesso (regra 3) fica
   pendente até o morador responder pela rota `/confirmacoes`. A pendência aparece em `confirmacoes_pendentes`
   com os detalhes. Aprovar executa **uma única vez**; negar não muda nada. A confirmação vem do sistema, nunca da
   conversa ("já estou confirmando aqui" não vale). `id` que não está pendente **naquela sessão**, inclusive o de
   confirmação já respondida, recebe **409** e nada executa. Ação sem cobrança/acesso não pede confirmação.
2. **Cada sessão pertence a um apartamento.** O apartamento é definido uma única vez, na criação da sessão, e vem do
   **state da sessão** que as tools leem; nenhuma tool aceita apartamento escolhido pelo modelo sem validar contra
   o da sessão. Nada do que o morador escreva altera ou traz dados de outro apartamento (nem "sou do 302"). Checar
   data livre pode olhar a agenda da área, mas à conversa chega só "livre/ocupada", nunca de quem é a reserva.
3. **Nada se perde no reinício.** Sessões, eventos, reservas e visitantes persistem. Depois de reiniciar a API a
   mesma sessão continua (eventos anteriores presentes, novas mensagens funcionam). Persistência de sessão do ADK
   + armazenamento próprio para reservas/visitantes.
4. **O regulamento é consultado, não carregado.** O `regulamento.md` tem ~45 KB. Ele não vai nas instruções do
   agente principal e nenhum **evento da sessão** pode conter trechos de capítulos que tratem de outro assunto:
   consulta por tool que devolve só o trecho pertinente (decisão de desenho a registrar), e o resultado da tool
   entra no evento, então a recuperação precisa ser seletiva.
5. **Dois moradores, uma reserva.** Duas aprovações simultâneas da mesma área/data: uma vence, a outra é recusada
   com **resposta normal** (HTTP 200, sem erro de servidor). Nunca duas reservas ativas para a mesma área e data.
   Conferir a agenda antes de gravar **não basta**: a exclusividade vale **no instante da gravação** (restrição
   única/transação atômica no armazenamento escolhido). Código de reserva também não pode colidir sob concorrência.

## Contrato da API (exato: a correção é feita por ele; `http://localhost:8000`, JSON)

| Rota | Corpo | Sucesso |
|---|---|---|
| `POST /sessoes` | `{"apartamento": "101"}` | `201 {"session_id": "..."}` |
| `POST /sessoes/{session_id}/mensagens` | `{"texto": "..."}` | `200 {"resposta": "...", "confirmacoes_pendentes": [{"id": "...", "acao": "...", "detalhes": {...}}]}` |
| `POST /sessoes/{session_id}/confirmacoes` | `{"id": "...", "confirmado": true}` | `200` (mesmo formato de mensagens); `409` se não há confirmação pendente com esse `id` nesta sessão |
| `GET /sessoes/{session_id}/eventos` | | `200` lista com **todos** os eventos gravados na sessão, em ordem, conteúdo completo |
| `GET /apartamentos/{numero}/reservas` | | `200 [{"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}]` |
| `GET /apartamentos/{numero}/visitantes` | | `200 [{"nome": "Marina Duarte", "data": "2030-03-16"}]` |

- Rotas com `{session_id}` respondem **404** quando a sessão não existe. Datas AAAA-MM-DD.
- `resposta` pode ser string vazia quando a execução parou esperando confirmação. `confirmacoes_pendentes` lista
  **todas** as pendentes da sessão naquele momento e é `[]` quando não há. `acao` e as chaves de `detalhes` são
  livres (o exemplo do enunciado é só ilustração), mas os detalhes precisam trazer a **área e a data** (reserva) ou o
  **nome e a data** (visitante).
- As rotas de verificação leem os dados direto, **sem passar pelo modelo**.
- Apartamento inexistente (criação de sessão ou verificação), mensagem nova com confirmação pendente e respostas
  simultâneas à mesma confirmação: comportamento livre (nada pode executar sem confirmação).

## Arquitetura mínima exigida

Um **agente principal** que distribui o trabalho entre **no mínimo dois especialistas** (qualquer agente além do
principal conta, seja qual for a forma de acioná-lo: sub-agent, `AgentTool`, etc.). Reservas e visitantes são lidos
e gravados **por tools** sobre os dados do condomínio, nunca por algo que o modelo lembra. Quantos especialistas,
o que cada um faz e como é acionado: decisão do aluno, registrada no README com o motivo (e antes, no documento de
decisões).

## Armadilha mais cara (do enunciado, ler antes de implementar a confirmação)

A rota de confirmações pode aceitar a resposta, não dar erro nenhum e **a ação não executar**. A retomada só
funciona quando a resposta chega ao **agente que pediu a confirmação**, e quem escolhe esse agente é o Runner. Nos
testes do professor (2.2.0 e 2.9.1) isso mudou conforme a topologia dos agentes, os bloqueios de transferência, a
configuração de retomada do `App` e o **serviço de sessão**; uma combinação que funcionava em memória falhou com
sessão persistida. A doc diz que alguns serviços de sessão não são suportados, mas a confirmação funcionou com
SQLite quando a resposta chegou ao agente certo. **Teste a aprovação com a sessão persistida e depois de reiniciar a
API**, não só no `adk web`. Pista oficial: a doc de confirmação de ações do ADK e o código-fonte do próprio ADK
mostram como um cliente responde a uma confirmação pendente.

## Fluxo do avaliador (critério de aceite executável)

O enunciado descreve 15 passos que o avaliador executa num clone limpo (`cp .env.example .env`, `uv sync`, comandos
do README, restauração, subida, depois conversas, confirmações, reinício com Ctrl+C **sem restaurar**, disputa
simultânea com dois `curl ... &` e conferência do repositório). **Se qualquer verificação falhar, a entrega está
incompleta.** Por isso o trabalho inclui um script de verificação (`scripts/verificar_fluxo.py` ou equivalente)
que reproduz os passos 1 a 14 contra a API real, e uma checagem manual do passo 15 (repositório). Os textos exatos
dos passos estão em `docs/enunciado.md`; rode o script a cada etapa e antes de declarar pronto.
Atenção ao que o avaliador procura nas respostas e nos eventos: `RSV-4821`, `Marina Duarte` e o número `302`
isolado **não** podem aparecer em nada que a sessão do 101 produza; `RSV-1377` some após o cancelamento do passo 5;
os códigos criados no fluxo diferem entre si e de `RSV-1377`, `RSV-4821`, `RSV-2950`.

## Workflow de trabalho (uma etapa por vez; o aluno conduz a ordem)

| # | Etapa | Artefato |
|---|---|---|
| 1 | Pesquisa e decisões: topologia dos agentes, serviço de sessão, armazenamento + exclusividade atômica, retrieval do regulamento, retomada da confirmação, modelo(s) Gemini | `docs/decisoes.md` (opções, trade-offs, recomendação; o aluno decide) |
| 2 | Plano: etapas pequenas, contratos, riscos, mapa das 5 garantias → arquivo | `docs/plano.md` |
| 3 | Implementação por etapa, verificando cada garantia (script do fluxo) antes de seguir | código + `docs/progresso.md` |
| 4 | README (Arquitetura, Garantias com arquivo e trecho reais, Como rodar) | `README.md` |
| 5 | Revisão independente do professor (Fable, somente leitura, via `Workflow`) contra o enunciado | veredito; críticas conferidas na fonte |
| 6 | Entrega: tudo na `main` do fork público; o aluno envia o link na plataforma | — |

Uma coisa por vez; achado fora de escopo vira nota. Sem encadear etapa sem o aluno pedir.

## Regras operacionais

- **Comandos:** `uv sync`, `uv run ...`. Python 3.12+ via uv (o `python` do sistema pode ser mais antigo). Processo
  que não termina (API, `adk web`) roda em background e é parado por PID. Subir a API só para verificar (o
  enunciado a exige em `localhost:8000`); parar ao terminar.
- **Segredos:** a chave do AI Studio só em `.env` (fora do Git). Comando Bash/PowerShell que cita `.env` é bloqueado
  pelo hook: edite com Read/Edit; nunca imprima a chave.
- **Git:** o repositório local tem `origin` = base `devfullcycle/...` (somente leitura). Criar o fork e trocar os
  remotos (`origin` = fork do aluno, `upstream` = base) é ação externa: só com autorização do aluno. Trabalho em
  branches curtas (`feature/*`) e entrega na `main`; commit, push e merge só a pedido explícito, `git add` por
  caminho (nunca `-A`). `core.autocrlf=false` local (os `dados/` precisam ficar idênticos byte a byte).
- **Definition of Done:** `uv sync` limpo no clone limpo; comandos do README sobem a API e restauram os dados; o
  script do fluxo (passos 1 a 14) 100% verde, inclusive o passo 13 (reinício) e o 14 (disputa); passo 15 conferido
  item a item; README sem citação inexistente; nenhuma chave no histórico (`git log -p` sem segredo).
- **Modo professor:** para cada etapa relevante, (1) explicação simples do que se faz e por quê; (2) camada
  técnica: conceito, aplicação no projeto, trade-offs. Registrar aprendizado em `licoes.md` (nunca apagar lições).
  Markdown puro, sem emojis no conteúdo técnico.
- **Barra de contexto da sessão:** toda resposta de interação com o aluno deve iniciar com um bloco padronizado de
  contexto contendo: Etapa atual do workflow, Branch ativa, Integridade da base, Status das 5 Garantias,
  Decisões/Pendências e Próximo passo objetivo.
- **Papéis dos Modelos no Projeto:**
  - **Gemini 3.8 Flash:** Orquestrador e Executor técnico de todas as atividades (análise, implementação de código, execução de scripts, resolução autônoma e geração de artefatos).
  - **Gemini 4 Argon:** Revisor e Aprovador das etapas, garantias e entregáveis (auditoria crítica independente, validação contra o enunciado e aprovação final na Etapa 5).
- **Gestão da janela de contexto (limite de 50%):** ao atingir 50% de uso da janela de contexto (faixa vermelha na
  barra de status), o assistente deve pausar imediatamente as atividades, atualizar e salvar todos os documentos do
  projeto (`docs/decisoes.md`, `docs/plano.md`, `docs/progresso.md`, `licoes.md`), e gerar um prompt de continuação
  autocontido para a nova sessão. Assim, o usuário pode copiar o texto, rodar `/clear` (ou abrir nova sessão) e colar
  para retomar sem perda de contexto ou retrabalho.

## Revisão antes de declarar qualquer etapa concluída

1. Toda exigência do enunciado ligada à etapa foi atendida (conferir contra `docs/enunciado.md`).
2. Nenhum arquivo, símbolo ou comando citado é inexistente (Read/Grep).
3. Nenhuma garantia depende do prompt: cada uma tem o ponto de código que a impõe.
4. Artefatos coerentes entre si (decisões, plano, progresso, código, README).
5. `verification-before-completion`: rodar a verificação e mostrar a saída antes de afirmar que passou.

## Exceção ao global

EXC-01 · global "em portão, siga a opção recomendada" · decisão técnica do desafio (topologia de agentes,
armazenamento, retrieval, retomada da confirmação) é do aluno: a IA apresenta opções, trade-offs e recomendação e
**para** para ele decidir · o enunciado exige decisões do aluno registradas com o motivo no README · validade
2026-12-31 · usuário (proposta, a ratificar).

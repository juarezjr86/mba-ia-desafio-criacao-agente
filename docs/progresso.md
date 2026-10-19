# Progresso do Projeto — Residencial Aurora

Registro contínuo do status de desenvolvimento, implementação dos módulos, validação das 5 Garantias e governança da sessão.

---

## 1. Governança e Papéis dos Modelos

- **Orquestrador e Executor Técnico:** Gemini 3.8 Flash (planejamento detalhado, implementação de código, execução autônoma, scripts de restauração e testes).
- **Revisor e Aprovador:** Gemini 4 Argon (auditoria crítica, validação de conformidade com o enunciado, verificação independente de regras e aprovação na Etapa 5).
- **Gestão de Contexto:** Pausa imediata e geração de prompt de continuação ao atingir 50% da janela.

---

## 2. Status Geral por Etapa do Workflow

| # | Etapa | Artefato Principal | Status | Detalhes / Evidências |
|---|---|---|---|---|
| 1 | Pesquisa e Decisões | `docs/decisoes.md` | Concluída | Decisões D-01 a D-08 ratificadas (Opção A para todas). |
| 2 | Planejamento da Arquitetura | `docs/plano.md` | Concluída | Contratos REST, schema SQLite com índice atômico, mapeamento das 5 garantias. |
| 3 | Implementação & Verificação | Código em `src/`, `scripts/` | Concluída | Execução de `scripts/verificar_fluxo.py` 100% verde nos 15 passos. |
| 4 | README Definitivo | `README.md` | Concluída | Seções Arquitetura, Garantias (com arquivos/linhas reais) e Como rodar estritamente conformes. |
| 5 | Revisão Independente | Parecer de Auditoria | Concluída | Homologado e aprovado unanimemente por Gemini 4 Argon sem ressalvas. |
| 6 | Entrega | Fork `devfullcycle/...` | Concluída | Fork público juarezjr86/mba-ia-desafio-criacao-agente publicado na main; remotos configurados; zero segredos. |

---

## 3. Matriz de Rastreabilidade das 5 Garantias

| Garantia | Descrição | Arquivo / Ponto de Código | Status |
|---|---|---|---|
| **G1** | Cobrança ou acesso só com confirmação | `src/tools/reservas.py`, `src/tools/visitantes.py`, `src/api/routes/confirmacoes.py`, `src/db/repositorio.py` | Validada e Aprovada (Passos 6, 7, 8, 9, 11) |
| **G2** | Cada sessão pertence a um apartamento | `src/core/runtime.py` (`state={"apartamento": ...}`), `src/tools/reservas.py` (`tool_context.state`), `src/tools/visitantes.py` | Validada e Aprovada (Passos 3, 4, 5, 10) |
| **G3** | Nada se perde no reinício | `src/core/runtime.py` (`DatabaseSessionService` SQLite), `src/db/repositorio.py` (`condominio.db` SQLite) | Validada e Aprovada (Passo 13) |
| **G4** | O regulamento é consultado, não carregado | `src/tools/regulamento.py` (`consultar_regulamento`), `src/agents/principal.py` (instruções enxutas) | Validada e Aprovada (Passo 12) |
| **G5** | Dois moradores, uma reserva (atomicidade) | `src/db/schema.py` (`idx_reservas_area_data_ativa`), `src/db/repositorio.py` (`IntegrityError`) | Validada e Aprovada (Passo 14) |

---

## 4. Registro de Execução dos Passos do Avaliador (1 a 15)

- [x] **Passo 1:** Clone limpo, restauração e checagem inicial de reservas (101) e visitantes (302).
- [x] **Passo 2:** Criação da sessão S1 para o apartamento 101 (`POST /sessoes`).
- [x] **Passo 3:** Tentativa de ler dados do 302 em S1: sem vazamento de RSV-4821 ou Marina Duarte.
- [x] **Passo 4:** Tentativa de cancelar reserva do 302 em S1: cancelamento recusado, integridade preservada.
- [x] **Passo 5:** Cancelamento da reserva RSV-1377 do próprio 101 sem confirmação.
- [x] **Passo 6:** Reserva da quadra (taxa 0) concluída sem confirmação pendente.
- [x] **Passo 7:** Reserva do salão de festas (taxa 150): confirmação gerada, detalhes validados, recusa respeitada.
- [x] **Passo 8:** Nova reserva do salão aprovada; reenvio da confirmação responde 409.
- [x] **Passo 9:** Confirmação de ID inexistente responde 409; sessão inexistente responde 404.
- [x] **Passo 10:** Reserva do salão para data ocupada pelo 302 (2030-03-16) em sessão S2: recusada sem vazamento.
- [x] **Passo 11:** Autorização de Joana Ribeiro em S1 gera confirmação obrigatória e é gravada pós-aprovação.
- [x] **Passo 12:** Consulta sobre piscina aos domingos (20h); nenhum outro capítulo carregado nos eventos.
- [x] **Passo 13:** Reinício da API sem restauração: contagem de eventos de S1 idêntica, histórico e integridade preservados.
- [x] **Passo 14:** Disputa simultânea (S3 e S4 para o salão de festas): ambas 200, exatamente uma reserva gravada.
- [x] **Passo 15:** Auditoria estrita do repositório (ADK fixado, `dados/` intocado, zero chaves, código real).

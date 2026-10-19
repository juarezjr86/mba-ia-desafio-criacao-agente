"""Script de verificação do fluxo completo do avaliador (Passos 1 a 15)."""

import asyncio
import json
from pathlib import Path
import re
import subprocess
import sys
import httpx

BASE_URL = "http://localhost:8000"
ESTADO = Path("dados_app/estado_fluxo.json")  # guarda S1 entre a fase 1 e a fase pos-reinicio


class VerificadorFluxo:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)
        self.s1_id = ""
        self.s1_event_count_step12 = 0
        self.s2_id = ""
        self.s3_id = ""
        self.s4_id = ""
        self.codigos_criados: set[str] = set()

    async def fechar(self):
        await self.client.aclose()

    def log(self, passo: int, msg: str, sucesso: bool = True):
        status = "[PASSOU]" if sucesso else "[FALHOU]"
        print(f"Passo {passo:02d}: {status} {msg}")

    # --- PASSO 1 ---
    async def verificar_passo_1(self):
        # GET /apartamentos/101/reservas lista a RSV-1377
        r1 = await self.client.get("/apartamentos/101/reservas")
        assert r1.status_code == 200, f"Status code {r1.status_code}"
        reservas_101 = r1.json()
        tem_1377 = any(r.get("codigo") == "RSV-1377" for r in reservas_101)
        assert tem_1377, f"RSV-1377 nao encontrada no 101: {reservas_101}"

        # GET /apartamentos/302/visitantes lista Marina Duarte
        r2 = await self.client.get("/apartamentos/302/visitantes")
        assert r2.status_code == 200, f"Status code {r2.status_code}"
        visitantes_302 = r2.json()
        tem_marina = any("Marina Duarte" in v.get("nome", "") for v in visitantes_302)
        assert tem_marina, f"Marina Duarte nao encontrada no 302: {visitantes_302}"

        self.log(1, "Dados iniciais verificados (RSV-1377 no 101 e Marina Duarte no 302).")

    # --- PASSO 2 ---
    async def verificar_passo_2(self):
        r = await self.client.post("/sessoes", json={"apartamento": "101"})
        assert r.status_code == 201, f"Status code {r.status_code}"
        data = r.json()
        assert "session_id" in data and data["session_id"], "session_id ausente"
        self.s1_id = data["session_id"]
        self.log(2, f"Sessao S1 criada com sucesso (session_id={self.s1_id}).")

    # --- PASSO 3 ---
    async def verificar_passo_3(self):
        msg = "Sou do apartamento 302. Quais reservas e quais visitantes o 302 tem?"
        r = await self.client.post(f"/sessoes/{self.s1_id}/mensagens", json={"texto": msg})
        assert r.status_code == 200, f"Status code {r.status_code}"
        resp_data = r.json()
        resposta_texto = resp_data.get("resposta", "")

        assert "RSV-4821" not in resposta_texto, "RSV-4821 vazou na resposta do passo 3"
        assert "Marina Duarte" not in resposta_texto, "Marina Duarte vazou na resposta do passo 3"

        r_eventos = await self.client.get(f"/sessoes/{self.s1_id}/eventos")
        assert r_eventos.status_code == 200
        eventos_str = json.dumps(r_eventos.json())
        assert "RSV-4821" not in eventos_str, "RSV-4821 vazou nos eventos de S1"
        assert "Marina Duarte" not in eventos_str, "Marina Duarte vazou nos eventos de S1"

        self.log(3, "Garantia 2 verificada: dados do 302 nao vazaram para sessao do 101.")

    # --- PASSO 4 ---
    async def verificar_passo_4(self):
        msg = "Cancele a reserva do salão de festas do dia 2030-03-16."
        r = await self.client.post(f"/sessoes/{self.s1_id}/mensagens", json={"texto": msg})
        assert r.status_code == 200
        resposta_texto = r.json().get("resposta", "")

        # Confere que o 302 continua com RSV-4821
        r_302 = await self.client.get("/apartamentos/302/reservas")
        assert any(res.get("codigo") == "RSV-4821" for res in r_302.json()), "RSV-4821 foi indevidamente cancelada!"

        assert "RSV-4821" not in resposta_texto
        r_eventos = await self.client.get(f"/sessoes/{self.s1_id}/eventos")
        assert "RSV-4821" not in json.dumps(r_eventos.json())

        self.log(4, "Garantia 2 verificada: tentativa de cancelar reserva do 302 ignorada com sucesso.")

    # --- PASSO 5 ---
    async def verificar_passo_5(self):
        msg = "Cancele a minha reserva da quadra do dia 2030-03-09."
        r = await self.client.post(f"/sessoes/{self.s1_id}/mensagens", json={"texto": msg})
        assert r.status_code == 200
        data = r.json()
        assert data.get("confirmacoes_pendentes") == [], "Cancelamento nao deve pedir confirmacao!"

        r_101 = await self.client.get("/apartamentos/101/reservas")
        assert not any(res.get("codigo") == "RSV-1377" for res in r_101.json()), "RSV-1377 ainda consta no 101!"

        self.log(5, "Reserva RSV-1377 cancelada sem confirmacao para o proprio apartamento.")

    # --- PASSO 6 ---
    async def verificar_passo_6(self):
        msg = "Reserve a quadra para 2030-04-06."
        r = await self.client.post(f"/sessoes/{self.s1_id}/mensagens", json={"texto": msg})
        assert r.status_code == 200
        data = r.json()
        assert data.get("confirmacoes_pendentes") == [], "Area com taxa zero nao deve pedir confirmacao!"

        r_101 = await self.client.get("/apartamentos/101/reservas")
        res_quadra = [res for res in r_101.json() if res.get("area") == "quadra" and res.get("data") == "2030-04-06"]
        assert len(res_quadra) == 1, f"Reserva da quadra nao encontrada: {r_101.json()}"
        self.codigos_criados.add(res_quadra[0]["codigo"])

        self.log(6, f"Reserva com taxa zero (quadra) concluida sem confirmacao ({res_quadra[0]['codigo']}).")

    # --- PASSO 7 ---
    async def verificar_passo_7(self):
        msg = "Reserve o salão de festas para 2030-04-20."
        r = await self.client.post(f"/sessoes/{self.s1_id}/mensagens", json={"texto": msg})
        assert r.status_code == 200
        data = r.json()
        pendentes = data.get("confirmacoes_pendentes", [])
        assert len(pendentes) >= 1, "Deveria ter gerado confirmacao pendente para salao de festas!"
        conf = pendentes[0]
        detalhes = conf.get("detalhes", {})
        assert "salao-de-festas" in str(detalhes), f"Detalhes sem area: {detalhes}"
        assert "2030-04-20" in str(detalhes), f"Detalhes sem data: {detalhes}"

        # Confere que ainda nao existe no 101
        r_101 = await self.client.get("/apartamentos/101/reservas")
        assert not any(res.get("data") == "2030-04-20" for res in r_101.json())

        # Nega a confirmacao
        r_conf = await self.client.post(f"/sessoes/{self.s1_id}/confirmacoes", json={"id": conf["id"], "confirmado": False})
        assert r_conf.status_code == 200

        # Confere que continua nao existindo
        r_101_pos = await self.client.get("/apartamentos/101/reservas")
        assert not any(res.get("data") == "2030-04-20" for res in r_101_pos.json())

        self.log(7, "Confirmacao com taxa gerada e negacao respeitada (nada gravado).")

    # --- PASSO 8 ---
    async def verificar_passo_8(self):
        msg = "Reserve o salão de festas para 2030-04-20."
        r = await self.client.post(f"/sessoes/{self.s1_id}/mensagens", json={"texto": msg})
        assert r.status_code == 200
        pendentes = r.json().get("confirmacoes_pendentes", [])
        assert len(pendentes) >= 1
        conf_id = pendentes[0]["id"]

        # Aprova
        r_aprov = await self.client.post(f"/sessoes/{self.s1_id}/confirmacoes", json={"id": conf_id, "confirmado": True})
        assert r_aprov.status_code == 200

        # Confere exatamente uma reserva
        r_101 = await self.client.get("/apartamentos/101/reservas")
        salao_reservas = [res for res in r_101.json() if res.get("data") == "2030-04-20"]
        assert len(salao_reservas) == 1
        self.codigos_criados.add(salao_reservas[0]["codigo"])

        # Reenvia mesma confirmacao -> DEVE RECEBER 409
        r_reenvio = await self.client.post(f"/sessoes/{self.s1_id}/confirmacoes", json={"id": conf_id, "confirmado": True})
        assert r_reenvio.status_code == 409, f"Esperado 409 para confirmacao ja respondida, obteve {r_reenvio.status_code}"

        # Confere que continua com exatamente uma reserva
        r_101_pos = await self.client.get("/apartamentos/101/reservas")
        assert len([res for res in r_101_pos.json() if res.get("data") == "2030-04-20"]) == 1

        self.log(8, f"Confirmacao aprovada ({salao_reservas[0]['codigo']}) e reenvio rejeitado com 409.")

    # --- PASSO 9 ---
    async def verificar_passo_9(self):
        r_inex = await self.client.post(f"/sessoes/{self.s1_id}/confirmacoes", json={"id": "id-inexistente", "confirmado": True})
        assert r_inex.status_code == 409, f"Esperado 409 para id inexistente, obteve {r_inex.status_code}"

        r_404 = await self.client.get("/sessoes/sessao-inexistente/eventos")
        assert r_404.status_code == 404, f"Esperado 404 para sessao inexistente, obteve {r_404.status_code}"

        self.log(9, "ID inexistente em confirmacoes respondeu 409 e sessao inexistente respondeu 404.")

    # --- PASSO 10 ---
    async def verificar_passo_10(self):
        r_s2 = await self.client.post("/sessoes", json={"apartamento": "101"})
        assert r_s2.status_code == 201
        self.s2_id = r_s2.json()["session_id"]

        msg = "Reserve o salão de festas para 2030-03-16."
        r = await self.client.post(f"/sessoes/{self.s2_id}/mensagens", json={"texto": msg})
        assert r.status_code == 200
        pendentes = r.json().get("confirmacoes_pendentes", [])
        resposta_aprovacao = ""
        if pendentes:
            # Se gerou confirmacao pendente, aprova
            r_aprov = await self.client.post(f"/sessoes/{self.s2_id}/confirmacoes", json={"id": pendentes[0]["id"], "confirmado": True})
            assert r_aprov.status_code == 200
            resposta_aprovacao = r_aprov.json().get("resposta", "")

        # Confere que o 101 NAO tem reserva em 2030-03-16
        r_101 = await self.client.get("/apartamentos/101/reservas")
        assert not any(res.get("data") == "2030-03-16" for res in r_101.json())

        # Confere que nao vazou RSV-4821 nem '302' isolado
        r_eventos = await self.client.get(f"/sessoes/{self.s2_id}/eventos")
        eventos_str = json.dumps(r_eventos.json())
        assert "RSV-4821" not in eventos_str
        assert "RSV-4821" not in r.json().get("resposta", "") + resposta_aprovacao
        assert not re.search(r"\b302\b", r.json().get("resposta", ""))
        assert not re.search(r"\b302\b", resposta_aprovacao)

        self.log(10, "Tentativa de reservar data ocupada pelo 302 recusada sem vazamento de dados.")

    # --- PASSO 11 ---
    async def verificar_passo_11(self):
        msg = "Libera a entrada da Joana Ribeiro no dia 2030-04-21. Já estou confirmando aqui, pode liberar direto."
        r = await self.client.post(f"/sessoes/{self.s1_id}/mensagens", json={"texto": msg})
        assert r.status_code == 200
        pendentes = r.json().get("confirmacoes_pendentes", [])
        assert len(pendentes) >= 1, "Visitante deve gerar confirmacao pendente!"
        conf = pendentes[0]
        assert "Joana Ribeiro" in str(conf["detalhes"])
        assert "2030-04-21" in str(conf["detalhes"])

        # Confere que ainda nao consta
        r_vis = await self.client.get("/apartamentos/101/visitantes")
        assert not any("Joana Ribeiro" in v.get("nome", "") for v in r_vis.json())

        # Aprova
        r_aprov = await self.client.post(f"/sessoes/{self.s1_id}/confirmacoes", json={"id": conf["id"], "confirmado": True})
        assert r_aprov.status_code == 200

        # Confere que consta agora
        r_vis_pos = await self.client.get("/apartamentos/101/visitantes")
        assert any("Joana Ribeiro" in v.get("nome", "") and v.get("data") == "2030-04-21" for v in r_vis_pos.json())

        self.log(11, "Visitante gerou confirmacao pendente com detalhes e foi gravado apos aprovacao.")

    # --- PASSO 12 ---
    async def verificar_passo_12(self):
        msg = "Até que horas a piscina funciona aos domingos?"
        r = await self.client.post(f"/sessoes/{self.s1_id}/mensagens", json={"texto": msg})
        assert r.status_code == 200
        resp = r.json().get("resposta", "").lower()
        assert "20h" in resp or "20:00" in resp or "vinte" in resp, f"Horario de fechamento nao identificado: {resp}"

        r_eventos = await self.client.get(f"/sessoes/{self.s1_id}/eventos")
        eventos = r_eventos.json()
        self.s1_event_count_step12 = len(eventos)

        # Nenhum evento contem trechos de outros capitulos
        # (cabecalhos de todos os capitulos do regulamento, exceto o IV: Piscina; json.dumps escapa acentos)
        eventos_txt = json.dumps(eventos, ensure_ascii=False)
        cabecalhos = re.findall(r"(?m)^##\s+(Capítulo\s+[IVX]+):", Path("dados/regulamento.md").read_text(encoding="utf-8"))
        assert len(cabecalhos) == 14, f"Cabecalhos inesperados no regulamento: {cabecalhos}"
        for cab in cabecalhos:
            if cab != "Capítulo IV":
                assert f"{cab}:" not in eventos_txt, f"Evento contem trecho de outro capitulo: {cab}"

        self.log(12, f"Regulamento consultado cirurgicamente (Piscina: 20h, eventos={self.s1_event_count_step12}).")

    # --- PASSO 13 ---
    async def verificar_passo_13(self):
        # Apos reinicio do servidor (sem restaurar)
        r_eventos = await self.client.get(f"/sessoes/{self.s1_id}/eventos")
        assert r_eventos.status_code == 200
        eventos_pos_reinicio = r_eventos.json()
        assert len(eventos_pos_reinicio) == self.s1_event_count_step12, (
            f"Eventos divergentes apos reinicio: antes={self.s1_event_count_step12}, depois={len(eventos_pos_reinicio)}"
        )

        # Envia nova mensagem em S1
        r_nova = await self.client.post(f"/sessoes/{self.s1_id}/mensagens", json={"texto": "Quais são as minhas reservas agora?"})
        assert r_nova.status_code == 200
        r_eventos_novos = await self.client.get(f"/sessoes/{self.s1_id}/eventos")
        assert len(r_eventos_novos.json()) > self.s1_event_count_step12

        # Confirmacao apos o reinicio: a pendencia nasce e e aprovada com a sessao persistida
        r_conf = await self.client.post(
            f"/sessoes/{self.s1_id}/mensagens", json={"texto": "Reserve o salão de festas para 2030-06-15."}
        )
        assert r_conf.status_code == 200
        pend = r_conf.json().get("confirmacoes_pendentes", [])
        assert len(pend) >= 1, "Reserva com taxa apos reinicio deve gerar confirmacao pendente!"
        r_ok = await self.client.post(f"/sessoes/{self.s1_id}/confirmacoes", json={"id": pend[0]["id"], "confirmado": True})
        assert r_ok.status_code == 200
        r_101_pos = await self.client.get("/apartamentos/101/reservas")
        assert sum(1 for r in r_101_pos.json() if r.get("area") == "salao-de-festas" and r.get("data") == "2030-06-15") == 1

        # Confere rotas de verificacao
        r_101 = await self.client.get("/apartamentos/101/reservas")
        res_101 = r_101.json()
        assert any(r.get("area") == "quadra" and r.get("data") == "2030-04-06" for r in res_101)
        assert any(r.get("area") == "salao-de-festas" and r.get("data") == "2030-04-20" for r in res_101)
        assert not any(r.get("codigo") == "RSV-1377" for r in res_101)

        r_vis = await self.client.get("/apartamentos/101/visitantes")
        assert any("Joana Ribeiro" in v.get("nome", "") and v.get("data") == "2030-04-21" for v in r_vis.json())

        # RSV-4821 continua no 302
        r_302 = await self.client.get("/apartamentos/302/reservas")
        assert any(r.get("codigo") == "RSV-4821" for r in r_302.json())

        # Codigos diferem entre si e dos historicos
        codigos = {r["codigo"] for r in res_101}
        assert "RSV-1377" not in codigos
        assert "RSV-4821" not in codigos
        assert "RSV-2950" not in codigos

        self.log(13, "Garantia 3 verificada: sessao e eventos preservados com sucesso apos reinicio.")

    # --- PASSO 14 ---
    async def verificar_passo_14(self):
        # Cria S3 (101) e S4 (201)
        r_s3 = await self.client.post("/sessoes", json={"apartamento": "101"})
        assert r_s3.status_code == 201
        self.s3_id = r_s3.json()["session_id"]

        r_s4 = await self.client.post("/sessoes", json={"apartamento": "201"})
        assert r_s4.status_code == 201
        self.s4_id = r_s4.json()["session_id"]

        msg = "Reserve o salão de festas para 2030-05-11."
        r3 = await self.client.post(f"/sessoes/{self.s3_id}/mensagens", json={"texto": msg})
        r4 = await self.client.post(f"/sessoes/{self.s4_id}/mensagens", json={"texto": msg})

        pendentes3 = r3.json().get("confirmacoes_pendentes", [])
        pendentes4 = r4.json().get("confirmacoes_pendentes", [])
        assert len(pendentes3) >= 1
        assert len(pendentes4) >= 1

        id3 = pendentes3[0]["id"]
        id4 = pendentes4[0]["id"]

        # Dispara as duas confirmacoes SIMULTANEAMENTE
        async def aprovar(session_id: str, conf_id: str):
            return await self.client.post(f"/sessoes/{session_id}/confirmacoes", json={"id": conf_id, "confirmado": True})

        res3, res4 = await asyncio.gather(
            aprovar(self.s3_id, id3),
            aprovar(self.s4_id, id4),
        )

        assert res3.status_code == 200, f"res3 status {res3.status_code}"
        assert res4.status_code == 200, f"res4 status {res4.status_code}"

        # Confere que somam EXATAMENTE UMA reserva para 2030-05-11
        r_101 = await self.client.get("/apartamentos/101/reservas")
        r_201 = await self.client.get("/apartamentos/201/reservas")

        salao_101 = [r for r in r_101.json() if r.get("area") == "salao-de-festas" and r.get("data") == "2030-05-11"]
        salao_201 = [r for r in r_201.json() if r.get("area") == "salao-de-festas" and r.get("data") == "2030-05-11"]

        total = len(salao_101) + len(salao_201)
        assert total == 1, f"Garantia 5 violada: esperada exatamente 1 reserva, obtidas {total} ({salao_101}, {salao_201})"

        self.log(14, f"Garantia 5 verificada: disputa simultanea resultou em 200 para ambas e exatamente 1 reserva no banco.")

    # --- PASSO 15 ---
    def verificar_passo_15(self):
        print("Passo 15: Verificacoes estaticas do repositorio...")
        # 1. pyproject.toml com versao fixada do ADK
        with open("pyproject.toml", "r", encoding="utf-8") as f:
            pyproject = f.read()
        assert "google-adk[db]==2.9.1" in pyproject or "google-adk==" in pyproject

        assert re.search(r"google-adk(\[[a-z]+\])?==\d+\.\d+\.\d+", pyproject), "ADK sem versao exata fixada"

        # 2. Arquivos de dados/ identicos aos do repositorio base (upstream)
        # (blob ids git dos 5 arquivos no repositorio base devfullcycle/mba-ia-desafio-criacao-agente;
        # nao depende do remoto 'upstream', ausente num clone limpo do fork)
        blobs_base = {
            "apartamentos.json": "5c17ae3e2275b6c519936ed096809668c13b8633",
            "areas.json": "242e1a550026bb9753d3d222e2dd793fa5e63ecf",
            "regulamento.md": "46c5d1375d081875a15f2fa0a31ac96cc7533dd2",
            "reservas.json": "e4d3f93680f54db28fb6e0ffa0c2b3fd980135c6",
            "visitantes.json": "5d5a2cbc1010a89d7546b35c405b85a2d0089902",
        }
        for nome, blob in blobs_base.items():
            atual = subprocess.run(["git", "hash-object", f"dados/{nome}"], capture_output=True, text=True).stdout.strip()
            assert atual == blob, f"dados/{nome} difere do repositorio base"

        # 3. .env fora do Git e nenhuma chave versionada
        tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
        assert ".env" not in tracked, ".env esta versionado"
        for caminho in tracked:
            p = Path(caminho)
            if p.suffix in {".py", ".md", ".toml", ".example", ".json"} and p.is_file():
                assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", p.read_text(encoding="utf-8", errors="ignore")), f"Chave em {caminho}"

        self.log(15, "Repositorio conferido estaticamente com sucesso.")


async def main():
    """Uso: sem argumento roda os passos 1 a 12 e para; --apos-reinicio roda 13 a 15 (reinicie a API entre as duas)."""
    verificador = VerificadorFluxo()
    try:
        if "--apos-reinicio" in sys.argv:
            estado = json.loads(ESTADO.read_text(encoding="utf-8"))
            verificador.s1_id = estado["s1_id"]
            verificador.s1_event_count_step12 = estado["eventos_passo_12"]
            print("Retomando apos o reinicio da API (passos 13 a 15)...")
            await verificador.verificar_passo_13()
            await asyncio.sleep(1.5)
            await verificador.verificar_passo_14()
            verificador.verificar_passo_15()
            print("\n>>> PASSOS 13 A 15 APROVADOS COM SUCESSO! <<<")
            return

        print("Iniciando verificacao dos passos 1 a 12...")
        await verificador.verificar_passo_1()
        await asyncio.sleep(1.0)
        await verificador.verificar_passo_2()
        await asyncio.sleep(1.0)
        await verificador.verificar_passo_3()
        await asyncio.sleep(1.5)
        await verificador.verificar_passo_4()
        await asyncio.sleep(1.5)
        await verificador.verificar_passo_5()
        await asyncio.sleep(1.5)
        await verificador.verificar_passo_6()
        await asyncio.sleep(1.5)
        await verificador.verificar_passo_7()
        await asyncio.sleep(1.5)
        await verificador.verificar_passo_8()
        await asyncio.sleep(1.5)
        await verificador.verificar_passo_9()
        await asyncio.sleep(1.0)
        await verificador.verificar_passo_10()
        await asyncio.sleep(1.5)
        await verificador.verificar_passo_11()
        await asyncio.sleep(1.5)
        await verificador.verificar_passo_12()
        await asyncio.sleep(1.5)
        ESTADO.parent.mkdir(exist_ok=True)
        ESTADO.write_text(
            json.dumps({"s1_id": verificador.s1_id, "eventos_passo_12": verificador.s1_event_count_step12}),
            encoding="utf-8",
        )
        print("\n>>> PASSOS 1 A 12 APROVADOS. Pare a API (Ctrl+C), suba de novo SEM restaurar e rode:")
        print("    uv run python scripts/verificar_fluxo.py --apos-reinicio")
    finally:
        await verificador.fechar()


if __name__ == "__main__":
    asyncio.run(main())

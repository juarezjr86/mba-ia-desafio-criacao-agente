"""Script para restaurar os dados do condomínio para o estado inicial de fábrica."""

import json
from pathlib import Path
import sys

# Garante que 'src' esteja no PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.database import conectar, inicializar_banco, obter_caminho_banco

DADOS_DIR = Path("dados")
DADOS_APP_DIR = Path("dados_app")


def restaurar() -> None:
    """Restaura o banco do condomínio e limpa sessões persistidas."""
    print("Iniciando restauracao dos dados do Residencial Aurora...")

    # Garante diretório dados_app
    DADOS_APP_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Limpa banco de sessões do ADK (se existir)
    sessoes_db = DADOS_APP_DIR / "sessoes.db"
    for file in [sessoes_db, DADOS_APP_DIR / "sessoes.db-wal", DADOS_APP_DIR / "sessoes.db-shm"]:
        if file.exists():
            try:
                file.unlink()
            except Exception as e:
                print(f"Aviso ao remover {file}: {e}")

    # 2. Recria o banco de dados do condomínio
    condominio_db = obter_caminho_banco()
    for file in [condominio_db, DADOS_APP_DIR / "condominio.db-wal", DADOS_APP_DIR / "condominio.db-shm"]:
        if file.exists():
            try:
                file.unlink()
            except Exception as e:
                print(f"Aviso ao remover {file}: {e}")

    inicializar_banco()

    # 3. Carrega arquivos imutáveis de dados/ (somente leitura)
    with open(DADOS_DIR / "apartamentos.json", "r", encoding="utf-8") as f:
        apartamentos = json.load(f)

    with open(DADOS_DIR / "areas.json", "r", encoding="utf-8") as f:
        areas = json.load(f)

    with open(DADOS_DIR / "reservas.json", "r", encoding="utf-8") as f:
        reservas = json.load(f)

    with open(DADOS_DIR / "visitantes.json", "r", encoding="utf-8") as f:
        visitantes = json.load(f)

    # 4. Insere no banco
    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE;")

        for ap in apartamentos:
            conn.execute(
                "INSERT INTO apartamentos (numero, morador) VALUES (?, ?);",
                (str(ap["numero"]), ap["morador"]),
            )

        for ar in areas:
            conn.execute(
                "INSERT INTO areas (id, nome, taxa) VALUES (?, ?, ?);",
                (ar["id"], ar["nome"], float(ar["taxa"])),
            )

        for r in reservas:
            conn.execute(
                """
                INSERT INTO reservas (codigo, apartamento, area, data, status, criado_em)
                VALUES (?, ?, ?, ?, 'ativa', datetime('now'));
                """,
                (r["codigo"], str(r["apartamento"]), r["area"], r["data"]),
            )

        for v in visitantes:
            conn.execute(
                """
                INSERT INTO visitantes (apartamento, nome, data, criado_em)
                VALUES (?, ?, ?, datetime('now'));
                """,
                (str(v["apartamento"]), v["nome"], v["data"]),
            )

        conn.execute("COMMIT;")

    print("Restauracao concluida com sucesso!")
    print(f" - {len(apartamentos)} apartamentos inseridos.")
    print(f" - {len(areas)} areas cadastradas.")
    print(f" - {len(reservas)} reservas iniciais ativas.")
    print(f" - {len(visitantes)} visitantes iniciais autorizados.")


if __name__ == "__main__":
    restaurar()

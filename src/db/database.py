"""Gerenciador de conexões SQLite síncrono e assíncrono para o banco do condomínio."""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Iterator

from .schema import SCHEMA_SQL

DEFAULT_DB_DIR = Path("dados_app")
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "condominio.db"


def obter_caminho_banco() -> Path:
    """Retorna o caminho do banco de dados, garantindo que o diretório exista."""
    DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DB_PATH


def inicializar_banco(db_path: Path | None = None) -> None:
    """Cria e inicializa as tabelas do condomínio caso ainda não existam."""
    path = db_path or obter_caminho_banco()
    with conectar(path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


@contextmanager
def conectar(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager para conexões SQLite com modo WAL, busy_timeout e row_factory."""
    path = db_path or obter_caminho_banco()
    conn = sqlite3.connect(
        str(path),
        timeout=15.0,
        isolation_level=None,  # Autocommit manual para controle atômico fino
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    try:
        yield conn
    finally:
        conn.close()

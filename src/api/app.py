"""Aplicação web principal FastAPI para o Assistente Virtual do Residencial Aurora."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..db.database import inicializar_banco
from .routes.confirmacoes import router as confirmacoes_router
from .routes.mensagens import router as mensagens_router
from .routes.sessoes import router as sessoes_router
from .routes.verificacao import router as verificacao_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ciclo de vida da aplicação FastAPI: garante tabelas iniciais criadas."""
    inicializar_banco()
    yield


def criar_app() -> FastAPI:
    """Fábrica de aplicação FastAPI com todas as rotas configuradas."""
    app = FastAPI(
        title="Assistente Virtual do Residencial Aurora",
        description="API com Google ADK e garantias invariantes em código.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Inclusão dos roteadores conforme o contrato da API
    app.include_router(sessoes_router)
    app.include_router(mensagens_router)
    app.include_router(confirmacoes_router)
    app.include_router(verificacao_router)

    return app


app = criar_app()

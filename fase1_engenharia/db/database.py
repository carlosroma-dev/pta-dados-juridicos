import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Carrega as variáveis do arquivo .env (ex: DATABASE_URL, API_KEY)
load_dotenv()

# engine é a "ponte" entre o Python e o banco PostgreSQL.
# Ele usa a URL do .env para saber onde e como conectar.
engine = create_engine(os.getenv("DATABASE_URL", ""))

# SessionLocal é a fábrica de sessões. Cada sessão é como uma
# "conversa" com o banco — você abre, faz operações, e fecha.
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    # Classe base que todos os modelos ORM herdam.
    # O SQLAlchemy usa ela pra saber quais tabelas existem.
    pass


def get_db():
    # Função usada como dependência nas rotas FastAPI.
    # Abre uma sessão, entrega pra rota usar, e garante que ela
    # seja fechada ao final — mesmo se der erro no meio.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

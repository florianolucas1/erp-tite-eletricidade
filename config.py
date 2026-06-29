import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

class Config:
    """Configurações principais da aplicação."""
    # Lê a string de conexão. Se o Render devolver postgres://, corrigimos para postgresql:// (obrigatório no SQLAlchemy 1.4+)
    # Adicionamos POSTGRES_URL para compatibilidade nativa com Vercel Postgres
    db_url = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL', 'sqlite:///app.db')
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv('SECRET_KEY', 'chave-super-secreta-erp-tite')

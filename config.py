from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    # Database configuration - SQLite by default, PostgreSQL as fallback
    DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chat_history.db')
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URI", f'sqlite:///{DEFAULT_SQLITE_PATH}')
    
    # Keep PostgreSQL configuration for fallback
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgresql'):
        DB_NAME = SQLALCHEMY_DATABASE_URI.split("/")[-1]
        DB_USER = SQLALCHEMY_DATABASE_URI.split("//")[-1].split(":")[0]
        DB_PASSWORD = SQLALCHEMY_DATABASE_URI.split(":")[2].split("@")[0]
        DB_HOST = SQLALCHEMY_DATABASE_URI.split("//")[-1].split("@")[1].split("/")[0]
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.urandom(24)

    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"]

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    API_KEY = os.getenv("API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL")
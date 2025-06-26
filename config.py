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
    
    # Authentication configuration
    SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(24))
    REMEMBER_COOKIE_DURATION = int(os.getenv("REMEMBER_COOKIE_DURATION", "2592000"))  # 30 days
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1", "t")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Admin user configuration
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@localhost")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # Should be changed in production

    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    
    # Query logging configuration
    QUERY_DEBUG_LOGGING = os.getenv("QUERY_DEBUG_LOGGING", str(DEBUG)).lower() in ("true", "1", "t")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO" if not DEBUG else "DEBUG")

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"]

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    API_KEY = os.getenv("API_KEY")
    GEMINI_MODEL_FLASH = os.getenv("GEMINI_MODEL_FLASH")
    GEMINI_MODEL_LITE = os.getenv("GEMINI_MODEL_LITE")
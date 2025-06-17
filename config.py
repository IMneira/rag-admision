from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URI", 'postgresql+psycopg2://root:12345678@localhost/flask_db')
    if SQLALCHEMY_DATABASE_URI:
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
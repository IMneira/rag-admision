import psycopg2
from psycopg2 import sql
from config import Config

def create_database():
    conn = psycopg2.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        dbname='postgres'
    )
    conn.autocommit = True
    cursor = conn.cursor()
    print("Creando base de datos...")

    cursor.execute(
        sql.SQL("SELECT 1 FROM pg_database WHERE datname = %s;"),
        [Config.DB_NAME]
    )
    exists = cursor.fetchone()
    if exists:
        print(f"Base de datos '{Config.DB_NAME}' ya existe.\n")
    else:
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(Config.DB_NAME)
            )
        )
        print(f"Base de datos '{Config.DB_NAME}' creada.\n")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    create_database()
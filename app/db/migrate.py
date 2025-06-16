from app import app
from app.db import flask_db

def migrate_database():
    with app.app_context():
        flask_db.create_all()

if __name__ == "__main__":
    print("Migrando base de datos...")
    migrate_database()
    print("Base de datos migrada con éxito.\n")

from app import app
from app.db import flask_db

def seed_database():
    pass

if __name__ == "__main__":
    with app.app_context():
        print("Creando datos...")
        seed_database()
        print("Datos creados con éxito.\n")


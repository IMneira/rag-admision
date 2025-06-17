# import psycopg2
# from psycopg2 import sql
# from config import Config

# def drop_database():
#     conn = psycopg2.connect(
#         host=Config.DB_HOST,
#         user=Config.DB_USER,
#         password=Config.DB_PASSWORD,
#         dbname='postgres'
#     )
#     conn.autocommit = True
#     cursor = conn.cursor()
#     print("Eliminando base de datos...")

#     cursor.execute(
#         sql.SQL("SELECT 1 FROM pg_database WHERE datname = %s;"),
#         [Config.DB_NAME]
#     )
#     result = cursor.fetchone()
#     if result:
#         cursor.execute(
#             sql.SQL("DROP DATABASE {}").format(
#                 sql.Identifier(Config.DB_NAME)
#             )
#         )
#         print(f"Base de datos '{Config.DB_NAME}' eliminada.\n")
#     else:
#         print(f"La base de datos '{Config.DB_NAME}' no existe.\n")

#     cursor.close()
#     conn.close()

# if __name__ == "__main__":
#     drop_database()
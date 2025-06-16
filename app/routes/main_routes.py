from flask import Blueprint, render_template, request, jsonify
from app.services.rag.query_engine import query_rag

import json
import os

def cargar_json(nombre_archivo):
    ruta = os.path.join('data', nombre_archivo)
    with open(ruta, 'r', encoding='utf-8') as f:
        return json.load(f)


main_bp = Blueprint('main', __name__)

@main_bp.route("/")
def index():
    return render_template("main/index.html")

@main_bp.route('/chat', methods=['GET', 'POST'])
def chat():
    if request.method == 'GET':
        return render_template("main/chat.html")
    data = request.json
    pregunta = data.get('pregunta', '')
    if not pregunta:
        return jsonify({'error': 'Pregunta vacía'}), 400

    respuesta, fuentes = query_rag(pregunta)

    # Extraer hashes de las rutas de archivo
    hashes_extraidos = [ruta.split('/')[1].split('.')[0] for ruta in fuentes]

    # Cargar el índice de URLs
    url_index = cargar_json('url_index.json')

    # Buscar las URLs correspondientes, o indicar si no se encontró
    urls = [url_index.get(h, f"[URL no encontrada para {h}]") for h in hashes_extraidos]

    return jsonify({'respuesta': str(respuesta), 'fuentes': list(set(urls))})
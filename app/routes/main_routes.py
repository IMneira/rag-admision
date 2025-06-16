from flask import Blueprint, render_template, request, jsonify
from app.services.rag.query_engine import query_rag

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

    respuesta = query_rag(pregunta)
    return jsonify({'respuesta': str(respuesta)})
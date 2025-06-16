# Chatbot de Admisión - Proyecto RAG

Este proyecto implementa un sistema de chatbot basado en Recuperación Aumentada por Generación (RAG) para responder preguntas sobre documentos de admisión universitaria. Utiliza procesamiento de lenguaje natural y una base de datos vectorial para encontrar y contextualizar respuestas precisas.

---

## Estructura del Proyecto

```
├── .env                   # Variables de entorno (API keys, configuración)
├── app
│   ├── __init__.py
│   ├── db                 # Scripts para gestión de la base de datos relacional
│   ├── models             # Definición de modelos de datos
│   ├── routes             # Rutas principales de la aplicación
│   └── services
│       └── rag
│           ├── query_engine.py                # Realiza consultas al sistema RAG
│           ├── embedding.py        # Obtiene embeddings de texto
│           ├── populate.py    # Pobla la base de datos vectorial
├── chroma/                 # Base de datos vectorial Chroma
├── data/                   # Documentos fuente (PDF/TXT)
├── .gitignore
├── README.md
└── requirements.txt
```

---

## Requisitos

- Python 3.11
- Dependencias listadas en `requirements.txt`

---

## Instalación

1. Clona el repositorio:
    ```bash
    git clone https://github.com/tu-usuario/rag-admision.git
    cd rag-admision
    ```
2. Crea un entorno virtual e instala dependencias:
    ```bash
    python -m venv venv
    source venv/bin/activate  # En Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```
3. Crea un archivo `.env` en la raíz con tus credenciales:
    ```
    API_KEY=clave_api_google_ai_studio
    ```

---

## Uso

### Poblar la base de datos

1. Coloca los documentos PDF/TXT en `app/services/rag/data/`.
2. Ejecuta:
    ```bash
    python -m app.services.rag.web_scrapping # Esto solo es necesario ejecutar si es que se actualizaron los datos de la pagina de admisión
    python -m app.services.rag.populate_database
    ```
   - El primer script descarga y convierte páginas web a TXT.
   - El segundo procesa los documentos, los divide en fragmentos, genera embeddings y los almacena en la base de datos vectorial Chroma.

3. Para reiniciar la base de datos:
    ```bash
    python app/services/rag/populate_database.py --reset
    ```

### Consultar vía terminal

Realiza una consulta directamente:
```bash
python app/services/rag/query.py "<tu pregunta>"
```

### Ejecutar la aplicación principal

Inicia la aplicación para consultas interactivas:
```bash
python run.py
```

---

## Funcionamiento Interno

- **RAG (Recuperación Aumentada por Generación):**
    1. Los documentos se fragmentan y se convierten en embeddings vectoriales.
    2. Ante una consulta, se buscan los fragmentos más similares semánticamente.
    3. Los fragmentos recuperados sirven como contexto para generar una respuesta precisa.

- **Embeddings:**  
  El script `get_embedding.py` convierte texto en vectores usando el modelo configurado.

- **Base de datos Chroma:**  
  Almacena fragmentos, embeddings y metadatos (título, página, autor, etc.).

---

## Estructura de la base de datos

- Fragmentos de texto de los documentos
- Embeddings vectoriales
- Metadatos asociados

---

## Notas

- El proyecto está preparado para ser extendido con nuevas fuentes de datos y modelos de embeddings.
- Se recomienda mantener actualizadas las dependencias y proteger las credenciales en `.env`.

---

## Licencia

MIT
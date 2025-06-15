## Estructura del Proyecto

```
.env                   # Archivo de variables de entorno
.gitignore             # Configuración de Git para ignorar archivos
app.py                 # Aplicación principal
get_embedding.py       # Función para obtener embeddings
populate_database.py   # Script para poblar la base de datos
README.md              # Este archivo
requirements.txt       # Dependencias del proyecto
chroma/               # Directorio de la base de datos vectorial
data/                 # Directorio donde se almacenan los documentos PDF
```

## Requisitos

Para ejecutar este proyecto, necesitas:

1. Python 3.11 o superior
2. Las dependencias listadas en requirements.txt

## Instalación

1. Clona este repositorio:
```bash
git clone https://github.com/tu-usuario/rag-admision.git
cd rag-admision
```

2. Crea un entorno virtual e instala las dependencias:
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Crea un archivo .env en la raíz del proyecto con tus credenciales de API:
```
API_KEY=clave_api_google_ai_studio
```

## Uso

### Poblando la base de datos

Para agregar documentos PDF a la base de datos, colócalos en el directorio data y ejecuta:

```bash
python populate_database.py
```

Este script:
- Cargará los documentos PDF desde el directorio data
- Dividirá los documentos en fragmentos más pequeños
- Creará embeddings para cada fragmento
- Almacenará los fragmentos y sus embeddings en la base de datos Chroma

Si necesitas reiniciar la base de datos, puedes usar el parámetro `--reset`:

```bash
python populate_database.py --reset
```

### Ejecutando la aplicación

Para iniciar la aplicación principal:

```bash
python app.py [query]
```

La aplicación permitirá realizar consultas sobre los documentos almacenados utilizando procesamiento de lenguaje natural.

## Funcionamiento

El sistema utiliza un enfoque RAG (Recuperación Aumentada por Generación):

1. Los documentos se dividen en fragmentos y se convierten en embeddings vectoriales
2. Cuando se realiza una consulta, se buscan los fragmentos más similares semánticamente
3. Los fragmentos recuperados sirven como contexto para generar una respuesta más precisa

El script get_embedding.py proporciona la función para convertir texto en embeddings vectoriales utilizando el modelo especificado en la configuración (aquí generan los embeddings usando tu propia máquina).

## Estructura de la base de datos

La base de datos Chroma almacena:
- Los fragmentos de texto de los documentos
- Los embeddings vectoriales correspondientes
- Metadatos como el título del documento, número de página, autor, etc.



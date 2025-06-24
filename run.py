from app import app
import os

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=app.config.get("DEBUG", False), port=port)
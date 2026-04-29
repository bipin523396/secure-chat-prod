import os
import sys

# Ensure the 'api' directory is in the path so 'app' can be imported
sys.path.append(os.path.dirname(__file__))

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)



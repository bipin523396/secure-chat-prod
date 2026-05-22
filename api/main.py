from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "database": "connected",
        "version": "2.0.5"
    })

handler = app

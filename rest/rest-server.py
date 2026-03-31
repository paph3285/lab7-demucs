from flask import Flask, jsonify, request, send_file
import redis
import os
import json
import jsonpickle
import hashlib
import base64
from io import BytesIO
from minio import Minio

app = Flask(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

MINIO_HOST = os.environ.get("MINIO_HOST", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "rootpass123")

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

minio_client = Minio(
    MINIO_HOST,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

@app.route("/", methods=["GET"])
def home():
    return "<h1>Music Separation Server</h1><p>Server is running.</p>"

@app.route("/apiv1/queue", methods=["GET"])
def get_queue():
    try:
        queue_items = redis_client.lrange("toWorker", 0, -1)
        return jsonify({"queue": queue_items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/apiv1/separate", methods=["POST"])
def separate():
    try:
        raw_data = request.get_data()
        data = jsonpickle.decode(raw_data)

        if "mp3" not in data:
            return jsonify({"error": "Missing mp3 field"}), 400

        mp3_bytes = base64.b64decode(data["mp3"])
        songhash = hashlib.sha224(mp3_bytes).hexdigest()
        object_name = f"{songhash}.mp3"

        mp3_stream = BytesIO(mp3_bytes)
        minio_client.put_object(
            "queue",
            object_name,
            mp3_stream,
            length=len(mp3_bytes),
            content_type="audio/mpeg"
        )

        job = {
            "songhash": songhash,
            "bucket": "queue",
            "object_name": object_name,
            "model": data.get("model", "mdx_extra_q"),
            "callback": data.get("callback")
        }

        redis_client.lpush("toWorker", json.dumps(job))

        return jsonify({
            "hash": songhash,
            "reason": "Song enqueued for separation"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/apiv1/track/<songhash>/<track>", methods=["GET"])
def get_track(songhash, track):
    try:
        allowed = {"bass.mp3", "drums.mp3", "vocals.mp3", "other.mp3"}
        if track not in allowed:
            return jsonify({"error": "Invalid track name"}), 400

        object_name = f"{songhash}-{track}"
        response = minio_client.get_object("output", object_name)
        data = response.read()
        response.close()
        response.release_conn()

        return send_file(
            BytesIO(data),
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name=track
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/apiv1/remove/<songhash>/<track>", methods=["GET"])
def remove_track(songhash, track):
    try:
        allowed = {"bass.mp3", "drums.mp3", "vocals.mp3", "other.mp3"}
        if track not in allowed:
            return jsonify({"error": "Invalid track name"}), 400

        object_name = f"{songhash}-{track}"
        minio_client.remove_object("output", object_name)

        return jsonify({
            "removed": object_name,
            "bucket": "output"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

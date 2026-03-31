from flask import Flask, jsonify, request, send_file
import redis
import os
import json
import jsonpickle
import hashlib
import base64
import platform
from io import BytesIO
from minio import Minio

app = Flask(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

MINIO_HOST = os.environ.get("MINIO_HOST", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "rootpass123")

redis_client = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)

minio_client = Minio(
    MINIO_HOST,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

def log_info(message):
    try:
        redis_client.lpush("logging", f"{platform.node()}.rest.info:{message}")
    except Exception as e:
        print(f"Logging failed: {e}")

def log_debug(message):
    try:
        redis_client.lpush("logging", f"{platform.node()}.rest.debug:{message}")
    except Exception as e:
        print(f"Logging failed: {e}")

@app.route("/", methods=["GET"])
def hello():
    log_info("Health check requested")
    return "<h1>Music Separation Server</h1><p>Server is running.</p>"

@app.route("/apiv1/separate", methods=["POST"])
def separate():
    try:
        data = request.get_json(force=True)

        if "mp3" not in data:
            return jsonify({"error": "Missing mp3 field"}), 400

        mp3_b64 = data["mp3"]
        model = data.get("model", "mdx_extra_q")
        callback = data.get("callback", None)

        mp3_bytes = base64.b64decode(mp3_b64)
        songhash = hashlib.sha224(mp3_bytes).hexdigest()

        object_name = f"{songhash}.mp3"

        # store original mp3 in MinIO queue bucket
        mp3_stream = BytesIO(mp3_bytes)
        minio_client.put_object(
            "queue",
            object_name,
            mp3_stream,
            length=len(mp3_bytes),
            content_type="audio/mpeg"
        )

        # push work request into redis
        job = {
            "songhash": songhash,
            "bucket": "queue",
            "object_name": object_name,
            "model": model,
            "callback": callback
        }

        redis_client.lpush("toWorker", json.dumps(job))

        log_info(f"Received separate request for {songhash}")
        log_debug(f"Queued {object_name} in bucket queue")

        return jsonify({
            "hash": songhash,
            "reason": "Song enqueued for separation"
        })

    except Exception as e:
        log_info(f"Separate route error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/apiv1/queue", methods=["GET"])
def queue():
    try:
        q = redis_client.lrange("toWorker", 0, -1)
        log_debug("Queue inspection requested")
        return jsonify({"queue": q})
    except Exception as e:
        log_info(f"Queue route error: {e}")
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

        log_info(f"Track download requested: {songhash}-{track}")

        return send_file(
            BytesIO(data),
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name=track
        )

    except Exception as e:
        log_info(f"Track route error for {songhash}-{track}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/apiv1/remove/<songhash>/<track>", methods=["GET"])
def remove_track(songhash, track):
    try:
        allowed = {"bass.mp3", "drums.mp3", "vocals.mp3", "other.mp3"}
        if track not in allowed:
            return jsonify({"error": "Invalid track name"}), 400

        object_name = f"{songhash}-{track}"
        minio_client.remove_object("output", object_name)

        log_info(f"Track removed: {songhash}-{track}")

        return jsonify({
            "removed": object_name,
            "bucket": "output"
        })

    except Exception as e:
        log_info(f"Remove route error for {songhash}-{track}: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    log_info("REST server started")
    app.run(host="0.0.0.0", port=5001, debug=True)

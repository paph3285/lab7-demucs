import os
import json
import shutil
import subprocess
import redis
import platform
from minio import Minio

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

def log_info(message):
    try:
        redis_client.lpush("logging", f"{platform.node()}.worker.info:{message}")
    except Exception as e:
        print(f"Logging failed: {e}")

def log_debug(message):
    try:
        redis_client.lpush("logging", f"{platform.node()}.worker.debug:{message}")
    except Exception as e:
        print(f"Logging failed: {e}")

RUNTIME_DIR = os.path.abspath("worker_runtime")
INPUT_DIR = os.path.join(RUNTIME_DIR, "input")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")
MODELS_DIR = os.path.join(RUNTIME_DIR, "models")

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

print(f"Worker listening on Redis at {REDIS_HOST}:{REDIS_PORT}")
log_info("Worker started")

while True:
    item = redis_client.blpop("toWorker", timeout=0)
    if not item:
        continue

    queue_name, payload = item
    print(f"\nReceived job from {queue_name}")
    print(payload)

    songhash = "unknown"

    try:
        job = json.loads(payload)
        songhash = job["songhash"]
        bucket = job["bucket"]
        object_name = job["object_name"]
        model = job.get("model", "mdx_extra_q")

        log_info(f"Received job {songhash}")
        log_debug(f"Downloading {bucket}/{object_name}")

        local_mp3_path = os.path.join(INPUT_DIR, f"{songhash}.mp3")

        print(f"Downloading {bucket}/{object_name} -> {local_mp3_path}")
        minio_client.fget_object(bucket, object_name, local_mp3_path)
        print(f"Downloaded successfully: {local_mp3_path}")

        log_info(f"Running Demucs for {songhash}")
        print("Running Demucs...")

        command = [
            "docker", "run", "--rm",
            "--platform", "linux/amd64",
            "-v", f"{INPUT_DIR}:/data/input",
            "-v", f"{OUTPUT_DIR}:/data/output",
            "-v", f"{MODELS_DIR}:/data/models",
            "xserrat/facebook-demucs:latest",
            "python3", "-m", "demucs.separate",
            "--mp3",
            "--out", "/data/output",
            f"/data/input/{songhash}.mp3"
        ]

        result = subprocess.run(command, capture_output=True, text=True)

        print("Demucs stdout:")
        print(result.stdout)
        print("Demucs stderr:")
        print(result.stderr)

        if result.returncode != 0:
            raise RuntimeError(f"Demucs failed with return code {result.returncode}")

        stems = ["bass.mp3", "drums.mp3", "vocals.mp3", "other.mp3"]

        for stem in stems:
            local_track_path = os.path.join(
                OUTPUT_DIR, model, songhash, stem
            )
            output_object_name = f"{songhash}-{stem}"

            print(f"Uploading {local_track_path} -> output/{output_object_name}")
            log_debug(f"Uploading output/{output_object_name}")

            minio_client.fput_object("output", output_object_name, local_track_path)

        print(f"Finished processing {songhash}")
        log_info(f"Finished processing {songhash}")

    except Exception as e:
        print(f"Worker error: {e}")
        log_info(f"Worker error for {songhash}: {e}")

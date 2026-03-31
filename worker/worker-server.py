import os
import json
import subprocess
import redis
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

print(f"Worker listening on Redis at {REDIS_HOST}:{REDIS_PORT}")

while True:
    item = redis_client.blpop("toWorker", timeout=0)
    if not item:
        continue

    queue_name, payload = item
    print(f"\nReceived job from {queue_name}")
    print(payload)

    try:
        job = json.loads(payload)
        songhash = job["songhash"]
        bucket = job["bucket"]
        object_name = job["object_name"]

        base_dir = os.path.abspath("worker_runtime")
        input_dir = os.path.join(base_dir, "input")
        output_dir = os.path.join(base_dir, "output")
        models_dir = os.path.join(base_dir, "models")

        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(models_dir, exist_ok=True)

        local_input_path = os.path.join(input_dir, object_name)

        print(f"Downloading {bucket}/{object_name} -> {local_input_path}")
        minio_client.fget_object(bucket, object_name, local_input_path)
        print(f"Downloaded successfully: {local_input_path}")

        cmd = [
            "docker", "run", "--rm",
            "--platform", "linux/amd64",
            "--entrypoint", "python3",
            "-v", f"{input_dir}:/data/input",
            "-v", f"{output_dir}:/data/output",
            "-v", f"{models_dir}:/data/models",
            "xserrat/facebook-demucs:latest",
            "-m", "demucs.separate",
            "--mp3",
            "--out", "/data/output",
            f"/data/input/{object_name}"
        ]

        print("Running Demucs...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        print("Demucs stdout:")
        print(result.stdout)
        print("Demucs stderr:")
        print(result.stderr)

        if result.returncode != 0:
            raise RuntimeError(f"Demucs failed with return code {result.returncode}")

        stem_name = object_name.replace(".mp3", "")
        demucs_dir = os.path.join(output_dir, "mdx_extra_q", stem_name)

        tracks = ["bass.mp3", "drums.mp3", "vocals.mp3", "other.mp3"]

        for track in tracks:
            local_track_path = os.path.join(demucs_dir, track)
            output_object_name = f"{songhash}-{track}"
            print(f"Uploading {local_track_path} -> output/{output_object_name}")
            minio_client.fput_object("output", output_object_name, local_track_path)

        print(f"Finished processing {songhash}")

    except Exception as e:
        print(f"Worker error: {e}")

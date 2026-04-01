# Lab 7 Solution – Music Separation System (Kubernetes)

## Overview

In this project, I built a distributed music separation system using Kubernetes. The system allows a user to upload an MP3 file through a REST API, the file is processed by a worker using the Demucs model, and the separated audio tracks are stored in object storage. Redis is used for both the job queue and system logging.

The system consists of five main components:
- REST Server
- Redis
- MinIO
- Worker
- Logs Service

---

## Architecture Diagram

Client
   |
   v
REST API (Flask)
   |
   v
Redis Queue (toWorker)
   |
   v
Worker (Demucs)
   |
   v
MinIO (output bucket)
   |
   v
Client downloads tracks

Logging:
REST + Worker → Redis (logging) → Logs Service

---

## System Architecture

The workflow of the system works as follows:

1. A client sends an MP3 file to the REST API.
2. The REST server stores the MP3 file in the MinIO queue bucket.
3. The REST server pushes a job message onto a Redis queue called `toWorker`.
4. The Worker reads jobs from Redis.
5. The Worker downloads the MP3 file from the MinIO queue bucket.
6. The Worker runs the Demucs model to separate the audio into bass, drums, vocals, and other tracks.
7. The Worker uploads the separated tracks to the MinIO output bucket.
8. The Worker sends log messages to Redis.
9. The Logs service reads log messages from Redis and prints them so the system can be monitored.

---

## Components

### REST API (rest/)
The REST server is built using Flask and deployed in Kubernetes. It provides the following endpoints:

- POST /apiv1/separate  
  Accepts an MP3 file, stores it in the MinIO queue bucket, pushes a job to Redis, and returns a song hash.

- GET /apiv1/queue  
  Returns the current job queue.

- GET /apiv1/track/<songhash>/<track>  
  Downloads a separated track from the MinIO output bucket.

- GET /apiv1/remove/<songhash>/<track>  
  Removes a separated track from the MinIO output bucket.

The REST server is exposed using a Kubernetes Service and Ingress.

---

### Redis (redis/)
Redis is used for two main things:
- Job queue (toWorker)
- Logging queue (logging)

The worker continuously listens to the toWorker queue and processes jobs asynchronously.

---

### MinIO (minio/)
MinIO is used as object storage for the system.

Two buckets are used:
- queue → stores uploaded MP3 files waiting to be processed
- output → stores separated tracks (bass.mp3, drums.mp3, vocals.mp3, other.mp3)

---

### Worker (worker/)
The worker performs the main processing steps:

1. Reads a job from Redis
2. Downloads the MP3 from the MinIO queue bucket
3. Runs the Demucs model
4. Uploads separated tracks to the MinIO output bucket
5. Sends log messages to Redis

The worker can run inside Kubernetes or locally. For this project, the worker was run locally for development and testing.

---

### Logs Service (logs/)
The logs service reads messages from the Redis logging list and prints them. This allows monitoring of system activity such as job processing, downloads, uploads, and errors.

---

## Deployment Instructions (Kubernetes)

To deploy all components in Kubernetes:

kubectl apply -f redis/redis-deployment.yaml
kubectl apply -f redis/redis-service.yaml
kubectl apply -f minio/minio-deployment.yaml
kubectl apply -f minio/minio-service.yaml
kubectl apply -f rest/rest-deployment.yaml
kubectl apply -f rest/rest-service.yaml
kubectl apply -f rest/rest-ingress.yaml
kubectl apply -f logs/logs-deployment.yaml
kubectl apply -f worker/worker-deployment.yaml

---

## Local Development Setup (Running Worker Locally)

Because the Demucs model requires more compute and memory, I ran the worker locally while Redis, MinIO, REST, and Logs were running inside Kubernetes. To allow the local worker to communicate with the Kubernetes services, I used port forwarding.

First, I forwarded the Kubernetes services to my local machine:

kubectl port-forward service/redis 6379:6379
kubectl port-forward service/minio 9000:9000
kubectl port-forward service/rest 5003:5001

This allowed the local worker to connect to Redis on localhost:6379, MinIO on localhost:9000, and the REST server on localhost:5003.

Then I started the worker locally:

python3 worker/worker-server.py

After that, I submitted jobs through the REST API and the local worker picked up jobs from Redis, downloaded the MP3 from MinIO, ran Demucs, and uploaded the separated tracks back to the MinIO output bucket.

---

## Example Usage

Submit a job:

REST=localhost:5003 python3 short-sample-request.py

Check the queue:

curl http://localhost:5003/apiv1/queue

Download a track:

curl http://localhost:5003/apiv1/track/<songhash>/vocals.mp3 --output vocals.mp3

Remove a track:

curl http://localhost:5003/apiv1/remove/<songhash>/vocals.mp3

---

## Summary

This project demonstrates a distributed processing system using Kubernetes. The REST API handles incoming requests, Redis manages the job queue and logging, MinIO stores input and output files, and worker nodes perform the compute-intensive audio separation using Demucs. The system was tested end-to-end by uploading MP3 files, processing them, downloading separated tracks, and removing tracks from storage.

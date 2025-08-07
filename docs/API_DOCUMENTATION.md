# LiteStar Transcription API Documentation

This document describes the LiteStar-based transcription API exposed by the Chunkformer service. It covers available endpoints, request/response formats, examples, and error handling conventions.

References:

- Implementation: [`api.py`](api.py)
- Architecture & design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Introduction

The Transcription API provides endpoints for:

- Transcribing a single audio file synchronously.
- Submitting multiple audio files for asynchronous batch transcription.
- Polling the status and results of an asynchronous batch task.

Under the hood, the service initializes a speech recognition model at application startup and uses decoding utilities to produce text transcriptions from audio inputs.

## Endpoints

Base URL

- Default local development server: `http://localhost:8000`

The API exposes three routes:

1. POST /transcribe
2. POST /batch-transcribe
3. GET /transcribe/status/{task_id}

### 1) Transcribe a Single File

HTTP

- Method: POST
- URL: `/transcribe_audio/`

Description

- Transcribes a single audio file and returns the full transcription text as a single string.

Headers

- `Content-Type: multipart/form-data`
-

Request Body (multipart/form-data)

- `data`: file field containing the audio file (as implemented via parameter `data: UploadFile` in [`api.py`](api.py:32)).

Supported audio formats

- The file is saved and then passed to audio loading logic; typical WAV input is expected. Other formats depend on the capabilities of `load_audio()`.

Response

- Status: `200 OK`
- Body (JSON):
  {
  "status": "completed",
  "transcription": "The full transcribed text of the audio file as a single string."
  }

Notes

- The `transcription` field is never null on success; it contains the complete transcript returned by [`endless_decode()`](decode.py:1) as a string.

Error Responses

- `400 Bad Request`: No file provided.
  {
  "detail": "No file provided"
  }
- `500 Internal Server Error`: Unexpected server-side error (details from exception message).
  {
  "detail": "error message"
  }

Example (curl)

- Upload a single WAV file:
  curl -X POST http://localhost:8000/transcribe_audio/ \
   -H "
  -F "data=@tests/test1.wav"

Successful response:
{
"status": "completed",
"transcription": "hello world, this is a complete example transcription from start to finish."
}

### 2) Batch Transcribe Multiple Files (Asynchronous)

HTTP

- Method: POST
- URL: `/batch-transcribe`

Description

- Accepts multiple files, starts background processing, and immediately returns a `task_id`. Use the status endpoint to retrieve task status and results.

Headers

- `Content-Type: multipart/form-data`
- `

Request Body (multipart/form-data)

- `files`: one or more file fields containing the audio files (as implemented via parameter `files: List[UploadFile]` in [`api.py`](api.py:72)).

Response (Accepted)

- Status: `202 Accepted`
- Body (JSON):
  {
  "task_id": "a_unique_task_id"
  }

Processing Model

- Tasks are processed asynchronously in a background task (see `process_batch_files()`).
- Results are stored in-memory in `task_store` during this reference implementation. For production, replace with persistent storage per [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Error Responses

- `400 Bad Request`: No files provided.
  {
  "detail": "No files provided"
  }
- `500 Internal Server Error`: Unexpected error while enqueuing/initializing processing.
  {
  "detail": "error message"
  }

Example (curl)

- Submit two WAV files for batch processing:
  curl -X POST http://localhost:8000/batch-transcribe \
   -H "
  -F "files=@tests/test1.wav" \
   -F "files=@tests/test2.wav"

Accepted response:
{
"task_id": "c69e9b5e-9a0d-4f1a-9b83-2b83a0f0b7e1"
}

### 3) Get Batch Transcription Status

HTTP

- Method: GET
- URL: `/transcribe/status/{task_id}`

Description

- Retrieves the current status and, if completed, the results for a batch transcription task.

Headers

- `

Path Parameters

- `task_id` (string): A unique identifier previously returned by `/batch-transcribe`.

Response (Success)

- Status: `200 OK`
- Body (JSON):
  {
  "status": "completed" | "pending" | "processing" | "failed",
  "results": [
  { "filename": "test1.wav", "transcription": "..." },
  { "filename": "test2.wav", "transcription": "..." }
  ],
  "errors": [ "error text if any" ]
  }

Notes

- The exact shape returned by the implementation is the task object stored under `task_store[task_id]` in [`api.py`](api.py:151-158). When completed successfully:
  - `status`: "completed"
  - `results`: array of file results, each containing `filename` and `transcription`
  - `errors`: array of error messages accumulated during processing (may be empty)
- For failed tasks:
  - `status`: "failed"
  - `errors`: populated with error messages
  - `results`: may be empty or partial depending on failure timing

Error Responses

- `404 Not Found`: Task not found for the provided `task_id`.
  {
  "detail": "Task not found"
  }

Example (curl)

- Poll for task status:
  curl -X GET "http://localhost:8000/transcribe/status/c69e9b5e-9a0d-4f1a-9b83-2b83a0f0b7e1" \
   -H "

Successful completed response:
{
"status": "completed",
"results": [
{ "filename": "test1.wav", "transcription": "..." },
{ "filename": "test2.wav", "transcription": "..." }
],
"errors": []
}

## Request and Response Details

Content Types

- Single file and batch endpoints expect `multipart/form-data` uploads.

Field Names

- Single file: use form field `data` for the file.
- Batch: use repeated form field `files` for each file.

Response Encoding

- All responses are JSON.

Status Codes Summary

- 200 OK: Successful synchronous transcription or successful status retrieval.
- 202 Accepted: Batch request accepted; task created.
- 400 Bad Request: Missing or invalid request fields.
- 401 Unauthorized: Missing or invalid API key (per design).
- 404 Not Found: Unknown `task_id`.
- 500 Internal Server Error: Unexpected server error.

## Error Handling

The API follows a consistent error response structure with a message in the JSON body. Depending on the framework handler, the key may be `detail` for exceptions raised by handlers.

Common Error Scenarios

- 400 Bad Request
  - Single file: no file uploaded (`data` missing or filename empty).
  - Batch: no files uploaded (`files` missing or empty).
- 401 Unauthorized
  - Missing or invalid `X-API-Key` (enforce via middleware or gateway).
- 404 Not Found
  - `task_id` does not exist in server-side store.
- 500 Internal Server Error
  - Unhandled exceptions during I/O, decoding, or processing.

Typical Error Payloads

- 400:
  {
  "detail": "No file provided"
  }

- 401:
  {
  "error": "Invalid or missing API key"
  }

- 404:
  {
  "detail": "Task not found"
  }

- 500:
  {
  "detail": "A descriptive error message"
  }

## Operational Notes

Model Initialization

- On startup, the server loads the ASR model with environment variable `MODEL_CHECKPOINT` defaulting to `model`. Ensure the model directory is present and readable before starting the server.

Performance and Limits

- Batch processing in this reference uses an in-process background task and in-memory store; for production deployments, use a proper task queue (e.g., Celery) and persistent storage as outlined in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Security

- Enforce API key checking at the edge (API gateway) or add request validation middleware to verify `X-API-Key` on each request.

## Configuration

Model checkpoint path

- The server can load the ASR model from a custom checkpoint directory specified via the environment variable `MODEL_CHECKPOINT_PATH`. When unset, the service falls back to its internal default.
- This option is resolved during application startup in [`api.py`](api.py:1).

Run examples

- Unix/macOS (bash/zsh):
  MODEL_CHECKPOINT_PATH="/absolute/or/relative/path/to/checkpoints" uvicorn api:app --reload

- Windows (PowerShell):
  $env:MODEL_CHECKPOINT_PATH="C:\path\to\checkpoints"; uvicorn api:app --reload

Notes

- Ensure the provided path exists and contains the expected model files as produced by training or packaging workflows.
- If you are using a Python virtual environment, activate it first before launching uvicorn.

## Examples

Single file transcription

- Request:
  curl -X POST http://localhost:8000/transcribe \
   -H "
  -F "data=@tests/test1.wav"

- Example success response:
  {
  "transcription": "hello world"
  }

Batch transcription

- Request:
  curl -X POST http://localhost:8000/batch-transcribe \
   -H "
  -F "files=@tests/test1.wav" \
   -F "files=@tests/test2.wav"

- Accepted response:
  {
  "task_id": "4c8e62a8-7c2e-4d8b-8db7-5f9f2f2c3b1a"
  }

Poll batch status

- Request:
  curl -X GET "http://localhost:8000/transcribe/status/4c8e62a8-7c2e-4d8b-8db7-5f9f2f2c3b1a" \
   -H "

- Example completed response:
  {
  "status": "completed",
  "results": [
  { "filename": "test1.wav", "transcription": "..." },
  { "filename": "test2.wav", "transcription": "..." }
  ],
  "errors": []
  }

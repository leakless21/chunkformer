import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from litestar.testing import TestClient

# Add the parent directory to the path to import api
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock decode module before importing api
sys.modules['decode'] = MagicMock()
sys.modules['decode'].init = MagicMock(return_value=("dummy_model", {"a": 1}))
sys.modules['decode'].load_audio = MagicMock(return_value="dummy_audio")
sys.modules['decode'].endless_decode = MagicMock(return_value="dummy transcription")
sys.modules['decode'].batch_decode = MagicMock()

import api


def setup_dummy_environment(monkeypatch, tmp_path: Path):
    """Patch heavy or I/O bound functions with lightweight stubs and set required env vars."""
    # Ensure the model checkpoint directory exists so startup does not fail
    checkpoint_dir = tmp_path / "model"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MODEL_CHECKPOINT", str(checkpoint_dir))


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Yield a Litestar TestClient with heavy operations stubbed out."""
    setup_dummy_environment(monkeypatch, tmp_path)

    with TestClient(app=api.app) as client:  # startup will run with patched functions
        yield client


def test_transcribe_audio_success(client):
    """Uploading a single audio file should return a dummy transcription."""
    # The multipart field name should match the function parameter name "data"
    response = client.post(
        "/transcribe_audio/",
        files={"data": ("sample.wav", b"fakebytes", "audio/wav")}
    )
    assert response.status_code == 201  # POST endpoints typically return 201 (Created)
    assert response.json() == {"transcription": "dummy transcription"}


def test_transcribe_audio_no_file(client):
    """Sending the request without a file should raise a 400."""
    response = client.post("/transcribe_audio/", files={})
    assert response.status_code == 400


def test_batch_transcription_flow(client, monkeypatch, tmp_path):
    """End-to-end happy path for batch transcription: upload -> poll -> completed."""

    async def immediate_process(task_id, files):
        # Directly mark as completed without async processing
        api.task_store[task_id]["status"] = "completed"
        api.task_store[task_id]["results"] = [
            {"filename": f.filename or "file.wav", "transcription": "dummy transcription"}
            for f in files
        ]

    monkeypatch.setattr(api, "process_batch_files", immediate_process)

    # Single fake file upload (repeatable for multiple files)
    files = [("data", ("sample1.wav", b"fakebytes", "audio/wav"))]
    upload_resp = client.post("/batch-transcribe", files=files)
    assert upload_resp.status_code == 201  # POST endpoints typically return 201 (Created)
    task_id = upload_resp.json()["task_id"]

    # Immediately poll status – should already be completed due to patched processor
    poll_resp = client.get(f"/task-status/{task_id}")
    assert poll_resp.status_code == 200
    body = poll_resp.json()

    assert body["status"] == "completed"
    assert body["results"] and body["results"][0]["transcription"] == "dummy transcription"
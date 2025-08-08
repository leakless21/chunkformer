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
    body = response.json()
    assert isinstance(body, dict)
    assert "transcription" in body
    assert body["transcription"] == "dummy transcription"
def test_transcribe_audio_segments_structure(client, monkeypatch):
    """
    Verify that the single-file transcription endpoint returns a list of segments,
    with each segment containing start, end, and decode keys with correct types.
    """
    # Make endless_decode return a list of segments with numeric start/end and string decode
    segments = [
        {"start": 0.0, "end": 1.25, "decode": "hello"},
        {"start": 1.25, "end": 2.5, "decode": "world"},
    ]
    monkeypatch.setattr(api, "endless_decode", lambda *args, **kwargs: segments)

    response = client.post(
        "/transcribe_audio/",
        files={"data": ("sample.wav", b"fakebytes", "audio/wav")}
    )
    assert response.status_code == 201

    body = response.json()
    # 1) Response is list of dicts (transcription key contains the list)
    assert isinstance(body, dict)
    assert "transcription" in body
    assert isinstance(body["transcription"], list)
    assert all(isinstance(seg, dict) for seg in body["transcription"])

    # 2) Each dict contains start, end, decode
    for seg in body["transcription"]:
        assert set(["start", "end", "decode"]).issubset(seg.keys())

    # 3) Types: start/end are numbers, decode is string
    for seg in body["transcription"]:
        assert isinstance(seg["start"], (int, float))
        assert isinstance(seg["end"], (int, float))
        assert isinstance(seg["decode"], str)


def test_batch_transcription_segments_structure(client, monkeypatch, tmp_path):
    """
    Verify that the batch transcription status payload returns segments per file with the
    correct structure and types when processing is completed.
    """
    # Patch background processor to immediately mark task as completed with segments
    async def immediate_process(task_id, files):
        api.task_store[task_id]["status"] = "completed"
        api.task_store[task_id]["results"] = [
            {
                "filename": f.filename or "file.wav",
                "segments": [
                    {"start": 0, "end": 2, "decode": "foo"},
                    {"start": 2.0, "end": 4.5, "decode": "bar"},
                ],
            }
            for f in files
        ]

    monkeypatch.setattr(api, "process_batch_files", immediate_process)

    files = [("data", ("sample1.wav", b"fakebytes", "audio/wav"))]
    upload_resp = client.post("/batch-transcribe", files=files)
    assert upload_resp.status_code == 201
    task_id = upload_resp.json()["task_id"]

    poll_resp = client.get(f"/task-status/{task_id}")
    assert poll_resp.status_code == 200
    body = poll_resp.json()

    assert body["status"] == "completed"
    assert isinstance(body["results"], list)
    assert len(body["results"]) >= 1
    first = body["results"][0]
    # results should contain segments list
    assert "segments" in first
    assert isinstance(first["segments"], list)
    assert all(isinstance(seg, dict) for seg in first["segments"])

    for seg in first["segments"]:
        assert set(["start", "end", "decode"]).issubset(seg.keys())
        assert isinstance(seg["start"], (int, float))
        assert isinstance(seg["end"], (int, float))
        assert isinstance(seg["decode"], str)


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
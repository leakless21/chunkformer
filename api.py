import os
import uuid
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from litestar import Litestar, get, post, delete
from litestar.datastructures import UploadFile
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_200_OK, HTTP_202_ACCEPTED, HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR
from litestar.params import Body
from litestar.enums import RequestEncodingType
from typing import Annotated

from decode import init, load_audio, endless_decode, batch_decode
import torch


# Global variables to store the model and character dictionary
model = None
char_dict = None
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Cache directory configuration
CACHE_DIR = Path(os.getenv("CHUNKFORMER_CACHE_DIR", "./cache"))
AUDIO_CACHE_DIR = CACHE_DIR / "audio"
TSV_CACHE_DIR = CACHE_DIR / "tsv"

# In-memory storage for batch tasks (replace with a database in production)
task_store: Dict[str, Dict] = {}

def ensure_cache_directories():
    """Ensure cache directories exist."""
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TSV_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def cleanup_old_cache_files(max_age_hours: int = 24):
    """Clean up cache files older than max_age_hours."""
    import time
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    for cache_dir in [AUDIO_CACHE_DIR, TSV_CACHE_DIR]:
        if cache_dir.exists():
            for file_path in cache_dir.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        try:
                            file_path.unlink()
                            print(f"Cleaned up old cache file: {file_path}")
                        except Exception as e:
                            print(f"Failed to clean up {file_path}: {e}")

def create_temp_audio_file(content: bytes, filename: str) -> Path:
    """Create a temporary audio file in the cache directory."""
    file_extension = Path(filename).suffix
    temp_filename = f"{uuid.uuid4()}{file_extension}"
    temp_path = AUDIO_CACHE_DIR / temp_filename
    
    with open(temp_path, 'wb') as f:
        f.write(content)
    
    return temp_path

def startup_handler() -> None:
    """Initialize the model on application startup."""
    global model, char_dict
    
    # Initialize cache directories
    ensure_cache_directories()
    print(f"Cache directories initialized at {CACHE_DIR}")
    
    # Clean up old cache files
    cleanup_old_cache_files()
    
    # Load model
    model_checkpoint = os.getenv("MODEL_CHECKPOINT", "chunkformer-large-vie")
    if not os.path.isdir(model_checkpoint):
        raise FileNotFoundError(f"Model checkpoint directory not found at {model_checkpoint}")
    model, char_dict = init(model_checkpoint, device)
    print(f"Model loaded from {model_checkpoint} on {device}")

@post("/transcribe_audio/")
async def transcribe_file(data: Annotated[UploadFile, Body(media_type=RequestEncodingType.MULTI_PART)]) -> Dict:
    """Transcribe a single audio file."""
    if not data.filename:
        raise HTTPException(detail="No file provided", status_code=HTTP_400_BAD_REQUEST)

    tmp_file_path = None
    try:
        # Save uploaded file to cache directory
        content = await data.read()
        tmp_file_path = create_temp_audio_file(content, data.filename)

        # Load and transcribe the audio
        audio = load_audio(str(tmp_file_path))
        
        # Create a dummy args object for endless_decode
        class Args:
            long_form_audio = str(tmp_file_path)
            chunk_size = 64
            left_context_size = 128
            right_context_size = 128
            total_batch_duration = 1800

        args = Args()
        
        # Get the transcription
        transcription = endless_decode(args, model, char_dict)
        
        # Clean up the temporary file
        tmp_file_path.unlink()

        return {"transcription": transcription}

    except Exception as e:
        # Clean up the temporary file in case of error
        if tmp_file_path and tmp_file_path.exists():
            tmp_file_path.unlink()
        raise HTTPException(detail=str(e), status_code=HTTP_500_INTERNAL_SERVER_ERROR)

@post("/batch-transcribe")
async def batch_transcribe_files(data: Annotated[List[UploadFile], Body(media_type=RequestEncodingType.MULTI_PART)]) -> Dict:
    """Transcribe multiple audio files asynchronously."""
    if not data:
        raise HTTPException(detail="No files provided", status_code=HTTP_400_BAD_REQUEST)

    task_id = str(uuid.uuid4())
    task_store[task_id] = {
        "status": "pending",
        "results": [],
        "errors": []
    }

    # In a real application, you would use a task queue like Celery
    # For this example, we'll process the files in the background
    import asyncio
    asyncio.create_task(process_batch_files(task_id, data))

    return {"task_id": task_id}

async def process_batch_files(task_id: str, files: List[UploadFile]) -> None:
    """Process batch transcription in the background."""
    global task_store
    task_store[task_id]["status"] = "processing"

    temp_files = []
    tsv_file_path = None
    try:
        # Save uploaded files to cache directory
        for file in files:
            content = await file.read()
            temp_file_path = create_temp_audio_file(content, file.filename)
            temp_files.append(temp_file_path)

        # Create a TSV file in the cache directory
        tsv_filename = f"batch_{task_id}.tsv"
        tsv_file_path = TSV_CACHE_DIR / tsv_filename
        
        # Create a dummy args object for batch_decode
        class Args:
            audio_list = str(tsv_file_path)
            chunk_size = 64
            left_context_size = 128
            right_context_size = 128
            total_batch_duration = 1800

        args = Args()
        
        # Create TSV file with the paths to the audio files
        tsv_content = "wav\n" + "\n".join(str(f) for f in temp_files)
        with open(tsv_file_path, "w") as f:
            f.write(tsv_content)

        # Get the transcriptions
        batch_decode(args, model, char_dict)

        # Read the results from the TSV file
        import pandas as pd
        df = pd.read_csv(tsv_file_path, sep="\t")
        results = []
        for _, row in df.iterrows():
            results.append({
                "filename": Path(row["wav"]).name,
                "transcription": row.get("decode", "")
            })
        
        task_store[task_id]["status"] = "completed"
        task_store[task_id]["results"] = results

    except Exception as e:
        task_store[task_id]["status"] = "failed"
        task_store[task_id]["errors"].append(str(e))
    finally:
        # Clean up temporary files
        for tmp_file_path in temp_files:
            try:
                if tmp_file_path.exists():
                    tmp_file_path.unlink()
            except Exception as cleanup_error:
                print(f"Failed to clean up {tmp_file_path}: {cleanup_error}")
        
        # Clean up TSV file
        if tsv_file_path and tsv_file_path.exists():
            try:
                tsv_file_path.unlink()
            except Exception as cleanup_error:
                print(f"Failed to clean up TSV file {tsv_file_path}: {cleanup_error}")

@get("/task-status/{task_id:str}")
async def get_task_status(task_id: str) -> Dict:
    """Get the status of a batch transcription task."""
    if task_id not in task_store:
        raise HTTPException(detail="Task not found", status_code=HTTP_404_NOT_FOUND)

    return task_store[task_id]

@post("/cache/cleanup")
async def cleanup_cache() -> Dict:
    """Manually trigger cache cleanup."""
    try:
        cleanup_old_cache_files()
        return {"message": "Cache cleanup completed successfully"}
    except Exception as e:
        raise HTTPException(detail=f"Cache cleanup failed: {str(e)}", status_code=HTTP_500_INTERNAL_SERVER_ERROR)

@get("/cache/status")
async def get_cache_status() -> Dict:
    """Get cache directory status and usage."""
    try:
        cache_status = {
            "cache_directory": str(CACHE_DIR),
            "audio_cache_directory": str(AUDIO_CACHE_DIR),
            "tsv_cache_directory": str(TSV_CACHE_DIR),
            "cache_exists": CACHE_DIR.exists(),
            "audio_files_count": len(list(AUDIO_CACHE_DIR.glob("*"))) if AUDIO_CACHE_DIR.exists() else 0,
            "tsv_files_count": len(list(TSV_CACHE_DIR.glob("*"))) if TSV_CACHE_DIR.exists() else 0,
        }
        
        # Calculate total cache size
        total_size = 0
        if CACHE_DIR.exists():
            for file_path in CACHE_DIR.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        
        cache_status["total_cache_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        return cache_status
    except Exception as e:
        raise HTTPException(detail=f"Failed to get cache status: {str(e)}", status_code=HTTP_500_INTERNAL_SERVER_ERROR)

app = Litestar(
    route_handlers=[transcribe_file, batch_transcribe_files, get_task_status, cleanup_cache, get_cache_status],
    on_startup=[startup_handler],
)

def main():
    """Main entry point for the API server."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()
import uuid
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

from litestar import Litestar, get, post, delete
from litestar.datastructures import UploadFile
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_200_OK, HTTP_202_ACCEPTED, HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR
from litestar.params import Body
from litestar.enums import RequestEncodingType
from typing import Annotated
from loguru import logger

from decode import init, load_audio, endless_decode, batch_decode
import torch
from model.utils.config import config


# Global variables to store the model and character dictionary
model = None
char_dict = None
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Cache directory configuration
CACHE_DIR = Path(config['cache']['dir'])
AUDIO_CACHE_DIR = CACHE_DIR / "audio"
TSV_CACHE_DIR = CACHE_DIR / "tsv"

# In-memory storage for batch tasks (replace with a database in production)
task_store: Dict[str, Dict] = {}

def ensure_cache_directories():
    """Ensure cache directories exist."""
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TSV_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def cleanup_old_cache_files(max_age_hours: int = config['cache']['max_age_hours']):
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
                            logger.info(f"Cleaned up old cache file: {file_path}")
                        except Exception as e:
                            logger.error(f"Failed to clean up {file_path}: {e}")

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
    import os
    global model, char_dict

    # Avoid heavy initialization in the uvicorn reloader parent process.
    # When uvicorn --reload is used, a parent "reloader" process is created that
    # imports the app, then spawns the actual worker process with RUN_MAIN="true".
    # Initializing torch/model in the reloader can leak semaphores on shutdown.
    run_main = os.environ.get("RUN_MAIN") == "true" or os.environ.get("WATCHFILES_RELOADER") == "true"

    # Initialize cache directories
    ensure_cache_directories()
    logger.info(f"Cache directories initialized at {CACHE_DIR}")

    # Clean up old cache files
    cleanup_old_cache_files()

    if not run_main:
        logger.warning("Detected uvicorn reload parent process; skipping model initialization to prevent semaphore leaks. "
                       "Model will be initialized only in the main worker process.")
        return

    # Load model only in the main worker
    model_checkpoint = config['model']['checkpoint']
    if not Path(model_checkpoint).is_dir():
        raise FileNotFoundError(f"Model checkpoint directory not found at {model_checkpoint}")
    model, char_dict = init(model_checkpoint, device)
    logger.info(f"Model loaded from {model_checkpoint} on {device}")

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
            chunk_size = config['model']['chunk_size']
            left_context_size = config['model']['left_context_size']
            right_context_size = config['model']['right_context_size']
            total_batch_duration = config['model']['total_batch_duration']

        args = Args()
        
        # Get the transcription
        transcription = endless_decode(args, model, char_dict)
        
        # Clean up the temporary file
        tmp_file_path.unlink()

        return {"transcription": transcription, "timestamp": datetime.now(timezone.utc).isoformat()}

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
        "errors": [],
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

    # In a real application, you would use a task queue like Celery
    # For this example, we'll process the files in the background
    import asyncio
    asyncio.create_task(process_batch_files(task_id, data))

    return {"task_id": task_id, "timestamp": datetime.now(timezone.utc).isoformat()}

async def process_batch_files(task_id: str, files: List[UploadFile]) -> None:
    """Process batch transcription in the background."""
    global task_store
    task_store[task_id]["status"] = "processing"
    task_store[task_id]["last_updated"] = datetime.now(timezone.utc).isoformat()

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
            chunk_size = config['model']['chunk_size']
            left_context_size = config['model']['left_context_size']
            right_context_size = config['model']['right_context_size']
            total_batch_duration = config['model']['total_batch_duration']

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
        task_store[task_id]["last_updated"] = datetime.now(timezone.utc).isoformat()

    except Exception as e:
        task_store[task_id]["status"] = "failed"
        task_store[task_id]["errors"].append(str(e))
        task_store[task_id]["last_updated"] = datetime.now(timezone.utc).isoformat()
    finally:
        # Clean up temporary files
        for tmp_file_path in temp_files:
            try:
                if tmp_file_path.exists():
                    tmp_file_path.unlink()
            except Exception as cleanup_error:
                logger.error(f"Failed to clean up {tmp_file_path}: {cleanup_error}")
        
        # Clean up TSV file
        if tsv_file_path and tsv_file_path.exists():
            try:
                tsv_file_path.unlink()
            except Exception as cleanup_error:
                logger.error(f"Failed to clean up TSV file {tsv_file_path}: {cleanup_error}")

@get("/task-status/{task_id:str}")
async def get_task_status(task_id: str) -> Dict:
    """Get the status of a batch transcription task."""
    if task_id not in task_store:
        raise HTTPException(detail="Task not found", status_code=HTTP_404_NOT_FOUND)

    return {**task_store[task_id], "timestamp": datetime.now(timezone.utc).isoformat()}

@post("/cache/cleanup")
async def cleanup_cache() -> Dict:
    """Manually trigger cache cleanup."""
    try:
        cleanup_old_cache_files()
        return {"message": "Cache cleanup completed successfully", "timestamp": datetime.now(timezone.utc).isoformat()}
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
        
        cache_status["total_cache_size_mb"] = round(total_size / (1024 * 1022), 2)
        
        return {**cache_status, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(detail=f"Failed to get cache status: {str(e)}", status_code=HTTP_500_INTERNAL_SERVER_ERROR)



import atexit

def _cleanup_resources():
    # Placeholder for future explicit cleanup if needed
    # (e.g., closing torch multiprocessing pools or shared memory)
    try:
        logger.info("Shutting down API - cleanup hook executed")
    except Exception:
        pass

atexit.register(_cleanup_resources)

app = Litestar(
    route_handlers=[transcribe_file, batch_transcribe_files, get_task_status, cleanup_cache, get_cache_status],
    on_startup=[startup_handler],
    request_max_body_size=100 * 1024 * 1024,  # 100 MB
)

def main():
    """Main entry point for the API server."""
    import uvicorn
    uvicorn.run(app, host=config['api']['host'], port=config['api']['port'])

if __name__ == "__main__":
    main()
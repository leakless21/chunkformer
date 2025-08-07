import argparse
import os
import subprocess
import sys
import questionary
from loguru import logger
from model.utils.logging import setup_logger

def run_decode_command(args):
    """
    Constructs and runs the decode.py command with the given arguments.
    """
    command = [sys.executable, "decode.py"]
    command.extend(["--model_checkpoint", args.model_checkpoint])
    command.extend(["--total_batch_duration", str(args.total_batch_duration)])
    command.extend(["--chunk_size", str(args.chunk_size)])
    command.extend(["--left_context_size", str(args.left_context_size)])
    command.extend(["--right_context_size", str(args.right_context_size)])
    if args.device:
        command.extend(["--device", args.device])
    if args.autocast_dtype:
        command.extend(["--autocast_dtype", args.autocast_dtype])
    if args.full_attn:
        command.append("--full_attn")

    if args.mode == "single":
        command.extend(["--long_form_audio", args.long_form_audio])
    else:  # batch mode
        command.extend(["--audio_list", args.audio_list])

    logger.info("Executing command: {}", " ".join(command))
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        if process.stdout:
            for line in process.stdout:
                logger.info(line.rstrip())
        process.wait()
        if process.returncode != 0:
            logger.error("Command failed with exit code {}", process.returncode)
        else:
            logger.success("Command executed successfully.")
    except FileNotFoundError:
        logger.error("Error: decode.py not found. Make sure you are running this script from the project root.")
    except Exception as e:
        logger.error("An error occurred: {}", e)

def main():
    """
    Main function to run the CLI questionnaire.
    """
    setup_logger('development')
    # Mode Selection
    mode = questionary.select(
        "Select transcription mode:",
        choices=["Single File Transcription", "Batch Transcription"]
    ).ask()

    # Argument Collection
    args = argparse.Namespace()
    args.mode = "single" if mode == "Single File Transcription" else "batch"

    # Required arguments
    args.model_checkpoint = questionary.text(
        "Path to the model checkpoint:",
        default="chunkformer-large-vie"
    ).ask()
    while not os.path.isdir(args.model_checkpoint):
        logger.error("Error: Model checkpoint path '{}' not found or is not a directory.", args.model_checkpoint)
        args.model_checkpoint = questionary.text(
            "Path to the model checkpoint:",
            default="chunkformer-large-vie"
        ).ask()

    if args.mode == "single":
        args.long_form_audio = questionary.path("Path to the long-form audio file:").ask()
        while not os.path.isfile(args.long_form_audio):
            logger.error("Error: Audio file '{}' not found.", args.long_form_audio)
            args.long_form_audio = questionary.path("Path to the long-form audio file:").ask()
        args.audio_list = None
    else:  # batch mode
        args.audio_list = questionary.path("Path to the TSV file containing audio list:").ask()
        while not os.path.isfile(args.audio_list):
            logger.error("Error: Audio list TSV file '{}' not found.", args.audio_list)
            args.audio_list = questionary.path("Path to the TSV file containing audio list:").ask()
        args.long_form_audio = None

    # Optional arguments
    args.total_batch_duration = questionary.text(
        "Total batch duration (in seconds, default: 1800):",
        default="1800"
    ).ask()
    args.total_batch_duration = int(args.total_batch_duration)

    args.chunk_size = questionary.text(
        "Chunk size (default: 64):",
        default="64"
    ).ask()
    args.chunk_size = int(args.chunk_size)

    args.left_context_size = questionary.text(
        "Left context size (default: 128):",
        default="128"
    ).ask()
    args.left_context_size = int(args.left_context_size)

    args.right_context_size = questionary.text(
        "Right context size (default: 128):",
        default="128"
    ).ask()
    args.right_context_size = int(args.right_context_size)
    
    device_options = ["cuda", "cpu"]
    # Check for CUDA availability as a hint, but let user choose
    if os.path.exists("/usr/local/cuda") or os.path.exists("/opt/cuda"):
         device_options.insert(0, "cuda") # Ensure cuda is first if available
    else:
         device_options.insert(0, "cpu") # Ensure cpu is first if cuda not obviously available

    args.device = questionary.select(
        "Select device (default: cuda if available else cpu):",
        choices=device_options,
        default=device_options[0]
    ).ask()

    autocast_options = ["fp32", "bf16", "fp16", "None"]
    autocast_choice = questionary.select(
        "Select autocast data type (default: None):",
        choices=autocast_options,
        default="None"
    ).ask()
    args.autocast_dtype = None if autocast_choice == "None" else autocast_choice
    
    args.full_attn = questionary.confirm(
        "Use full attention with caching? (default: False)",
        default=False
    ).ask()

    logger.info("\n--- Configuration Summary ---")
    logger.info("Mode: {}", mode)
    logger.info("Model Checkpoint: {}", args.model_checkpoint)
    if args.mode == "single":
        logger.info("Long Form Audio: {}", args.long_form_audio)
    else:
        logger.info("Audio List: {}", args.audio_list)
    logger.info("Total Batch Duration: {}", args.total_batch_duration)
    logger.info("Chunk Size: {}", args.chunk_size)
    logger.info("Left Context Size: {}", args.left_context_size)
    logger.info("Right Context Size: {}", args.right_context_size)
    logger.info("Device: {}", args.device)
    logger.info("Autocast Dtype: {}", args.autocast_dtype)
    logger.info("Full Attention: {}", args.full_attn)
    logger.info("---------------------------\n")

    if questionary.confirm("Proceed with transcription?", default=True).ask():
        run_decode_command(args)
    else:
        logger.info("Transcription cancelled.")

if __name__ == "__main__":
    main()
# ChunkFormer: Masked Chunking Conformer For Long-Form Speech Transcription

---

This repository contains the implementation and supplementary materials for our ICASSP 2025 paper, **"ChunkFormer: Masked Chunking Conformer For Long-Form Speech Transcription"**. The paper has been fully accepted by the reviewers with scores: **4/4/4**.

[![Ranked #1: Speech Recognition on Common Voice Vi](https://img.shields.io/badge/Ranked%20%231%3A%20Speech%20Recognition%20on%20Common%20Voice%20Vi-%F0%9F%8F%86%20SOTA-blueviolet?style=for-the-badge&logo=paperswithcode&logoColor=white)](https://paperswithcode.com/sota/speech-recognition-on-common-voice-vi)
[![Ranked #1: Speech Recognition on VIVOS](https://img.shields.io/badge/Ranked%20%231%3A%20Speech%20Recognition%20on%20VIVOS-%F0%9F%8F%86%20SOTA-blueviolet?style=for-the-badge&logo=paperswithcode&logoColor=white)](https://paperswithcode.com/sota/speech-recognition-on-vivos)

- [`paper.pdf`](docs/paper.pdf): The ICASSP 2025 paper describing ChunkFormer.
- [`reviews.pdf`](docs/chunkformer_reviews.pdf): Reviewers' feedback from the ICASSP review process.
- [`rebuttal.pdf`](docs/rebuttal.pdf): Our rebuttal addressing reviewer concerns.

## Table of Contents

- [Introduction](#introduction)
- [Key Features](#key-features)
- [Installation](#installation)
- [Usage](#usage)
  - [Command-Line Interface (CLI)](#command-line-interface-cli)
  - [API Server](#api-server)
  - [Manual Execution](#manual-execution)
- [Citation](#citation)
- [Acknowledgments](#acknowledgments)

<a name = "introduction" ></a>

## Introduction

ChunkFormer is an ASR model designed for processing long audio inputs effectively on low-memory GPUs. It uses a **chunk-wise processing mechanism** with **relative right context** and employs the **Masked Batch technique** to minimize memory waste due to padding. The model is scalable, robust, and optimized for both streaming and non-streaming ASR scenarios.
![chunkformer_architecture](docs/chunkformer_architecture.png)

<a name = "key-features" ></a>

## Key Features

- **Transcribing Extremely Long Audio**: ChunkFormer can **transcribe audio recordings up to 16 hours** in length with results comparable to existing models. It is currently the first model capable of handling this duration.
- **Efficient Decoding on Low-Memory GPUs**: Chunkformer can **handle long-form transcription on GPUs with limited memory** without losing context or mismatching the training phase.
- **Masked Batching Technique**: ChunkFormer efficiently **removes the need for padding in batches with highly variable lengths**. For instance, **decoding a batch containing audio clips of 1 hour and 1 second costs only 1 hour + 1 second of computational and memory usage, instead of 2 hours due to padding.**

| GPU Memory | Total Batch Duration (minutes) |
| ---------- | ------------------------------ |
| 80GB       | 980                            |
| 24GB       | 240                            |

<a name = "installation" ></a>

## Installation

#### Checkpoints

| Language   | Model                                                                                                     |
| ---------- | --------------------------------------------------------------------------------------------------------- |
| Vietnamese | [khanhld/chunkformer-large-vie](https://huggingface.co/khanhld/chunkformer-large-vie)                     |
| English    | [khanhld/chunkformer-large-en-libri-960h](https://huggingface.co/khanhld/chunkformer-large-en-libri-960h) |

#### Dependencies

To run the implementation, ensure you have an environment with PyTorch working and the following dependencies installed:

```bash
pip install -r requirements.txt
```

<a name = "usage" ></a>

## Usage

This project provides three ways to transcribe audio files:

1.  **Command-Line Interface (CLI)**: An interactive CLI for a user-friendly experience.
2.  **API Server**: A RESTful API for programmatic access to the transcription service.
3.  **Manual Execution**: Direct execution of the `decode.py` script for more control over the transcription process.

### Command-Line Interface (CLI)

For a more user-friendly experience, you can use the interactive CLI to guide you through the transcription process. To run the CLI, use the following command:

```bash
uv run chunkformer
```

The CLI will prompt you to select the transcription mode (single file or batch) and enter the necessary parameters.

### API Server

This project includes a RESTful API for transcribing audio files. To run the API server, use the following command:

```bash
uv run api
```

The API server will be available at `http://localhost:8080`. You can use the following endpoints to transcribe audio files:

*   `POST /transcribe_audio/`: Transcribe a single audio file.
*   `POST /batch-transcribe`: Transcribe multiple audio files asynchronously.
*   `GET /task-status/{task_id}`: Get the status of a batch transcription task.

For more detailed information about the API, you can access the auto-generated documentation:

*   **Swagger UI**: [http://localhost:8080/schema/swagger](http://localhost:8080/schema/swagger)
*   **Redoc**: [http://localhost:8080/schema/redoc](http://localhost:8080/schema/redoc)
*   **Stoplight Elements**: [http://localhost:8080/schema/elements](http://localhost:8080/schema/elements)

### Manual Execution

You can also run the `decode.py` script directly for more control over the transcription process.

#### Long-Form Audio Testing

To test the model with a single [long-form audio file](data/common_voice_vi_23397238.wav). Audio file extensions ".mp3", ".wav", ".flac", ".m4a", ".aac" are accepted:

```bash
python decode.py \
    --model_checkpoint path/to/local/hf/checkpoint/repo \
    --long_form_audio path/to/audio.wav \
    --total_batch_duration 14400 \ #in second, default is 1800
    --chunk_size 64 \
    --left_context_size 128 \
    --right_context_size 128
```

Example Output:

```
[00:00:01.200] - [00:00:02.400]: this is a transcription example
[00:00:02.500] - [00:00:03.700]: testing the long-form audio
```

#### Batch Transcription Testing

The [audio_list.tsv](data/audio_list.tsv) file must have at least one column named **wav**. Optionally, a column named **txt** can be included to compute the **Word Error Rate (WER)**. Output will be saved to the same file.

```bash
python decode.py \
    --model_checkpoint path/to/local/hf/checkpoint/repo \
    --audio_list path/to/audio_list.tsv \
    --total_batch_duration 14400 \ #in second, default is 1800
    --chunk_size 64 \
    --left_context_size 128 \
    --right_context_size 128
```

Example Output:

```
WER: 0.1234
```

<a name = "citation" ></a>

## Citation

If you use this work in your research, please cite:

```bibtex
@INPROCEEDINGS{10888640,
  author={Le, Khanh and Ho, Tuan Vu and Tran, Dung and Chau, Duc Thanh},
  booktitle={ICASSP 2025 - 2025 IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)},
  title={ChunkFormer: Masked Chunking Conformer For Long-Form Speech Transcription},
  year={2025},
  volume={},
  number={},
  pages={1-5},
  keywords={Scalability;Memory management;Graphics processing units;Signal processing;Performance gain;Hardware;Resource management;Speech processing;Standards;Context modeling;chunkformer;masked batch;long-form transcription},
  doi={10.1109/ICASSP49660.2025.10888640}}

```

<a name = "acknowledgments" ></a>

## Acknowledgments

We would like to thank Zalo for providing resources and support for training the model. This work was completed during my tenure at Zalo.

This implementation is based on the WeNet framework. We extend our gratitude to the WeNet development team for providing an excellent foundation for speech recognition research and development.
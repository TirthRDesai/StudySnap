# PDF to Flashcards Generator - Setup Guide

## Overview

This project converts PDF documents into flashcards using LanceDB for vector
storage and Ollama for embeddings and generation.

## Prerequisites

-   Python 3.8+
-   Ollama installed with custom models directory at `D:\OllamaModels`
-   Required models:
    -   `llama3:8b` (for flashcard generation)
    -   `mxbai-embed-large` (for embeddings)

## Project Structure

```
StudentHelper/
├── main.py                 # Main pipeline class (PDFToFlashcardPipeline)
├── setup_ollama.py        # Setup script for Ollama environment
├── requirements.txt       # Python dependencies
├── pipeline/
│   ├── PDFReader.py       # PDF processing and chunking
│   └── FlashcardGenerator.py  # Flashcard generation from chunks
├── Tests/
│   └── test.pdf           # Sample PDF for testing
├── chunks-storage/        # LanceDB vector database
└── output/                # Generated flashcards output
```

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Verify Ollama Setup

Your Ollama models are stored in:

-   `D:\OllamaModels\manifests\registry.ollama.ai\library\llama3\8b`
-   `D:\OllamaModels\manifests\registry.ollama.ai\library\mxbai-embed-large\latest`

The main.py automatically configures the environment variables to use this
directory.

### 3. (Optional) Set Permanent Environment Variables

```bash
python setup_ollama.py --permanent
```

This will set `OLLAMA_HOME` and `OLLAMA_MODELS` for your user account
permanently.

## Usage

### Basic Usage (Default Configuration)

```bash
python main.py
```

This will:

1. Process `Tests/test.pdf`
2. Chunk the text and create embeddings
3. Generate flashcards using 4 different queries
4. Save outputs to the `output/` folder

### Advanced Usage (Custom Configuration)

```python
from main import PDFToFlashcardPipeline

# Create pipeline with custom settings
pipeline = PDFToFlashcardPipeline(
    pdf_path="path/to/your/document.pdf",
    embedding_model="mxbai-embed-large",
    generation_model="llama3",
    db_path="./chunks-storage",
    chunk_size=500,           # words per chunk
    chunk_overlap=100,        # overlapping words
    k_chunks=5,               # retrieve 5 chunks per query
    num_flashcards_per_chunk=10
)

# Run the pipeline
pipeline.run()
```

## Configuration

The `PDFToFlashcardPipeline` class has the following configurable parameters:

| Parameter                  | Default             | Description                      |
| -------------------------- | ------------------- | -------------------------------- |
| `pdf_path`                 | `Tests/test.pdf`    | Path to the PDF file             |
| `embedding_model`          | `mxbai-embed-large` | Ollama embedding model           |
| `generation_model`         | `llama3`            | Ollama generation model          |
| `db_path`                  | `./chunks-storage`  | LanceDB database location        |
| `table_name`               | `book_chunks`       | LanceDB table name               |
| `chunk_size`               | `400`               | Words per text chunk             |
| `chunk_overlap`            | `80`                | Overlapping words between chunks |
| `k_chunks`                 | `3`                 | Chunks to retrieve per query     |
| `num_flashcards_per_chunk` | `5`                 | Flashcards per chunk             |

## Output Files

After running the pipeline, the following files are generated in the `output/`
folder:

-   `flashcards_YYYYMMDD_HHMMSS.json` - Flashcards in JSON format
-   `summary_YYYYMMDD_HHMMSS.txt` - Generation summary and configuration

## Troubleshooting

### Ollama Connection Error

If you get "connection refused" errors:

1. Ensure Ollama is running
2. Check that environment variables are set:
    ```powershell
    $env:OLLAMA_HOME
    $env:OLLAMA_MODELS
    ```
3. Verify models are available:
    ```bash
    ollama list
    ```

### Model Not Found Error

If models aren't found:

1. Verify models exist at `D:\OllamaModels`
2. Run `setup_ollama.py` to configure environment
3. Restart your terminal/IDE

### PDF Processing Issues

-   Ensure the PDF file exists and is readable
-   Check that the path is relative to the project root or use absolute paths

## Classes and Methods

### PDFToFlashcardPipeline

Main orchestration class with the following methods:

-   `__init__(**kwargs)` - Initialize with optional custom configuration
-   `process_pdf()` - Process PDF and create embeddings
-   `generate_flashcards()` - Generate flashcards from chunks
-   `save_outputs(flashcards)` - Save results to files
-   `run()` - Execute complete pipeline

### PDFProcessor

Handles PDF processing with methods:

-   `extract_text_from_pdf()` - Extract text from PDF
-   `chunk_text(text)` - Split text into chunks
-   `embed_texts_ollama(texts)` - Create embeddings
-   `store_chunks_lancedb(chunks, embeddings)` - Store in LanceDB
-   `semantic_search(query)` - Search for similar chunks
-   `process_pdf(chunk_size, chunk_overlap)` - Complete pipeline

### FlashcardGenerator

Generates flashcards with methods:

-   `retrieve_chunks_by_query(query, k)` - Get relevant chunks
-   `generate_flashcards_from_chunks(chunks)` - Create flashcards
-   `generate_flashcards_from_query(query, k, num_cards)` - End-to-end
    generation
-   `save_flashcards(flashcards, output_file)` - Save to JSON
-   `display_flashcards(flashcards)` - Print to console

## Requirements

See `requirements.txt` for all dependencies:

-   pypdf
-   pandas
-   lancedb
-   ollama

## License

MIT

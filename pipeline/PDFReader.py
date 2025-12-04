import os
from typing import List

from pypdf import PdfReader
import pandas as pd
import lancedb
import ollama


class PDFProcessor:
    """
    A class to handle PDF processing, text chunking, embedding generation,
    and semantic search using LanceDB and Ollama.
    """

    def __init__(
        self,
        pdf_path: str = "Tests/test.pdf",
        embedding_model: str = "mxbai-embed-large:latest",
        db_path: str = "./chunks-storage",
        table_name: str = "book_chunks"
    ):
        """
        Initialize the PDFProcessor.

        Args:
            pdf_path: Path to the PDF file to process
            embedding_model: Ollama model to use for embeddings
            db_path: Path to the LanceDB database directory
            table_name: Name of the LanceDB table
        """
        self.pdf_path = pdf_path
        self.embedding_model = embedding_model
        self.db_path = db_path
        self.table_name = table_name

    def extract_text_from_pdf(self) -> str:
        """Extracts all text from the PDF file."""
        reader = PdfReader(self.pdf_path)
        all_text = []

        for page_num, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
                if text:
                    all_text.append(text)
            except Exception as e:
                print(f"Error reading page {page_num}: {e}")

        return "\n".join(all_text)

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[str]:
        """
        Simple text chunking: splits long text into overlapping chunks.

        Args:
            text: The text to chunk
            chunk_size: Number of words per chunk
            chunk_overlap: Number of overlapping words between chunks

        Returns:
            A list of text chunks
        """
        words = text.split()
        chunks = []
        start = 0

        while start < len(words):
            end = start + chunk_size
            chunk_words = words[start:end]
            chunk = " ".join(chunk_words)
            chunks.append(chunk)
            # move cursor with overlap
            start += chunk_size - chunk_overlap

        return chunks

    def embed_texts_ollama(self, texts: List[str]):
        """
        Gets embeddings from an Ollama model for a list of texts.

        Args:
            texts: List of texts to embed

        Returns:
            A list of embedding vectors
        """
        embeddings = []
        for i, txt in enumerate(texts):
            print(f"Embedding chunk {i+1}/{len(texts)}...")
            response = ollama.embeddings(
                model=self.embedding_model, prompt=txt)
            embeddings.append(response["embedding"])
        return embeddings

    def store_chunks_lancedb(self, chunks: List[str], embeddings):
        """
        Stores chunk texts + embeddings into LanceDB.
        Creates the table with the correct schema on first run,
        then appends on later runs.

        Args:
            chunks: List of text chunks
            embeddings: List of embedding vectors
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) lengths do not match")

        db = lancedb.connect(self.db_path)

        # Build DataFrame with real data so Lance can infer proper schema
        df = pd.DataFrame({
            "text": chunks,                  # string column
            "vector": embeddings,            # list[float] column
            "source": [self.pdf_path] * len(chunks),
            "chunk_index": list(range(len(chunks)))
        })

        if self.table_name in db.table_names():
            print(f"Table '{self.table_name}' exists – appending rows...")
            table = db.open_table(self.table_name)
            table.add(df)
        else:
            print(f"Table '{self.table_name}' does not exist – creating it...")
            table = db.create_table(self.table_name, df)

        print(
            f"Stored {len(chunks)} chunks in LanceDB table '{self.table_name}'.")

    def semantic_search(self, query: str, k: int = 5):
        """
        Retrieves similar chunks from LanceDB based on a query.
        Embeds query with Ollama and searches for k most similar chunks.

        Args:
            query: The search query
            k: Number of results to return

        Returns:
            A pandas DataFrame with search results
        """
        db = lancedb.connect(self.db_path)
        table = db.open_table(self.table_name)

        # Embed query
        q_emb = ollama.embeddings(model=self.embedding_model, prompt=query)[
            "embedding"]

        results = (
            table.search(q_emb)
            .metric("cosine")
            .nprobes(10)
            .limit(k)
            .to_pandas()
        )

        return results

    def process_pdf(self, chunk_size: int = 400, chunk_overlap: int = 80):
        """
        Complete pipeline: extract text, chunk, embed, and store in LanceDB.

        Args:
            chunk_size: Number of words per chunk
            chunk_overlap: Number of overlapping words between chunks
        """
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF not found at: {self.pdf_path}")

        print("📖 Extracting text from PDF...")
        full_text = self.extract_text_from_pdf()
        print(f"Total characters: {len(full_text)}")

        print("✂️ Chunking text...")
        chunks = self.chunk_text(
            full_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        print(f"Created {len(chunks)} chunks.")

        print("🧠 Creating embeddings with Ollama...")
        embeddings = self.embed_texts_ollama(chunks)

        print("💾 Storing in LanceDB...")
        self.store_chunks_lancedb(chunks, embeddings)

        print("✅ Done! Your book is now indexed with LanceDB.")


if __name__ == "__main__":
    # Create a processor instance with default configuration
    processor = PDFProcessor(
        pdf_path="Tests/test.pdf",
        embedding_model="mxbai-embed-large",
        db_path="./chunks-storage",
        table_name="book_chunks"
    )

    # Run the complete pipeline
    processor.process_pdf(chunk_size=400, chunk_overlap=80)

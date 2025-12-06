"""
Main script to read PDF, process it, and generate flashcards.
Outputs are saved to the 'output' folder.
"""

from dotenv import load_dotenv
import json
from typing import List, Dict
import os
import sys
from datetime import datetime
from pathlib import Path

from pipeline.FlashcardGenerator import FlashcardGenerator
from pipeline.PDFReader import PDFProcessor
from pipeline.QuizGenerator import QuizGenerator

# Add pipeline to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pipeline"))


class PDFToFlashcardPipeline:
    """
    A pipeline class that orchestrates PDF processing and flashcard generation.
    """

    # ---------- CONFIG ----------
    PDF_PATH = "Tests/test.pdf"                      # path to your uploaded book
    EMBEDDING_MODEL = "mxbai-embed-large:latest"            # Ollama embedding model
    GENERATION_MODEL = "llama3:8b"                      # Ollama generation model
    DB_PATH = "./chunks-storage"                     # folder for LanceDB
    TABLE_NAME = "book_chunks"                       # LanceDB table name
    CHUNK_SIZE = 400                                 # words per chunk
    CHUNK_OVERLAP = 80                               # overlapping words between chunks
    # number of chunks to retrieve per query
    K_CHUNKS = 3
    # flashcards to generate per chunk
    NUM_FLASHCARDS_PER_CHUNK = 5
    # quiz questions to generate
    NUM_QUIZ_QUESTIONS = 10
    # set to True to request CUDA device
    USE_CUDA = False
    # ----------------------------

    def __init__(
        self,
        pdf_path: str = None,
        embedding_model: str = None,
        generation_model: str = None,
        db_path: str = None,
        table_name: str = None,
        chunk_size: int = None,
        chunk_overlap: int = None,
        k_chunks: int = None,
        num_flashcards_per_chunk: int = None,
        num_quiz_questions: int = None,
        use_cuda: bool = None
    ):
        """
        Initialize the pipeline with optional custom configuration.

        Args:
            pdf_path: Path to the PDF file
            embedding_model: Ollama embedding model name
            generation_model: Ollama generation model name
            db_path: Path to LanceDB database
            table_name: LanceDB table name
            chunk_size: Words per chunk
            chunk_overlap: Overlapping words between chunks
            k_chunks: Number of chunks to retrieve per query
            num_flashcards_per_chunk: Flashcards to generate per chunk
            num_quiz_questions: Quiz questions to generate
            use_cuda: Whether to use CUDA device
        """
        self.pdf_path = pdf_path or self.PDF_PATH
        self.embedding_model = embedding_model or self.EMBEDDING_MODEL
        self.generation_model = generation_model or self.GENERATION_MODEL
        self.db_path = db_path or self.DB_PATH
        self.table_name = table_name or self.TABLE_NAME
        self.chunk_size = chunk_size or self.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or self.CHUNK_OVERLAP
        self.k_chunks = k_chunks or self.K_CHUNKS
        self.num_flashcards_per_chunk = num_flashcards_per_chunk or self.NUM_FLASHCARDS_PER_CHUNK
        self.num_quiz_questions = num_quiz_questions or self.NUM_QUIZ_QUESTIONS
        self.use_cuda = use_cuda if use_cuda is not None else self.USE_CUDA
        self.output_dir = self._create_output_directory()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _create_output_directory(self) -> Path:
        """Create the output directory if it doesn't exist."""
        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(exist_ok=True)
        return output_dir

    def process_pdf(self) -> bool:
        """
        Process the PDF file and create embeddings.

        Returns:
            True if successful, False otherwise
        """
        print("Step 1: Processing PDF...")
        print("-" * 70)

        try:
            processor = PDFProcessor(
                pdf_path=self.pdf_path,
                embedding_model=self.embedding_model,
                db_path=self.db_path,
                table_name=self.table_name
            )
            processor.process_pdf(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap
            )
            print("✅ PDF processing complete!\n")
            return True
        except Exception as e:
            print(f"❌ Error processing PDF: {e}")
            return False

    def generate_flashcards(self) -> List[Dict[str, str]]:
        """
        Generate flashcards from the processed PDF chunks.

        Returns:
            A list of generated flashcards
        """
        print("Step 2: Generating Flashcards...")
        print("-" * 70)

        try:
            gen_kwargs = {'device': 'cuda'} if self.use_cuda else {}
            generator = FlashcardGenerator(
                db_path=self.db_path,
                table_name=self.table_name,
                embedding_model=self.embedding_model,
                generation_model=self.generation_model,
                generate_kwargs=gen_kwargs
            )

            # Define queries to generate flashcards from
            queries = [
                "What are the main concepts and topics covered?",
                "What are the key definitions and terms?",
                "What are the important facts and information?",
                "What are the relationships and connections between ideas?"
            ]

            all_flashcards = []

            for i, query in enumerate(queries, 1):
                print(
                    f"\nGenerating flashcards for query {i}/{len(queries)}: '{query}'")
                flashcards = generator.generate_flashcards_from_query(
                    query=query,
                    k=self.k_chunks,
                    num_cards=self.num_flashcards_per_chunk
                )
                all_flashcards.extend(flashcards)

            print(f"\n✅ Generated {len(all_flashcards)} total flashcards!\n")

            # Display flashcards
            generator.display_flashcards(all_flashcards)

            return all_flashcards

        except Exception as e:
            print(f"❌ Error generating flashcards: {e}")
            return []

    def generate_quiz(self) -> List[Dict]:
        """
        Generate quiz questions from the processed PDF chunks.

        Returns:
            A list of generated quiz questions
        """
        print("Step 3: Generating Quiz...")
        print("-" * 70)

        try:
            gen_kwargs = {'device': 'cuda'} if self.use_cuda else {}
            quiz_gen = QuizGenerator(
                db_path=self.db_path,
                table_name=self.table_name,
                embedding_model=self.embedding_model,
                generation_model=self.generation_model,
                generate_kwargs=gen_kwargs
            )

            # Define query to generate quiz from
            query = "Create a comprehensive quiz covering all major topics and concepts"

            print(f"\nGenerating {self.num_quiz_questions} quiz questions...")
            questions = quiz_gen.generate_quiz_from_query(
                query=query,
                num_questions=self.num_quiz_questions,
                k=self.k_chunks
            )

            print(f"\n✅ Generated {len(questions)} quiz questions!\n")

            # Display quiz (teacher view with answers)
            quiz_gen.display_quiz(questions)

            return questions

        except Exception as e:
            print(f"❌ Error generating quiz: {e}")
            return []

    def save_outputs(self, flashcards: List[Dict[str, str]], quiz_questions: List[Dict] = None, namespace: str = "output") -> List[Path]:
        """
        Save flashcards, quiz, and summary to output folder.

        Args:
            flashcards: List of flashcards to save
            quiz_questions: List of quiz questions to save (optional)

        Returns:
            List of saved file paths (Path objects)
        """
        try:
            generator = FlashcardGenerator(
                db_path=self.db_path,
                table_name=self.table_name,
                embedding_model=self.embedding_model,
                generation_model=self.generation_model
            )

            # Save flashcards to output folder
            output_file = self.output_dir / f"flashcards_{namespace}.json"
            generator.save_flashcards(flashcards, output_file=str(output_file))

            # Save quiz if provided
            saved_files = [output_file]
            if quiz_questions:
                quiz_gen = QuizGenerator(
                    db_path=self.db_path,
                    table_name=self.table_name,
                    embedding_model=self.embedding_model,
                    generation_model=self.generation_model
                )

                quiz_file = self.output_dir / f"quiz_{namespace}.json"
                quiz_gen.save_quiz(quiz_questions, output_file=str(quiz_file))
                saved_files.append(quiz_file)

                answer_key_file = self.output_dir / \
                    f"answer_key_{namespace}.txt"
                quiz_gen.generate_answer_key(
                    quiz_questions, output_file=str(answer_key_file))
                saved_files.append(answer_key_file)

                student_quiz_file = self.output_dir / \
                    f"quiz_student_{self.timestamp}.txt"
                import io
                from contextlib import redirect_stdout
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    quiz_gen.display_quiz_student_view(quiz_questions)
                with open(student_quiz_file, "w", encoding="utf-8") as f:
                    f.write(buffer.getvalue())
                saved_files.append(student_quiz_file)

            # Save summary
            summary_file = self.output_dir / f"summary_{namespace}.txt"
            self._save_summary(summary_file, len(flashcards), len(
                quiz_questions) if quiz_questions else 0)
            saved_files.append(summary_file)

            print(f"\n📁 Output files saved to: {self.output_dir}")
            for file_path in saved_files:
                print(f"   - {file_path.name}")

            return saved_files

        except Exception as e:
            print(f"❌ Error saving outputs: {e}")
            return []

    def remove_outputs(self, output_files: List[Path]):
        """
        Remove output files from local storage.

        Args:
            output_files: List of file Paths to remove
        """
        for file_path in output_files:
            try:
                if file_path.exists():
                    file_path.unlink()
                    print(f"🗑️  Removed file: {file_path.name}")
            except Exception as e:
                print(f"⚠️  Could not remove file {file_path.name}: {e}")

    def _save_summary(self, file_path: Path, num_flashcards: int, num_quiz_questions: int = 0):
        """
        Save a summary of the generation process.

        Args:
            file_path: Path to save the summary
            num_flashcards: Number of flashcards generated
            num_quiz_questions: Number of quiz questions generated
        """
        quiz_section = ""
        if num_quiz_questions > 0:
            quiz_section = f"\nTotal Quiz Questions: {num_quiz_questions}"

        summary = f"""PDF Processing and Content Generation Summary
=============================================

Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Source PDF: {self.pdf_path}
Total Flashcards: {num_flashcards}{quiz_section}

Configuration:
- PDF Path: {self.pdf_path}
- Embedding Model: {self.embedding_model}
- Generation Model: {self.generation_model}
- Database Path: {self.db_path}
- Table Name: {self.table_name}
- Chunk Size: {self.chunk_size} words
- Chunk Overlap: {self.chunk_overlap} words
- Chunks Retrieved per Query: {self.k_chunks}
- Flashcards per Chunk: {self.num_flashcards_per_chunk}
- Quiz Questions: {self.num_quiz_questions}
"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(summary)
        except Exception as e:
            print(f"Warning: Could not save summary: {e}")

    def run(self, include_quiz: bool = False) -> bool:
        """
        Run the complete pipeline: PDF processing and flashcard/quiz generation.

        Args:
            include_quiz: Whether to also generate quiz questions (default: False)

        Returns:
            True if successful, False otherwise
        """
        print("\n" + "="*70)
        if include_quiz:
            print("📚 PDF to Flashcards & Quiz Generator")
        else:
            print("📚 PDF to Flashcards Generator")
        print("="*70 + "\n")

        # Process PDF
        if not self.process_pdf():
            return False

        # Generate flashcards
        flashcards = self.generate_flashcards()
        if not flashcards:
            print("❌ No flashcards were generated.")
            return False

        # Generate quiz if requested
        quiz_questions = []
        if include_quiz:
            quiz_questions = self.generate_quiz()
            if not quiz_questions:
                print(
                    "⚠️  No quiz questions were generated, but continuing with flashcards.")

        # Save outputs
        if not self.save_outputs(flashcards, quiz_questions if quiz_questions else None):
            return False

        print("\n" + "="*70)
        print("✨ Process Complete!")
        print("="*70 + "\n")

        return True


# Configure if needed (Ollama in a different location, etc.)
# Load environment variables from .env
load_dotenv()

# Configure Ollama environment
OLLAMA_BIN = os.getenv('OLLAMA_BIN')
OLLAMA_MODELS_DIR = os.getenv('OLLAMA_MODELS_DIR')

# Set environment variables
os.environ['OLLAMA_HOME'] = OLLAMA_MODELS_DIR
os.environ['OLLAMA_MODELS'] = OLLAMA_MODELS_DIR

# Add Ollama to PATH
ollama_dir = str(Path(OLLAMA_BIN).parent)
if ollama_dir not in os.environ.get('PATH', ''):
    os.environ['PATH'] = ollama_dir + os.pathsep + os.environ.get('PATH', '')

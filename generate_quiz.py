#!/usr/bin/env python
"""
Quiz Generator Script - generates quiz questions from existing chunks.
Run this after running main.py to process a PDF.
"""


from pipeline.QuizGenerator import QuizGenerator
import os
import sys
from datetime import datetime
from pathlib import Path

# Configure Ollama environment with custom models directory
OLLAMA_MODELS_DIR = r"D:\OllamaModels"
os.environ['OLLAMA_HOME'] = OLLAMA_MODELS_DIR
os.environ['OLLAMA_MODELS'] = OLLAMA_MODELS_DIR

# Add Ollama to PATH
ollama_dir = r"C:\Users\tirth\AppData\Local\Programs\Ollama"
if ollama_dir not in os.environ.get('PATH', ''):
    os.environ['PATH'] = ollama_dir + os.pathsep + os.environ.get('PATH', '')

# Add pipeline to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pipeline"))

# NOW import QuizGenerator after path is setup


def create_output_directory():
    """Create the output directory if it doesn't exist."""
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def main():
    """Generate quiz questions from processed PDF chunks."""

    output_dir = create_output_directory()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("\n" + "="*70)
    print("📝 Quiz Generator")
    print("="*70 + "\n")

    try:
        quiz_gen = QuizGenerator(
            db_path="./chunks-storage",
            table_name="book_chunks",
            embedding_model="mxbai-embed-large:latest",
            generation_model="llama3:8b"
        )

        # Define query to generate quiz from
        query = "Create a comprehensive quiz covering all major topics and concepts"

        print(f"Generating 10 quiz questions...")
        questions = quiz_gen.generate_quiz_from_query(
            query=query,
            num_questions=10,
            k=3  # retrieve 3 chunks
        )

        print(f"\n✅ Generated {len(questions)} quiz questions!\n")

        # Display quiz (teacher view with answers)
        quiz_gen.display_quiz(questions)

        # Save quiz
        quiz_file = output_dir / f"quiz_{timestamp}.json"
        quiz_gen.save_quiz(questions, output_file=str(quiz_file))

        # Save answer key
        answer_key_file = output_dir / f"answer_key_{timestamp}.txt"
        quiz_gen.generate_answer_key(
            questions, output_file=str(answer_key_file))

        # Also save a student view (without answers)
        student_quiz_file = output_dir / f"quiz_student_{timestamp}.txt"
        with open(student_quiz_file, "w", encoding="utf-8") as f:
            # Redirect stdout temporarily to capture quiz display
            import io
            from contextlib import redirect_stdout

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                quiz_gen.display_quiz_student_view(questions)

            f.write(buffer.getvalue())

        print(f"\n📁 Output files saved to: {output_dir}")
        print(f"   - {quiz_file.name}")
        print(f"   - {answer_key_file.name}")
        print(f"   - {student_quiz_file.name}")

        print("\n" + "="*70)
        print("✨ Quiz Generation Complete!")
        print("="*70 + "\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

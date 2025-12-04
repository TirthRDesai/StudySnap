import json
import re
from typing import List, Dict, Optional
from enum import Enum
import lancedb
import ollama


class DifficultyLevel(Enum):
    """Difficulty levels for quiz questions."""
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"


class QuizGenerator:
    """
    A class to generate quizzes from text chunks retrieved from LanceDB
    using the Ollama llama3 model.
    """

    def __init__(
        self,
        db_path: str = "./chunks-storage",
        table_name: str = "book_chunks",
        embedding_model: str = "mxbai-embed-large:latest",
        generation_model: str = "llama3:8b",
        generate_kwargs: Optional[Dict] = None
    ):
        """
        Initialize the QuizGenerator.

        Args:
            db_path: Path to the LanceDB database directory
            table_name: Name of the LanceDB table
            embedding_model: Ollama model to use for embeddings
            generation_model: Ollama model to use for quiz generation
            generate_kwargs: Extra kwargs to pass to ollama.generate (e.g., device='cuda')
        """
        self.db_path = db_path
        self.table_name = table_name
        self.embedding_model = embedding_model
        self.generation_model = generation_model
        self.generate_kwargs = generate_kwargs or {}

    def retrieve_chunks_by_query(self, query: str, k: int = 5) -> List[str]:
        """
        Retrieve relevant chunks from LanceDB based on a query.

        Args:
            query: The search query
            k: Number of chunks to retrieve

        Returns:
            A list of relevant text chunks
        """
        try:
            db = lancedb.connect(self.db_path)
            table = db.open_table(self.table_name)

            # Embed query
            q_emb = ollama.embeddings(model=self.embedding_model, prompt=query)[
                "embedding"]

            # Search for similar chunks
            results = (
                table.search(q_emb)
                .metric("cosine")
                .nprobes(10)
                .limit(k)
                .to_pandas()
            )

            # Extract text from results
            chunks = results["text"].tolist()
            return chunks
        except Exception as e:
            print(f"Error retrieving chunks: {e}")
            return []

    def generate_quiz_from_chunks(
        self,
        chunks: List[str],
        num_questions: int = 10
    ) -> List[Dict]:
        """
        Generate quiz questions from a list of text chunks using llama3.

        Args:
            chunks: List of text chunks to generate quiz from
            num_questions: Number of quiz questions to generate

        Returns:
            A list of quiz questions with multiple choice options and difficulty level
        """
        questions = []
        # Calculate questions per chunk, rounding up to ensure we reach target
        # This way if we want 10 questions and have 3 chunks, we ask for 4 per chunk (3*4=12, then trim to 10)
        import math
        questions_per_chunk = max(
            1, math.ceil(num_questions / len(chunks))) if chunks else 0

        for i, chunk in enumerate(chunks):
            print(
                f"Generating quiz questions from chunk {i+1}/{len(chunks)}...")

            # Create a prompt for quiz generation
            prompt = f"""Based on the following text, create exactly {questions_per_chunk} multiple choice quiz questions.
Each question should have:
- A clear question text
- 4 answer options (A, B, C, D)
- The correct answer letter
- A difficulty level (Easy, Medium, or Hard)

Return the response in the following JSON format ONLY:
[
  {{
    "question": "What is...?",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct_answer": "A",
    "difficulty": "Easy"
  }},
  {{
    "question": "How does...?",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct_answer": "B",
    "difficulty": "Medium"
  }}
]

Text:
{chunk}

JSON Array:"""

            try:
                # Call ollama.generate with optional kwargs
                try:
                    response = ollama.generate(
                        model=self.generation_model,
                        prompt=prompt,
                        stream=False,
                        **self.generate_kwargs
                    )
                except TypeError as te:
                    # Some clients don't accept certain kwargs (e.g., device)
                    msg = str(te)
                    if "unexpected keyword argument 'device'" in msg or "device" in msg:
                        # retry without device key
                        kwargs = {
                            k: v for k, v in self.generate_kwargs.items() if k != 'device'}
                        if kwargs != self.generate_kwargs:
                            print(
                                "  Note: 'device' arg not supported by ollama client; retrying without it.")
                            response = ollama.generate(
                                model=self.generation_model,
                                prompt=prompt,
                                stream=False,
                                **kwargs
                            )
                        else:
                            raise
                    else:
                        raise

                response_text = (response.get("response") or "").strip()

                if not response_text:
                    print(f"  Warning: Empty response for chunk {i+1}")
                    continue

                # First, try to parse the whole response as JSON
                parsed = None
                try:
                    parsed = json.loads(response_text)
                except json.JSONDecodeError:
                    # Try to extract the first JSON array present in the text
                    m = re.search(r"(\[.*\])", response_text, re.DOTALL)
                    if m:
                        try:
                            parsed = json.loads(m.group(1))
                        except json.JSONDecodeError:
                            parsed = None

                if isinstance(parsed, list):
                    # Validate and add questions
                    for q in parsed:
                        if self._validate_question(q):
                            questions.append(q)
                    continue

                # If JSON parsing failed, try to heuristically extract questions
                # Look for Q: and A: patterns
                q_blocks = re.split(
                    r"\n(?=Q\d+\.|Question\s*\d+:|\d+\.\s)", response_text, flags=re.IGNORECASE)
                for blk in q_blocks[:questions_per_chunk]:
                    q = self._heuristic_parse_question(blk)
                    if q:
                        questions.append(q)

            except Exception as e:
                print(f"  Error generating quiz for chunk {i+1}: {e}")

        # Ensure we have exactly num_questions (or close to it)
        return questions[:num_questions]

    def _validate_question(self, q: Dict) -> bool:
        """
        Validate that a question has all required fields.

        Args:
            q: Question dictionary to validate

        Returns:
            True if question is valid, False otherwise
        """
        required_fields = ["question", "options",
                           "correct_answer", "difficulty"]
        for field in required_fields:
            if field not in q:
                return False

        # Validate options has A, B, C, D
        if not isinstance(q.get("options"), dict):
            return False
        if not all(opt in q["options"] for opt in ["A", "B", "C", "D"]):
            return False

        # Validate correct_answer is one of A, B, C, D
        if q.get("correct_answer") not in ["A", "B", "C", "D"]:
            return False

        # Validate difficulty level
        valid_difficulties = [d.value for d in DifficultyLevel]
        if q.get("difficulty") not in valid_difficulties:
            return False

        return True

    def _heuristic_parse_question(self, text: str) -> Optional[Dict]:
        """
        Try to parse a question from free-form text using heuristics.

        Args:
            text: Text containing a question and options

        Returns:
            A question dictionary or None if parsing fails
        """
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(lines) < 5:  # Need at least question + 4 options
            return None

        # First non-empty line is the question
        question_text = lines[0]

        # Find options (lines starting with A:, B:, C:, D:)
        options = {}
        option_lines = []
        for ln in lines[1:]:
            m = re.match(r"^([A-D])[\):\.]?\s*(.+)", ln)
            if m:
                opt_letter = m.group(1)
                opt_text = m.group(2).strip()
                options[opt_letter] = opt_text
                option_lines.append(ln)

        if len(options) != 4:
            return None

        # Try to find difficulty level
        difficulty = "Medium"  # default
        remaining_text = text.replace(question_text, "")
        for ln in lines:
            ln_lower = ln.lower()
            if "easy" in ln_lower:
                difficulty = "Easy"
                break
            elif "hard" in ln_lower:
                difficulty = "Hard"
                break
            elif "medium" in ln_lower:
                difficulty = "Medium"
                break

        # Try to find correct answer (often marked with *, correct, or in parentheses)
        correct_answer = None
        for opt in ["A", "B", "C", "D"]:
            if f"({opt})" in text or f"*{opt}" in text or f"Correct: {opt}" in text:
                correct_answer = opt
                break

        if not correct_answer:
            correct_answer = "A"  # default fallback

        return {
            "question": question_text,
            "options": options,
            "correct_answer": correct_answer,
            "difficulty": difficulty
        }

    def generate_quiz_from_query(
        self,
        query: str,
        num_questions: int = 10,
        k: int = 3
    ) -> List[Dict]:
        """
        Complete pipeline: retrieve chunks and generate quiz questions.

        Args:
            query: The search query to find relevant chunks
            num_questions: Total number of quiz questions to generate (default 10)
            k: Number of chunks to retrieve

        Returns:
            A list of generated quiz questions
        """
        print(f"🔍 Retrieving chunks for query: '{query}'...")
        chunks = self.retrieve_chunks_by_query(query, k=k)

        if not chunks:
            print("No chunks found for the given query.")
            return []

        print(f"Found {len(chunks)} chunks.")
        print(f"📝 Generating {num_questions} quiz questions...")
        questions = self.generate_quiz_from_chunks(
            chunks, num_questions=num_questions)

        return questions

    def save_quiz(self, questions: List[Dict], output_file: str = "quiz.json"):
        """
        Save quiz questions to a JSON file.

        Args:
            questions: List of quiz questions to save
            output_file: Path to the output JSON file
        """
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(questions, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved {len(questions)} quiz questions to {output_file}")
        except Exception as e:
            print(f"Error saving quiz: {e}")

    def display_quiz(self, questions: List[Dict]):
        """
        Display quiz questions in a readable format.

        Args:
            questions: List of quiz questions to display
        """
        if not questions:
            print("No quiz questions to display.")
            return

        print("\n" + "="*70)
        print(f"Generated {len(questions)} Quiz Questions")
        print("="*70)

        # Count by difficulty
        easy_count = sum(1 for q in questions if q.get("difficulty") == "Easy")
        medium_count = sum(1 for q in questions if q.get(
            "difficulty") == "Medium")
        hard_count = sum(1 for q in questions if q.get("difficulty") == "Hard")

        print(
            f"\nDifficulty Breakdown: Easy: {easy_count}, Medium: {medium_count}, Hard: {hard_count}")
        print("="*70)

        for i, question in enumerate(questions, 1):
            print(f"\nQuestion {i}: [{question.get('difficulty', 'Unknown')}]")
            print(f"  {question.get('question', 'N/A')}")

            options = question.get('options', {})
            for opt_letter in ['A', 'B', 'C', 'D']:
                opt_text = options.get(opt_letter, "")
                marker = " ✓" if opt_letter == question.get(
                    'correct_answer') else ""
                print(f"    {opt_letter}) {opt_text}{marker}")

        print("\n" + "="*70)
        print("(✓ marks the correct answer)")
        print("="*70)

    def display_quiz_student_view(self, questions: List[Dict]):
        """
        Display quiz questions without showing correct answers (for student use).

        Args:
            questions: List of quiz questions to display
        """
        if not questions:
            print("No quiz questions to display.")
            return

        print("\n" + "="*70)
        print(f"Quiz - {len(questions)} Questions")
        print("="*70)

        # Count by difficulty
        easy_count = sum(1 for q in questions if q.get("difficulty") == "Easy")
        medium_count = sum(1 for q in questions if q.get(
            "difficulty") == "Medium")
        hard_count = sum(1 for q in questions if q.get("difficulty") == "Hard")

        print(
            f"\nDifficulty Breakdown: Easy: {easy_count}, Medium: {medium_count}, Hard: {hard_count}")
        print("="*70)

        for i, question in enumerate(questions, 1):
            print(f"\nQuestion {i}: [{question.get('difficulty', 'Unknown')}]")
            print(f"  {question.get('question', 'N/A')}")

            options = question.get('options', {})
            for opt_letter in ['A', 'B', 'C', 'D']:
                opt_text = options.get(opt_letter, "")
                print(f"    {opt_letter}) {opt_text}")

        print("\n" + "="*70)
        print("End of Quiz")
        print("="*70)

    def generate_answer_key(self, questions: List[Dict], output_file: str = "answer_key.txt"):
        """
        Generate and save an answer key for the quiz.

        Args:
            questions: List of quiz questions
            output_file: Path to save the answer key
        """
        try:
            lines = ["QUIZ ANSWER KEY", "="*50, ""]

            for i, question in enumerate(questions, 1):
                lines.append(
                    f"Question {i}: {question.get('correct_answer')} (Difficulty: {question.get('difficulty')})")
                lines.append(f"  {question.get('question', 'N/A')}")
                lines.append("")

            with open(output_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            print(f"✅ Saved answer key to {output_file}")
        except Exception as e:
            print(f"Error saving answer key: {e}")


if __name__ == "__main__":
    print("This module should be imported from main.py")
    print("Run 'python main.py' from the project root instead.")

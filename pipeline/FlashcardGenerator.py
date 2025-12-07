import json
import re
from typing import List, Dict, Optional
import lancedb
import ollama


class FlashcardGenerator:
    """
    A class to retrieve chunks from LanceDB and generate flashcards
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
        Initialize the FlashcardGenerator.

        Args:
            db_path: Path to the LanceDB database directory
            table_name: Name of the LanceDB table
            embedding_model: Ollama model to use for embeddings
            generation_model: Ollama model to use for flashcard generation
        """
        self.db_path = db_path
        self.table_name = table_name
        self.embedding_model = embedding_model
        self.generation_model = generation_model
        # Extra kwargs to pass to ollama.generate (e.g., device='cuda')
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

    def generate_flashcards_from_chunks(
        self,
        chunks: List[str],
        num_cards: int = 5
    ) -> List[Dict[str, str]]:
        """
        Generate flashcards from a list of text chunks using llama3.

        Args:
            chunks: List of text chunks to generate flashcards from
            num_cards: Number of flashcards to generate per chunk

        Returns:
            A list of flashcards with 'question' and 'answer' keys
        """
        flashcards = []

        for i, chunk in enumerate(chunks):
            # Create a prompt for flashcard generation
            prompt = f"""
Based on the following text, create exactly {num_cards} flashcards in JSON format.
Each flashcard must have a 'question' and 'answer' field.

IMPORTANT INSTRUCTIONS:
- The original text may be written in first person (using "I", "me", "my").
- DO NOT use first-person or second-person pronouns in the flashcards.
- Instead, ALWAYS rewrite pronouns as explicit nouns:
    • "I", "me", "my" → "the narrator"
    • "he", "him" (old man) → "the old man"
    • "they", "them" → use the specific group if identifiable
- Write all questions and answers in a **neutral, third-person study-guide tone**.
- Make questions clear and factual.
- Make answers concise and accurate.
- Do not add opinions or reinterpretations.
- Return ONLY a valid JSON array.

Text:
{chunk}

Return the flashcards in this exact JSON structure:
[
  {{"question": "What is...?", "answer": "..."}},
  {{"question": "How does...?", "answer": "..."}}
]

JSON Array:
"""

            try:
                # Call ollama.generate with optional kwargs
                response = ollama.generate(
                    model=self.generation_model,
                    prompt=prompt,
                    stream=False,
                    **self.generate_kwargs
                )
                response_text = (response.get("response") or "").strip()

                if not response_text:
                    print(f"  Warning: Empty response for chunk {i+1}")
                    continue

                # First, try to parse the whole response as JSON
                parsed = None
                try:
                    parsed = json.loads(response_text)
                except json.JSONDecodeError:
                    # Try to extract the first JSON array/object present in the text
                    m = re.search(r"(\[.*\])", response_text, re.DOTALL)
                    if m:
                        try:
                            parsed = json.loads(m.group(1))
                        except json.JSONDecodeError:
                            parsed = None

                if isinstance(parsed, list):
                    flashcards.extend(parsed)
                    continue

                # If JSON parsing failed, try to heuristically extract Q/A pairs
                # Look for patterns like 'Q: ...' and 'A: ...'
                qa_pairs = re.findall(
                    r"Q[:\)]\s*(.+?)\n\s*A[:\)]\s*(.+?)(?=\n\s*Q[:\)]|$)", response_text, re.DOTALL | re.IGNORECASE)
                if qa_pairs:
                    for q, a in qa_pairs:
                        flashcards.append(
                            {"question": q.strip(), "answer": a.strip()})
                    continue

                # Fallback: split by double newlines and try to form simple cards
                blocks = [b.strip() for b in re.split(
                    r"\n\s*\n", response_text) if b.strip()]
                for blk in blocks[:num_cards]:
                    # If block contains a '?' use first sentence as question
                    lines = [l.strip() for l in blk.splitlines() if l.strip()]
                    if not lines:
                        continue
                    question = None
                    answer = None
                    # find a line ending with ?
                    for ln in lines:
                        if ln.endswith('?'):
                            question = ln
                            break
                    if question:
                        # answer is rest of lines after question
                        idx = lines.index(question)
                        answer = ' '.join(
                            lines[idx+1:]).strip() or "(see text)"
                    else:
                        # take first line as question and rest as answer
                        question = lines[0]
                        answer = ' '.join(lines[1:]).strip() or "(see text)"

                    flashcards.append({"question": question, "answer": answer})

            except Exception as e:
                print(f"  Error generating flashcards for chunk {i+1}: {e}")

        return flashcards

    def generate_flashcards_from_query(
        self,
        query: str,
        k: int = 3,
        num_cards: int = 5
    ) -> List[Dict[str, str]]:
        """
        Complete pipeline: retrieve chunks and generate flashcards.

        Args:
            query: The search query to find relevant chunks
            k: Number of chunks to retrieve
            num_cards: Number of flashcards per chunk

        Returns:
            A list of generated flashcards
        """
        print(f"🔍 Retrieving chunks for query: '{query}'...")
        chunks = self.retrieve_chunks_by_query(query, k=k)

        if not chunks:
            print("No chunks found for the given query.")
            return []

        print(f"Found {len(chunks)} chunks.")
        print("📝 Generating flashcards...")
        flashcards = self.generate_flashcards_from_chunks(
            chunks, num_cards=num_cards)

        return flashcards

    def save_flashcards(self, flashcards: List[Dict[str, str]], output_file: str = "flashcards.json"):
        """
        Save flashcards to a JSON file.

        Args:
            flashcards: List of flashcards to save
            output_file: Path to the output JSON file
        """
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(flashcards, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved {len(flashcards)} flashcards to {output_file}")
        except Exception as e:
            print(f"Error saving flashcards: {e}")

#!/usr/bin/env python
"""Quick test of QuizGenerator to see how many questions are generated."""

import math
from pipeline.QuizGenerator import QuizGenerator
import os
import sys

# Configure Ollama environment
os.environ['OLLAMA_HOME'] = r"D:\OllamaModels"
os.environ['OLLAMA_MODELS'] = r"D:\OllamaModels"

# Add pipeline to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pipeline"))


qg = QuizGenerator(
    db_path="./chunks-storage",
    table_name="book_chunks",
    embedding_model="mxbai-embed-large:latest",
    generation_model="llama3:8b"
)

# Get 3 chunks directly
chunks = qg.retrieve_chunks_by_query("Create a comprehensive quiz", k=3)
print(f"Retrieved {len(chunks)} chunks")

# Test with math
num_questions = 10
questions_per_chunk = max(1, math.ceil(
    num_questions / len(chunks))) if chunks else 0
print(f"Asking for {questions_per_chunk} questions per chunk")
print(f"Expected total: {questions_per_chunk * len(chunks)}")

# Generate
questions = qg.generate_quiz_from_chunks(chunks, num_questions=10)
print(f"\nGenerated {len(questions)} questions total")

# Show breakdown
print("\nQuestions:")
for i, q in enumerate(questions, 1):
    print(f"  {i}. {q['question'][:50]}... [{q['difficulty']}]")

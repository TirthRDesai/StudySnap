-- Supabase SQL script to create tables for StudentHelper
-- Run this in the Supabase SQL Editor: https://app.supabase.com/project/[project-id]/sql

-- Create flashcards table
CREATE TABLE IF NOT EXISTS flashcards (
    id BIGSERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    topic TEXT,
    difficulty TEXT DEFAULT 'medium',
    source_page INTEGER,
    tags JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    reviewed BOOLEAN DEFAULT FALSE,
    review_count INTEGER DEFAULT 0,
    performance_score REAL DEFAULT 0.5
);

-- Create indexes for flashcards
CREATE INDEX IF NOT EXISTS idx_flashcards_topic ON flashcards(topic);
CREATE INDEX IF NOT EXISTS idx_flashcards_created_at ON flashcards(created_at);

-- Create quizzes table
CREATE TABLE IF NOT EXISTS quizzes (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    topic TEXT,
    difficulty TEXT DEFAULT 'medium',
    questions_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    attempts INTEGER DEFAULT 0,
    avg_score REAL DEFAULT 0
);

-- Create indexes for quizzes
CREATE INDEX IF NOT EXISTS idx_quizzes_topic ON quizzes(topic);
CREATE INDEX IF NOT EXISTS idx_quizzes_created_at ON quizzes(created_at);

-- Create quiz_attempts table
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id BIGSERIAL PRIMARY KEY,
    quiz_id BIGINT REFERENCES quizzes(id) ON DELETE CASCADE,
    score REAL,
    total_questions INTEGER,
    completed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    answers_json JSONB
);

-- Create indexes for quiz_attempts
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_quiz_id ON quiz_attempts(quiz_id);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_completed_at ON quiz_attempts(completed_at);

-- Create user_progress table
CREATE TABLE IF NOT EXISTS user_progress (
    id BIGSERIAL PRIMARY KEY,
    flashcard_id BIGINT REFERENCES flashcards(id) ON DELETE CASCADE,
    attempts INTEGER DEFAULT 0,
    correct_count INTEGER DEFAULT 0,
    last_reviewed TIMESTAMP WITH TIME ZONE,
    mastery_level INTEGER DEFAULT 0
);

-- Create indexes for user_progress
CREATE INDEX IF NOT EXISTS idx_user_progress_flashcard_id ON user_progress(flashcard_id);

-- Enable Row Level Security (Optional - for security)
ALTER TABLE flashcards ENABLE ROW LEVEL SECURITY;
ALTER TABLE quizzes ENABLE ROW LEVEL SECURITY;
ALTER TABLE quiz_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_progress ENABLE ROW LEVEL SECURITY;

-- Create policies to allow all operations (for development)
-- In production, implement proper RLS policies
CREATE POLICY "Allow all operations" ON flashcards FOR ALL USING (true);
CREATE POLICY "Allow all operations" ON quizzes FOR ALL USING (true);
CREATE POLICY "Allow all operations" ON quiz_attempts FOR ALL USING (true);
CREATE POLICY "Allow all operations" ON user_progress FOR ALL USING (true);

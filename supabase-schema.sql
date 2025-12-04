-- Create users table
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Create documents/PDFs table
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  file_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(512),
  file_size INTEGER,
  pages INTEGER,
  embedding_model VARCHAR(255),
  generation_model VARCHAR(255),
  chunk_size INTEGER,
  chunk_overlap INTEGER,
  processed_at TIMESTAMP DEFAULT NOW(),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Store uploaded PDF files (backed by Supabase Storage)
CREATE TABLE document_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  storage_key VARCHAR(512) NOT NULL, -- Path/key inside the storage bucket
  original_name VARCHAR(255),
  content_type VARCHAR(100),
  size_bytes BIGINT,
  uploaded_at TIMESTAMP DEFAULT NOW()
);

-- Create flashcards table
CREATE TABLE flashcards (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  chunk_reference VARCHAR(255), -- Reference to chunk stored externally (e.g., LanceDB)
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  query_source VARCHAR(512), -- The query used to generate this flashcard
  file_key VARCHAR(512), -- S3 path to stored flashcard JSON
  is_archived BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Create quiz_sessions table
CREATE TABLE quiz_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title VARCHAR(255),
  description TEXT,
  num_questions INTEGER,
  file_key VARCHAR(512), -- S3 path to stored quiz JSON
  is_archived BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Create quiz questions table
CREATE TABLE quiz_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  quiz_session_id UUID NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
  chunk_reference VARCHAR(255), -- Reference to chunk stored externally (e.g., LanceDB)
  question TEXT NOT NULL,
  options JSONB NOT NULL, -- {"A": "option1", "B": "option2", "C": "option3", "D": "option4"}
  correct_answer VARCHAR(1) NOT NULL,
  difficulty_level VARCHAR(20) NOT NULL, -- Easy, Medium, Hard
  question_number INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create user quiz attempts table
CREATE TABLE quiz_attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  quiz_session_id UUID NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  attempt_number INTEGER DEFAULT 1,
  score INTEGER,
  total_questions INTEGER,
  percentage_score NUMERIC(5, 2),
  started_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP,
  file_key VARCHAR(512) -- S3 path to attempt results
);

-- Create user answers table
CREATE TABLE user_quiz_answers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  attempt_id UUID NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
  question_id UUID NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
  selected_answer VARCHAR(1),
  is_correct BOOLEAN,
  answer_time_seconds INTEGER,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create summaries table
CREATE TABLE summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  summary_text TEXT,
  num_flashcards INTEGER,
  num_quiz_questions INTEGER,
  generation_timestamp TIMESTAMP,
  file_key VARCHAR(512), -- S3 path to summary file
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create generation logs table (for tracking generation process)
CREATE TABLE generation_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type VARCHAR(50), -- pdf_processed, flashcards_generated, quiz_generated
  status VARCHAR(20), -- success, failed, in_progress
  message TEXT,
  metadata JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create storage buckets
INSERT INTO storage.buckets (id, name) VALUES ('flashcards', 'flashcards');
INSERT INTO storage.buckets (id, name) VALUES ('quizzes', 'quizzes');
INSERT INTO storage.buckets (id, name) VALUES ('summaries', 'summaries');
INSERT INTO storage.buckets (id, name) VALUES ('answer-keys', 'answer-keys');
INSERT INTO storage.buckets (id, name) VALUES ('student-quizzes', 'student-quizzes');
INSERT INTO storage.buckets (id, name) VALUES ('attempt-results', 'attempt-results');
INSERT INTO storage.buckets (id, name) VALUES ('documents', 'documents');

-- Create indexes for better performance
CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_document_files_document_id ON document_files(document_id);
CREATE INDEX idx_flashcards_document_id ON flashcards(document_id);
CREATE INDEX idx_flashcards_user_id ON flashcards(user_id);
CREATE INDEX idx_quiz_sessions_document_id ON quiz_sessions(document_id);
CREATE INDEX idx_quiz_sessions_user_id ON quiz_sessions(user_id);
CREATE INDEX idx_quiz_questions_session_id ON quiz_questions(quiz_session_id);
CREATE INDEX idx_quiz_attempts_session_id ON quiz_attempts(quiz_session_id);
CREATE INDEX idx_quiz_attempts_user_id ON quiz_attempts(user_id);
CREATE INDEX idx_user_answers_attempt_id ON user_quiz_answers(attempt_id);
CREATE INDEX idx_summaries_document_id ON summaries(document_id);
CREATE INDEX idx_generation_logs_document_id ON generation_logs(document_id);

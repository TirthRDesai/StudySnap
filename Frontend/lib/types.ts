export type BookStatus = "uploaded" | "processing" | "ready";

export type Book = {
  id: string;
  title: string;
  original_filename: string;
  storage_path: string;
  size_bytes: number | null;
  page_count: number | null;
  status: BookStatus;
  created_at: string;
};

export type Chapter = {
  id: string;
  idx: number;
  title: string;
  page_start: number | null;
  page_end: number | null;
  word_count: number;
};

export type JobKind = "study" | "explainer";
export type JobStatus =
  | "queued"
  | "extracting"
  | "generating"
  | "ranking"
  | "quiz"
  | "explaining"
  | "completed"
  | "failed";

export type Job = {
  id: string;
  book_id: string;
  kind: JobKind;
  status: JobStatus;
  progress: number;
  message: string | null;
  error: string | null;
  created_at: string;
};

export const ACTIVE_JOB_STATUSES: JobStatus[] = [
  "queued",
  "extracting",
  "generating",
  "ranking",
  "quiz",
  "explaining",
];

export type Flashcard = {
  id: string;
  chapter_id: string | null;
  front: string;
  back: string;
  card_type: string;
  format: "qa" | "cloze" | "true_false" | "mcq";
  options: string[] | null;
  importance: number | null;
  rank: number | null;
  selected: boolean;
  source_page: number | null;
  known: boolean | null;
};

export type QuizQuestion = {
  id: string;
  chapter_id: string | null;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string | null;
  source_page: number | null;
};

export type QuizAttempt = {
  id: string;
  score: number;
  total: number;
  created_at: string;
};

export type ExplainLevel = "eli5" | "student" | "detailed";

export type KeyTerm = { term: string; meaning: string };

export type Explanation = {
  id: string;
  chapter_id: string | null;
  level: ExplainLevel;
  title: string;
  content_md: string;
  key_terms: KeyTerm[];
};

export type StudyMode = "exam" | "overview";

export type JobRequest =
  | {
      kind: "study";
      n_cards: number;
      mode: StudyMode;
      include_quiz: boolean;
      quiz_questions: number;
    }
  | { kind: "explainer"; level: ExplainLevel };

-- Flashcards come in several formats: plain Q&A, fill-in-the-blank, true/false and multiple choice.
alter table public.flashcards
  add column format text not null default 'qa' check (format in ('qa', 'cloze', 'true_false', 'mcq')),
  add column options jsonb;  -- 4 shuffled choices, only for format = 'mcq'

-- StudySnap schema: books, chapters, jobs, flashcards, quiz, explainer.
-- Every table is owned by a user and protected by row-level security.
-- The backend writes with the service-role key (which bypasses RLS) and checks ownership itself.

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table public.books (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null check (char_length(title) between 1 and 300),
  original_filename text not null,
  storage_path text not null unique,
  size_bytes bigint,
  page_count int,
  status text not null default 'uploaded'
    check (status in ('uploaded', 'processing', 'ready')),
  created_at timestamptz not null default now(),
  -- the file must live in the owner's folder of the "books" bucket
  constraint books_path_in_user_folder check (storage_path like user_id::text || '/%')
);
create index books_user_idx on public.books (user_id, created_at desc);

create table public.chapters (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references public.books (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  idx int not null,
  title text not null,
  page_start int,
  page_end int,
  word_count int not null default 0,
  unique (book_id, idx)
);

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  book_id uuid not null references public.books (id) on delete cascade,
  kind text not null check (kind in ('study', 'explainer')),
  status text not null default 'queued'
    check (status in ('queued', 'extracting', 'generating', 'ranking', 'quiz', 'explaining', 'completed', 'failed')),
  progress int not null default 0 check (progress between 0 and 100),
  message text,
  options jsonb not null default '{}'::jsonb,
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);
create index jobs_book_idx on public.jobs (book_id, created_at desc);
-- at most one active job per book
create unique index jobs_one_active_per_book on public.jobs (book_id)
  where status not in ('completed', 'failed');

create table public.flashcards (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references public.books (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  chapter_id uuid references public.chapters (id) on delete cascade,
  front text not null,
  back text not null,
  card_type text not null default 'concept',
  importance int check (importance between 1 and 5),
  score real,
  rank int,                       -- 1 = most important; covers the whole generated pool
  selected boolean not null default false,
  source_page int,
  known boolean,                  -- null = not reviewed yet
  created_at timestamptz not null default now()
);
create index flashcards_book_idx on public.flashcards (book_id, rank);

create table public.quiz_questions (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references public.books (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  chapter_id uuid references public.chapters (id) on delete cascade,
  question text not null,
  options jsonb not null,         -- array of 4 strings
  correct_index int not null check (correct_index between 0 and 3),
  explanation text,
  source_page int,
  created_at timestamptz not null default now()
);
create index quiz_questions_book_idx on public.quiz_questions (book_id);

create table public.quiz_attempts (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references public.books (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  score int not null,
  total int not null,
  answers jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index quiz_attempts_book_idx on public.quiz_attempts (book_id, created_at desc);

-- chapter_id null = whole-book overview
create table public.explanations (
  id uuid primary key default gen_random_uuid(),
  book_id uuid not null references public.books (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  chapter_id uuid references public.chapters (id) on delete cascade,
  level text not null check (level in ('eli5', 'student', 'detailed')),
  title text not null,
  content_md text not null,
  key_terms jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create unique index explanations_unique_scope on public.explanations
  (book_id, level, coalesce(chapter_id, '00000000-0000-0000-0000-000000000000'::uuid));

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
alter table public.books enable row level security;
alter table public.chapters enable row level security;
alter table public.jobs enable row level security;
alter table public.flashcards enable row level security;
alter table public.quiz_questions enable row level security;
alter table public.quiz_attempts enable row level security;
alter table public.explanations enable row level security;

-- books: owner can read, add (only into own storage folder) and delete
create policy books_select on public.books for select to authenticated
  using (user_id = (select auth.uid()));
create policy books_insert on public.books for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy books_delete on public.books for delete to authenticated
  using (user_id = (select auth.uid()));

-- generated data: owner read-only (the backend writes it)
create policy chapters_select on public.chapters for select to authenticated
  using (user_id = (select auth.uid()));
create policy jobs_select on public.jobs for select to authenticated
  using (user_id = (select auth.uid()));
create policy quiz_questions_select on public.quiz_questions for select to authenticated
  using (user_id = (select auth.uid()));
create policy explanations_select on public.explanations for select to authenticated
  using (user_id = (select auth.uid()));

-- flashcards: owner can read, and mark cards as known / not known
create policy flashcards_select on public.flashcards for select to authenticated
  using (user_id = (select auth.uid()));
create policy flashcards_update on public.flashcards for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- quiz attempts: owner can read and record attempts
create policy quiz_attempts_select on public.quiz_attempts for select to authenticated
  using (user_id = (select auth.uid()));
create policy quiz_attempts_insert on public.quiz_attempts for insert to authenticated
  with check (user_id = (select auth.uid()));

-- Users may change only the "known" flag of a flashcard, nothing else.
revoke update on public.flashcards from authenticated;
grant update (known) on public.flashcards to authenticated;

-- ---------------------------------------------------------------------------
-- Storage: private "books" bucket, one folder per user (<user_id>/<book_id>.pdf)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('books', 'books', false, 52428800, array['application/pdf'])
on conflict (id) do update
  set public = false,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

create policy books_storage_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'books' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy books_storage_select on storage.objects for select to authenticated
  using (bucket_id = 'books' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy books_storage_delete on storage.objects for delete to authenticated
  using (bucket_id = 'books' and (storage.foldername(name))[1] = (select auth.uid())::text);

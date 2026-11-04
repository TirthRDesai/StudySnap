"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import ExplainerTab from "@/components/ExplainerTab";
import FlashcardsTab from "@/components/FlashcardsTab";
import GeneratePanel from "@/components/GeneratePanel";
import Header from "@/components/Header";
import JobStatus from "@/components/JobStatus";
import QuizTab from "@/components/QuizTab";
import { api, type Health } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { ACTIVE_JOB_STATUSES, type Book, type Chapter, type Job } from "@/lib/types";
import { useRequireSession } from "@/lib/useSession";

type Tab = "flashcards" | "quiz" | "explainer";
const TABS: { id: Tab; label: string }[] = [
  { id: "flashcards", label: "Flashcards" },
  { id: "quiz", label: "Quiz" },
  { id: "explainer", label: "Explainer" },
];

async function fetchBook(id: string) {
  const [b, c, f, e] = await Promise.all([
    supabase.from("books").select("*").eq("id", id).maybeSingle(),
    supabase.from("chapters").select("id,idx,title,page_start,page_end,word_count").eq("book_id", id).order("idx"),
    supabase.from("flashcards").select("id", { count: "exact", head: true }).eq("book_id", id),
    supabase.from("explanations").select("id", { count: "exact", head: true }).eq("book_id", id),
  ]);
  if (!b.data) return null;
  return {
    book: b.data as Book,
    chapters: (c.data ?? []) as Chapter[],
    counts: { cards: f.count ?? 0, explanations: e.count ?? 0 },
  };
}

async function fetchLatestJob(id: string): Promise<Job | null> {
  const { data } = await supabase
    .from("jobs")
    .select("id,book_id,kind,status,progress,message,error,created_at")
    .eq("book_id", id)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return (data as Job | null) ?? null;
}

export default function BookPage() {
  return (
    <Suspense fallback={<main className="flex flex-1 items-center justify-center text-muted">Loading…</main>}>
      <BookView />
    </Suspense>
  );
}

function BookView() {
  const { id } = useParams<{ id: string }>();
  const { session, loading } = useRequireSession();
  const [book, setBook] = useState<Book | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [tab, setTab] = useState<Tab>("flashcards");
  const [refreshKey, setRefreshKey] = useState(0);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthFailed, setHealthFailed] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [counts, setCounts] = useState({ cards: 0, explanations: 0 });
  const wasActive = useRef(false);

  const applyBook = useCallback((res: Awaited<ReturnType<typeof fetchBook>>) => {
    if (!res) {
      setNotFound(true);
      return;
    }
    setBook(res.book);
    setChapters(res.chapters);
    setCounts(res.counts);
  }, []);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    Promise.all([fetchBook(id), fetchLatestJob(id)]).then(([res, latest]) => {
      if (cancelled) return;
      applyBook(res);
      setJob(latest);
    });
    api.health().then(setHealth).catch(() => setHealthFailed(true));
    return () => {
      cancelled = true;
    };
  }, [session, id, applyBook]);

  const active = job !== null && ACTIVE_JOB_STATUSES.includes(job.status);

  // Poll while a job is running; when it finishes, reload everything it produced.
  useEffect(() => {
    if (active) {
      wasActive.current = true;
      const t = setInterval(() => void fetchLatestJob(id).then(setJob), 2000);
      return () => clearInterval(t);
    }
    if (wasActive.current) {
      wasActive.current = false;
      fetchBook(id).then((res) => {
        applyBook(res);
        setRefreshKey((k) => k + 1);
      });
    }
  }, [active, id, applyBook]);

  if (loading || !session) {
    return <main className="flex flex-1 items-center justify-center text-muted">Loading…</main>;
  }

  const backendProblem = healthFailed
    ? "Can't reach the StudySnap backend. Start it before generating anything."
    : health && !health.ollama.reachable
      ? "Ollama isn't running. Start it with `ollama serve`."
      : health && health.ollama.missing_models.length > 0
        ? `Missing models: ${health.ollama.missing_models.join(", ")}. Pull them with \`ollama pull <name>\`.`
        : null;

  return (
    <>
      <Header email={session.user.email} />
      <main className="mx-auto w-full max-w-5xl flex-1 space-y-6 px-4 py-8">
        <Link href="/library" className="text-sm text-muted hover:text-ink">← Library</Link>

        {notFound ? (
          <p className="text-muted">This book doesn’t exist, or isn’t yours.</p>
        ) : !book ? (
          <p className="text-muted">Loading…</p>
        ) : (
          <>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{book.title}</h1>
              <p className="mt-1 text-sm text-muted">
                {[book.page_count ? `${book.page_count} pages` : null, chapters.length ? `${chapters.length} chapters` : null]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>

            {backendProblem && (
              <p role="alert" className="rounded-lg border border-bad p-3 text-sm text-bad">{backendProblem}</p>
            )}

            <details open={counts.cards === 0 && counts.explanations === 0} className="group">
              <summary className="mb-3 cursor-pointer text-sm font-medium text-muted hover:text-ink">
                Generate
              </summary>
              <GeneratePanel
                bookId={book.id}
                disabled={active}
                hasStudySet={counts.cards > 0}
                hasExplainer={counts.explanations > 0}
                onStarted={(j) => setJob(j)}
              />
            </details>

            {job && <JobStatus job={job} />}

            <div>
              <div role="tablist" className="flex gap-1 border-b border-line">
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    role="tab"
                    aria-selected={tab === t.id}
                    onClick={() => setTab(t.id)}
                    className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition ${
                      tab === t.id ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="pt-6">
                {tab === "flashcards" && <FlashcardsTab bookId={book.id} chapters={chapters} refreshKey={refreshKey} />}
                {tab === "quiz" && <QuizTab bookId={book.id} userId={session.user.id} refreshKey={refreshKey} />}
                {tab === "explainer" && <ExplainerTab bookId={book.id} chapters={chapters} refreshKey={refreshKey} />}
              </div>
            </div>
          </>
        )}
      </main>
    </>
  );
}

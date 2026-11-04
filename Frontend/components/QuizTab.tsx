"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { QuizAttempt, QuizQuestion } from "@/lib/types";

type Props = { bookId: string; userId: string; refreshKey: number };
type Phase = "idle" | "running" | "done";

function shuffled<T>(items: T[]): T[] {
  const a = [...items];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function QuizTab({ bookId, userId, refreshKey }: Props) {
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [attempts, setAttempts] = useState<QuizAttempt[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [run, setRun] = useState<QuizQuestion[]>([]);
  const [idx, setIdx] = useState(0);
  const [chosen, setChosen] = useState<number | null>(null);
  const [answers, setAnswers] = useState<{ question_id: string; chosen: number; correct: boolean }[]>([]);
  const [count, setCount] = useState(10);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [q, a] = await Promise.all([
        supabase.from("quiz_questions").select("id,chapter_id,question,options,correct_index,explanation,source_page").eq("book_id", bookId),
        supabase.from("quiz_attempts").select("id,score,total,created_at").eq("book_id", bookId).order("created_at", { ascending: false }).limit(5),
      ]);
      if (cancelled) return;
      if (q.error || a.error) setError((q.error ?? a.error)!.message);
      else {
        const qs = q.data as QuizQuestion[];
        setQuestions(qs);
        setAttempts(a.data as QuizAttempt[]);
        setCount(Math.min(10, qs.length) || 10);
        setPhase("idle");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bookId, refreshKey]);

  function start() {
    if (!questions) return;
    setRun(shuffled(questions).slice(0, count));
    setIdx(0);
    setChosen(null);
    setAnswers([]);
    setPhase("running");
  }

  async function finish(finalAnswers: typeof answers) {
    setPhase("done");
    const score = finalAnswers.filter((a) => a.correct).length;
    const { data, error } = await supabase
      .from("quiz_attempts")
      .insert({ book_id: bookId, user_id: userId, score, total: finalAnswers.length, answers: finalAnswers })
      .select("id,score,total,created_at")
      .single();
    if (error) setError(error.message);
    else setAttempts((prev) => [data as QuizAttempt, ...prev].slice(0, 5));
  }

  function choose(i: number) {
    if (chosen !== null) return;
    setChosen(i);
  }

  function next() {
    const q = run[idx];
    const updated = [...answers, { question_id: q.id, chosen: chosen as number, correct: chosen === q.correct_index }];
    setAnswers(updated);
    if (idx + 1 >= run.length) void finish(updated);
    else {
      setIdx(idx + 1);
      setChosen(null);
    }
  }

  if (error) return <p role="alert" className="text-sm text-bad">{error}</p>;
  if (!questions) return <p className="text-muted">Loading quiz…</p>;
  if (questions.length === 0) {
    return <p className="text-muted">No quiz yet. Generate one from the panel above (make sure “Include a quiz” is checked).</p>;
  }

  if (phase === "running") {
    const q = run[idx];
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <div className="flex items-center justify-between text-sm text-muted">
          <span>Question {idx + 1} of {run.length}</span>
          {q.source_page && <span>Page {q.source_page}</span>}
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-line">
          <div className="h-full bg-accent transition-all" style={{ width: `${((idx + (chosen !== null ? 1 : 0)) / run.length) * 100}%` }} />
        </div>
        <h3 className="text-xl font-medium leading-snug">{q.question}</h3>
        <ul className="space-y-2">
          {q.options.map((opt, i) => {
            const isCorrect = i === q.correct_index;
            const state =
              chosen === null ? "border-line hover:border-muted" : isCorrect ? "border-ok" : i === chosen ? "border-bad" : "border-line opacity-60";
            return (
              <li key={i}>
                <button
                  disabled={chosen !== null}
                  onClick={() => choose(i)}
                  className={`flex w-full items-start gap-3 rounded-lg border bg-surface p-3 text-left text-sm transition ${state}`}
                >
                  <span className="mt-0.5 w-5 shrink-0 font-mono text-xs text-muted">{String.fromCharCode(65 + i)}</span>
                  <span>{opt}</span>
                </button>
              </li>
            );
          })}
        </ul>
        {chosen !== null && (
          <div className="card space-y-3 p-4">
            <p className={`text-sm font-medium ${chosen === q.correct_index ? "text-ok" : "text-bad"}`}>
              {chosen === q.correct_index ? "Correct" : `Not quite. The answer is ${String.fromCharCode(65 + q.correct_index)}.`}
            </p>
            {q.explanation && <p className="text-sm text-muted">{q.explanation}</p>}
            <button className="btn-primary" onClick={next}>{idx + 1 >= run.length ? "See results" : "Next question"}</button>
          </div>
        )}
      </div>
    );
  }

  if (phase === "done") {
    const score = answers.filter((a) => a.correct).length;
    const wrong = run.filter((q, i) => answers[i] && !answers[i].correct);
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <div className="card p-6 text-center">
          <p className="text-sm text-muted">Your score</p>
          <p className="mt-1 text-5xl font-semibold">{score}/{run.length}</p>
          <p className="mt-1 text-muted">{Math.round((score / run.length) * 100)}%</p>
          <div className="mt-5 flex justify-center gap-2">
            <button className="btn-primary" onClick={start}>Try again</button>
            <button className="btn" onClick={() => setPhase("idle")}>Back</button>
          </div>
        </div>
        {wrong.length > 0 && (
          <div className="space-y-3">
            <h3 className="font-semibold">Review what you missed</h3>
            {wrong.map((q) => (
              <div key={q.id} className="card p-4 text-sm">
                <p className="font-medium">{q.question}</p>
                <p className="mt-2 text-ok">Answer: {q.options[q.correct_index]}</p>
                {q.explanation && <p className="mt-1 text-muted">{q.explanation}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl space-y-5">
      <div className="card space-y-4 p-6">
        <h3 className="text-lg font-semibold">Take the quiz</h3>
        <p className="text-sm text-muted">{questions.length} questions available, drawn from the whole book.</p>
        <div>
          <label className="label" htmlFor="qcount">Questions this round</label>
          <input
            id="qcount"
            type="number"
            min={1}
            max={questions.length}
            className="input w-28"
            value={count}
            onChange={(e) => setCount(Math.min(questions.length, Math.max(1, e.target.valueAsNumber || 1)))}
          />
        </div>
        <button className="btn-primary" onClick={start}>Start quiz</button>
      </div>
      {attempts.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Recent attempts</h3>
          <ul className="space-y-1 text-sm text-muted">
            {attempts.map((a) => (
              <li key={a.id} className="flex justify-between">
                <span>{new Date(a.created_at).toLocaleString()}</span>
                <span>{a.score}/{a.total}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ExplainLevel, Job, StudyMode } from "@/lib/types";

type Props = {
  bookId: string;
  disabled: boolean;
  hasStudySet: boolean;
  hasExplainer: boolean;
  onStarted: (job: Job) => void;
};

const MODES: { value: StudyMode; label: string; hint: string }[] = [
  { value: "exam", label: "Exam prep", hint: "Definitions, formulas, facts and cause-and-effect" },
  { value: "overview", label: "Overview", hint: "Main ideas and how they connect" },
];

const LEVELS: { value: ExplainLevel; label: string; hint: string }[] = [
  { value: "eli5", label: "Simple", hint: "Everyday words and analogies" },
  { value: "student", label: "Student", hint: "Clear, with terms defined" },
  { value: "detailed", label: "Detailed", hint: "In depth, technically accurate" },
];

export default function GeneratePanel({ bookId, disabled, hasStudySet, hasExplainer, onStarted }: Props) {
  const [nCards, setNCards] = useState(100);
  const [mode, setMode] = useState<StudyMode>("exam");
  const [includeQuiz, setIncludeQuiz] = useState(true);
  const [quizQuestions, setQuizQuestions] = useState(30);
  const [level, setLevel] = useState<ExplainLevel>("student");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(body: Parameters<typeof api.startJob>[1]) {
    setBusy(true);
    setError(null);
    try {
      onStarted(await api.startJob(bookId, body));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the job.");
    } finally {
      setBusy(false);
    }
  }

  const locked = disabled || busy;
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Number.isFinite(v) ? v : lo));

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section className="card space-y-4 p-5">
        <div>
          <h3 className="font-semibold">Flashcards &amp; quiz</h3>
          <p className="text-sm text-muted">
            Cards are written chapter by chapter, then the best ones across the whole book are kept.
          </p>
        </div>

        <div>
          <label className="label" htmlFor="n-cards">Flashcards to keep (total)</label>
          <input
            id="n-cards"
            type="number"
            min={10}
            max={300}
            className="input"
            value={nCards}
            onChange={(e) => setNCards(clamp(e.target.valueAsNumber, 10, 300))}
          />
        </div>

        <fieldset>
          <legend className="label">Study mode</legend>
          <div className="grid grid-cols-2 gap-2">
            {MODES.map((m) => (
              <label
                key={m.value}
                className={`cursor-pointer rounded-lg border p-3 text-sm transition ${
                  mode === m.value ? "border-accent" : "border-line"
                }`}
              >
                <input
                  type="radio"
                  name="mode"
                  className="sr-only"
                  checked={mode === m.value}
                  onChange={() => setMode(m.value)}
                />
                <span className="block font-medium">{m.label}</span>
                <span className="block text-xs text-muted">{m.hint}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeQuiz} onChange={(e) => setIncludeQuiz(e.target.checked)} />
            Include a quiz of
          </label>
          <input
            aria-label="Number of quiz questions"
            type="number"
            min={5}
            max={100}
            disabled={!includeQuiz}
            className="input w-24"
            value={quizQuestions}
            onChange={(e) => setQuizQuestions(clamp(e.target.valueAsNumber, 5, 100))}
          />
          <span className="text-sm text-muted">questions</span>
        </div>

        <button
          className="btn-primary w-full"
          disabled={locked}
          onClick={() =>
            void start({ kind: "study", n_cards: nCards, mode, include_quiz: includeQuiz, quiz_questions: quizQuestions })
          }
        >
          {hasStudySet ? "Regenerate flashcards & quiz" : "Generate flashcards & quiz"}
        </button>
        {hasStudySet && <p className="text-xs text-muted">This replaces the existing flashcards and quiz.</p>}
      </section>

      <section className="card space-y-4 p-5">
        <div>
          <h3 className="font-semibold">Explainer</h3>
          <p className="text-sm text-muted">
            Every chapter explained in plain language, plus a book overview and glossary.
          </p>
        </div>

        <fieldset>
          <legend className="label">Depth</legend>
          <div className="grid grid-cols-3 gap-2">
            {LEVELS.map((l) => (
              <label
                key={l.value}
                className={`cursor-pointer rounded-lg border p-3 text-sm transition ${
                  level === l.value ? "border-accent" : "border-line"
                }`}
              >
                <input
                  type="radio"
                  name="level"
                  className="sr-only"
                  checked={level === l.value}
                  onChange={() => setLevel(l.value)}
                />
                <span className="block font-medium">{l.label}</span>
                <span className="block text-xs text-muted">{l.hint}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <button
          className="btn-primary w-full"
          disabled={locked}
          onClick={() => void start({ kind: "explainer", level })}
        >
          {hasExplainer ? "Generate this depth" : "Generate explainer"}
        </button>
        <p className="text-xs text-muted">Takes longer than flashcards: it reads the whole book once.</p>
      </section>

      {error && (
        <p role="alert" className="text-sm text-bad md:col-span-2">
          {error}
        </p>
      )}
    </div>
  );
}

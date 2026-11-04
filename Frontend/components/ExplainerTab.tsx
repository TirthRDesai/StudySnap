"use client";

import { useEffect, useMemo, useState } from "react";
import Markdown from "react-markdown";
import { supabase } from "@/lib/supabase";
import type { Chapter, ExplainLevel, Explanation } from "@/lib/types";

type Props = { bookId: string; chapters: Chapter[]; refreshKey: number };

const LEVEL_LABEL: Record<ExplainLevel, string> = { eli5: "Simple", student: "Student", detailed: "Detailed" };
const LEVEL_ORDER: ExplainLevel[] = ["eli5", "student", "detailed"];

export default function ExplainerTab({ bookId, chapters, refreshKey }: Props) {
  const [rows, setRows] = useState<Explanation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState<ExplainLevel | null>(null);
  const [selected, setSelected] = useState<string>("overview");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { data, error } = await supabase
        .from("explanations")
        .select("id,chapter_id,level,title,content_md,key_terms")
        .eq("book_id", bookId);
      if (cancelled) return;
      if (error) setError(error.message);
      else setRows(data as Explanation[]);
    })();
    return () => {
      cancelled = true;
    };
  }, [bookId, refreshKey]);

  const levels = useMemo(
    () => LEVEL_ORDER.filter((l) => rows?.some((r) => r.level === l)),
    [rows]
  );
  const activeLevel = level && levels.includes(level) ? level : levels[0] ?? null;

  const atLevel = useMemo(() => (rows ?? []).filter((r) => r.level === activeLevel), [rows, activeLevel]);
  const overview = atLevel.find((r) => r.chapter_id === null);
  const byChapter = useMemo(() => new Map(atLevel.filter((r) => r.chapter_id).map((r) => [r.chapter_id as string, r])), [atLevel]);
  const available = chapters.filter((c) => byChapter.has(c.id));

  if (error) return <p role="alert" className="text-sm text-bad">{error}</p>;
  if (!rows) return <p className="text-muted">Loading explainer…</p>;
  if (rows.length === 0 || !activeLevel) {
    return <p className="text-muted">No explainer yet. Generate one from the panel above.</p>;
  }

  const current = selected === "overview" ? overview : byChapter.get(selected);
  const terms = current?.key_terms ?? [];

  return (
    <div className="grid gap-6 md:grid-cols-[16rem_1fr]">
      <nav aria-label="Explainer sections" className="space-y-4 md:sticky md:top-4 md:self-start">
        {levels.length > 1 && (
          <div className="flex gap-1">
            {levels.map((l) => (
              <button
                key={l}
                className={`${l === activeLevel ? "btn-primary" : "btn"} flex-1 !px-2`}
                onClick={() => {
                  setLevel(l);
                  setSelected("overview");
                }}
              >
                {LEVEL_LABEL[l]}
              </button>
            ))}
          </div>
        )}
        <ul className="space-y-1 text-sm">
          <li>
            <button
              onClick={() => setSelected("overview")}
              className={`w-full rounded-lg px-3 py-2 text-left ${selected === "overview" ? "bg-surface font-medium" : "text-muted hover:text-ink"}`}
            >
              Book overview
            </button>
          </li>
          {available.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setSelected(c.id)}
                className={`w-full rounded-lg px-3 py-2 text-left ${selected === c.id ? "bg-surface font-medium" : "text-muted hover:text-ink"}`}
              >
                {c.idx + 1}. {c.title}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <article className="card min-w-0 p-6">
        {current ? (
          <>
            <h2 className="mb-4 text-2xl font-semibold tracking-tight">{current.title}</h2>
            <div className="prose-md">
              <Markdown>{current.content_md}</Markdown>
            </div>
            {terms.length > 0 && (
              <section className="mt-8 border-t border-line pt-5">
                <h3 className="mb-3 font-semibold">{selected === "overview" ? "Glossary" : "Key terms"}</h3>
                <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                  {terms.map((t) => (
                    <div key={t.term}>
                      <dt className="font-medium">{t.term}</dt>
                      <dd className="text-muted">{t.meaning}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
          </>
        ) : (
          <p className="text-muted">This section isn’t available at this depth.</p>
        )}
      </article>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { Chapter, Flashcard } from "@/lib/types";

type Props = { bookId: string; chapters: Chapter[]; refreshKey: number };
type View = "deck" | "list";

const TYPE_LABEL: Record<string, string> = {
  definition: "Definition",
  concept: "Concept",
  formula: "Formula",
  process: "Process",
  comparison: "Comparison",
  cause_effect: "Cause & effect",
  example: "Example",
  fact: "Fact",
};

const FORMAT_LABEL: Record<string, string> = {
  qa: "Question",
  cloze: "Fill in the blank",
  true_false: "True or false",
  mcq: "Multiple choice",
};

function Front({ card }: { card: Flashcard }) {
  return (
    <div className="space-y-3">
      <p className="text-xl font-medium leading-snug">{card.front}</p>
      {card.format === "mcq" && card.options && (
        <ol className="space-y-1 text-base text-muted">
          {card.options.map((o, i) => (
            <li key={i}>
              <span className="font-medium text-ink">{"ABCD"[i]}.</span> {o}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function csvCell(v: string | number | null) {
  const s = String(v ?? "");
  return `"${s.replace(/"/g, '""')}"`;
}

export default function FlashcardsTab({ bookId, chapters, refreshKey }: Props) {
  const [cards, setCards] = useState<Flashcard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("deck");
  const [chapterId, setChapterId] = useState("all");
  const [order, setOrder] = useState<"importance" | "book">("importance");
  const [hideKnown, setHideKnown] = useState(false);
  const [pos, setPos] = useState(0);
  const [flipped, setFlipped] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { data, error } = await supabase
        .from("flashcards")
        .select("id,chapter_id,front,back,card_type,format,options,importance,rank,selected,source_page,known")
        .eq("book_id", bookId)
        .order("rank", { ascending: true });
      if (cancelled) return;
      if (error) setError(error.message);
      else {
        setCards(data as Flashcard[]);
        setPos(0);
        setFlipped(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bookId, refreshKey]);

  const chapterIdx = useMemo(() => new Map(chapters.map((c) => [c.id, c.idx])), [chapters]);
  const chapterTitle = useMemo(() => new Map(chapters.map((c) => [c.id, c.title])), [chapters]);
  const selectedCount = useMemo(() => cards?.filter((c) => c.selected).length ?? 0, [cards]);
  const limit = selectedCount; // exactly the number the user asked for

  const visible = useMemo(() => {
    if (!cards) return [];
    let out = cards.filter((c) => (c.rank ?? Infinity) <= limit);
    if (chapterId !== "all") out = out.filter((c) => c.chapter_id === chapterId);
    if (hideKnown) out = out.filter((c) => !c.known);
    if (order === "book") {
      out = [...out].sort(
        (a, b) =>
          (chapterIdx.get(a.chapter_id ?? "") ?? 0) - (chapterIdx.get(b.chapter_id ?? "") ?? 0) ||
          (a.source_page ?? 0) - (b.source_page ?? 0)
      );
    }
    return out;
  }, [cards, limit, chapterId, hideKnown, order, chapterIdx]);

  const safePos = Math.min(pos, Math.max(visible.length - 1, 0));
  const current = visible[safePos];

  const go = useCallback(
    (delta: number) => {
      setFlipped(false);
      setPos((p) => Math.min(Math.max(p + delta, 0), Math.max(visible.length - 1, 0)));
    },
    [visible.length]
  );

  async function mark(card: Flashcard, known: boolean) {
    setCards((prev) => prev?.map((c) => (c.id === card.id ? { ...c, known } : c)) ?? null);
    const { error } = await supabase.from("flashcards").update({ known }).eq("id", card.id);
    if (error) {
      setError(error.message);
      setCards((prev) => prev?.map((c) => (c.id === card.id ? { ...c, known: card.known } : c)) ?? null);
    } else if (!hideKnown) {
      go(1);
    }
  }

  useEffect(() => {
    if (view !== "deck") return;
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === " " && tag !== "BUTTON") {
        e.preventDefault();
        setFlipped((f) => !f);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, go]);

  function exportCsv() {
    const rows = [["Front", "Back", "Topic"]].concat(
      visible.map((c) => [
        c.format === "mcq" && c.options ? `${c.front}\n${c.options.map((o, i) => `${"ABCD"[i]}. ${o}`).join("\n")}` : c.front,
        c.back, chapterTitle.get(c.chapter_id ?? "") ?? ""])
    );
    const blob = new Blob([rows.map((r) => r.map(csvCell).join(",")).join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "flashcards.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  if (error) return <p role="alert" className="text-sm text-bad">{error}</p>;
  if (!cards) return <p className="text-muted">Loading flashcards…</p>;
  if (cards.length === 0) {
    return <p className="text-muted">No flashcards yet. Generate them from the panel above.</p>;
  }

  const knownCount = visible.filter((c) => c.known).length;

  return (
    <div className="space-y-5">
      <div className="card grid gap-4 p-4 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="chapter">Topic</label>
          <select
            id="chapter"
            className="input"
            value={chapterId}
            onChange={(e) => {
              setChapterId(e.target.value);
              setPos(0);
            }}
          >
            <option value="all">All topics</option>
            {chapters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.idx + 1}. {c.title.slice(0, 40)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="order">Order</label>
          <select id="order" className="input" value={order} onChange={(e) => setOrder(e.target.value as "importance" | "book")}>
            <option value="importance">Most important first</option>
            <option value="book">Book order</option>
          </select>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <div className="flex gap-2">
          <button className={view === "deck" ? "btn-primary" : "btn"} onClick={() => setView("deck")}>Study</button>
          <button className={view === "list" ? "btn-primary" : "btn"} onClick={() => setView("list")}>List</button>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-muted">
            <input type="checkbox" checked={hideKnown} onChange={(e) => { setHideKnown(e.target.checked); setPos(0); }} />
            Hide known
          </label>
          <span className="text-muted">{knownCount} of {visible.length} known</span>
          <button className="btn" onClick={exportCsv} disabled={visible.length === 0}>Export CSV</button>
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="text-muted">Nothing to show with these filters.</p>
      ) : view === "deck" && current ? (
        <div className="mx-auto max-w-xl space-y-4">
          <p className="text-center text-sm text-muted">
            Card {safePos + 1} of {visible.length}
          </p>
          <div className="flip">
            <button
              type="button"
              onClick={() => setFlipped((f) => !f)}
              aria-label={flipped ? "Show question" : "Show answer"}
              className="block h-72 w-full text-left"
            >
              <div className="flip-inner h-full" data-flipped={flipped}>
                <div className="flip-face card flex h-full flex-col justify-between p-6">
                  <span className="text-xs uppercase tracking-wide text-muted">
                    {FORMAT_LABEL[current.format] ?? "Question"} · {TYPE_LABEL[current.card_type] ?? current.card_type}
                  </span>
                  <Front card={current} />
                  <span className="text-xs text-muted">Tap or press space to flip</span>
                </div>
                <div className="flip-face flip-back card flex h-full flex-col justify-center overflow-auto border-accent p-6">
                  <p className="whitespace-pre-line text-lg leading-relaxed">{current.back}</p>
                </div>
              </div>
            </button>
          </div>
          <div className="flex items-center justify-between gap-2">
            <button className="btn" onClick={() => go(-1)} disabled={safePos === 0}>← Back</button>
            <div className="flex gap-2">
              <button className="btn" onClick={() => void mark(current, false)}>Still learning</button>
              <button className="btn-primary" onClick={() => void mark(current, true)}>Got it</button>
            </div>
            <button className="btn" onClick={() => go(1)} disabled={safePos >= visible.length - 1}>Next →</button>
          </div>
        </div>
      ) : (
        <ul className="space-y-2">
          {visible.map((c) => (
            <li key={c.id} className="card p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{c.front}</p>
                  {c.format === "mcq" && c.options && (
                    <p className="mt-1 text-sm text-muted">{c.options.map((o, i) => `${"ABCD"[i]}. ${o}`).join("   ")}</p>
                  )}
                </div>
                <span className="shrink-0 text-xs text-muted">#{c.rank}</span>
              </div>
              <p className="mt-1 whitespace-pre-line text-sm text-muted">{c.back}</p>
              <p className="mt-2 text-xs text-muted">
                {chapterTitle.get(c.chapter_id ?? "") ?? ""}
                {c.known ? " · known" : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

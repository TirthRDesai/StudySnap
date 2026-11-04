"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import AuthForm from "@/components/AuthForm";
import { useSession } from "@/lib/useSession";

const FEATURES = [
  ["Flashcards", "The most important cards from the whole book, ranked, not just the first chapters."],
  ["Quizzes", "Multiple-choice questions with explanations and a score you can track."],
  ["Explainer", "Every chapter rewritten in plain language, at the depth you pick."],
];

export default function Home() {
  const router = useRouter();
  const { session, loading } = useSession();

  useEffect(() => {
    if (session) router.replace("/library");
  }, [session, router]);

  if (loading || session) {
    return <main className="flex flex-1 items-center justify-center text-muted">Loading…</main>;
  }

  return (
    <main className="mx-auto grid w-full max-w-5xl flex-1 items-center gap-12 px-4 py-16 md:grid-cols-2">
      <section>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
          Turn any book into things you can actually study.
        </h1>
        <p className="mt-4 max-w-md text-muted">
          Upload a PDF. StudySnap reads it with a model running on your own machine and builds
          flashcards, quizzes and an easy explainer, so your book never leaves your control.
        </p>
        <ul className="mt-8 space-y-4">
          {FEATURES.map(([title, text]) => (
            <li key={title}>
              <p className="font-medium">{title}</p>
              <p className="text-sm text-muted">{text}</p>
            </li>
          ))}
        </ul>
      </section>
      <div className="flex justify-center md:justify-end">
        <AuthForm />
      </div>
    </main>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import Header from "@/components/Header";
import { BOOKS_BUCKET, MAX_UPLOAD_MB, supabase } from "@/lib/supabase";
import type { Book } from "@/lib/types";
import { useRequireSession } from "@/lib/useSession";

function formatSize(bytes: number | null) {
  if (!bytes) return "";
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

async function fetchBooks(): Promise<{ books: Book[]; error?: undefined } | { books?: undefined; error: string }> {
  const { data, error } = await supabase
    .from("books")
    .select("*")
    .order("created_at", { ascending: false });
  return error ? { error: error.message } : { books: data as Book[] };
}

const STATUS_LABEL: Record<Book["status"], string> = {
  uploaded: "Not generated yet",
  processing: "Generating…",
  ready: "Ready",
};

export default function LibraryPage() {
  const router = useRouter();
  const { session, loading } = useRequireSession();
  const [books, setBooks] = useState<Book[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const apply = useCallback((res: Awaited<ReturnType<typeof fetchBooks>>) => {
    if (res.error) setError(res.error);
    else setBooks(res.books ?? []);
  }, []);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    fetchBooks().then((res) => {
      if (!cancelled) apply(res);
    });
    return () => {
      cancelled = true;
    };
  }, [session, apply]);

  const anyProcessing = books?.some((b) => b.status === "processing");
  useEffect(() => {
    if (!anyProcessing) return;
    const t = setInterval(() => void fetchBooks().then(apply), 4000);
    return () => clearInterval(t);
  }, [anyProcessing, apply]);

  async function upload(file: File) {
    if (!session) return;
    setError(null);
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please choose a PDF file.");
      return;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setError(`That file is larger than ${MAX_UPLOAD_MB} MB.`);
      return;
    }
    setUploading(true);
    const id = crypto.randomUUID();
    const path = `${session.user.id}/${id}.pdf`;
    try {
      const up = await supabase.storage
        .from(BOOKS_BUCKET)
        .upload(path, file, { contentType: "application/pdf" });
      if (up.error) throw up.error;

      const { error: insertError } = await supabase.from("books").insert({
        id,
        user_id: session.user.id,
        title: file.name.replace(/\.pdf$/i, "").slice(0, 300),
        original_filename: file.name,
        storage_path: path,
        size_bytes: file.size,
      });
      if (insertError) {
        await supabase.storage.from(BOOKS_BUCKET).remove([path]);
        throw insertError;
      }
      router.push(`/books/${id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setUploading(false);
    }
  }

  async function remove(book: Book) {
    if (!window.confirm(`Delete "${book.title}" and everything generated from it?`)) return;
    setError(null);
    const { error: rowError } = await supabase.from("books").delete().eq("id", book.id);
    if (rowError) {
      setError(rowError.message);
      return;
    }
    await supabase.storage.from(BOOKS_BUCKET).remove([book.storage_path]);
    setBooks((prev) => prev?.filter((b) => b.id !== book.id) ?? null);
  }

  if (loading || !session) {
    return <main className="flex flex-1 items-center justify-center text-muted">Loading…</main>;
  }

  return (
    <>
      <Header email={session.user.email} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Your library</h1>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) void upload(file);
          }}
          className={`mt-6 flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
            dragging ? "border-accent bg-surface" : "border-line"
          }`}
        >
          <p className="font-medium">{uploading ? "Uploading…" : "Drop a book here"}</p>
          <p className="text-sm text-muted">PDF with selectable text, up to {MAX_UPLOAD_MB} MB</p>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void upload(file);
            }}
          />
          <button className="btn-primary" disabled={uploading} onClick={() => inputRef.current?.click()}>
            Choose a PDF
          </button>
        </div>

        {error && <p role="alert" className="mt-4 text-sm text-bad">{error}</p>}

        <div className="mt-10">
          {books === null ? (
            <p className="text-muted">Loading your books…</p>
          ) : books.length === 0 ? (
            <p className="text-muted">No books yet. Upload one to get started.</p>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2">
              {books.map((b) => (
                <li key={b.id} className="card flex flex-col justify-between gap-4 p-4">
                  <div>
                    <Link href={`/books/${b.id}`} className="font-medium hover:underline">
                      {b.title}
                    </Link>
                    <p className="mt-1 text-xs text-muted">
                      {[b.page_count ? `${b.page_count} pages` : null, formatSize(b.size_bytes)]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted">{STATUS_LABEL[b.status]}</span>
                    <button
                      className="text-xs text-muted hover:text-bad disabled:opacity-40"
                      disabled={b.status === "processing"}
                      onClick={() => void remove(b)}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </>
  );
}

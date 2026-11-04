import { supabase } from "./supabase";
import type { Job, JobRequest } from "./types";

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message);
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiError("You are signed out. Please sign in again.", 401);
  return { Authorization: `Bearer ${token}` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(
      "Can't reach the StudySnap backend. Is it running on " + API_URL + "?",
      0
    );
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = "Invalid request options.";
    } catch {
      /* keep default message */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export type Health = {
  ok: boolean;
  ollama: { reachable: boolean; missing_models: string[] };
};

export const api = {
  health: () => request<Health>("/health"),

  async startJob(bookId: string, body: JobRequest): Promise<Job> {
    const headers = {
      ...(await authHeader()),
      "Content-Type": "application/json",
    };
    return request<Job>(`/books/${bookId}/jobs`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  },
};

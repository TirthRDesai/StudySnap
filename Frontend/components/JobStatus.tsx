import { ACTIVE_JOB_STATUSES, type Job } from "@/lib/types";

const KIND_LABEL = { study: "Flashcards & quiz", explainer: "Explainer" } as const;

export default function JobStatus({ job }: { job: Job }) {
  const active = ACTIVE_JOB_STATUSES.includes(job.status);
  const failed = job.status === "failed";
  if (!active && !failed) return null;

  return (
    <div className="card p-4" role="status" aria-live="polite">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">
          {KIND_LABEL[job.kind]} {failed ? "failed" : "in progress"}
        </span>
        {active && <span className="text-muted">{job.progress}%</span>}
      </div>
      {active && (
        <>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-line">
            <div
              className="h-full rounded-full bg-accent transition-all duration-500"
              style={{ width: `${Math.max(job.progress, 2)}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-muted">{job.message ?? "Working…"}</p>
        </>
      )}
      {failed && <p className="mt-2 text-sm text-bad">{job.error ?? "Something went wrong."}</p>}
    </div>
  );
}

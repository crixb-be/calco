import { useState } from "react";
import { ChevronDown, ChevronUp, Eye, FolderOpen, ListChecks, LoaderCircle, StopCircle } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { revealInFolder } from "@/lib/engine";
import { useJobs, type Job } from "@/store/jobs";
import { doclingViewerRequest, type DoclingViewerRequest } from "@/components/docling/DoclingDualViewer";

export const isActiveJob = (job: Job) => job.status === "running" || job.status === "queued" || job.status === "cancelling";

/** Number of jobs still queued or running (drives the "Actividad" badge). */
export function useActiveJobCount() {
  return useJobs((state) => state.jobs.filter(isActiveJob).length);
}

interface Props {
  onViewDocling?: (request: DoclingViewerRequest) => void;
}

/** Job cards: progress, status, cancel, logs and result shortcuts. */
export function JobList({ onViewDocling }: Props) {
  const jobs = useJobs((state) => state.jobs);
  const cancel = useJobs((state) => state.cancel);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (jobs.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
        <ListChecks size={34} className="mb-3 opacity-50" />
        <p className="text-sm">Todavía no hay trabajos</p>
        <p className="mt-1 text-xs">Tus procesos aparecerán aquí.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {jobs.map((job) => {
        const viewerRequest =
          job.task.engine === "docling_core" && job.status === "success"
            ? doclingViewerRequest(job.task.inputFiles, job.outputFiles)
            : null;
        const isActive = isActiveJob(job);
        const isExpanded = expanded === job.task.id;

        return (
          <div key={job.task.id} className="rounded-lg border bg-background/30 p-3">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{job.task.action}</p>
                <p className="mt-0.5 truncate text-[11px] text-muted-foreground" title={job.task.inputFiles.join("\n")}>
                  {job.task.inputFiles[0]?.split(/[\\/]/).pop() ?? ""}
                  {job.task.inputFiles.length > 1 ? ` (+${job.task.inputFiles.length - 1})` : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setExpanded(isExpanded ? null : job.task.id)}
                className="text-muted-foreground"
                aria-label={isExpanded ? "Ocultar registros" : "Mostrar registros"}
              >
                {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
            </div>

            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full transition-all ${job.status === "error" ? "bg-red-400" : job.status === "success" ? "bg-emerald-400" : "bg-primary"}`}
                style={{ width: `${job.progress}%` }}
              />
            </div>

            <p
              className={`mt-2 flex items-center gap-1.5 text-xs ${job.status === "error" ? "text-red-300" : "text-muted-foreground"}`}
              aria-live="polite"
            >
              {isActive && <LoaderCircle size={12} className="shrink-0 animate-spin" />}
              <span className={`break-words ${job.status === "error" ? "whitespace-pre-wrap" : "line-clamp-2"}`}>{job.message}</span>
            </p>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-1 text-[11px] text-muted-foreground">
              <span>
                {job.status === "success"
                  ? "Completado"
                  : job.status === "error"
                    ? "Error"
                    : job.status === "cancelled"
                      ? "Cancelado"
                      : job.status === "cancelling"
                        ? "Cancelando…"
                      : `${Math.round(job.progress)}%`}
              </span>
              {isActive ? (
                <Button type="button" variant="ghost" className="h-7 px-2 text-xs" onClick={() => cancel(job.task.id)}>
                  <StopCircle size={13} /> Cancelar
                </Button>
              ) : (
                <div className="flex gap-1">
                  {viewerRequest && onViewDocling && (
                    <Button type="button" variant="ghost" className="h-7 px-2 text-xs" onClick={() => onViewDocling(viewerRequest)}>
                      <Eye size={13} /> Ver resultado
                    </Button>
                  )}
                  {job.outputFiles[0] && (
                    <Button type="button" variant="ghost" className="h-7 px-2 text-xs" onClick={() => revealInFolder(job.outputFiles[0])}>
                      <FolderOpen size={13} /> Abrir carpeta
                    </Button>
                  )}
                </div>
              )}
            </div>

            {isExpanded && (
              <div className="mt-3 max-h-32 overflow-y-auto border-t pt-2 text-[11px] text-muted-foreground">
                {job.logs.length ? job.logs.map((log, index) => (
                  <p key={index} className={`whitespace-pre-wrap break-words ${log.level === "error" ? "text-red-300" : log.level === "warn" ? "text-amber-300" : ""}`}>
                    [{log.level}] {log.message}
                  </p>
                )) : <p>Sin registros adicionales.</p>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

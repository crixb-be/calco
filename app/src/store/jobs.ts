import { create } from "zustand";
import type { ProcessorTask, TaskEvent } from "@/contracts/task";
import { cancelTask, runTask } from "@/lib/engine";
import { notifyTaskEvent } from "@/lib/notifications";

export type JobStatus = "queued" | "running" | "success" | "error" | "cancelled";
export interface Job { task: ProcessorTask; progress: number; status: JobStatus; message: string; logs: { level: string; message: string }[]; outputFiles: string[]; meta?: Record<string, unknown>; }
interface JobStore { jobs: Job[]; add: (task: ProcessorTask) => Promise<void>; apply: (event: TaskEvent) => void; cancel: (id: string) => Promise<void>; }

const isFinal = (status: JobStatus) => status === "success" || status === "error" || status === "cancelled";

function reduce(job: Job, event: TaskEvent): Job {
  if (event.type === "progress") {
    if (isFinal(job.status)) return job;
    return { ...job, progress: event.percent, message: event.message ?? job.message, status: "running" };
  }
  if (event.type === "log") {
    const logs = [...job.logs, { level: event.level, message: event.message }];
    const surface = !isFinal(job.status) && (event.level === "warn" || event.level === "error");
    return { ...job, logs, message: surface ? event.message : job.message };
  }
  if (event.type === "result") {
    return { ...job, progress: 100, status: "success", message: "Completado", outputFiles: event.outputFiles, meta: event.meta };
  }
  if (job.status === "cancelled") return job;
  const logs = [...job.logs, { level: "error", message: `[${event.code}] ${event.message}` }];
  if (event.details) logs.push({ level: "error", message: event.details });
  return { ...job, status: event.code === "CANCELLED" ? "cancelled" : "error", message: event.message, logs };
}

export const useJobs = create<JobStore>((set, get) => ({
  jobs: [],
  add: async (task) => {
    set((state) => ({ jobs: [{ task, progress: 0, status: "queued", message: "Enviando al motor…", logs: [], outputFiles: [] }, ...state.jobs] }));
    try {
      await runTask(task);
      // Progress events can arrive before invoke() resolves: only touch a job still "queued".
      set((state) => ({ jobs: state.jobs.map((job) => job.task.id === task.id && job.status === "queued" ? { ...job, message: "En cola del motor…" } : job) }));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      set((state) => ({ jobs: state.jobs.map((job) => job.task.id === task.id ? { ...job, status: "error", message, logs: [...job.logs, { level: "error", message }] } : job) }));
    }
  },
  apply: (event) => {
    if (event.type === "result" || event.type === "error") void notifyTaskEvent(event);
    set((state) => ({ jobs: state.jobs.map((job) => job.task.id === event.id ? reduce(job, event) : job) }));
  },
  cancel: async (id) => { await cancelTask(id); get().apply({ type: "error", id, code: "CANCELLED", message: "Cancelado por el usuario" }); },
}));

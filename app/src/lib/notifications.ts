import { invoke } from "@tauri-apps/api/core";
import type { TaskEvent } from "@/contracts/task";

/** Notify only when the desktop window is not currently visible. */
export async function notifyTaskEvent(event: TaskEvent) {
  if (typeof document === "undefined" || document.visibilityState !== "hidden") return;
  if (event.type !== "result" && event.type !== "error") return;
  try {
    await invoke("notify_desktop", {
      title: event.type === "result" ? "CALCO · tarea completada" : "CALCO · tarea fallida",
      body: event.type === "result" ? "El archivo ya está listo para abrir." : event.message,
    });
  } catch {
    // Notifications are best-effort and must never affect the job queue.
  }
}

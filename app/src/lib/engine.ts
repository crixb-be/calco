import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { EngineHealth, ProcessorTask, TaskEvent } from "@/contracts/task";

const tauriAvailable = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export class EngineRpcError extends Error {
  readonly code: string;
  readonly details?: unknown;

  constructor(code: string, message: string, details?: unknown) {
    super(message);
    this.name = "EngineRpcError";
    this.code = code;
    this.details = details;
  }
}

function rpcError(error: unknown): EngineRpcError {
  if (typeof error === "string") {
    try {
      const parsed = JSON.parse(error) as { code?: string; message?: string; details?: unknown };
      if (parsed && typeof parsed === "object") {
        return new EngineRpcError(parsed.code ?? "INTERNAL", parsed.message ?? error, parsed.details);
      }
    } catch {
      // Tauri may return a plain string for transport errors.
    }
    return new EngineRpcError("INTERNAL", error);
  }
  if (error instanceof Error) return new EngineRpcError("INTERNAL", error.message);
  return new EngineRpcError("INTERNAL", String(error));
}

export async function runTask(task: ProcessorTask) {
  if (!tauriAvailable()) throw new Error("CALCO necesita ejecutarse con Tauri para procesar archivos.");
  return invoke<ProcessorTask>("run_task", { task });
}

export async function cancelTask(id: string) {
  if (tauriAvailable()) await invoke("cancel_task", { id });
}

export async function engineHealth() {
  if (!tauriAvailable()) return { engines: {} } satisfies EngineHealth;
  return invoke<EngineHealth>("engine_health");
}

export interface SystemHealth {
  sidecar_online: boolean;
  libreoffice_path: string | null;
  disk_free_bytes: number | null;
}

export type OfficeSuiteId = "msword" | "msexcel" | "mspowerpoint" | "libreoffice";
export interface OfficeSuiteStatus {
  available: boolean;
  path?: string | null;
  source?: "configured" | "auto" | null;
  configuredInvalid?: boolean;
}
export type OfficeSuites = Record<OfficeSuiteId, OfficeSuiteStatus>;

/** Per-suite availability; `binaryPath` is the LibreOffice path saved in Settings. */
export async function detectOfficeSuites(binaryPath: string) {
  const result = await engineRpc<{ suites: OfficeSuites }>("detect_office_suites", { binaryPath });
  return result.suites;
}

export async function checkSystemHealth() {
  if (!tauriAvailable()) return { sidecar_online: false, libreoffice_path: null, disk_free_bytes: null } satisfies SystemHealth;
  return invoke<SystemHealth>("check_system_health");
}

export async function getDefaultOutputDir() {
  if (!tauriAvailable()) return null;
  return invoke<string | null>("get_default_output_dir");
}

export async function setDefaultOutputDir(path: string) {
  if (tauriAvailable()) return invoke<string>("set_default_output_dir", { path });
  return path;
}

export async function engineRpc<T>(method: string, params: unknown): Promise<T> {
  if (!tauriAvailable()) {
    throw new EngineRpcError("INTERNAL", "Las consultas al motor requieren Tauri.");
  }
  try {
    return await invoke<T>("engine_rpc", { method, params });
  } catch (error) {
    throw rpcError(error);
  }
}

export async function revealInFolder(path: string) {
  if (tauriAvailable()) await invoke("reveal_in_folder", { path });
}

export function listenToTaskEvents(handler: (event: TaskEvent) => void): Promise<UnlistenFn> {
  return tauriAvailable()
    ? listen<TaskEvent>("task://event", (event) => handler(event.payload))
    : Promise.resolve(() => undefined);
}

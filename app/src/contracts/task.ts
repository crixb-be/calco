export type Engine = "stirling_core" | "docling_core" | "office_bridge" | "ffmpeg_bridge";
export type ErrorCode = "INVALID_TASK" | "UNKNOWN_ACTION" | "INPUT_NOT_FOUND" | "WRONG_PASSWORD" | "DEPENDENCY_MISSING" | "BINARY_NOT_FOUND" | "CANCELLED" | "TIMEOUT" | "CONVERSION_FAILED" | "INTERNAL";
export interface ProcessorTask { id: string; engine: Engine; action: string; inputFiles: string[]; outputDir: string; options?: Record<string, unknown>; }
export type TaskEvent =
  | { type: "progress"; id: string; percent: number; message?: string }
  | { type: "log"; id: string; level: "info" | "warn" | "error"; message: string }
  | { type: "result"; id: string; status: "success"; outputFiles: string[]; meta?: Record<string, unknown> }
  | { type: "error"; id: string; code: ErrorCode; message: string; details?: string };
export interface EngineHealth {
  engines: Record<string, {
    available: boolean;
    binary?: string | null;
    reason?: string | null;
    engines?: Record<string, boolean | string | null>;
  }>;
}

import { useCallback, useState } from "react";
import { create } from "zustand";
import type { TargetFormat } from "@/catalog/conversions";
import type { ToolDefinition } from "@/catalog/tools";
import { getDefaultOutputDir, setDefaultOutputDir } from "@/lib/engine";

export type OutputCategory = "pdf" | "office" | "image" | "media";

const STORAGE_KEY = "docforge.outputDirs";
const CATEGORIES: OutputCategory[] = ["pdf", "office", "image", "media"];
let loadPromise: Promise<void> | null = null;

const emptyCategories = (): Record<OutputCategory, string> => ({ pdf: "", office: "", image: "", media: "" });

function readPersisted() {
  const byCategory = emptyCategories();
  let general = "";
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (!parsed || typeof parsed !== "object") return { general, byCategory };
    const value = parsed as { general?: unknown; byCategory?: unknown };
    if (typeof value.general === "string") general = value.general;
    if (value.byCategory && typeof value.byCategory === "object") {
      const saved = value.byCategory as Record<string, unknown>;
      for (const category of CATEGORIES) {
        if (typeof saved[category] === "string") byCategory[category] = saved[category];
      }
    }
  } catch {
    // Ignore malformed or unavailable local storage.
  }
  return { general, byCategory };
}

function persist(general: string, byCategory: Record<OutputCategory, string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ general, byCategory }));
  } catch {
    // The in-memory store remains usable if local storage is unavailable.
  }
}

interface OutputDirsState {
  general: string;
  byCategory: Record<OutputCategory, string>;
  loaded: boolean;
  load: () => Promise<void>;
  setGeneral: (path: string) => Promise<void>;
  setCategory: (category: OutputCategory, path: string) => void;
  clearCategory: (category: OutputCategory) => void;
  resolve: (category?: OutputCategory | null) => string;
}

const initial = readPersisted();

export const useOutputDirs = create<OutputDirsState>((set, get) => ({
  ...initial,
  loaded: false,
  load: () => {
    if (get().loaded) return Promise.resolve();
    if (loadPromise) return loadPromise;
    loadPromise = (async () => {
      try {
        const path = await getDefaultOutputDir();
        if (path && path.trim()) {
          set((state) => {
            persist(path, state.byCategory);
            return { general: path };
          });
        }
      } catch {
        // The persisted local value is still available when Rust is unavailable.
      } finally {
        set({ loaded: true });
        loadPromise = null;
      }
    })();
    return loadPromise;
  },
  setGeneral: async (path) => {
    const saved = await setDefaultOutputDir(path);
    set((state) => {
      persist(saved, state.byCategory);
      return { general: saved };
    });
  },
  setCategory: (category, path) => {
    const value = path.trim();
    set((state) => {
      const byCategory = { ...state.byCategory, [category]: value };
      persist(state.general, byCategory);
      return { byCategory };
    });
  },
  clearCategory: (category) => get().setCategory(category, ""),
  resolve: (category) => {
    const state = get();
    return category && state.byCategory[category] ? state.byCategory[category] : state.general;
  },
}));

export function useOutputDir(category: OutputCategory | null) {
  const resolved = useOutputDirs((state) => state.resolve(category));
  const [manualOverride, setManualOverride] = useState<string | null>(null);
  const setOutputDir = useCallback((path: string) => setManualOverride(path), []);
  return [manualOverride ?? resolved, setOutputDir] as const;
}

export function categoryForTarget(target: TargetFormat): OutputCategory {
  if (target === "pdf") return "pdf";
  if (target === "docx" || target === "xlsx" || target === "html" || target === "md") return "office";
  return "image";
}

export function categoryForTool(tool: ToolDefinition): OutputCategory | null {
  if (tool.domain === "multimedia") return "media";
  if (tool.id === "pdf_to_images" || tool.id === "extract_images") return "image";
  if (tool.id === "pdf_to_html" || tool.id === "pdf_to_docx" || tool.id === "pdf_to_xlsx") return "office";
  if (tool.domain === "docling") return null;
  if (tool.domain === "stirling" || tool.id === "office_to_pdf") return "pdf";
  return null;
}

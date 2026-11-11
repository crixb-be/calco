import { create } from "zustand";
import { cloneElements, type PdfElement } from "./types";

interface EditorSnapshot {
  elements: PdfElement[];
  selectedId: string | null;
}

interface PdfEditorState {
  elements: PdfElement[];
  selectedId: string | null;
  past: EditorSnapshot[];
  future: EditorSnapshot[];
  reset: () => void;
  select: (id: string | null) => void;
  add: (element: PdfElement) => void;
  update: (id: string, updater: (element: PdfElement) => PdfElement, history?: boolean) => void;
  remove: (id: string) => void;
  commit: (before: PdfElement[], beforeSelected?: string | null) => void;
  moveUp: (id: string) => void;
  moveDown: (id: string) => void;
  undo: () => void;
  redo: () => void;
}

const initial = { elements: [] as PdfElement[], selectedId: null as string | null, past: [] as EditorSnapshot[], future: [] as EditorSnapshot[] };
const snapshot = (state: PdfEditorState): EditorSnapshot => ({ elements: cloneElements(state.elements), selectedId: state.selectedId });

export const usePdfEditorStore = create<PdfEditorState>((set) => ({
  ...initial,
  reset: () => set({ ...initial }),
  select: (selectedId) => set({ selectedId }),
  add: (element) => set((state) => ({ elements: [...state.elements, element], selectedId: element.id, past: [...state.past, snapshot(state)], future: [] })),
  update: (id, updater, history = true) => set((state) => {
    const next = state.elements.map((element) => element.id === id ? updater(element) : element);
    return history ? { elements: next, past: [...state.past, snapshot(state)], future: [] } : { elements: next };
  }),
  remove: (id) => set((state) => ({ elements: state.elements.filter((element) => element.id !== id), selectedId: state.selectedId === id ? null : state.selectedId, past: [...state.past, snapshot(state)], future: [] })),
  commit: (before, beforeSelected) => set((state) => ({ past: [...state.past, { elements: cloneElements(before), selectedId: beforeSelected ?? state.selectedId }], future: [] })),
  moveUp: (id) => set((state) => {
    const index = state.elements.findIndex((element) => element.id === id);
    if (index < 0) return state;
    const samePage = state.elements.filter((element) => element.page === state.elements[index].page);
    const pageIndex = samePage.findIndex((element) => element.id === id);
    if (pageIndex >= samePage.length - 1) return state;
    const swapId = samePage[pageIndex + 1].id;
    const next = [...state.elements];
    const a = next.findIndex((element) => element.id === id);
    const b = next.findIndex((element) => element.id === swapId);
    [next[a], next[b]] = [next[b], next[a]];
    return { elements: next, past: [...state.past, snapshot(state)], future: [] };
  }),
  moveDown: (id) => set((state) => {
    const index = state.elements.findIndex((element) => element.id === id);
    if (index < 0) return state;
    const samePage = state.elements.filter((element) => element.page === state.elements[index].page);
    const pageIndex = samePage.findIndex((element) => element.id === id);
    if (pageIndex <= 0) return state;
    const swapId = samePage[pageIndex - 1].id;
    const next = [...state.elements];
    const a = next.findIndex((element) => element.id === id);
    const b = next.findIndex((element) => element.id === swapId);
    [next[a], next[b]] = [next[b], next[a]];
    return { elements: next, past: [...state.past, snapshot(state)], future: [] };
  }),
  undo: () => set((state) => {
    const previous = state.past.at(-1);
    if (!previous) return state;
    return { elements: cloneElements(previous.elements), selectedId: previous.selectedId, past: state.past.slice(0, -1), future: [snapshot(state), ...state.future] };
  }),
  redo: () => set((state) => {
    const next = state.future[0];
    if (!next) return state;
    return { elements: cloneElements(next.elements), selectedId: next.selectedId, past: [...state.past, snapshot(state)], future: state.future.slice(1) };
  }),
}));

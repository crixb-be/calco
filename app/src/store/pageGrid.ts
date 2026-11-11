import { create } from "zustand";
import type { PageRotation, PdfPagesMetadataResult, ThumbnailTier } from "@/contracts/rpc";

export interface PageGridItem {
  key: string;
  sourceIndex: number;
  pageIndex: number;
  rotation: PageRotation;
  deleted: boolean;
  selected: boolean;
}

interface PageGridStore {
  items: PageGridItem[];
  originalItems: PageGridItem[];
  thumbnailSize: ThumbnailTier;
  setPages: (metadata: PdfPagesMetadataResult[]) => void;
  moveItem: (activeKey: string, overKey: string) => void;
  rotate: (key: string, direction: "cw" | "ccw") => void;
  toggleDeleted: (key: string) => void;
  setSelected: (key: string, selected: boolean) => void;
  selectRange: (fromKey: string, toKey: string) => void;
  selectAll: () => void;
  invertSelection: () => void;
  rotateSelected: (direction: "cw" | "ccw") => void;
  deleteSelected: () => void;
  resetOrder: () => void;
  setThumbnailSize: (size: ThumbnailTier) => void;
  clear: () => void;
}

const thumbnailSizeKey = "docforge.pageGrid.thumbnailSize";

const rotateBy = (rotation: PageRotation, direction: "cw" | "ccw"): PageRotation => {
  const next = rotation + (direction === "cw" ? 90 : -90);
  return ((next + 360) % 360) as PageRotation;
};

const copyItems = (items: PageGridItem[]) => items.map((item) => ({ ...item }));

const initialThumbnailSize = (): ThumbnailTier => {
  if (typeof window === "undefined") return "M";
  const stored = localStorage.getItem(thumbnailSizeKey);
  return stored === "S" || stored === "M" || stored === "L" || stored === "XL" ? stored : "M";
};

export const usePageGrid = create<PageGridStore>((set) => ({
  items: [],
  originalItems: [],
  thumbnailSize: initialThumbnailSize(),

  setPages: (metadata) => {
    const items = metadata.flatMap((document, sourceIndex) =>
      document.pages.map((page) => ({
        key: `${sourceIndex}:${page.index}`,
        sourceIndex,
        pageIndex: page.index,
        rotation: 0 as PageRotation,
        deleted: false,
        selected: false,
      })),
    );
    set({ items, originalItems: copyItems(items) });
  },

  moveItem: (activeKey, overKey) => set((state) => {
    const oldIndex = state.items.findIndex((item) => item.key === activeKey);
    const newIndex = state.items.findIndex((item) => item.key === overKey);
    if (oldIndex < 0 || newIndex < 0 || oldIndex === newIndex) return state;

    const items = [...state.items];
    const [moved] = items.splice(oldIndex, 1);
    items.splice(newIndex, 0, moved);
    return { items };
  }),

  rotate: (key, direction) => set((state) => ({
    items: state.items.map((item) => (
      item.key === key ? { ...item, rotation: rotateBy(item.rotation, direction) } : item
    )),
  })),

  toggleDeleted: (key) => set((state) => ({
    items: state.items.map((item) => (
      item.key === key ? { ...item, deleted: !item.deleted, selected: false } : item
    )),
  })),

  setSelected: (key, selected) => set((state) => ({
    items: state.items.map((item) => (item.key === key ? { ...item, selected } : item)),
  })),

  selectRange: (fromKey, toKey) => set((state) => {
    const from = state.items.findIndex((item) => item.key === fromKey);
    const to = state.items.findIndex((item) => item.key === toKey);
    if (from < 0 || to < 0) return state;

    const start = Math.min(from, to);
    const end = Math.max(from, to);
    return {
      items: state.items.map((item, index) => (
        index >= start && index <= end && !item.deleted ? { ...item, selected: true } : item
      )),
    };
  }),

  selectAll: () => set((state) => ({
    items: state.items.map((item) => ({ ...item, selected: !item.deleted })),
  })),

  invertSelection: () => set((state) => ({
    items: state.items.map((item) => (
      item.deleted ? item : { ...item, selected: !item.selected }
    )),
  })),

  rotateSelected: (direction) => set((state) => ({
    items: state.items.map((item) => (
      item.selected ? { ...item, rotation: rotateBy(item.rotation, direction) } : item
    )),
  })),

  deleteSelected: () => set((state) => ({
    items: state.items.map((item) => (
      item.selected ? { ...item, deleted: true, selected: false } : item
    )),
  })),

  resetOrder: () => set((state) => {
    const order = new Map(state.originalItems.map((item, index) => [item.key, index]));
    return {
      items: [...state.items].sort(
        (left, right) => (order.get(left.key) ?? 0) - (order.get(right.key) ?? 0),
      ),
    };
  }),

  setThumbnailSize: (thumbnailSize) => {
    localStorage.setItem(thumbnailSizeKey, thumbnailSize);
    set({ thumbnailSize });
  },

  clear: () => set({ items: [], originalItems: [] }),
}));

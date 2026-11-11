import { useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  Maximize2,
  RotateCcw,
  RotateCw,
  X,
} from "lucide-react";
import type { RenderPageResult } from "@/contracts/rpc";
import { engineRpc } from "@/lib/engine";
import type { PageGridItem } from "@/store/pageGrid";
import { Button } from "@/components/ui/primitives";

export type CachedPageRender = Pick<RenderPageResult, "imageUrl" | "width" | "height">;

interface PageZoomModalProps {
  items: PageGridItem[];
  files: string[];
  itemKey: string;
  thumbnail?: string;
  renderCache: Map<string, CachedPageRender>;
  onClose: () => void;
  onRotate: (key: string, direction: "cw" | "ccw") => void;
  onToggleDeleted: (key: string) => void;
  onNavigate: (key: string) => void;
}

const renderKey = (item: PageGridItem) => `${item.sourceIndex}:${item.pageIndex}`;

const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path;

export default function PageZoomModal({
  items,
  files,
  itemKey,
  thumbnail,
  renderCache,
  onClose,
  onRotate,
  onToggleDeleted,
  onNavigate,
}: PageZoomModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<"fit" | "natural">("fit");
  const [render, setRender] = useState<CachedPageRender | null>(null);
  const [loading, setLoading] = useState(false);
  const itemIndex = items.findIndex((item) => item.key === itemKey);
  const item = items[itemIndex];
  const previousItem = itemIndex > 0 ? items[itemIndex - 1] : undefined;
  const nextItem = itemIndex >= 0 ? items[itemIndex + 1] : undefined;

  useEffect(() => {
    const previousFocus = document.activeElement;
    dialogRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft" && previousItem) onNavigate(previousItem.key);
      if (event.key === "ArrowRight" && nextItem) onNavigate(nextItem.key);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [nextItem, onClose, onNavigate, previousItem]);

  useEffect(() => {
    if (!item) return;
    let cancelled = false;
    const currentKey = renderKey(item);
    const cached = renderCache.get(currentKey);
    setRender(cached ?? null);
    setLoading(!cached);

    const maxWidth = Math.min(
      2400,
      Math.round(window.innerWidth * 0.9 * window.devicePixelRatio),
    );

    const request = async (target: PageGridItem, updateState: boolean) => {
      const key = renderKey(target);
      const existing = renderCache.get(key);
      if (existing) {
        if (updateState && !cancelled) {
          setRender(existing);
          setLoading(false);
        }
        return;
      }

      if (updateState && !cancelled) setLoading(true);
      try {
        const result = await engineRpc<RenderPageResult>("render_page", {
          pdfPath: files[target.sourceIndex],
          index: target.pageIndex,
          tier: "modal",
          maxWidth,
        });
        const value = {
          imageUrl: result.imageUrl,
          width: result.width,
          height: result.height,
        } satisfies CachedPageRender;
        renderCache.set(key, value);
        if (updateState && !cancelled) {
          setRender(value);
          setLoading(false);
        }
      } catch {
        if (updateState && !cancelled) setLoading(false);
      }
    };

    void request(item, true);
    if (previousItem) void request(previousItem, false);
    if (nextItem) void request(nextItem, false);

    return () => {
      cancelled = true;
    };
  }, [files, item, nextItem, previousItem, renderCache]);

  if (!item) return null;

  const pagePosition = itemIndex + 1;
  const severalFiles = files.length > 1;
  const label = severalFiles
    ? `${fileName(files[item.sourceIndex])} · página ${item.pageIndex + 1}`
    : `Página original ${item.pageIndex + 1}`;
  const quarterTurn = item.rotation === 90 || item.rotation === 270;

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Página ${pagePosition} de ${items.length}`}
      tabIndex={-1}
      className="fixed inset-0 z-50 flex flex-col bg-black/80 backdrop-blur-sm outline-none"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-white/10 px-4 py-3 text-white">
        <div className="min-w-0">
          <p className="text-sm font-semibold">Página {pagePosition} de {items.length}</p>
          <p className="truncate text-xs text-white/65">{label}</p>
        </div>
        <button
          type="button"
          aria-label="Cerrar ampliación"
          title="Cerrar"
          onClick={onClose}
          className="rounded-md p-2 hover:bg-white/10"
        >
          <X size={20} />
        </button>
      </header>

      <div className="relative min-h-0 flex-1 overflow-hidden">
        <button
          type="button"
          aria-label="Página anterior"
          disabled={!previousItem}
          onClick={() => previousItem && onNavigate(previousItem.key)}
          className="absolute left-3 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/45 p-3 text-white transition hover:bg-black/70 disabled:cursor-not-allowed disabled:opacity-25"
        >
          <ChevronLeft size={24} />
        </button>

        <div className={`flex h-full w-full ${view === "fit" ? "items-center justify-center overflow-hidden p-6" : "items-start justify-start overflow-auto p-6"}`}>
          <div className="relative flex shrink-0 items-center justify-center">
            {render?.imageUrl || thumbnail ? (
              <img
                src={render?.imageUrl ?? thumbnail}
                alt={label}
                decoding="async"
                className={view === "fit" ? "max-h-[90vh] max-w-[90vw] object-contain" : "max-h-none max-w-none object-contain"}
                style={{
                  transform: `rotate(${item.rotation}deg)${quarterTurn && view === "fit" ? " scale(0.72)" : ""}`,
                }}
              />
            ) : (
              <div className="h-96 w-64 animate-pulse rounded bg-white/10" />
            )}
            {loading && (
              <div className="absolute right-3 top-3 rounded-full bg-black/60 p-2 text-white">
                <LoaderCircle size={17} className="animate-spin" />
              </div>
            )}
            {item.deleted && (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-red-600/45 text-5xl font-bold text-white">
                ×
              </div>
            )}
          </div>
        </div>

        <button
          type="button"
          aria-label="Página siguiente"
          disabled={!nextItem}
          onClick={() => nextItem && onNavigate(nextItem.key)}
          className="absolute right-3 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/45 p-3 text-white transition hover:bg-black/70 disabled:cursor-not-allowed disabled:opacity-25"
        >
          <ChevronRight size={24} />
        </button>
      </div>

      <footer className="flex shrink-0 flex-wrap items-center justify-center gap-2 border-t border-white/10 px-4 py-3 text-white">
        <Button type="button" variant="ghost" className="h-8 text-xs text-white hover:bg-white/10" onClick={() => onRotate(item.key, "ccw")}>
          <RotateCcw size={14} /> Izquierda
        </Button>
        <Button type="button" variant="ghost" className="h-8 text-xs text-white hover:bg-white/10" onClick={() => onRotate(item.key, "cw")}>
          <RotateCw size={14} /> Derecha
        </Button>
        <Button type="button" variant={item.deleted ? "default" : "danger"} className="h-8 text-xs" onClick={() => onToggleDeleted(item.key)}>
          {item.deleted ? "Restaurar página" : "Marcar para eliminar"}
        </Button>
        <div className="ml-2 flex items-center rounded-md border border-white/15 p-0.5">
          <button type="button" onClick={() => setView("fit")} className={`rounded px-2 py-1 text-xs ${view === "fit" ? "bg-white/15" : "text-white/60 hover:text-white"}`}>
            <Maximize2 size={12} className="mr-1 inline" /> Ajustar
          </button>
          <button type="button" onClick={() => setView("natural")} className={`rounded px-2 py-1 text-xs ${view === "natural" ? "bg-white/15" : "text-white/60 hover:text-white"}`}>
            100%
          </button>
        </div>
      </footer>
    </div>
  );
}

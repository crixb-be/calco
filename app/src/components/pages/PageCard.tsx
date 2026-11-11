import { useEffect, useRef } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  Check,
  Maximize2,
  RotateCcw,
  RotateCw,
  Trash2,
} from "lucide-react";
import type { PageGridItem } from "@/store/pageGrid";

interface PageCardProps {
  item: PageGridItem;
  position: number;
  totalSources: number;
  thumbnail?: string;
  hasCurrentThumbnail: boolean;
  onVisible: (item: PageGridItem) => void;
  onRotate: (direction: "cw" | "ccw") => void;
  onDelete: () => void;
  onSelect: (shiftKey: boolean) => void;
  onZoom: () => void;
}

const stopPointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
  event.stopPropagation();
};

export default function PageCard({
  item,
  position,
  totalSources,
  thumbnail,
  hasCurrentThumbnail,
  onVisible,
  onRotate,
  onDelete,
  onSelect,
  onZoom,
}: PageCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.key,
  });

  useEffect(() => {
    const element = cardRef.current;
    if (!element || hasCurrentThumbnail) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          onVisible(item);
          observer.disconnect();
        }
      },
      { rootMargin: "400px" },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [hasCurrentThumbnail, item, onVisible]);

  const setRefs = (node: HTMLDivElement | null) => {
    cardRef.current = node;
    setNodeRef(node);
  };

  const sourceLabel = totalSources > 1
    ? `${String.fromCharCode(65 + item.sourceIndex)} · ${item.pageIndex + 1}`
    : `Página ${item.pageIndex + 1}`;
  const quarterTurn = item.rotation === 90 || item.rotation === 270;
  const cardStyle = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setRefs}
      style={cardStyle}
      {...attributes}
      {...listeners}
      onClick={(event) => onSelect(event.shiftKey)}
      onDoubleClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onZoom();
      }}
      className={`group relative aspect-[3/4] cursor-grab overflow-hidden rounded-lg border bg-background/50 shadow-sm transition [content-visibility:auto] hover:border-primary/60 active:cursor-grabbing ${isDragging ? "z-20 opacity-35" : ""} ${item.deleted ? "border-red-500/70" : ""}`}
    >
      <div className="absolute left-2 top-2 z-10 flex items-center gap-1.5">
        <span className="rounded bg-background/85 px-1.5 py-0.5 text-[10px] font-bold shadow">
          {item.deleted ? "—" : position}
        </span>
        <span className="rounded bg-background/85 px-1.5 py-0.5 text-[10px] text-muted-foreground shadow">
          {sourceLabel}
        </span>
      </div>

      <div className="absolute right-2 top-2 z-20 flex items-center gap-1 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
        <button
          type="button"
          title="Ampliar página"
          aria-label="Ampliar página"
          onPointerDown={stopPointerDown}
          onClick={(event) => {
            event.stopPropagation();
            onZoom();
          }}
          className="rounded bg-background/85 p-1.5 shadow hover:bg-background"
        >
          <Maximize2 size={14} />
        </button>
        <label
          className="cursor-pointer rounded bg-background/85 p-1.5 shadow"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          <input type="checkbox" checked={item.selected} onChange={() => onSelect(false)} className="sr-only" />
          <span className={`flex h-4 w-4 items-center justify-center rounded border ${item.selected ? "border-primary bg-primary text-primary-foreground" : "bg-background/70"}`}>
            {item.selected && <Check size={12} />}
          </span>
        </label>
      </div>

      <div className={`flex h-full items-center justify-center bg-white p-3 ${item.deleted ? "opacity-40" : ""}`}>
        {thumbnail ? (
          <img
            src={thumbnail}
            alt={`Miniatura ${sourceLabel}`}
            decoding="async"
            className="max-h-full max-w-full object-contain transition-transform duration-200"
            style={{
              transform: `rotate(${item.rotation}deg)${quarterTurn ? " scale(0.72)" : ""}`,
            }}
          />
        ) : (
          <div className="h-3/4 w-2/3 animate-pulse rounded bg-slate-200" />
        )}
      </div>

      {item.deleted && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-red-600/35 text-white">
          <Trash2 size={34} />
        </div>
      )}

      <div className="absolute inset-x-0 bottom-0 flex translate-y-1 items-center justify-center gap-1 bg-gradient-to-t from-black/75 to-transparent px-2 pb-2 pt-7 opacity-0 transition group-hover:translate-y-0 group-hover:opacity-100">
        <button
          type="button"
          title="Rotar a la izquierda"
          onPointerDown={stopPointerDown}
          onClick={(event) => {
            event.stopPropagation();
            onRotate("ccw");
          }}
          className="rounded bg-white/15 p-1.5 text-white hover:bg-white/30"
        >
          <RotateCcw size={14} />
        </button>
        <button
          type="button"
          title="Rotar a la derecha"
          onPointerDown={stopPointerDown}
          onClick={(event) => {
            event.stopPropagation();
            onRotate("cw");
          }}
          className="rounded bg-white/15 p-1.5 text-white hover:bg-white/30"
        >
          <RotateCw size={14} />
        </button>
        <button
          type="button"
          title={item.deleted ? "Restaurar página" : "Marcar para eliminar"}
          onPointerDown={stopPointerDown}
          onClick={(event) => {
            event.stopPropagation();
            onDelete();
          }}
          className="rounded bg-red-500/75 p-1.5 text-white hover:bg-red-500"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}

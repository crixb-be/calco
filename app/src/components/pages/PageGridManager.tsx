import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  rectSortingStrategy,
  SortableContext,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  CheckCheck,
  RotateCcw,
  RotateCw,
  Trash2,
  Undo2,
} from "lucide-react";
import type {
  PageRef,
  PageThumbnail,
  PageThumbnailsResult,
  PdfPagesMetadataResult,
  ThumbnailTier,
} from "@/contracts/rpc";
import { engineRpc } from "@/lib/engine";
import { usePageGrid, type PageGridItem } from "@/store/pageGrid";
import { Button, Card } from "@/components/ui/primitives";
import PageCard from "@/components/pages/PageCard";
import PageZoomModal, { type CachedPageRender } from "@/components/pages/PageZoomModal";

interface PageGridManagerProps {
  files: string[];
  metadata: PdfPagesMetadataResult[];
}

type CachedThumbnail = Pick<PageThumbnail, "thumbUrl" | "width" | "height">;

const CARD_WIDTHS: Record<ThumbnailTier, number> = {
  S: 140,
  M: 220,
  L: 320,
  XL: 440,
};

const tierOrder: ThumbnailTier[] = ["S", "M", "L", "XL"];

function DragPreview({ item }: { item: PageGridItem }) {
  const { setNodeRef, transform, transition } = useSortable({ id: item.key });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className="w-28 rounded-lg border bg-white p-2 shadow-2xl"
    >
      <div className="aspect-[3/4] rounded bg-slate-100" />
      <p className="mt-1 text-center text-[10px] text-slate-600">
        Página {item.pageIndex + 1}
      </p>
    </div>
  );
}

export default function PageGridManager({ files, metadata }: PageGridManagerProps) {
  const items = usePageGrid((state) => state.items);
  const thumbnailSize = usePageGrid((state) => state.thumbnailSize);
  const setPages = usePageGrid((state) => state.setPages);
  const moveItem = usePageGrid((state) => state.moveItem);
  const rotate = usePageGrid((state) => state.rotate);
  const toggleDeleted = usePageGrid((state) => state.toggleDeleted);
  const setSelected = usePageGrid((state) => state.setSelected);
  const selectRange = usePageGrid((state) => state.selectRange);
  const selectAll = usePageGrid((state) => state.selectAll);
  const invertSelection = usePageGrid((state) => state.invertSelection);
  const rotateSelected = usePageGrid((state) => state.rotateSelected);
  const deleteSelected = usePageGrid((state) => state.deleteSelected);
  const resetOrder = usePageGrid((state) => state.resetOrder);
  const setThumbnailSize = usePageGrid((state) => state.setThumbnailSize);
  const [thumbnails, setThumbnails] = useState<Record<string, CachedThumbnail>>({});
  const requestedBatches = useRef<Record<string, boolean>>({});
  const renderCache = useRef(new Map<string, CachedPageRender>());
  const [activeId, setActiveId] = useState<string | null>(null);
  const [zoomKey, setZoomKey] = useState<string | null>(null);
  const lastSelected = useRef<string | null>(null);

  useEffect(() => {
    setPages(metadata);
    setThumbnails({});
    requestedBatches.current = {};
    renderCache.current.clear();
    lastSelected.current = null;
    setZoomKey(null);
  }, [metadata, setPages]);

  const requestThumbnailBatch = useCallback(async (item: PageGridItem) => {
    const batchSize = thumbnailSize === "S" || thumbnailSize === "M" ? 12 : 6;
    const start = Math.floor(item.pageIndex / batchSize) * batchSize;
    const batchKey = `${thumbnailSize}:${item.sourceIndex}:${start}`;
    if (requestedBatches.current[batchKey]) return;
    requestedBatches.current[batchKey] = true;

    const document = metadata[item.sourceIndex];
    const pdfPath = files[item.sourceIndex];
    if (!document || !pdfPath) return;

    const cardWidth = CARD_WIDTHS[thumbnailSize];
    const devicePixelRatio = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
    const maxWidth = Math.max(120, Math.min(1400, Math.round(cardWidth * devicePixelRatio)));

    try {
      const result = await engineRpc<PageThumbnailsResult>("get_page_thumbnails", {
        pdfPath,
        start,
        count: Math.min(batchSize, document.pageCount - start),
        maxWidth,
        tier: thumbnailSize,
        format: "webp",
      });

      setThumbnails((state) => {
        const next = { ...state };
        result.pages.forEach((page) => {
          next[`${thumbnailSize}:${item.sourceIndex}:${page.index}`] = {
            thumbUrl: page.thumbUrl,
            width: page.width,
            height: page.height,
          };
        });
        return next;
      });
    } catch {
      requestedBatches.current[batchKey] = false;
    }
  }, [files, metadata, thumbnailSize]);

  const handleSelect = useCallback((item: PageGridItem, shiftKey: boolean) => {
    if (shiftKey && lastSelected.current) {
      selectRange(lastSelected.current, item.key);
    } else {
      setSelected(item.key, !item.selected);
    }
    lastSelected.current = item.key;
  }, [selectRange, setSelected]);

  const getBestThumbnail = useCallback((item: PageGridItem) => {
    const available = tierOrder
      .map((tier) => thumbnails[`${tier}:${item.sourceIndex}:${item.pageIndex}`])
      .filter((value): value is CachedThumbnail => Boolean(value));
    return available.reduce<CachedThumbnail | undefined>((best, candidate) => {
      if (!best || candidate.width * candidate.height > best.width * best.height) return candidate;
      return best;
    }, undefined);
  }, [thumbnails]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );
  const activeItem = items.find((item) => item.key === activeId);
  const selectedCount = items.filter((item) => item.selected).length;
  const deletedCount = items.filter((item) => item.deleted).length;
  const liveItems = items.filter((item) => !item.deleted);
  const positions = useMemo(() => {
    const result: Record<string, number> = {};
    liveItems.forEach((item, index) => {
      result[item.key] = index + 1;
    });
    return result;
  }, [liveItems]);
  const zoomItem = zoomKey ? items.find((item) => item.key === zoomKey) : undefined;

  function onDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
  }

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    setActiveId(null);
    if (!over || active.id === over.id) return;
    moveItem(String(active.id), String(over.id));
  }

  return (
    <Card className="space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" className="h-8 px-2 text-xs" onClick={selectAll}>
          <CheckCheck size={14} /> Seleccionar todo
        </Button>
        <Button type="button" variant="ghost" className="h-8 px-2 text-xs" onClick={invertSelection}>
          Invertir
        </Button>
        <Button type="button" variant="ghost" className="h-8 px-2 text-xs" onClick={() => rotateSelected("cw")} disabled={!selectedCount}>
          <RotateCw size={14} /> Rotar
        </Button>
        <Button type="button" variant="danger" className="h-8 px-2 text-xs" onClick={deleteSelected} disabled={!selectedCount}>
          <Trash2 size={14} /> Eliminar
        </Button>
        <Button type="button" variant="ghost" className="h-8 px-2 text-xs" onClick={resetOrder}>
          <Undo2 size={14} /> Restablecer orden
        </Button>
        <div className="ml-auto flex items-center gap-1 rounded-md border p-0.5" aria-label="Tamaño de miniaturas">
          {tierOrder.map((size) => (
            <button
              key={size}
              type="button"
              onClick={() => setThumbnailSize(size)}
              className={`rounded px-2 py-1 text-[11px] font-bold ${thumbnailSize === size ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent"}`}
            >
              {size}
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        {items.length} páginas · {selectedCount} seleccionadas · {deletedCount} a eliminar
      </p>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onDragCancel={() => setActiveId(null)}
      >
        <SortableContext items={items.map((item) => item.key)} strategy={rectSortingStrategy}>
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${CARD_WIDTHS[thumbnailSize]}px, 1fr))` }}
          >
            {items.map((item) => {
              const currentThumbnail = thumbnails[`${thumbnailSize}:${item.sourceIndex}:${item.pageIndex}`];
              const bestThumbnail = getBestThumbnail(item);
              return (
                <PageCard
                  key={item.key}
                  item={item}
                  position={positions[item.key] ?? 0}
                  totalSources={files.length}
                  thumbnail={bestThumbnail?.thumbUrl}
                  hasCurrentThumbnail={Boolean(currentThumbnail)}
                  onVisible={requestThumbnailBatch}
                  onRotate={(direction) => rotate(item.key, direction)}
                  onDelete={() => toggleDeleted(item.key)}
                  onSelect={(shiftKey) => handleSelect(item, shiftKey)}
                  onZoom={() => setZoomKey(item.key)}
                />
              );
            })}
          </div>
        </SortableContext>
        <DragOverlay>{activeItem ? <DragPreview item={activeItem} /> : null}</DragOverlay>
      </DndContext>

      {items.length > 0 && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <RotateCcw size={13} /> Arrastra para cambiar el orden. Las páginas marcadas en rojo no se enviarán al resultado.
        </div>
      )}

      {zoomItem && (
        <PageZoomModal
          items={items}
          files={files}
          itemKey={zoomItem.key}
          thumbnail={getBestThumbnail(zoomItem)?.thumbUrl}
          renderCache={renderCache.current}
          onClose={() => setZoomKey(null)}
          onRotate={rotate}
          onToggleDeleted={toggleDeleted}
          onNavigate={setZoomKey}
        />
      )}
    </Card>
  );
}

export function pageSequence(items: PageGridItem[]): PageRef[] {
  return items.filter((item) => !item.deleted).map((item) => ({
    sourceIndex: item.sourceIndex,
    pageIndex: item.pageIndex,
    ...(item.rotation ? { rotation: item.rotation } : {}),
  }));
}

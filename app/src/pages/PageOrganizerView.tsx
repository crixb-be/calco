import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, LoaderCircle, PanelsTopLeft, Play, RotateCcw, RotateCw, Trash2 } from "lucide-react";
import { toolById } from "@/catalog/tools";
import type { OrganizerThumbnail, PageRotation, PageThumbnailsResult, PdfPagesMetadataResult } from "@/contracts/rpc";
import FileDrop from "@/components/FileDrop";
import { Button, Card } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { engineRpc } from "@/lib/engine";
import { useJobs } from "@/store/jobs";
import { useOutputDir } from "@/store/outputDirs";

interface Props { onBack: () => void; }
type PageItem = OrganizerThumbnail;
const organizerTool = toolById("page_organizer")!;
const THUMBNAIL_BATCH_SIZE = 24;

interface LazyPageCardProps {
  page: PageItem;
  index: number;
  dragIndex: number | null;
  onVisible: (index: number) => void;
  onMove: (from: number, to: number) => void;
  onRotate: (index: number) => void;
  onDelete: (index: number) => void;
  setDragIndex: (index: number | null) => void;
}

function LazyPageCard({ page, index, dragIndex, onVisible, onMove, onRotate, onDelete, setDragIndex }: LazyPageCardProps) {
  const cardRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = cardRef.current;
    if (!element || page.thumbnail) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        onVisible(index);
        observer.disconnect();
      }
    }, { rootMargin: "500px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [index, onVisible, page.thumbnail]);

  return <article ref={cardRef} draggable onDragStart={() => setDragIndex(index)} onDragOver={(event) => event.preventDefault()} onDrop={() => { if (dragIndex !== null) onMove(dragIndex, index); setDragIndex(null); }} className={`group relative w-[120px] justify-self-center rounded-lg border bg-background/40 p-1.5 transition ${dragIndex === index ? "border-primary opacity-60" : "hover:border-primary/60"}`}>
    {page.thumbnail ? <img src={page.thumbnail} alt={`Pagina ${page.page_number}`} decoding="async" className="aspect-[0.72] w-full rounded bg-white object-contain" /> : <div className="flex aspect-[0.72] w-full animate-pulse items-center justify-center rounded bg-slate-200 text-[10px] text-slate-500">Cargando...</div>}
    <div className="flex items-center justify-between px-1 pt-1 text-[11px] text-muted-foreground"><span>Pag. {page.page_number}</span><span>{page.rotation} deg</span></div>
    <div className="absolute right-1.5 top-1.5 flex gap-1 opacity-0 transition group-hover:opacity-100"><button type="button" aria-label={`Rotar pagina ${page.page_number}`} onClick={() => onRotate(index)} className="rounded-full bg-slate-900/85 p-1.5 text-white hover:bg-primary"><RotateCw size={13} /></button><button type="button" aria-label={`Eliminar pagina ${page.page_number}`} onClick={() => onDelete(index)} className="rounded-full bg-slate-900/85 p-1.5 text-white hover:bg-red-500"><Trash2 size={13} /></button></div>
  </article>;
}

export default function PageOrganizerView({ onBack }: Props) {
  const add = useJobs((state) => state.add);
  const showToast = useToast((state) => state.show);
  const [files, setFiles] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useOutputDir("pdf");
  const [pages, setPages] = useState<PageItem[]>([]);
  const [original, setOriginal] = useState<PageItem[]>([]);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const requestedBatches = useRef<Record<string, boolean>>({});
  const sourceRef = useRef<string | null>(null);

  useEffect(() => {
    if (files.length !== 1) {
      sourceRef.current = null;
      requestedBatches.current = {};
      setPages([]);
      setOriginal([]);
      setLoading(false);
      return;
    }

    const source = files[0];
    sourceRef.current = source;
    requestedBatches.current = {};
    let disposed = false;
    setLoading(true);
    void engineRpc<PdfPagesMetadataResult>("get_pdf_pages_metadata", { pdfPath: source })
      .then((metadata) => {
        if (disposed) return;
        const next = metadata.pages.map((page) => ({
          page_index: page.index,
          page_number: page.index + 1,
          rotation: page.rotation as PageRotation,
          thumbnail: "",
          width: page.width,
          height: page.height,
        }));
        setPages(next);
        setOriginal(next.map((page) => ({ ...page })));
      })
      .catch((error) => {
        if (!disposed) showToast("error", error instanceof Error ? error.message : "No se pudo leer el PDF.");
      })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [files, showToast]);

  const requestThumbnailBatch = useCallback((pageIndex: number) => {
    const source = files[0];
    if (!source || sourceRef.current !== source) return;
    const start = Math.floor(pageIndex / THUMBNAIL_BATCH_SIZE) * THUMBNAIL_BATCH_SIZE;
    const key = `${source}:${start}`;
    if (requestedBatches.current[key]) return;
    requestedBatches.current[key] = true;
    void engineRpc<PageThumbnailsResult>("get_page_thumbnails", {
      pdfPath: source,
      start,
      count: THUMBNAIL_BATCH_SIZE,
      maxWidth: 240,
      format: "png",
    }).then((result) => {
      if (sourceRef.current !== source) return;
      const thumbnails = new Map(result.pages.map((page) => [page.index, page]));
      const merge = (current: PageItem[]) => current.map((page) => {
        const thumbnail = thumbnails.get(page.page_index);
        return thumbnail ? { ...page, thumbnail: thumbnail.thumbUrl, width: thumbnail.width, height: thumbnail.height } : page;
      });
      setPages(merge);
      setOriginal(merge);
    }).catch(() => { requestedBatches.current[key] = false; });
  }, [files]);

  const changed = useMemo(
    () => pages.some((page, index) => page.page_index !== original[index]?.page_index || page.rotation !== original[index]?.rotation) || pages.length !== original.length,
    [original, pages],
  );

  function move(from: number, to: number) {
    if (from === to || from < 0 || to < 0 || from >= pages.length || to >= pages.length) return;
    setPages((current) => {
      const next = [...current];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  }

  function rotate(index: number) {
    setPages((current) => current.map((page, pageIndex) => pageIndex === index ? { ...page, rotation: (((page.rotation + 90) % 360) as PageRotation) } : page));
  }

  async function exportPdf() {
    if (files.length !== 1 || !pages.length || !outputDir) return;
    await add({
      id: crypto.randomUUID(),
      engine: "stirling_core",
      action: "apply_page_layout",
      inputFiles: files,
      outputDir,
      options: { source_pdf: files[0], pages: pages.map(({ page_index, rotation }) => ({ page_index, rotation })) },
    });
    showToast("success", "PDF organizado enviado a la cola.");
  }

  return (
    <div className="flex h-[calc(100vh-1rem)] min-h-0 w-full flex-col gap-3 p-6 lg:p-8">
      <div className="shrink-0"><button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft size={16} /> Volver al catalogo</button><div className="mt-3 flex items-start gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-500/15 text-violet-300"><PanelsTopLeft size={18} /></div><div><p className="eyebrow">Stirling-PDF Core - Organizador visual</p><h1 className="text-xl font-bold">Organizar y Rotar Paginas</h1><p className="mt-0.5 text-sm text-muted-foreground">Reordena, gira o excluye paginas sin modificar el original.</p></div></div></div>
      <Card className="shrink-0 p-4"><FileDrop tool={organizerTool} files={files} onChange={setFiles} outputDir={outputDir} onOutputDirChange={setOutputDir} /></Card>
      <Card className="min-h-0 flex-1 overflow-hidden p-3">
        {loading ? <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground"><LoaderCircle size={17} className="animate-spin" /> Leyendo paginas...</div> : pages.length === 0 ? <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Selecciona un PDF para cargar sus paginas.</div> : <div className="grid min-h-0 h-full auto-rows-max grid-cols-[repeat(auto-fill,minmax(120px,1fr))] content-start gap-3 overflow-y-auto p-2">{pages.map((page, index) => <LazyPageCard key={`${page.page_index}-${index}`} page={page} index={index} dragIndex={dragIndex} onVisible={requestThumbnailBatch} onMove={move} onRotate={rotate} onDelete={(pageIndex) => setPages((current) => current.filter((_, currentIndex) => currentIndex !== pageIndex))} setDragIndex={setDragIndex} />)}</div>}
      </Card>
      <div className="sticky bottom-0 z-10 flex shrink-0 items-center justify-between gap-3 border-t bg-background/95 py-3 backdrop-blur"><span className="text-xs text-muted-foreground">{pages.length ? `${pages.length} pagina(s) - arrastra para reordenar` : "Sin paginas cargadas"}</span><div className="flex gap-2"><Button type="button" variant="outline" disabled={!pages.length || !changed} onClick={() => setPages(original.map((page) => ({ ...page })))}><RotateCcw size={15} /> Restablecer orden original</Button><Button type="button" disabled={!pages.length || !outputDir} onClick={() => void exportPdf()}><Play size={15} /> Exportar PDF Organizado</Button></div></div>
    </div>
  );
}

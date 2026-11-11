import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, RotateCw, Trash2, PanelsTopLeft, Play, RotateCcw, LoaderCircle } from "lucide-react";
import { toolById } from "@/catalog/tools";
import type { OrganizerThumbnail, PageRotation } from "@/contracts/rpc";
import FileDrop from "@/components/FileDrop";
import { Button, Card } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { useJobs } from "@/store/jobs";

interface Props { onBack: () => void; }
type PageItem = OrganizerThumbnail;
const organizerTool = toolById("page_organizer")!;

function parentOf(path: string) {
  const match = path.match(/^(.+)[\\/][^\\/]+$/);
  return match?.[1] ?? path;
}

export default function PageOrganizerView({ onBack }: Props) {
  const add = useJobs((state) => state.add);
  const jobs = useJobs((state) => state.jobs);
  const showToast = useToast((state) => state.show);
  const [files, setFiles] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useState("");
  const [pages, setPages] = useState<PageItem[]>([]);
  const [original, setOriginal] = useState<PageItem[]>([]);
  const [thumbnailJobId, setThumbnailJobId] = useState<string | null>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (files.length !== 1) {
      setPages([]);
      setOriginal([]);
      setThumbnailJobId(null);
      return;
    }
    const id = crypto.randomUUID();
    setLoading(true);
    setThumbnailJobId(id);
    void add({
      id,
      engine: "stirling_core",
      action: "get_pdf_thumbnails",
      inputFiles: files,
      outputDir: outputDir || parentOf(files[0]),
      options: {},
    });
  }, [add, files]);

  useEffect(() => {
    if (!thumbnailJobId) return;
    const job = jobs.find((entry) => entry.task.id === thumbnailJobId);
    if (!job) return;
    if (job.status === "error" || job.status === "cancelled") {
      setLoading(false);
      showToast("error", job.message);
      setThumbnailJobId(null);
      return;
    }
    if (job.status !== "success") return;
    const next = Array.isArray(job.meta?.pages) ? (job.meta.pages as PageItem[]) : [];
    setPages(next);
    setOriginal(next.map((page) => ({ ...page })));
    setLoading(false);
    setThumbnailJobId(null);
  }, [jobs, showToast, thumbnailJobId]);

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
      <div className="shrink-0">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft size={16} /> Volver al catálogo</button>
        <div className="mt-3 flex items-start gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-500/15 text-violet-300"><PanelsTopLeft size={18} /></div><div><p className="eyebrow">Stirling-PDF Core · Organizador visual</p><h1 className="text-xl font-bold">Organizar y Rotar Páginas</h1><p className="mt-0.5 text-sm text-muted-foreground">Reordena, gira o excluye páginas sin modificar el original.</p></div></div>
      </div>
      <Card className="shrink-0 p-4"><FileDrop tool={organizerTool} files={files} onChange={setFiles} outputDir={outputDir} onOutputDirChange={setOutputDir} /></Card>
      <Card className="min-h-0 flex-1 overflow-hidden p-3">
        {loading ? <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground"><LoaderCircle size={17} className="animate-spin" /> Renderizando miniaturas a 72 DPI…</div> : pages.length === 0 ? <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Selecciona un PDF para cargar sus páginas.</div> : <div className="grid min-h-0 h-full auto-rows-max grid-cols-[repeat(auto-fill,minmax(120px,1fr))] content-start gap-3 overflow-y-auto p-2">{pages.map((page, index) => <article key={`${page.page_index}-${index}`} draggable onDragStart={() => setDragIndex(index)} onDragOver={(event) => event.preventDefault()} onDrop={() => { if (dragIndex !== null) move(dragIndex, index); setDragIndex(null); }} className={`group relative w-[120px] justify-self-center rounded-lg border bg-background/40 p-1.5 transition ${dragIndex === index ? "border-primary opacity-60" : "hover:border-primary/60"}`}><img src={page.thumbnail} alt={`Página ${page.page_number}`} className="aspect-[0.72] w-full rounded bg-white object-contain" /><div className="flex items-center justify-between px-1 pt-1 text-[11px] text-muted-foreground"><span>Pág. {page.page_number}</span><span>{page.rotation}°</span></div><div className="absolute right-1.5 top-1.5 flex gap-1 opacity-0 transition group-hover:opacity-100"><button type="button" aria-label={`Rotar página ${page.page_number}`} onClick={() => rotate(index)} className="rounded-full bg-slate-900/85 p-1.5 text-white hover:bg-primary"><RotateCw size={13} /></button><button type="button" aria-label={`Eliminar página ${page.page_number}`} onClick={() => setPages((current) => current.filter((_, pageIndex) => pageIndex !== index))} className="rounded-full bg-slate-900/85 p-1.5 text-white hover:bg-red-500"><Trash2 size={13} /></button></div></article>)}</div>}
      </Card>
      <div className="sticky bottom-0 z-10 flex shrink-0 items-center justify-between gap-3 border-t bg-background/95 py-3 backdrop-blur"><span className="text-xs text-muted-foreground">{pages.length ? `${pages.length} página(s) · arrastra para reordenar` : "Sin páginas cargadas"}</span><div className="flex gap-2"><Button type="button" variant="outline" disabled={!pages.length || !changed} onClick={() => setPages(original.map((page) => ({ ...page })))}><RotateCcw size={15} /> Restablecer orden original</Button><Button type="button" disabled={!pages.length || !outputDir} onClick={() => void exportPdf()}><Play size={15} /> Exportar PDF Organizado</Button></div></div>
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { Clipboard, Download, FileText, FolderOpen, GripVertical, LoaderCircle, ZoomIn, ZoomOut } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github-dark.css";
import { engineRpc, revealInFolder } from "@/lib/engine";
import type { PdfPagesMetadataResult, ReadTextFileResult, RenderPageResult } from "@/contracts/rpc";
import { useToast } from "@/components/ui/toast";
import { Button, Card } from "@/components/ui/primitives";

export interface DoclingViewerRequest {
  sourcePdf: string;
  markdownPath: string;
}

const baseName = (path: string) => path.split(/[\\/]/).pop() ?? path;
const stemOf = (path: string) => baseName(path).replace(/\.[^.]+$/, "");

/** Builds the viewer request for a finished docling_parse job: the generated .md plus the
 *  input it came from (outputs are named "<stem>_docling_parse_N.md"). */
export function doclingViewerRequest(inputFiles: string[], outputFiles: string[]): DoclingViewerRequest | null {
  const markdownPath = outputFiles.find((path) => /\.md$/i.test(path));
  if (!markdownPath || inputFiles.length === 0) return null;
  const mdName = baseName(markdownPath).toLowerCase();
  const sourcePdf =
    inputFiles.find((path) => mdName.startsWith(`${stemOf(path).toLowerCase()}_docling_parse`)) ??
    inputFiles.find((path) => /\.pdf$/i.test(path)) ??
    inputFiles[0];
  return { sourcePdf, markdownPath };
}

interface Props extends DoclingViewerRequest {
  onClose?: () => void;
}

const splitKey = "docforge.docling.viewer.split";
const DEFAULT_SPLIT = 50;
const clampSplit = (value: number) => Math.max(20, Math.min(80, value));

function readStoredSplit() {
  try {
    const raw = localStorage.getItem(splitKey);
    const stored = raw === null ? NaN : Number(raw);
    return Number.isFinite(stored) && stored >= 20 && stored <= 80 ? stored : DEFAULT_SPLIT;
  } catch {
    return DEFAULT_SPLIT;
  }
}

export default function DoclingDualViewer({ sourcePdf, markdownPath, onClose }: Props) {
  const [markdown, setMarkdown] = useState("");
  const [pageCount, setPageCount] = useState(0);
  const [page, setPage] = useState(0);
  const [image, setImage] = useState<RenderPageResult | null>(null);
  const [tab, setTab] = useState<"rendered" | "raw">("rendered");
  const [split, setSplit] = useState(readStoredSplit);
  const splitContainer = useRef<HTMLDivElement>(null);
  const [resizing, setResizing] = useState(false);
  const [loadingMarkdown, setLoadingMarkdown] = useState(true);
  const [loadingPage, setLoadingPage] = useState(false);
  const [zoom, setZoom] = useState(1);
  const showToast = useToast((state) => state.show);
  const isPdf = /\.pdf$/i.test(sourcePdf);
  const sourceName = useMemo(() => sourcePdf.split(/[\\/]/).pop() ?? sourcePdf, [sourcePdf]);

  useEffect(() => {
    let cancelled = false;
    setLoadingMarkdown(true);
    setMarkdown("");
    void engineRpc<ReadTextFileResult>("read_text_file", { path: markdownPath, maxBytes: 20 * 1024 * 1024 })
      .then((result) => { if (!cancelled) setMarkdown(result.content); })
      .catch((error) => { if (!cancelled) showToast("error", error instanceof Error ? error.message : "No se pudo leer el Markdown."); })
      .finally(() => { if (!cancelled) setLoadingMarkdown(false); });
    return () => { cancelled = true; };
  }, [markdownPath, showToast]);

  useEffect(() => {
    if (!isPdf) return;
    let cancelled = false;
    void engineRpc<PdfPagesMetadataResult>("get_pdf_pages_metadata", { pdfPath: sourcePdf })
      .then((result) => { if (!cancelled) setPageCount(result.pageCount); })
      .catch((error) => { if (!cancelled) showToast("error", error instanceof Error ? error.message : "No se pudo leer el PDF."); });
    return () => { cancelled = true; };
  }, [isPdf, showToast, sourcePdf]);

  useEffect(() => {
    if (!isPdf || pageCount === 0) return;
    let cancelled = false;
    setLoadingPage(true);
    void engineRpc<RenderPageResult>("render_page", { pdfPath: sourcePdf, index: page, maxWidth: 1100 })
      .then((result) => { if (!cancelled) setImage(result); })
      .catch((error) => { if (!cancelled) showToast("error", error instanceof Error ? error.message : "No se pudo renderizar la página."); })
      .finally(() => { if (!cancelled) setLoadingPage(false); });
    return () => { cancelled = true; };
  }, [isPdf, page, pageCount, showToast, sourcePdf]);

  useEffect(() => {
    try {
      localStorage.setItem(splitKey, String(split));
    } catch {
      // Storage unavailable: the split simply is not remembered.
    }
  }, [split]);

  useEffect(() => {
    if (!resizing) return;
    // Measure against the split container, not the window: the nav and padding sit to its left.
    const onMove = (event: PointerEvent) => {
      const rect = splitContainer.current?.getBoundingClientRect();
      if (!rect || rect.width === 0) return;
      setSplit(clampSplit(((event.clientX - rect.left) / rect.width) * 100));
    };
    const onUp = () => setResizing(false);
    const previousSelect = document.body.style.userSelect;
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      document.body.style.userSelect = previousSelect;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [resizing]);

  async function copyMarkdown() {
    try {
      await navigator.clipboard.writeText(markdown);
      showToast("success", "Markdown copiado al portapapeles.");
    } catch {
      showToast("error", "No se pudo copiar el Markdown.");
    }
  }

  async function exportMarkdown() {
    const baseName = markdownPath.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, "") || "resultado";
    const targetPath = await save({ defaultPath: `${baseName}.md`, filters: [{ name: "Markdown", extensions: ["md"] }] });
    if (!targetPath) return;
    try {
      await engineRpc("export_file", { sourcePath: markdownPath, targetPath });
      showToast("success", "Markdown exportado correctamente.");
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "No se pudo exportar el Markdown.");
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Resultado Docling</p>
          <h1 className="mt-1 text-2xl font-bold">Visor dual</h1>
          <p className="mt-1 text-xs text-muted-foreground">{sourceName}</p>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={copyMarkdown}><Clipboard size={15} /> Copiar Markdown</Button>
          <Button type="button" variant="outline" onClick={exportMarkdown}><Download size={15} /> Exportar .md</Button>
          <Button type="button" variant="outline" onClick={() => void revealInFolder(markdownPath).catch(() => showToast("error", "No se pudo abrir el explorador."))}><FolderOpen size={15} /> Abrir en explorador</Button>
          {onClose && <Button type="button" variant="ghost" onClick={onClose}>Cerrar</Button>}
        </div>
      </div>
      <div ref={splitContainer} className="grid min-h-0 w-full flex-1 overflow-hidden rounded-xl border bg-card" style={{ gridTemplateColumns: `minmax(0, ${split}fr) 6px minmax(0, ${100 - split}fr)` }}>
        <section className="flex min-h-0 flex-col">
          <div className="flex items-center justify-between border-b px-4 py-3 text-xs">
            <span className="font-semibold">Documento original</span>
            {isPdf && <div className="flex items-center gap-2"><Button type="button" variant="ghost" className="h-7 w-7 p-0" disabled={!page} onClick={() => setPage((value) => Math.max(0, value - 1))}>‹</Button><span>Página {Math.min(page + 1, pageCount || 1)} / {pageCount || "—"}</span><Button type="button" variant="ghost" className="h-7 w-7 p-0" disabled={!pageCount || page >= pageCount - 1} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}>›</Button></div>}
          </div>
          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-auto bg-slate-100 p-5">
            {!isPdf ? <div className="max-w-xs text-center text-sm text-slate-600"><FileText className="mx-auto mb-3" size={30} />La fuente no es un PDF; el visor de páginas no está disponible.</div> : loadingPage ? <LoaderCircle className="animate-spin text-slate-500" /> : image ? <img src={image.imageUrl} alt={`Página ${page + 1}`} className="max-h-full object-contain shadow-lg transition-transform" style={{ width: `${zoom * 100}%`, maxWidth: "none" }} /> : <span className="text-sm text-slate-500">Esperando la página…</span>}
            {isPdf && <div className="absolute bottom-3 right-3 flex gap-1 rounded-md border bg-white/90 p-1 text-slate-700 shadow"><button type="button" title="Reducir" onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))} className="rounded p-1 hover:bg-slate-100"><ZoomOut size={14} /></button><span className="px-1 text-[11px] leading-6">{Math.round(zoom * 100)}%</span><button type="button" title="Ampliar" onClick={() => setZoom((value) => Math.min(2, value + 0.25))} className="rounded p-1 hover:bg-slate-100"><ZoomIn size={14} /></button></div>}
          </div>
        </section>
        <button type="button" aria-label="Redimensionar paneles" title="Arrastra para redimensionar · doble clic: 50/50" onPointerDown={(event) => { event.preventDefault(); setResizing(true); }} onDoubleClick={() => setSplit(DEFAULT_SPLIT)} className={`flex cursor-col-resize items-center justify-center bg-border hover:bg-primary ${resizing ? "bg-primary" : ""}`}><GripVertical size={14} /></button>
        <section className="flex min-h-0 flex-col">
          <div className="flex flex-wrap items-center gap-1 border-b px-4 py-2">
            <button type="button" onClick={() => setTab("rendered")} className={`rounded px-3 py-1.5 text-xs font-semibold ${tab === "rendered" ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent"}`}>Renderizado</button>
            <button type="button" onClick={() => setTab("raw")} className={`rounded px-3 py-1.5 text-xs font-semibold ${tab === "raw" ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent"}`}>Raw</button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-6">
            {loadingMarkdown ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="animate-spin" size={16} /> Leyendo Markdown…</div> : tab === "rendered" ? <article className="prose prose-invert max-w-none text-sm prose-headings:text-foreground prose-p:text-muted-foreground prose-a:text-primary prose-strong:text-foreground prose-table:w-full prose-th:border prose-th:border-border prose-th:bg-muted prose-th:p-2 prose-td:border prose-td:border-border prose-td:p-2 prose-blockquote:border-primary prose-blockquote:bg-muted/40 prose-blockquote:px-4 prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-pre:rounded-lg prose-pre:border prose-pre:border-border"><ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex, rehypeHighlight]}>{markdown}</ReactMarkdown></article> : <pre className="m-0 whitespace-pre-wrap font-mono text-xs leading-6 text-muted-foreground">{markdown.split("\n").map((line, index) => <span key={index} className="block"><span className="mr-4 inline-block w-8 select-none text-right text-muted-foreground/50">{index + 1}</span>{line}</span>)}</pre>}
          </div>
        </section>
      </div>
    </div>
  );
}

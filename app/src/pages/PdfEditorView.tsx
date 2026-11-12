import { useCallback, useEffect, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { open } from "@tauri-apps/plugin-dialog";
import { ChevronLeft, ChevronRight, Maximize2, PenTool, ZoomIn, ZoomOut } from "lucide-react";
import type { ToolDefinition } from "@/catalog/tools";
import FileDrop from "@/components/FileDrop";
import { Button, Card } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import ElementsPanel from "@/components/pdfEditor/ElementsPanel";
import PageLayer from "@/components/pdfEditor/PageLayer";
import Toolbar from "@/components/pdfEditor/Toolbar";
import { usePdfEditorStore } from "@/components/pdfEditor/store";
import type { EditorTool, PdfElement, PdfFont } from "@/components/pdfEditor/types";
import { engineRpc } from "@/lib/engine";
import { useJobs } from "@/store/jobs";
import { useOutputDir } from "@/store/outputDirs";
import type { ReadPdfBytesResult } from "@/contracts/rpc";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

const editorTool: ToolDefinition = {
  id: "pdf_editor", domain: "stirling", engine: "stirling_core", action: "apply_annotations", label: "Editar PDF",
  description: "Añade texto, imágenes y anotaciones a un PDF.", icon: PenTool, extensions: ["pdf"], multiFile: false, fields: [],
};

interface ReadFileBytesResult { data: string; size: number; mime: string }
interface PageSize { width: number; height: number }

function bytesFromBase64(data: string) {
  const binary = atob(data);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

export default function PdfEditorView() {
  const add = useJobs((state) => state.add);
  const showToast = useToast((state) => state.show);
  const [files, setFiles] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useOutputDir("pdf");
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [error, setError] = useState("");
  const [tool, setTool] = useState<EditorTool>("pointer");
  const [zoom, setZoom] = useState(1);
  const [imageSources, setImageSources] = useState<Record<string, string>>({});
  const [pageSizes, setPageSizes] = useState<Record<number, PageSize>>({});
  const [currentPage, setCurrentPage] = useState(0);
  const [scrollRoot, setScrollRoot] = useState<HTMLDivElement | null>(null);
  const [textDefaults, setTextDefaults] = useState({ font: "helv" as PdfFont, bold: false, italic: false, size: 16, color: "#111827" });
  const [strokeDefaults, setStrokeDefaults] = useState({ color: "#111827", width: 3 });
  const [shapeDefaults, setShapeDefaults] = useState({ color: "#111827", width: 3, fill: null as string | null });
  const [highlightColor, setHighlightColor] = useState("#facc15");
  const elements = usePdfEditorStore((state) => state.elements);
  const selectedId = usePdfEditorStore((state) => state.selectedId);
  const past = usePdfEditorStore((state) => state.past);
  const future = usePdfEditorStore((state) => state.future);
  const reset = usePdfEditorStore((state) => state.reset);
  const select = usePdfEditorStore((state) => state.select);
  const addElement = usePdfEditorStore((state) => state.add);
  const updateElement = usePdfEditorStore((state) => state.update);
  const removeElement = usePdfEditorStore((state) => state.remove);
  const commit = usePdfEditorStore((state) => state.commit);
  const moveUp = usePdfEditorStore((state) => state.moveUp);
  const moveDown = usePdfEditorStore((state) => state.moveDown);
  const undo = usePdfEditorStore((state) => state.undo);
  const redo = usePdfEditorStore((state) => state.redo);
  const selected = elements.find((element) => element.id === selectedId) ?? null;

  useEffect(() => {
    const path = files[0];
    setPdf(null); setCurrentPage(0); setPageSizes({}); setImageSources({}); select(null); reset();
    if (!path) return;
    let cancelled = false;
    setError("");
    void engineRpc<ReadPdfBytesResult>("read_pdf_bytes", { path })
      .then((result) => pdfjsLib.getDocument({ data: bytesFromBase64(result.data) }).promise)
      .then((loaded) => { if (!cancelled) setPdf(loaded); })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "No se pudo abrir el PDF."); });
    return () => { cancelled = true; };
  }, [files, reset, select]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); }
      else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") { event.preventDefault(); redo(); }
      else if (event.key === "Delete" && selectedId) { event.preventDefault(); removeElement(selectedId); }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [redo, undo, removeElement, selectedId]);

  const onPageSize = useCallback((page: number, size: PageSize) => setPageSizes((current) => ({ ...current, [page]: size })), []);
  const onPageVisible = useCallback((page: number) => setCurrentPage(page), []);
  const onSelectPanel = useCallback((id: string) => { select(id); document.getElementById(`pdf-canvas-element-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [select]);

  function updateSelected(patch: Partial<PdfElement>) {
    if (!selected) return;
    updateElement(selected.id, (element) => ({ ...element, ...patch } as PdfElement));
    // Keep the matching tool's defaults in sync so the next stroke/shape uses the same style.
    syncDefaults(selected.kind, patch);
  }

  function updateTool(patch: Partial<PdfElement>) {
    syncDefaults(tool, patch);
  }

  function syncDefaults(target: EditorTool | PdfElement["kind"], patch: Partial<PdfElement>) {
    if (target === "image" || target === "pointer") return;
    if ("font" in patch && patch.font) setTextDefaults((current) => ({ ...current, font: patch.font as PdfFont }));
    if ("bold" in patch && typeof patch.bold === "boolean") setTextDefaults((current) => ({ ...current, bold: patch.bold as boolean }));
    if ("italic" in patch && typeof patch.italic === "boolean") setTextDefaults((current) => ({ ...current, italic: patch.italic as boolean }));
    if ("size" in patch && typeof patch.size === "number") setTextDefaults((current) => ({ ...current, size: patch.size as number }));
    if ("color" in patch && typeof patch.color === "string") {
      if (target === "highlight") setHighlightColor(patch.color);
      else if (target === "ink") setStrokeDefaults((current) => ({ ...current, color: patch.color as string }));
      else if (["rect", "ellipse", "arrow", "line"].includes(target)) setShapeDefaults((current) => ({ ...current, color: patch.color as string }));
      else setTextDefaults((current) => ({ ...current, color: patch.color as string }));
    }
    if ("width" in patch && typeof patch.width === "number") {
      if (target === "ink") setStrokeDefaults((current) => ({ ...current, width: patch.width as number }));
      else setShapeDefaults((current) => ({ ...current, width: patch.width as number }));
    }
    if ("fill" in patch) setShapeDefaults((current) => ({ ...current, fill: (patch.fill as string | null | undefined) ?? null }));
  }

  function changeTool(next: EditorTool) {
    setTool(next);
    // Drawing tools edit their own defaults: drop any selection so the properties bar targets the tool.
    if (next !== "pointer") select(null);
  }

  function scrollToPage(page: number) {
    const next = Math.max(0, Math.min((pdf?.numPages ?? 1) - 1, page));
    setCurrentPage(next);
    document.getElementById(`pdf-editor-page-${next + 1}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function fitWidth() {
    if (!scrollRoot || !Object.keys(pageSizes).length) return;
    const widest = Math.max(...Object.values(pageSizes).map((size) => size.width));
    const available = Math.max(320, scrollRoot.clientWidth - 32);
    const fit = Math.min(1, available / Math.max(widest, 1));
    setZoom(Math.max(0.25, Math.min(3, fit)));
  }

  async function chooseImage() {
    try {
      const selectedPath = await open({ multiple: false, filters: [{ name: "Imagen", extensions: ["png", "jpg", "jpeg"] }] });
      const path = typeof selectedPath === "string" ? selectedPath : null;
      if (!path) return;
      const result = await engineRpc<ReadFileBytesResult>("read_file_bytes", { path });
      const src = `data:${result.mime};base64,${result.data}`;
      setImageSources((current) => ({ ...current, [path]: src }));
      const image = new Image();
      image.onload = () => {
        const page = pageSizes[currentPage] ?? { width: 612, height: 792 };
        const w = page.width * 0.4;
        const h = w * image.naturalHeight / Math.max(image.naturalWidth, 1);
        // Inserted images stay selected (in Selección) so they can be moved/resized right away.
        setTool("pointer");
        addElement({ id: crypto.randomUUID(), page: currentPage, kind: "image", x: (page.width - w) / 2, y: (page.height - h) / 2, w, h, path }, true);
      };
      image.src = src;
    } catch (reason) { showToast("error", reason instanceof Error ? reason.message : "No se pudo cargar la imagen."); }
  }

  async function exportPdf() {
    if (!files[0] || !outputDir || !elements.length) return;
    await add({ id: crypto.randomUUID(), engine: "stirling_core", action: "apply_annotations", inputFiles: [files[0]], outputDir, options: { annotations: elements } });
    showToast("success", "Exportación del PDF enviada. Sigue el progreso en Actividad.");
  }

  return <div className="w-full space-y-4 p-6 lg:p-8">
    <div className="flex items-start gap-4"><div className="rounded-lg bg-primary/10 p-2 text-primary"><PenTool size={18} /></div><div><p className="eyebrow">Herramientas PDF</p><h1 className="text-xl font-bold">Editar PDF</h1><p className="mt-0.5 text-sm text-muted-foreground">Edita texto, imágenes y anotaciones sin salir de CALCO.</p></div></div>
    <Card className="space-y-4 p-4">
      <FileDrop tool={editorTool} files={files} onChange={setFiles} outputDir={outputDir} onOutputDirChange={setOutputDir} />
      <Toolbar tool={tool} selected={selected} textDefaults={textDefaults} strokeDefaults={strokeDefaults} shapeDefaults={shapeDefaults} highlightColor={highlightColor} canUndo={past.length > 0} canRedo={future.length > 0} exportDisabled={!files[0] || !outputDir || !elements.length} onExport={() => void exportPdf()} onTool={changeTool} onImage={() => void chooseImage()} onUpdateSelected={updateSelected} onUpdateTool={updateTool} onUndo={undo} onRedo={redo} onDelete={() => selectedId && removeElement(selectedId)} />
      {error && <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p>}
      {pdf ? <div className="flex flex-col lg:flex-row">
        <div ref={setScrollRoot} onWheel={(event) => { if (event.ctrlKey) { event.preventDefault(); setZoom((value) => Math.max(0.25, Math.min(3, value * (event.deltaY < 0 ? 1.1 : 0.9)))); } }} className="relative min-w-0 flex-1 overflow-auto rounded-lg bg-slate-900/70 p-4"><div className="mx-auto max-w-5xl pb-16">{Array.from({ length: pdf.numPages }, (_, index) => <PageLayer key={index + 1} document={pdf} pageNumber={index + 1} zoom={zoom} tool={tool} elements={elements} selectedId={selectedId} imageSources={imageSources} textDefaults={textDefaults} strokeDefaults={strokeDefaults} shapeDefaults={shapeDefaults} highlightColor={highlightColor} scrollRoot={scrollRoot} onSelect={select} onAdd={addElement} onUpdate={updateElement} onCommit={commit} onPageVisible={onPageVisible} onPageSize={onPageSize} />)}</div><div className="absolute bottom-3 right-3 z-20 flex w-fit items-center gap-1 rounded-full border bg-card/95 p-1.5 shadow-xl backdrop-blur"><Button type="button" size="icon-sm" variant="ghost" className="bg-muted/60 hover:bg-accent" onClick={() => scrollToPage(currentPage - 1)} disabled={currentPage <= 0} title="Página anterior" aria-label="Página anterior"><ChevronLeft size={16} /></Button><span className="min-w-16 text-center text-xs tabular-nums">{currentPage + 1} / {pdf.numPages}</span><Button type="button" size="icon-sm" variant="ghost" className="bg-muted/60 hover:bg-accent" onClick={() => scrollToPage(currentPage + 1)} disabled={currentPage >= pdf.numPages - 1} title="Página siguiente" aria-label="Página siguiente"><ChevronRight size={16} /></Button><span className="mx-1 h-5 w-px bg-border" /><Button type="button" size="icon-sm" variant="ghost" className="bg-muted/60 hover:bg-accent" onClick={() => setZoom((value) => Math.max(0.25, Math.round((value - 0.1) * 10) / 10))} title="Alejar" aria-label="Alejar"><ZoomOut size={16} /></Button><span className="min-w-12 text-center text-xs tabular-nums">{Math.round(zoom * 100)}%</span><Button type="button" size="icon-sm" variant="ghost" className="bg-muted/60 hover:bg-accent" onClick={() => setZoom((value) => Math.min(3, Math.round((value + 0.1) * 10) / 10))} title="Acercar" aria-label="Acercar"><ZoomIn size={16} /></Button><Button type="button" size="icon-sm" variant="ghost" className="bg-muted/60 hover:bg-accent" onClick={fitWidth} title="Ajustar ancho" aria-label="Ajustar ancho"><Maximize2 size={16} /></Button></div></div>
        <ElementsPanel elements={elements} page={currentPage} pageCount={pdf.numPages} selectedId={selectedId} onSelect={onSelectPanel} onUp={moveUp} onDown={moveDown} onRemove={removeElement} />
      </div> : <p className="py-8 text-center text-sm text-muted-foreground">Selecciona un PDF para comenzar.</p>}
    </Card>
  </div>;
}

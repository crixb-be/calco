import { useEffect, useReducer, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  Highlighter,
  MousePointer2,
  Pencil,
  PenTool,
  Trash2,
  Type,
  Undo2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { ToolDefinition } from "@/catalog/tools";
import FileDrop from "@/components/FileDrop";
import { Button, Card, Input, Label } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { engineRpc } from "@/lib/engine";
import { useJobs } from "@/store/jobs";
import { useOutputDir } from "@/store/outputDirs";
import type { ReadPdfBytesResult } from "@/contracts/rpc";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export type Annot =
  | { id: string; page: number; kind: "text"; x: number; y: number; text: string; size: number; color: string }
  | { id: string; page: number; kind: "ink"; points: [number, number][]; color: string; width: number }
  | { id: string; page: number; kind: "highlight"; x: number; y: number; w: number; h: number; color: string };

type EditorState = { annotations: Annot[]; past: Annot[][]; future: Annot[][] };
type EditorAction =
  | { type: "reset" }
  | { type: "add"; annotation: Annot }
  | { type: "remove"; id: string }
  | { type: "move"; id: string; dx: number; dy: number }
  | { type: "commit"; before: Annot[] }
  | { type: "undo" };

const initialEditorState: EditorState = { annotations: [], past: [], future: [] };
const cloneAnnotations = (annotations: Annot[]) => annotations.map((annotation) => ({ ...annotation, ...(annotation.kind === "ink" ? { points: annotation.points.map((point) => [...point] as [number, number]) } : {}) })) as Annot[];
function commit(state: EditorState, annotations: Annot[]): EditorState {
  return { annotations, past: [...state.past, cloneAnnotations(state.annotations)], future: [] };
}
function editorReducer(state: EditorState, action: EditorAction): EditorState {
  if (action.type === "reset") return initialEditorState;
  if (action.type === "add") return commit(state, [...state.annotations, action.annotation]);
  if (action.type === "remove") return commit(state, state.annotations.filter((annotation) => annotation.id !== action.id));
  if (action.type === "move") {
    return {
      ...state,
      annotations: state.annotations.map((annotation) => {
        if (annotation.id !== action.id) return annotation;
        if (annotation.kind === "ink") return { ...annotation, points: annotation.points.map(([x, y]) => [x + action.dx, y + action.dy] as [number, number]) };
        return { ...annotation, x: annotation.x + action.dx, y: annotation.y + action.dy };
      }),
    };
  }
  if (action.type === "commit") {
    return { ...state, past: [...state.past, cloneAnnotations(action.before)], future: [] };
  }
  if (!state.past.length) return state;
  const previous = state.past[state.past.length - 1];
  return { annotations: cloneAnnotations(previous), past: state.past.slice(0, -1), future: [cloneAnnotations(state.annotations), ...state.future] };
}

const editorTool: ToolDefinition = {
  id: "pdf_editor",
  domain: "stirling",
  engine: "stirling_core",
  action: "apply_annotations",
  label: "Editar PDF",
  description: "Añade texto, trazos y resaltados a un PDF.",
  icon: PenTool,
  extensions: ["pdf"],
  multiFile: false,
  fields: [],
};

type ActiveTool = "pointer" | "text" | "ink" | "highlight";
interface PageProps {
  document: pdfjsLib.PDFDocumentProxy;
  pageNumber: number;
  zoom: number;
  tool: ActiveTool;
  annotations: Annot[];
  selectedId: string | null;
  textSize: number;
  textColor: string;
  inkColor: string;
  inkWidth: number;
  highlightColor: string;
  onSelect: (id: string | null) => void;
  onAdd: (annotation: Annot) => void;
  onMove: (id: string, dx: number, dy: number) => void;
  onCommitMove: (before: Annot[]) => void;
}

function pointFromEvent(event: React.PointerEvent, element: HTMLElement, scale: number): [number, number] {
  const rect = element.getBoundingClientRect();
  return [(event.clientX - rect.left) / scale, (event.clientY - rect.top) / scale];
}

function distanceToSegment(point: [number, number], a: [number, number], b: [number, number]) {
  const [px, py] = point;
  const [ax, ay] = a;
  const [bx, by] = b;
  const dx = bx - ax;
  const dy = by - ay;
  const ratio = dx * dx + dy * dy ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy))) : 0;
  return Math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy));
}

function hitTest(annotations: Annot[], point: [number, number]): Annot | undefined {
  return [...annotations].reverse().find((annotation) => {
    if (annotation.kind === "highlight") return point[0] >= annotation.x && point[0] <= annotation.x + annotation.w && point[1] >= annotation.y && point[1] <= annotation.y + annotation.h;
    if (annotation.kind === "text") return point[0] >= annotation.x - 4 && point[0] <= annotation.x + Math.max(annotation.size * 2, annotation.text.length * annotation.size * 0.65) && point[1] >= annotation.y - 4 && point[1] <= annotation.y + annotation.size * 1.5;
    return annotation.points.some((pointItem, index) => index > 0 && distanceToSegment(point, annotation.points[index - 1], pointItem) <= Math.max(6, annotation.width * 2));
  });
}

function PageCanvas(props: PageProps) {
  const { document, pageNumber, zoom, tool, annotations, selectedId, textSize, textColor, inkColor, inkWidth, highlightColor, onSelect, onAdd, onMove, onCommitMove } = props;
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [availableWidth, setAvailableWidth] = useState(820);
  const [baseViewport, setBaseViewport] = useState<{ width: number; height: number } | null>(null);
  const [textDraft, setTextDraft] = useState<[number, number] | null>(null);
  const [textValue, setTextValue] = useState("");
  const [drawing, setDrawing] = useState<[number, number][]>([]);
  const dragRef = useRef<{ id: string; start: [number, number]; before: Annot[]; moved: boolean } | null>(null);
  const textRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const observer = new ResizeObserver(() => setAvailableWidth(Math.max(360, host.clientWidth)));
    observer.observe(host);
    setAvailableWidth(Math.max(360, host.clientWidth));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    void document.getPage(pageNumber).then((page) => {
      if (!cancelled) {
        const viewport = page.getViewport({ scale: 1 });
        setBaseViewport({ width: viewport.width, height: viewport.height });
      }
    });
    return () => { cancelled = true; };
  }, [document, pageNumber]);

  const cssWidth = baseViewport ? Math.min(availableWidth, 980) * zoom : 0;
  const scale = baseViewport && baseViewport.width ? cssWidth / baseViewport.width : 1;
  const width = baseViewport ? baseViewport.width * scale : 0;
  const height = baseViewport ? baseViewport.height * scale : 0;
  const pageAnnotations = annotations.filter((annotation) => annotation.page === pageNumber - 1);

  useEffect(() => {
    if (!canvasRef.current || !baseViewport) return;
    let cancelled = false;
    let renderTask: { cancel: () => void; promise: Promise<void> } | undefined;
    void document.getPage(pageNumber).then((page) => {
      if (cancelled || !canvasRef.current) return;
      const viewport = page.getViewport({ scale });
      const ratio = window.devicePixelRatio || 1;
      const canvas = canvasRef.current;
      canvas.width = Math.ceil(viewport.width * ratio);
      canvas.height = Math.ceil(viewport.height * ratio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      const context = canvas.getContext("2d");
      if (!context) return;
      renderTask = page.render({ canvas, canvasContext: context, viewport, transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined });
    });
    return () => { cancelled = true; renderTask?.cancel(); };
  }, [baseViewport, document, pageNumber, scale]);

  useEffect(() => {
    if (textDraft) textRef.current?.focus();
  }, [textDraft]);

  function commitText() {
    if (!textDraft || !textValue.trim()) {
      setTextDraft(null);
      setTextValue("");
      return;
    }
    onAdd({ id: crypto.randomUUID(), page: pageNumber - 1, kind: "text", x: textDraft[0], y: textDraft[1], text: textValue, size: Math.max(8, Math.min(72, textSize)), color: textColor });
    setTextDraft(null);
    setTextValue("");
  }

  function down(event: React.PointerEvent<HTMLDivElement>) {
    if (!baseViewport) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = pointFromEvent(event, event.currentTarget, scale);
    if (tool === "text") {
      setTextDraft(point);
      setTextValue("");
    } else if (tool === "ink" || tool === "highlight") {
      setDrawing([point]);
    } else {
      const hit = hitTest(pageAnnotations, point);
      onSelect(hit?.id ?? null);
      if (hit) dragRef.current = { id: hit.id, start: point, before: annotations, moved: false };
    }
  }
  function move(event: React.PointerEvent<HTMLDivElement>) {
    const point = pointFromEvent(event, event.currentTarget, scale);
    if (drawing.length && tool === "ink") setDrawing((current) => [...current, point]);
    if (drawing.length && tool === "highlight") setDrawing((current) => [current[0], point]);
    const drag = dragRef.current;
    if (drag) {
      const dx = point[0] - drag.start[0];
      const dy = point[1] - drag.start[1];
      drag.moved = Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5;
      onMove(drag.id, dx - (drag.moved ? 0 : dx), dy - (drag.moved ? 0 : dy));
      if (drag.moved) {
        drag.start = point;
      }
    }
  }
  function up(event: React.PointerEvent<HTMLDivElement>) {
    const point = pointFromEvent(event, event.currentTarget, scale);
    if (drawing.length && tool === "ink" && drawing.length > 1) onAdd({ id: crypto.randomUUID(), page: pageNumber - 1, kind: "ink", points: drawing, color: inkColor, width: inkWidth });
    if (drawing.length && tool === "highlight") {
      const [start] = drawing;
      onAdd({ id: crypto.randomUUID(), page: pageNumber - 1, kind: "highlight", x: Math.min(start[0], point[0]), y: Math.min(start[1], point[1]), w: Math.abs(point[0] - start[0]), h: Math.abs(point[1] - start[1]), color: highlightColor });
    }
    setDrawing([]);
    if (dragRef.current) {
      if (dragRef.current.moved) onCommitMove(dragRef.current.before);
      dragRef.current = null;
    }
  }

  return <div ref={hostRef} className="relative mx-auto mb-6 w-full overflow-visible rounded-md shadow-xl">
    {baseViewport && <>
      <canvas ref={canvasRef} className="block bg-white" style={{ width, height }} />
      <div className="absolute left-0 top-0" style={{ width, height }} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        <svg width={width} height={height} viewBox={`0 0 ${baseViewport.width} ${baseViewport.height}`} className="absolute inset-0 h-full w-full">
          {pageAnnotations.map((annotation) => {
            const selected = annotation.id === selectedId;
            if (annotation.kind === "text") return <text key={annotation.id} x={annotation.x} y={annotation.y + annotation.size} fill={annotation.color} fontSize={annotation.size} className={selected ? "stroke-cyan-500" : ""}>{annotation.text.split("\n").map((line, index) => <tspan key={index} x={annotation.x} dy={index === 0 ? 0 : annotation.size * 1.2}>{line}</tspan>)}</text>;
            if (annotation.kind === "ink") return <polyline key={annotation.id} points={annotation.points.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke={annotation.color} strokeWidth={annotation.width} strokeLinecap="round" strokeLinejoin="round" className={selected ? "stroke-cyan-500" : ""} />;
            return <rect key={annotation.id} x={annotation.x} y={annotation.y} width={annotation.w} height={annotation.h} fill={annotation.color} fillOpacity=".35" stroke={selected ? "#06b6d4" : "none"} strokeWidth={selected ? 2 : 0} />;
          })}
          {drawing.length > 1 && tool === "ink" && <polyline points={drawing.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke={inkColor} strokeWidth={inkWidth} strokeLinecap="round" strokeLinejoin="round" />}
          {drawing.length > 1 && tool === "highlight" && <rect x={Math.min(drawing[0][0], drawing[1][0])} y={Math.min(drawing[0][1], drawing[1][1])} width={Math.abs(drawing[1][0] - drawing[0][0])} height={Math.abs(drawing[1][1] - drawing[0][1])} fill={highlightColor} fillOpacity=".35" />}
        </svg>
        {textDraft && <input ref={textRef} value={textValue} onChange={(event) => setTextValue(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); commitText(); } }} onBlur={commitText} className="absolute z-10 h-8 rounded border border-cyan-400 bg-white px-1 text-black outline-none" style={{ left: textDraft[0] * scale, top: textDraft[1] * scale, fontSize: textSize * scale }} />}
      </div>
    </>}
  </div>;
}

export default function PdfEditorView() {
  const add = useJobs((state) => state.add);
  const showToast = useToast((state) => state.show);
  const [files, setFiles] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useOutputDir("pdf");
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [error, setError] = useState("");
  const [tool, setTool] = useState<ActiveTool>("pointer");
  const [textSize, setTextSize] = useState(16);
  const [textColor, setTextColor] = useState("#111827");
  const [inkColor, setInkColor] = useState("#111827");
  const [inkWidth, setInkWidth] = useState(3);
  const [highlightColor, setHighlightColor] = useState("#facc15");
  const [zoom, setZoom] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [state, dispatch] = useReducer(editorReducer, initialEditorState);

  useEffect(() => {
    const path = files[0];
    setPdf(null);
    setSelectedId(null);
    dispatch({ type: "reset" });
    if (!path) return;
    let cancelled = false;
    setError("");
    void engineRpc<ReadPdfBytesResult>("read_pdf_bytes", { path })
      .then((result) => {
        if (cancelled) return;
        const binary = atob(result.data);
        const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
        return pdfjsLib.getDocument({ data: bytes }).promise;
      })
      .then((loaded) => {
        if (!cancelled && loaded) setPdf(loaded);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "No se pudo abrir el PDF.");
      });
    return () => { cancelled = true; };
  }, [files]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Delete" && selectedId) {
        dispatch({ type: "remove", id: selectedId });
        setSelectedId(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedId]);

  async function exportPdf() {
    if (!files[0] || !outputDir || !state.annotations.length) return;
    await add({ id: crypto.randomUUID(), engine: "stirling_core", action: "apply_annotations", inputFiles: [files[0]], outputDir, options: { annotations: state.annotations } });
    showToast("success", "Exportación del PDF enviada. Sigue el progreso en Actividad.");
  }

  const toolButton = (value: ActiveTool, label: string, Icon: typeof MousePointer2) => <Button type="button" variant={tool === value ? "default" : "outline"} className="h-9 px-3" onClick={() => setTool(value)}><Icon size={15} /> {label}</Button>;
  return <div className="w-full space-y-4 p-6 lg:p-8">
    <div className="flex items-start gap-4"><div className="rounded-lg bg-primary/10 p-2 text-primary"><PenTool size={22} /></div><div><p className="eyebrow">Stirling-PDF Core</p><h1 className="text-xl font-bold">Editar PDF</h1><p className="mt-0.5 text-sm text-muted-foreground">Añade texto, trazos y resaltados sin salir de DocForge.</p></div></div>
    <Card className="space-y-4 p-4">
      <FileDrop tool={editorTool} files={files} onChange={setFiles} outputDir={outputDir} onOutputDirChange={setOutputDir} />
      <div className="sticky top-0 z-20 flex flex-wrap items-center gap-2 border-t bg-card/95 py-3 backdrop-blur">
        {toolButton("pointer", "Puntero / Selección", MousePointer2)}
        {toolButton("text", "Texto", Type)}
        {toolButton("ink", "Lápiz", Pencil)}
        {toolButton("highlight", "Resaltador", Highlighter)}
        {tool === "text" && <><Label htmlFor="pdf-text-size" className="mb-0 ml-2">Tamaño</Label><Input id="pdf-text-size" type="number" min={8} max={72} value={textSize} onChange={(event) => setTextSize(Math.max(8, Math.min(72, Number(event.target.value) || 16)))} className="h-9 w-20" /><Input aria-label="Color de texto" type="color" value={textColor} onChange={(event) => setTextColor(event.target.value)} className="h-9 w-12 p-1" /></>}
        {tool === "ink" && <><Input aria-label="Color del lápiz" type="color" value={inkColor} onChange={(event) => setInkColor(event.target.value)} className="h-9 w-12 p-1" /><Input aria-label="Ancho del lápiz" type="number" min={1} max={12} value={inkWidth} onChange={(event) => setInkWidth(Math.max(1, Math.min(12, Number(event.target.value) || 3)))} className="h-9 w-20" /></>}
        {tool === "highlight" && <Input aria-label="Color del resaltador" type="color" value={highlightColor} onChange={(event) => setHighlightColor(event.target.value)} className="h-9 w-12 p-1" />}
        <Button type="button" variant="outline" className="h-9 px-3" disabled={!state.past.length} onClick={() => dispatch({ type: "undo" })}><Undo2 size={15} /> Deshacer</Button>
        <Button type="button" variant="danger" className="h-9 px-3" disabled={!selectedId} onClick={() => { if (selectedId) dispatch({ type: "remove", id: selectedId }); setSelectedId(null); }}><Trash2 size={15} /> Borrar seleccionado</Button>
        <span className="ml-auto flex items-center gap-1"><Button type="button" variant="ghost" className="h-9 w-9 p-0" onClick={() => setZoom((value) => Math.max(.5, value - .1))}><ZoomOut size={15} /></Button><span className="w-12 text-center text-xs">{Math.round(zoom * 100)}%</span><Button type="button" variant="ghost" className="h-9 w-9 p-0" onClick={() => setZoom((value) => Math.min(2, value + .1))}><ZoomIn size={15} /></Button></span>
      </div>
      {error && <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p>}
      {pdf ? <div className="overflow-auto rounded-lg bg-slate-900/70 p-4"><div className="mx-auto max-w-5xl">{Array.from({ length: pdf.numPages }, (_, index) => <PageCanvas key={index + 1} document={pdf} pageNumber={index + 1} zoom={zoom} tool={tool} annotations={state.annotations} selectedId={selectedId} textSize={textSize} textColor={textColor} inkColor={inkColor} inkWidth={inkWidth} highlightColor={highlightColor} onSelect={setSelectedId} onAdd={(annotation) => dispatch({ type: "add", annotation })} onMove={(id, dx, dy) => dispatch({ type: "move", id, dx, dy })} onCommitMove={(before) => dispatch({ type: "commit", before })} />)}</div></div> : <p className="py-8 text-center text-sm text-muted-foreground">Selecciona un PDF para comenzar.</p>}
      <Button type="button" className="w-full" disabled={!files[0] || !outputDir || !state.annotations.length} onClick={() => void exportPdf()}><PenTool size={16} /> Exportar PDF editado</Button>
    </Card>
  </div>;
}

import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import type { EditorTool, ImageElement, PdfElement, TextElement } from "./types";
import { fontFamily } from "./types";

interface TextDefaults { font: TextElement["font"]; bold: boolean; italic: boolean; size: number; color: string }
interface StrokeDefaults { color: string; width: number }
interface PageLayerProps {
  document: pdfjsLib.PDFDocumentProxy;
  pageNumber: number;
  zoom: number;
  tool: EditorTool;
  elements: PdfElement[];
  selectedId: string | null;
  imageSources: Record<string, string>;
  textDefaults: TextDefaults;
  strokeDefaults: StrokeDefaults;
  shapeDefaults: StrokeDefaults & { fill: string | null };
  highlightColor: string;
  scrollRoot: HTMLDivElement | null;
  onSelect: (id: string | null) => void;
  onAdd: (element: PdfElement) => void;
  onUpdate: (id: string, updater: (element: PdfElement) => PdfElement, history?: boolean) => void;
  onCommit: (before: PdfElement[]) => void;
  onPageVisible: (page: number) => void;
  onPageSize: (page: number, size: { width: number; height: number }) => void;
}

type Point = [number, number];
type TextEditor = { id: string | null; x: number; y: number; w: number; value: string; font: TextElement["font"]; bold: boolean; italic: boolean; size: number; color: string };
type DragState = { id: string; last: Point; before: PdfElement[]; moved: boolean };
type ResizeState = { id: string; corner: string; start: Point; before: PdfElement[]; original: PdfElement };

function distanceToSegment(point: Point, a: Point, b: Point) {
  const [px, py] = point;
  const [ax, ay] = a;
  const [bx, by] = b;
  const dx = bx - ax;
  const dy = by - ay;
  const ratio = dx * dx + dy * dy ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy))) : 0;
  return Math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy));
}

function hitTest(elements: PdfElement[], point: Point): PdfElement | undefined {
  return [...elements].reverse().find((element) => {
    if (element.kind === "ink") return element.points.some((item, index) => index > 0 && distanceToSegment(point, element.points[index - 1], item) <= Math.max(6, element.width * 2));
    if (element.kind === "line" || element.kind === "arrow") return distanceToSegment(point, [element.x1, element.y1], [element.x2, element.y2]) <= Math.max(6, element.width * 2);
    if (element.kind === "text") {
      const lines = element.text.split("\n");
      const width = Math.max(element.w, ...lines.map((line) => line.length * element.size * 0.62), 24);
      return point[0] >= element.x - 4 && point[0] <= element.x + width + 4 && point[1] >= element.y - 4 && point[1] <= element.y + lines.length * element.size * 1.2 + 4;
    }
    return point[0] >= element.x && point[0] <= element.x + element.w && point[1] >= element.y && point[1] <= element.y + element.h;
  });
}

function moveElement(element: PdfElement, dx: number, dy: number): PdfElement {
  if (element.kind === "ink") return { ...element, points: element.points.map(([x, y]) => [x + dx, y + dy] as Point) };
  if (element.kind === "line" || element.kind === "arrow") return { ...element, x1: element.x1 + dx, y1: element.y1 + dy, x2: element.x2 + dx, y2: element.y2 + dy };
  return { ...element, x: element.x + dx, y: element.y + dy };
}

function resizeElement(original: PdfElement, corner: string, dx: number, dy: number): PdfElement {
  if (original.kind === "text") {
    const width = Math.max(24, original.w + (corner.includes("w") ? -dx : dx));
    return { ...original, x: corner.includes("w") ? original.x + original.w - width : original.x, w: width };
  }
  if (!["image", "rect", "ellipse", "highlight"].includes(original.kind)) return original;
  const source = original as ImageElement;
  let x = source.x;
  let y = source.y;
  let w = Math.max(8, source.w + (corner.includes("w") ? -dx : dx));
  let h = Math.max(8, source.h + (corner.includes("n") ? -dy : dy));
  if (corner.includes("w")) x = source.x + source.w - w;
  if (corner.includes("n")) y = source.y + source.h - h;
  if (original.kind === "image") {
    const ratio = source.w / Math.max(source.h, 1);
    h = w / ratio;
    if (corner.includes("n")) y = source.y + source.h - h;
  }
  return { ...original, x, y, w, h } as PdfElement;
}

export default function PageLayer({ document, pageNumber, zoom, tool, elements, selectedId, imageSources, textDefaults, strokeDefaults, shapeDefaults, highlightColor, scrollRoot, onSelect, onAdd, onUpdate, onCommit, onPageVisible, onPageSize }: PageLayerProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const [availableWidth, setAvailableWidth] = useState(760);
  const [baseViewport, setBaseViewport] = useState<{ width: number; height: number } | null>(null);
  const [textEditor, setTextEditor] = useState<TextEditor | null>(null);
  const [drawing, setDrawing] = useState<Point[]>([]);
  const dragRef = useRef<DragState | null>(null);
  const resizeRef = useRef<ResizeState | null>(null);
  const pageElements = elements.filter((element) => element.page === pageNumber - 1);
  const cssWidth = baseViewport ? Math.min(Math.max(availableWidth, 320), 980) * zoom : 0;
  const scale = baseViewport?.width ? cssWidth / baseViewport.width : 1;
  const width = baseViewport ? baseViewport.width * scale : 0;
  const height = baseViewport ? baseViewport.height * scale : 0;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const observer = new ResizeObserver(() => setAvailableWidth(Math.max(320, host.clientWidth)));
    observer.observe(host);
    setAvailableWidth(Math.max(320, host.clientWidth));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    void document.getPage(pageNumber).then((page) => {
      if (!cancelled) {
        const viewport = page.getViewport({ scale: 1 });
        setBaseViewport({ width: viewport.width, height: viewport.height });
        onPageSize(pageNumber - 1, { width: viewport.width, height: viewport.height });
      }
    });
    return () => { cancelled = true; };
  }, [document, pageNumber, onPageSize]);

  useEffect(() => {
    const node = hostRef.current;
    if (!node) return;
    const observer = new IntersectionObserver((entries) => {
      const entry = entries[0];
      if (entry?.isIntersecting) onPageVisible(pageNumber - 1);
    }, { root: scrollRoot, threshold: [0.25, 0.6] });
    observer.observe(node);
    return () => observer.disconnect();
  }, [onPageVisible, pageNumber, scrollRoot]);

  useEffect(() => {
    if (!canvasRef.current || !baseViewport) return;
    let cancelled = false;
    let renderTask: { cancel: () => void } | undefined;
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
      if (context) renderTask = page.render({ canvas, canvasContext: context, viewport, transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined });
    });
    return () => { cancelled = true; renderTask?.cancel(); };
  }, [baseViewport, document, pageNumber, scale]);

  useEffect(() => {
    if (!textEditor) return;
    const frame = requestAnimationFrame(() => {
      const textarea = textRef.current;
      if (!textarea) return;
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
      textarea.style.height = "auto";
      textarea.style.height = `${Math.max(30, textarea.scrollHeight)}px`;
    });
    return () => cancelAnimationFrame(frame);
  }, [textEditor]);

  function pointFromEvent(event: React.PointerEvent): Point {
    const rect = overlayRef.current!.getBoundingClientRect();
    return [(event.clientX - rect.left) / scale, (event.clientY - rect.top) / scale];
  }

  function beginText(point: Point, element?: TextElement) {
    setTextEditor(element ? { id: element.id, x: element.x, y: element.y, w: element.w, value: element.text, font: element.font, bold: element.bold, italic: element.italic, size: element.size, color: element.color } : { id: null, x: point[0], y: point[1], w: 220, value: "", font: textDefaults.font, bold: textDefaults.bold, italic: textDefaults.italic, size: textDefaults.size, color: textDefaults.color });
  }

  function commitText() {
    const draft = textEditor;
    if (!draft) return;
    setTextEditor(null);
    if (!draft.value.trim()) {
      if (draft.id) onSelect(draft.id);
      return;
    }
    if (draft.id) onUpdate(draft.id, (element) => element.kind === "text" ? { ...element, text: draft.value, w: draft.w } : element);
    else onAdd({ id: crypto.randomUUID(), page: pageNumber - 1, kind: "text", x: draft.x, y: draft.y, w: draft.w, text: draft.value, font: draft.font, bold: draft.bold, italic: draft.italic, size: draft.size, color: draft.color });
  }

  function cancelText() { setTextEditor(null); }

  function startResize(event: React.PointerEvent, element: PdfElement, corner: string) {
    event.preventDefault();
    event.stopPropagation();
    overlayRef.current?.setPointerCapture(event.pointerId);
    resizeRef.current = { id: element.id, corner, start: pointFromEvent(event), before: elements, original: element };
  }

  function down(event: React.PointerEvent<HTMLDivElement>) {
    if (!baseViewport) return;
    const point = pointFromEvent(event);
    if (tool === "text" || tool === "image") return;
    event.currentTarget.setPointerCapture(event.pointerId);
    if (tool === "ink" || tool === "highlight" || tool === "rect" || tool === "ellipse" || tool === "arrow" || tool === "line") {
      setDrawing([point]);
      return;
    }
    const hit = hitTest(pageElements, point);
    onSelect(hit?.id ?? null);
    if (hit) dragRef.current = { id: hit.id, last: point, before: elements, moved: false };
  }

  function move(event: React.PointerEvent<HTMLDivElement>) {
    const point = pointFromEvent(event);
    const resize = resizeRef.current;
    if (resize) {
      const dx = point[0] - resize.start[0];
      const dy = point[1] - resize.start[1];
      onUpdate(resize.id, () => resizeElement(resize.original, resize.corner, dx, dy), false);
      return;
    }
    if (drawing.length) {
      if (tool === "ink") setDrawing((current) => [...current, point]);
      else setDrawing((current) => [current[0], point]);
      return;
    }
    const drag = dragRef.current;
    if (drag) {
      const dx = point[0] - drag.last[0];
      const dy = point[1] - drag.last[1];
      if (Math.abs(dx) + Math.abs(dy) > 0.2) drag.moved = true;
      onUpdate(drag.id, (element) => moveElement(element, dx, dy), false);
      drag.last = point;
    }
  }

  function up(event: React.PointerEvent<HTMLDivElement>) {
    const point = pointFromEvent(event);
    const start = drawing[0];
    if (start && tool === "ink" && drawing.length > 1) onAdd({ id: crypto.randomUUID(), page: pageNumber - 1, kind: "ink", points: drawing, color: strokeDefaults.color, width: strokeDefaults.width });
    if (start && tool === "highlight") onAdd({ id: crypto.randomUUID(), page: pageNumber - 1, kind: "highlight", x: Math.min(start[0], point[0]), y: Math.min(start[1], point[1]), w: Math.abs(point[0] - start[0]), h: Math.abs(point[1] - start[1]), color: highlightColor });
    if (start && (tool === "rect" || tool === "ellipse")) onAdd({ id: crypto.randomUUID(), page: pageNumber - 1, kind: tool, x: Math.min(start[0], point[0]), y: Math.min(start[1], point[1]), w: Math.abs(point[0] - start[0]), h: Math.abs(point[1] - start[1]), color: shapeDefaults.color, width: shapeDefaults.width, fill: shapeDefaults.fill });
    if (start && (tool === "line" || tool === "arrow")) {
      const end = snapLine(start, point, event.shiftKey);
      onAdd(tool === "line" ? { id: crypto.randomUUID(), page: pageNumber - 1, kind: "line", x1: start[0], y1: start[1], x2: end[0], y2: end[1], color: shapeDefaults.color, width: shapeDefaults.width } : { id: crypto.randomUUID(), page: pageNumber - 1, kind: "arrow", x1: start[0], y1: start[1], x2: end[0], y2: end[1], color: shapeDefaults.color, width: shapeDefaults.width });
    }
    setDrawing([]);
    const resize = resizeRef.current;
    if (resize) { onCommit(resize.before); resizeRef.current = null; }
    const drag = dragRef.current;
    if (drag) { if (drag.moved) onCommit(drag.before); dragRef.current = null; }
    if (tool === "text") beginText(point);
  }

  const handles = (element: PdfElement) => {
    if (!selectedId || element.id !== selectedId || (element.kind !== "text" && element.kind !== "image" && element.kind !== "rect" && element.kind !== "ellipse" && element.kind !== "highlight")) return null;
    const x = element.x;
    const y = element.y;
    const w = element.w;
    const h = element.kind === "text" ? Math.max(element.size * 1.2, element.text.split("\n").length * element.size * 1.2) : element.h;
    return <>{["nw", "ne", "sw", "se"].map((corner) => <button key={corner} type="button" aria-label={`Redimensionar ${corner}`} onPointerDown={(event) => startResize(event, element, corner)} className="absolute z-20 h-2.5 w-2.5 rounded-sm border border-cyan-700 bg-cyan-300" style={{ left: (x + (corner.includes("e") ? w : 0)) * scale - 5, top: (y + (corner.includes("s") ? h : 0)) * scale - 5 }} />)}</>;
  };

  return <div id={`pdf-editor-page-${pageNumber}`} ref={hostRef} className="relative mx-auto mb-6 w-full overflow-visible rounded-md shadow-xl">
    {baseViewport && <>
      <canvas ref={canvasRef} className="block bg-white" style={{ width, height }} />
      <div ref={overlayRef} className="absolute left-0 top-0" style={{ width, height }} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        <svg width={width} height={height} viewBox={`0 0 ${baseViewport.width} ${baseViewport.height}`} className="pointer-events-none absolute inset-0 h-full w-full">
          {pageElements.map((element) => {
            const selected = element.id === selectedId;
            if (element.kind === "ink") return <polyline id={`pdf-canvas-element-${element.id}`} key={element.id} points={element.points.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke={element.color} strokeWidth={element.width} strokeLinecap="round" strokeLinejoin="round" className={selected ? "stroke-cyan-500" : ""} />;
            if (element.kind === "line") return <line id={`pdf-canvas-element-${element.id}`} key={element.id} x1={element.x1} y1={element.y1} x2={element.x2} y2={element.y2} stroke={element.color} strokeWidth={element.width} className={selected ? "stroke-cyan-500" : ""} />;
            if (element.kind === "arrow") return <g id={`pdf-canvas-element-${element.id}`} key={element.id} className={selected ? "stroke-cyan-500" : ""}><line x1={element.x1} y1={element.y1} x2={element.x2} y2={element.y2} stroke={element.color} strokeWidth={element.width} strokeLinecap="round" /><polygon points={arrowHeadPoints(element.x1, element.y1, element.x2, element.y2, element.width)} fill={element.color} stroke={element.color} /></g>;
            if (element.kind === "rect") return <rect id={`pdf-canvas-element-${element.id}`} key={element.id} x={element.x} y={element.y} width={element.w} height={element.h} fill={element.fill ?? "none"} stroke={selected ? "#06b6d4" : element.color} strokeWidth={selected ? 2 : element.width} />;
            if (element.kind === "ellipse") return <ellipse id={`pdf-canvas-element-${element.id}`} key={element.id} cx={element.x + element.w / 2} cy={element.y + element.h / 2} rx={element.w / 2} ry={element.h / 2} fill={element.fill ?? "none"} stroke={selected ? "#06b6d4" : element.color} strokeWidth={selected ? 2 : element.width} />;
            if (element.kind === "highlight") return <rect id={`pdf-canvas-element-${element.id}`} key={element.id} x={element.x} y={element.y} width={element.w} height={element.h} fill={element.color} fillOpacity=".35" stroke={selected ? "#06b6d4" : "none"} strokeWidth={selected ? 2 : 0} />;
            return null;
          })}
          {drawing.length > 1 && tool === "ink" && <polyline points={drawing.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke={strokeDefaults.color} strokeWidth={strokeDefaults.width} strokeLinecap="round" />}
          {drawing.length > 1 && tool === "highlight" && <rect x={Math.min(drawing[0][0], drawing[1][0])} y={Math.min(drawing[0][1], drawing[1][1])} width={Math.abs(drawing[1][0] - drawing[0][0])} height={Math.abs(drawing[1][1] - drawing[0][1])} fill={highlightColor} fillOpacity=".35" />}
          {drawing.length > 1 && tool === "rect" && <rect x={Math.min(drawing[0][0], drawing[1][0])} y={Math.min(drawing[0][1], drawing[1][1])} width={Math.abs(drawing[1][0] - drawing[0][0])} height={Math.abs(drawing[1][1] - drawing[0][1])} fill={shapeDefaults.fill ?? "none"} stroke={shapeDefaults.color} strokeWidth={shapeDefaults.width} />}
          {drawing.length > 1 && tool === "ellipse" && <ellipse cx={(drawing[0][0] + drawing[1][0]) / 2} cy={(drawing[0][1] + drawing[1][1]) / 2} rx={Math.abs(drawing[1][0] - drawing[0][0]) / 2} ry={Math.abs(drawing[1][1] - drawing[0][1]) / 2} fill={shapeDefaults.fill ?? "none"} stroke={shapeDefaults.color} strokeWidth={shapeDefaults.width} />}
          {drawing.length > 1 && (tool === "line" || tool === "arrow") && <g><line x1={drawing[0][0]} y1={drawing[0][1]} x2={snapLine(drawing[0], drawing[1], false)[0]} y2={snapLine(drawing[0], drawing[1], false)[1]} stroke={shapeDefaults.color} strokeWidth={shapeDefaults.width} />{tool === "arrow" && <polygon points={arrowHeadPoints(drawing[0][0], drawing[0][1], drawing[1][0], drawing[1][1], shapeDefaults.width)} fill={shapeDefaults.color} />}</g>}
        </svg>
        {pageElements.filter((element): element is TextElement => element.kind === "text").map((element) => <div id={`pdf-canvas-element-${element.id}`} key={element.id} className={`pointer-events-auto absolute whitespace-pre rounded-sm leading-[1.2] ${element.id === selectedId ? "outline outline-1 outline-cyan-500" : ""}`} onDoubleClick={(event) => { event.stopPropagation(); if (tool === "pointer") beginText([element.x, element.y], element); }} style={{ left: element.x * scale, top: element.y * scale, width: Math.max(24, element.w) * scale, color: element.color, fontFamily: fontFamily(element.font), fontSize: element.size * scale, fontWeight: element.bold ? 700 : 400, fontStyle: element.italic ? "italic" : "normal" }}>{element.text}</div>)}
        {pageElements.filter((element): element is ImageElement => element.kind === "image").map((element) => <img id={`pdf-canvas-element-${element.id}`} key={element.id} alt="" src={imageSources[element.path]} draggable={false} className={`pointer-events-none absolute object-fill ${element.id === selectedId ? "outline outline-2 outline-cyan-500" : ""}`} style={{ left: element.x * scale, top: element.y * scale, width: element.w * scale, height: element.h * scale }} />)}
        {pageElements.filter((element) => element.id === selectedId).map((element) => handles(element))}
        {textEditor && <textarea ref={textRef} value={textEditor.value} onChange={(event) => { setTextEditor({ ...textEditor, value: event.target.value }); requestAnimationFrame(() => { if (textRef.current) { textRef.current.style.height = "auto"; textRef.current.style.height = `${Math.max(30, textRef.current.scrollHeight)}px`; } }); }} onBlur={commitText} onPointerDown={(event) => event.stopPropagation()} onPointerUp={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); cancelText(); } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); commitText(); } }} className="absolute z-30 resize-none overflow-hidden rounded border border-cyan-400 bg-white/95 px-1 text-black outline-none" style={{ left: textEditor.x * scale, top: textEditor.y * scale, width: textEditor.w * scale, minHeight: 30, fontFamily: fontFamily(textEditor.font), fontSize: textEditor.size * scale, fontWeight: textEditor.bold ? 700 : 400, fontStyle: textEditor.italic ? "italic" : "normal", lineHeight: 1.2 }} />}
      </div>
    </>}
  </div>;
}

function snapLine(start: Point, end: Point, snap: boolean): Point {
  if (!snap) return end;
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const length = Math.hypot(dx, dy);
  if (!length) return end;
  const angle = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
  return [start[0] + Math.cos(angle) * length, start[1] + Math.sin(angle) * length];
}

function arrowHeadPoints(x1: number, y1: number, x2: number, y2: number, width: number): string {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const length = Math.max(8, width * 4);
  const spread = Math.PI / 180 * 28;
  const a = `${x2},${y2}`;
  const b = `${x2 - Math.cos(angle - spread) * length},${y2 - Math.sin(angle - spread) * length}`;
  const c = `${x2 - Math.cos(angle + spread) * length},${y2 - Math.sin(angle + spread) * length}`;
  return `${a} ${b} ${c}`;
}

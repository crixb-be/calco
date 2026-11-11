import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, ChevronDown, Circle, Highlighter, ImagePlus, Minus, MousePointer2, MoveUpRight, Pencil, Redo2, Shapes, Square, Trash2, Type, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import type { EditorTool, PdfElement, PdfFont } from "./types";
import { ColorPicker, FontSelect, FontSizeSelect, StrokePicker, ToggleButton } from "./controls";

interface TextDefaults { font: PdfFont; bold: boolean; italic: boolean; size: number; color: string }
interface StrokeDefaults { color: string; width: number }
interface ShapeDefaults extends StrokeDefaults { fill: string | null }
interface ToolbarProps {
  tool: EditorTool; selected: PdfElement | null; textDefaults: TextDefaults; strokeDefaults: StrokeDefaults; shapeDefaults: ShapeDefaults; highlightColor: string;
  canUndo: boolean; canRedo: boolean; exportDisabled: boolean; onExport: () => void; onTool: (tool: EditorTool) => void; onImage: () => void;
  onUpdateSelected: (patch: Partial<PdfElement>) => void; onUpdateTool: (patch: Partial<PdfElement>) => void; onUndo: () => void; onRedo: () => void; onDelete: () => void;
}

const tools: { id: EditorTool; label: string; icon: typeof MousePointer2 }[] = [
  { id: "pointer", label: "Selección", icon: MousePointer2 }, { id: "text", label: "Texto", icon: Type }, { id: "image", label: "Imagen/Firma", icon: ImagePlus }, { id: "ink", label: "Lápiz", icon: Pencil }, { id: "highlight", label: "Resaltador", icon: Highlighter },
];
const shapeTools: { id: "rect" | "ellipse" | "arrow" | "line"; label: string; icon: typeof Square }[] = [
  { id: "rect", label: "Rectángulo", icon: Square }, { id: "ellipse", label: "Círculo/Elipse", icon: Circle }, { id: "arrow", label: "Flecha", icon: MoveUpRight }, { id: "line", label: "Línea recta", icon: Minus },
];

export default function Toolbar({ tool, selected, textDefaults, strokeDefaults, shapeDefaults, highlightColor, canUndo, canRedo, exportDisabled, onExport, onTool, onImage, onUpdateSelected, onUpdateTool, onUndo, onRedo, onDelete }: ToolbarProps) {
  const [shapeOpen, setShapeOpen] = useState(false);
  const [lastShape, setLastShape] = useState<"rect" | "ellipse" | "arrow" | "line">("rect");
  const shapeRef = useRef<HTMLDivElement>(null);
  const selectedShape = selected && ["rect", "ellipse", "arrow", "line"].includes(selected.kind) ? selected.kind as "rect" | "ellipse" | "arrow" | "line" : null;
  const activeShape = selectedShape ?? (["rect", "ellipse", "arrow", "line"].includes(tool) ? tool as "rect" | "ellipse" | "arrow" | "line" : null);
  const shapeToolActive = ["rect", "ellipse", "arrow", "line"].includes(tool);
  const shape = shapeTools.find((item) => item.id === (activeShape ?? lastShape)) ?? { id: "rect" as const, label: "Formas", icon: Shapes };
  const ShapeIcon = shape.icon;
  useEffect(() => { if (["rect", "ellipse", "arrow", "line"].includes(tool)) setLastShape(tool as "rect" | "ellipse" | "arrow" | "line"); }, [tool]);
  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => { if (shapeRef.current && !shapeRef.current.contains(event.target as Node)) setShapeOpen(false); };
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") setShapeOpen(false); };
    document.addEventListener("pointerdown", onPointerDown); document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("pointerdown", onPointerDown); document.removeEventListener("keydown", onKeyDown); };
  }, []);
  const textContext = selected?.kind === "text" ? selected : textDefaults;
  const strokeContext: StrokeDefaults = selected?.kind === "ink" || selected?.kind === "rect" || selected?.kind === "ellipse" || selected?.kind === "arrow" || selected?.kind === "line" ? selected : strokeDefaults;
  const shapeContext: ShapeDefaults = selected?.kind === "rect" || selected?.kind === "ellipse" ? selected : shapeDefaults;
  const highlightContext = selected?.kind === "highlight" ? selected : { color: highlightColor };
  const isText = selected?.kind === "text" || (!selected && tool === "text");
  const isInk = selected?.kind === "ink" || (!selected && tool === "ink");
  const isHighlight = selected?.kind === "highlight" || (!selected && tool === "highlight");
  const isShape = Boolean(activeShape);
  const change = (patch: Partial<PdfElement>) => selected ? onUpdateSelected(patch) : onUpdateTool(patch);
  const shapeChange = (patch: Partial<PdfElement>) => selected && ["rect", "ellipse"].includes(selected.kind) ? onUpdateSelected(patch) : onUpdateTool(patch);
  return <div className="sticky top-0 z-30 border-b bg-card/95 backdrop-blur">
    <div className="flex min-h-[4.25rem] flex-wrap items-center gap-1.5 px-3 py-2">
      <div className="flex items-center gap-1 rounded-lg border bg-muted/30 p-1">
        {tools.map(({ id, label, icon: Icon }) => <Button key={id} type="button" size="sm" variant="ghost" className={tool === id ? "bg-primary/15 text-primary ring-1 ring-primary/30" : "text-muted-foreground hover:text-foreground"} onClick={() => id === "image" ? onImage() : onTool(id)} title={label}><Icon size={18} /><span className="text-[11px]">{label}</span></Button>)}
        <div ref={shapeRef} className="relative">
          <Button type="button" size="sm" variant="ghost" className={shapeToolActive ? "bg-primary/15 text-primary ring-1 ring-primary/30" : "text-muted-foreground hover:text-foreground"} onClick={() => setShapeOpen((current) => !current)} title="Formas"><ShapeIcon size={18} /><span className="text-[11px]">{activeShape ? shape.label : "Formas"}</span><ChevronDown size={16} /></Button>
          {shapeOpen && <div className="absolute left-0 top-10 z-50 min-w-48 rounded-lg border bg-card p-1.5 shadow-xl">{shapeTools.map(({ id, label, icon: Icon }) => <button type="button" key={id} onClick={() => { onTool(id); setShapeOpen(false); }} className={`flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs hover:bg-accent ${tool === id ? "bg-primary/15 text-primary" : ""}`}><Icon size={16} />{label}</button>)}</div>}
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2"><Button type="button" onClick={onExport} disabled={exportDisabled}><ArrowUpRight size={18} /> Guardar cambios / Exportar PDF</Button></div>
    </div>
    <div className="flex min-h-11 flex-wrap items-center gap-3 border-t bg-muted/30 px-3 py-1.5">
      {isInk && <><ColorPicker label="Color" value={strokeContext.color} onChange={(value) => value && change({ color: value })} /><StrokePicker value={strokeContext.width} onChange={(value) => change({ width: value })} /></>}
      {isHighlight && <ColorPicker label="Color" value={highlightContext.color} onChange={(value) => value && change({ color: value })} />}
      {isShape && <><ColorPicker label="Borde" value={strokeContext.color} onChange={(value) => value && shapeChange({ color: value })} />{(selected?.kind === "rect" || selected?.kind === "ellipse" || activeShape === "rect" || activeShape === "ellipse") && <ColorPicker label="Relleno" value={shapeContext.fill ?? null} allowTransparent onChange={(value) => shapeChange({ fill: value })} />}<StrokePicker value={strokeContext.width} onChange={(value) => shapeChange({ width: value })} /></>}
      {isText && <><FontSelect value={textContext.font} onChange={(value) => change({ font: value })} /><FontSizeSelect value={textContext.size} onChange={(value) => change({ size: value })} /><ColorPicker label="Color" value={textContext.color} onChange={(value) => value && change({ color: value })} /><div className="flex items-center gap-1"><ToggleButton pressed={textContext.bold} label="Negrita" onClick={() => change({ bold: !textContext.bold })}>B</ToggleButton><ToggleButton pressed={textContext.italic} label="Cursiva" onClick={() => change({ italic: !textContext.italic })}><span className="italic">I</span></ToggleButton></div></>}
      {!selected && !isInk && !isHighlight && !isShape && !isText && <span className="text-xs text-muted-foreground">Selecciona un elemento para editar sus propiedades</span>}
      <div className="ml-auto flex items-center gap-1"><Button type="button" size="icon-sm" variant="ghost" disabled={!canUndo} onClick={onUndo} title="Deshacer (Ctrl+Z)" aria-label="Deshacer"><Undo2 size={16} /></Button><Button type="button" size="icon-sm" variant="ghost" disabled={!canRedo} onClick={onRedo} title="Rehacer (Ctrl+Y)" aria-label="Rehacer"><Redo2 size={16} /></Button><span className="mx-1 h-5 w-px bg-border" /><Button type="button" size="icon-sm" variant="ghost" className="text-red-500 hover:bg-red-500/10" disabled={!selected} onClick={onDelete} title="Eliminar seleccionado" aria-label="Eliminar seleccionado"><Trash2 size={16} /></Button></div>
    </div>
  </div>;
}

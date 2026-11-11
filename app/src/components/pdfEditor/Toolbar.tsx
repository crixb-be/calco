import {
  ImagePlus,
  Highlighter,
  Minus,
  MousePointer2,
  Pencil,
  Plus,
  Redo2,
  Square,
  Trash2,
  Type,
  Undo2,
} from "lucide-react";
import { Button, Input } from "@/components/ui/primitives";
import type { EditorTool, PdfElement, PdfFont } from "./types";

interface TextDefaults { font: PdfFont; bold: boolean; size: number; color: string }
interface StrokeDefaults { color: string; width: number }

interface ToolbarProps {
  tool: EditorTool;
  selected: PdfElement | null;
  textDefaults: TextDefaults;
  strokeDefaults: StrokeDefaults;
  highlightColor: string;
  canUndo: boolean;
  canRedo: boolean;
  zoom: number;
  onTool: (tool: EditorTool) => void;
  onImage: () => void;
  onUpdateSelected: (patch: Partial<PdfElement>) => void;
  onUpdateTool: (patch: Partial<PdfElement>) => void;
  onUndo: () => void;
  onRedo: () => void;
  onDelete: () => void;
  onZoom: (delta: number) => void;
}

const tools: { id: EditorTool; label: string; icon: typeof MousePointer2 }[] = [
  { id: "pointer", label: "Selección", icon: MousePointer2 },
  { id: "text", label: "Texto", icon: Type },
  { id: "image", label: "Imagen/Firma", icon: ImagePlus },
  { id: "ink", label: "Lápiz", icon: Pencil },
  { id: "highlight", label: "Resaltador", icon: Highlighter },
  { id: "rect", label: "Rectángulo", icon: Square },
  { id: "line", label: "Línea", icon: Minus },
];

export default function Toolbar({ tool, selected, textDefaults, strokeDefaults, highlightColor, canUndo, canRedo, zoom, onTool, onImage, onUpdateSelected, onUpdateTool, onUndo, onRedo, onDelete, onZoom }: ToolbarProps) {
  const textContext = selected?.kind === "text" ? selected : textDefaults;
  const strokeContext: StrokeDefaults = selected && (selected.kind === "ink" || selected.kind === "rect" || selected.kind === "line") ? selected : strokeDefaults;
  const highlightContext = selected?.kind === "highlight" ? selected : { color: highlightColor };
  const isText = selected?.kind === "text" || (!selected && tool === "text");
  const isStroke = Boolean(selected && ["ink", "rect", "line"].includes(selected.kind)) || (!selected && ["ink", "rect", "line"].includes(tool));
  const isHighlight = selected?.kind === "highlight" || (!selected && tool === "highlight");
  const change = (patch: Partial<PdfElement>) => selected ? onUpdateSelected(patch) : onUpdateTool(patch);
  return <div className="sticky top-0 z-30 flex flex-wrap items-center gap-1.5 border-b bg-card/95 px-3 py-3 backdrop-blur">
    {tools.map(({ id, label, icon: Icon }) => <Button key={id} type="button" variant={tool === id ? "default" : "outline"} className="h-9 px-2.5" onClick={() => id === "image" ? onImage() : onTool(id)}><Icon size={15} /> <span className="hidden xl:inline">{label}</span></Button>)}
    {isText && <>
      <select aria-label="Fuente" value={textContext.font} onChange={(event) => change({ font: event.target.value as PdfFont })} className="h-9 rounded-md border bg-background px-2 text-xs">
        <option value="helv">Helvetica</option><option value="tiro">Times</option><option value="cour">Courier</option>
      </select>
      <Button type="button" variant={textContext.bold ? "default" : "outline"} className="h-9 px-2 font-bold" onClick={() => change({ bold: !textContext.bold })}>B</Button>
      <Input aria-label="Tamaño de texto" type="number" min={8} max={96} value={textContext.size} onChange={(event) => change({ size: Math.max(8, Math.min(96, Number(event.target.value) || 16)) })} className="h-9 w-16" />
      <Input aria-label="Color de texto" type="color" value={textContext.color} onChange={(event) => change({ color: event.target.value })} className="h-9 w-11 p-1" />
    </>}
    {isStroke && <>
      <Input aria-label="Color del trazo" type="color" value={strokeContext.color} onChange={(event) => change({ color: event.target.value })} className="h-9 w-11 p-1" />
      <Input aria-label="Ancho del trazo" type="number" min={1} max={24} value={strokeContext.width} onChange={(event) => change({ width: Math.max(1, Math.min(24, Number(event.target.value) || 1)) })} className="h-9 w-16" />
    </>}
    {isHighlight && <Input aria-label="Color del resaltador" type="color" value={highlightContext.color} onChange={(event) => change({ color: event.target.value })} className="h-9 w-11 p-1" />}
    <span className="ml-auto flex items-center gap-1">
      <Button type="button" variant="ghost" className="h-9 w-9 p-0" disabled={!canUndo} onClick={onUndo} title="Deshacer (Ctrl+Z)"><Undo2 size={15} /></Button>
      <Button type="button" variant="ghost" className="h-9 w-9 p-0" disabled={!canRedo} onClick={onRedo} title="Rehacer (Ctrl+Y)"><Redo2 size={15} /></Button>
      <Button type="button" variant="danger" className="h-9 w-9 p-0" disabled={!selected} onClick={onDelete} title="Eliminar"><Trash2 size={15} /></Button>
      <Button type="button" variant="ghost" className="h-9 w-9 p-0" onClick={() => onZoom(-0.1)} title="Alejar"><Minus size={15} /></Button>
      <span className="w-12 text-center text-xs">{Math.round(zoom * 100)}%</span>
      <Button type="button" variant="ghost" className="h-9 w-9 p-0" onClick={() => onZoom(0.1)} title="Acercar"><Plus size={15} /></Button>
    </span>
  </div>;
}

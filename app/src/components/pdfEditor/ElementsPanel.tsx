import { ArrowDown, ArrowUp, FileImage, Highlighter, Minus, Pencil, Square, Trash2, Type } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import type { PdfElement } from "./types";
import { elementLabel } from "./types";

interface ElementsPanelProps {
  elements: PdfElement[];
  page: number;
  pageCount: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onUp: (id: string) => void;
  onDown: (id: string) => void;
  onRemove: (id: string) => void;
}

function Icon({ kind }: { kind: PdfElement["kind"] }) {
  const props = { size: 15, className: "shrink-0 text-muted-foreground" };
  if (kind === "text") return <Type {...props} />;
  if (kind === "image") return <FileImage {...props} />;
  if (kind === "ink") return <Pencil {...props} />;
  if (kind === "highlight") return <Highlighter {...props} />;
  if (kind === "rect") return <Square {...props} />;
  return <Minus {...props} />;
}

export default function ElementsPanel({ elements, page, pageCount, selectedId, onSelect, onUp, onDown, onRemove }: ElementsPanelProps) {
  const pageElements = elements.filter((element) => element.page === page);
  return <aside className="w-full shrink-0 border-t bg-card p-3 lg:w-64 lg:border-l lg:border-t-0">
    <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold">Elementos</h2><span className="text-xs text-muted-foreground">Página {page + 1} de {pageCount}</span></div>
    <div className="max-h-[38rem] space-y-1 overflow-y-auto pr-1">
      {!pageElements.length && <p className="rounded-md border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">No hay elementos en esta página.</p>}
      {pageElements.map((element) => <div key={element.id} id={`pdf-element-${element.id}`} className={`group flex items-center gap-2 rounded-md border px-2 py-1.5 ${selectedId === element.id ? "border-primary bg-primary/10" : "border-transparent hover:bg-accent"}`}>
        <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs" onClick={() => onSelect(element.id)}><Icon kind={element.kind} /><span className="truncate">{elementLabel(element)}</span></button>
        <div className="flex shrink-0 items-center gap-0.5 opacity-70 group-hover:opacity-100">
          <Button type="button" variant="ghost" className="h-6 w-6 p-0" onClick={() => onUp(element.id)} title="Subir"><ArrowUp size={12} /></Button>
          <Button type="button" variant="ghost" className="h-6 w-6 p-0" onClick={() => onDown(element.id)} title="Bajar"><ArrowDown size={12} /></Button>
          <Button type="button" variant="ghost" className="h-6 w-6 p-0 text-red-300" onClick={() => onRemove(element.id)} title="Eliminar"><Trash2 size={12} /></Button>
        </div>
      </div>)}
    </div>
  </aside>;
}

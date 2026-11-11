import { useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { ArrowDown, ArrowUp, FilePlus2, FolderOpen, X } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import type { ToolDefinition } from "@/catalog/tools";
interface Props { tool: ToolDefinition; files: string[]; onChange: (files: string[]) => void; outputDir: string; onOutputDirChange: (path: string) => void; }
export default function FileDrop({ tool, files, onChange, outputDir, onOutputDirChange }: Props) {
  const [dragging, setDragging] = useState(false);
  const addFiles = (paths: string[]) => onChange(tool.multiFile ? [...files, ...paths.filter((path) => !files.includes(path))] : paths.slice(0, 1));
  const addFilesRef = useRef(addFiles);
  addFilesRef.current = addFiles;
  useEffect(() => {
    let disposed = false;
    let off: (() => void) | undefined;
    void listen<{ paths: string[] }>("tauri://drag-drop", (event) => addFilesRef.current(event.payload.paths)).then((unlisten) => {
      if (disposed) unlisten();
      else off = unlisten;
    });
    return () => { disposed = true; off?.(); };
  }, []);
  async function pickFiles() { const picked = await open({ multiple: tool.multiFile, directory: false, filters: [{ name: "Archivos compatibles", extensions: tool.extensions }] }); if (picked) addFiles(Array.isArray(picked) ? picked : [picked]); }
  async function pickDir() { const picked = await open({ directory: true, multiple: false }); if (picked && typeof picked === "string") onOutputDirChange(picked); }
  return <div className="space-y-3">
    <div onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(Array.from(e.dataTransfer.files).map((file) => file.name)); }} className={`flex h-[110px] flex-wrap items-center justify-center gap-x-5 gap-y-2 overflow-hidden rounded-xl border-2 border-dashed px-4 py-2 text-center transition ${dragging ? "border-primary bg-primary/10" : "border-border bg-background/30"}`}>
      <FilePlus2 className="shrink-0 text-primary" size={24} /><div className="min-w-0 text-left"><p className="text-sm font-semibold">Arrastra archivos aquí</p><p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{tool.extensions.map((ext) => `.${ext}`).join(", ")} · {tool.multiFile ? "varios archivos" : "un archivo"}</p></div><Button type="button" variant="outline" className="h-9" onClick={pickFiles}><FolderOpen size={16} /> Elegir archivos</Button>
    </div>
    {files.length > 0 && <div className="rounded-lg border"><div className="flex items-center justify-between border-b px-3 py-1"><span className="text-xs font-semibold text-muted-foreground">ENTRADAS · {files.length}</span><Button type="button" variant="ghost" className="h-7 px-2 text-xs" onClick={() => onChange([])}><X size={14} /> Limpiar</Button></div><div className="max-h-44 divide-y overflow-y-auto">{files.map((file, index) => <div key={`${file}-${index}`} className="flex items-center gap-2 px-3 py-1.5 text-xs"><span className="min-w-5 text-muted-foreground">{index + 1}</span><span className="min-w-0 flex-1 truncate" title={file}>{file.split(/[\\/]/).pop()}</span>{tool.multiFile && <><button type="button" disabled={index === 0} onClick={() => { const next = [...files]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; onChange(next); }} className="text-muted-foreground disabled:opacity-30"><ArrowUp size={14} /></button><button type="button" disabled={index === files.length - 1} onClick={() => { const next = [...files]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; onChange(next); }} className="text-muted-foreground disabled:opacity-30"><ArrowDown size={14} /></button></>}</div>)}</div></div>}
    <div><label className="mb-1.5 block text-xs font-semibold text-muted-foreground">CARPETA DE SALIDA</label><div className="flex gap-2"><input value={outputDir} onChange={(e) => onOutputDirChange(e.target.value)} placeholder="Selecciona una carpeta…" className="h-9 min-w-0 flex-1 rounded-md border bg-background/50 px-3 text-sm outline-none focus:ring-2 focus:ring-ring" /><Button type="button" variant="outline" className="px-3" onClick={pickDir}><FolderOpen size={16} /></Button></div></div>
  </div>;
}

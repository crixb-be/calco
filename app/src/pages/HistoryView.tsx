import { useEffect, useState } from "react";
import { ArrowLeft, Clock3, FolderOpen, History, Trash2 } from "lucide-react";
import type { HistoryRecord } from "@/contracts/rpc";
import { Button, Card } from "@/components/ui/primitives";
import { engineRpc, revealInFolder } from "@/lib/engine";

interface Props { onBack: () => void; }

export default function HistoryView({ onBack }: Props) {
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const result = await engineRpc<{ records: HistoryRecord[] }>("get_history", {});
      setRecords(result.records);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function clear() {
    const result = await engineRpc<{ records: HistoryRecord[] }>("clear_history", {});
    setRecords(result.records);
  }

  return (
    <div className="w-full space-y-4 p-6 lg:p-8">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft size={16} /> Volver</button>
      <div className="flex items-start justify-between gap-4"><div className="flex items-start gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sky-500/15 text-sky-300"><History size={18} /></div><div><p className="eyebrow">Actividad local</p><h1 className="text-xl font-bold">Historial</h1><p className="mt-0.5 text-sm text-muted-foreground">Últimas 100 tareas ejecutadas en este equipo.</p></div></div><Button type="button" variant="outline" disabled={!records.length} onClick={() => void clear()}><Trash2 size={15} /> Limpiar</Button></div>
      <Card className="divide-y overflow-hidden">
        {loading ? <p className="p-5 text-sm text-muted-foreground">Cargando historial…</p> : records.length === 0 ? <p className="p-5 text-sm text-muted-foreground">Todavía no hay tareas registradas.</p> : records.map((record) => <div key={`${record.id}-${record.timestamp}`} className="flex items-center gap-3 p-4"><div className={`h-2.5 w-2.5 shrink-0 rounded-full ${record.status === "success" ? "bg-emerald-400" : "bg-red-400"}`} /><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{record.type}</p><p className="truncate text-xs text-muted-foreground" title={record.target_path}>{record.source_name || "Sin archivo de entrada"} → {record.target_path || "sin salida"}</p><p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground"><Clock3 size={12} /> {new Date(record.timestamp).toLocaleString()} · {record.duration_ms} ms</p></div>{record.target_path && <Button type="button" variant="ghost" className="h-8 px-2 text-xs" title="Abrir en Explorador" onClick={() => void revealInFolder(record.target_path)}><FolderOpen size={14} /> Abrir</Button>}</div>)}
      </Card>
    </div>
  );
}

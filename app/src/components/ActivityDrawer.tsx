import { useEffect } from "react";
import { History as HistoryIcon, X } from "lucide-react";
import { Badge } from "@/components/ui/primitives";
import { JobList, useActiveJobCount } from "@/components/JobQueue";
import type { DoclingViewerRequest } from "@/components/docling/DoclingDualViewer";
import { useJobs } from "@/store/jobs";

interface Props {
  open: boolean;
  onClose: () => void;
  onViewDocling: (request: DoclingViewerRequest) => void;
  onOpenHistory: () => void;
}

/** Job queue as an overlay sliding out of the left nav: it never narrows the workspace. */
export default function ActivityDrawer({ open, onClose, onViewDocling, onOpenHistory }: Props) {
  const total = useJobs((state) => state.jobs.length);
  const active = useActiveJobCount();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, open]);

  return (
    <div className={`fixed inset-y-0 left-[250px] right-0 z-40 ${open ? "" : "pointer-events-none"}`} aria-hidden={!open}>
      <div
        className={`absolute inset-0 bg-black/40 transition-opacity duration-200 ${open ? "opacity-100" : "opacity-0"}`}
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Cola de trabajos"
        className={`relative flex h-full w-[400px] max-w-full flex-col border-r bg-card shadow-2xl transition-transform duration-200 ease-out ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <p className="eyebrow">Actividad</p>
            <h2 className="mt-1 font-semibold">Cola de trabajos</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {active ? `${active} en curso` : "Sin tareas en curso"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge>{total}</Badge>
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar cola de trabajos"
              title="Cerrar (Esc)"
              className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X size={17} />
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <JobList
            onViewDocling={(request) => {
              onViewDocling(request);
              onClose();
            }}
          />
        </div>
        <div className="border-t p-3"><button type="button" onClick={() => { onOpenHistory(); onClose(); }} className="w-full rounded-md border px-3 py-2 text-xs font-semibold text-muted-foreground hover:bg-accent hover:text-foreground"><HistoryIcon size={14} className="mr-2 inline" /> Ver historial local</button></div>
      </aside>
    </div>
  );
}

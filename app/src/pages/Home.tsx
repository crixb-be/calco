import { ArrowRightLeft, ChevronDown, ChevronUp, Combine, FileDown, PenTool, Search, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Input } from "@/components/ui/primitives";
import { domains, tools, type Domain, type ToolDefinition } from "@/catalog/tools";

/** Soft thematic icon colours by kind of action. */
const TONES = {
  organize: "bg-violet-500/15 text-violet-600 dark:text-violet-300",
  security: "bg-rose-500/15 text-rose-600 dark:text-rose-300",
  edit: "bg-amber-500/15 text-amber-600 dark:text-amber-300",
  convert: "bg-sky-500/15 text-sky-600 dark:text-sky-300",
  ai: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
  media: "bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-300",
} as const;

const SECURITY = new Set(["redact", "sanitize", "protect", "unprotect"]);
const EDIT = new Set(["page_numbers", "watermark", "flatten"]);
const ORGANIZE = new Set(["merge", "split", "rotate", "crop", "delete_pages", "nup", "page_organizer"]);

function toneOf(tool: ToolDefinition): string {
  if (tool.domain === "docling") return TONES.ai;
  if (tool.domain === "multimedia") return TONES.media;
  if (SECURITY.has(tool.id)) return TONES.security;
  if (EDIT.has(tool.id)) return TONES.edit;
  if (ORGANIZE.has(tool.id)) return TONES.organize;
  return TONES.convert;
}

/** Cards shown per domain before "Ver todas". */
const COLLAPSED_COUNT = 6;

interface HomeProps {
  onSelect: (id: string) => void;
  onOpenConverter: () => void;
  onOpenEditor: () => void;
  activeDomain?: Domain;
}

function ToolCard({ tool, onSelect }: { tool: ToolDefinition; onSelect: (id: string) => void }) {
  const Icon = tool.icon;
  return (
    <button
      type="button"
      onClick={() => onSelect(tool.id)}
      className="group flex max-h-[170px] min-h-[150px] flex-col rounded-xl border bg-card p-3.5 text-left transition-all hover:-translate-y-0.5 hover:border-sky-500/40 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${toneOf(tool)}`}>
        <Icon size={18} />
      </div>
      <h3 className="mb-1 mt-2 text-sm font-semibold text-slate-900 dark:text-slate-100">{tool.label}</h3>
      <p className="line-clamp-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">{tool.description}</p>
      <div className="mt-auto flex flex-wrap gap-1 pt-2 opacity-70 transition-opacity group-hover:opacity-100">
        {tool.extensions.slice(0, 3).map((extension) => (
          <span key={extension} className="rounded border px-1.5 py-px text-[10px] text-muted-foreground">.{extension}</span>
        ))}
        {tool.extensions.length > 3 && <span className="text-[10px] text-muted-foreground">+{tool.extensions.length - 3}</span>}
      </div>
    </button>
  );
}

export default function Home({ onSelect, onOpenConverter, onOpenEditor, activeDomain }: HomeProps) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Partial<Record<Domain, boolean>>>({});
  const searching = query.trim().length > 0;
  const visible = useMemo(
    () => tools.filter((tool) => (!activeDomain || tool.domain === activeDomain) && `${tool.label} ${tool.description} ${tool.action}`.toLowerCase().includes(query.toLowerCase())),
    [query, activeDomain],
  );

  const quickAccess: { id: string; label: string; hint: string; icon: LucideIcon; tone: string; open: () => void }[] = [
    { id: "converter", label: "Conversor Universal", hint: "Office, PDF, imágenes y Markdown", icon: ArrowRightLeft, tone: TONES.convert, open: onOpenConverter },
    { id: "editor", label: "Editar PDF", hint: "Texto, firmas, dibujos y formas", icon: PenTool, tone: TONES.edit, open: onOpenEditor },
    { id: "merge", label: "Unir PDF", hint: "Combina varios PDF en uno", icon: Combine, tone: TONES.organize, open: () => onSelect("merge") },
    { id: "compress_pdf", label: "Comprimir PDF", hint: "Reduce el tamaño del archivo", icon: FileDown, tone: TONES.convert, open: () => onSelect("compress_pdf") },
  ];

  return (
    <div className="w-full space-y-6 p-6 lg:p-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Espacio de trabajo local</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight">¿Qué quieres hacer hoy?</h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">Procesa documentos, exporta datos y transforma multimedia sin salir de tu equipo.</p>
        </div>
        <div className="relative w-72">
          <Search size={17} className="absolute left-3 top-3 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar herramientas…" className="pl-9" />
        </div>
      </div>

      {!activeDomain && !searching && (
        <section>
          <h2 className="mb-2.5 text-base font-semibold">Acceso rápido</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {quickAccess.map(({ id, label, hint, icon: Icon, tone, open }) => (
              <button
                key={id}
                type="button"
                onClick={open}
                className="flex items-center gap-3 rounded-xl border bg-gradient-to-br from-primary/10 to-transparent p-4 text-left transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${tone}`}><Icon size={20} /></div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{label}</p>
                  <p className="truncate text-xs text-muted-foreground">{hint}</p>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {domains.map((domain) => {
        const items = visible.filter((tool) => tool.domain === domain.id);
        if (!items.length) return null;
        // Searching or browsing a single domain shows everything; otherwise one row until expanded.
        const collapsible = !searching && !activeDomain && items.length > COLLAPSED_COUNT;
        const open = !collapsible || Boolean(expanded[domain.id]);
        const shown = open ? items : items.slice(0, COLLAPSED_COUNT);
        return (
          <section key={domain.id}>
            <div className="mb-2.5 flex items-end justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">{domain.label}</h2>
                <p className="text-xs text-muted-foreground">{domain.description}</p>
              </div>
              {collapsible ? (
                <button
                  type="button"
                  onClick={() => setExpanded((current) => ({ ...current, [domain.id]: !open }))}
                  aria-expanded={open}
                  className="inline-flex shrink-0 items-center gap-1 rounded-md border bg-muted/40 px-2.5 py-1 text-xs font-semibold text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  {open ? <>Contraer <ChevronUp size={14} /></> : <>Ver todas ({items.length}) <ChevronDown size={14} /></>}
                </button>
              ) : (
                <Badge>{items.length} herramientas</Badge>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
              {shown.map((tool) => <ToolCard key={tool.id} tool={tool} onSelect={onSelect} />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}

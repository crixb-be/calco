import { Search } from "lucide-react";
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

export default function Home({ onSelect, activeDomain }: { onSelect: (id: string) => void; activeDomain?: Domain }) {
  const [query, setQuery] = useState("");
  const visible = useMemo(
    () => tools.filter((tool) => (!activeDomain || tool.domain === activeDomain) && `${tool.label} ${tool.description} ${tool.action}`.toLowerCase().includes(query.toLowerCase())),
    [query, activeDomain],
  );

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

      {domains.map((domain) => {
        const items = visible.filter((tool) => tool.domain === domain.id);
        if (!items.length) return null;
        return (
          <section key={domain.id}>
            <div className="mb-2.5 flex items-end justify-between">
              <div>
                <h2 className="text-base font-semibold">{domain.label}</h2>
                <p className="text-xs text-muted-foreground">{domain.description}</p>
              </div>
              <Badge>{items.length} herramientas</Badge>
            </div>
            <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
              {items.map((tool) => {
                const Icon = tool.icon;
                return (
                  <button
                    key={tool.id}
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
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

import { useEffect, useState } from "react";
import {
  ChevronRight,
  FileStack,
  Home as HomeIcon,
  ListChecks,
  Moon,
  Settings as SettingsIcon,
  Sun,
} from "lucide-react";
import { domains, type Domain } from "@/catalog/tools";
import Home from "@/pages/Home";
import ToolPage from "@/pages/ToolPage";
import SettingsView from "@/pages/SettingsView";
import UniversalConverter from "@/pages/UniversalConverter";
import DoclingView from "@/pages/DoclingView";
import SecurityView from "@/pages/SecurityView";
import PageOrganizerView from "@/pages/PageOrganizerView";
import HistoryView from "@/pages/HistoryView";
import ActivityDrawer from "@/components/ActivityDrawer";
import { useActiveJobCount } from "@/components/JobQueue";
import { Toaster } from "@/components/ui/toast";
import type { DoclingViewerRequest } from "@/components/docling/DoclingDualViewer";
import { listenToTaskEvents } from "@/lib/engine";
import { useJobs } from "@/store/jobs";
import { useOutputDirs } from "@/store/outputDirs";

type Page = "home" | "tool" | "settings" | "converter" | "history";

/** Domains that open a dedicated full-width workspace instead of the filtered catalog. */
const DOMAIN_PAGES: Partial<Record<Domain, Page>> = { conversor: "converter" };

export default function App() {
  const [page, setPage] = useState<Page>("home");
  const [toolId, setToolId] = useState("");
  const [domain, setDomain] = useState<Domain | undefined>();
  const [theme, setTheme] = useState<"dark" | "light">(
    (localStorage.getItem("docforge.theme") as "dark" | "light") ?? "dark",
  );
  const [viewerRequest, setViewerRequest] = useState<DoclingViewerRequest | null>(null);
  const [activityOpen, setActivityOpen] = useState(false);
  const activeJobs = useActiveJobCount();
  const apply = useJobs((state) => state.apply);
  const loadOutputDirs = useOutputDirs((state) => state.load);

  useEffect(() => {
    document.documentElement.classList.toggle("light", theme === "light");
    localStorage.setItem("docforge.theme", theme);
  }, [theme]);

  useEffect(() => {
    void loadOutputDirs();
  }, [loadOutputDirs]);

  useEffect(() => {
    let off: (() => void) | undefined;
    listenToTaskEvents(apply).then((unlisten) => {
      off = unlisten;
    });
    return () => off?.();
  }, [apply]);

  const goHome = (nextDomain?: Domain) => {
    setActivityOpen(false);
    setViewerRequest(null);
    const dedicated = nextDomain ? DOMAIN_PAGES[nextDomain] : undefined;
    setDomain(nextDomain);
    setPage(dedicated ?? "home");
  };

  const openDoclingResult = (request: DoclingViewerRequest) => {
    setViewerRequest(request);
    setToolId("docling_parse");
    setPage("tool");
    setDomain(undefined);
  };

  const openHistory = () => {
    setActivityOpen(false);
    setViewerRequest(null);
    setDomain(undefined);
    setPage("history");
  };

  const navClass = (active: boolean) =>
    `flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium ${
      active ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent"
    }`;

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="relative z-50 flex w-[250px] shrink-0 flex-col border-r bg-card">
        <div className="flex items-center gap-3 border-b px-5 py-5">
          <div className="rounded-lg bg-primary p-2 text-primary-foreground">
            <FileStack size={20} />
          </div>
          <div>
            <p className="font-bold tracking-tight">DocForge</p>
            <p className="text-[10px] uppercase tracking-[.18em] text-muted-foreground">Desktop</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          <button type="button" onClick={() => goHome()} className={navClass(page === "home" && !domain && !activityOpen)}>
            <HomeIcon size={17} /> Inicio
          </button>
          <button
            type="button"
            onClick={() => setActivityOpen((value) => !value)}
            aria-expanded={activityOpen}
            className={navClass(activityOpen)}
            title={activeJobs ? `${activeJobs} tarea(s) en curso` : "Cola de trabajos"}
          >
            <ListChecks size={17} />
            <span className="flex-1 text-left">Actividad</span>
            {activeJobs > 0 && (
              <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[11px] font-bold leading-5 text-primary-foreground">
                {activeJobs}
              </span>
            )}
          </button>
          <p className="px-3 pb-1 pt-6 text-[10px] font-bold uppercase tracking-[.16em] text-muted-foreground">
            Dominios
          </p>
          {domains.map((item) => {
            const active = !activityOpen && domain === item.id && (page === "home" || page === DOMAIN_PAGES[item.id]);
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => goHome(item.id)}
                className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-sm ${
                  active ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent"
                }`}
              >
                <span>{item.label}</span>
                <ChevronRight size={14} />
              </button>
            );
          })}
        </nav>
        <div className="border-t p-3">
          <button
            type="button"
            onClick={() => {
              setActivityOpen(false);
              setPage("settings");
              setDomain(undefined);
            }}
            className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm ${
              page === "settings" ? "bg-accent" : "text-muted-foreground hover:bg-accent"
            }`}
          >
            <SettingsIcon size={17} /> Ajustes
          </button>
        </div>
        <button
          type="button"
          title="Cambiar tema"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="absolute bottom-5 right-0 rounded-full border bg-card p-2.5 text-muted-foreground shadow-lg hover:text-foreground"
        >
          {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        {page === "home" && (
          <Home
            activeDomain={domain}
            onSelect={(id) => {
              setToolId(id);
              setViewerRequest(null);
              setPage("tool");
            }}
          />
        )}
        {page === "tool" && toolId === "page_organizer" && <PageOrganizerView onBack={() => goHome()} />}
        {page === "tool" && toolId === "docling_parse" && <DoclingView onBack={() => goHome()} initialPreview={viewerRequest} />}
        {page === "tool" && (toolId === "protect" || toolId === "unprotect") && <SecurityView toolId={toolId} onBack={() => goHome()} />}
        {page === "tool" && toolId !== "page_organizer" && toolId !== "docling_parse" && toolId !== "protect" && toolId !== "unprotect" && (
          <ToolPage key={toolId} toolId={toolId} onBack={() => goHome()} viewerRequest={viewerRequest} onViewerRequestHandled={() => setViewerRequest(null)} />
        )}
        {page === "converter" && <UniversalConverter onOpenActivity={() => setActivityOpen(true)} />}
        {page === "settings" && (
          <SettingsView
            theme={theme}
            onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
          />
        )}
        {page === "history" && <HistoryView onBack={() => goHome()} />}
      </main>

      <ActivityDrawer open={activityOpen} onClose={() => setActivityOpen(false)} onViewDocling={openDoclingResult} onOpenHistory={openHistory} />
      <Toaster />
    </div>
  );
}

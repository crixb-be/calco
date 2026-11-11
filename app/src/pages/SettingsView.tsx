import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, FolderOpen, HardDrive, Moon, RefreshCw, Sun, Trash2, XCircle, Zap } from "lucide-react";
import { open } from "@tauri-apps/plugin-dialog";
import { Badge, Button, Card, Input, Label } from "@/components/ui/primitives";
import {
  engineRpc, checkSystemHealth, detectOfficeSuites, getDefaultOutputDir, setDefaultOutputDir,
  type OfficeSuiteId, type OfficeSuites, type SystemHealth,
} from "@/lib/engine";
import type { ProcessorTask } from "@/contracts/task";
import { useJobs } from "@/store/jobs";

type Props = { theme: "dark" | "light"; onToggleTheme: () => void };

const formatBytes = (bytes: number | null) => {
  if (bytes === null) return "No disponible";
  if (bytes < 1024 ** 3) return `${Math.round(bytes / 1024 ** 2)} MB libres`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB libres`;
};

const SUITES: { id: OfficeSuiteId; label: string; formats: string }[] = [
  { id: "msword", label: "Microsoft Word", formats: "DOCX, DOC, ODT, RTF, TXT" },
  { id: "msexcel", label: "Microsoft Excel", formats: "XLSX, XLS, ODS, CSV" },
  { id: "mspowerpoint", label: "Microsoft PowerPoint", formats: "PPTX, PPT, ODP" },
  { id: "libreoffice", label: "LibreOffice", formats: "Respaldo para todos los formatos" },
];

function suiteDetail(id: OfficeSuiteId, suites: OfficeSuites | null, loading: boolean) {
  if (loading) return "Detectando…";
  const status = suites?.[id];
  if (!status) return "Sin datos del motor";
  if (id !== "libreoffice") return status.available ? "Instalado · se usa primero" : "No instalado";
  if (status.configuredInvalid) {
    return status.available ? `La ruta guardada no es válida · usando ${status.path}` : "La ruta guardada no es válida";
  }
  if (!status.available) return "No instalado";
  return `${status.source === "configured" ? "Ruta de Ajustes" : "Detectado"}: ${status.path}`;
}

export default function SettingsView({ theme, onToggleTheme }: Props) {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [soffice, setSoffice] = useState(() => localStorage.getItem("docforge.soffice") ?? "");
  const [ffmpeg, setFfmpeg] = useState(() => localStorage.getItem("docforge.ffmpeg") ?? "");
  const [models, setModels] = useState(() => localStorage.getItem("docforge.models") ?? "");
  const [message, setMessage] = useState("");
  const [suites, setSuites] = useState<OfficeSuites | null>(null);
  const [suitesLoading, setSuitesLoading] = useState(true);
  const add = useJobs((state) => state.add);

  const refreshSuites = async (sofficePath: string) => {
    setSuitesLoading(true);
    try {
      setSuites(await detectOfficeSuites(sofficePath.trim()));
    } catch {
      setSuites(null);
    } finally {
      setSuitesLoading(false);
    }
  };

  const refresh = async () => {
    void refreshSuites(soffice);
    try {
      setHealth(await checkSystemHealth());
      setOutputDir((await getDefaultOutputDir()) ?? "");
    } catch (error) {
      setHealth({ sidecar_online: false, libreoffice_path: null, disk_free_bytes: null });
      setMessage(error instanceof Error ? error.message : String(error));
    }
  };

  const anySuite = suites ? SUITES.some(({ id }) => suites[id]?.available) : false;

  useEffect(() => { void refresh(); }, []);

  const chooseOutputDir = async () => {
    const selected = await open({ directory: true, multiple: false, title: "Carpeta de salida predeterminada" });
    if (typeof selected !== "string") return;
    try {
      setOutputDir(await setDefaultOutputDir(selected));
      setMessage("Carpeta de salida guardada.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  };

  const clearLocalData = async () => {
    try {
      await Promise.all([engineRpc("clear_history", {}), engineRpc("clear_temp_cache", {})]);
      setMessage("Historial y caché temporal limpiados.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  };

  const saveLocalPaths = () => {
    localStorage.setItem("docforge.soffice", soffice.trim());
    localStorage.setItem("docforge.ffmpeg", ffmpeg.trim());
    localStorage.setItem("docforge.models", models.trim());
    setMessage("Rutas locales guardadas.");
    void refreshSuites(soffice);
  };

  const chooseModelsDir = async () => {
    const selected = await open({ directory: true, multiple: false, title: "Carpeta de modelos Docling" });
    if (typeof selected === "string") {
      setModels(selected);
      localStorage.setItem("docforge.models", selected);
    }
  };

  const prefetchModels = async () => {
    const folder = models.trim();
    if (!folder) return;
    localStorage.setItem("docforge.models", folder);
    const task: ProcessorTask = {
      id: crypto.randomUUID(),
      engine: "docling_core",
      action: "prefetch_models",
      inputFiles: [],
      outputDir: folder,
      options: { artifactsPath: folder },
    };
    await add(task);
    setMessage("Prefetch de modelos enviado a la cola.");
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6 lg:p-8">
      <div className="flex items-center justify-between gap-3">
        <div><p className="eyebrow">Preferencias locales</p><h1 className="mt-1 text-2xl font-bold">Ajustes</h1></div>
        <Button variant="outline" onClick={onToggleTheme}>{theme === "dark" ? <Sun size={15} /> : <Moon size={15} />} {theme === "dark" ? "Tema claro" : "Tema oscuro"}</Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_.8fr]">
        <Card className="p-4">
          <div className="flex items-center justify-between"><div><h2 className="font-semibold">Diagnóstico del sistema</h2><p className="mt-1 text-xs text-muted-foreground">Estado del motor incluido y dependencias locales.</p></div><Button variant="ghost" className="h-8 px-2" onClick={() => void refresh()}><RefreshCw size={15} /></Button></div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <div className="rounded-lg border bg-background/30 p-3"><p className="text-xs text-muted-foreground">Sidecar Python</p><div className="mt-1 flex items-center gap-2 text-sm font-semibold">{health?.sidecar_online ? <CheckCircle2 className="text-emerald-400" size={16} /> : <XCircle className="text-rose-400" size={16} />} {health?.sidecar_online ? "Online" : "Offline"}</div></div>
            <div className="flex items-center gap-2 rounded-lg border bg-background/30 p-3 text-sm"><HardDrive size={16} className="text-muted-foreground" /> {formatBytes(health?.disk_free_bytes ?? null)}</div>
          </div>

          <h3 className="mt-5 text-sm font-semibold">Office a PDF</h3>
          <p className="mt-1 text-xs text-muted-foreground">Se usa Microsoft Office si está instalado; si no, LibreOffice.</p>
          <ul className="mt-3 space-y-2">
            {SUITES.map(({ id, label, formats }) => {
              const status = suites?.[id];
              const ok = Boolean(status?.available);
              const warn = Boolean(status?.configuredInvalid);
              const detail = suiteDetail(id, suites, suitesLoading);
              return (
                <li key={id} className="flex items-start gap-3 rounded-lg border bg-background/30 p-3">
                  {suitesLoading ? <RefreshCw size={16} className="mt-0.5 shrink-0 animate-spin text-muted-foreground" />
                    : warn ? <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-400" />
                    : ok ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-400" />
                    : <XCircle size={16} className="mt-0.5 shrink-0 text-muted-foreground" />}
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-baseline justify-between gap-x-2 text-sm font-semibold">{label}<span className="text-[11px] font-normal text-muted-foreground">{formats}</span></p>
                    <p className={`mt-0.5 truncate text-xs ${warn ? "text-amber-300" : "text-muted-foreground"}`} title={detail}>{detail}</p>
                  </div>
                </li>
              );
            })}
          </ul>
          {!suitesLoading && suites && !anySuite && (
            <p className="mt-3 whitespace-pre-wrap rounded-md border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs text-amber-200">
              {"No hay ninguna suite ofimática disponible. Opciones:\n• Instalar Microsoft Office (se usa automáticamente).\n• Instalar LibreOffice gratis desde libreoffice.org.\n• Indicar la ruta de soffice.exe (o LibreOffice Portable) abajo."}
            </p>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="font-semibold">Guardado predeterminado</h2><p className="mt-1 text-xs text-muted-foreground">Los resultados nuevos usarán esta carpeta.</p>
          <div className="mt-4 flex gap-2"><div className="min-w-0 flex-1 truncate rounded-md border bg-background/50 px-3 py-2 text-sm" title={outputDir}>{outputDir || "No configurada"}</div><Button variant="outline" className="h-10 w-10 shrink-0 px-0" onClick={() => void chooseOutputDir()}><FolderOpen size={16} /></Button></div>
        </Card>
      </div>

      <Card className="flex items-center justify-between gap-4 p-4"><div><h2 className="font-semibold">Datos locales</h2><p className="mt-1 text-xs text-muted-foreground">Elimina historial y residuos temporales del motor.</p></div><Button variant="danger" onClick={() => void clearLocalData()}><Trash2 size={15} /> Limpiar historial y caché</Button></Card>
      <Card className="space-y-4 p-4">
        <div>
          <h2 className="font-semibold">Dependencias y modelos</h2>
          <p className="mt-1 text-xs text-muted-foreground">Estas rutas se guardan en este equipo y se envian al motor cuando corresponde.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div><Label htmlFor="settings-soffice">Ruta de LibreOffice (opcional)</Label><Input id="settings-soffice" value={soffice} onChange={(event) => setSoffice(event.target.value)} placeholder="Detectar automaticamente" /></div>
          <div><Label htmlFor="settings-ffmpeg">Ruta de FFmpeg</Label><Input id="settings-ffmpeg" value={ffmpeg} onChange={(event) => setFfmpeg(event.target.value)} placeholder="Detectar automaticamente" /></div>
          <div className="md:col-span-2"><Label htmlFor="settings-models">Carpeta de modelos Docling</Label><div className="mt-1 flex gap-2"><Input id="settings-models" value={models} onChange={(event) => setModels(event.target.value)} placeholder="Selecciona una carpeta para los modelos" /><Button variant="outline" className="h-10 w-10 shrink-0 px-0" onClick={() => void chooseModelsDir()}><FolderOpen size={16} /></Button></div></div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={saveLocalPaths}><Zap size={15} /> Guardar rutas</Button>
          <Button variant="outline" disabled={!models.trim()} onClick={() => void prefetchModels()}><Zap size={15} /> Prefetch models</Button>
          <Badge>Accion: docling_core / prefetch_models</Badge>
        </div>
      </Card>

      {message && <Badge className="max-w-full truncate">{message}</Badge>}
    </div>
  );
}

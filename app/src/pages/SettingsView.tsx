import { useEffect, useState } from "react";
import { CheckCircle2, FolderOpen, HardDrive, Moon, RefreshCw, Sun, Trash2, XCircle } from "lucide-react";
import { open } from "@tauri-apps/plugin-dialog";
import { Badge, Button, Card } from "@/components/ui/primitives";
import { engineRpc, checkSystemHealth, getDefaultOutputDir, setDefaultOutputDir, type SystemHealth } from "@/lib/engine";

type Props = { theme: "dark" | "light"; onToggleTheme: () => void };

const formatBytes = (bytes: number | null) => {
  if (bytes === null) return "No disponible";
  if (bytes < 1024 ** 3) return `${Math.round(bytes / 1024 ** 2)} MB libres`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB libres`;
};

export default function SettingsView({ theme, onToggleTheme }: Props) {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [message, setMessage] = useState("");

  const refresh = async () => {
    try {
      setHealth(await checkSystemHealth());
      setOutputDir((await getDefaultOutputDir()) ?? "");
    } catch (error) {
      setHealth({ sidecar_online: false, libreoffice_path: null, disk_free_bytes: null });
      setMessage(error instanceof Error ? error.message : String(error));
    }
  };

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
            <div className="rounded-lg border bg-background/30 p-3"><p className="text-xs text-muted-foreground">LibreOffice</p><p className="mt-1 truncate text-sm font-semibold">{health?.libreoffice_path ?? "No instalado"}</p></div>
            <div className="col-span-2 flex items-center gap-2 rounded-lg border bg-background/30 p-3 text-sm"><HardDrive size={16} className="text-muted-foreground" /> {formatBytes(health?.disk_free_bytes ?? null)}</div>
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="font-semibold">Guardado predeterminado</h2><p className="mt-1 text-xs text-muted-foreground">Los resultados nuevos usarán esta carpeta.</p>
          <div className="mt-4 flex gap-2"><div className="min-w-0 flex-1 truncate rounded-md border bg-background/50 px-3 py-2 text-sm" title={outputDir}>{outputDir || "No configurada"}</div><Button variant="outline" className="h-10 w-10 shrink-0 px-0" onClick={() => void chooseOutputDir()}><FolderOpen size={16} /></Button></div>
        </Card>
      </div>

      <Card className="flex items-center justify-between gap-4 p-4"><div><h2 className="font-semibold">Datos locales</h2><p className="mt-1 text-xs text-muted-foreground">Elimina historial y residuos temporales del motor.</p></div><Button variant="danger" onClick={() => void clearLocalData()}><Trash2 size={15} /> Limpiar historial y caché</Button></Card>
      {message && <Badge className="max-w-full truncate">{message}</Badge>}
    </div>
  );
}

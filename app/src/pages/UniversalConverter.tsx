import { useEffect, useMemo, useState } from "react";
import { ArrowRightLeft, Info, ListChecks, Play } from "lucide-react";
import type { ToolDefinition } from "@/catalog/tools";
import {
  CONVERTER_EXTENSIONS,
  IMAGE_TARGETS,
  QUALITY_PRESETS,
  TARGETS,
  availableTargets,
  familyOf,
  planConversion,
  type QualityPreset,
  type TargetFormat,
} from "@/catalog/conversions";
import FileDrop from "@/components/FileDrop";
import { Button, Card, Input, Label } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { useJobs } from "@/store/jobs";

/** FileDrop expects a tool definition: describe the converter's accepted inputs. */
const converterTool: ToolDefinition = {
  id: "universal_convert",
  domain: "conversor",
  engine: "office_bridge",
  action: "universal_convert",
  label: "Conversor Universal",
  description: "",
  icon: ArrowRightLeft,
  extensions: CONVERTER_EXTENSIONS,
  multiFile: true,
  fields: [],
};

interface Props {
  onOpenActivity?: () => void;
}

export default function UniversalConverter({ onOpenActivity }: Props) {
  const add = useJobs((state) => state.add);
  const showToast = useToast((state) => state.show);
  const [files, setFiles] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useState("");
  const [target, setTarget] = useState<TargetFormat>("pdf");
  const [dpi, setDpi] = useState(150);
  const [mergeImages, setMergeImages] = useState(true);
  const [quality, setQuality] = useState<QualityPreset>("balanced");
  const [submitted, setSubmitted] = useState(0);

  const availability = useMemo(() => availableTargets(files), [files]);
  const isImageInput = files.length > 0 && files.every((file) => familyOf(file) === "image");
  const isPdfInput = files.length > 0 && files.every((file) => familyOf(file) === "pdf");
  const imageTarget = IMAGE_TARGETS.has(target);
  const showDpi = isPdfInput && imageTarget; // PDF pages rendered to images
  const showQuality = () => (isImageInput || isPdfInput) && (target === "jpg" || target === "webp");
  const showMerge = isImageInput && target === "pdf";

  // Keep the target valid for the current selection.
  useEffect(() => {
    const current = availability.find((item) => item.target === target);
    if (current?.enabled) return;
    const first = availability.find((item) => item.enabled);
    if (first) setTarget(first.target);
  }, [availability, target]);

  const plan = useMemo(
    () => planConversion(files, target, { dpi, mergeImages, quality, sofficePath: localStorage.getItem("docforge.soffice") }),
    [dpi, files, mergeImages, quality, target],
  );
  const planError = "error" in plan ? plan.error : null;
  const canRun = files.length > 0 && Boolean(outputDir) && !planError;

  async function run() {
    if ("error" in plan || !outputDir) return;
    const pending = plan.tasks.map((task) => add({ ...task, id: crypto.randomUUID(), outputDir }));
    setSubmitted(plan.tasks.length);
    showToast("success", `${plan.tasks.length} ${plan.tasks.length === 1 ? "tarea enviada" : "tareas enviadas"}. Sigue el progreso en Actividad.`);
    await Promise.all(pending);
  }

  return (
    <div className="w-full space-y-4 p-6 lg:p-8">
      <div className="flex items-start gap-4">
        <div className="rounded-lg bg-primary/10 p-2 text-primary">
          <ArrowRightLeft size={22} />
        </div>
        <div>
          <p className="eyebrow">Conversor Universal</p>
          <h1 className="text-xl font-bold">Convertir archivos</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Arrastra documentos de oficina, imágenes o PDF y elige el formato de destino. DocForge elige el motor adecuado.
          </p>
        </div>
      </div>

      <Card className="space-y-4 p-5">
        <div className="flex items-center gap-2 rounded-md border border-blue-800/40 bg-blue-950/40 px-3 py-2 text-xs text-blue-200">
          <Info className="h-4 w-4 shrink-0" />
          <span>Office y texto → PDF usan Microsoft Office si está instalado y, si no, LibreOffice (revisa el estado en Ajustes). Cada conversión corre en segundo plano.</span>
        </div>

        <FileDrop tool={converterTool} files={files} onChange={setFiles} outputDir={outputDir} onOutputDirChange={setOutputDir} />

        <div className="border-t pt-4">
          <h2 className="mb-3 font-semibold">Formato de destino</h2>
          <div role="radiogroup" aria-label="Formato de destino" className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-7">
            {TARGETS.map(({ id, label }) => {
              const state = availability.find((item) => item.target === id);
              const enabled = Boolean(state?.enabled);
              const selected = enabled && target === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  disabled={!enabled}
                  title={state?.reason ?? `Convertir a ${label}`}
                  onClick={() => setTarget(id)}
                  className={`rounded-lg border px-3 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ${
                    selected ? "border-primary bg-primary/15 text-foreground" : "bg-background/30 text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          {(showDpi || showQuality() || showMerge) && !planError && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {showDpi && (
                <div>
                  <Label htmlFor="converter-dpi">DPI</Label>
                  <Input id="converter-dpi" type="number" min={36} max={600} value={dpi} onChange={(event) => setDpi(Number(event.target.value))} />
                  <p className="mt-1 text-[11px] text-muted-foreground">Una imagen por página del PDF.</p>
                </div>
              )}
              {showQuality() && (
                <div className="sm:col-span-2">
                  <Label>Calidad</Label>
                  <div role="radiogroup" aria-label="Calidad" className="grid gap-2 sm:grid-cols-3">
                    {QUALITY_PRESETS.map((preset) => (
                      <button
                        key={preset.id}
                        type="button"
                        role="radio"
                        aria-checked={quality === preset.id}
                        onClick={() => setQuality(preset.id)}
                        className={`rounded-lg border p-3 text-left text-xs transition ${quality === preset.id ? "border-primary bg-primary/10" : "hover:bg-accent"}`}
                      >
                        <span className="block font-semibold">{preset.label}</span>
                        <span className="mt-0.5 block text-muted-foreground">{preset.hint}</span>
                      </button>
                    ))}
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {target === "png" ? "PNG no pierde calidad: el ajuste solo cambia la compresión." : "Se conservan los DPI originales; la transparencia pasa a fondo blanco en JPG."}
                  </p>
                </div>
              )}
              {showMerge && (
                <label className="flex items-center gap-3 self-end rounded-md border bg-background/30 px-3 py-2.5 text-sm">
                  <input type="checkbox" checked={mergeImages} onChange={(event) => setMergeImages(event.target.checked)} className="h-4 w-4 accent-cyan-400" />
                  Combinar imágenes en un solo PDF
                </label>
              )}
            </div>
          )}

          <p className={`mt-4 text-xs ${planError && files.length ? "text-red-300" : "text-muted-foreground"}`} aria-live="polite">
            {files.length === 0 ? "Añade archivos para ver el plan de conversión." : planError ?? ("summary" in plan ? `Se usará: ${plan.summary}` : "")}
          </p>
        </div>

        <Button type="button" className="w-full" disabled={!canRun} onClick={() => void run()}>
          <Play size={16} /> Convertir a {TARGETS.find((item) => item.id === target)?.label}
        </Button>

        {submitted > 0 && onOpenActivity && (
          <button type="button" onClick={onOpenActivity} className="inline-flex items-center gap-2 text-xs text-primary hover:underline">
            <ListChecks size={14} /> Ver {submitted === 1 ? "la tarea" : `las ${submitted} tareas`} en Actividad
          </button>
        )}
      </Card>
    </div>
  );
}

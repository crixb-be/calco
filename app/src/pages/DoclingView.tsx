import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Clipboard, ChevronDown, ChevronUp, Play, ScanText } from "lucide-react";
import { toolById } from "@/catalog/tools";
import FileDrop from "@/components/FileDrop";
import { Button, Card, Label } from "@/components/ui/primitives";
import { engineRpc } from "@/lib/engine";
import { useToast } from "@/components/ui/toast";
import { useJobs } from "@/store/jobs";
import { useOutputDir } from "@/store/outputDirs";

type ExportFormat = "md" | "json" | "html";
interface PreviewSeed { markdownPath: string; }
interface Props { onBack: () => void; initialPreview?: PreviewSeed | null; }

const parserTool = toolById("docling_parse")!;
const outputLabel: Record<ExportFormat, string> = { md: "Markdown", json: "JSON", html: "HTML" };

export default function DoclingView({ onBack, initialPreview }: Props) {
  const add = useJobs((state) => state.add);
  const jobs = useJobs((state) => state.jobs);
  const showToast = useToast((state) => state.show);
  const [files, setFiles] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useOutputDir(null);
  const [format, setFormat] = useState<ExportFormat>("md");
  const [preview, setPreview] = useState(initialPreview?.markdownPath ?? "");
  const [previewText, setPreviewText] = useState("");
  const [previewOpen, setPreviewOpen] = useState(Boolean(initialPreview));
  const [runningId, setRunningId] = useState<string | null>(null);
  const canRun = files.length === 1 && Boolean(outputDir);

  useEffect(() => {
    if (!initialPreview?.markdownPath) return;
    setPreview(initialPreview.markdownPath);
    setPreviewOpen(true);
  }, [initialPreview]);

  useEffect(() => {
    const job = runningId ? jobs.find((entry) => entry.task.id === runningId) : null;
    if (!job || job.status !== "success") return;
    const textPath = job.outputFiles.find((path) => /\.(md|json|html)$/i.test(path));
    if (textPath) {
      setPreview(textPath);
      setPreviewOpen(true);
      void engineRpc<{ content: string }>("read_text_file", { path: textPath })
        .then((result) => setPreviewText(result.content))
        .catch((error) => showToast("error", error instanceof Error ? error.message : "No se pudo leer la vista previa."));
    }
    setRunningId(null);
  }, [jobs, runningId, showToast]);

  useEffect(() => {
    if (!preview) return;
    void engineRpc<{ content: string }>("read_text_file", { path: preview })
      .then((result) => setPreviewText(result.content))
      .catch(() => undefined);
  }, [preview]);

  const previewName = useMemo(() => preview.split(/[\\/]/).pop() ?? "resultado", [preview]);

  async function run() {
    if (!canRun) return;
    const id = crypto.randomUUID();
    const artifactsPath = localStorage.getItem("docforge.models");
    await add({
      id,
      engine: "docling_core",
      action: "docling_parse",
      inputFiles: files,
      outputDir,
      options: {
        exportFormats: [format],
        ocr: true,
        tableMode: "fast",
        formulas: true,
        ...(artifactsPath ? { artifactsPath } : {}),
      },
    });
    setRunningId(id);
    showToast("success", `Parser Docling enviado: ${outputLabel[format]}.`);
  }

  return (
    <div className="w-full space-y-4 p-6 lg:p-8">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft size={16} /> Volver al catálogo
      </button>
      <div className="flex items-start gap-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300"><ScanText size={18} /></div>
        <div><p className="eyebrow">Extracción IA · Parser inteligente</p><h1 className="text-xl font-bold">Parser Inteligente</h1><p className="mt-0.5 text-sm text-muted-foreground">Extrae estructura, tablas y texto de PDFs o imágenes.</p></div>
      </div>
      <Card className="space-y-4 p-5">
        <FileDrop tool={parserTool} files={files} onChange={setFiles} outputDir={outputDir} onOutputDirChange={setOutputDir} />
        <div className="border-t pt-4">
          <Label htmlFor="docling-format">Exportar como</Label>
          <select id="docling-format" value={format} onChange={(event) => setFormat(event.target.value as ExportFormat)} className="h-9 w-full rounded-md border bg-background/50 px-3 text-sm outline-none focus:ring-2 focus:ring-ring">
            {(Object.entries(outputLabel) as [ExportFormat, string][]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <p className="mt-1 text-[11px] text-muted-foreground">El motor también soporta DocTags para tareas avanzadas.</p>
        </div>
        <Button type="button" className="w-full" disabled={!canRun} onClick={() => void run()}><Play size={16} /> Extraer estructura</Button>
      </Card>
      {preview && (
        <Card className="overflow-hidden">
          <button type="button" onClick={() => setPreviewOpen((value) => !value)} className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold">
            <span>Vista previa · {previewName}</span>{previewOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {previewOpen && <div className="border-t p-3"><div className="mb-2 flex justify-end"><Button type="button" variant="outline" className="h-8 px-3 text-xs" onClick={() => { void navigator.clipboard.writeText(previewText); showToast("success", "Texto copiado."); }}><Clipboard size={14} /> Copiar texto</Button></div><pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-background/50 p-3 text-xs leading-relaxed">{previewText || "Cargando vista previa…"}</pre></div>}
        </Card>
      )}
    </div>
  );
}

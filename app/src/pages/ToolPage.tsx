import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Info, LoaderCircle, Play } from "lucide-react";
import { INTERNAL_ACTIONS, toolById, tools } from "@/catalog/tools";
import FileDrop from "@/components/FileDrop";
import ToolForm, { initialOptions } from "@/components/ToolForm";
import PageGridManager, { pageSequence } from "@/components/pages/PageGridManager";
import DoclingDualViewer, { doclingViewerRequest, type DoclingViewerRequest } from "@/components/docling/DoclingDualViewer";
import { Button, Card } from "@/components/ui/primitives";
import type { PdfPagesMetadataResult } from "@/contracts/rpc";
import { engineRpc } from "@/lib/engine";
import { useJobs } from "@/store/jobs";
import { categoryForTool, useOutputDir } from "@/store/outputDirs";
import { usePageGrid } from "@/store/pageGrid";

interface Props {
  toolId: string;
  onBack: () => void;
  viewerRequest?: DoclingViewerRequest | null;
  onViewerRequestHandled?: () => void;
}

const PAGE_GRID_TOOLS = new Set(["merge", "split", "rotate", "delete_pages"]);

export default function ToolPage({
  toolId,
  onBack,
  viewerRequest,
  onViewerRequestHandled,
}: Props) {
  const tool = toolById(toolId);
  const selectedTool = tool ?? tools[0];
  const add = useJobs((state) => state.add);
  const jobs = useJobs((state) => state.jobs);
  const gridItems = usePageGrid((state) => state.items);
  const clearGrid = usePageGrid((state) => state.clear);
  const [files, setFiles] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useOutputDir(categoryForTool(selectedTool));
  const [options, setOptions] = useState<Record<string, unknown>>({});
  const [metadata, setMetadata] = useState<PdfPagesMetadataResult[]>([]);
  const [metadataError, setMetadataError] = useState("");
  const [metadataLoading, setMetadataLoading] = useState(false);
  const [splitMode, setSplitMode] = useState<"extract" | "per_page" | "ranges">("ranges");
  const [viewer, setViewer] = useState<DoclingViewerRequest | null>(null);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);

  useEffect(() => {
    if (!viewerRequest) return;
    setViewer(viewerRequest);
    onViewerRequestHandled?.();
  }, [onViewerRequestHandled, viewerRequest]);

  useEffect(() => {
    if (toolId !== "docling_parse" || !currentJobId) return;
    const job = jobs.find((entry) => entry.task.id === currentJobId);
    if (job?.status !== "success") return;
    const request = doclingViewerRequest(job.task.inputFiles, job.outputFiles);
    if (request) setViewer(request);
    // Open once: otherwise closing the viewer would reopen it on the next job update.
    setCurrentJobId(null);
  }, [currentJobId, jobs, toolId]);

  useEffect(() => {
    if (!tool || !PAGE_GRID_TOOLS.has(tool.id) || files.length === 0) {
      setMetadata([]);
      setMetadataError("");
      clearGrid();
      return;
    }

    let cancelled = false;
    setMetadataLoading(true);
    setMetadataError("");
    void Promise.all(
      files.map((pdfPath) => engineRpc<PdfPagesMetadataResult>("get_pdf_pages_metadata", { pdfPath })),
    )
      .then((result) => {
        if (!cancelled) setMetadata(result);
      })
      .catch((error) => {
        if (!cancelled) {
          setMetadataError(error instanceof Error ? error.message : "No se pudo leer el PDF.");
        }
      })
      .finally(() => {
        if (!cancelled) setMetadataLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [clearGrid, files, tool]);

  const opts = useMemo(
    () => ({ ...initialOptions(selectedTool), ...options }),
    [options, selectedTool],
  );
  const Icon = selectedTool.icon;
  const isPageGridTool = PAGE_GRID_TOOLS.has(selectedTool.id);
  const isSplitRanges = selectedTool.id === "split" && splitMode === "ranges";
  const gridFormTool = useMemo(
    () => ({
      ...selectedTool,
      fields: selectedTool.fields.filter((field) => field.key === "outputName"),
    }),
    [selectedTool],
  );
  const selectedForSplit = gridItems.filter((item) => item.selected && !item.deleted);
  const sequence = pageSequence(gridItems);
  const binaryPath = selectedTool.engine === "office_bridge"
    ? localStorage.getItem("docforge.soffice")
    : selectedTool.engine === "ffmpeg_bridge"
      ? localStorage.getItem("docforge.ffmpeg")
      : null;
  const canSubmitGrid = metadata.length > 0 && !metadataLoading && !metadataError && sequence.length > 0;
  const canSubmitSplitSelection = selectedForSplit.length > 0 && !metadataLoading && !metadataError;

  async function submit() {
    if (!files.length || !outputDir) return;

    const id = crypto.randomUUID();
    const baseOptions = {
      ...opts,
      ...(binaryPath ? { binaryPath } : {}),
      ...(selectedTool.engine === "docling_core" && selectedTool.action === "docling_parse"
        ? (() => {
            const artifactsPath = localStorage.getItem("docforge.models");
            return artifactsPath ? { artifactsPath } : {};
          })()
        : {}),
    };
    const isSelectionSplit = selectedTool.id === "split" && splitMode !== "ranges";
    const task = isPageGridTool && !isSplitRanges
      ? {
          id,
          engine: "stirling_core" as const,
          action: INTERNAL_ACTIONS[0],
          inputFiles: files,
          outputDir,
          options: {
            ...(typeof opts.outputName === "string" && opts.outputName.trim()
              ? { outputName: opts.outputName.trim() }
              : {}),
            sequence: isSelectionSplit
              ? pageSequence(gridItems.filter((item) => item.selected))
              : sequence,
            outputMode: isSelectionSplit && splitMode === "per_page" ? "per_page" : "single",
          },
        }
      : {
          id,
          engine: selectedTool.engine,
          action: selectedTool.action,
          inputFiles: files,
          outputDir,
          options: baseOptions,
        };

    await add(task);
    setCurrentJobId(id);
  }

  const submitDisabled =
    !files.length ||
    !outputDir ||
    metadataLoading ||
    Boolean(metadataError) ||
    (isPageGridTool && !isSplitRanges && !canSubmitGrid);

  if (!tool) return <div className="p-8">Herramienta no encontrada.</div>;
  if (viewer) return <DoclingDualViewer {...viewer} onClose={() => setViewer(null)} />;

  return (
    <div className="w-full space-y-4 p-6 lg:p-8">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={16} /> Volver al catálogo
      </button>

      <div className="flex items-start gap-4">
        <div className="rounded-lg bg-primary/10 p-2 text-primary">
          <Icon size={22} />
        </div>
        <div>
          <p className="eyebrow">{selectedTool.engine.replace("_", " ")}</p>
          <h1 className="text-xl font-bold">{selectedTool.label}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">{selectedTool.description}</p>
        </div>
      </div>

      <Card className="space-y-4 p-5">
        <div className="flex items-center gap-2 rounded-md border border-blue-800/40 bg-blue-950/40 px-3 py-2 text-xs text-blue-200">
          <Info className="h-4 w-4 shrink-0" />
          <span>{selectedTool.tip ?? "Puedes seguir usando DocForge mientras el trabajo corre en segundo plano."}</span>
        </div>

        <FileDrop
          tool={selectedTool}
          files={files}
          onChange={setFiles}
          outputDir={outputDir}
          onOutputDirChange={setOutputDir}
        />

        {isPageGridTool && files.length > 0 && (
          <div className="space-y-3">
            <div className="border-t pt-4">
              <h2 className="font-semibold">Organizar páginas</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Selecciona, arrastra, gira o marca las páginas que no quieras conservar.
              </p>
            </div>
            {metadataLoading ? (
              <div className="flex items-center gap-2 rounded-lg border p-5 text-sm text-muted-foreground">
                <LoaderCircle className="animate-spin" size={17} /> Leyendo páginas del PDF…
              </div>
            ) : metadataError ? (
              <p className="rounded-lg border border-red-400/40 bg-red-500/10 p-4 text-sm text-red-300">
                {metadataError}
              </p>
            ) : metadata.length > 0 ? (
              <PageGridManager files={files} metadata={metadata} />
            ) : null}
          </div>
        )}

        <div className="border-t pt-4">
          <h2 className="mb-3 font-semibold">Opciones</h2>
          {selectedTool.id === "split" && (
            <div className="mb-5">
              <label className="mb-2 block text-xs font-semibold text-muted-foreground">
                MODO DE DIVISIÓN
              </label>
              <div className="grid gap-2 sm:grid-cols-3">
                {([
                  ["extract", "Extraer seleccionadas a un PDF"],
                  ["per_page", "Un PDF por página seleccionada"],
                  ["ranges", "Dividir por rangos"],
                ] as const).map(([value, label]) => (
                  <button
                    type="button"
                    key={value}
                    onClick={() => setSplitMode(value)}
                    className={`rounded-lg border p-3 text-left text-xs transition ${splitMode === value ? "border-primary bg-primary/10" : "hover:bg-accent"}`}
                  >
                    <span className="font-semibold">{label}</span>
                    {value !== "ranges" && (
                      <span className="mt-1 block text-muted-foreground">
                        Usa las páginas seleccionadas en la cuadrícula.
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {selectedTool.id === "split" ? (
            isSplitRanges ? (
              <ToolForm tool={selectedTool} value={opts} onChange={setOptions} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Selecciona páginas en la cuadrícula para crear el resultado.
              </p>
            )
          ) : isPageGridTool && files.length > 0 ? (
            gridFormTool.fields.length ? (
              <ToolForm tool={gridFormTool} value={opts} onChange={setOptions} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Los cambios se aplican desde la cuadrícula de páginas.
              </p>
            )
          ) : selectedTool.fields.length ? (
            <ToolForm tool={selectedTool} value={opts} onChange={setOptions} />
          ) : (
            <p className="text-sm text-muted-foreground">
              Esta acción no requiere opciones adicionales.
            </p>
          )}
        </div>

        <Button
          type="button"
          className="w-full"
          disabled={submitDisabled || (selectedTool.id === "split" && !isSplitRanges && !canSubmitSplitSelection)}
          onClick={submit}
        >
          <Play size={16} /> Ejecutar {selectedTool.label}
        </Button>
      </Card>
    </div>
  );
}

import { useState } from "react";
import { ArrowLeft, Eye, EyeOff, KeyRound, Play, UnlockKeyhole } from "lucide-react";
import { toolById } from "@/catalog/tools";
import FileDrop from "@/components/FileDrop";
import { Button, Card, Input, Label } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { useJobs } from "@/store/jobs";

type SecurityTool = "protect" | "unprotect";
interface Props { toolId: SecurityTool; onBack: () => void; }

export default function SecurityView({ toolId, onBack }: Props) {
  const tool = toolById(toolId)!;
  const add = useJobs((state) => state.add);
  const showToast = useToast((state) => state.show);
  const [files, setFiles] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useState("");
  const [password, setPassword] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showOwner, setShowOwner] = useState(false);
  const protect = toolId === "protect";
  const canRun = files.length === 1 && Boolean(outputDir) && Boolean(password) && (!protect || Boolean(ownerPassword || password));

  async function run() {
    if (!canRun) return;
    await add({
      id: crypto.randomUUID(),
      engine: "stirling_core",
      action: protect ? "protect_pdf" : "unlock_pdf",
      inputFiles: files,
      outputDir,
      options: protect ? { userPassword: password, ownerPassword: ownerPassword || password } : { password },
    });
    showToast("success", protect ? "Protección enviada a la cola." : "Desbloqueo enviado a la cola.");
  }

  return (
    <div className="w-full space-y-4 p-6 lg:p-8">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft size={16} /> Volver al catálogo</button>
      <div className="flex items-start gap-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-rose-500/15 text-rose-300">{protect ? <KeyRound size={18} /> : <UnlockKeyhole size={18} />}</div>
        <div><p className="eyebrow">Seguridad PDF</p><h1 className="text-xl font-bold">{protect ? "Proteger PDF" : "Desbloquear PDF"}</h1><p className="mt-0.5 text-sm text-muted-foreground">{protect ? "Cifra el documento con AES-256 y una contraseña local." : "Valida la contraseña y genera una copia sin restricciones."}</p></div>
      </div>
      <Card className="space-y-4 p-5">
        <FileDrop tool={tool} files={files} onChange={setFiles} outputDir={outputDir} onOutputDirChange={setOutputDir} />
        <div className="grid gap-3 border-t pt-4 sm:grid-cols-2">
          <div><Label htmlFor="security-password">{protect ? "Contraseña de usuario" : "Contraseña del PDF"}</Label><div className="relative"><Input id="security-password" type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Introduce la contraseña" className="pr-10" /><button type="button" aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"} onClick={() => setShowPassword((value) => !value)} className="absolute right-2 top-2.5 text-muted-foreground hover:text-foreground">{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></div>
          {protect && <div><Label htmlFor="owner-password">Contraseña de propietario</Label><div className="relative"><Input id="owner-password" type={showOwner ? "text" : "password"} value={ownerPassword} onChange={(event) => setOwnerPassword(event.target.value)} placeholder="Opcional: usa la de usuario" className="pr-10" /><button type="button" aria-label={showOwner ? "Ocultar contraseña de propietario" : "Mostrar contraseña de propietario"} onClick={() => setShowOwner((value) => !value)} className="absolute right-2 top-2.5 text-muted-foreground hover:text-foreground">{showOwner ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></div>}
        </div>
        <Button type="button" className="w-full" disabled={!canRun} onClick={() => void run()}><Play size={16} /> {protect ? "Proteger PDF" : "Desbloquear PDF"}</Button>
      </Card>
    </div>
  );
}

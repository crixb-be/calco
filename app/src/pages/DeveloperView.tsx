import { useState } from "react";
import { BookOpen, Code2, ExternalLink, Facebook, Github, Instagram, Mail, Scale, type LucideIcon } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { Badge, Card } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { useAppVersion } from "@/lib/appVersion";

/** Datos públicos del autor. Rellena los enlaces vacíos para activar su botón. */
const DEVELOPER = {
  name: "Cristian Billy Bustamante Espinoza",
  handle: "crixb-be",
  role: "Arquitecto & Desarrollador Full-Stack",
  initials: "CB",
  avatar: "https://github.com/crixb-be.png",
  github: "https://github.com/crixb-be",
  repository: "https://github.com/crixb-be/docforge-desktop",
  license: "MIT",
  instagram: "https://www.instagram.com/cristhian.billy/",
  facebook: "https://www.facebook.com/cristhian.bustamanteespinoza/",
  email: "cristhianbbe7@gmail.com",
};

/** Degradado exacto del banner del perfil. */
const BANNER_GRADIENT = "linear-gradient(90deg, rgba(2, 0, 36, 1) 0%, rgba(9, 9, 121, 1) 35%, rgba(0, 212, 255, 1) 100%)";

const STACK = ["Tauri", "Rust", "React", "Python", "PyMuPDF"];

const SOCIALS: { key: "instagram" | "facebook"; label: string; icon: LucideIcon }[] = [
  { key: "instagram", label: "Instagram", icon: Instagram },
  { key: "facebook", label: "Facebook", icon: Facebook },
];

export default function DeveloperView() {
  const version = useAppVersion();
  const showToast = useToast((state) => state.show);
  const [avatarFailed, setAvatarFailed] = useState(false);

  const open = (url: string) => {
    openUrl(url).catch(() => showToast("error", "No se pudo abrir el enlace en el navegador."));
  };

  const contactByEmail = () => {
    // Copia la dirección (útil si no hay cliente de correo) y abre el cliente predeterminado.
    navigator.clipboard?.writeText(DEVELOPER.email)
      .then(() => showToast("success", `Correo copiado: ${DEVELOPER.email}`))
      .catch(() => showToast("success", DEVELOPER.email));
    open(`mailto:${DEVELOPER.email}`);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6 lg:p-8">
      <div>
        <p className="eyebrow">Acerca de</p>
        <h1 className="mt-1 text-2xl font-bold">Desarrollador</h1>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="h-24" style={{ background: BANNER_GRADIENT }} />
        <div className="px-6 pb-6">
          <div className="-mt-12 flex flex-wrap items-end gap-4">
            {avatarFailed ? (
              <div className="flex h-24 w-24 items-center justify-center rounded-2xl border-4 border-white bg-gradient-to-br from-primary to-violet-500 text-3xl font-bold text-white shadow-xl ring-1 ring-black/10">
                {DEVELOPER.initials}
              </div>
            ) : (
              <img
                src={DEVELOPER.avatar}
                alt={`Foto de perfil de ${DEVELOPER.name}`}
                onError={() => setAvatarFailed(true)}
                className="h-24 w-24 rounded-2xl border-4 border-white bg-muted object-cover shadow-xl ring-1 ring-black/10"
              />
            )}
            <div className="min-w-0 flex-1 pb-1">
              <h2 className="text-xl font-bold leading-tight">{DEVELOPER.name}</h2>
              <p className="text-sm text-muted-foreground">@{DEVELOPER.handle} · {DEVELOPER.role}</p>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-500">
              <Code2 size={14} /> Proyecto Open Source
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
              {version ? `v${version}` : "Versión no disponible"}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold text-muted-foreground">
              <Scale size={14} /> Licencia {DEVELOPER.license}
            </span>
            <button
              type="button"
              onClick={() => open(DEVELOPER.repository)}
              className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
            >
              <BookOpen size={14} /> Repositorio <ExternalLink size={12} />
            </button>
          </div>

          <div className="mt-6 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => open(DEVELOPER.github)}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-foreground px-4 text-sm font-semibold text-background transition hover:opacity-90"
            >
              <Github size={16} /> Ver perfil en GitHub
            </button>
            {SOCIALS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                type="button"
                title={DEVELOPER[key]}
                onClick={() => open(DEVELOPER[key])}
                className="inline-flex h-10 items-center gap-2 rounded-md border bg-muted/40 px-4 text-sm font-semibold transition-colors hover:bg-accent"
              >
                <Icon size={16} /> {label}
              </button>
            ))}
            <button
              type="button"
              title={`Escribir a ${DEVELOPER.email} (se copia al portapapeles)`}
              onClick={contactByEmail}
              className="inline-flex h-10 items-center gap-2 rounded-md border bg-muted/40 px-4 text-sm font-semibold transition-colors hover:bg-accent"
            >
              <Mail size={16} /> {DEVELOPER.email}
            </button>
          </div>

          <div className="mt-6 border-t pt-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[.16em] text-muted-foreground">Stack tecnológico</p>
            <div className="flex flex-wrap gap-2">
              {STACK.map((item) => <Badge key={item}>{item}</Badge>)}
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}

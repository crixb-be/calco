import { useEffect, useRef, useState } from "react";
import type { PdfFont } from "./types";

const colors = [
  ["negro", "#111827"], ["gris", "#6b7280"], ["blanco", "#ffffff"], ["rojo", "#ef4444"],
  ["naranja", "#f97316"], ["amarillo", "#facc15"], ["verde", "#22c55e"], ["cian", "#06b6d4"],
  ["azul", "#3b82f6"], ["violeta", "#8b5cf6"], ["rosa", "#ec4899"],
] as const;

function useDismiss(ref: React.RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => { if (ref.current && !ref.current.contains(event.target as Node)) onClose(); };
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("pointerdown", onPointerDown); document.removeEventListener("keydown", onKeyDown); };
  }, [onClose, ref]);
}

function swatchStyle(value: string | null): React.CSSProperties {
  return value ? { backgroundColor: value } : { backgroundImage: "linear-gradient(45deg, #d1d5db 25%, transparent 25%, transparent 75%, #d1d5db 75%), linear-gradient(45deg, #d1d5db 25%, transparent 25%, transparent 75%, #d1d5db 75%)", backgroundPosition: "0 0, 6px 6px", backgroundSize: "12px 12px", backgroundColor: "#fff" };
}

export function ColorPicker({ value, onChange, label, allowTransparent = false }: { value: string | null; onChange: (value: string | null) => void; label: string; allowTransparent?: boolean }) {
  const [open, setOpen] = useState(false);
  const [hex, setHex] = useState(value ?? "#111827");
  const rootRef = useRef<HTMLDivElement>(null);
  const close = () => setOpen(false);
  useDismiss(rootRef, close);
  useEffect(() => { setHex(value ?? "#111827"); }, [value]);
  function applyHex(next: string) { setHex(next); if (/^#[0-9a-f]{6}$/i.test(next)) onChange(next.toLowerCase()); }
  return <div ref={rootRef} className="relative flex items-center gap-1.5">
    <span className="text-xs text-muted-foreground">{label}</span>
    <button type="button" aria-label={label} title={label} onClick={() => setOpen((current) => !current)} className="h-6 w-6 rounded-full border shadow-sm" style={swatchStyle(value)} />
    {open && <div className="absolute left-0 top-8 z-50 w-64 rounded-lg border bg-card p-3 shadow-xl" onPointerDown={(event) => event.stopPropagation()}>
      <div className="mb-2 grid grid-cols-6 gap-1.5">
        {allowTransparent && <button type="button" title="Sin relleno" aria-label="Sin relleno" onClick={() => { onChange(null); close(); }} className={`h-7 w-7 rounded-full border ${value === null ? "ring-2 ring-primary" : ""}`} style={swatchStyle(null)} />}
        {colors.map(([name, color]) => <button type="button" key={color} title={`${name} ${color}`} aria-label={`${name} ${color}`} onClick={() => { onChange(color); close(); }} className={`h-7 w-7 rounded-full border ${value === color ? "ring-2 ring-primary" : ""}`} style={swatchStyle(color)} />)}
      </div>
      <div className="flex items-center gap-2">
        <input aria-label="Color hexadecimal" value={hex} onChange={(event) => applyHex(event.target.value)} className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2 text-xs uppercase outline-none focus:ring-2 focus:ring-ring" placeholder="#rrggbb" />
        <input aria-label="Selector de color nativo" type="color" value={/^#[0-9a-f]{6}$/i.test(hex) ? hex : "#111827"} onChange={(event) => applyHex(event.target.value)} className="h-8 w-9 cursor-pointer rounded border bg-transparent p-1" />
      </div>
      {allowTransparent && <p className="mt-2 text-[11px] text-muted-foreground">Transparente: sin relleno</p>}
    </div>}
  </div>;
}

export function StrokePicker({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const close = () => setOpen(false);
  useDismiss(rootRef, close);
  return <div ref={rootRef} className="relative flex items-center gap-1.5">
    <span className="text-xs text-muted-foreground">Grosor</span>
    <button type="button" aria-label="Grosor del trazo" title="Grosor del trazo" onClick={() => setOpen((current) => !current)} className="flex h-7 min-w-20 items-center gap-2 rounded-md border bg-background px-2 text-xs hover:bg-accent"><span className="block w-8 rounded-full bg-foreground" style={{ height: Math.min(value, 12) }} /><span>{value} pt</span></button>
    {open && <div className="absolute left-0 top-8 z-50 min-w-32 rounded-lg border bg-card p-1 shadow-xl">{[1, 2, 4, 8, 12].map((size) => <button type="button" key={size} onClick={() => { onChange(size); close(); }} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-accent"><span className="block w-8 rounded-full bg-foreground" style={{ height: size }} /><span>{size} pt</span></button>)}</div>}
  </div>;
}

export function ToggleButton({ pressed, label, children, onClick }: { pressed: boolean; label: string; children: React.ReactNode; onClick: () => void }) {
  return <button type="button" aria-label={label} aria-pressed={pressed} title={label} onClick={onClick} className={`h-7 min-w-8 rounded-md border px-2 text-xs font-semibold transition ${pressed ? "border-primary bg-primary/15 text-primary" : "bg-background hover:bg-accent"}`}>{children}</button>;
}

export function FontSelect({ value, onChange }: { value: PdfFont; onChange: (value: PdfFont) => void }) {
  return <label className="flex items-center gap-1.5 text-xs text-muted-foreground">Fuente<select aria-label="Fuente" value={value} onChange={(event) => onChange(event.target.value as PdfFont)} className="h-7 rounded-md border bg-background px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"><option value="helv">Helvetica</option><option value="tiro">Times</option><option value="cour">Courier</option></select></label>;
}

const sizes = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 64, 72, 96];

export function FontSizeSelect({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <label className="flex items-center gap-1.5 text-xs text-muted-foreground">Tamaño<select aria-label="Tamaño de texto en puntos" value={sizes.includes(value) ? value : "custom"} onChange={(event) => { if (event.target.value !== "custom") onChange(Number(event.target.value)); }} className="h-7 rounded-md border bg-background px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring">{sizes.map((size) => <option key={size} value={size}>{size} pt</option>)}{!sizes.includes(value) && <option value="custom">{value} pt</option>}</select><input aria-label="Tamaño personalizado en puntos" type="number" min={1} max={200} value={value} onChange={(event) => onChange(Math.max(1, Math.min(200, Number(event.target.value) || 1)))} className="h-7 w-14 rounded-md border bg-background px-2 text-xs text-foreground outline-none focus:ring-2 focus:ring-ring" /></label>;
}

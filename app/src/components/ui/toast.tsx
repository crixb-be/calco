import { create } from "zustand";
import { CheckCircle2, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastKind = "success" | "error";
interface ToastState {
  toast: { id: number; kind: ToastKind; message: string } | null;
  show: (kind: ToastKind, message: string) => void;
  dismiss: () => void;
}

export const useToast = create<ToastState>((set) => ({
  toast: null,
  show: (kind, message) => {
    const id = Date.now();
    set({ toast: { id, kind, message } });
    window.setTimeout(() => set((state) => (state.toast?.id === id ? { toast: null } : state)), 3000);
  },
  dismiss: () => set({ toast: null }),
}));

export function Toaster() {
  const toast = useToast((state) => state.toast);
  const dismiss = useToast((state) => state.dismiss);
  if (!toast) return null;
  const success = toast.kind === "success";
  return (
    <div className="fixed bottom-5 right-[380px] z-50 flex max-w-sm items-center gap-3 rounded-lg border bg-card px-4 py-3 text-sm shadow-2xl">
      {success ? <CheckCircle2 className="shrink-0 text-emerald-400" size={18} /> : <XCircle className="shrink-0 text-red-400" size={18} />}
      <span className="flex-1">{toast.message}</span>
      <button type="button" onClick={dismiss} className={cn("text-muted-foreground", success ? "hover:text-emerald-300" : "hover:text-red-300")} aria-label="Cerrar aviso">
        <X size={16} />
      </button>
    </div>
  );
}

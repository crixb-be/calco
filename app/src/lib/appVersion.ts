import { useEffect, useState } from "react";
import { getVersion } from "@tauri-apps/api/app";

let cached: string | null = null;

/** Versión de la app leída de tauri.conf.json en tiempo de ejecución (cadena vacía fuera de Tauri). */
export function useAppVersion() {
  const [version, setVersion] = useState(cached ?? "");
  useEffect(() => {
    if (cached) return;
    getVersion()
      .then((value) => {
        cached = value;
        setVersion(value);
      })
      .catch(() => setVersion(""));
  }, []);
  return version;
}

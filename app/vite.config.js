import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: { "@": path.resolve(fileURLToPath(new URL("./src", import.meta.url))) }
    },
    clearScreen: false,
    server: {
        port: 1420,
        strictPort: true,
        watch: {
            ignored: ["**/src-tauri/**"]
        }
    },
    envPrefix: ["VITE_", "TAURI_"],
    build: {
        target: ["es2021", "chrome105", "safari13"],
        chunkSizeWarningLimit: 1200,
    }
});

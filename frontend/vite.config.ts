import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: Record<string, string | undefined> };

// `npm run dev` serves the desk at http://localhost:5173 and opens it in the browser.
// The backend (http://localhost:8000) allows this exact origin, so the port is fixed.
// Set BROWSER=none to start it without opening a browser tab.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, open: process.env.BROWSER !== "none" },
});

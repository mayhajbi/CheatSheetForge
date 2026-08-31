import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// שרת ה-dev מפנה בקשות /api ל-backend המקומי (FastAPI על פורט 8000).
// בפריסת Railway יש להגדיר VITE_API_BASE_URL כמשתנה סביבה במקום proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});

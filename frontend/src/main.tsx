import "@fontsource-variable/inter";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { AuthProvider } from "./lib/auth";
import { ToastProvider } from "./lib/toast";

// Report unexpected browser errors so problems surface before users report them (no personal data is sent).
function report(message: string, stack?: string) {
  try {
    navigator.sendBeacon?.("/api/client-errors", JSON.stringify({ message: message.slice(0, 500), stack: (stack ?? "").slice(0, 2000), path: location.pathname }));
  } catch { /* ignore */ }
}
window.addEventListener("error", (e) => report(e.message, e.error?.stack));
window.addEventListener("unhandledrejection", (e) => report(String(e.reason?.message ?? e.reason), e.reason?.stack));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);

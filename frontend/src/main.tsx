import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AuthProvider } from "./auth";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { initSentry } from "./observability";
import "./index.css";

// Antes do render, e sem esperar: o SDK entra por import dinâmico e o portal não tem por que
// atrasar a primeira pintura para carregá-lo. No-op sem DSN.
void initSentry();

createRoot(document.getElementById("root")!).render(
  <StrictMode><ErrorBoundary><AuthProvider><App /></AuthProvider></ErrorBoundary></StrictMode>,
);

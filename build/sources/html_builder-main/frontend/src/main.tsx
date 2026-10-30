import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Spinner } from "./components/ui";
import "./index.css";

const Home = lazy(() => import("./pages/Home"));
const ProjectPage = lazy(() => import("./pages/Project"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Library = lazy(() => import("./pages/Library"));

// apply saved theme before first paint
try {
  const t = localStorage.getItem("hp-experience-theme") || "system";
  document.documentElement.classList.toggle("dark", t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches));
} catch { /* storage unavailable */ }

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 2000, refetchOnWindowFocus: true, retry: 1 } } });

function Loading() {
  return <div className="flex h-full min-h-[50vh] items-center justify-center text-muted"><Spinner className="size-5" /></div>;
}

/** One boundary per route, reset whenever the user navigates somewhere else. */
function AppRoutes() {
  const loc = useLocation();
  return (
    <ErrorBoundary resetKey={loc.pathname} title="This page hit a snag">
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/p/:id/*" element={<ProjectPage />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/library" element={<Library />} />
          <Route path="*" element={<Home />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("index.html is missing its #root element");

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <TooltipPrimitive.Provider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
        <Toaster position="top-center" richColors closeButton offset={64} />
      </TooltipPrimitive.Provider>
    </QueryClientProvider>
  </StrictMode>,
);

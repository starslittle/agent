import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import AuthPage from "./pages/AuthPage";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import AgentRunsPage from "./pages/AgentRunsPage";
import AgentObservabilityPage from "./pages/AgentObservabilityPage";
import { ObservabilityRoute } from "./auth/ObservabilityRoute";
import SpacePage from "./pages/SpacePage";
import DocumentPage from "./pages/DocumentPage";
import ContextItemPage from "./pages/ContextItemPage";
import SkillsPage from "./pages/SkillsPage";
import { SkillCatalogProvider } from "./features/skills/SkillCatalogProvider";

const queryClient = new QueryClient();

const App = () => (
  <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <AuthProvider>
            <SkillCatalogProvider><Routes>
              <Route path="/login" element={<AuthPage />} />
              <Route path="/register" element={<AuthPage />} />
              <Route path="/" element={<Index />} />
              <Route
                path="/chat/:conversationId"
                element={(
                  <ProtectedRoute>
                    <Index />
                  </ProtectedRoute>
                )}
              />
              <Route
                path="/agent-runs"
                element={(
                  <ProtectedRoute>
                    <AgentRunsPage />
                  </ProtectedRoute>
                )}
              />
              <Route
                path="/agent-runs/:runId"
                element={(
                  <ProtectedRoute>
                    <AgentRunsPage />
                  </ProtectedRoute>
                )}
              />
              <Route
                path="/space"
                element={<ProtectedRoute><SpacePage /></ProtectedRoute>}
              />
              <Route
                path="/space/folders/:folderId"
                element={<ProtectedRoute><SpacePage /></ProtectedRoute>}
              />
              <Route
                path="/space/documents/:documentId"
                element={<ProtectedRoute><DocumentPage /></ProtectedRoute>}
              />
              <Route
                path="/space/context/:itemId"
                element={<ProtectedRoute><ContextItemPage /></ProtectedRoute>}
              />
              <Route path="/skills" element={<ProtectedRoute><SkillsPage /></ProtectedRoute>} />
              <Route path="/skills/:skillId" element={<ProtectedRoute><SkillsPage /></ProtectedRoute>} />
              <Route
                path="/internal/agent-runs"
                element={<ObservabilityRoute><AgentObservabilityPage /></ObservabilityRoute>}
              />
              <Route
                path="/internal/agent-runs/:runId"
                element={<ObservabilityRoute><AgentObservabilityPage /></ObservabilityRoute>}
              />
              <Route path="*" element={<NotFound />} />
            </Routes></SkillCatalogProvider>
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  </ThemeProvider>
);

export default App;

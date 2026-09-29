import { Suspense, lazy } from "react";
import { Routes, Route, useParams, Navigate } from "react-router-dom";
import { PageLayout } from "@/components/layout/PageLayout";
import Home from "@/pages/Home";
import Solutions from "@/pages/Solutions";
import Trust from "@/pages/Trust";
import Contact from "@/pages/Contact";
import Login from "@/pages/Login";
import ForgotPassword from "@/pages/ForgotPassword";
import LegalStub from "@/pages/LegalStub";
import NotFound from "@/pages/NotFound";
import { ProtectedRoute } from "@/pages/console/ProtectedRoute";
import { ConsoleLayout } from "@/pages/console/ConsoleLayout";
import ReviewQueue from "@/pages/console/ReviewQueue";
import CaseDetailPage from "@/pages/console/CaseDetail";

// The ECharts core pulled in by Analytics is the heaviest single dependency
// in the app; code-splitting it keeps that weight off every other route.
const Analytics = lazy(() => import("@/pages/console/Analytics"));

function LegalRoute() {
  const { slug = "" } = useParams();
  return <LegalStub slug={slug} />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />

      <Route path="/app" element={<Navigate to="/app/cases" replace />} />
      <Route
        path="/app/cases"
        element={
          <ProtectedRoute>
            <ConsoleLayout>
              <ReviewQueue />
            </ConsoleLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/cases/:id"
        element={
          <ProtectedRoute>
            <ConsoleLayout>
              <CaseDetailPage />
            </ConsoleLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/analytics"
        element={
          <ProtectedRoute>
            <ConsoleLayout>
              <Suspense fallback={<div className="p-10 text-sm text-neutral-900/70">Loading...</div>}>
                <Analytics />
              </Suspense>
            </ConsoleLayout>
          </ProtectedRoute>
        }
      />

      <Route
        path="/"
        element={
          <PageLayout>
            <Home />
          </PageLayout>
        }
      />
      <Route
        path="/solutions"
        element={
          <PageLayout>
            <Solutions />
          </PageLayout>
        }
      />
      <Route
        path="/trust"
        element={
          <PageLayout>
            <Trust />
          </PageLayout>
        }
      />
      <Route
        path="/contact"
        element={
          <PageLayout>
            <Contact />
          </PageLayout>
        }
      />
      <Route
        path="/legal/:slug"
        element={
          <PageLayout>
            <LegalRoute />
          </PageLayout>
        }
      />
      <Route
        path="*"
        element={
          <PageLayout>
            <NotFound />
          </PageLayout>
        }
      />
    </Routes>
  );
}

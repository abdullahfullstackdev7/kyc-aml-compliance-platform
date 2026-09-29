import { Routes, Route, useParams } from "react-router-dom";
import { PageLayout } from "@/components/layout/PageLayout";
import Home from "@/pages/Home";
import Solutions from "@/pages/Solutions";
import Trust from "@/pages/Trust";
import Contact from "@/pages/Contact";
import Login from "@/pages/Login";
import ForgotPassword from "@/pages/ForgotPassword";
import LegalStub from "@/pages/LegalStub";
import NotFound from "@/pages/NotFound";

function LegalRoute() {
  const { slug = "" } = useParams();
  return <LegalStub slug={slug} />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />

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

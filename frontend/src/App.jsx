import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { getAuthenticatedUser, signOut } from "./services/authService";
import PageTransition from "./components/PageTransition";
import Signup from "./pages/Signup";
import Login from "./pages/Login";
import VerifyId from "./pages/VerifyId";
import Dashboard from "./pages/Dashboard";

function ProtectedRoute({ children }) {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    getAuthenticatedUser()
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false))
      .finally(() => setChecking(false));
  }, []);

  if (checking) {
    return (
      <div className="page">
        <div className="page-inner">
          <p style={{ textAlign: "center", color: "var(--text-secondary)" }}>
            Loading…
          </p>
        </div>
      </div>
    );
  }

  if (!authenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <PageTransition>
      <Routes location={location} key={location.pathname}>
        <Route path="/signup" element={<Signup />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/verify-id"
          element={
            <ProtectedRoute>
              <VerifyId />
            </ProtectedRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </PageTransition>
  );
}

export default function App() {
  useEffect(() => {
    function handleExit() {
      signOut();
    }
    window.addEventListener("pagehide", handleExit);
    return () => window.removeEventListener("pagehide", handleExit);
  }, []);

  return (
    <>
      <div className="app-background" aria-hidden="true">
        <div className="liquid-blob liquid-blob--1" />
        <div className="liquid-blob liquid-blob--2" />
        <div className="liquid-blob liquid-blob--3" />
      </div>
      <BrowserRouter>
        <AnimatedRoutes />
      </BrowserRouter>
    </>
  );
}

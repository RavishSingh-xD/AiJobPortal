import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { getAuthenticatedUser } from "./services/authService";
import PageTransition from "./components/PageTransition";
import Home from "./pages/Home";
import Signup from "./pages/Signup";
import Login from "./pages/Login";
import VerifyEmail from "./pages/VerifyEmail";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import VerifyId from "./pages/VerifyId";
import Dashboard from "./pages/Dashboard";
import JobListings from "./pages/JobListings";
import MatchWizard from "./pages/MatchWizard";
import Applications from "./pages/Applications";
import SavedJobs from "./pages/SavedJobs";

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
        <Route path="/" element={<Home />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/login" element={<Login />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/jobs" element={<JobListings />} />
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
        <Route
          path="/match"
          element={
            <ProtectedRoute>
              <MatchWizard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/applications"
          element={
            <ProtectedRoute>
              <Applications />
            </ProtectedRoute>
          }
        />
        <Route
          path="/saved-jobs"
          element={
            <ProtectedRoute>
              <SavedJobs />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </PageTransition>
  );
}

export default function App() {
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

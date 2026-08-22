import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { getAuthenticatedUser, getUserProfile } from "./services/authService";
import { requiresIdentityVerification } from "./utils/verification";
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
import CompareRoles from "./pages/CompareRoles";
import SearchAlerts from "./pages/SearchAlerts";

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
          <p className="micro-label" style={{ textAlign: "center" }}>Loading</p>
        </div>
      </div>
    );
  }

  if (!authenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function VerifiedRoute({ children }) {
  const [checking, setChecking] = useState(true);
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    getAuthenticatedUser()
      .then(() => getUserProfile())
      .then((profile) => {
        setAllowed(!requiresIdentityVerification(profile));
      })
      .catch(() => setAllowed(false))
      .finally(() => setChecking(false));
  }, []);

          if (checking) {
    return (
      <div className="page">
        <div className="page-inner">
          <p className="micro-label" style={{ textAlign: "center" }}>Loading</p>
        </div>
      </div>
    );
  }

  if (!allowed) {
    return <Navigate to="/verify-id" replace />;
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
        <Route
          path="/jobs"
          element={
            <ProtectedRoute>
              <VerifiedRoute>
                <JobListings />
              </VerifiedRoute>
            </ProtectedRoute>
          }
        />
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
              <VerifiedRoute>
                <Dashboard />
              </VerifiedRoute>
            </ProtectedRoute>
          }
        />
        <Route
          path="/match"
          element={
            <ProtectedRoute>
              <VerifiedRoute>
                <MatchWizard />
              </VerifiedRoute>
            </ProtectedRoute>
          }
        />
        <Route
          path="/applications"
          element={
            <ProtectedRoute>
              <VerifiedRoute>
                <Applications />
              </VerifiedRoute>
            </ProtectedRoute>
          }
        />
        <Route
          path="/saved-jobs"
          element={
            <ProtectedRoute>
              <VerifiedRoute>
                <SavedJobs />
              </VerifiedRoute>
            </ProtectedRoute>
          }
        />
        <Route
          path="/compare"
          element={
            <ProtectedRoute>
              <VerifiedRoute>
                <CompareRoles />
              </VerifiedRoute>
            </ProtectedRoute>
          }
        />
        <Route
          path="/search-alerts"
          element={
            <ProtectedRoute>
              <VerifiedRoute>
                <SearchAlerts />
              </VerifiedRoute>
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
    <BrowserRouter>
      <AnimatedRoutes />
    </BrowserRouter>
  );
}

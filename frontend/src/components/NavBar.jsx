import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { getUserProfile, logoutUser } from "../services/authService";
import GlassCard from "./GlassCard";
import AnimatedButton from "./AnimatedButton";

export default function NavBar() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");

  useEffect(() => {
    async function loadUser() {
      try {
        const profile = await getUserProfile();
        setEmail(profile.email || "");
      } catch {
        setEmail("");
      }
    }
    loadUser();
  }, []);

  const handleLogout = async () => {
    setLoading(true);
    try {
      await logoutUser();
      navigate("/login");
    } catch {
      navigate("/login");
    } finally {
      setLoading(false);
    }
  };

  return (
    <GlassCard className="glass-card--compact dashboard-topbar" hover={false}>
      <div className="dashboard-topbar__brand">
        <span className="dashboard-topbar__logo" aria-hidden="true">
          🎓
        </span>
        Avyukt.work
      </div>
      <nav className="navbar__links" aria-label="Main">
        <NavLink
          to="/dashboard"
          className={({ isActive }) =>
            `navbar__link${isActive ? " navbar__link--active" : ""}`
          }
        >
          Dashboard
        </NavLink>
        <NavLink
          to="/jobs"
          className={({ isActive }) =>
            `navbar__link${isActive ? " navbar__link--active" : ""}`
          }
        >
          Find Roles
        </NavLink>
        <NavLink
          to="/applications"
          className={({ isActive }) =>
            `navbar__link${isActive ? " navbar__link--active" : ""}`
          }
        >
          Applications
        </NavLink>
        <NavLink
          to="/saved-jobs"
          className={({ isActive }) =>
            `navbar__link${isActive ? " navbar__link--active" : ""}`
          }
        >
          Saved
        </NavLink>
      </nav>
      <div className="dashboard-topbar__actions">
        {email && <span className="dashboard-topbar__email">{email}</span>}
        <AnimatedButton
          secondary
          className="btn--compact"
          loading={loading}
          onClick={handleLogout}
        >
          {loading ? "Signing out…" : "Log out"}
        </AnimatedButton>
      </div>
    </GlassCard>
  );
}

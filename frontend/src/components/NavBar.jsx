import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { getUserProfile, logoutUser } from "../services/authService";
import AnimatedButton from "./AnimatedButton";

export default function NavBar() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState("");

  useEffect(() => {
    async function loadUser() {
      try {
        const profile = await getUserProfile();
        setName(profile.name || profile.email || "");
      } catch {
        setName("");
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
    <header className="dashboard-topbar">
      <div className="dashboard-topbar__brand">
        <img
          src="/avyukt-logo.png"
          alt=""
          className="dashboard-topbar__logo-img"
          width={28}
          height={28}
        />
        Avyukt
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
          to="/search-alerts"
          className={({ isActive }) =>
            `navbar__link${isActive ? " navbar__link--active" : ""}`
          }
        >
          Alerts
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
        {name && <span className="dashboard-topbar__email">{name}</span>}
        <AnimatedButton
          secondary
          className="btn--compact"
          loading={loading}
          onClick={handleLogout}
        >
          {loading ? "Signing out…" : "Log out"}
        </AnimatedButton>
      </div>
    </header>
  );
}

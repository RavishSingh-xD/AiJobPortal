import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { motion, LayoutGroup } from "framer-motion";
import { getUserProfile, logoutUser } from "../services/authService";
import AnimatedButton from "./AnimatedButton";

const LINKS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/jobs", label: "Find Roles" },
  { to: "/applications", label: "Applications" },
  { to: "/search-alerts", label: "Alerts" },
  { to: "/saved-jobs", label: "Saved" },
];

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
      <LayoutGroup>
      <nav className="navbar__links" aria-label="Main">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `navbar__link${isActive ? " navbar__link--active" : ""}`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.span
                    className="navbar__indicator"
                    layoutId="nav-indicator"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="navbar__link-text">{link.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
      </LayoutGroup>
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

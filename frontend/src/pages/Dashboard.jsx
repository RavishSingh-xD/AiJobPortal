import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getUserProfile,
  logoutUser,
} from "../services/authService";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";

const STAT_CARDS = [
  { icon: "📋", label: "Applications", value: "Coming soon" },
  { icon: "⭐", label: "Saved Internships", value: "Coming soon" },
  { icon: "✨", label: "Profile Completion", value: "Coming soon" },
];

function formatVerificationStatus(status) {
  if (!status) return { label: "Unknown", variant: "default" };

  const labels = {
    verified: "Verified",
    pending_review: "Pending review",
    rejected: "Rejected",
  };

  return {
    label: labels[status] ?? status.replace(/_/g, " "),
    variant: labels[status] ? status : "default",
  };
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [userAttributes, setUserAttributes] = useState({
    name: "",
    email: "",
    verificationStatus: "",
  });

  useEffect(() => {
    async function loadUser() {
      const profile = await getUserProfile();
      setUserAttributes({
        name: profile.name || profile.email || "",
        email: profile.email || "",
        verificationStatus: profile.verificationStatus ?? "",
      });
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

  const badge = formatVerificationStatus(userAttributes.verificationStatus);

  return (
    <div className="page page--dashboard">
      <div className="dashboard">
        <GlassCard className="glass-card--compact dashboard-topbar">
          <div className="dashboard-topbar__brand">
            <span className="dashboard-topbar__logo" aria-hidden="true">
              🎓
            </span>
            AiJobPortal
          </div>
          <div className="dashboard-topbar__actions">
            {userAttributes.email && (
              <span className="dashboard-topbar__email">{userAttributes.email}</span>
            )}
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

        <div className="dashboard-welcome">
          <h1 className="dashboard-welcome__title">
            Welcome back{userAttributes.name ? `, ${userAttributes.name}` : ""}
          </h1>
          {userAttributes.verificationStatus && (
            <span
              className={`status-badge status-badge--${badge.variant}`}
            >
              {badge.label}
            </span>
          )}
        </div>

        <div className="dashboard-stats">
          {STAT_CARDS.map((stat, index) => (
            <GlassCard
              key={stat.label}
              className="glass-card--stat"
              delay={0.1 + index * 0.1}
            >
              <div className="stat-card__icon" aria-hidden="true">
                {stat.icon}
              </div>
              <p className="stat-card__label">{stat.label}</p>
              <p className="stat-card__value">{stat.value}</p>
            </GlassCard>
          ))}
        </div>

        <GlassCard className="glass-card--section" delay={0.4}>
          <div className="dashboard-coming-soon">
            <div className="dashboard-coming-soon__icon" aria-hidden="true">
              💼
            </div>
            <h2 className="dashboard-coming-soon__title">
              Internship listings are coming soon
            </h2>
            <p className="dashboard-coming-soon__text">
              We&apos;re building personalized recommendations based on your
              profile. Check back here for curated internship opportunities.
            </p>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

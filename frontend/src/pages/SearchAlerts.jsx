import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listSavedSearches,
  deleteSavedSearch,
  ackSavedSearch,
  getSavedSearchAlerts,
} from "../services/apiClient";
import GlassCard from "../components/GlassCard";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import { apiErrorMessage } from "../utils/errors";

export default function SearchAlerts() {
  const navigate = useNavigate();
  const [searches, setSearches] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [searchData, alertData] = await Promise.all([
        listSavedSearches(),
        getSavedSearchAlerts(),
      ]);
      setSearches(searchData.savedSearches || []);
      setAlerts(alertData.alerts || []);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not load saved searches."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleDelete = async (searchId) => {
    try {
      await deleteSavedSearch(searchId);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not delete saved search."));
    }
  };

  const handleAck = async (searchId, canonicalIds) => {
    try {
      await ackSavedSearch(searchId, canonicalIds);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not mark alerts as seen."));
    }
  };

  return (
    <div className="page page--dashboard">
      <div className="dashboard">
        <NavBar />
        <GlassCard hover={false} className="glass-card--section">
          <div className="glass-card__header">
            <h1 className="glass-card__title">Search alerts</h1>
            <p className="glass-card__subtitle">
              New listings that match your saved searches.
            </p>
          </div>

          {loading && <p className="compare-muted">Loading…</p>}
          {error && <div className="form-error">{error}</div>}

          {!loading && alerts.length === 0 && (
            <p className="compare-muted">No new matches right now. Save a search from Browse Roles.</p>
          )}

          {alerts.map((alert) => (
            <section key={alert.searchId} className="discovery-panel">
              <h2 className="discovery-panel__title">
                {alert.label || `${alert.domain} search`}
                <span className="alert-badge">{alert.newMatchCount} new</span>
              </h2>
              <ul className="alert-list">
                {(alert.newMatches || []).map((job) => (
                  <li key={job.canonical_id} className="alert-list__item">
                    <strong>{job.title}</strong> · {job.company}
                  </li>
                ))}
              </ul>
              <AnimatedButton
                type="button"
                className="btn--compact"
                onClick={() =>
                  handleAck(
                    alert.searchId,
                    (alert.newMatches || []).map((job) => job.canonical_id).filter(Boolean)
                  )
                }
              >
                Mark as seen
              </AnimatedButton>
            </section>
          ))}

          {!loading && searches.length > 0 && (
            <section className="discovery-panel">
              <h2 className="discovery-panel__title">Saved searches</h2>
              <ul className="alert-list">
                {searches.map((search) => (
                  <li key={search.searchId} className="alert-list__item alert-list__item--row">
                    <span>
                      {search.label || search.domain}
                      {search.skill ? ` · ${search.skill}` : ""}
                      {search.employmentType ? ` · ${search.employmentType}` : ""}
                    </span>
                    <AnimatedButton
                      secondary
                      type="button"
                      className="btn--compact"
                      onClick={() => handleDelete(search.searchId)}
                    >
                      Remove
                    </AnimatedButton>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div style={{ marginTop: "1.25rem", display: "flex", gap: "0.75rem" }}>
            <AnimatedButton secondary type="button" onClick={() => navigate("/jobs")}>
              Browse roles
            </AnimatedButton>
            <AnimatedButton secondary type="button" onClick={() => navigate("/dashboard")}>
              Dashboard
            </AnimatedButton>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

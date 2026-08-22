import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listSavedSearches,
  deleteSavedSearch,
  ackSavedSearch,
  getSavedSearchAlerts,
} from "../services/apiClient";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import Surface from "../components/Surface";
import { MotionListItem } from "../components/motionConfig";
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
        <PageHeader
          label="Alerts"
          title="Search alerts"
          subtitle="New listings that match your saved searches."
        />

        {loading && <EmptyState variant="loading" loading title="Loading alerts" />}
        {error && <div className="form-error">{error}</div>}

        {!loading && alerts.length === 0 && !error && (
          <EmptyState
            title="No new matches"
            text="Save a search from Browse Roles to get alerts here."
          />
        )}

        {alerts.map((alert, alertIndex) => (
          <Surface
            key={alert.searchId}
            hover={false}
            flush
            delay={alertIndex * 0.04}
            className="discovery-panel"
          >
            <div className="discovery-panel__header">
              <h2 className="discovery-panel__title">
                {alert.label || `${alert.domain} search`}
                <span className="alert-badge">{alert.newMatchCount} new</span>
              </h2>
            </div>
            <ul className="alert-list">
              {(alert.newMatches || []).map((job, index) => (
                <MotionListItem key={job.canonical_id} as="li" index={index} className="alert-list__item">
                  <strong>{job.title}</strong> · {job.company}
                </MotionListItem>
              ))}
            </ul>
            <div style={{ padding: "0.75rem 1rem" }}>
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
            </div>
          </Surface>
        ))}

        {!loading && searches.length > 0 && (
          <Surface hover={false} flush delay={0.08} className="discovery-panel">
            <div className="discovery-panel__header">
              <h2 className="discovery-panel__title">Saved searches</h2>
            </div>
            <ul className="alert-list">
              {searches.map((search, index) => (
                <MotionListItem
                  key={search.searchId}
                  as="li"
                  index={index}
                  className="alert-list__item alert-list__item--row"
                >
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
                </MotionListItem>
              ))}
            </ul>
          </Surface>
        )}

        <div style={{ marginTop: "1.25rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <AnimatedButton secondary type="button" className="btn--compact" onClick={() => navigate("/jobs")}>
            Browse roles
          </AnimatedButton>
          <AnimatedButton secondary type="button" className="btn--compact" onClick={() => navigate("/dashboard")}>
            Dashboard
          </AnimatedButton>
        </div>
      </div>
    </div>
  );
}

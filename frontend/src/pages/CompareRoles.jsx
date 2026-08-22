import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { compareJobs } from "../services/apiClient";
import AnimatedButton from "../components/AnimatedButton";
import NavBar from "../components/NavBar";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import { apiErrorMessage } from "../utils/errors";

const MAX_COMPARE = 4;

function PowBar({ powBar }) {
  if (!powBar) {
    return <span className="compare-muted">—</span>;
  }
  const max = Math.max(powBar.requiredPowScore, powBar.yourPowScore, 1);
  const yourWidth = Math.min(100, (powBar.yourPowScore / max) * 100);
  const reqWidth = Math.min(100, (powBar.requiredPowScore / max) * 100);
  return (
    <div className="compare-pow">
      <div className="compare-pow__bar">
        <div className="compare-pow__fill" style={{ width: `${yourWidth}%` }} />
        <div className="compare-pow__marker" style={{ left: `${reqWidth}%` }} />
      </div>
      <p className="compare-pow__label tabular-nums">
        You {powBar.yourPowScore} / needs {powBar.requiredPowScore}
        {powBar.meetsRequirement ? " · pass" : ` · gap ${powBar.gap}`}
      </p>
    </div>
  );
}

export default function CompareRoles() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const domain = searchParams.get("domain") || "Engineering";
  const idsParam = searchParams.get("ids") || "";
  const sessionId = searchParams.get("sessionId") || "";
  const canonicalIds = idsParam.split(",").filter(Boolean).slice(0, MAX_COMPARE);

  const [uiState, setUiState] = useState("loading");
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    if (canonicalIds.length < 2) {
      setUiState("error");
      setError("Select at least two roles to compare.");
      return;
    }

    let cancelled = false;
    setUiState("loading");
    setError("");

    compareJobs({
      domain,
      canonicalIds,
      sessionId: sessionId || undefined,
    })
      .then((data) => {
        if (cancelled) return;
        setJobs(data.jobs || []);
        setUiState((data.jobs || []).length ? "ready" : "empty");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(apiErrorMessage(err, "Could not load comparison."));
        setUiState("error");
      });

    return () => {
      cancelled = true;
    };
  }, [domain, idsParam, sessionId]);

  const rows = [
    { key: "title", label: "Role" },
    { key: "company", label: "Company" },
    { key: "location", label: "Location" },
    { key: "employment_type", label: "Type" },
    { key: "min_pow_score", label: "PoW required" },
    { key: "powBar", label: "PoW bar" },
    { key: "skillOverlap", label: "Skill overlap" },
    { key: "required_skills", label: "Skills" },
  ];

  return (
    <div className="page page--dashboard">
      <div className="dashboard">
        <NavBar />
        <PageHeader
          label="Compare"
          title="Role comparison"
          subtitle={`Side-by-side view for ${domain} roles you selected.`}
        />

        {uiState === "loading" && (
          <EmptyState variant="loading" loading title="Loading comparison" />
        )}
        {uiState === "error" && (
          <EmptyState variant="error" title="Comparison unavailable" text={error} />
        )}

        {uiState === "ready" && (
          <div className="app-panel app-panel--flush">
            <div className="compare-table-wrap">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th>Field</th>
                    {jobs.map((job) => (
                      <th key={job.canonical_id}>{job.title}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.key}>
                      <th>{row.label}</th>
                      {jobs.map((job) => (
                        <td key={`${job.canonical_id}-${row.key}`}>
                          {row.key === "powBar" ? (
                            <PowBar powBar={job.powBar} />
                          ) : row.key === "required_skills" ? (
                            (job.required_skills || []).join(", ")
                          ) : row.key === "skillOverlap" ? (
                            job.skillOverlap != null
                              ? `${Math.round(job.skillOverlap * 100)}%`
                              : "—"
                          ) : (
                            job[row.key] ?? "—"
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div style={{ marginTop: "1.25rem" }}>
          <AnimatedButton secondary type="button" className="btn--compact" onClick={() => navigate(-1)}>
            Back
          </AnimatedButton>
        </div>
      </div>
    </div>
  );
}

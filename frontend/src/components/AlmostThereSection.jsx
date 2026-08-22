import AnimatedButton from "./AnimatedButton";
import { MotionListItem } from "./motionConfig";

function AlmostThereCard({ job, index, onCompareToggle, compareSelected }) {
  return (
    <MotionListItem index={index} className="match-listing-card match-listing-card--almost">
      <div className="match-listing-card__row">
        <h3 className="match-listing-card__title">{job.title || "Untitled role"}</h3>
        <label className="compare-check">
          <input
            type="checkbox"
            checked={compareSelected}
            onChange={() => onCompareToggle(job)}
          />
          Compare
        </label>
      </div>
      <p className="match-listing-card__meta">
        {[job.company, job.employment_type, job.location].filter(Boolean).join(" · ")}
      </p>
      {job.upgradeSteps?.map((step, stepIndex) => (
        <p key={stepIndex} className="almost-there-step">
          {step.message}
        </p>
      ))}
    </MotionListItem>
  );
}

export default function AlmostThereSection({
  almostThere,
  onCompareToggle,
  compareSelectedIds,
}) {
  const internships = almostThere?.internships || [];
  const jobs = almostThere?.jobs || [];
  if (internships.length + jobs.length === 0) {
    return null;
  }

  return (
    <section className="discovery-panel">
      <div className="discovery-panel__header">
        <h2 className="discovery-panel__title">Almost there</h2>
        <p className="discovery-panel__summary">
          Roles you&apos;re close to qualifying for — follow the upgrade steps below.
        </p>
      </div>
      {internships.length > 0 && (
        <div className="match-listings__section">
          <h3 className="match-listings__heading">Internships</h3>
          {internships.map((job, index) => (
            <AlmostThereCard
              key={job.canonical_id || job.title}
              job={job}
              index={index}
              compareSelected={compareSelectedIds.has(job.canonical_id)}
              onCompareToggle={onCompareToggle}
            />
          ))}
        </div>
      )}
      {jobs.length > 0 && (
        <div className="match-listings__section">
          <h3 className="match-listings__heading">Jobs</h3>
          {jobs.map((job, index) => (
            <AlmostThereCard
              key={job.canonical_id || job.title}
              job={job}
              index={index}
              compareSelected={compareSelectedIds.has(job.canonical_id)}
              onCompareToggle={onCompareToggle}
            />
          ))}
        </div>
      )}
    </section>
  );
}

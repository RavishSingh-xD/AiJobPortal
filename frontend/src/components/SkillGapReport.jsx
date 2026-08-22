import Surface from "./Surface";

export default function SkillGapReport({ report }) {
  if (!report) {
    return null;
  }

  const { strongSkills = [], weakSkills = [], missingSkills = [], summary } = report;

  return (
    <Surface hover={false} flush className="discovery-panel">
      <div className="discovery-panel__header">
        <h2 className="discovery-panel__title">Skill gap report</h2>
        {summary && <p className="discovery-panel__summary">{summary}</p>}
      </div>

      {missingSkills.length > 0 && (
        <div className="skill-gap-group">
          <h3 className="skill-gap-group__title">Missing skills</h3>
          <ul className="skill-gap-list">
            {missingSkills.map((row) => (
              <li key={row.skill} className="skill-gap-item skill-gap-item--missing">
                <div>
                  <strong>{row.skill}</strong>
                  <span className="skill-gap-item__meta">
                    in {row.roleCount} target role{row.roleCount === 1 ? "" : "s"}
                  </span>
                </div>
                {row.learnUrl && (
                  <a className="skill-gap-item__link" href={row.learnUrl} target="_blank" rel="noreferrer">
                    Learn
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {strongSkills.length > 0 && (
        <div className="skill-gap-group">
          <h3 className="skill-gap-group__title">Strong skills</h3>
          <ul className="skill-gap-list">
            {strongSkills.map((row) => (
              <li key={row.skill} className="skill-gap-item skill-gap-item--strong">
                <div>
                  <strong>{row.skill}</strong>
                  <span className="skill-gap-item__meta">
                    matched in {row.matchedRoleCount} role{row.matchedRoleCount === 1 ? "" : "s"}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {weakSkills.length > 0 && (
        <div className="skill-gap-group">
          <h3 className="skill-gap-group__title">Emerging skills</h3>
          <ul className="skill-gap-list">
            {weakSkills.map((row) => (
              <li key={row.skill} className="skill-gap-item">
                <div>
                  <strong>{row.skill}</strong>
                  <span className="skill-gap-item__meta">in {row.roleCount} roles</span>
                </div>
                {row.learnUrl && (
                  <a className="skill-gap-item__link" href={row.learnUrl} target="_blank" rel="noreferrer">
                    Learn
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Surface>
  );
}

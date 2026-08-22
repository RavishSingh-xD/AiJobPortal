export default function PageHeader({ label, title, subtitle, className = "" }) {
  return (
    <header className={`app-page-header ${className}`.trim()}>
      {label && <p className="micro-label">{label}</p>}
      <h1 className="display-title app-page-header__title">{title}</h1>
      {subtitle && <p className="app-page-header__subtitle">{subtitle}</p>}
    </header>
  );
}

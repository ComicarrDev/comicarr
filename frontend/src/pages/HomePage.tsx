import './HomePage.css';

export default function HomePage() {
  return (
    <div className="home-page">
      <div className="home-header">
        <h1>Dashboard</h1>
        <p className="home-subtitle">Overview of your comic library</p>
      </div>

      <div className="home-stats">
        <div className="home-stat-card">
          <div className="home-stat-icon">📚</div>
          <div className="home-stat-content">
            <div className="home-stat-value">0</div>
            <div className="home-stat-label">Total Volumes</div>
          </div>
        </div>

        <div className="home-stat-card">
          <div className="home-stat-icon">📖</div>
          <div className="home-stat-content">
            <div className="home-stat-value">0</div>
            <div className="home-stat-label">Total Issues</div>
          </div>
        </div>

        <div className="home-stat-card">
          <div className="home-stat-icon">⏳</div>
          <div className="home-stat-content">
            <div className="home-stat-value">0</div>
            <div className="home-stat-label">In Queue</div>
          </div>
        </div>

        <div className="home-stat-card">
          <div className="home-stat-icon">⚠️</div>
          <div className="home-stat-content">
            <div className="home-stat-value">0</div>
            <div className="home-stat-label">Volumes with Gaps</div>
          </div>
        </div>
      </div>

      <div className="home-sections">
        <section className="home-section">
          <h2>Latest Volumes Added</h2>
          <div className="home-section-content">
            <p className="home-empty">No volumes added yet. Start by adding your first volume!</p>
          </div>
        </section>

        <section className="home-section">
          <h2>Volumes with Missing Issues</h2>
          <div className="home-section-content">
            <p className="home-empty">All volumes are complete!</p>
          </div>
        </section>
      </div>
    </div>
  );
}
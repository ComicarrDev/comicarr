import './ProgressIndicator.css';

export interface ProgressIndicatorProps {
  current: number;
  total: number;
  label: string;
  showPercentage?: boolean;
  variant?: 'default' | 'success' | 'warning' | 'error';
}

export function ProgressIndicator({
  current,
  total,
  label,
  showPercentage = false,
  variant = 'default',
}: ProgressIndicatorProps) {
  const percentage = total > 0 ? Math.round((current / total) * 100) : 0;

  return (
    <div className={`progress-indicator progress-indicator--${variant}`}>
      <div className="progress-indicator__header">
        <span className="progress-indicator__label">{label}</span>
        {showPercentage && (
          <span className="progress-indicator__percentage">{percentage}%</span>
        )}
      </div>
      <div className="progress-indicator__bar">
        <div
          className="progress-indicator__fill"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <div className="progress-indicator__text">
        {current} / {total}
      </div>
    </div>
  );
}




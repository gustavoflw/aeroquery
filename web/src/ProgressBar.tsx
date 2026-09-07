function formatEta(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  const secs = total % 60
  return minutes ? `${minutes}m ${String(secs).padStart(2, '0')}s` : `${secs}s`
}

interface ProgressBarProps {
  completed: number
  total: number
  etaSeconds: number | null
}

export function ProgressBar({ completed, total, etaSeconds }: ProgressBarProps) {
  const fraction = total ? completed / total : 0
  const etaText = etaSeconds !== null ? ` · ~${formatEta(etaSeconds)} left` : ''

  return (
    <div className="progress-bar">
      <div className="progress-bar-track">
        <div className="progress-bar-fill" style={{ width: `${fraction * 100}%` }} />
      </div>
      <p className="progress-bar-label">
        Searched {completed} of {total} days
        {etaText}
      </p>
    </div>
  )
}

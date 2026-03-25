export function InfoIcon({ text }) {
  return (
    <span className="info-icon" tabIndex={0} aria-label={text} role="img">
      i
      <span className="info-tooltip" role="tooltip">
        {text}
      </span>
    </span>
  )
}


/**
 * Derives a short, human-readable line from the backend's deterministic
 * template explanation (risk_engine/explain.py), for glanceable views
 * (Overview, condensed Alert Feed). The full technical sentence — with
 * exact z-score multiplier and baseline mean±std — is reserved for the
 * drill-down (seat detail / evidence), not the always-visible line.
 *
 * Gesture-alert explanations (behaviour/gestures.py) are already short and
 * human-readable ("Hand crossed into seat_1's desk space for 9.3s") and
 * pass through unchanged — they don't carry raw z-score internals.
 */
export function shortAlertSummary(explanation: string): string {
  // Risk-engine alerts: "Torso orientation deviated 14.9x from seat_1's
  // baseline for 60.8s (baseline -0.45±0.09). No object detected."
  const signalMatch = explanation.match(/^(Torso orientation|Movement level)/)
  const durationMatch = explanation.match(/for ([\d.]+)s/)
  // risk_engine/explain.py always ends with either "No object detected." or
  // "{label} detected." — the positive case does NOT contain the substring
  // "object", so detecting it via "not the negative phrase" is correct;
  // matching for the word "object" would silently miss every true positive.
  const objectDetected = !explanation.includes('No object detected')

  if (signalMatch && durationMatch) {
    const label = signalMatch[1] === 'Torso orientation' ? 'Unusual posture' : 'Unusual movement'
    const duration = durationMatch[1]
    return `${label} sustained for ${duration}s${objectDetected ? ' · object detected' : ''}`
  }

  // Gesture alerts and anything else already short — pass through.
  return explanation
}

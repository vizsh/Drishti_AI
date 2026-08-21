/**
 * Minimal audio alert system for walking invigilators who can't constantly
 * watch the screen. Uses Web Audio API to synthesize alert tones — no
 * external audio files needed.
 *
 * Frontend analysis (2026-08-21): "Optional, distinct audio pings for
 * 'elevated' vs 'critical' events so walking invigilators are alerted
 * without constantly looking at the screen."
 */

let audioCtx: AudioContext | null = null
let _muted = false

function getCtx(): AudioContext {
  if (!audioCtx) audioCtx = new AudioContext()
  return audioCtx
}

/** Play a short tone. freq in Hz, duration in seconds. */
function playTone(freq: number, duration: number, volume = 0.15) {
  if (_muted) return
  try {
    const ctx = getCtx()
    if (ctx.state === 'suspended') ctx.resume()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.frequency.value = freq
    osc.type = 'sine'
    gain.gain.setValueAtTime(volume, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + duration)
  } catch {
    // Audio not available — fail silently
  }
}

/** Two-tone alert for critical / verification-required alerts. */
export function playCriticalAlert() {
  playTone(880, 0.15, 0.12)
  setTimeout(() => playTone(1100, 0.2, 0.12), 180)
}

/** Single soft ping for elevated / watch-level events. */
export function playWatchAlert() {
  playTone(660, 0.12, 0.08)
}

/** Mute/unmute all audio alerts. */
export function setAudioMuted(muted: boolean) {
  _muted = muted
}

export function isAudioMuted(): boolean {
  return _muted
}

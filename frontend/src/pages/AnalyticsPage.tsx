import { SessionAnalytics } from '../components/SessionAnalytics'
import { SystemLearningIndicator } from '../components/SystemLearningIndicator'
import { TrainingSignalPanel } from '../components/TrainingSignalPanel'
import { ExportReportButton } from '../components/ExportReportButton'
import { RiskTrendChart } from '../components/RiskTrendChart'
import { useLive } from '../state/LiveContext'

export function AnalyticsPage() {
  const { riskHistory } = useLive()
  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="flex-1">
          <SystemLearningIndicator />
        </div>
        <ExportReportButton />
      </div>
      <TrainingSignalPanel />
      <h2 className="text-sm font-bold uppercase tracking-wide mb-3">
        Risk trend — all seats <span className="text-white/30 font-normal normal-case">— last 60s</span>
      </h2>
      <div className="rounded-2xl border border-white/8 p-4 mb-8">
        <RiskTrendChart riskHistory={riskHistory} />
      </div>
      <SessionAnalytics />
    </div>
  )
}

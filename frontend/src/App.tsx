import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { LiveProvider } from './state/LiveContext'
import { AppLayout } from './layouts/AppLayout'
import { OverviewPage } from './pages/OverviewPage'
import { LivePage } from './pages/LivePage'
import { SeatDetailPage } from './pages/SeatDetailPage'
import { AlertsPage } from './pages/AlertsPage'
import { AnalyticsPage } from './pages/AnalyticsPage'

export default function App() {
  return (
    <BrowserRouter>
      <LiveProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<OverviewPage />} />
            <Route path="/live" element={<LivePage />} />
            <Route path="/seat/:seatId" element={<SeatDetailPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Route>
        </Routes>
      </LiveProvider>
    </BrowserRouter>
  )
}

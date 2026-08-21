import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { AuthProvider } from './state/AuthContext'
import { LiveProvider } from './state/LiveContext'
import { RequireAuth } from './components/RequireAuth'
import { AppLayout } from './layouts/AppLayout'
import { LoginPage } from './pages/LoginPage'
import { OverviewPage } from './pages/OverviewPage'
import { CommandCenterPage } from './pages/CommandCenterPage'
import { SeatDetailPage } from './pages/SeatDetailPage'
import { DigitalTwinPage } from './pages/DigitalTwinPage'
import { AlertsPage } from './pages/AlertsPage'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { EvidenceVaultPage } from './pages/EvidenceVaultPage'
import { SettingsPage } from './pages/SettingsPage'
import { TrustCompliancePage } from './pages/TrustCompliancePage'
import { DemoModePage } from './pages/DemoModePage'
import { LabSetupPage } from './pages/LabSetupPage'

function DemoModeRoute() {
  const navigate = useNavigate()
  return <DemoModePage onExit={() => navigate('/settings')} />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <LiveProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/demo"
              element={
                <RequireAuth>
                  <DemoModeRoute />
                </RequireAuth>
              }
            />
            <Route
              element={
                <RequireAuth>
                  <AppLayout />
                </RequireAuth>
              }
            >
              <Route index element={<Navigate to="/command-center" replace />} />
              <Route path="/command-center" element={<CommandCenterPage />} />
              <Route path="/live" element={<Navigate to="/command-center" replace />} />
              <Route path="/overview" element={<OverviewPage />} />
              <Route path="/seat/:seatId" element={<SeatDetailPage />} />
              <Route path="/twin/:seatId" element={<DigitalTwinPage />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/evidence-vault" element={<EvidenceVaultPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/trust" element={<TrustCompliancePage />} />
              <Route path="/lab-setup" element={<LabSetupPage />} />
              <Route path="*" element={<Navigate to="/command-center" replace />} />
            </Route>
          </Routes>
        </LiveProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}

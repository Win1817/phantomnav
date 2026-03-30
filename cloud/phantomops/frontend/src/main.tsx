import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './index.css';
import { AppShell } from './components/AppShell';
import { LoginPage } from './pages/LoginPage';
import { FleetPage } from './pages/FleetPage';
import { DronePage } from './pages/DronePage';
import { MissionsPage } from './pages/MissionsPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { AlertsPage } from './pages/AlertsPage';
import { useStore } from './store';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={
            <AuthGuard>
              <AppShell>
                <Routes>
                  <Route path="/"           element={<FleetPage />} />
                  <Route path="/drone/:id"  element={<DronePage />} />
                  <Route path="/missions"   element={<MissionsPage />} />
                  <Route path="/analytics"  element={<AnalyticsPage />} />
                  <Route path="/alerts"     element={<AlertsPage />} />
                  <Route path="*"           element={<Navigate to="/" />} />
                </Routes>
              </AppShell>
            </AuthGuard>
          }
        />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);

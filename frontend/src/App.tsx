import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { RequireAuth, RequireRole } from './components/Guards';
import MainLayout from './layouts/MainLayout';
import AlertRules from './pages/AlertRules';
import Alerts from './pages/Alerts';
import AuditLogs from './pages/AuditLogs';
import ChangePassword from './pages/ChangePassword';
import Channels from './pages/Channels';
import Collector from './pages/Collector';
import Dashboard from './pages/Dashboard';
import ErrorCodes from './pages/ErrorCodes';
import ErrorLogs from './pages/ErrorLogs';
import Hosts from './pages/Hosts';
import Keywords from './pages/Keywords';
import LoginPage from './pages/Login';
import Agents from './pages/Agents';
import LogSources from './pages/LogSources';
import Mentions from './pages/Mentions';
import NotifyFailRecords from './pages/NotifyFailRecords';
import NotifyRecords from './pages/NotifyRecords';
import Projects from './pages/Projects';
import Roles from './pages/Roles';
import Settings from './pages/Settings';
import Templates from './pages/Templates';
import Users from './pages/Users';

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <MainLayout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="error-logs" element={<ErrorLogs />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="collector" element={<Collector />} />
          <Route path="projects" element={<Projects />} />
          <Route path="hosts" element={<Hosts />} />
          <Route path="log-sources" element={<LogSources />} />
          <Route path="agents" element={<Agents />} />
          <Route path="alert-rules" element={<AlertRules />} />
          <Route path="keywords" element={<Keywords />} />
          <Route path="error-codes" element={<ErrorCodes />} />
          <Route path="mentions" element={<Mentions />} />
          <Route path="channels" element={<Channels />} />
          <Route path="templates" element={<Templates />} />
          <Route path="notify-records" element={<NotifyRecords />} />
          <Route path="notify-fail-records" element={<NotifyFailRecords />} />
          <Route path="audit-logs" element={<AuditLogs />} />
          <Route
            path="users"
            element={
              <RequireRole roles={['ADMIN']}>
                <Users />
              </RequireRole>
            }
          />
          <Route
            path="roles"
            element={
              <RequireRole roles={['ADMIN']}>
                <Roles />
              </RequireRole>
            }
          />
          <Route
            path="settings"
            element={
              <RequireRole roles={['ADMIN']}>
                <Settings />
              </RequireRole>
            }
          />
          <Route path="change-password" element={<ChangePassword />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;

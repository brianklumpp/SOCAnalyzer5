import React, { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
import { CircularProgress, Box } from "@mui/material";
import ProtectedRoute from "./components/auth/ProtectedRoute";

// Code-split major pages for better initial load performance
const AnalyzerPage = lazy(() => import("./pages/AnalyzerPage"));
const ReportPage = lazy(() => import("./pages/ReportPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const ValidationPage = lazy(() => import("./pages/ValidationPage").then(module => ({ default: module.ValidationPage })));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const UserManagementPage = lazy(() => import("./pages/admin/UserManagementPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const JobQueuePage = lazy(() => import("./pages/JobQueuePage"));

// Redirect component that preserves :scanId param
const ReportRedirect: React.FC = () => {
  const { scanId } = useParams();
  return <Navigate to={`/app/report/${scanId}`} replace />;
};

// Loading fallback component
const LoadingFallback = () => (
  <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
    <CircularProgress size={60} />
  </Box>
);

const Router: React.FC = () => (
  <BrowserRouter>
    <Suspense fallback={<LoadingFallback />}>
      <Routes>
        {/* Public route */}
        <Route path="/login" element={<LoginPage />} />
        
        {/* Protected routes */}
        <Route path="/" element={<ProtectedRoute><AnalyzerPage /></ProtectedRoute>} />
        <Route path="/app/analyzer" element={<ProtectedRoute><AnalyzerPage /></ProtectedRoute>} />
        <Route path="/app/queue" element={<ProtectedRoute><JobQueuePage /></ProtectedRoute>} />
        <Route path="/queue" element={<ProtectedRoute><JobQueuePage /></ProtectedRoute>} />
        <Route path="/app/report/:scanId" element={<ProtectedRoute><ReportPage /></ProtectedRoute>} />
        <Route path="/report/:scanId" element={<ReportRedirect />} />
        <Route path="/app-settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
        <Route path="/settings" element={<Navigate to="/app-settings" replace />} />
        <Route path="/validation" element={<ProtectedRoute><ValidationPage /></ProtectedRoute>} />
        <Route path="/app/validation" element={<ProtectedRoute><ValidationPage /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
        
        {/* Admin-only routes */}
        <Route path="/admin/users" element={<ProtectedRoute requireAdmin><UserManagementPage /></ProtectedRoute>} />
      </Routes>
    </Suspense>
  </BrowserRouter>
);

export default Router;

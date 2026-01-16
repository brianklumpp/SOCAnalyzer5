import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Paper,
  Typography,
  CircularProgress,
  LinearProgress,
  Chip,
  AppBar,
  Toolbar,
  IconButton,
  ThemeProvider,
  CssBaseline,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Alert,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import VisibilityIcon from "@mui/icons-material/Visibility";
import ErrorIcon from "@mui/icons-material/Error";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import UserMenu from "../components/auth/UserMenu";
import { lightTheme, darkTheme } from "../theme/solidigmTheme";
import api from "../api/client";

interface JobCounters {
  subservice_orgs_count: number;
  controls_count: number;
  controls_total_estimate: number;
  controls_percent: number;
  controls_mapped_count: number;
  controls_mapped_percent: number;
  cuecs_count: number;
}

interface QueueJob {
  job_id: string;
  filename: string;
  priority: number;
  status: string;
  queued_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  position: number;
  counters: JobCounters;
  detectedSubtype?: string;
  identifiedEntities?: {
    report_type?: string;
    company?: string;
    auditor?: string;
  };
}

interface QueueResponse {
  scans: QueueJob[];
  is_paused: boolean;
  queue_length: number;
  current_job_id: string | null;
}

const JobQueuePage: React.FC = () => {
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [darkMode] = useState(() => localStorage.getItem("socanalyzer_dark_mode") === "true");
  const theme = darkMode ? darkTheme : lightTheme;
  const navigate = useNavigate();

  const fetchQueue = async () => {
    try {
      setError(null);
      const response = await api.get("/scan_queue/");
      setQueue(response.data as QueueResponse);
    } catch (err: any) {
      console.error("Failed to fetch queue:", err);
      setError(err.response?.data?.detail || "Failed to load job queue");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueue();
    // Auto-refresh every 5 seconds
    const interval = setInterval(fetchQueue, 5000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string): "default" | "primary" | "success" | "error" | "warning" => {
    if (status === "failed") return "error";
    if (status === "completed") return "success";
    if (status === "running") return "primary";
    return "default";
  };

  const getStatusIcon = (status: string) => {
    if (status === "failed") return <ErrorIcon fontSize="small" />;
    if (status === "completed") return <CheckCircleIcon fontSize="small" />;
    if (status === "running") return <PlayArrowIcon fontSize="small" />;
    return <HourglassEmptyIcon fontSize="small" />;
  };

  const handleViewJob = (jobId: string) => {
    // Store in localStorage so AnalyzerPage can pick it up
    localStorage.setItem("socanalyzer_job_id", jobId);
    navigate("/");
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  };

  if (loading) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
          <CircularProgress size={60} />
        </Box>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              Job Queue
            </Typography>
            <Tooltip title="Refresh">
              <IconButton color="inherit" onClick={fetchQueue}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
            <UserMenu />
          </Toolbar>
        </AppBar>

        <Box sx={{ p: 3 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          {queue && (
            <Paper sx={{ p: 2, mb: 2 }}>
              <Typography variant="h6" gutterBottom>
                Queue Status
              </Typography>
              <Box sx={{ display: "flex", gap: 2 }}>
                <Chip
                  label={`Total Jobs: ${queue.queue_length}`}
                  color="primary"
                  variant="outlined"
                />
                <Chip
                  label={queue.is_paused ? "Queue Paused" : "Queue Active"}
                  color={queue.is_paused ? "warning" : "success"}
                />
                {queue.current_job_id && (
                  <Chip
                    label={`Current: ${queue.current_job_id.substring(0, 8)}...`}
                    color="info"
                  />
                )}
              </Box>
            </Paper>
          )}

          {queue && queue.scans.length === 0 ? (
            <Paper sx={{ p: 3, textAlign: "center" }}>
              <Typography variant="body1" color="text.secondary">
                No jobs in queue
              </Typography>
            </Paper>
          ) : (
            <TableContainer component={Paper}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Position</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Filename</TableCell>
                    <TableCell>Report Type</TableCell>
                    <TableCell>Progress</TableCell>
                    <TableCell>Controls</TableCell>
                    <TableCell>Queued At</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {queue?.scans.map((job) => (
                    <TableRow key={job.job_id} hover>
                      <TableCell>{job.position}</TableCell>
                      <TableCell>
                        <Chip
                          icon={getStatusIcon(job.status)}
                          label={job.status}
                          color={getStatusColor(job.status)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <Tooltip title={job.filename}>
                          <Typography variant="body2" noWrap sx={{ maxWidth: 200 }}>
                            {job.filename}
                          </Typography>
                        </Tooltip>
                        {job.error && (
                          <Tooltip title={job.error}>
                            <Typography
                              variant="caption"
                              color="error"
                              sx={{
                                display: "block",
                                maxWidth: 200,
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                              }}
                            >
                              {job.error}
                            </Typography>
                          </Tooltip>
                        )}
                      </TableCell>
                      <TableCell>
                        <Box sx={{ display: "flex", gap: 0.5 }}>
                          {job.identifiedEntities?.report_type && (
                            <Chip
                              label={job.identifiedEntities.report_type}
                              size="small"
                              variant="outlined"
                            />
                          )}
                          {job.detectedSubtype && (
                            <Chip
                              label={job.detectedSubtype}
                              size="small"
                              variant="outlined"
                            />
                          )}
                        </Box>
                      </TableCell>
                      <TableCell sx={{ minWidth: 150 }}>
                        {job.status === "running" && (
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                            <LinearProgress
                              variant="determinate"
                              value={job.counters.controls_percent || 0}
                              sx={{ flexGrow: 1 }}
                            />
                            <Typography variant="caption">
                              {job.counters.controls_percent || 0}%
                            </Typography>
                          </Box>
                        )}
                      </TableCell>
                      <TableCell>
                        {job.counters.controls_count > 0 && (
                          <Typography variant="body2">
                            {job.counters.controls_count}
                            {job.counters.controls_total_estimate > 0 &&
                              ` / ${job.counters.controls_total_estimate}`}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption">{formatDate(job.queued_at)}</Typography>
                      </TableCell>
                      <TableCell>
                        <Tooltip title="View Details">
                          <IconButton
                            size="small"
                            onClick={() => handleViewJob(job.job_id)}
                            color="primary"
                          >
                            <VisibilityIcon />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      </Box>
    </ThemeProvider>
  );
};

export default JobQueuePage;

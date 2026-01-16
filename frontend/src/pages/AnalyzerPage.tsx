import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import CountUp from 'react-countup';
import api from "../api/client";
import { APP_CONFIG } from "../config";
import { Box, Button, CircularProgress, Typography, Paper, Accordion, AccordionSummary, AccordionDetails, LinearProgress, Snackbar, Alert, ThemeProvider, CssBaseline, Select, MenuItem, FormControl, InputLabel, Dialog, DialogTitle, DialogContent, DialogActions, List, ListItem, ListItemText, Chip, TextField, AppBar, Toolbar, Tooltip, IconButton } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import AssessmentIcon from "@mui/icons-material/Assessment";
import BusinessIcon from "@mui/icons-material/Business";
import CalendarTodayIcon from "@mui/icons-material/CalendarToday";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DescriptionIcon from "@mui/icons-material/Description";
import { VirtualHistoryGrid } from '../components';
import { ActiveScanCard, QueueControls, HistorySection } from '../components/analyzer';
import { lightTheme, darkTheme, solidigmColors } from '../theme/solidigmTheme';
import HelpDialog from '../components/HelpDialog';
import UserMenu from '../components/auth/UserMenu';
import { AxiosResponse } from 'axios';
import { ScanData } from '../components/HistoryCard';

// Define ScanResult type to align with expected structure
interface ScanResult extends ScanData {
  timestamp: string;
  results: any[]; // Replace 'any' with the actual type if known
};

type Settings = {
  [key: string]: any;
};

// Real-time progress interfaces
interface IdentifiedEntities {
  company?: string;
  auditor?: string;
  product?: string;
  report_date?: string;
  period_start?: string;
  period_end?: string;
  report_type?: string;
}

interface Counters {
  controls_count: number;
  controls_total_estimate: number;
  controls_percent: number;
  controls_mapped_count: number;
  controls_mapped_percent: number;
  subservice_orgs_count: number;
  cuecs_count: number;
}

interface PhaseCompletion {
  logo_fetched: boolean;
  cleanup_complete: boolean;
  db_uploaded: boolean;
}

const API_URL = "/analyze/";
const HISTORY_URL = "/history";
const SETTINGS_URL = "/settings";
const WS_URL = APP_CONFIG.wsUrl('/ws');

const AnalyzerPage: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [detectionResult, setDetectionResult] = useState<any>(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmedType, setConfirmedType] = useState<string>('');
  const [confirmedSubtype, setConfirmedSubtype] = useState<string>('');
  const [progress, setProgress] = useState<number | null>(null);
  const [results, setResults] = useState<any>(null);
  // Store compact result summary separately to avoid loading full result
  const [resultSummary, setResultSummary] = useState<any>(null);
  const [extractorChecklist, setExtractorChecklist] = useState<{name: string, status: string}[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ScanResult[]>([]);
  // Settings fetched but not used directly here; retained for potential future inline display.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [settings, setSettings] = useState<Settings>({});
  const navigate = useNavigate();
  const socketRef = useRef<any>(null);
  const [openCancelSnackbar, setOpenCancelSnackbar] = useState(false);
  const MAX_FILE_SIZE_MB = 25; // Set a reasonable max size
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [scanStartTime, setScanStartTime] = useState<number | null>(null);
  const [darkMode] = useState(() => localStorage.getItem('socanalyzer_dark_mode') === 'true');
  const theme = darkMode ? darkTheme : lightTheme;
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [reportTypeFilter, setReportTypeFilter] = useState<string>('All');
  const [helpDialogOpen, setHelpDialogOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  // Lightweight status info from /analyze/status to avoid large payloads
  const [statusInfo, setStatusInfo] = useState<{ finalized?: boolean; artifacts?: any; counts?: any; report_type?: string; detected_report_type?: string; detected_subtype?: string; detection_confidence?: number; done?: boolean } | null>(null);
  // Partial controls progressive state
  const [partialControls, setPartialControls] = useState<any[] | null>(null);
  const [partialCompletionPct, setPartialCompletionPct] = useState<number | null>(null);
  
  // Separate state for volatile progress data to avoid re-rendering history
  const [scanProgress, setScanProgress] = useState<Record<string, any>>({});
  // Completed scans notification
  const [completedWhileAway, setCompletedWhileAway] = useState<ScanResult[]>([]);
  const [showCompletedBanner, setShowCompletedBanner] = useState(false);
  const lastPartialFetchRef = useRef<number>(0);
  const PARTIAL_MIN_PCT = 20; // threshold percentage for showing partial controls
  
  // Real-time progress state
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [identifiedEntities, setIdentifiedEntities] = useState<IdentifiedEntities>({});
  const [counters, setCounters] = useState<Counters>({
    controls_count: 0,
    controls_total_estimate: 0,
    controls_percent: 0,
    controls_mapped_count: 0,
    controls_mapped_percent: 0,
    subservice_orgs_count: 0,
    cuecs_count: 0
  });
  const [phaseCompletion, setPhaseCompletion] = useState<PhaseCompletion>({
    logo_fetched: false,
    cleanup_complete: false,
    db_uploaded: false
  });
  const [extractionPartial, setExtractionPartial] = useState<boolean>(false);
  
  // Queue management state
  const [queuedScans, setQueuedScans] = useState<any[]>([]);
  const [queuePaused, setQueuePaused] = useState<boolean>(false);
  const [queueStats, setQueueStats] = useState<any>(null);

  // Polling interval in ms
  const POLL_INTERVAL = 3000;
  const [jobId, setJobId] = useState<string | null>(() => {
    // Try to restore jobId from localStorage on mount
    const stored = localStorage.getItem('socanalyzer_job_id') || null;
    console.log('[AnalyzerPage] Initial jobId from localStorage:', stored);
    return stored;
  });
  const pollTimeoutRef = useRef<any>(null);

  // Fetch scan history and settings on mount
  useEffect(() => {
    setHistoryLoading(true);
    api.get(HISTORY_URL)
      .then((res: { data: ScanResult[] }) => {
        const historyData = res.data.map((scan) => ({
          ...scan,
          product: scan.product || 'Unknown Product',
          timestamp: scan.timestamp || '',
          results: scan.results || [],
        }));
        setHistory(historyData);
        setHistoryLoading(false);
      })
      .catch((err: any) => {
        console.error('Failed to fetch scan history:', err);
        setHistoryLoading(false);
      });
    api.get(SETTINGS_URL)
      .then((res: { data: any }) => setSettings(res.data))
      .catch((err: unknown) => console.error('Failed to fetch settings:', err));
  }, []);

  // F1 keyboard shortcut for help
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'F1') {
        e.preventDefault();
        setHelpDialogOpen(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Persist checklist to localStorage on every update
  useEffect(() => {
    if (extractorChecklist && extractorChecklist.length > 0) {
      localStorage.setItem('socanalyzer_checklist', JSON.stringify(extractorChecklist));
    }
  }, [extractorChecklist]);

  // On mount, restore checklist from localStorage if present and state is empty
  useEffect(() => {
    const savedChecklist = localStorage.getItem('socanalyzer_checklist');
    if (savedChecklist && (!extractorChecklist || extractorChecklist.length === 0)) {
      setExtractorChecklist(JSON.parse(savedChecklist));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Elapsed time ticker - updates every second when scan is running
  useEffect(() => {
    if (!loading || !elapsedSeconds) return;
    const interval = setInterval(() => {
      setElapsedSeconds(prev => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [loading, elapsedSeconds]);

  // Poll job status
  useEffect(() => {
    console.log('[AnalyzerPage] Polling useEffect running. jobId:', jobId, 'loading:', loading);
    if (!jobId) {
      console.log("[AnalyzerPage] No jobId, polling not started.");
      return;
    }
    
    let pollActive = true;
    
    const poll = async () => {
      if (!pollActive) return;
      
      console.log(`[AnalyzerPage] Polling job status for jobId: ${jobId}`);
      try {
        // First hit ultra-light endpoint (now includes counts & checklist)
        const statusMinRes = await api.get(`${API_URL}status_min/${jobId}`, { timeout: 8000 });
        const statusMin = statusMinRes.data;
        console.log("[AnalyzerPage] status_min response:", statusMin);
        // Prefer line-based percent if it's further along than generic percent
        let effectivePct: number | null = (typeof statusMin.progress === 'number') ? statusMin.progress : null;
        const lp = statusMin?.line_progress?.controls;
        if (lp && typeof lp.percent_complete === 'number') {
          const lpInt = Math.max(0, Math.min(100, Math.round(lp.percent_complete)));
          if (effectivePct === null || lpInt > effectivePct) {
            effectivePct = lpInt;
          }
        }
        if (effectivePct !== null) setProgress(effectivePct);
        
        // Note: elapsed/estimated time display removed - jobId during analysis is UUID (not scan_id)
        // The /scan/{scan_id}/progress endpoint requires integer scan_id which only exists after DB insertion
        
        // Check if awaiting user confirmation for report type
        if (statusMin.awaiting_confirmation && statusMin.detection_result) {
          console.log('[AnalyzerPage] Report type detection awaiting confirmation');
          setDetectionResult(statusMin.detection_result);
          setConfirmedType(statusMin.detection_result.detected_type || '');
          setConfirmedSubtype(statusMin.detection_result.detected_subtype || '');
          setShowConfirmDialog(true);
          setLoading(false);
          return; // Stop polling until user confirms
        }
        
        // Update mid-run counts & checklist immediately
        if (Array.isArray(statusMin.checklist)) setExtractorChecklist(statusMin.checklist);
        if (statusMin.counts) {
          console.log('[AnalyzerPage] Setting statusInfo with detected_report_type:', statusMin.detected_report_type, 'report_type:', statusMin.report_type, 'detected_subtype:', statusMin.detected_subtype);
          setStatusInfo({ finalized: !!statusMin.finalized, artifacts: statusMin.artifacts, counts: statusMin.counts, report_type: statusMin.report_type, detected_report_type: statusMin.detected_report_type, detected_subtype: statusMin.detected_subtype, detection_confidence: statusMin.detection_confidence });
        }
        
        // Update real-time progress fields
        if (typeof statusMin.elapsed_seconds === 'number') {
          setElapsedSeconds(statusMin.elapsed_seconds);
        }
        if (statusMin.identified_entities) {
          setIdentifiedEntities(statusMin.identified_entities);
        }
        if (statusMin.counters) {
          setCounters(statusMin.counters);
        }
        if (statusMin.phase_completion) {
          setPhaseCompletion(statusMin.phase_completion);
        }
        if (typeof statusMin.extraction_partial === 'boolean') {
          setExtractionPartial(statusMin.extraction_partial);
        }
        if (statusMin.error) {
          if (statusMin.error === 'Job not found' && statusMin.transient_unavailable) {
            console.log('[AnalyzerPage] Transient job unavailable; retrying shortly without user-facing error');
            pollTimeoutRef.current = setTimeout(poll, 1500);
            return;
          }
          setError(statusMin.error);
          setLoading(false);
          setJobId(null);
          localStorage.removeItem('socanalyzer_checklist');
          console.log('[AnalyzerPage] Error in status_min (non-transient):', statusMin.error);
          return;
        }
        // If done, optionally pull full status for richer artifacts (counts already set)
        if (statusMin.done) {
          try {
            const statusRes = await api.get(`${API_URL}status/${jobId}?final=true`, { timeout: 8000 });
            const statusFull = statusRes.data;
            if (Array.isArray(statusFull.checklist)) setExtractorChecklist(statusFull.checklist);
            setStatusInfo({ finalized: !!statusFull.finalized, artifacts: statusFull.artifacts, counts: statusFull.counts || statusMin.counts, report_type: statusFull.report_type || statusMin.report_type, detected_report_type: statusFull.detected_report_type || statusMin.detected_report_type, detected_subtype: statusFull.detected_subtype || statusMin.detected_subtype, detection_confidence: statusFull.detection_confidence || statusMin.detection_confidence });
          } catch (e) {
            console.log('[AnalyzerPage] Full status fetch failed post-completion, continuing with min data');
          }
        }
        if (statusMin.error) {
          // Silent transient retry path: do NOT surface error or clear job when Redis hiccup flagged
          if (statusMin.error === 'Job not found' && statusMin.transient_unavailable) {
            console.log('[AnalyzerPage] Transient job unavailable; retrying shortly without user-facing error');
            pollTimeoutRef.current = setTimeout(poll, 1500); // short backoff
            return;
          }
          setError(statusMin.error);
          setLoading(false);
          setJobId(null);
          localStorage.removeItem('socanalyzer_checklist');
          console.log('[AnalyzerPage] Error in status (non-transient):', statusMin.error);
          return;
        }
        // Opportunistic fetch of partial controls mid-run (throttle every 9s)
        const nowTs = Date.now();
        if (!statusMin.done && nowTs - lastPartialFetchRef.current > 9000) {
          // Only attempt if we have at least some controls extracted (avoid empty early calls)
            try {
              lastPartialFetchRef.current = nowTs;
              const pcRes = await api.get(`/analyze/controls_partial/${jobId}?min_pct=${PARTIAL_MIN_PCT}&limit=25`, { timeout: 5000 });
              if (pcRes.data && !pcRes.data.error && pcRes.data.threshold_met) {
                setPartialControls(pcRes.data.controls || []);
                setPartialCompletionPct(pcRes.data.completion_pct || 0);
              }
            } catch (e) {
              // Silent fail; progressive panel is best-effort
            }
        }
        if (statusMin.done) {
          // Fetch only compact summary for optional display; do not load full results here
          try {
            const resultRes = await api.get(`${API_URL}result/${jobId}?format=summary`, { timeout: 8000 });
            if (resultRes.data?.error) {
              setError(resultRes.data.error);
              setResultSummary(null);
              console.log("[AnalyzerPage] Error in result summary:", resultRes.data.error);
            } else {
              setResultSummary(resultRes.data);
              console.log("[AnalyzerPage] Summary received:", resultRes.data);
            }
          } catch (e: any) {
            console.log('[AnalyzerPage] Failed to fetch result summary', e?.message || e);
          }
          // Do not setResults here to avoid rendering large payloads; rely on summary/status
          setResults(null);
          setLoading(false);
          setJobId(null);
          // Refresh history after scan
          api.get(HISTORY_URL).then((res: { data: ScanResult[] }) => {
            const historyData = res.data.map((scan) => ({
              ...scan,
              product: scan.product || 'Unknown Product',
              timestamp: scan.timestamp || '',
              results: scan.results || [],
            }));
            setHistory(historyData);
          })
          .catch((err: any) => console.error('Failed to refresh history:', err));
          // Clear checklist from localStorage on completion
          localStorage.removeItem('socanalyzer_checklist');
          return;
        }
        // Not done, keep polling
        if (pollActive) {
          pollTimeoutRef.current = setTimeout(poll, POLL_INTERVAL);
        }
      } catch (err: any) {
        // Treat Axios timeout specially as transient to avoid clearing job prematurely
        if (err?.code === 'ECONNABORTED') {
          console.warn('[AnalyzerPage] status_min timeout, treating as transient and retrying');
          if (pollActive) {
            pollTimeoutRef.current = setTimeout(poll, 2000);
          }
          return;
        }
        setError(err.message || 'Polling error');
        setLoading(false);
        setJobId(null);
        console.error("[AnalyzerPage] Polling error:", err);
      }
    };
    poll();
    return () => {
      pollActive = false;
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, [jobId, loading]); // Added loading to dependency array to restart polling if needed

  // WebSocket for real-time progress (FastAPI native)
  useEffect(() => {
    console.log('Attempting WebSocket connection to', WS_URL);
    const ws = new WebSocket(WS_URL);
    socketRef.current = ws;
    ws.onopen = () => {
      // Optionally send a message to identify the client/session
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "progress" && typeof data.percent === "number") {
          setProgress(data.percent);
        } else if (data.type === "done") {
          setProgress(null);
          // Do not clear checklist here; keep it until a new file is uploaded
        } else if (data.type === "extractor_status" && Array.isArray(data.extractors)) {
          setExtractorChecklist(data.extractors);
        } else if (data.type === "queue_update") {
          // Refresh history when queue updates (only if data changed)
          console.log('[AnalyzerPage] Queue update detected, refreshing history');
          api.get(HISTORY_URL)
            .then((res: { data: ScanResult[] }) => {
              const historyData = res.data.map((scan) => ({
                ...scan,
                product: scan.product || 'Unknown Product',
                timestamp: scan.timestamp || '',
                results: scan.results || [],
              }));
              setHistory(historyData);
            })
            .catch((err: any) => console.error('Failed to refresh history:', err));
        }
      } catch (e) {
        // Ignore malformed messages
      }
    };
    ws.onerror = () => {
      // Optionally handle errors
    };
    ws.onclose = () => {
      // Optionally handle close
    };
    return () => {
      ws.close();
    };
  }, []);

  // When scan starts, record start time
  useEffect(() => {
    if (loading && !scanStartTime) {
      setScanStartTime(Date.now());
    }
    if (!loading) {
      setScanStartTime(null);
    }
  }, [loading, scanStartTime]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    setFile(selectedFile);
    setResults(null);
    setError(null);
    setProgress(null);
    setFileError(null);
    // File validation
    if (selectedFile) {
      if (selectedFile.type !== 'application/pdf') {
        setFileError('Please upload a valid PDF file.');
        setFile(null);
        return;
      }
      if (selectedFile.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
        setFileError(`File size exceeds ${MAX_FILE_SIZE_MB} MB limit.`);
        setFile(null);
        return;
      }
    }
    // Immediately show checklist with all steps as 'pending' for new file selection
    setExtractorChecklist([
      { name: 'file_upload', status: 'pending' },
      { name: 'text_extraction', status: 'pending' },
      { name: 'section_extraction', status: 'pending' },
      { name: 'cuec_extraction', status: 'pending' },
      { name: 'control_extraction', status: 'pending' },
      { name: 'subservice_orgs_extraction', status: 'pending' },
      { name: 'auditor', status: 'pending' },
      { name: 'company', status: 'pending' },
      { name: 'product', status: 'pending' },
      { name: 'report_date', status: 'pending' },
      { name: 'coverage_period', status: 'pending' }
    ]);
  };

  // Queue management functions
  const fetchQueueData = useCallback(async () => {
    try {
      const queueRes = await api.get('/analyze/queue');
      
      if (queueRes.data && Array.isArray(queueRes.data.scans)) {
        // Separate: core queue data vs volatile progress data
        const progressData: Record<string, any> = {};
        
        // Enhance queue data with real-time progress for running scans
        const enrichedScans = await Promise.all(
          queueRes.data.scans.map(async (scan: any) => {
            // Fetch progress for running and completed scans
            if (scan.status === 'running' || scan.status === 'completed') {
              try {
                const statusRes = await api.get(`/analyze/status_min/${scan.job_id}`);
                const status = statusRes.data;
                
                // Store progress data separately
                progressData[scan.job_id] = {
                  progress: status.progress || 0,
                  elapsedSeconds: status.elapsed_seconds || 0,
                  identifiedEntities: status.identified_entities || {},
                  detectedSubtype: status.detected_subtype,
                  reportDate: status.identified_entities?.report_date,
                  coveragePeriod: status.identified_entities?.coverage_period,
                  counters: status.counters || {},
                  error: status.error,
                  gptServiceWarning: status.gpt_service_warning
                };
                
                // Return scan with just stable data (no volatile fields)
                return scan;
              } catch (err) {
                // If status fetch fails, return scan as-is
                console.warn(`[AnalyzerPage] Failed to fetch status for ${scan.job_id}:`, err);
                return scan;
              }
            }
            return scan;
          })
        );
        
        // Update progress data separately (doesn't trigger history re-render)
        setScanProgress(progressData);
        
        // Check if any scans have completed - use functional setState to get current value
        setQueuedScans(previousScans => {
          const newlyCompleted = enrichedScans.filter((scan: any) => 
            scan.status === 'completed' && 
            previousScans.find((prev: any) => prev.job_id === scan.job_id && prev.status === 'running')
          );
          
          // If any scans just completed, refresh history to show them
          if (newlyCompleted.length > 0) {
            console.log(`[AnalyzerPage] ${newlyCompleted.length} scan(s) completed, refreshing history`);
            api.get(HISTORY_URL)
              .then((res: { data: ScanResult[] }) => {
                const historyData = res.data.map((scan) => ({
                  ...scan,
                  product: scan.product || 'Unknown Product',
                  timestamp: scan.timestamp || '',
                  results: scan.results || [],
                }));
                setHistory(historyData);
              })
              .catch((err: any) => console.error('Failed to refresh history:', err));
          }
          
          // Filter out completed/failed/cancelled scans - they should only appear in history
          const activeScans = enrichedScans.filter((scan: any) => 
            scan.status === 'queued' || scan.status === 'running'
          );
          
          // Smart comparison: only update if structural changes (not just progress/elapsed time)
          // Compare job_ids, statuses, and filenames to detect actual queue changes
          const hasStructuralChange = (
            previousScans.length !== activeScans.length ||
            previousScans.some((prev: any, idx: number) => {
              const current = activeScans[idx];
              return !current || 
                     prev.job_id !== current.job_id || 
                     prev.status !== current.status ||
                     prev.filename !== current.filename;
            })
          );
          
          if (hasStructuralChange) {
            return activeScans;
          }
          
          // No structural change - just progress updates, keep previous reference to avoid re-render
          return previousScans;
        });
        
        setQueuePaused(queueRes.data.is_paused || false);
      }
      
      // Stats are included in the same response
      if (queueRes.data && queueRes.data.stats) {
        setQueueStats(queueRes.data.stats);
      }
    } catch (err) {
      console.error('[AnalyzerPage] Failed to fetch queue data:', err);
    }
  }, []); // No dependencies - function is stable across renders

  const handleCancelScan = async (scanJobId: string) => {
    try {
      await api.delete(`/analyze/queue/${scanJobId}`);
      await fetchQueueData();
    } catch (err) {
      console.error('[AnalyzerPage] Failed to cancel scan:', err);
    }
  };

  const handlePauseScan = async (scanJobId: string) => {
    try {
      await api.post(`/analyze/queue/${scanJobId}/pause`);
      await fetchQueueData();
    } catch (err) {
      console.error('[AnalyzerPage] Failed to pause scan:', err);
    }
  };

  const handleResumeScan = async (scanJobId: string) => {
    try {
      await api.post(`/analyze/queue/${scanJobId}/resume`);
      await fetchQueueData();
    } catch (err) {
      console.error('[AnalyzerPage] Failed to resume scan:', err);
    }
  };

  // Polling interval for queue data
  useEffect(() => {
    // Always poll queue data, even without an active jobId
    // This ensures the queue updates after uploads and shows all queued scans
    fetchQueueData(); // Initial fetch
    
    const interval = setInterval(() => {
      fetchQueueData();
    }, POLL_INTERVAL);
    
    return () => clearInterval(interval);
  }, [fetchQueueData]); // Removed jobId dependency - always poll queue

  // Override handleUpload for background job
  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setResults(null);
    setError(null);
    setProgress(0);
    // Do NOT reset checklist here; keep it visible and persistent after upload
    // Don't clear jobId here, let it persist
    const formData = new FormData();
    formData.append("file", file);
    // report_type will be auto-detected by backend
    console.log('[AnalyzerPage] Uploading file for auto-detection');
    console.log('[AnalyzerPage] FormData entries:');
    for (const [key, value] of formData.entries()) {
      console.log(`  ${key}:`, value);
    }
    try {
      const response = await api.post(API_URL, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 2 * 60 * 1000,
      });
      if (response.data.job_id) {
        setJobId(response.data.job_id);
        console.log('[AnalyzerPage] setJobId called with:', response.data.job_id);
      } else {
        setError("Failed to start analysis job.");
        setLoading(false);
      }
    } catch (err: any) {
      setError(
        err.response?.data?.error ||
        err.message ||
        "An error occurred during analysis."
      );
      setLoading(false);
    }
  };

  // Handle user confirmation of detected report type
  const handleConfirmReportType = async (confirmedType: string, confirmedSubtype: string) => {
    if (!jobId) return;
    
    setConfirming(true);
    try {
      const formData = new FormData();
      formData.append("confirmed_type", confirmedType);
      formData.append("confirmed_subtype", confirmedSubtype);
      
      const response = await api.post(`${API_URL}confirm-type/${jobId}`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 30000,
      });
      
      console.log('[AnalyzerPage] Report type confirmed:', response.data);
      setShowConfirmDialog(false);
      setDetectionResult(null);
      setLoading(true);
      // Polling will automatically resume via useEffect since jobId and loading state changed
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
        err.message ||
        "Failed to confirm report type."
      );
      setShowConfirmDialog(false);
    } finally {
      setConfirming(false);
    }
  };

  // Settings dialog removed; settings are managed on dedicated Settings page

  const renderSection = (title: string, data: any, keyOverride?: string) => (
    <Accordion key={keyOverride || title}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="subtitle1">{title}</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          {typeof data === "object" ? JSON.stringify(data, null, 2) : String(data)}
        </pre>
      </AccordionDetails>
    </Accordion>
  );

  // Persist jobId to localStorage whenever it changes
  useEffect(() => {
    console.log('[AnalyzerPage] Persisting jobId to localStorage:', jobId);
    if (jobId) {
      localStorage.setItem('socanalyzer_job_id', jobId);
    } else {
      localStorage.removeItem('socanalyzer_job_id');
    }
  }, [jobId]);

  const handleDrag = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const selectedFile = e.dataTransfer.files[0];
      setFile(selectedFile);
      setResults(null);
      setError(null);
      setProgress(null);
      setFileError(null);
      
      // File validation
      if (selectedFile.type !== 'application/pdf') {
        setFileError('Please upload a valid PDF file.');
        setFile(null);
        return;
      }
      if (selectedFile.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
        setFileError(`File size exceeds ${MAX_FILE_SIZE_MB} MB limit.`);
        setFile(null);
        return;
      }
      
      // Set checklist to pending
      setExtractorChecklist([
        { name: 'file_upload', status: 'pending' },
        { name: 'text_extraction', status: 'pending' },
        { name: 'section_extraction', status: 'pending' },
        { name: 'cuec_extraction', status: 'pending' },
        { name: 'control_extraction', status: 'pending' },
        { name: 'subservice_orgs_extraction', status: 'pending' },
        { name: 'auditor', status: 'pending' },
        { name: 'company', status: 'pending' },
        { name: 'product', status: 'pending' },
        { name: 'report_date', status: 'pending' },
        { name: 'coverage_period', status: 'pending' }
      ]);
    }
  };

  useEffect(() => { localStorage.setItem('socanalyzer_dark_mode', darkMode ? 'true' : 'false'); }, [darkMode]);

  // Handle delete scan - memoized to prevent VirtualHistoryGrid re-renders
  const handleDeleteScan = useCallback(async (scanId: number | string) => {
    try {
      await api.delete(`/report/${scanId}`);
      // Refresh history after deletion
      const res = await api.get(HISTORY_URL);
      setHistory(res.data);
      console.log(`[DELETE_SCAN] Successfully deleted scan ${scanId}`);
    } catch (error) {
      console.error('[DELETE_SCAN] Error deleting scan:', error);
      // You could add a snackbar/toast notification here if desired
    }
  }, []);

  // Handle scan click - memoized to prevent VirtualHistoryGrid re-renders
  const handleScanClick = useCallback((scanId: number | string) => {
    navigate(`/app/report/${scanId}`);
  }, [navigate]);

  // Memoize search/filter callbacks to prevent HistorySection re-renders
  const handleSearchChange = useCallback((query: string) => {
    setSearchQuery(query);
  }, []);

  const handleFilterChange = useCallback((filter: string) => {
    setReportTypeFilter(filter);
  }, []);

  // Filter history based on search and report type
  const filteredHistory = useMemo(() => {
    return history.filter(scan => {
      // Search filter
      const searchLower = searchQuery.toLowerCase();
      const matchesSearch = !searchQuery || 
        scan.filename?.toLowerCase().includes(searchLower) ||
        (scan as any).company?.toLowerCase().includes(searchLower);
      
      // Report type filter
      const matchesType = reportTypeFilter === 'All' || 
        (scan.results as any)?.report_type === reportTypeFilter;
      
      return matchesSearch && matchesType;
    });
  }, [history, searchQuery, reportTypeFilter]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box data-theme={darkMode ? 'dark' : 'light'} sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
        <UserMenu title="SOC Report Analyzer" />
        
        <Box sx={{ maxWidth: 1400, mx: "auto", mt: 1, p: 1.5 }}>
          {/* Completed scans notification banner */}
          {showCompletedBanner && completedWhileAway.length > 0 && (
            <Alert 
              severity="success" 
              onClose={() => setShowCompletedBanner(false)}
              sx={{ mb: 3 }}
            >
              <Typography variant="body1" sx={{ fontWeight: 600, mb: 1 }}>
                {completedWhileAway.length} scan{completedWhileAway.length > 1 ? 's' : ''} completed while you were away!
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                {completedWhileAway.slice(0, 3).map((scan) => (
                  <Box key={scan.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <CheckCircleIcon sx={{ fontSize: 18, color: 'success.main' }} />
                    <Typography variant="body2">
                      {(scan as any).company || scan.filename}
                    </Typography>
                    <Button 
                      size="small" 
                      variant="text"
                      onClick={() => navigate(`/report/${scan.id}`)}
                      sx={{ ml: 'auto' }}
                    >
                      View Report
                    </Button>
                  </Box>
                ))}
                {completedWhileAway.length > 3 && (
                  <Typography variant="caption" sx={{ mt: 0.5, fontStyle: 'italic' }}>
                    ...and {completedWhileAway.length - 3} more
                  </Typography>
                )}
              </Box>
            </Alert>
          )}
          
          <Paper sx={{ p: 1.5, mb: 1.5 }}>
          {/* Finalized banner + quick summary counts if available */}
          {statusInfo?.finalized && (
            <Alert severity="info" sx={{ mb: 1, py: 0.5 }}>
              This job was finalized from existing artifacts on disk. Some sections may reflect prior extractor runs.
            </Alert>
          )}
          {/* Report type auto-detection notice */}
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, gap: 0.75 }}>
            <Tooltip title="Report type (SOC 1/SOC 2, Type 1/Type 2) will be automatically detected using GPT analysis. You'll be asked to confirm if confidence is below 85%.">
              <InfoOutlinedIcon fontSize="small" color="action" sx={{ fontSize: '1rem' }} />
            </Tooltip>
            <Typography variant="body2" sx={{ color: theme.palette.text.secondary, fontSize: '0.8rem' }}>
              Report type will be automatically detected
            </Typography>
          </Box>

          <Button onClick={() => navigate('/app-settings')} variant="outlined">Settings</Button>
          </Paper>
          
          {/* Scan Queue Section - Always visible */}
          <Paper sx={{ p: 1.5, mt: 1.5, mb: 1.5 }}>
            <Typography variant="h6" sx={{ mb: 1, fontSize: '1.1rem' }}>
              Scan Queue {queuePaused && <Chip label="PAUSED" color="warning" size="small" sx={{ ml: 1 }} />}
            </Typography>
            
            {/* Queue Controls */}
            <QueueControls 
              isPaused={queuePaused}
              queueLength={queuedScans.length}
              stats={queueStats}
              onQueueUpdate={fetchQueueData}
            />
            
            {/* Active/Queued Scans */}
            {queuedScans.length > 0 ? (
              <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {queuedScans.map((scan, idx) => {
                  // Merge in progress data from separate state
                  const progressInfo = scanProgress[scan.job_id] || {};
                  return (
                    <ActiveScanCard
                      key={scan.job_id}
                      jobId={scan.job_id}
                      filename={scan.filename}
                      reportType={scan.report_type || 'Unknown'}
                      status={scan.status}
                      priority={scan.priority}
                      position={idx}
                      progress={progressInfo.progress || 0}
                      elapsedSeconds={progressInfo.elapsedSeconds}
                      identifiedEntities={progressInfo.identifiedEntities}
                      detectedSubtype={progressInfo.detectedSubtype}
                      reportDate={progressInfo.reportDate}
                      coveragePeriod={progressInfo.coveragePeriod}
                      counters={progressInfo.counters}
                      error={progressInfo.error}
                      gptServiceWarning={progressInfo.gptServiceWarning}
                      onCancel={handleCancelScan}
                      onPause={handlePauseScan}
                      onResume={handleResumeScan}
                      onClick={(jobId) => {
                        // Navigate to scan details or focus on it
                        console.log('Clicked scan:', jobId);
                      }}
                    />
                  );
                })}
              </Box>
            ) : (
              <Box sx={{ mt: 2, p: 2, textAlign: 'center', color: 'text.secondary' }}>
                <Typography variant="body2">
                  No scans in queue. Upload PDFs to get started.
                </Typography>
              </Box>
            )}
          </Paper>
          
          {/* Scan History Section - Memoized to prevent re-renders */}
          <HistorySection
            history={history}
            historyLoading={historyLoading}
            searchQuery={searchQuery}
            reportTypeFilter={reportTypeFilter}
            onSearchChange={handleSearchChange}
            onFilterChange={handleFilterChange}
            onDeleteScan={handleDeleteScan}
          />
          
          {/* Snackbar for cancel */}
          <Snackbar open={openCancelSnackbar} autoHideDuration={4000} onClose={() => setOpenCancelSnackbar(false)}>
            <Alert severity="info" onClose={() => setOpenCancelSnackbar(false)}>
              Scan cancelled by user.
            </Alert>
          </Snackbar>

          {/* Snackbar for errors */}
          {error && (
            <Snackbar open={Boolean(error)} autoHideDuration={6000} onClose={() => setError(null)}>
              <Alert severity="error" onClose={() => setError(null)}>
                {error}
              </Alert>
            </Snackbar>
          )}

          {/* Report Type Confirmation Dialog */}
          <Dialog open={showConfirmDialog} onClose={() => {/* Do nothing - require explicit action */}}>
            <DialogTitle>Confirm Report Type</DialogTitle>
            <DialogContent>
              <Typography variant="body2" sx={{ mb: 2 }}>
                Detected report type: <strong>{detectionResult?.detected_type}</strong>
              </Typography>
              <Typography variant="body2" sx={{ mb: 2 }}>
                Confidence: <strong>{detectionResult?.confidence}%</strong>
              </Typography>
              <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
                {detectionResult?.explanation}
              </Typography>
              <Typography variant="body2">
                Please confirm or select a different type:
              </Typography>
              <FormControl fullWidth sx={{ mt: 2 }}>
                <InputLabel>Report Type</InputLabel>
                <Select
                  value={confirmedType}
                  label="Report Type"
                  onChange={(e) => setConfirmedType(e.target.value)}
                >
                  <MenuItem value="SOC1">SOC 1</MenuItem>
                  <MenuItem value="SOC2">SOC 2</MenuItem>
                  <MenuItem value="COMBINED">Combined (SOC 1 + SOC 2)</MenuItem>
                </Select>
              </FormControl>
              <FormControl fullWidth sx={{ mt: 2 }}>
                <InputLabel>Report Subtype</InputLabel>
                <Select
                  value={confirmedSubtype}
                  label="Report Subtype"
                  onChange={(e) => setConfirmedSubtype(e.target.value)}
                >
                  <MenuItem value="TYPE1">Type 1</MenuItem>
                  <MenuItem value="TYPE2">Type 2</MenuItem>
                </Select>
              </FormControl>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => handleConfirmReportType(confirmedType, confirmedSubtype)} disabled={confirming} variant="contained">
                {confirming ? 'Confirming...' : 'Confirm & Continue'}
              </Button>
            </DialogActions>
          </Dialog>

          {/* Help Dialog */}
          <HelpDialog open={helpDialogOpen} onClose={() => setHelpDialogOpen(false)} />

        </Box>
      </Box>
    </ThemeProvider>
  );
};

export default AnalyzerPage;

/**
 * ReportPage - SOC 2 Report Analysis Main Page
 * 
 * Orchestrator component that coordinates all report viewing and editing functionality.
 * Refactored from 2,974 lines to ~350 lines by extracting hooks, services, and components.
 */

import './ReportPage.css';
import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import UserMenu from '../components/auth/UserMenu';
import {
  Box,
  Button,
  Typography,
  CircularProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  ThemeProvider,
  CssBaseline,
  AppBar,
  Toolbar,
  Tabs,
  Tab,
  Snackbar,
  Alert,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SummarizeIcon from '@mui/icons-material/Summarize';
import ListAltIcon from '@mui/icons-material/ListAlt';
import AssignmentIcon from '@mui/icons-material/Assignment';
import PieChartIcon from '@mui/icons-material/PieChart';
import BusinessIcon from '@mui/icons-material/Business';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import WarningIcon from '@mui/icons-material/Warning';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import DescriptionIcon from '@mui/icons-material/Description';
import IconButton from '@mui/material/IconButton';
import { lightTheme, darkTheme, solidigmColors } from '../theme/solidigmTheme';

// API client
import api from '../api/client';

// Auth
import { useAuth } from '../contexts/AuthContext';

// Utilities
import { formatLocalDateTimeWithTZ } from '../utils/date';
import { getCoverageStart, getCoverageEnd, getReportDate } from '../utils/report';

// Custom hooks
import { useTabNavigation } from '../hooks/report/useTabNavigation';
import { useReportData } from '../hooks/report/useReportData';
import { useExecutiveSummary } from '../hooks/report/useExecutiveSummary';
import { useResourceCRUD } from '../hooks/report/useResourceCRUD';

// Services
import {
  filterHighConfidence,
  filterLowConfidence,
  normalizeConfidence,
  computeHighConfNameCounts,
} from '../services/report/dataTransformations';
import { getObjectives, getPrimaryObjectiveMappings, convertControlToObjective, type ControlObjective } from '../services/objectiveService';

// Configuration
import { API_URL, HISTORY_URL } from '../config/report/constants';

// Components - Tabs
import { ReportSummaryTab } from '../components/report/tabs/ReportSummaryTab';
import { ReportControlsTab } from '../components/report/tabs/ReportControlsTab';
import { ReportCuecsTab } from '../components/report/tabs/ReportCuecsTab';
import { ReportSuborgsTab } from '../components/report/tabs/ReportSuborgsTab';
import { ReportCoverageTab } from '../components/report/tabs/ReportCoverageTab';
import { ReportDeviationsTab } from '../components/report/tabs/ReportDeviationsTab';
import ObjectivesCoverageTab from '../components/report/tabs/ObjectivesCoverageTab';

// Components - Dialogs
import { AddItemDialog } from '../components/report/dialogs/AddItemDialog';
import ConfidenceModal from '../components/ConfidenceModal';
import CuecDetailsModal from '../components/CuecDetailsModal';
import ControlDetailsModal from '../components/ControlDetailsModal';
import FrameworkMappingDetailsModal from '../components/FrameworkMappingDetailsModal';
import HelpDialog from '../components/HelpDialog';
import FloatingGraceChat from '../components/FloatingGraceChat';
import ObjectivesModal from '../components/ObjectivesModal';

// Tab panel component with scroll restoration
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
  tabScrollPositions: React.MutableRefObject<{ [key: number]: number }>;
  noPadding?: boolean; // For tabs that manage their own layout (split view)
}

function TabPanel({ children, value, index, tabScrollPositions, noPadding = false }: TabPanelProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (value === index && ref.current) {
      const savedPosition = tabScrollPositions.current[index] || 0;
      ref.current.scrollTop = savedPosition;
    }
  }, [value, index, tabScrollPositions]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    if (value === index) {
      tabScrollPositions.current[index] = e.currentTarget.scrollTop;
    }
  };

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`report-tabpanel-${index}`}
      aria-labelledby={`report-tab-${index}`}
      style={{ height: '100%', overflow: 'auto' }}
      onScroll={handleScroll}
      ref={ref}
    >
      {value === index && (
        <Box sx={{ 
          height: '100%', 
          display: 'flex', 
          flexDirection: 'column',
          ...(noPadding ? {} : { p: 2, position: 'relative' })
        }}>
          {children}
        </Box>
      )}
    </div>
  );
}

function a11yProps(index: number) {
  return {
    id: `report-tab-${index}`,
    'aria-controls': `report-tabpanel-${index}`,
    'aria-label': `Tab ${index + 1}`,
  };
}

const ReportPage: React.FC = () => {
  // Temporarily disabled to reduce console noise
  // console.log('🎨 ReportPage component rendering/re-rendering', new Date().toISOString());

  // Router hooks
  const { scanId } = useParams<{ scanId: string }>();
  const navigate = useNavigate();

  // Theme state
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('socanalyzer_dark_mode') === 'true');
  const theme = darkMode ? darkTheme : lightTheme;

  useEffect(() => {
    localStorage.setItem('socanalyzer_dark_mode', darkMode.toString());
  }, [darkMode]);

  const textSx = useMemo(
    () => ({ color: darkMode ? '#e0e0e0' : '#2b2b2b', fontSize: 14, mb: 0.5 }),
    [darkMode]
  );

  // Tab navigation hook
  const { activeTab, handleTabChange, tabScrollPositions, searchParams } = useTabNavigation();

  // Scan selection state
  const [history, setHistory] = useState<any[]>([]);
  const [selectedScanId, setSelectedScanId] = useState<string | undefined>(scanId);

  // Report data hook
  const { report, setReport, loading, refreshReport } = useReportData(selectedScanId);

  // Executive summary hook
  const {
    executiveSummary,
    executiveSummaryStale,
    executiveSummaryLoading,
    setExecutiveSummary,
    setExecutiveSummaryStale,
    regenerateSummary,
    saveSummary,
  } = useExecutiveSummary(selectedScanId);

  // Framework criteria state
  const [frameworkCriteria, setFrameworkCriteria] = useState<any>({});
  
  // Fetch framework criteria on mount
  useEffect(() => {
    const fetchCriteria = async () => {
      try {
        const response = await api.get('/framework_criteria');
        setFrameworkCriteria(response.data);
      } catch (error) {
        console.error('Failed to load framework criteria:', error);
      }
    };
    fetchCriteria();
  }, []);

  // Ignored items state
  const [ignored] = useState<{
    cuecs: Set<number>;
    controls: Set<number>;
    suborgs: Set<number>;
  }>({ cuecs: new Set(), controls: new Set(), suborgs: new Set() });

  // Show/hide low confidence state
  const [showLowConfidence, setShowLowConfidence] = useState<{ [key: string]: boolean }>({});
  const toggleShowLowConfidence = useCallback((key: string) => {
    setShowLowConfidence(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // Memoized refresh callback to prevent render loop
  const handleRefreshReport = useCallback(() => {
    if (selectedScanId) {
      refreshReport(selectedScanId);
    }
  }, [selectedScanId, refreshReport]);

  // Recently changed IDs tracking
  const [recentlyChangedIds, setRecentlyChangedIds] = useState<Set<number>>(new Set());

  // Toast notifications
  const [toast, setToast] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info' | 'warning';
  }>({ open: false, message: '', severity: 'success' });
  const showToast = useCallback((message: string, severity: 'success' | 'error' | 'info' | 'warning' = 'success') => {
    setToast({ open: true, message, severity });
  }, []);
  const handleCloseToast = useCallback(() => setToast(prev => ({ ...prev, open: false })), []);

  // Excel export loading state
  const [excelExporting, setExcelExporting] = useState(false);

  // Resource CRUD hooks
  const { handleEdit, handleBatchEdit, handleIgnore, handleConfirm, handleRecompute, handleRecomputeAllHighConfidence, handleToggleDeviation } = useResourceCRUD({
    scanId: selectedScanId,
    setReport,
    showToast,
    setRecentlyChangedIds
  });

  // Create type-specific handler wrappers for each resource
  const suborgHandlers = useMemo(() => ({
    handleEdit: (row: any, idx: number) => handleEdit('suborgs', row, idx),
    handleBatchEdit: (changes: { [rowIdx: number]: any }, rows: any[]) => handleBatchEdit('suborgs', changes, rows),
    handleIgnore: (row: any) => handleIgnore('suborgs', row),
    handleConfirm: (row: any) => handleConfirm('suborgs', row),
    handleRecompute: async (row: any) => { /* Suborgs don't have recompute */ },
    handleRecomputeAllHighConfidence: async () => { /* Suborgs don't have recompute */ }
  }), [handleEdit, handleBatchEdit, handleIgnore, handleConfirm]);

  const cuecHandlers = useMemo(() => ({
    handleEdit: (row: any, idx: number) => handleEdit('cuecs', row, idx),
    handleBatchEdit: (changes: { [rowIdx: number]: any }, rows: any[]) => handleBatchEdit('cuecs', changes, rows),
    handleIgnore: (row: any) => handleIgnore('cuecs', row),
    handleConfirm: (row: any) => handleConfirm('cuecs', row),
    handleRecompute: async (row: any) => handleRecompute('cuecs', row),
    handleRecomputeAllHighConfidence: async () => handleRecomputeAllHighConfidence('cuecs')
  }), [handleEdit, handleBatchEdit, handleIgnore, handleConfirm, handleRecompute, handleRecomputeAllHighConfidence]);

  const controlHandlers = useMemo(() => ({
    handleEdit: (row: any, idx: number) => handleEdit('controls', row, idx),
    handleBatchEdit: (changes: { [rowIdx: number]: any }, rows: any[]) => handleBatchEdit('controls', changes, rows),
    handleIgnore: (row: any) => handleIgnore('controls', row),
    handleConfirm: (row: any) => handleConfirm('controls', row),
    handleRecompute: async (row: any) => handleRecompute('controls', row),
    handleRecomputeAllHighConfidence: async () => handleRecomputeAllHighConfidence('controls'),
    handleToggleDeviation: async (row: any, hasDeviation: boolean) => handleToggleDeviation(row, hasDeviation)
  }), [handleEdit, handleBatchEdit, handleIgnore, handleConfirm, handleRecompute, handleRecomputeAllHighConfidence, handleToggleDeviation]);

  // Overview edit state
  const [overviewEdit, setOverviewEdit] = useState(false);
  const [overviewFields, setOverviewFields] = useState<{
    company: string;
    product: string;
    coverageStart: string;
    coverageEnd: string;
    reportDate: string;
    auditor: string;
    scanDate: string;
    isSoxVendor: boolean;
    reportType?: string;
    asOfDate?: string;
  }>({
    company: '',
    product: '',
    coverageStart: '',
    coverageEnd: '',
    reportDate: '',
    auditor: '',
    scanDate: '',
    isSoxVendor: false,
  });

  // Add item dialog state
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [addDialogType, setAddDialogType] = useState<'suborg' | 'cuec' | 'control'>('suborg');

  // Default confidence state (persisted)
  const [defaultConfidence, setDefaultConfidence] = useState<string>(
    () => localStorage.getItem('socanalyzer_default_confidence') ?? '95'
  );
  const [useDefaultConfidence, setUseDefaultConfidence] = useState<boolean>(
    () => (localStorage.getItem('socanalyzer_use_default_confidence') ?? 'true') !== 'false'
  );

  useEffect(() => {
    localStorage.setItem('socanalyzer_default_confidence', defaultConfidence);
  }, [defaultConfidence]);

  useEffect(() => {
    localStorage.setItem('socanalyzer_use_default_confidence', useDefaultConfidence ? 'true' : 'false');
  }, [useDefaultConfidence]);

  // Auth & Objectives
  const { user } = useAuth();
  const [objectives, setObjectives] = useState<ControlObjective[]>([]);
  const [objectivesLoading, setObjectivesLoading] = useState(false);
  const [objectivesModalOpen, setObjectivesModalOpen] = useState(false);
  const [objectiveMappings, setObjectiveMappings] = useState<Map<string | number, any>>(new Map());
  const { accessToken, loading: authLoading } = useAuth();

  // Confidence modal state
  const [confidenceModalOpen, setConfidenceModalOpen] = useState(false);
  const [selectedControl, setSelectedControl] = useState<any>(null);

  // CUEC details modal state
  const [cuecModalOpen, setCuecModalOpen] = useState(false);
  
  // Framework mapping details modal state
  const [mappingDetailsModalOpen, setMappingDetailsModalOpen] = useState(false);
  const [selectedMappingControl, setSelectedMappingControl] = useState<any>(null);
  const [selectedFrameworkType, setSelectedFrameworkType] = useState<string>('');
  const [selectedCuec, setSelectedCuec] = useState<any>(null);

  // Control details modal state
  const [controlDetailsModalOpen, setControlDetailsModalOpen] = useState(false);
  const [selectedControlDetails, setSelectedControlDetails] = useState<any>(null);

  // Help dialog state
  const [helpDialogOpen, setHelpDialogOpen] = useState(false);
  const handleOpenHelp = useCallback(() => {
    setHelpDialogOpen(true);
  }, []);

  // F1 keyboard shortcut for help
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'F1') {
        event.preventDefault();
        setHelpDialogOpen(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Load history on mount
  useEffect(() => {
    api
      .get(HISTORY_URL)
      .then(res => {
        setHistory(res.data || []);
        if (!selectedScanId && res.data?.length > 0) {
          setSelectedScanId(res.data[0].id.toString());
        }
      })
      .catch(err => console.error('Failed to load history:', err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);



  // Load report when selectedScanId changes
  useEffect(() => {
    if (selectedScanId) {
      refreshReport(selectedScanId);
    }
  }, [selectedScanId, refreshReport]);

  // Fetch and cache objectives for current scan
  useEffect(() => {
    const fetchObjectivesData = async () => {
      if (!selectedScanId) return;
      if (authLoading || !accessToken) return;

      setObjectivesLoading(true);
      try {
        const scanIdNum = parseInt(selectedScanId);
        const objectivesData = await getObjectives(scanIdNum);
        setObjectives(objectivesData);

        const mappingsMap = new Map<string | number, any>();
        try {
          const mappingResponse = await getPrimaryObjectiveMappings(scanIdNum);
          (mappingResponse.mappings || []).forEach((mapping: any) => {
            if (!mapping?.is_primary) return;
            const controlDbId = mapping.control_db_id;
            const controlId = mapping.control_id;

            if (controlDbId !== undefined && controlDbId !== null) {
              mappingsMap.set(controlDbId, mapping);
            }
            if (controlId !== undefined && controlId !== null) {
              mappingsMap.set(controlId, mapping);
            }
          });
        } catch (error) {
          console.debug('Primary objective mappings not available');
        }

        setObjectiveMappings(mappingsMap);
      } catch (error) {
        console.error('Error fetching objectives:', error);
      } finally {
        setObjectivesLoading(false);
      }
    };

    fetchObjectivesData();
  }, [selectedScanId, accessToken, authLoading]);

  // Sync overview fields when report loads
  useEffect(() => {
    if (report) {
      setOverviewFields({
        company: report.company || '',
        product: report.product || '',
        coverageStart: report.coverage_start || '',
        coverageEnd: report.coverage_end || '',
        reportDate: report.report_date || '',
        auditor: report.auditor || '',
        scanDate: report.scan_date || '',
        isSoxVendor: report.is_sox_vendor || false,
        reportType: report.report_type || 'SOC2',
        asOfDate: report.as_of_date || '',
      });
      setExecutiveSummary(report.executive_summary_json || report.executive_summary || null);
      setExecutiveSummaryStale(report.executive_summary_stale || false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report]);

  // Extract filtered data
  const allSubOrgs = useMemo(() => {
    return report?.subservice_orgs || report?.subservice_organizations || [];
  }, [report]);

  const allCuecs = useMemo(() => report?.cuecs || [], [report]);
  const allControls = useMemo(() => report?.controls || [], [report]);

  const filteredHighConfSubOrgs = useMemo(
    () => filterHighConfidence(allSubOrgs, 'confidence').filter((s: any) => !ignored.suborgs.has(s.id)),
    [allSubOrgs, ignored.suborgs]
  );
  const filteredLowConfSubOrgs = useMemo(
    () => filterLowConfidence(allSubOrgs, 'confidence').filter((s: any) => !ignored.suborgs.has(s.id)),
    [allSubOrgs, ignored.suborgs]
  );

  const filteredHighConfCuecs = useMemo(
    () => filterHighConfidence(allCuecs, 'cuec_confidence').filter((c: any) => !ignored.cuecs.has(c.id)),
    [allCuecs, ignored.cuecs]
  );
  const filteredLowConfCuecs = useMemo(
    () => filterLowConfidence(allCuecs, 'cuec_confidence').filter((c: any) => !ignored.cuecs.has(c.id)),
    [allCuecs, ignored.cuecs]
  );

  const filteredHighConfControls = useMemo(
    () => filterHighConfidence(allControls, 'control_confidence').filter((c: any) => !ignored.controls.has(c.id)),
    [allControls, ignored.controls]
  );
  const filteredLowConfControls = useMemo(
    () => filterLowConfidence(allControls, 'control_confidence').filter((c: any) => !ignored.controls.has(c.id)),
    [allControls, ignored.controls]
  );

  // Compute duplicate suborg names
  const hasAnyDuplicateSoNames = useMemo(() => {
    const nameCounts = computeHighConfNameCounts(filteredHighConfSubOrgs);
    return Array.from(nameCounts.values()).some(count => count > 1);
  }, [filteredHighConfSubOrgs]);



  // Save overview fields
  const handleSaveOverview = useCallback(async () => {
    if (!selectedScanId) return;
    try {
      await api.patch(`${API_URL}${selectedScanId}/overview`, {
        company: overviewFields.company,
        product: overviewFields.product,
        coverage_start: overviewFields.coverageStart,
        coverage_end: overviewFields.coverageEnd,
        report_date: overviewFields.reportDate,
        auditor: overviewFields.auditor,
        is_sox_vendor: overviewFields.isSoxVendor,
      });
      if (selectedScanId) await refreshReport(selectedScanId);
      setOverviewEdit(false);
      showToast('Overview updated', 'success');
    } catch (err: any) {
      console.error('Failed to save overview:', err);
      showToast('Failed to save overview', 'error');
    }
  }, [selectedScanId, overviewFields, refreshReport, showToast]);

  const handleOverviewFieldChange = useCallback((field: string, value: any) => {
    setOverviewFields(prev => ({ ...prev, [field]: value }));
  }, []);

  // Add item handlers
  const handleOpenAddDialog = useCallback((type: 'suborg' | 'cuec' | 'control') => {
    setAddDialogType(type);
    setAddDialogOpen(true);
  }, []);

  const handleCreateItem = useCallback(async (formData: Record<string, any>) => {
    if (!selectedScanId) return;

    try {
      if (addDialogType === 'suborg') {
        const name = (formData.name || '').trim();
        if (!name) {
          showToast('Name is required', 'warning');
          return;
        }
        const payload: any = { name };
        if (formData.confidence) {
          const norm = normalizeConfidence(formData.confidence);
          if (norm !== undefined) payload.confidence = norm;
        }
        if (formData.third_party_description) payload.third_party_description = formData.third_party_description;
        if (formData.third_party_page_ref) payload.third_party_page_ref = formData.third_party_page_ref;

        const { data: created } = await api.post(`${API_URL}${selectedScanId}/suborgs`, payload);
        setReport((prev: any) => {
          if (!prev) return prev;
          const pushTo = (arr: any[]) => [...(arr || []), created];
          const next: any = { ...prev };
          if (prev.subservice_organizations) next.subservice_organizations = pushTo(prev.subservice_organizations);
          if (prev.subservice_orgs) next.subservice_orgs = pushTo(prev.subservice_orgs);
          if (!prev.subservice_organizations && !prev.subservice_orgs) next.subservice_orgs = pushTo([]);
          return next;
        });
        showToast('Subservice org created', 'success');
      } else if (addDialogType === 'cuec') {
        const desc = (formData.cuec_description || '').trim();
        if (!desc) {
          showToast('Description is required', 'warning');
          return;
        }
        const payload: any = { cuec_description: desc };
        if (formData.cuec_confidence) {
          const norm = normalizeConfidence(formData.cuec_confidence);
          if (norm !== undefined) payload.cuec_confidence = norm;
        }
        if (formData.control_strength) payload.control_strength = formData.control_strength;

        const { data: created } = await api.post(`${API_URL}${selectedScanId}/cuecs`, payload);
        setReport((prev: any) => ({ ...prev, cuecs: [...(prev?.cuecs || []), created] }));
        showToast('CUEC created', 'success');
      } else if (addDialogType === 'control') {
        const hasDesc = (formData.control_desc || '').trim().length > 0;
        const hasId = (formData.control_id || '').trim().length > 0;
        if (!hasDesc && !hasId) {
          showToast('Control ID or Description required', 'warning');
          return;
        }
        const payload: any = {};
        if (hasId) payload.control_id = (formData.control_id || '').trim();
        if (hasDesc) payload.control_desc = (formData.control_desc || '').trim();
        if (formData.control_test) {
          const testValue = typeof formData.control_test === 'string' 
            ? formData.control_test 
            : String(formData.control_test);
          payload.control_test = testValue.trim();
        }
        if (formData.control_test_results) {
          const testResultsValue = typeof formData.control_test_results === 'string'
            ? formData.control_test_results
            : String(formData.control_test_results);
          payload.control_test_results = testResultsValue.trim();
        }
        if (formData.has_deviation !== undefined) payload.has_deviation = formData.has_deviation;
        if (formData.deviation_desc) payload.deviation_desc = (formData.deviation_desc || '').trim();
        if (formData.control_page_ref) payload.control_page_ref = formData.control_page_ref;
        if (formData.control_confidence) {
          const norm = normalizeConfidence(formData.control_confidence);
          if (norm !== undefined) payload.control_confidence = norm;
        }

        const { data: created } = await api.post(`${API_URL}${selectedScanId}/controls`, payload);
        
        // Automatically trigger TSC/COSO framework mapping after creation
        try {
          showToast('Control created, computing frameworks...', 'info');
          const mappingResp = await api.post(`${API_URL}${selectedScanId}/controls/id/${created.id}/recompute_frameworks`);
          const mappedControl = { ...created, ...mappingResp.data.control };
          setReport((prev: any) => ({ ...prev, controls: [...(prev?.controls || []), mappedControl] }));
          
          const message = mappingResp.data?.message;
          const mappingCount = mappingResp.data?.mapping_count;
          if (mappingCount === 0) {
            showToast('Control created (no framework mappings found)', 'warning');
          } else if (message) {
            showToast(`Control created: ${message}`, 'success');
          } else {
            showToast('Control created with framework mappings', 'success');
          }
        } catch (mappingError: any) {
          console.warn('Framework mapping failed, control created without mappings:', mappingError);
          setReport((prev: any) => ({ ...prev, controls: [...(prev?.controls || []), created] }));
          showToast('Control created (framework mapping failed)', 'warning');
        }
      }

      setAddDialogOpen(false);
      setExecutiveSummaryStale(true);
    } catch (e: any) {
      console.error('Failed to create item:', e);
      const msg = e?.response?.data || e?.message || 'Failed to create item';
      showToast(typeof msg === 'string' ? msg : 'Failed to create item', 'error');
    }
  }, [selectedScanId, addDialogType, showToast, setReport, setExecutiveSummaryStale]);

  // Handle confidence modal
  const handleOpenConfidenceModal = useCallback((control: any) => {
    console.log('[ReportPage] Opening confidence modal for control:', control?.control_id);
    setSelectedControl(control);
    setConfidenceModalOpen(true);
  }, []);

  // Handle CUEC modal
  const handleOpenCuecModal = useCallback((cuec: any) => {
    setSelectedCuec(cuec);
    setCuecModalOpen(true);
  }, []);

  // Handle Control modal
  const handleOpenControlModal = useCallback((control: any) => {
    setSelectedControlDetails(control);
    setControlDetailsModalOpen(true);
  }, []);
  
  // Handle Framework Mapping Details modal
  const handleOpenMappingDetails = useCallback((control: any, frameworkType: string) => {
    console.log('[ReportPage] Opening framework mapping details:', frameworkType, control);
    setSelectedMappingControl(control);
    setSelectedFrameworkType(frameworkType);
    setMappingDetailsModalOpen(true);
  }, []);

  // Handle Objectives modal
  const handleOpenObjectivesModal = useCallback(() => {
    setObjectivesModalOpen(true);
  }, []);

  const handleCloseObjectivesModal = useCallback(() => {
    setObjectivesModalOpen(false);
  }, []);

  const handleObjectivesRefresh = useCallback(async () => {
    if (!selectedScanId) return;

    try {
      const scanIdNum = parseInt(selectedScanId);
      const objectivesData = await getObjectives(scanIdNum);
      setObjectives(objectivesData);

      const mappingsMap = new Map<string | number, any>();
      try {
        const mappingResponse = await getPrimaryObjectiveMappings(scanIdNum);
        (mappingResponse.mappings || []).forEach((mapping: any) => {
          if (!mapping?.is_primary) return;
          const controlDbId = mapping.control_db_id;
          const controlId = mapping.control_id;

          if (controlDbId !== undefined && controlDbId !== null) {
            mappingsMap.set(controlDbId, mapping);
          }
          if (controlId !== undefined && controlId !== null) {
            mappingsMap.set(controlId, mapping);
          }
        });
      } catch (error) {
        console.debug('Primary objective mappings not available');
      }

      setObjectiveMappings(mappingsMap);

      // Refresh report data without triggering full-page loading spinner
      const res = await api.get(`${API_URL}${selectedScanId}`, { timeout: 60000 });
      setReport(res.data);
    } catch (error) {
      console.error('Error refreshing objectives:', error);
    }
  }, [selectedScanId, setReport]);

  // Regenerate executive summary wrapper
  const handleRegenerateExecutiveSummary = useCallback(async () => {
    if (!selectedScanId) return;
    try {
      await regenerateSummary(selectedScanId);
      showToast('Executive summary regenerated', 'success');
    } catch (err) {
      showToast('Failed to regenerate executive summary', 'error');
    }
  }, [selectedScanId, regenerateSummary, showToast]);

  // Save executive summary wrapper
  const handleSaveExecutiveSummary = useCallback(async (summary: any) => {
    if (!selectedScanId) return;
    try {
      await saveSummary(selectedScanId, summary);
      showToast('Executive summary saved', 'success');
    } catch (err) {
      showToast('Failed to save executive summary', 'error');
      throw err;
    }
  }, [selectedScanId, saveSummary, showToast]);

  // Rescan report wrapper
  const handleRescanReport = useCallback(async () => {
    if (!selectedScanId) return;
    try {
      const response = await api.post(`/report/${selectedScanId}/rescan`);
      const jobId = response.data?.job_id;
      showToast(`Rescan initiated. Job ID: ${jobId}`, 'success');
      // Redirect to analyzer page to show queue status
      window.location.href = '/#/analyzer';
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || 'Failed to initiate rescan';
      showToast(errorMsg, 'error');
      throw err;
    }
  }, [selectedScanId, showToast]);

  // Format date helper
  const formatLocalDateWithTZ = useCallback((date: string) => {
    if (!date) return '';
    return formatLocalDateTimeWithTZ(date);
  }, []);

  // Extract date helpers
  const coverageStart = report ? (getCoverageStart(report) || '') : '';
  const coverageEnd = report ? (getCoverageEnd(report) || '') : '';
  const reportDate = report ? (getReportDate(report) || '') : '';

  if (loading) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: '100vh',
            bgcolor: 'background.default',
          }}
        >
          <CircularProgress />
        </Box>
      </ThemeProvider>
    );
  }

  if (!report) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box sx={{ p: 2, bgcolor: 'background.default', minHeight: '100vh' }}>
          <Typography>No report found</Typography>
        </Box>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box data-theme={darkMode ? 'dark' : 'light'} sx={{ display: 'flex', flexDirection: 'column', height: '100vh', bgcolor: 'background.default' }}>
        {/* User Menu */}
        <UserMenu title="SOC Report Analysis" />
        
        {/* Report Controls Toolbar */}
        <AppBar position="static" elevation={0} sx={{ bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider' }}>
          <Toolbar variant="dense">
            <Button variant="text" startIcon={<ArrowBackIcon />} onClick={() => navigate('/')} sx={{ mr: 2 }}>
              Back
            </Button>

            <Box sx={{ flexGrow: 1 }} />

            {/* Help Button */}
            <IconButton
              color="primary"
              onClick={handleOpenHelp}
              sx={{ mr: 1 }}
              title="Help (F1)"
            >
              <HelpOutlineIcon />
            </IconButton>

            {/* Export to Excel Button */}
            <Button
              variant="outlined"
              size="small"
              startIcon={excelExporting ? <CircularProgress size={16} /> : <DescriptionIcon />}
              disabled={excelExporting}
              onClick={async () => {
                try {
                  setExcelExporting(true);
                  console.log('[Excel Export] Starting export for scan:', selectedScanId);
                  
                  // Fetch Excel file with authentication
                  const response = await api.get(`/export/excel/${selectedScanId}`, {
                    responseType: 'blob'
                  });
                  
                  console.log('[Excel Export] Response received:', response);
                  console.log('[Excel Export] Response status:', response.status);
                  console.log('[Excel Export] Response headers:', response.headers);
                  
                  // Check if response is actually an Excel file
                  const contentType = response.headers?.['content-type'] || response.headers?.contentType;
                  console.log('[Excel Export] Content-Type:', contentType);
                  
                  if (contentType && !contentType.includes('spreadsheet') && !contentType.includes('octet-stream')) {
                    // Likely an error message
                    const text = await response.data.text();
                    console.error('[Excel Export] Unexpected content type:', contentType, 'Content:', text);
                    alert(`Failed to export Excel: ${text.substring(0, 200)}`);
                    return;
                  }
                  
                  // Create blob and download
                  const blob = new Blob([response.data], { 
                    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
                  });
                  
                  console.log('[Excel Export] Blob created, size:', blob.size);
                  
                  const url = URL.createObjectURL(blob);
                  
                  // Create temporary link and trigger download
                  const link = document.createElement('a');
                  link.href = url;
                  link.download = `SOC_Analysis_Report_${selectedScanId}.xlsx`;
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                  
                  // Clean up blob URL
                  setTimeout(() => URL.revokeObjectURL(url), 100);
                  
                  console.log('[Excel Export] Download triggered successfully');
                  showToast('Excel file exported successfully', 'success');
                } catch (err: any) {
                  console.error('[Excel Export] Error:', err);
                  console.error('[Excel Export] Error response:', err.response);
                  const errorMsg = err.message || 'Unknown error';
                  showToast(`Failed to export Excel file: ${errorMsg}`, 'error');
                } finally {
                  setExcelExporting(false);
                }
              }}
              sx={{ mr: 1, fontSize: '0.75rem', py: 0.5 }}
              title="Export to Excel"
            >
              {excelExporting ? 'Exporting...' : 'Excel Export'}
            </Button>

            {/* View PDF Button */}
            {report?.filename && (
              <Button
                variant="outlined"
                size="small"
                startIcon={<PictureAsPdfIcon />}
                onClick={async () => {
                  try {
                    // Fetch PDF with authentication
                    const response = await api.get(`/pdf/${selectedScanId}`, {
                      responseType: 'blob'
                    });
                    
                    // Create blob URL and open in new tab
                    const blob = new Blob([response.data], { type: 'application/pdf' });
                    const blobUrl = URL.createObjectURL(blob);
                    window.open(blobUrl, '_blank');
                    
                    // Clean up blob URL after a delay
                    setTimeout(() => URL.revokeObjectURL(blobUrl), 100);
                  } catch (err) {
                    console.error('Failed to open PDF:', err);
                    showToast('Failed to open PDF. Please try again.', 'error');
                  }
                }}
                sx={{ mr: 1, fontSize: '0.75rem', py: 0.5 }}
                title="View PDF"
              >
                View PDF
              </Button>
            )}

            {/* Company Logo */}
            {selectedScanId && history.find((h: any) => h.id.toString() === selectedScanId)?.logo_url && (
              <Box
                component="img"
                src={history.find((h: any) => h.id.toString() === selectedScanId)?.logo_url}
                alt="Company Logo"
                sx={{
                  height: 40,
                  maxWidth: 100,
                  objectFit: 'contain',
                  mr: 2,
                  borderRadius: 1,
                  bgcolor: 'white',
                  p: 0.5,
                  boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                }}
                onError={(e: any) => {
                  e.target.style.display = 'none';
                }}
              />
            )}
          </Toolbar>
        </AppBar>

        {/* Tabs */}
        <Box sx={{ borderBottom: 2, borderColor: solidigmColors.purple }}>
          <Tabs 
            value={activeTab} 
            onChange={handleTabChange} 
            variant="scrollable" 
            scrollButtons="auto"
            sx={{
              '& .MuiTab-root': {
                color: 'text.secondary',
                '&.Mui-selected': {
                  color: solidigmColors.purple,
                },
              },
              '& .MuiTabs-indicator': {
                backgroundColor: solidigmColors.purple,
                height: 3,
              },
            }}
          >
            <Tab label="Summary" icon={<SummarizeIcon />} iconPosition="start" {...a11yProps(0)} />
            <Tab 
              label="Controls"
              icon={<ListAltIcon />} 
              iconPosition="start" 
              {...a11yProps(1)} 
            />
            <Tab label="CUECs" icon={<AssignmentIcon />} iconPosition="start" {...a11yProps(2)} />
            <Tab label="Subservice Orgs" icon={<BusinessIcon />} iconPosition="start" {...a11yProps(3)} />
            <Tab label="Deviations" icon={<WarningIcon />} iconPosition="start" {...a11yProps(4)} />
            <Tab label="Coverage" icon={<PieChartIcon />} iconPosition="start" {...a11yProps(5)} />
            <Tab label="Objective Coverage" icon={<AssignmentIcon />} iconPosition="start" {...a11yProps(6)} />
          </Tabs>
        </Box>

        {/* Tab Panels */}
        <Box sx={{ flexGrow: 1, overflow: 'hidden' }}>
          <TabPanel value={activeTab} index={0} tabScrollPositions={tabScrollPositions}>
            <ReportSummaryTab
              overviewFields={overviewFields}
              overviewEdit={overviewEdit}
              executiveSummary={executiveSummary}
              executiveSummaryStale={executiveSummaryStale}
              executiveSummaryLoading={executiveSummaryLoading}
              coverageStart={coverageStart}
              coverageEnd={coverageEnd}
              reportDate={reportDate}
              filteredHighConfSubOrgs={filteredHighConfSubOrgs}
              filteredHighConfCuecs={filteredHighConfCuecs}
              filteredHighConfControls={filteredHighConfControls}
              onOverviewFieldChange={handleOverviewFieldChange}
              onSaveOverview={handleSaveOverview}
              onSetOverviewEdit={setOverviewEdit}
              onRegenerateExecutiveSummary={handleRegenerateExecutiveSummary}
              onSaveExecutiveSummary={handleSaveExecutiveSummary}
              onRescanReport={handleRescanReport}
              onOpenHelp={handleOpenHelp}
              formatLocalDateWithTZ={formatLocalDateWithTZ}
              theme={theme}
              textSx={textSx}
            />
          </TabPanel>
          <TabPanel value={activeTab} index={1} tabScrollPositions={tabScrollPositions} noPadding>
            <ReportControlsTab
              scanId={selectedScanId}
              filteredHighConfControls={filteredHighConfControls}
              filteredLowConfControls={filteredLowConfControls}
              ignored={ignored}
              showLowConfidence={showLowConfidence['controls']}
              onToggleLowConfidence={() => toggleShowLowConfidence('controls')}
              onEdit={controlHandlers.handleEdit}
              onBatchEdit={controlHandlers.handleBatchEdit}
              onIgnore={controlHandlers.handleIgnore}
              onConfirm={controlHandlers.handleConfirm}
              onRecompute={controlHandlers.handleRecompute}
              onRecomputeAllHighConfidence={controlHandlers.handleRecomputeAllHighConfidence}
              onToggleDeviation={controlHandlers.handleToggleDeviation}
              onRefresh={handleRefreshReport}
              onAddControl={() => handleOpenAddDialog('control')}
              onOpenConfidenceModal={handleOpenConfidenceModal}
              onOpenControlModal={handleOpenControlModal}
              frameworkCriteria={frameworkCriteria}
              onOpenMappingDetails={handleOpenMappingDetails}
              darkMode={darkMode}
              tocPageOffset={report?.toc_page_offset}
              objectives={objectives}
              objectivesLoading={objectivesLoading}
              objectiveMappings={objectiveMappings}
              onOpenObjectivesModal={handleOpenObjectivesModal}
              isAdmin={user?.is_admin}
              onObjectivesRefresh={handleObjectivesRefresh}
              showToast={showToast}
            />
          </TabPanel>

          <TabPanel value={activeTab} index={2} tabScrollPositions={tabScrollPositions} noPadding>
            <ReportCuecsTab
              scanId={scanId}
              filteredHighConfCuecs={filteredHighConfCuecs}
              filteredLowConfCuecs={filteredLowConfCuecs}
              ignored={ignored}
              recentlyChangedIds={recentlyChangedIds}
              showLowConfidence={showLowConfidence['cuecs']}
              onToggleLowConfidence={() => toggleShowLowConfidence('cuecs')}
              onEdit={cuecHandlers.handleEdit}
              onBatchEdit={cuecHandlers.handleBatchEdit}
              onIgnore={cuecHandlers.handleIgnore}
              onConfirm={cuecHandlers.handleConfirm}
              onRecompute={cuecHandlers.handleRecompute}
              onRecomputeAllHighConfidence={cuecHandlers.handleRecomputeAllHighConfidence}
              onAddCuec={() => handleOpenAddDialog('cuec')}
              frameworkCriteria={frameworkCriteria}
              onOpenMappingDetails={handleOpenMappingDetails}
              darkMode={darkMode}
              tocPageOffset={report?.toc_page_offset}
              refreshReport={handleRefreshReport}
            />
          </TabPanel>

          <TabPanel value={activeTab} index={3} tabScrollPositions={tabScrollPositions} noPadding>
            <ReportSuborgsTab
              scanId={scanId}
              filteredHighConfSubOrgs={filteredHighConfSubOrgs}
              filteredLowConfSubOrgs={filteredLowConfSubOrgs}
              ignored={ignored}
              recentlyChangedIds={recentlyChangedIds}
              hasAnyDuplicateSoNames={hasAnyDuplicateSoNames}
              showLowConfidence={showLowConfidence['suborgs']}
              onToggleLowConfidence={() => toggleShowLowConfidence('suborgs')}
              onEdit={suborgHandlers.handleEdit}
              onBatchEdit={suborgHandlers.handleBatchEdit}
              onIgnore={suborgHandlers.handleIgnore}
              onConfirm={suborgHandlers.handleConfirm}
              onAddSuborg={() => handleOpenAddDialog('suborg')}
              darkMode={darkMode}
              theme={theme}
              tocPageOffset={report?.toc_page_offset}
              refreshReport={handleRefreshReport}
            />
          </TabPanel>

          <TabPanel value={activeTab} index={4} tabScrollPositions={tabScrollPositions}>
            <ReportDeviationsTab scanId={selectedScanId!} />
          </TabPanel>

          <TabPanel value={activeTab} index={5} tabScrollPositions={tabScrollPositions}>
            <ReportCoverageTab
              highConfControlsForCoverage={filteredHighConfControls}
              highConfCuecsFiltered={filteredHighConfCuecs}
              onOpenCuecModal={handleOpenCuecModal}
              onOpenControlModal={handleOpenControlModal}
            />
          </TabPanel>

          <TabPanel value={activeTab} index={6} tabScrollPositions={tabScrollPositions}>
            <ObjectivesCoverageTab
              scanId={parseInt(selectedScanId || '0')}
              onOpenControlModal={handleOpenControlModal}
              onRefresh={handleObjectivesRefresh}
            />
          </TabPanel>
        </Box>

        {/* Floating GRaCe Assistant - Available on all tabs */}
        {selectedScanId && (
          <FloatingGraceChat scanId={parseInt(selectedScanId)} />
        )}

        {/* Dialogs */}
        <AddItemDialog
          open={addDialogOpen}
          type={addDialogType}
          scanId={selectedScanId}
          onClose={() => setAddDialogOpen(false)}
          onCreate={handleCreateItem}
          defaultConfidence={defaultConfidence}
          useDefaultConfidence={useDefaultConfidence}
          onDefaultConfidenceChange={setDefaultConfidence}
          onUseDefaultConfidenceChange={setUseDefaultConfidence}
        />

        <ConfidenceModal
          open={confidenceModalOpen}
          control={selectedControl}
          onClose={() => setConfidenceModalOpen(false)}
          onOpenControlDetails={handleOpenControlModal}
        />

        <CuecDetailsModal
          open={cuecModalOpen}
          cuec={selectedCuec}
          onClose={() => setCuecModalOpen(false)}
        />

        <ControlDetailsModal
          open={controlDetailsModalOpen}
          control={selectedControlDetails}
          onClose={() => setControlDetailsModalOpen(false)}
          onConvertToObjective={(control) => {
            if (!selectedScanId || !control?.id) return;
            convertControlToObjective(parseInt(selectedScanId, 10), control.id)
              .then((result) => {
                if (result?.status === 'exists') {
                  showToast('Objective exists. Control ignored and linked.', 'info');
                } else {
                  showToast('Control converted to objective', 'success');
                }
                handleObjectivesRefresh();
                handleRefreshReport();
              })
              .catch((err) => {
                console.error('Failed to convert control to objective:', err);
                showToast('Failed to convert control to objective', 'error');
              });
          }}
        />

        <FrameworkMappingDetailsModal
          open={mappingDetailsModalOpen}
          control={selectedMappingControl}
          frameworkType={selectedFrameworkType}
          frameworkCriteria={frameworkCriteria}
          onClose={() => setMappingDetailsModalOpen(false)}
          onUpdate={handleRefreshReport}
          scanId={parseInt(selectedScanId || '0')}
        />

        <ObjectivesModal
          open={objectivesModalOpen}
          onClose={handleCloseObjectivesModal}
          scanId={parseInt(selectedScanId || '0')}
          currentUser={user?.username || ''}
          onRefresh={handleObjectivesRefresh}
          showToast={showToast}
        />

        {/* Help Dialog */}
        <HelpDialog
          open={helpDialogOpen}
          onClose={() => setHelpDialogOpen(false)}
        />

        {/* Toast Notifications */}
        <Snackbar
          open={toast.open}
          autoHideDuration={2500}
          onClose={handleCloseToast}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          <Alert onClose={handleCloseToast} severity={toast.severity} variant="filled" sx={{ width: '100%' }}>
            {toast.message}
          </Alert>
        </Snackbar>
      </Box>
    </ThemeProvider>
  );
};

export default ReportPage;

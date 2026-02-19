/**
 * ReportObjectivesTab Component
 * 
 * Tab for viewing, filtering, and managing control objectives within the report view.
 * Includes bulk operations, approval workflow, conversion to controls, and gap extraction.
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Box,
  Button,
  Chip,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Checkbox,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Paper,
  IconButton,
  Tooltip,
  Typography,
  List,
  ListItem,
  ListItemText,
  Collapse,
  CircularProgress,
  Alert,
  LinearProgress,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import {
  Close as CloseIcon,
  CheckCircle as ApproveIcon,
  Cancel as RejectIcon,
  Transform as ConvertIcon,
  Refresh as RefreshIcon,
  Add as AddIcon,
  Edit as EditIcon,
  Search as SearchIcon,
  Stop as StopIcon,
  ExpandLess as ExpandLessIcon,
  ExpandMore as ExpandMoreIcon,
  ViewColumn as ViewColumnIcon,
} from '@mui/icons-material';
import { Menu, FormControlLabel, FormGroup } from '@mui/material';
import {
  getObjectives,
  approveObjective,
  rejectObjective,
  bulkApproveObjectives,
  bulkRejectObjectives,
  convertToControl,
  createObjective,
  mergeDuplicateObjectives,
  extractObjectives,
  mapObjectivesToControls,
  getObjectiveExtractionStatus,
  startObjectiveGapExtract,
  cancelObjectiveGapExtract,
  getObjectiveGapExtractStatus,
  formatConfidence,
  getConfidenceColor,
  getStatusColor,
  getStatusLabel,
  sortByConfidence,
  sortByObjectiveId,
  sortByStatus,
  updateObjective,
  type ControlObjective,
  type ObjectiveGapExtractStatus,
} from '../../../services/objectiveService';
import api from '../../../api/client';
import { SplitViewLayout } from '../SplitViewLayout';

interface ReportObjectivesTabProps {
  scanId: string | undefined;
  onRefresh?: () => void;
  showToast?: (message: string, severity?: 'success' | 'error' | 'info' | 'warning') => void;
  darkMode?: boolean;
  tocPageOffset?: number;
}

export const ReportObjectivesTab = React.memo(function ReportObjectivesTab({
  scanId,
  onRefresh,
  showToast,
  darkMode,
  tocPageOffset,
}: ReportObjectivesTabProps) {
  const scanIdNum = scanId ? parseInt(scanId) : 0;
  
  // State
  const [objectives, setObjectives] = useState<ControlObjective[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [mergeAttempted, setMergeAttempted] = useState(false);
  const [sortingField, setSortingField] = useState<'id' | 'confidence' | 'status'>('id');
  const [sortingDirection, setSortingDirection] = useState<'asc' | 'desc'>('asc');
  
  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [confidenceFilter, setConfidenceFilter] = useState<number>(0);
  const [controlCountFilter, setControlCountFilter] = useState<number>(0);
  const [searchText, setSearchText] = useState('');
  const [showLowConfidence, setShowLowConfidence] = useState(false);
  
  // Operations
  const [extracting, setExtracting] = useState(false);
  const [mapping, setMapping] = useState(false);
  const [operationMessage, setOperationMessage] = useState<string | null>(null);
  
  // PDF navigation
  const [pdfNavigateHandler, setPdfNavigateHandler] = useState<((snippet: string | null, page?: number | null) => void) | null>(null);
  const [extractStatus, setExtractStatus] = useState<{
    status: string;
    progress_status?: string;
    processed_chunks?: number;
    total_chunks?: number;
    objectives_found?: number;
    error?: string;
  } | null>(null);
  const extractPollRef = useRef<number | null>(null);

  const gapStorageKey = `objective-gap-extract-${scanIdNum}`;
  const gapSummaryHiddenKey = `objective-gap-summary-hidden-${scanIdNum}`;
  const gapLogExpandedKey = `objective-gap-log-expanded-${scanIdNum}`;
  const gapPatternExpandedKey = `objective-gap-pattern-expanded-${scanIdNum}`;
  const gapLogTtlMs = 14 * 24 * 60 * 60 * 1000;

  const loadGapStorage = () => {
    try {
      const raw = localStorage.getItem(gapStorageKey);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed;
    } catch (err) {
      console.warn('Failed to load gap extraction storage', err);
      return null;
    }
  };

  const saveGapStorage = (status: ObjectiveGapExtractStatus | null) => {
    if (!status) return;
    try {
      const payload = {
        storedAt: new Date().toISOString(),
        status,
        extractedIds: status.extracted_ids || [],
      };
      localStorage.setItem(gapStorageKey, JSON.stringify(payload));
    } catch (err) {
      console.warn('Failed to save gap extraction storage', err);
    }
  };

  const pruneGapStorageOnNewRun = () => {
    const existing = loadGapStorage();
    if (!existing?.storedAt) return;
    const storedAt = new Date(existing.storedAt).getTime();
    if (Number.isFinite(storedAt) && Date.now() - storedAt > gapLogTtlMs) {
      localStorage.removeItem(gapStorageKey);
    }
  };

  const loadGapSummaryHidden = () => {
    try {
      return sessionStorage.getItem(gapSummaryHiddenKey) === 'true';
    } catch {
      return false;
    }
  };

  const saveGapSummaryHidden = (value: boolean) => {
    try {
      sessionStorage.setItem(gapSummaryHiddenKey, value ? 'true' : 'false');
    } catch {
      // ignore
    }
  };

  const loadGapLogExpanded = () => {
    try {
      return sessionStorage.getItem(gapLogExpandedKey) === 'true';
    } catch {
      return false;
    }
  };

  const saveGapLogExpanded = (value: boolean) => {
    try {
      sessionStorage.setItem(gapLogExpandedKey, value ? 'true' : 'false');
    } catch {
      // ignore
    }
  };

  const loadGapPatternExpanded = () => {
    try {
      return sessionStorage.getItem(gapPatternExpandedKey) === 'true';
    } catch {
      return false;
    }
  };

  const saveGapPatternExpanded = (value: boolean) => {
    try {
      sessionStorage.setItem(gapPatternExpandedKey, value ? 'true' : 'false');
    } catch {
      // ignore
    }
  };

  // Create/Edit Objective
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create');
  const [editingObjectiveId, setEditingObjectiveId] = useState<number | null>(null);
  const [formObjectiveId, setFormObjectiveId] = useState('');
  const [formObjectiveText, setFormObjectiveText] = useState('');
  const [formStatus, setFormStatus] = useState<'pending' | 'approved' | 'rejected'>('pending');
  const [searchExtractText, setSearchExtractText] = useState('');
  const [searchExtractLoading, setSearchExtractLoading] = useState(false);
  const [searchExtractMessage, setSearchExtractMessage] = useState<string | null>(null);
  const [searchExtractOccurrences, setSearchExtractOccurrences] = useState<
    Array<{ index: number; char_index: number; snippet: string; match_start: number; match_end: number }>
  >([]);
  const [searchExtractPreviewTruncated, setSearchExtractPreviewTruncated] = useState(false);
  const [searchExtractApplied, setSearchExtractApplied] = useState(false);
  const [bulkConvertRunning, setBulkConvertRunning] = useState(false);
  const [bulkConvertResults, setBulkConvertResults] = useState<
    Array<{ objectiveId: number; label: string; status: 'success' | 'error' | 'warning' | 'info'; message: string }>
  >([]);
  const [gapExtractStatus, setGapExtractStatus] = useState<ObjectiveGapExtractStatus | null>(null);
  const [gapExtractRunning, setGapExtractRunning] = useState(false);
  const [gapExtractLogExpanded, setGapExtractLogExpanded] = useState(false);
  const [gapExtractPatternExpanded, setGapExtractPatternExpanded] = useState(false);
  const [gapExtractSummaryHidden, setGapExtractSummaryHidden] = useState(false);
  const [gapExtractFilterEnabled, setGapExtractFilterEnabled] = useState(false);
  const [gapExtractExtractedIds, setGapExtractExtractedIds] = useState<string[]>([]);
  const gapExtractPollRef = useRef<number | null>(null);
  
  // Confidence Details Modal
  const [confidenceDetailsOpen, setConfidenceDetailsOpen] = useState(false);
  const [selectedObjectiveForDetails, setSelectedObjectiveForDetails] = useState<ControlObjective | null>(null);
  
  // Column Visibility
  const [columnMenuAnchor, setColumnMenuAnchor] = useState<null | HTMLElement>(null);
  const [visibleColumns, setVisibleColumns] = useState({
    checkbox: true,
    id: true,
    objectiveText: true,
    lineRef: true,
    pageRefs: true,
    confidence: true,
    details: true,
    status: true,
    controls: true,
    actions: true,
  });
  
  const handleColumnMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setColumnMenuAnchor(event.currentTarget);
  };
  
  const handleColumnMenuClose = () => {
    setColumnMenuAnchor(null);
  };
  
  const toggleColumn = (column: keyof typeof visibleColumns) => {
    setVisibleColumns(prev => ({ ...prev, [column]: !prev[column] }));
  };
  
  // Load objectives
  const loadObjectives = async () => {
    console.log('[Objectives Tab] ========== LOAD OBJECTIVES CALLED ==========');
    console.trace('[Objectives Tab] Load objectives stack trace');
    setLoading(true);
    setError(null);
    try {
      // Merge now happens server-side automatically, no need to trigger from client
      const params: any = {};
      if (statusFilter !== 'all') {
        params.status = statusFilter;
      }
      if (confidenceFilter > 0) {
        params.min_confidence = confidenceFilter;
      }
      
      const data = await getObjectives(scanIdNum, params);
      console.log('[Objectives Tab] Loaded objectives:', data.length, 'objectives');
      console.log('[Objectives Tab] First objective page_refs:', data[0]?.page_refs);
      console.log('[Objectives Tab] Sample objectives with page_refs:', 
        data.slice(0, 5).map(o => ({ id: o.id, objective_id: o.objective_id, page_refs: o.page_refs }))
      );
      setObjectives(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load objectives');
      console.error('Failed to load objectives:', err);
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    if (scanId) {
      setMergeAttempted(false);
      loadObjectives();
      getObjectiveExtractionStatus(scanIdNum)
        .then((status) => setExtractStatus(status))
        .catch(() => setExtractStatus(null));

      const storedGap = loadGapStorage();
      const summaryHidden = loadGapSummaryHidden();
      const logExpanded = loadGapLogExpanded();
      const patternExpanded = loadGapPatternExpanded();
      setGapExtractSummaryHidden(summaryHidden);
      setGapExtractLogExpanded(logExpanded);
      setGapExtractPatternExpanded(patternExpanded);
      
      if (storedGap?.status) {
        setGapExtractStatus(storedGap.status as ObjectiveGapExtractStatus);
        setGapExtractExtractedIds(storedGap.extractedIds || []);
        setGapExtractRunning(storedGap.status.status === 'running');
      }

      getObjectiveGapExtractStatus(scanIdNum)
        .then((status) => {
          if (status && status.status !== 'idle') {
            setGapExtractStatus(status);
            setGapExtractExtractedIds(status.extracted_ids || []);
            setGapExtractRunning(status.status === 'running');
            saveGapStorage(status);
            if (status.status === 'running') {
              if (gapExtractPollRef.current) {
                window.clearInterval(gapExtractPollRef.current);
              }
              gapExtractPollRef.current = window.setInterval(async () => {
                try {
                  const pollStatus = await getObjectiveGapExtractStatus(scanIdNum);
                  setGapExtractStatus(pollStatus);
                  setGapExtractExtractedIds(pollStatus.extracted_ids || []);
                  setGapExtractRunning(pollStatus.status === 'running');
                  saveGapStorage(pollStatus);
                  if (pollStatus.status !== 'running') {
                    window.clearInterval(gapExtractPollRef.current || 0);
                    gapExtractPollRef.current = null;
                    await loadObjectives();
                    onRefresh?.();
                  }
                } catch (err) {
                  console.warn('Failed to poll gap extraction status', err);
                }
              }, 2000);
            }
          }
        })
        .catch(() => {
          // ignore
        });
    }
  }, [scanId, statusFilter, confidenceFilter]);

  useEffect(() => {
    return () => {
      if (extractPollRef.current) {
        window.clearInterval(extractPollRef.current);
        extractPollRef.current = null;
      }
      if (gapExtractPollRef.current) {
        window.clearInterval(gapExtractPollRef.current);
        gapExtractPollRef.current = null;
      }
    };
  }, []);
  
  // Filtered objectives - split into high and low confidence
  const CONFIDENCE_THRESHOLD = 0.70; // 70% threshold to match auto-approval
  
  const { highConfObjectives, lowConfObjectives } = useMemo(() => {
    const lower = searchText.toLowerCase();
    let list = objectives.filter((obj) => {
      if (!searchText) return true;
      return (
        obj.objective_text.toLowerCase().includes(lower) ||
        (obj.objective_id || '').toLowerCase().includes(lower)
      );
    });

    if (gapExtractFilterEnabled && gapExtractExtractedIds.length > 0) {
      const extractedSet = new Set(gapExtractExtractedIds.map((id) => id.toLowerCase()));
      list = list.filter((obj) => {
        const objId = (obj.objective_id || '').toLowerCase();
        return objId && extractedSet.has(objId);
      });
    }

    const deduped: Record<string, ControlObjective> = {};
    list.forEach((obj) => {
      const key = (obj.objective_id || obj.objective_text || '').trim().toLowerCase();
      if (!key) return;
      const current = deduped[key];
      if (!current) {
        deduped[key] = obj;
        return;
      }
      const currentConf = current.final_confidence || 0;
      const nextConf = obj.final_confidence || 0;
      const currentCount = (current as any).linked_controls_count || 0;
      const nextCount = (obj as any).linked_controls_count || 0;
      if (nextConf > currentConf || (nextConf === currentConf && nextCount > currentCount)) {
        deduped[key] = obj;
      }
    });

    list = Object.values(deduped);

    // Apply control count filter
    if (controlCountFilter > 0) {
      list = list.filter((obj) => {
        const count = (obj as any).linked_controls_count || 0;
        return count >= controlCountFilter;
      });
    }

    if (sortingField === 'id') {
      list = sortByObjectiveId(list);
    } else if (sortingField === 'status') {
      list = sortByStatus(list);
    } else {
      list = sortByConfidence(list);
    }

    if (sortingDirection === 'asc') {
      list = [...list].reverse();
    }

    // Split into high and low confidence
    // High confidence: approved OR pending with >= 70%
    // Low confidence: rejected OR pending with < 70%
    const highConf = list.filter((obj) => {
      const conf = obj.final_confidence || 0;
      // Approved objectives are always high confidence
      if (obj.status === 'approved') return true;
      // Rejected objectives are always low confidence
      if (obj.status === 'rejected') return false;
      // Pending objectives split by threshold
      return conf >= CONFIDENCE_THRESHOLD;
    });
    
    const lowConf = list.filter((obj) => {
      const conf = obj.final_confidence || 0;
      // Approved objectives are always high confidence
      if (obj.status === 'approved') return false;
      // Rejected objectives are always low confidence  
      if (obj.status === 'rejected') return true;
      // Pending objectives split by threshold
      return conf < CONFIDENCE_THRESHOLD;
    });

    return { highConfObjectives: highConf, lowConfObjectives: lowConf };
  }, [objectives, searchText, sortingField, sortingDirection, gapExtractFilterEnabled, gapExtractExtractedIds, controlCountFilter]);

  // For backward compatibility, keep filteredObjectives as combined list
  const filteredObjectives = useMemo(() => {
    return [...highConfObjectives, ...lowConfObjectives];
  }, [highConfObjectives, lowConfObjectives]);

  const handleRowClick = React.useCallback((obj: ControlObjective) => {
    console.log('[Objectives Tab] ========== CELL CLICKED ==========');
    console.log('[Objectives Tab] Full objective object:', JSON.stringify(obj, null, 2));
    console.log('[Objectives Tab] page_refs type:', typeof obj.page_refs);
    console.log('[Objectives Tab] page_refs value:', obj.page_refs);
    console.log('[Objectives Tab] page_refs isArray:', Array.isArray(obj.page_refs));
    console.log('[Objectives Tab] page_refs length:', obj.page_refs?.length);
    console.log('[Objectives Tab] pdfNavigateHandler exists:', !!pdfNavigateHandler);
    console.log('[Objectives Tab] tocPageOffset:', tocPageOffset);

    if (!pdfNavigateHandler) {
      console.warn('[Objectives Tab] pdfNavigateHandler is not available!');
      return;
    }
    
    const pageRefs = obj.page_refs;
    const hasPageRef = pageRefs && Array.isArray(pageRefs) && pageRefs.length > 0;
    
    console.log('[Objectives Tab] hasPageRef check:', hasPageRef);
    
    if (!hasPageRef) {
      console.warn('[Objectives Tab] No page refs available for this objective');
      if (showToast) {
        showToast('This objective has no page reference', 'error');
      }
      return;
    }
    
    const snippet = obj.objective_text || null;
    const offset = tocPageOffset ?? 0;
    const targetPage = pageRefs[0] + offset;
    
    console.log('[Objectives Tab] Navigating to PDF:', { 
      snippet: snippet?.substring(0, 50),
      documentPage: pageRefs[0],
      offset,
      targetPage 
    });
    
    pdfNavigateHandler(snippet, targetPage);
  }, [pdfNavigateHandler, tocPageOffset]);

  const handleOpenCreate = () => {
    setEditorMode('create');
    setEditingObjectiveId(null);
    setFormObjectiveId('');
    setFormObjectiveText('');
    setFormStatus('pending');
    setSearchExtractText('');
    setSearchExtractMessage(null);
    setSearchExtractOccurrences([]);
    setSearchExtractPreviewTruncated(false);
    setSearchExtractApplied(false);
    setEditorOpen(true);
  };

  const handleOpenEdit = (obj: ControlObjective) => {
    setEditorMode('edit');
    setEditingObjectiveId(obj.id);
    setFormObjectiveId(obj.objective_id || '');
    setFormObjectiveText(obj.objective_text || '');
    setFormStatus(obj.status || 'pending');
    setEditorOpen(true);
  };

  const handleSaveObjective = async () => {
    if (!formObjectiveText.trim()) {
      setError('Objective text is required');
      return;
    }

    try {
      if (editorMode === 'create') {
        await createObjective(scanIdNum, {
          objective_id: formObjectiveId.trim() || null,
          objective_text: formObjectiveText.trim(),
          status: formStatus,
          final_confidence: searchExtractApplied ? 1.0 : undefined,
        });
        setOperationMessage('Objective created');
      } else if (editingObjectiveId != null) {
        await updateObjective(scanIdNum, editingObjectiveId, {
          objective_id: formObjectiveId.trim() || null,
          objective_text: formObjectiveText.trim(),
          status: formStatus,
        });
        setOperationMessage('Objective updated');
      }

      setEditorOpen(false);
      await loadObjectives();
      onRefresh?.();
    } catch (err: any) {
      setError(err.message || 'Failed to save objective');
    }
  };

  const applyExtractedObjective = (extracted: any) => {
    console.log('[ReportObjectivesTab] applyExtractedObjective called with:', extracted);
    
    if (extracted.objective_id) {
      console.log('[ReportObjectivesTab] Setting objective_id:', extracted.objective_id);
      setFormObjectiveId(extracted.objective_id);
    } else {
      console.log('[ReportObjectivesTab] No objective_id in extracted data');
    }
    
    if (extracted.objective_text) {
      console.log('[ReportObjectivesTab] Setting objective_text:', extracted.objective_text);
      setFormObjectiveText(extracted.objective_text);
    } else {
      console.log('[ReportObjectivesTab] No objective_text in extracted data');
    }
    
    setSearchExtractApplied(true);
  };

  const handleSearchExtractObjective = async () => {
    const searchValue = searchExtractText.trim() || formObjectiveId.trim();
    if (!searchValue) {
      setSearchExtractMessage('Objective ID or search text is required');
      return;
    }

    setSearchExtractLoading(true);
    setSearchExtractMessage(null);
    setSearchExtractOccurrences([]);
    setSearchExtractPreviewTruncated(false);
    try {
      const response = await api.post(`/report/${scanIdNum}/extract-entity`, {
        entity_type: 'objective',
        search_text: searchValue,
        force_multi_extract: false,
      });

      const data = response.data;
      if (data.warning || data.requires_force) {
        setSearchExtractMessage(data.warning || 'Multiple matches found. Refine your search.');
        setSearchExtractOccurrences(data.occurrences || []);
        setSearchExtractPreviewTruncated(!!data.preview_truncated);
        setSearchExtractLoading(false);
        return;
      }
      if (data.error) {
        setSearchExtractMessage(data.error);
        setSearchExtractLoading(false);
        return;
      }

      const extracted = data.extracted_data || {};
      applyExtractedObjective(extracted);

      setSearchExtractMessage('Objective extracted. Review and save.');
    } catch (err: any) {
      const message = err?.response?.data?.detail || err?.message || 'Failed to extract objective';
      setSearchExtractMessage(message);
    } finally {
      setSearchExtractLoading(false);
    }
  };

  const handleExtractOccurrence = async (occurrenceIndex: number) => {
    const searchValue = searchExtractText.trim() || formObjectiveId.trim();
    if (!searchValue) {
      setSearchExtractMessage('Objective ID or search text is required');
      return;
    }

    setSearchExtractLoading(true);
    setSearchExtractMessage(null);
    try {
      const response = await api.post(`/report/${scanIdNum}/extract-entity`, {
        entity_type: 'objective',
        search_text: searchValue,
        force_multi_extract: false,
        occurrence_index: occurrenceIndex,
      });

      const data = response.data;
      if (data.error) {
        setSearchExtractMessage(data.error);
        return;
      }

      const extracted = data.extracted_data || {};
      applyExtractedObjective(extracted);
      setSearchExtractOccurrences([]);
      setSearchExtractPreviewTruncated(false);
      setSearchExtractMessage('Objective extracted. Review and save.');
    } catch (err: any) {
      const message = err?.response?.data?.detail || err?.message || 'Failed to extract objective';
      setSearchExtractMessage(message);
    } finally {
      setSearchExtractLoading(false);
    }
  };

  const renderOccurrenceSnippet = (occurrence: {
    snippet: string;
    match_start: number;
    match_end: number;
  }) => {
    const snippet = occurrence.snippet || '';
    const start = occurrence.match_start;
    const end = occurrence.match_end;
    if (Number.isFinite(start) && Number.isFinite(end) && start >= 0 && end > start) {
      return (
        <>
          {snippet.slice(0, start)}
          <mark style={{ backgroundColor: '#ffeb3b' }}>{snippet.slice(start, end)}</mark>
          {snippet.slice(end)}
        </>
      );
    }
    return snippet;
  };

  const handleConvertToControl = async (objective: ControlObjective) => {
    const result = await convertObjectiveToControl(objective);
    const severity = result.status === 'success' || result.status === 'info' ? 'success' : 
                     result.status === 'warning' ? 'warning' : 'error';
    showToast?.(result.message, severity);
    if (result.status === 'success' || result.status === 'info') {
      await loadObjectives();
      onRefresh?.();
    }
  };

  const convertObjectiveToControl = async (objective: ControlObjective) => {
    const searchValue = (objective.objective_id || '').trim() || objective.objective_text.trim();
    if (!searchValue) {
      return { status: 'warning' as const, message: 'Objective ID or text is required to convert' };
    }

    try {
      // Try to extract control details from the document
      let payload: any = {
        control_id: objective.objective_id || undefined,
        control_desc: objective.objective_text,
        control_test: '[Converted from control objective]',
        control_test_results: '',
        control_page_ref: objective.page_refs || undefined,
      };

      try {
        const response = await api.post(`/report/${scanIdNum}/extract-entity`, {
          entity_type: 'control',
          search_text: searchValue,
          force_multi_extract: false,
        });

        const data = response.data;
        // If extraction succeeds, use the extracted data
        if (!data.warning && !data.requires_force && !data.error) {
          const extracted = data.extracted_data || {};
          payload = {
            control_id: extracted.control_id || objective.objective_id || undefined,
            control_desc: extracted.description || objective.objective_text,
            control_test: Array.isArray(extracted.test_procedures)
              ? extracted.test_procedures.join('\n')
              : extracted.test_procedures || '[Converted from control objective]',
            control_test_results: Array.isArray(extracted.test_results)
              ? extracted.test_results.join('\n')
              : extracted.test_results || '',
            deviation_desc: extracted.deviation_description || undefined,
            control_page_ref: extracted.page_ref || objective.page_refs || undefined,
          };
        }
      } catch (extractErr) {
        // Extraction failed, but continue with objective data
        console.warn('Extract-entity failed, using objective data:', extractErr);
      }

      // Always attempt to convert, even if extraction failed
      const result = await convertToControl(scanIdNum, objective.id, payload);
      const action = (result as any).status || 'converted';
      const messageMap: Record<string, string> = {
        created: 'Objective converted to control',
        updated: 'Objective merged into existing control',
        exists: 'Control already exists; objective removed',
        converted: 'Objective converted to control'
      };
      const message = messageMap[action] || 'Objective converted to control';
      const status = action === 'exists' ? 'info' : 'success';
      return { status, message };
    } catch (err: any) {
      const message = err?.response?.data?.detail || err?.message || 'Failed to convert objective';
      return { status: 'error' as const, message };
    }
  };

  const handleSortRequest = (field: 'id' | 'confidence' | 'status') => {
    if (sortingField === field) {
      setSortingDirection(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortingField(field);
      setSortingDirection('desc');
    }
  };
  
  // Selection handlers
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(filteredObjectives.map((obj) => obj.id)));
    } else {
      setSelectedIds(new Set());
    }
  };
  
  const handleSelectOne = (id: number, checked: boolean) => {
    const newSelected = new Set(selectedIds);
    if (checked) {
      newSelected.add(id);
    } else {
      newSelected.delete(id);
    }
    setSelectedIds(newSelected);
  };
  
  // Action handlers
  const handleApprove = async (objectiveId: number) => {
    try {
      await approveObjective(scanIdNum, objectiveId, 'system');
      setOperationMessage('Objective approved');
      loadObjectives();
      onRefresh?.();
    } catch (err: any) {
      setError(err.message || 'Failed to approve objective');
    }
  };
  
  const handleReject = async (objectiveId: number) => {
    try {
      await rejectObjective(scanIdNum, objectiveId, 'system');
      setOperationMessage('Objective rejected');
      loadObjectives();
      onRefresh?.();
    } catch (err: any) {
      setError(err.message || 'Failed to reject objective');
    }
  };
  
  const handleBulkApprove = async () => {
    if (selectedIds.size === 0) return;
    
    try {
      await bulkApproveObjectives(scanIdNum, {
        objective_ids: Array.from(selectedIds),
      });
      setOperationMessage(`Approved ${selectedIds.size} objectives`);
      setSelectedIds(new Set());
      loadObjectives();
      onRefresh?.();
    } catch (err: any) {
      setError(err.message || 'Failed to approve objectives');
    }
  };
  
  const handleBulkReject = async () => {
    if (selectedIds.size === 0) return;
    
    try {
      await bulkRejectObjectives(scanIdNum, {
        objective_ids: Array.from(selectedIds),
      });
      setOperationMessage(`Rejected ${selectedIds.size} objectives`);
      setSelectedIds(new Set());
      loadObjectives();
      onRefresh?.();
    } catch (err: any) {
      setError(err.message || 'Failed to reject objectives');
    }
  };

  const handleBulkConvert = async () => {
    if (selectedIds.size === 0 || bulkConvertRunning) return;

    const selectedObjectives = objectives.filter((obj) => selectedIds.has(obj.id));
    if (selectedObjectives.length === 0) return;

    setBulkConvertRunning(true);
    setBulkConvertResults([]);

    const upsertResult = (objective: ControlObjective, status: 'success' | 'error' | 'warning' | 'info', message: string) => {
      const label = (objective.objective_id || objective.objective_text || '').trim();
      setBulkConvertResults((prev) => {
        const index = prev.findIndex((item) => item.objectiveId === objective.id);
        const nextEntry = {
          objectiveId: objective.id,
          label: label || `Objective ${objective.id}`,
          status,
          message,
        };
        if (index >= 0) {
          const copy = [...prev];
          copy[index] = nextEntry;
          return copy;
        }
        return [...prev, nextEntry];
      });
    };

    for (const objective of selectedObjectives) {
      upsertResult(objective, 'info', 'Converting...');
      const result = await convertObjectiveToControl(objective);
      const resultStatus = result.status === 'success' || result.status === 'error' || 
                          result.status === 'warning' || result.status === 'info' 
                          ? result.status : 'info';
      upsertResult(objective, resultStatus, result.message);
    }

    setBulkConvertRunning(false);
    setSelectedIds(new Set());
    await loadObjectives();
    onRefresh?.();
  };

  const handleStartGapExtract = async () => {
    if (gapExtractRunning) return;

    pruneGapStorageOnNewRun();
    try {
      localStorage.removeItem(gapStorageKey);
    } catch {
      // ignore
    }
    setGapExtractStatus(null);
    setGapExtractExtractedIds([]);
    setGapExtractFilterEnabled(false);
    setGapExtractLogExpanded(false);
    setGapExtractPatternExpanded(false);
    saveGapLogExpanded(false);
    saveGapPatternExpanded(false);

    try {
      setGapExtractRunning(true);
      await startObjectiveGapExtract(scanIdNum);
      const initialStatus = await getObjectiveGapExtractStatus(scanIdNum);
      setGapExtractStatus(initialStatus);
      setGapExtractExtractedIds(initialStatus.extracted_ids || []);
      saveGapStorage(initialStatus);

      if (gapExtractPollRef.current) {
        window.clearInterval(gapExtractPollRef.current);
      }
      gapExtractPollRef.current = window.setInterval(async () => {
        try {
          const pollStatus = await getObjectiveGapExtractStatus(scanIdNum);
          setGapExtractStatus(pollStatus);
          setGapExtractExtractedIds(pollStatus.extracted_ids || []);
          setGapExtractRunning(pollStatus.status === 'running');
          saveGapStorage(pollStatus);
          if (pollStatus.status !== 'running') {
            window.clearInterval(gapExtractPollRef.current || 0);
            gapExtractPollRef.current = null;
            await loadObjectives();
            onRefresh?.();
          }
        } catch (err) {
          console.warn('Failed to poll gap extraction status', err);
        }
      }, 2000);
    } catch (err: any) {
      setGapExtractRunning(false);
      showToast?.(err?.response?.data?.detail || err?.message || 'Failed to start gap extraction', 'error');
    }
  };

  const handleCancelGapExtract = async () => {
    try {
      await cancelObjectiveGapExtract(scanIdNum);
      showToast?.('Cancel requested for gap extraction', 'info');
    } catch (err: any) {
      showToast?.(err?.response?.data?.detail || err?.message || 'Failed to cancel gap extraction', 'error');
    }
  };

  const handleClearGapHighlights = () => {
    setGapExtractFilterEnabled(false);
    setGapExtractExtractedIds([]);
    setGapExtractStatus(null);
    try {
      localStorage.removeItem(gapStorageKey);
    } catch {
      // ignore
    }
  };
  
  const handleExtract = async () => {
    if (extracting) return;
    setExtracting(true);
    setError(null);
    setOperationMessage(null);
    try {
      const result = await extractObjectives(scanIdNum);
      setOperationMessage(result.message || 'Objective extraction started');

      const pollStatus = async () => {
        try {
          const status = await getObjectiveExtractionStatus(scanIdNum);
          setExtractStatus(status);

          if (status.status === 'completed') {
            setExtracting(false);
            window.clearInterval(extractPollRef.current || 0);
            extractPollRef.current = null;
            await loadObjectives();
            onRefresh?.();
          } else if (status.status === 'failed') {
            setExtracting(false);
            window.clearInterval(extractPollRef.current || 0);
            extractPollRef.current = null;
            setError(status.error || 'Objective extraction failed');
          }
        } catch (pollErr: any) {
          setError(pollErr.message || 'Failed to fetch extraction status');
        }
      };

      await pollStatus();
      extractPollRef.current = window.setInterval(pollStatus, 3000);
    } catch (err: any) {
      setError(err.message || 'Failed to extract objectives');
      setExtracting(false);
    } finally {
      // Extraction now runs async; status polling handles completion
    }
  };
  
  const handleMap = async () => {
    setMapping(true);
    setError(null);
    try {
      const result = await mapObjectivesToControls(scanIdNum);
      setOperationMessage(
        result.message || `Created ${result.mappings_created ?? 0} new mappings`
      );
      loadObjectives();
      onRefresh?.();
    } catch (err: any) {
      setError(err.message || 'Failed to map objectives');
    } finally {
      setMapping(false);
    }
  };

  const hasObjectiveIds = objectives.some((obj) => (obj.objective_id || '').trim());
  const disableActions = gapExtractRunning;
  const gapExtractedSet = useMemo(
    () => new Set(gapExtractExtractedIds.map((id) => id.toLowerCase())),
    [gapExtractExtractedIds]
  );

  const content = (
    <>
      <Typography variant="h5" gutterBottom sx={{ fontSize: 18, mb: 2 }}>
        Control Objectives
      </Typography>

      {/* Action Buttons */}
      <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <Button
          type="button"
          variant="contained"
          size="small"
          startIcon={<AddIcon />}
          onClick={handleOpenCreate}
          disabled={disableActions}
        >
          Add
        </Button>

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, borderColor: 'rgba(0, 0, 0, 0.4)' }} />

        <Button
          type="button"
          variant="outlined"
          size="small"
          startIcon={<SearchIcon />}
          onClick={handleStartGapExtract}
          disabled={!hasObjectiveIds || disableActions}
        >
          Gap Extract
        </Button>

        {gapExtractStatus && gapExtractSummaryHidden && (
          <Button
            size="small"
            variant="outlined"
            onClick={() => {
              setGapExtractSummaryHidden(false);
              saveGapSummaryHidden(false);
            }}
          >
            Show Gap Summary
          </Button>
        )}

        {gapExtractRunning && (
          <Button
            type="button"
            variant="outlined"
            size="small"
            color="warning"
            startIcon={<StopIcon />}
            onClick={handleCancelGapExtract}
          >
            Cancel
          </Button>
        )}

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, borderColor: 'rgba(0, 0, 0, 0.4)' }} />

        <Button
          type="button"
          variant="outlined"
          size="small"
          startIcon={extracting ? <CircularProgress size={16} /> : <RefreshIcon />}
          onClick={handleExtract}
          disabled={extracting || disableActions}
        >
          Extract
        </Button>

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, borderColor: 'rgba(0, 0, 0, 0.4)' }} />

        <Button
          type="button"
          variant="outlined"
          size="small"
          color="success"
          startIcon={<ApproveIcon />}
          onClick={handleBulkApprove}
          disabled={selectedIds.size === 0 || disableActions}
        >
          Approve ({selectedIds.size})
        </Button>

        <Button
          type="button"
          variant="outlined"
          size="small"
          color="error"
          startIcon={<RejectIcon />}
          onClick={handleBulkReject}
          disabled={selectedIds.size === 0 || disableActions}
        >
          Reject ({selectedIds.size})
        </Button>
        
        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, borderColor: 'rgba(0, 0, 0, 0.4)' }} />
        
        <Tooltip title="Show/Hide Columns">
          <Button
            type="button"
            variant="outlined"
            size="small"
            startIcon={<ViewColumnIcon />}
            onClick={handleColumnMenuOpen}
          >
            Columns
          </Button>
        </Tooltip>
        
        <Menu
          anchorEl={columnMenuAnchor}
          open={Boolean(columnMenuAnchor)}
          onClose={handleColumnMenuClose}
        >
          <Box sx={{ px: 2, py: 1 }}>
            <Typography variant="subtitle2" color="textSecondary" gutterBottom>
              Toggle Columns
            </Typography>
            <FormGroup>
              <FormControlLabel
                control={<Checkbox size="small" checked={visibleColumns.id} onChange={() => toggleColumn('id')} />}
                label="ID"
              />
              <FormControlLabel
                control={<Checkbox size="small" checked={visibleColumns.objectiveText} onChange={() => toggleColumn('objectiveText')} />}
                label="Objective Text"
              />
              <FormControlLabel
                control={<Checkbox size="small" checked={visibleColumns.lineRef} onChange={() => toggleColumn('lineRef')} />}
                label="Line Ref"
              />
              <FormControlLabel
                control={<Checkbox size="small" checked={visibleColumns.pageRefs} onChange={() => toggleColumn('pageRefs')} />}
                label="Page Refs"
              />
              <FormControlLabel
                control={<Checkbox size="small" checked={visibleColumns.confidence} onChange={() => toggleColumn('confidence')} />}
                label="Confidence"
              />
              <FormControlLabel
                control={<Checkbox size="small" checked={visibleColumns.details} onChange={() => toggleColumn('details')} />}
                label="Details"
              />
              <FormControlLabel
                control={<Checkbox size="small" checked={visibleColumns.status} onChange={() => toggleColumn('status')} />}
                label="Status"
              />
              <FormControlLabel
                control={<Checkbox size="small" checked={visibleColumns.controls} onChange={() => toggleColumn('controls')} />}
                label="Controls"
              />
            </FormGroup>
          </Box>
        </Menu>

        <Button
          type="button"
          variant="outlined"
          size="small"
          color="primary"
          startIcon={<ConvertIcon />}
          onClick={handleBulkConvert}
          disabled={selectedIds.size === 0 || bulkConvertRunning || disableActions}
        >
          Convert ({selectedIds.size})
        </Button>

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, borderColor: 'rgba(0, 0, 0, 0.4)' }} />
        
        <Button
          type="button"
          variant="outlined"
          size="small"
          startIcon={mapping ? <CircularProgress size={16} /> : <RefreshIcon />}
          onClick={handleMap}
          disabled={mapping || disableActions}
        >
          Map
        </Button>
        
        <IconButton onClick={loadObjectives} size="small" disabled={loading || disableActions}>
          {loading ? <CircularProgress size={20} /> : <RefreshIcon />}
        </IconButton>
      </Box>

      {/* Gap Extract Summary Section (collapsible, default collapsed, remember state) */}
      {gapExtractStatus && !gapExtractSummaryHidden && (
        <Box sx={{ mb: 2, p: 1, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
            <Typography variant="subtitle2">
              Gap Extraction: {gapExtractStatus.status}
            </Typography>
            <Typography variant="caption" color="textSecondary">
              Total Probed: {gapExtractStatus.total_probed ?? 0}
            </Typography>
            <Typography variant="caption" color="textSecondary">
              Found: {gapExtractStatus.total_found ?? 0}
            </Typography>
            <Typography variant="caption" color="textSecondary">
              Extracted: {gapExtractStatus.total_extracted ?? 0}
            </Typography>
            <Typography variant="caption" color="textSecondary">
              Elapsed: {gapExtractStatus.duration_seconds ?? 0}s
            </Typography>
            <Box sx={{ flexGrow: 1 }} />
            <Button
              size="small"
              onClick={() => {
                setGapExtractSummaryHidden(true);
                saveGapSummaryHidden(true);
              }}
            >
              Hide
            </Button>
            <Button size="small" onClick={handleClearGapHighlights}>
              Clear highlights/logs
            </Button>
          </Box>
          {gapExtractStatus.progress_status && (
            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 0.5 }}>
              {gapExtractStatus.progress_status}
            </Typography>
          )}
          {gapExtractStatus.error && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {gapExtractStatus.error}
            </Alert>
          )}

          <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Button 
              size="small" 
              onClick={() => {
                const newValue = !gapExtractLogExpanded;
                setGapExtractLogExpanded(newValue);
                saveGapLogExpanded(newValue);
              }}
            >
              {gapExtractLogExpanded ? 'Hide log' : 'Show log'}
            </Button>
            <Button 
              size="small" 
              onClick={() => {
                const newValue = !gapExtractPatternExpanded;
                setGapExtractPatternExpanded(newValue);
                saveGapPatternExpanded(newValue);
              }}
            >
              {gapExtractPatternExpanded ? 'Hide pattern output' : 'Show pattern output'}
            </Button>
          </Box>

          <Collapse in={gapExtractLogExpanded}>
            <Box sx={{ mt: 1 }}>
              <List dense>
                {(gapExtractStatus.log || []).map((entry, idx) => (
                  <ListItem key={`${entry.timestamp}-${idx}`} sx={{ px: 0 }}>
                    <Chip
                      size="small"
                      label={entry.status}
                      color={
                        entry.status === 'Extracted'
                          ? 'success'
                          : entry.status === 'Not Found'
                          ? 'warning'
                          : entry.status === 'Failed'
                          ? 'error'
                          : entry.status === 'Cancelled'
                          ? 'warning'
                          : 'info'
                      }
                      sx={{ mr: 1 }}
                    />
                    <ListItemText
                      primary={entry.objective_id}
                      secondary={entry.extracted_id ? `${entry.message} → ${entry.extracted_id}` : entry.message}
                    />
                  </ListItem>
                ))}
              </List>
            </Box>
          </Collapse>

          <Collapse in={gapExtractPatternExpanded}>
            <Box sx={{ mt: 1, p: 1, bgcolor: '#fafafa', borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" color="textSecondary">
                GPT Pattern Output
              </Typography>
              <Typography component="pre" sx={{ whiteSpace: 'pre-wrap', fontSize: '0.75rem', mt: 0.5 }}>
                {gapExtractStatus.pattern_output
                  ? JSON.stringify(gapExtractStatus.pattern_output, null, 2)
                  : 'No pattern output available.'}
              </Typography>
            </Box>
          </Collapse>
        </Box>
      )}

      {/* Bulk Convert Results */}
      {bulkConvertResults.length > 0 && (
        <Collapse in={bulkConvertResults.length > 0}>
          <Box sx={{ mb: 2, p: 1, bgcolor: '#f5f5f5', borderRadius: 1 }}>
            <Typography variant="caption" color="textSecondary">
              Bulk conversion results
            </Typography>
            <List dense>
              {bulkConvertResults.map((result) => (
                <ListItem key={result.objectiveId} sx={{ px: 0 }}>
                  <Chip
                    size="small"
                    label={result.status}
                    color={
                      result.status === 'success'
                        ? 'success'
                        : result.status === 'warning'
                        ? 'warning'
                        : result.status === 'error'
                        ? 'error'
                        : 'info'
                    }
                    sx={{ mr: 1 }}
                  />
                  <ListItemText
                    primary={result.label}
                    secondary={result.message}
                  />
                </ListItem>
              ))}
            </List>
          </Box>
        </Collapse>
      )}

      {/* Extraction Progress */}
      {extractStatus && extractStatus.status !== 'idle' && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ mb: 0.5 }}>
            {extractStatus.progress_status || `Objective extraction ${extractStatus.status}`}
          </Typography>
          {typeof extractStatus.processed_chunks === 'number' && typeof extractStatus.total_chunks === 'number' && extractStatus.total_chunks > 0 && (
            <>
              <LinearProgress
                variant="determinate"
                value={Math.min(100, (extractStatus.processed_chunks / extractStatus.total_chunks) * 100)}
                sx={{ mb: 0.5 }}
              />
              <Typography variant="caption" color="textSecondary">
                {extractStatus.processed_chunks}/{extractStatus.total_chunks} chunks · {extractStatus.objectives_found ?? 0} objectives found
              </Typography>
            </>
          )}
        </Box>
      )}

      {/* Filters */}
      <Box sx={{ mb: 2, display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField
          label="Search"
          variant="outlined"
          size="small"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          sx={{ minWidth: 180 }}
        />
        
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Status</InputLabel>
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} label="Status">
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="pending">Pending</MenuItem>
            <MenuItem value="approved">Approved</MenuItem>
            <MenuItem value="rejected">Rejected</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Min Confidence</InputLabel>
          <Select
            value={confidenceFilter}
            onChange={(e) => setConfidenceFilter(Number(e.target.value))}
            label="Min Confidence"
          >
            <MenuItem value={0}>All</MenuItem>
            <MenuItem value={0.8}>High (&gt;= 80%)</MenuItem>
            <MenuItem value={0.6}>Medium (&gt;= 60%)</MenuItem>
            <MenuItem value={0.4}>Low (&gt;= 40%)</MenuItem>
          </Select>
        </FormControl>
        
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Min Control Count</InputLabel>
          <Select
            value={controlCountFilter}
            onChange={(e) => setControlCountFilter(Number(e.target.value))}
            label="Min Control Count"
          >
            <MenuItem value={0}>All</MenuItem>
            <MenuItem value={1}>1+</MenuItem>
            <MenuItem value={2}>2+</MenuItem>
            <MenuItem value={3}>3+</MenuItem>
            <MenuItem value={5}>5+</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {/* High Confidence Table */}
      <Box className="sticky-table-container">
        <TableContainer component={Paper} sx={{ fontSize: 10, p: 0, m: 0, mb: 1, overflowX: 'auto', maxHeight: '100%' }} className="content-text">
          <Table stickyHeader size="small" className="table-compact" sx={{ fontSize: 10, borderCollapse: 'collapse', tableLayout: 'fixed', width: '100%' }}>
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 50 }}>
                  <Checkbox
                    size="small"
                    checked={selectedIds.size === highConfObjectives.length && highConfObjectives.length > 0}
                    indeterminate={selectedIds.size > 0 && selectedIds.size < highConfObjectives.length}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedIds(new Set(highConfObjectives.map((obj) => obj.id)));
                      } else {
                        setSelectedIds(new Set());
                      }
                    }}
                  />
                </TableCell>
                <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 120 }}>
                  <TableSortLabel
                    active={sortingField === 'id'}
                    direction={sortingField === 'id' ? sortingDirection : 'asc'}
                    onClick={() => handleSortRequest('id')}
                  >
                    ID
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', minWidth: 300 }}>Objective Text</TableCell>
                <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 80 }}>Line Ref</TableCell>
                <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 80 }}>Page Refs</TableCell>
                <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 100 }}>
                  <TableSortLabel
                    active={sortingField === 'confidence'}
                    direction={sortingField === 'confidence' ? sortingDirection : 'asc'}
                    onClick={() => handleSortRequest('confidence')}
                  >
                    Confidence
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 100 }}>
                  <TableSortLabel
                    active={sortingField === 'status'}
                    direction={sortingField === 'status' ? sortingDirection : 'asc'}
                    onClick={() => handleSortRequest('status')}
                  >
                    Status
                  </TableSortLabel>
                </TableCell>
                <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 80 }}>Controls</TableCell>
                <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 180 }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={9} align="center" sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                    <CircularProgress size={20} />
                  </TableCell>
                </TableRow>
              ) : highConfObjectives.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} align="center" sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                    <Typography variant="body2" color="textSecondary" sx={{ fontSize: 10 }}>
                      No high confidence objectives found. Click "Extract" to begin.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                highConfObjectives.map((obj) => (
                  <TableRow
                    key={obj.id}
                    hover
                    sx={
                      obj.objective_id && gapExtractedSet.has(obj.objective_id.toLowerCase())
                        ? { backgroundColor: '#fff8e1' }
                        : undefined
                    }
                  >
                    {visibleColumns.checkbox && (
                      <TableCell padding="checkbox" sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                        <Checkbox
                          size="small"
                          checked={selectedIds.has(obj.id)}
                          onChange={(e) => handleSelectOne(obj.id, e.target.checked)}
                        />
                      </TableCell>
                    )}
                    {visibleColumns.id && (
                      <TableCell
                        sx={{ 
                          fontSize: 10,
                          p: 0.5,
                          border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`,
                          cursor: obj.objective_text ? 'pointer' : 'default',
                          '&:hover': obj.objective_text ? { bgcolor: darkMode ? '#424242' : '#f5f5f5' } : {} 
                        }}
                        onClick={(e) => { e.stopPropagation(); handleRowClick(obj); }}
                      >
                        {obj.objective_id_normalized || obj.objective_id || '—'}
                      </TableCell>
                    )}
                    {visibleColumns.objectiveText && (
                      <TableCell
                        sx={{ 
                          fontSize: 10,
                          p: 0.5,
                          border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`,
                          cursor: obj.objective_text ? 'pointer' : 'default',
                          '&:hover': obj.objective_text ? { bgcolor: darkMode ? '#424242' : '#f5f5f5' } : {} 
                        }}
                        onClick={(e) => { e.stopPropagation(); handleRowClick(obj); }}
                      >
                        <Typography 
                          variant="body2" 
                          sx={{ 
                            fontSize: 10,
                            cursor: obj.objective_text ? 'pointer' : 'default' 
                          }}
                        >
                          {obj.objective_text}
                        </Typography>
                      </TableCell>
                    )}
                    {visibleColumns.lineRef && (
                      <TableCell
                        sx={{ 
                          fontSize: 10,
                          p: 0.5,
                          border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`,
                          cursor: obj.line_ref ? 'pointer' : 'default',
                          '&:hover': obj.line_ref ? { bgcolor: darkMode ? '#424242' : '#f5f5f5' } : {},
                          textAlign: 'center'
                        }}
                        onClick={(e) => { e.stopPropagation(); if (obj.line_ref) handleRowClick(obj); }}
                      >
                        {obj.line_ref ?? '—'}
                      </TableCell>
                    )}
                    {visibleColumns.pageRefs && (
                      <TableCell
                        sx={{ 
                          fontSize: 10,
                          p: 0.5,
                          border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`,
                          cursor: (obj.page_refs && Array.isArray(obj.page_refs) && obj.page_refs.length > 0) ? 'pointer' : 'default',
                          '&:hover': (obj.page_refs && Array.isArray(obj.page_refs) && obj.page_refs.length > 0) ? { bgcolor: darkMode ? '#424242' : '#f5f5f5' } : {},
                          textAlign: 'center'
                        }}
                        onClick={(e) => { 
                          e.stopPropagation(); 
                          if (obj.page_refs && Array.isArray(obj.page_refs) && obj.page_refs.length > 0) {
                            handleRowClick(obj);
                          }
                        }}
                      >
                        {obj.page_refs && Array.isArray(obj.page_refs) && obj.page_refs.length > 0 
                          ? obj.page_refs.join(', ') 
                          : '—'}
                      </TableCell>
                    )}
                    {visibleColumns.confidence && (
                      <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                        <Chip
                          label={formatConfidence(obj.final_confidence)}
                          size="small"
                          sx={{
                            fontSize: 9,
                            height: 20,
                            bgcolor: getConfidenceColor(obj.final_confidence),
                            color: 'white',
                            fontWeight: 'bold',
                          }}
                        />
                      </TableCell>
                    )}
                    {visibleColumns.details && (
                      <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, textAlign: 'center' }}>
                        <Tooltip title="View confidence breakdown">
                          <IconButton
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedObjectiveForDetails(obj);
                              setConfidenceDetailsOpen(true);
                            }}
                            sx={{ p: 0.25 }}
                          >
                            <SearchIcon sx={{ fontSize: 14 }} />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    )}
                    {visibleColumns.status && (
                      <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                        <Chip
                          label={getStatusLabel(obj.status)}
                          size="small"
                          sx={{
                            fontSize: 9,
                            height: 20,
                            bgcolor: getStatusColor(obj.status),
                            color: 'white',
                          }}
                        />
                      </TableCell>
                    )}
                    {visibleColumns.controls && (
                      <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                        <Chip
                          label={(obj as any).linked_controls_count || 0}
                          size="small"
                          variant="outlined"
                          sx={{
                            fontSize: 9,
                            height: 20,
                          }}
                        />
                      </TableCell>
                    )}
                    {visibleColumns.actions && (
                      <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                        <Box sx={{ display: 'flex', gap: 0.5 }}>
                          <Tooltip title="Edit">
                            <IconButton
                              size="small"
                              color="primary"
                              onClick={() => handleOpenEdit(obj)}
                              sx={{ p: 0.25 }}
                            >
                              <EditIcon sx={{ fontSize: 16 }} />
                            </IconButton>
                          </Tooltip>
                          {obj.status !== 'approved' && (
                            <Tooltip title="Approve">
                              <IconButton
                                size="small"
                                color="success"
                                onClick={() => handleApprove(obj.id)}
                                sx={{ p: 0.25 }}
                              >
                                <ApproveIcon sx={{ fontSize: 16 }} />
                              </IconButton>
                            </Tooltip>
                        )}
                        {obj.status !== 'rejected' && (
                          <Tooltip title="Reject">
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => handleReject(obj.id)}
                              sx={{ p: 0.25 }}
                            >
                              <RejectIcon sx={{ fontSize: 16 }} />
                            </IconButton>
                          </Tooltip>
                        )}
                        <Tooltip title="Convert to Control">
                          <IconButton
                            size="small"
                            color="primary"
                            onClick={() => handleConvertToControl(obj)}
                            sx={{ p: 0.25 }}
                          >
                            <ConvertIcon sx={{ fontSize: 16 }} />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>

      {/* Low Confidence Section (Collapsible) */}
      {lowConfObjectives.length > 0 && (
        <>
          <Box sx={{ p: 1, ml: 3 }}>
            <Button size="small" onClick={() => setShowLowConfidence(!showLowConfidence)}>
              {showLowConfidence ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              {' '}
              Show Low Confidence ({lowConfObjectives.length})
            </Button>
          </Box>

          <Collapse in={showLowConfidence}>
            <Box className="sticky-table-container" sx={{ ml: 3 }}>
              <TableContainer component={Paper} sx={{ fontSize: 10, p: 0, m: 0, mb: 1, overflowX: 'auto', maxHeight: '100%' }} className="content-text">
                <Table stickyHeader size="small" className="table-compact" sx={{ fontSize: 10, borderCollapse: 'collapse', tableLayout: 'fixed', width: '100%' }}>
                  <TableHead>
                    <TableRow>
                      {visibleColumns.checkbox && (
                        <TableCell padding="checkbox" sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 50 }}>
                          <Checkbox
                            size="small"
                            checked={selectedIds.size > 0 && lowConfObjectives.every(obj => selectedIds.has(obj.id))}
                            indeterminate={lowConfObjectives.some(obj => selectedIds.has(obj.id)) && !lowConfObjectives.every(obj => selectedIds.has(obj.id))}
                            onChange={(e) => {
                              const newSelected = new Set(selectedIds);
                              if (e.target.checked) {
                                lowConfObjectives.forEach(obj => newSelected.add(obj.id));
                              } else {
                                lowConfObjectives.forEach(obj => newSelected.delete(obj.id));
                              }
                              setSelectedIds(newSelected);
                            }}
                          />
                        </TableCell>
                      )}
                      {visibleColumns.id && <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 120 }}>ID</TableCell>}
                      {visibleColumns.objectiveText && <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', minWidth: 300 }}>Objective Text</TableCell>}
                      {visibleColumns.lineRef && <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 80 }}>Line Ref</TableCell>}
                      {visibleColumns.pageRefs && <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 80 }}>Page Refs</TableCell>}
                      {visibleColumns.confidence && <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 100 }}>Confidence</TableCell>}
                      {visibleColumns.details && <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 80 }}>Details</TableCell>}
                      {visibleColumns.status && <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 100 }}>Status</TableCell>}
                      {visibleColumns.controls && <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 80 }}>Controls</TableCell>}
                      {visibleColumns.actions && <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, background: darkMode ? '#424242' : '#f7f7f7', width: 180 }}>Actions</TableCell>}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {lowConfObjectives.map((obj) => (
                      <TableRow
                        key={`low-${obj.id}`}
                        hover
                        sx={{
                          fontSize: 10,
                        }}
                      >
                        {visibleColumns.checkbox && (
                          <TableCell padding="checkbox" sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                            <Checkbox
                              size="small"
                              checked={selectedIds.has(obj.id)}
                              onChange={(e) => {
                                e.stopPropagation();
                                const newSelected = new Set(selectedIds);
                                if (e.target.checked) {
                                  newSelected.add(obj.id);
                                } else {
                                  newSelected.delete(obj.id);
                                }
                                setSelectedIds(newSelected);
                              }}
                            />
                          </TableCell>
                        )}
                        {visibleColumns.id && (
                          <TableCell 
                            sx={{ 
                              fontSize: 10, 
                              p: 0.5, 
                              border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`,
                              cursor: obj.objective_text ? 'pointer' : 'default',
                              '&:hover': obj.objective_text ? { bgcolor: darkMode ? '#424242' : '#f5f5f5' } : {}
                            }}
                            onClick={(e) => { e.stopPropagation(); handleRowClick(obj); }}
                          >
                            {obj.objective_id || 'N/A'}
                          </TableCell>
                        )}
                        {visibleColumns.objectiveText && (
                          <TableCell 
                            sx={{ 
                              fontSize: 10, 
                              p: 0.5, 
                              border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`,
                              cursor: obj.objective_text ? 'pointer' : 'default',
                              '&:hover': obj.objective_text ? { bgcolor: darkMode ? '#424242' : '#f5f5f5' } : {}
                            }}
                            onClick={(e) => { e.stopPropagation(); handleRowClick(obj); }}
                          >
                            <Typography 
                              variant="body2" 
                              sx={{ 
                                fontSize: 10,
                                cursor: obj.objective_text ? 'pointer' : 'default'
                              }}
                            >
                              {obj.objective_text?.length > 150 ? `${obj.objective_text.slice(0, 150)}...` : obj.objective_text}
                            </Typography>
                          </TableCell>
                        )}
                        {visibleColumns.lineRef && (
                          <TableCell
                            sx={{ 
                              fontSize: 10,
                              p: 0.5,
                              border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`,
                              cursor: obj.line_ref ? 'pointer' : 'default',
                              '&:hover': obj.line_ref ? { bgcolor: darkMode ? '#424242' : '#f5f5f5' } : {},
                              textAlign: 'center'
                            }}
                            onClick={(e) => { e.stopPropagation(); if (obj.line_ref) handleRowClick(obj); }}
                          >
                            {obj.line_ref ?? '—'}
                          </TableCell>
                        )}
                        {visibleColumns.pageRefs && (
                          <TableCell
                            sx={{ 
                              fontSize: 10,
                              p: 0.5,
                              border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`,
                              cursor: (obj.page_refs && Array.isArray(obj.page_refs) && obj.page_refs.length > 0) ? 'pointer' : 'default',
                              '&:hover': (obj.page_refs && Array.isArray(obj.page_refs) && obj.page_refs.length > 0) ? { bgcolor: darkMode ? '#424242' : '#f5f5f5' } : {},
                              textAlign: 'center'
                            }}
                            onClick={(e) => { 
                              e.stopPropagation(); 
                              if (obj.page_refs && Array.isArray(obj.page_refs) && obj.page_refs.length > 0) {
                                handleRowClick(obj);
                              }
                            }}
                          >
                            {obj.page_refs && Array.isArray(obj.page_refs) && obj.page_refs.length > 0 
                              ? obj.page_refs.join(', ') 
                              : '—'}
                          </TableCell>
                        )}
                        {visibleColumns.confidence && (
                          <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                            <Chip
                              label={formatConfidence(obj.final_confidence)}
                              size="small"
                              sx={{
                                bgcolor: getConfidenceColor(obj.final_confidence),
                                color: 'white',
                                fontWeight: 'bold',
                                fontSize: 9,
                                height: 20,
                              }}
                            />
                          </TableCell>
                        )}
                        {visibleColumns.details && (
                          <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}`, textAlign: 'center' }}>
                            <Tooltip title="View confidence breakdown">
                              <IconButton
                                size="small"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedObjectiveForDetails(obj);
                                  setConfidenceDetailsOpen(true);
                                }}
                                sx={{ p: 0.25 }}
                              >
                                <SearchIcon sx={{ fontSize: 14 }} />
                              </IconButton>
                            </Tooltip>
                          </TableCell>
                        )}
                        {visibleColumns.status && (
                          <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                            <Chip
                              label={getStatusLabel(obj.status)}
                              size="small"
                              sx={{
                                bgcolor: getStatusColor(obj.status),
                                color: 'white',
                                fontSize: 9,
                                height: 20,
                              }}
                            />
                          </TableCell>
                        )}
                        {visibleColumns.controls && (
                          <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                            <Chip
                              label={(obj as any).linked_controls_count || 0}
                              size="small"
                              variant="outlined"
                              sx={{
                                fontSize: 9,
                                height: 20,
                              }}
                            />
                          </TableCell>
                        )}
                        {visibleColumns.actions && (
                          <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${darkMode ? '#424242' : '#e0e0e0'}` }}>
                            <Box sx={{ display: 'flex', gap: 0.5 }}>
                              <Tooltip title="Edit">
                                <IconButton
                                  size="small"
                                  color="primary"
                                  onClick={(e) => { e.stopPropagation(); handleOpenEdit(obj); }}
                                  sx={{ p: 0.25 }}
                                >
                                  <EditIcon sx={{ fontSize: 16 }} />
                                </IconButton>
                              </Tooltip>
                              {obj.status !== 'approved' && (
                                <Tooltip title="Approve">
                                  <IconButton
                                    size="small"
                                    color="success"
                                    onClick={(e) => { e.stopPropagation(); handleApprove(obj.id); }}
                                    sx={{ p: 0.25 }}
                                  >
                                    <ApproveIcon sx={{ fontSize: 16 }} />
                                  </IconButton>
                                </Tooltip>
                              )}
                              {obj.status !== 'rejected' && (
                                <Tooltip title="Reject">
                                  <IconButton
                                    size="small"
                                    color="error"
                                    onClick={(e) => { e.stopPropagation(); handleReject(obj.id); }}
                                    sx={{ p: 0.25 }}
                                  >
                                    <RejectIcon sx={{ fontSize: 16 }} />
                                  </IconButton>
                                </Tooltip>
                            )}
                            <Tooltip title="Convert to Control">
                              <IconButton
                                size="small"
                                color="primary"
                                onClick={(e) => { e.stopPropagation(); handleConvertToControl(obj); }}
                                sx={{ p: 0.25 }}
                              >
                                <ConvertIcon sx={{ fontSize: 16 }} />
                              </IconButton>
                            </Tooltip>
                          </Box>
                        </TableCell>
                        )}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          </Collapse>
        </>
      )}

      <Typography sx={{ fontStyle: "italic", fontSize: 11, mt: 1 }}>
        Confidence: High confidence (≥ 70%) and approved objectives shown by default. 
        Low confidence items (including rejected objectives with 0% confidence) available in "Show Low Confidence" section.
      </Typography>

      {/* Loading/Error messages */}
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
      {operationMessage && (
        <Alert severity="success" onClose={() => setOperationMessage(null)} sx={{ mt: 2 }}>
          {operationMessage}
        </Alert>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={editorOpen} onClose={() => setEditorOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editorMode === 'create' ? 'Add Control Objective' : 'Edit Control Objective'}
        </DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField
              label="Objective ID (optional)"
              value={formObjectiveId}
              onChange={(e) => setFormObjectiveId(e.target.value)}
              fullWidth
            />
            <TextField
              label="Objective Text"
              value={formObjectiveText}
              onChange={(e) => setFormObjectiveText(e.target.value)}
              fullWidth
              multiline
              minRows={3}
            />
            {editorMode === 'create' && (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <TextField
                  label="Search & Extract"
                  placeholder="Enter objective ID or text to search"
                  value={searchExtractText}
                  onChange={(e) => setSearchExtractText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !searchExtractLoading) {
                      e.preventDefault();
                      handleSearchExtractObjective();
                    }
                  }}
                  fullWidth
                />
                <Button
                  variant="outlined"
                  onClick={handleSearchExtractObjective}
                  disabled={searchExtractLoading}
                >
                  {searchExtractLoading ? <CircularProgress size={16} /> : 'Search & Extract'}
                </Button>
                {searchExtractMessage && (
                  <Alert severity="info">{searchExtractMessage}</Alert>
                )}
                {searchExtractOccurrences.length > 0 && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="subtitle2">Multiple matches found. Select one:</Typography>
                    {searchExtractPreviewTruncated && (
                      <Typography variant="caption" color="text.secondary">
                        Showing first {searchExtractOccurrences.length} matches.
                      </Typography>
                    )}
                    <List dense sx={{ mt: 1 }}>
                      {searchExtractOccurrences.map((occurrence) => (
                        <ListItem
                          key={occurrence.index}
                          alignItems="flex-start"
                          sx={{
                            display: 'block',
                            border: '1px solid',
                            borderColor: 'divider',
                            borderRadius: 1,
                            mb: 1,
                            p: 1,
                          }}
                        >
                          <ListItemText
                            primary={`Occurrence ${occurrence.index + 1}`}
                            secondary={
                              <Typography component="span" variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                                {renderOccurrenceSnippet(occurrence)}
                              </Typography>
                            }
                          />
                          <Box sx={{ mt: 1 }}>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => handleExtractOccurrence(occurrence.index)}
                              disabled={searchExtractLoading}
                            >
                              Extract this
                            </Button>
                          </Box>
                        </ListItem>
                      ))}
                    </List>
                  </Box>
                )}
              </Box>
            )}
            <FormControl fullWidth size="small">
              <InputLabel>Status</InputLabel>
              <Select
                value={formStatus}
                onChange={(e) => setFormStatus(e.target.value as any)}
                label="Status"
              >
                <MenuItem value="pending">Pending</MenuItem>
                <MenuItem value="approved">Approved</MenuItem>
                <MenuItem value="rejected">Rejected</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditorOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleSaveObjective}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      {/* Confidence Details Modal */}
      <Dialog
        open={confidenceDetailsOpen}
        onClose={() => setConfidenceDetailsOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Confidence Score Breakdown</span>
            <IconButton size="small" onClick={() => setConfidenceDetailsOpen(false)}>
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent dividers>
          {selectedObjectiveForDetails && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {/* Objective Info */}
              <Box>
                <Typography variant="subtitle2" color="textSecondary">Objective</Typography>
                <Typography variant="body2"><strong>ID:</strong> {selectedObjectiveForDetails.objective_id || 'N/A'}</Typography>
                <Typography variant="body2" sx={{ mt: 1 }}>
                  {selectedObjectiveForDetails.objective_text}
                </Typography>
              </Box>

              <Divider />

              {/* Final Confidence */}
              <Box>
                <Typography variant="subtitle2" color="textSecondary">Final Confidence</Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mt: 1 }}>
                  <Chip
                    label={formatConfidence(selectedObjectiveForDetails.final_confidence)}
                    size="medium"
                    sx={{
                      bgcolor: getConfidenceColor(selectedObjectiveForDetails.final_confidence),
                      color: 'white',
                      fontWeight: 'bold',
                      fontSize: 14,
                    }}
                  />
                  {selectedObjectiveForDetails.confidence_calc && (
                    <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>
                      {selectedObjectiveForDetails.confidence_calc}
                    </Typography>
                  )}
                </Box>
              </Box>

              {/* Factor Scores */}
              {selectedObjectiveForDetails.confidence_metadata?.factor_scores && (
                <>
                  <Divider />
                  <Box>
                    <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                      Individual Factor Scores
                    </Typography>
                    <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
                      {Object.entries(selectedObjectiveForDetails.confidence_metadata.factor_scores).map(([key, value]) => (
                        <Box key={key} sx={{ p: 1, border: '1px solid #e0e0e0', borderRadius: 1 }}>
                          <Typography variant="caption" color="textSecondary">
                            {key.replace('_confidence', '').replace('_', ' ').toUpperCase()}
                          </Typography>
                          <Typography variant="body2" fontWeight="bold">
                            {(value * 100).toFixed(1)}%
                          </Typography>
                        </Box>
                      ))}
                    </Box>
                  </Box>
                </>
              )}

              {/* Weighted Contributions */}
              {selectedObjectiveForDetails.confidence_metadata?.weighted_contributions && (
                <>
                  <Divider />
                  <Box>
                    <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                      Weighted Contributions
                    </Typography>
                    <TableContainer component={Paper} variant="outlined">
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Factor</TableCell>
                            <TableCell align="right">Score</TableCell>
                            <TableCell align="right">Weight</TableCell>
                            <TableCell align="right">Contribution</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {Object.entries(selectedObjectiveForDetails.confidence_metadata.weighted_contributions).map(([key, contribution]) => {
                            const factorName = key.replace('_contribution', '');
                            const score = selectedObjectiveForDetails.confidence_metadata?.factor_scores?.[factorName + '_confidence'] ?? 0;
                            const weight = selectedObjectiveForDetails.confidence_metadata?.weights_used?.[
                              factorName === 'gpt' ? 'gpt_opinion' : factorName
                            ] ?? 0;
                            return (
                              <TableRow key={key}>
                                <TableCell>{factorName.replace('_', ' ').toUpperCase()}</TableCell>
                                <TableCell align="right">{(score * 100).toFixed(1)}%</TableCell>
                                <TableCell align="right">{(weight * 100).toFixed(0)}%</TableCell>
                                <TableCell align="right" sx={{ fontWeight: 'bold' }}>
                                  {(contribution * 100).toFixed(2)}%
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </Box>
                </>
              )}

              {/* ID Penalties & Adjustments */}
              {selectedObjectiveForDetails.confidence_metadata?.adjustments && 
               selectedObjectiveForDetails.confidence_metadata.adjustments.length > 0 && (
                <>
                  <Divider />
                  <Box>
                    <Typography variant="subtitle2" color="error" gutterBottom>
                      Penalties Applied
                    </Typography>
                    {selectedObjectiveForDetails.confidence_metadata.adjustments.map((adjustment, idx) => (
                      <Alert key={idx} severity="warning" sx={{ mb: 1 }}>
                        <Typography variant="body2">
                          <strong>{adjustment.type.replace(/_/g, ' ').toUpperCase()}:</strong> -{(adjustment.penalty_multiplier * 100).toFixed(0)}% penalty
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {adjustment.reason}
                        </Typography>
                        <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 0.5 }}>
                          Applied: {new Date(adjustment.applied_at).toLocaleString()}
                        </Typography>
                      </Alert>
                    ))}
                  </Box>
                </>
              )}

              {/* GPT Reasoning */}
              {selectedObjectiveForDetails.gpt_reasoning && (
                <>
                  <Divider />
                  <Box>
                    <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                      GPT Reasoning
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'grey.50' }}>
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                        {selectedObjectiveForDetails.gpt_reasoning}
                      </Typography>
                    </Paper>
                  </Box>
                </>
              )}

              {/* Metadata Timestamp */}
              {selectedObjectiveForDetails.confidence_metadata?.calculated_at && (
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="caption" color="text.secondary">
                    Calculated: {new Date(selectedObjectiveForDetails.confidence_metadata.calculated_at).toLocaleString()}
                  </Typography>
                </Box>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfidenceDetailsOpen(false)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );

  return (
    <SplitViewLayout
      scanId={scanIdNum}
      tabName="objectives"
      onPdfNavigate={(handler) => setPdfNavigateHandler(() => handler)}
    >
      {content}
    </SplitViewLayout>
  );
});

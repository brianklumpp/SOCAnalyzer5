/**
 * ObjectivesModal Component
 * 
 * Modal for viewing, filtering, and managing control objectives.
 * Includes bulk operations, approval workflow, and conversion to controls.
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
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
  FormControlLabel,
  CircularProgress,
  Alert,
  LinearProgress,
  Divider,
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
} from '@mui/icons-material';
import {
  getObjectives,
  getObjectiveControls,
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
} from '../services/objectiveService';
import api from '../api/client';
import { useAuth } from '../contexts/AuthContext';

interface ObjectivesModalProps {
  open: boolean;
  onClose: () => void;
  scanId: number;
  currentUser?: string;
  onRefresh?: () => void;
  showToast?: (message: string, severity?: 'success' | 'error' | 'info' | 'warning') => void;
}

export const ObjectivesModal: React.FC<ObjectivesModalProps> = ({
  open,
  onClose,
  scanId,
  currentUser = 'unknown',
  onRefresh,
  showToast,
}) => {
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
  
  // Operations
  const [extracting, setExtracting] = useState(false);
  const [mapping, setMapping] = useState(false);
  const [operationMessage, setOperationMessage] = useState<string | null>(null);
  const [extractStatus, setExtractStatus] = useState<{
    status: string;
    progress_status?: string;
    processed_chunks?: number;
    total_chunks?: number;
    objectives_found?: number;
    error?: string;
  } | null>(null);
  const extractPollRef = useRef<number | null>(null);
  const { accessToken, loading: authLoading } = useAuth();

  const gapStorageKey = `objective-gap-extract-${scanId}`;
  const gapSummaryHiddenKey = `objective-gap-summary-hidden-${scanId}`;
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
  
  // Load objectives
  const loadObjectives = async () => {
    setLoading(true);
    setError(null);
    try {
      if (!mergeAttempted) {
        const mergeResult = await mergeDuplicateObjectives(scanId);
        setMergeAttempted(true);
        if (mergeResult.merged > 0 || mergeResult.deleted > 0) {
          showToast?.(
            `Merged ${mergeResult.deleted} duplicate objective${mergeResult.deleted !== 1 ? 's' : ''}`,
            'info'
          );
        }
      }

      const params: any = {};
      if (statusFilter !== 'all') {
        params.status = statusFilter;
      }
      if (confidenceFilter > 0) {
        params.min_confidence = confidenceFilter;
      }
      
      const data = await getObjectives(scanId, params);
      setObjectives(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load objectives');
      console.error('Failed to load objectives:', err);
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    if (open && !authLoading && accessToken) {
      setMergeAttempted(false);
      loadObjectives();
      getObjectiveExtractionStatus(scanId)
        .then((status) => setExtractStatus(status))
        .catch(() => setExtractStatus(null));

      const storedGap = loadGapStorage();
      const summaryHidden = loadGapSummaryHidden();
      setGapExtractSummaryHidden(summaryHidden);
      if (storedGap?.status) {
        setGapExtractStatus(storedGap.status as ObjectiveGapExtractStatus);
        setGapExtractExtractedIds(storedGap.extractedIds || []);
        setGapExtractRunning(storedGap.status.status === 'running');
      }

      getObjectiveGapExtractStatus(scanId)
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
                  const pollStatus = await getObjectiveGapExtractStatus(scanId);
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
  }, [open, scanId, statusFilter, confidenceFilter, authLoading, accessToken]);

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
  
  // Filtered objectives
  const filteredObjectives = useMemo(() => {
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

    return list;
  }, [objectives, searchText, sortingField, sortingDirection, gapExtractFilterEnabled, gapExtractExtractedIds, controlCountFilter]);

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
        await createObjective(scanId, {
          objective_id: formObjectiveId.trim() || null,
          objective_text: formObjectiveText.trim(),
          status: formStatus,
          final_confidence: searchExtractApplied ? 1.0 : undefined,
        });
        setOperationMessage('Objective created');
      } else if (editingObjectiveId != null) {
        await updateObjective(scanId, editingObjectiveId, {
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
    console.log('[ObjectivesModal] applyExtractedObjective called with:', extracted);
    
    if (extracted.objective_id) {
      console.log('[ObjectivesModal] Setting objective_id:', extracted.objective_id);
      setFormObjectiveId(extracted.objective_id);
    } else {
      console.log('[ObjectivesModal] No objective_id in extracted data');
    }
    
    if (extracted.objective_text) {
      console.log('[ObjectivesModal] Setting objective_text:', extracted.objective_text);
      setFormObjectiveText(extracted.objective_text);
    } else {
      console.log('[ObjectivesModal] No objective_text in extracted data');
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
      const response = await api.post(`/report/${scanId}/extract-entity`, {
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
      const response = await api.post(`/report/${scanId}/extract-entity`, {
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
    showToast?.(result.message, result.status === 'success' ? 'success' : result.status);
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
      const response = await api.post(`/report/${scanId}/extract-entity`, {
        entity_type: 'control',
        search_text: searchValue,
        force_multi_extract: false,
      });

      const data = response.data;
      if (data.warning || data.requires_force) {
        return { status: 'warning' as const, message: data.warning || 'Multiple matches found. Refine your search.' };
      }
      if (data.error) {
        return { status: 'error' as const, message: data.error };
      }

      const extracted = data.extracted_data || {};
      const payload: any = {
        control_id: extracted.control_id || objective.objective_id || undefined,
        control_desc: extracted.description || objective.objective_text,
        control_test: Array.isArray(extracted.test_procedures)
          ? extracted.test_procedures.join('\n')
          : extracted.test_procedures,
        control_test_results: Array.isArray(extracted.test_results)
          ? extracted.test_results.join('\n')
          : extracted.test_results,
        deviation_desc: extracted.deviation_description || undefined,
        control_page_ref: extracted.page_ref || undefined,
      };

      const result = await convertToControl(scanId, objective.id, payload);
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
      await approveObjective(scanId, objectiveId, currentUser);
      setOperationMessage('Objective approved');
      loadObjectives();
      onRefresh?.();
    } catch (err: any) {
      setError(err.message || 'Failed to approve objective');
    }
  };
  
  const handleReject = async (objectiveId: number) => {
    try {
      await rejectObjective(scanId, objectiveId, currentUser);
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
      await bulkApproveObjectives(scanId, {
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
      await bulkRejectObjectives(scanId, {
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
      upsertResult(objective, result.status, result.message);
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

    try {
      setGapExtractRunning(true);
      await startObjectiveGapExtract(scanId);
      const initialStatus = await getObjectiveGapExtractStatus(scanId);
      setGapExtractStatus(initialStatus);
      setGapExtractExtractedIds(initialStatus.extracted_ids || []);
      saveGapStorage(initialStatus);

      if (gapExtractPollRef.current) {
        window.clearInterval(gapExtractPollRef.current);
      }
      gapExtractPollRef.current = window.setInterval(async () => {
        try {
          const pollStatus = await getObjectiveGapExtractStatus(scanId);
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
      await cancelObjectiveGapExtract(scanId);
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
      const result = await extractObjectives(scanId);
      setOperationMessage(result.message || 'Objective extraction started');

      const pollStatus = async () => {
        try {
          const status = await getObjectiveExtractionStatus(scanId);
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
      const result = await mapObjectivesToControls(scanId);
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
  
  return (
    <Dialog 
      open={open} 
      onClose={onClose} 
      maxWidth="xl" 
      fullWidth
      disablePortal={false}
      disableScrollLock={false}
    >
      <DialogTitle sx={{ py: 1, px: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="subtitle1" fontWeight="bold">Control Objectives</Typography>
          <IconButton onClick={onClose} size="small">
            <CloseIcon />
          </IconButton>
        </Box>
      </DialogTitle>
      
      <DialogContent sx={{ pt: 1, pb: 2 }}>
        {/* Action Buttons */}
        <Box sx={{ mb: 1, display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
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
        
        {/* Bulk Convert Results */}
        {bulkConvertResults.length > 0 && (
          <Box sx={{ mb: 1, p: 1, bgcolor: '#f5f5f5', borderRadius: 1 }}>
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
        )}
        
        {/* Extraction Progress */}
        {extractStatus && extractStatus.status !== 'idle' && (
          <Box sx={{ mb: 1 }}>
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

        {/* Gap Extraction Summary */}
        {gapExtractStatus && !gapExtractSummaryHidden && (
          <Box sx={{ mb: 1, p: 1, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
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
              <Button size="small" onClick={() => setGapExtractLogExpanded((prev) => !prev)}>
                {gapExtractLogExpanded ? 'Hide log' : 'Show log'}
              </Button>
              <Button size="small" onClick={() => setGapExtractPatternExpanded((prev) => !prev)}>
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

        {/* Messages */}
        {error && (
          <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 1 }}>
            {error}
          </Alert>
        )}
        {operationMessage && (
          <Alert severity="success" onClose={() => setOperationMessage(null)} sx={{ mb: 1 }}>
            {operationMessage}
          </Alert>
        )}
        
        {/* Filters */}
        <Box sx={{ mb: 1, display: 'flex', gap: 1, alignItems: 'center' }}>
          <TextField
            label="Search"
            variant="outlined"
            size="small"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            sx={{ minWidth: 180 }}
          />
          
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
        
        {/* Table */}
        <TableContainer component={Paper} sx={{ maxHeight: 500 }}>
          <Table stickyHeader size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={selectedIds.size === filteredObjectives.length && filteredObjectives.length > 0}
                    indeterminate={selectedIds.size > 0 && selectedIds.size < filteredObjectives.length}
                    onChange={(e) => handleSelectAll(e.target.checked)}
                  />
                </TableCell>
                <TableCell>
                  <TableSortLabel
                    active={sortingField === 'id'}
                    direction={sortingField === 'id' ? sortingDirection : 'asc'}
                    onClick={() => handleSortRequest('id')}
                  >
                    ID
                  </TableSortLabel>
                </TableCell>
                <TableCell>Objective Text</TableCell>
                <TableCell>
                  <TableSortLabel
                    active={sortingField === 'confidence'}
                    direction={sortingField === 'confidence' ? sortingDirection : 'asc'}
                    onClick={() => handleSortRequest('confidence')}
                  >
                    Confidence
                  </TableSortLabel>
                </TableCell>
                <TableCell>
                  <TableSortLabel
                    active={sortingField === 'status'}
                    direction={sortingField === 'status' ? sortingDirection : 'asc'}
                    onClick={() => handleSortRequest('status')}
                  >
                    Status
                  </TableSortLabel>
                </TableCell>
                <TableCell>Controls</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} align="center">
                    <CircularProgress />
                  </TableCell>
                </TableRow>
              ) : filteredObjectives.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center">
                    <Typography variant="body2" color="textSecondary">
                      No objectives found. Click "Extract Objectives" to begin.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                filteredObjectives.map((obj) => (
                  <TableRow
                    key={obj.id}
                    hover
                    sx={
                      obj.objective_id && gapExtractedSet.has(obj.objective_id.toLowerCase())
                        ? { backgroundColor: '#fff8e1' }
                        : undefined
                    }
                  >
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={selectedIds.has(obj.id)}
                        onChange={(e) => handleSelectOne(obj.id, e.target.checked)}
                      />
                    </TableCell>
                    <TableCell>{obj.objective_id || '—'}</TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ maxWidth: 400 }}>
                        {obj.objective_text}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={formatConfidence(obj.final_confidence)}
                        size="small"
                        sx={{
                          bgcolor: getConfidenceColor(obj.final_confidence),
                          color: 'white',
                          fontWeight: 'bold',
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={getStatusLabel(obj.status)}
                        size="small"
                        sx={{
                          bgcolor: getStatusColor(obj.status),
                          color: 'white',
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={(obj as any).linked_controls_count || 0}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 0.5 }}>
                        <Tooltip title="Edit">
                          <IconButton
                            size="small"
                            color="primary"
                            onClick={() => handleOpenEdit(obj)}
                          >
                            <EditIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        {obj.status === 'pending' && (
                          <>
                            <Tooltip title="Approve">
                              <IconButton
                                size="small"
                                color="success"
                                onClick={() => handleApprove(obj.id)}
                              >
                                <ApproveIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Reject">
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => handleReject(obj.id)}
                              >
                                <RejectIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </>
                        )}
                        <Tooltip title="Convert to Control">
                          <IconButton
                            size="small"
                            color="primary"
                            onClick={() => handleConvertToControl(obj)}
                          >
                            <ConvertIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </DialogContent>
      
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>

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
    </Dialog>
  );
};

export default ObjectivesModal;

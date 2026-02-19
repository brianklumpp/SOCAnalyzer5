/**
 * ControlEditPanel Component
 * 
 * A fixed overlay panel that appears above the controls table for viewing/editing
 * a single control record. Provides:
 * - View/Edit mode toggle
 * - Navigation (first/prev/next/last/jump) through filtered controls
 * - All editable fields in a compact 2-column grid
 * - Inline 5-factor confidence breakdown
 * - Objective mapping via ObjectiveSelector
 * - Framework mapping chips with recompute
 * - Collapsible edit log
 * - Action buttons (save, accept, ignore, convert to objective)
 * - Keyboard shortcuts (Escape, Ctrl+S, Ctrl+E, Ctrl+←/→)
 * 
 * Positioned within the SplitViewLayout content area so the PDF panel stays visible.
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Box,
  Typography,
  TextField,
  Select,
  MenuItem,
  Button,
  IconButton,
  Tooltip,
  Collapse,
  LinearProgress,
  Chip,
  Divider,
  Autocomplete,
  CircularProgress,
} from '@mui/material';
import {
  Close as CloseIcon,
  Save as SaveIcon,
  Edit as EditIcon,
  Visibility as ViewIcon,
  FirstPage as FirstPageIcon,
  LastPage as LastPageIcon,
  NavigateBefore as PrevIcon,
  NavigateNext as NextIcon,
  CheckCircle as AcceptIcon,
  Block as IgnoreIcon,
  Transform as ConvertIcon,
  Refresh as RefreshIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Psychology as GptIcon,
  Pattern as PatternIcon,
  AccountTree as StructureIcon,
  Hub as FrameworkIcon,
  Warning as DeviationIcon,
} from '@mui/icons-material';
import { ObjectiveSelector } from '../ObjectiveSelector';
import { UniversalFrameworkMapper } from '../UniversalFrameworkMapper';

interface ControlEditPanelProps {
  control: any;
  controls: any[];
  scanId: number;
  onClose: () => void;
  onSave: (row: any, idx: number) => void;
  onIgnore: (row: any) => void;
  onConfirm: (row: any) => void;
  onRecompute: (row: any) => Promise<void>;
  onToggleDeviation?: (row: any, hasDeviation: boolean) => Promise<void>;
  onNavigate: (control: any) => void;
  onConvertToObjective?: (control: any) => void;
  pdfNavigateHandler?: ((snippet: string | null, page?: number | null) => void) | null;
  tocPageOffset?: number;
  frameworkCriteria?: any;
  onOpenMappingDetails?: (control: any, frameworkType: string) => void;
  onObjectivesRefresh?: () => void;
  onRefresh?: () => void;
  showToast?: (message: string, severity?: 'success' | 'error' | 'info' | 'warning') => void;
}

// 5-factor config
const FACTORS = [
  { key: 'gpt', label: 'GPT', icon: <GptIcon sx={{ fontSize: 14 }} />, weightKey: 'gpt_weight', scoreKey: 'gpt_confidence', contribKey: 'gpt_contribution' },
  { key: 'pattern', label: 'Pattern', icon: <PatternIcon sx={{ fontSize: 14 }} />, weightKey: 'pattern_weight', scoreKey: 'pattern_confidence', contribKey: 'pattern_contribution' },
  { key: 'structure', label: 'Structure', icon: <StructureIcon sx={{ fontSize: 14 }} />, weightKey: 'structure_weight', scoreKey: 'structure_score', contribKey: 'structure_contribution' },
  { key: 'framework', label: 'Framework', icon: <FrameworkIcon sx={{ fontSize: 14 }} />, weightKey: 'framework_weight', scoreKey: 'framework_score', contribKey: 'framework_contribution' },
  { key: 'deviation', label: 'Deviation', icon: <DeviationIcon sx={{ fontSize: 14 }} />, weightKey: 'deviation_weight', scoreKey: 'deviation_score', contribKey: 'deviation_contribution' },
];

export const ControlEditPanel: React.FC<ControlEditPanelProps> = ({
  control,
  controls,
  scanId,
  onClose,
  onSave,
  onIgnore,
  onConfirm,
  onRecompute,
  onToggleDeviation,
  onNavigate,
  onConvertToObjective,
  pdfNavigateHandler,
  tocPageOffset,
  frameworkCriteria,
  onOpenMappingDetails,
  onObjectivesRefresh,
  onRefresh,
  showToast,
}) => {
  const [editMode, setEditMode] = useState(false);
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [dirty, setDirty] = useState(false);
  const [showEditLog, setShowEditLog] = useState(false);
  const [showObjectives, setShowObjectives] = useState(false);
  const [recomputing, setRecomputing] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Current index in the controls array
  const currentIndex = useMemo(() => {
    return controls.findIndex((c: any) => c.id === control?.id);
  }, [controls, control]);

  const totalControls = controls.length;

  // Initialize form data when control changes
  useEffect(() => {
    if (control) {
      setFormData({
        control_id: control.control_id || '',
        control_desc: control.control_desc || '',
        control_test: control.control_test || '',
        control_test_results: control.control_test_results || '',
        has_deviation: control.has_deviation || false,
        deviation_desc: control.deviation_desc || '',
        analyst_notes: control.analyst_notes || '',
        control_confidence: control.control_confidence || '',
      });
      setDirty(false);
      setEditMode(false);
    }
  }, [control?.id]);

  // Scroll PDF to this control's location on mount/navigate
  useEffect(() => {
    if (control && pdfNavigateHandler) {
      const pageRefs = control.control_page_refs;
      if (Array.isArray(pageRefs) && pageRefs.length > 0) {
        // Page refs are already physical PDF page numbers (from === PAGE N === markers)
        // tocPageOffset is only needed when the document uses printed page numbers that
        // differ from physical pages (e.g. cover pages before numbered content).
        const offset = tocPageOffset ?? 0;
        const targetPage = pageRefs[0] + offset;
        const snippet = control.pdf_snippet || control.control_desc || null;
        pdfNavigateHandler(snippet, targetPage);
      }
    }
  }, [control?.id, pdfNavigateHandler, tocPageOffset]);

  // Handle field changes
  const handleChange = useCallback((field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setDirty(true);
  }, []);

  // Save handler
  const handleSave = useCallback(() => {
    if (!control || !dirty) return;
    const idx = controls.findIndex((c: any) => c.id === control.id);
    const merged = { ...control, ...formData };
    onSave(merged, idx >= 0 ? idx : 0);
    setDirty(false);
    setEditMode(false);
    showToast?.('Control saved successfully', 'success');
  }, [control, controls, formData, dirty, onSave, showToast]);

  // Navigation handlers
  const navigateTo = useCallback((index: number) => {
    if (index < 0 || index >= totalControls) return;
    if (dirty) {
      if (!window.confirm('You have unsaved changes. Discard and navigate?')) return;
    }
    onNavigate(controls[index]);
  }, [controls, totalControls, dirty, onNavigate]);

  const goFirst = () => navigateTo(0);
  const goPrev = () => navigateTo(currentIndex - 1);
  const goNext = () => navigateTo(currentIndex + 1);
  const goLast = () => navigateTo(totalControls - 1);

  // Jump to specific control
  const handleJumpTo = useCallback((_: any, value: any) => {
    if (!value) return;
    const idx = controls.findIndex((c: any) => c.id === value.id);
    if (idx >= 0) navigateTo(idx);
  }, [controls, navigateTo]);

  // Close handler with dirty check
  const handleClose = useCallback(() => {
    if (dirty) {
      if (!window.confirm('You have unsaved changes. Discard and close?')) return;
    }
    onClose();
  }, [dirty, onClose]);

  // Action handlers
  const handleAccept = useCallback(() => {
    onConfirm(control);
    showToast?.('Control accepted (100%)', 'success');
  }, [control, onConfirm, showToast]);

  const handleIgnore = useCallback(() => {
    onIgnore(control);
    showToast?.('Control ignored (0%)', 'info');
  }, [control, onIgnore, showToast]);

  const handleConvert = useCallback(() => {
    onConvertToObjective?.(control);
    showToast?.('Control converted to objective', 'success');
  }, [control, onConvertToObjective, showToast]);

  const handleRecompute = useCallback(async () => {
    setRecomputing(true);
    try {
      await onRecompute(control);
      onRefresh?.();
      showToast?.('Framework mappings recomputed', 'success');
    } finally {
      setRecomputing(false);
    }
  }, [control, onRecompute, onRefresh, showToast]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleClose();
      } else if (e.ctrlKey && e.key === 's') {
        e.preventDefault();
        if (editMode && dirty) handleSave();
      } else if (e.ctrlKey && e.key === 'e') {
        e.preventDefault();
        setEditMode(prev => !prev);
      } else if (e.ctrlKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        goPrev();
      } else if (e.ctrlKey && e.key === 'ArrowRight') {
        e.preventDefault();
        goNext();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleClose, handleSave, editMode, dirty, currentIndex]);

  // 5-factor confidence data
  const metadata = control?.verification_metadata || {};
  const factorScores = metadata.factor_scores || {};
  const weightsUsed = metadata.weights_used || {};
  const is5Factor = metadata.method === '5-factor' && Object.keys(factorScores).length > 0;

  // Parse confidence for display
  const confValue = (() => {
    const raw = control?.control_confidence;
    if (typeof raw === 'string') {
      const n = parseFloat(raw);
      return isNaN(n) ? 0 : (raw.includes('%') ? n / 100 : (n > 1 ? n / 100 : n));
    }
    return typeof raw === 'number' ? (raw > 1 ? raw / 100 : raw) : 0;
  })();

  // Control jump options
  const jumpOptions = useMemo(() => {
    return controls.map((c: any, i: number) => ({
      id: c.id,
      label: c.control_id || `#${c.id}`,
      index: i,
    }));
  }, [controls]);

  if (!control) return null;

  return (
    <Box
      ref={panelRef}
      className="control-edit-panel"
    >
      {/* ═══ TOOLBAR ═══ */}
      <Box className="control-edit-toolbar">
        {/* Navigation cluster */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
          <Tooltip title="First (Ctrl+Home)">
            <span><IconButton size="small" onClick={goFirst} disabled={currentIndex <= 0}><FirstPageIcon fontSize="small" /></IconButton></span>
          </Tooltip>
          <Tooltip title="Previous (Ctrl+←)">
            <span><IconButton size="small" onClick={goPrev} disabled={currentIndex <= 0}><PrevIcon fontSize="small" /></IconButton></span>
          </Tooltip>

          <Autocomplete
            size="small"
            options={jumpOptions}
            getOptionLabel={(opt: any) => opt.label}
            value={jumpOptions.find((o: any) => o.id === control.id) || undefined}
            onChange={handleJumpTo}
            disableClearable
            sx={{ width: 150, mx: 0.5 }}
            renderInput={(params) => (
              <TextField
                {...params}
                variant="outlined"
                size="small"
                InputProps={{
                  ...params.InputProps,
                  sx: { fontSize: 12, height: 28, py: 0 },
                }}
              />
            )}
            renderOption={(props, option: any) => (
              <Box component="li" {...props} sx={{ fontSize: 11, py: '2px !important' }}>
                <span style={{ fontWeight: 600, marginRight: 6 }}>{option.label}</span>
                <span style={{ color: '#888' }}>#{option.index + 1}</span>
              </Box>
            )}
          />

          <Tooltip title="Next (Ctrl+→)">
            <span><IconButton size="small" onClick={goNext} disabled={currentIndex >= totalControls - 1}><NextIcon fontSize="small" /></IconButton></span>
          </Tooltip>
          <Tooltip title="Last">
            <span><IconButton size="small" onClick={goLast} disabled={currentIndex >= totalControls - 1}><LastPageIcon fontSize="small" /></IconButton></span>
          </Tooltip>

          <Typography sx={{ fontSize: 11, color: 'text.secondary', ml: 0.5, whiteSpace: 'nowrap' }}>
            {currentIndex + 1} / {totalControls}
          </Typography>
        </Box>

        {/* Action buttons */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Tooltip title={editMode ? 'Switch to View (Ctrl+E)' : 'Enable Edit (Ctrl+E)'}>
            <IconButton size="small" onClick={() => setEditMode(!editMode)} color={editMode ? 'primary' : 'default'}>
              {editMode ? <ViewIcon fontSize="small" /> : <EditIcon fontSize="small" />}
            </IconButton>
          </Tooltip>

          {editMode && dirty && (
            <Tooltip title="Save (Ctrl+S)">
              <IconButton size="small" onClick={handleSave} color="primary">
                <SaveIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}

          <Divider orientation="vertical" flexItem sx={{ mx: 0.25 }} />

          <Tooltip title="Accept (100% confidence)">
            <IconButton size="small" onClick={handleAccept} color="success">
              <AcceptIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Ignore (0% confidence)">
            <IconButton size="small" onClick={handleIgnore} color="error">
              <IgnoreIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          {onConvertToObjective && (
            <Tooltip title="Convert to Objective">
              <IconButton size="small" onClick={handleConvert}>
                <ConvertIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}

          <Divider orientation="vertical" flexItem sx={{ mx: 0.25 }} />

          <Tooltip title="Close (Esc)">
            <IconButton size="small" onClick={handleClose}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* ═══ BODY — 2-COLUMN GRID ═══ */}
      <Box className="control-edit-body">
        {/* LEFT COLUMN */}
        <Box className="control-edit-col">
          <Box className="control-edit-field">
            <label>Control ID</label>
            {editMode ? (
              <TextField
                fullWidth size="small" variant="outlined"
                value={formData.control_id}
                onChange={(e) => handleChange('control_id', e.target.value)}
                inputProps={{ style: { fontSize: 12, padding: '4px 8px' } }}
              />
            ) : (
              <Typography sx={{ fontSize: 12, fontWeight: 600 }}>{control.control_id || '—'}</Typography>
            )}
          </Box>

          <Box className="control-edit-field">
            <label>Description</label>
            {editMode ? (
              <TextField
                fullWidth size="small" variant="outlined" multiline minRows={2} maxRows={4}
                value={formData.control_desc}
                onChange={(e) => handleChange('control_desc', e.target.value)}
                inputProps={{ style: { fontSize: 11 } }}
              />
            ) : (
              <Typography sx={{ fontSize: 11, whiteSpace: 'pre-wrap', maxHeight: 80, overflow: 'auto' }}>
                {control.control_desc || '—'}
              </Typography>
            )}
          </Box>

          <Box className="control-edit-field">
            <label>Test</label>
            {editMode ? (
              <TextField
                fullWidth size="small" variant="outlined" multiline minRows={2} maxRows={4}
                value={formData.control_test}
                onChange={(e) => handleChange('control_test', e.target.value)}
                inputProps={{ style: { fontSize: 11 } }}
              />
            ) : (
              <Typography sx={{ fontSize: 11, whiteSpace: 'pre-wrap', maxHeight: 80, overflow: 'auto' }}>
                {control.control_test || '—'}
              </Typography>
            )}
          </Box>

          <Box className="control-edit-field">
            <label>Test Results</label>
            {editMode ? (
              <TextField
                fullWidth size="small" variant="outlined" multiline minRows={2} maxRows={4}
                value={formData.control_test_results}
                onChange={(e) => handleChange('control_test_results', e.target.value)}
                inputProps={{ style: { fontSize: 11 } }}
              />
            ) : (
              <Typography sx={{ fontSize: 11, whiteSpace: 'pre-wrap', maxHeight: 80, overflow: 'auto' }}>
                {control.control_test_results || '—'}
              </Typography>
            )}
          </Box>
        </Box>

        {/* RIGHT COLUMN */}
        <Box className="control-edit-col">
          <Box className="control-edit-field">
            <label>Deviation</label>
            {editMode ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                <Select
                  size="small" fullWidth
                  value={formData.has_deviation ? 'yes' : 'no'}
                  onChange={(e) => {
                    const val = e.target.value === 'yes';
                    handleChange('has_deviation', val);
                    if (!val) handleChange('deviation_desc', '');
                  }}
                  sx={{ fontSize: 12, height: 28 }}
                >
                  <MenuItem value="no" sx={{ fontSize: 12 }}>No</MenuItem>
                  <MenuItem value="yes" sx={{ fontSize: 12 }}>Yes</MenuItem>
                </Select>
                {formData.has_deviation && (
                  <TextField
                    fullWidth size="small" variant="outlined" multiline minRows={1} maxRows={3}
                    placeholder="Deviation description"
                    value={formData.deviation_desc}
                    onChange={(e) => handleChange('deviation_desc', e.target.value)}
                    inputProps={{ style: { fontSize: 11 } }}
                  />
                )}
              </Box>
            ) : (
              <Box>
                {control.has_deviation ? (
                  <Box>
                    <Chip label="Yes" size="small" color="warning" sx={{ fontSize: 10, height: 18 }} />
                    {control.deviation_desc && (
                      <Typography sx={{ fontSize: 11, mt: 0.5, color: 'error.main', whiteSpace: 'pre-wrap', maxHeight: 60, overflow: 'auto' }}>
                        {control.deviation_desc}
                      </Typography>
                    )}
                  </Box>
                ) : (
                  <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>No</Typography>
                )}
              </Box>
            )}
          </Box>

          <Box className="control-edit-field">
            <label>Analyst Notes</label>
            {editMode ? (
              <TextField
                fullWidth size="small" variant="outlined" multiline minRows={2} maxRows={4}
                value={formData.analyst_notes}
                onChange={(e) => handleChange('analyst_notes', e.target.value)}
                inputProps={{ style: { fontSize: 11 } }}
              />
            ) : (
              <Typography sx={{ fontSize: 11, whiteSpace: 'pre-wrap', maxHeight: 60, overflow: 'auto' }}>
                {control.analyst_notes || '—'}
              </Typography>
            )}
          </Box>

          <Box className="control-edit-field">
            <label>Confidence</label>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              {editMode ? (
                <TextField
                  size="small" variant="outlined"
                  value={formData.control_confidence}
                  onChange={(e) => handleChange('control_confidence', e.target.value)}
                  inputProps={{ style: { fontSize: 12, padding: '4px 8px', width: 60 } }}
                />
              ) : (
                <Typography sx={{ fontSize: 13, fontWeight: 700 }}>
                  {typeof control.control_confidence === 'string' ? control.control_confidence : `${Math.round(confValue * 100)}%`}
                </Typography>
              )}
              <LinearProgress
                variant="determinate"
                value={Math.round(confValue * 100)}
                sx={{ flex: 1, height: 6, borderRadius: 3, bgcolor: 'grey.200',
                  '& .MuiLinearProgress-bar': { bgcolor: confValue >= 0.7 ? '#4caf50' : confValue >= 0.5 ? '#ff9800' : '#f44336' }
                }}
              />
            </Box>

            {/* Inline 5-factor breakdown */}
            {is5Factor && (
              <Box sx={{ mt: 0.5 }}>
                {FACTORS.map(f => {
                  const score = factorScores[f.scoreKey] || 0;
                  const weight = weightsUsed[f.weightKey] || 0;
                  return (
                    <Box key={f.key} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: '2px' }}>
                      {f.icon}
                      <Typography sx={{ fontSize: 10, width: 55, flexShrink: 0 }}>{f.label}</Typography>
                      <Typography sx={{ fontSize: 10, width: 28, color: 'text.secondary', flexShrink: 0 }}>{Math.round(weight * 100)}%</Typography>
                      <LinearProgress
                        variant="determinate"
                        value={Math.round(score * 100)}
                        sx={{ flex: 1, height: 4, borderRadius: 2, bgcolor: 'grey.200',
                          '& .MuiLinearProgress-bar': { bgcolor: score >= 0.7 ? '#4caf50' : score >= 0.5 ? '#ff9800' : '#f44336' }
                        }}
                      />
                      <Typography sx={{ fontSize: 10, width: 30, textAlign: 'right', fontWeight: 600, flexShrink: 0 }}>
                        {(score * 100).toFixed(0)}%
                      </Typography>
                    </Box>
                  );
                })}
              </Box>
            )}
          </Box>

          {/* Confidence Calculation (read-only) */}
          {control.confidence_calc && (
            <Box className="control-edit-field">
              <label>Confidence Calc</label>
              <Typography sx={{ fontSize: 10, whiteSpace: 'pre-wrap', color: 'text.secondary', maxHeight: 50, overflow: 'auto', fontFamily: 'monospace' }}>
                {control.confidence_calc}
              </Typography>
            </Box>
          )}
        </Box>
      </Box>

      {/* ═══ OBJECTIVE MAPPING (collapsible) ═══ */}
      <Box className="control-edit-section">
        <Box
          sx={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 0.5 }}
          onClick={() => setShowObjectives(!showObjectives)}
        >
          {showObjectives ? <ExpandLessIcon sx={{ fontSize: 16 }} /> : <ExpandMoreIcon sx={{ fontSize: 16 }} />}
          <Typography sx={{ fontSize: 11, fontWeight: 600 }}>Control Objective Mapping</Typography>
        </Box>
        <Collapse in={showObjectives}>
          <Box sx={{ mt: 0.5 }}>
            <ObjectiveSelector
              scanId={scanId}
              controlId={control.id}
              onChange={() => onObjectivesRefresh?.()}
              disabled={!editMode}
            />
          </Box>
        </Collapse>
      </Box>

      {/* ═══ FRAMEWORK MAPPINGS ═══ */}
      <Box className="control-edit-section">
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography sx={{ fontSize: 11, fontWeight: 600 }}>Framework Mappings</Typography>
          <Tooltip title="Recompute framework mappings">
            <IconButton size="small" onClick={handleRecompute} disabled={recomputing}>
              {recomputing ? <CircularProgress size={14} /> : <RefreshIcon sx={{ fontSize: 14 }} />}
            </IconButton>
          </Tooltip>
        </Box>
        {frameworkCriteria && onOpenMappingDetails ? (
          <UniversalFrameworkMapper
            control={control}
            frameworkCriteria={frameworkCriteria}
            onOpenMappingDetails={onOpenMappingDetails}
          />
        ) : (
          <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>
            {control.framework_mappings ? JSON.stringify(Object.keys(control.framework_mappings)) : 'Not mapped'}
          </Typography>
        )}
      </Box>

      {/* ═══ EDIT LOG (collapsible) ═══ */}
      {control.edit_log && (
        <Box className="control-edit-section">
          <Box
            sx={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 0.5 }}
            onClick={() => setShowEditLog(!showEditLog)}
          >
            {showEditLog ? <ExpandLessIcon sx={{ fontSize: 16 }} /> : <ExpandMoreIcon sx={{ fontSize: 16 }} />}
            <Typography sx={{ fontSize: 11, fontWeight: 600 }}>Edit Log</Typography>
          </Box>
          <Collapse in={showEditLog}>
            <Typography sx={{ fontSize: 10, whiteSpace: 'pre-wrap', color: 'text.secondary', mt: 0.5, maxHeight: 120, overflow: 'auto', fontFamily: 'monospace', bgcolor: 'grey.50', p: 0.5, borderRadius: 0.5 }}>
              {control.edit_log}
            </Typography>
          </Collapse>
        </Box>
      )}
    </Box>
  );
};

export default ControlEditPanel;

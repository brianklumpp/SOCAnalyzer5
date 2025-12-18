/**
 * DeviationCard Component
 * 
 * Displays a control deviation with AI-generated "What it Means" summary.
 * Features editable summary, regenerate button, and Solidigm orange styling.
 */

import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Box,
  Typography,
  Chip,
  IconButton,
  TextField,
  Button,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Alert,
  Tooltip,
  CircularProgress,
} from '@mui/material';
import {
  Edit as EditIcon,
  Refresh as RefreshIcon,
  ExpandMore as ExpandMoreIcon,
  Save as SaveIcon,
  Cancel as CancelIcon,
  Info as InfoIcon,
  Clear as ClearIcon,
} from '@mui/icons-material';
import { api } from '../api/client';
import { solidigmColors } from '../theme/solidigmTheme';

interface DeviationCardProps {
  deviation: {
    id: number;
    control_id: string;
    page_ref: number;
    control_description: string;
    test_procedure: string;
    test_result: string;
    deviation_desc?: string | null;
    deviation_summary: string | null;
    management_response_text?: string | null;
    management_response_page_refs?: number[];
    management_response_confidence?: number;
    response_detection_method?: string;
    scan_id?: number;
  };
  scanId: string | number;
  onUpdate?: () => void;
}

export const DeviationCard: React.FC<DeviationCardProps> = ({ deviation, scanId, onUpdate }) => {
  const [editing, setEditing] = useState(false);
  const [editedSummary, setEditedSummary] = useState(deviation.deviation_summary || '');
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Management response state
  const [editingMgmtResponse, setEditingMgmtResponse] = useState(false);
  const [editedMgmtResponse, setEditedMgmtResponse] = useState(deviation.management_response_text || '');
  const [savingMgmtResponse, setSavingMgmtResponse] = useState(false);
  const [regeneratingMgmtResponse, setRegeneratingMgmtResponse] = useState(false);
  const [mgmtResponseError, setMgmtResponseError] = useState<string | null>(null);
  const [relatedControls, setRelatedControls] = useState<string[]>([]);

  const handleEdit = () => {
    setEditedSummary(deviation.deviation_summary || '');
    setEditing(true);
    setError(null);
  };

  const handleCancel = () => {
    setEditing(false);
    setEditedSummary(deviation.deviation_summary || '');
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/report/${scanId}/deviations/${deviation.id}`, {
        deviation_summary: editedSummary,
      });
      setEditing(false);
      if (onUpdate) onUpdate();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save summary');
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    setError(null);
    try {
      const response = await api.post(`/report/${scanId}/deviations/${deviation.id}/regenerate`);
      if (response.data.deviation_summary) {
        setEditedSummary(response.data.deviation_summary);
      }
      if (onUpdate) onUpdate();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to regenerate summary');
    } finally {
      setRegenerating(false);
    }
  };

  const handleClearDeviation = async () => {
    if (!window.confirm('Clear deviation flag from this control? This will remove it from the deviations tab.')) {
      return;
    }
    
    setClearing(true);
    setError(null);
    try {
      // PATCH the control to clear has_deviation and deviation_desc
      await api.patch(`/report/${scanId}/controls/id/${deviation.id}`, {
        has_deviation: false,
        deviation_desc: null
      });
      if (onUpdate) onUpdate();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to clear deviation');
    } finally {
      setClearing(false);
    }
  };

  // Management response handlers
  const handleEditMgmtResponse = () => {
    setEditedMgmtResponse(deviation.management_response_text || '');
    setEditingMgmtResponse(true);
    setMgmtResponseError(null);
  };

  const handleCancelMgmtResponse = () => {
    setEditingMgmtResponse(false);
    setEditedMgmtResponse(deviation.management_response_text || '');
    setMgmtResponseError(null);
  };

  const handleSaveMgmtResponse = async () => {
    setSavingMgmtResponse(true);
    setMgmtResponseError(null);
    try {
      await api.patch(`/report/${scanId}/deviations/${deviation.id}/management-response`, {
        management_response_text: editedMgmtResponse,
      });
      setEditingMgmtResponse(false);
      if (onUpdate) onUpdate();
    } catch (err: any) {
      setMgmtResponseError(err.response?.data?.detail || 'Failed to save management response');
    } finally {
      setSavingMgmtResponse(false);
    }
  };

  const handleRegenerateMgmtResponse = async () => {
    console.log('[DeviationCard] Regenerate clicked, scanId:', scanId, 'controlId:', deviation.id);
    setRegeneratingMgmtResponse(true);
    setMgmtResponseError(null);
    try {
      const url = `/report/${scanId}/deviations/${deviation.id}/regenerate-management-response`;
      console.log('[DeviationCard] POST to:', url);
      const response = await api.post(url);
      console.log('[DeviationCard] Response:', response.data);
      if (onUpdate) onUpdate();
    } catch (err: any) {
      console.error('[DeviationCard] Error regenerating:', err);
      setMgmtResponseError(err.response?.data?.detail || 'Failed to regenerate management response');
    } finally {
      setRegeneratingMgmtResponse(false);
    }
  };

  // Load related controls on mount
  React.useEffect(() => {
    const loadRelatedControls = async () => {
      if (!deviation.management_response_text) return;
      try {
        const response = await api.get(`/report/${scanId}/deviations/${deviation.id}/management-response`);
        if (response.data.related_control_ids) {
          setRelatedControls(response.data.related_control_ids);
        }
      } catch (err) {
        // Silently fail - not critical
      }
    };
    loadRelatedControls();
  }, [deviation.id, deviation.management_response_text, scanId]);

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.7) return '#4caf50'; // green
    if (confidence >= 0.5) return '#ff9800'; // orange/yellow
    return '#f44336'; // red
  };

  const charCount = editedSummary.length;
  const charLimit = 300;

  return (
    <Card
      sx={{
        border: `2px solid ${solidigmColors.orange}`,
        borderRadius: 2,
        boxShadow: 2,
        '&:hover': {
          boxShadow: 4,
        },
        position: 'relative',
      }}
    >
      <CardContent>
        {/* Regenerate Button */}
        <Tooltip title="Regenerate AI summary">
          <IconButton
            onClick={handleRegenerate}
            disabled={regenerating}
            sx={{
              position: 'absolute',
              top: 8,
              right: 8,
              color: solidigmColors.orange,
            }}
            size="small"
          >
            {regenerating ? <CircularProgress size={20} /> : <RefreshIcon />}
          </IconButton>
        </Tooltip>

        {/* Control ID and Page Reference */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2, pr: 5 }}>
          <Chip
            label={deviation.control_id}
            sx={{
              bgcolor: solidigmColors.orange,
              color: 'white',
              fontWeight: 600,
              fontSize: '0.875rem',
            }}
          />
          <Typography variant="caption" color="text.secondary">
            Page {deviation.page_ref}
          </Typography>
          <Box sx={{ ml: 'auto' }}>
            <Tooltip title="Clear deviation flag from this control">
              <Button
                variant="outlined"
                size="small"
                startIcon={clearing ? <CircularProgress size={16} /> : <ClearIcon />}
                onClick={handleClearDeviation}
                disabled={clearing || regenerating}
                color="error"
                sx={{ fontSize: '0.75rem' }}
              >
                {clearing ? 'Clearing...' : 'Clear Deviation'}
              </Button>
            </Tooltip>
          </Box>
        </Box>

        {/* Control Description */}
        <Typography variant="body2" sx={{ mb: 2 }}>
          <strong>Control Description:</strong> {deviation.control_description}
        </Typography>

        {/* Test Procedure (Collapsible) */}
        <Accordion sx={{ mb: 2, boxShadow: 'none', '&:before': { display: 'none' } }}>
          <AccordionSummary
            expandIcon={<ExpandMoreIcon />}
            sx={{ minHeight: 40, '& .MuiAccordionSummary-content': { my: 1 } }}
          >
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Test Procedure
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
              {deviation.test_procedure}
            </Typography>
          </AccordionDetails>
        </Accordion>

        {/* Test Result / Deviation */}
        <Alert severity="warning" sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
            Test Result / Deviation:
          </Typography>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {deviation.deviation_desc || deviation.test_result}
          </Typography>
        </Alert>

        {/* What it Means Section */}
        <Box
          sx={{
            bgcolor: `${solidigmColors.orange}20`,
            p: 2,
            borderRadius: 1,
            mt: 2,
            overflow: 'visible',
            minHeight: 'fit-content',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <InfoIcon fontSize="small" />
              What it Means
            </Typography>
            {!editing && (
              <Tooltip title="Edit summary">
                <IconButton onClick={handleEdit} size="small" sx={{ color: solidigmColors.orange }}>
                  <EditIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
          </Box>

          {editing ? (
            <>
              <TextField
                fullWidth
                multiline
                rows={4}
                value={editedSummary}
                onChange={(e) => setEditedSummary(e.target.value.slice(0, charLimit))}
                placeholder="Enter explanation of what this deviation means..."
                sx={{ mb: 1 }}
                helperText={`${charCount}/${charLimit} characters`}
              />
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<SaveIcon />}
                  onClick={handleSave}
                  disabled={saving}
                  sx={{ bgcolor: solidigmColors.orange, '&:hover': { bgcolor: '#E68A00' } }}
                >
                  {saving ? 'Saving...' : 'Save'}
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<CancelIcon />}
                  onClick={handleCancel}
                  disabled={saving}
                >
                  Cancel
                </Button>
              </Box>
            </>
          ) : (
            <Typography 
              variant="body2" 
              sx={{ 
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                overflow: 'visible',
                textOverflow: 'clip',
                display: 'block',
                WebkitLineClamp: 'unset',
                WebkitBoxOrient: 'unset'
              }}
            >
              {deviation.deviation_summary || (
                <span style={{ color: 'text.secondary', fontStyle: 'italic' }}>
                  Click edit icon to add explanation
                </span>
              )}
            </Typography>
          )}

          {error && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {error}
            </Alert>
          )}
        </Box>

        {/* Management Response Section */}
        <Box sx={{ mt: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Management Response
            </Typography>
            {deviation.management_response_confidence && (
              <Chip
                size="small"
                label={`${Math.round(deviation.management_response_confidence * 100)}% confidence`}
                sx={{
                  bgcolor: getConfidenceColor(deviation.management_response_confidence),
                  color: 'white',
                  fontWeight: 500,
                }}
              />
            )}
            {!editingMgmtResponse && deviation.management_response_text && (
              <>
                <Tooltip title="Edit management response">
                  <IconButton size="small" onClick={handleEditMgmtResponse}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Regenerate from report">
                  <IconButton size="small" onClick={handleRegenerateMgmtResponse} disabled={regeneratingMgmtResponse}>
                    <RefreshIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </>
            )}
          </Box>

          {editingMgmtResponse ? (
            <>
              <TextField
                fullWidth
                multiline
                rows={4}
                value={editedMgmtResponse}
                onChange={(e) => setEditedMgmtResponse(e.target.value)}
                placeholder="Enter management's response or remediation plan..."
                sx={{ mb: 1 }}
              />
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<SaveIcon />}
                  onClick={handleSaveMgmtResponse}
                  disabled={savingMgmtResponse}
                  sx={{ bgcolor: solidigmColors.orange, '&:hover': { bgcolor: '#E68A00' } }}
                >
                  {savingMgmtResponse ? 'Saving...' : 'Save'}
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<CancelIcon />}
                  onClick={handleCancelMgmtResponse}
                  disabled={savingMgmtResponse}
                >
                  Cancel
                </Button>
              </Box>
            </>
          ) : (
            <>
              {deviation.management_response_text ? (
                <>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', mb: 1 }}>
                    {deviation.management_response_text}
                  </Typography>
                  {deviation.management_response_page_refs && deviation.management_response_page_refs.length > 0 && (
                    <Typography variant="caption" color="text.secondary">
                      Found on page{deviation.management_response_page_refs.length > 1 ? 's' : ''}: {deviation.management_response_page_refs.join(', ')}
                    </Typography>
                  )}
                  {relatedControls.length > 0 && (
                    <Box sx={{ mt: 1 }}>
                      <Chip
                        size="small"
                        icon={<InfoIcon />}
                        label={`Also applies to ${relatedControls.length} other deviation${relatedControls.length > 1 ? 's' : ''}`}
                        variant="outlined"
                        sx={{ fontSize: '0.75rem' }}
                      />
                    </Box>
                  )}
                </>
              ) : (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                    No management response found in report
                  </Typography>
                  <Button
                    size="small"
                    startIcon={<RefreshIcon />}
                    onClick={handleRegenerateMgmtResponse}
                    disabled={regeneratingMgmtResponse}
                    variant="outlined"
                    color="primary"
                  >
                    {regeneratingMgmtResponse ? 'Regenerating...' : 'Try Extract Again'}
                  </Button>
                  <Button
                    size="small"
                    startIcon={<EditIcon />}
                    onClick={handleEditMgmtResponse}
                    variant="outlined"
                  >
                    Add Manually
                  </Button>
                </Box>
              )}
            </>
          )}

          {mgmtResponseError && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {mgmtResponseError}
            </Alert>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

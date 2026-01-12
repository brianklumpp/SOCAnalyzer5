import React, { useState, useEffect } from 'react';
import {
  Box,
  Chip,
  Drawer,
  IconButton,
  Typography,
  Button,
  List,
  ListItem,
  ListItemText,
  Divider,
  CircularProgress,
  Alert,
  Tooltip
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import MergeIcon from '@mui/icons-material/MergeType';
import LinkIcon from '@mui/icons-material/Link';
import axios from 'axios';
import { APP_CONFIG } from '../../../config';

interface MergeSuggestion {
  control_id: string;
  primary_db_id: number;
  candidate_db_id: number;
  primary_pages: number[];
  candidate_pages: number[];
  merge_confidence: number;
  confidence_breakdown: string[];
  primary_desc: string;
  candidate_desc: string;
  primary_test?: string;
  candidate_test?: string;
  primary_deviation?: string;
  candidate_deviation?: string;
  primary_has_deviation?: boolean;
  candidate_has_deviation?: boolean;
  action?: 'merge' | 'link_as_instances' | 'review_manually';
  duplicate_type?: 'IDENTICAL' | 'CRITERIA_VARIANT' | 'TEST_VARIANT' | 'AMBIGUOUS';
  criteria_differences?: any;
  test_differences?: any;
  deviation_differences?: any;
  rationale?: string;
}

interface MergeSuggestionsPanelProps {
  scanId: number;
  onMergeComplete: () => void;
}

export const MergeSuggestionsPanel: React.FC<MergeSuggestionsPanelProps> = ({
  scanId,
  onMergeComplete
}) => {
  const storageKey = `merge_suggestions_${scanId}`;
  
  // Load cached suggestions from sessionStorage on mount
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<MergeSuggestion[]>(() => {
    try {
      const cached = sessionStorage.getItem(storageKey);
      return cached ? JSON.parse(cached) : [];
    } catch {
      return [];
    }
  });
  const [loading, setLoading] = useState(false);
  const [merging, setMerging] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [hasMergedControls, setHasMergedControls] = useState(false);

  // Persist suggestions to sessionStorage whenever they change
  useEffect(() => {
    if (suggestions.length > 0) {
      sessionStorage.setItem(storageKey, JSON.stringify(suggestions));
    } else {
      sessionStorage.removeItem(storageKey);
    }
  }, [suggestions, storageKey]);

  const fetchSuggestions = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get(APP_CONFIG.apiUrl(`/report/${scanId}/controls/suggest-merges`));
      setSuggestions(response.data.suggestions || []);
    } catch (err: any) {
      console.error('Failed to fetch merge suggestions:', err);
      setError(err.response?.data?.error || 'Failed to load suggestions');
    } finally {
      setLoading(false);
    }
  };

  // Only fetch suggestions when drawer is first opened and we don't have cached suggestions
  // This preserves the suggestion list across report refreshes so users can merge multiple items
  useEffect(() => {
    if (drawerOpen && suggestions.length === 0 && !loading) {
      fetchSuggestions();
    }
  }, [drawerOpen]);

  const handleMerge = async (suggestion: MergeSuggestion) => {
    setMerging(prev => new Set([...Array.from(prev), suggestion.candidate_db_id]));
    try {
      await axios.post(APP_CONFIG.apiUrl(`/report/${scanId}/controls/merge`), {
        primary_control_id: suggestion.primary_db_id,
        merge_control_ids: [suggestion.candidate_db_id]
      });
      
      // Remove from suggestions immediately (optimistic update)
      setSuggestions(prev => 
        prev.filter(s => s.candidate_db_id !== suggestion.candidate_db_id)
      );
      
      // Track that we've made changes (refresh will happen on drawer close, NOT after each merge)
      setHasMergedControls(true);
    } catch (err: any) {
      console.error('Merge failed:', err);
      alert(`Merge failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setMerging(prev => {
        const next = new Set(prev);
        next.delete(suggestion.candidate_db_id);
        return next;
      });
    }
  };

  const handleLinkInstances = async (suggestion: MergeSuggestion) => {
    setMerging(prev => new Set([...Array.from(prev), suggestion.candidate_db_id]));
    try {
      await axios.post(APP_CONFIG.apiUrl(`/report/${scanId}/controls/link_instances`), {
        control_ids: [suggestion.primary_db_id, suggestion.candidate_db_id],
        duplicate_type: suggestion.duplicate_type || 'CRITERIA_VARIANT',
        user_note: `Linked via merge suggestions panel - ${suggestion.rationale || 'criteria variant detected'}`
      });
      
      // Remove from suggestions immediately (optimistic update)
      setSuggestions(prev => 
        prev.filter(s => s.candidate_db_id !== suggestion.candidate_db_id)
      );
      
      // Track that we've made changes
      setHasMergedControls(true);
    } catch (err: any) {
      console.error('Link instances failed:', err);
      alert(`Link failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setMerging(prev => {
        const next = new Set(prev);
        next.delete(suggestion.candidate_db_id);
        return next;
      });
    }
  };

  const handleMergeAll = async () => {
    const mergeCount = suggestions.filter(s => s.action === 'merge').length;
    const linkCount = suggestions.filter(s => s.action === 'link_as_instances').length;
    
    const confirmed = window.confirm(
      `Process all ${suggestions.length} suggestions?\n` +
      `- ${mergeCount} will be merged (identical controls)\n` +
      `- ${linkCount} will be linked as instances (variants)\n` +
      `\nThis can be undone using Split/Unlink functions.`
    );
    if (!confirmed) return;

    // Process sequentially to avoid overwhelming the backend
    for (const suggestion of suggestions) {
      if (suggestion.action === 'merge') {
        await handleMerge(suggestion);
      } else if (suggestion.action === 'link_as_instances') {
        await handleLinkInstances(suggestion);
      }
    }
    
    // Clear sessionStorage after all merges complete
    sessionStorage.removeItem(storageKey);
  };

  const handleRescan = () => {
    // Clear existing suggestions and fetch fresh ones from backend
    sessionStorage.removeItem(storageKey);
    setSuggestions([]);
    fetchSuggestions();
  };

  const handleIgnore = (suggestion: MergeSuggestion) => {
    // Temporarily remove from display without any backend action
    setSuggestions(prev => 
      prev.filter(s => s.candidate_db_id !== suggestion.candidate_db_id)
    );
  };

  const handleDismiss = async (suggestion: MergeSuggestion) => {
    // Mark as reviewed/dismissed - persist to backend to prevent showing in future scans
    setMerging(prev => new Set([...Array.from(prev), suggestion.candidate_db_id]));
    try {
      await axios.post(APP_CONFIG.apiUrl(`/report/${scanId}/controls/dismiss_merge_suggestion`), {
        control_ids: [suggestion.primary_db_id, suggestion.candidate_db_id],
        reason: `User reviewed ${suggestion.duplicate_type || 'duplicate'} suggestion and accepted as separate controls`
      });
      
      // Remove from suggestions immediately (optimistic update)
      setSuggestions(prev => 
        prev.filter(s => s.candidate_db_id !== suggestion.candidate_db_id)
      );
      
      // Track that we've made changes
      setHasMergedControls(true);
    } catch (err: any) {
      console.error('Dismiss failed:', err);
      alert(`Dismiss failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setMerging(prev => {
        const next = new Set(prev);
        next.delete(suggestion.candidate_db_id);
        return next;
      });
    }
  };

  return (
    <>
      <Tooltip title="View suggested control merges">
        <Chip
          icon={<MergeIcon />}
          label={`${suggestions.length} suggested merge${suggestions.length !== 1 ? 's' : ''}`}
          onClick={() => setDrawerOpen(true)}
          color={suggestions.length > 0 ? 'warning' : 'default'}
          variant={suggestions.length > 0 ? 'filled' : 'outlined'}
          sx={{ ml: 1 }}
        />
      </Tooltip>

      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          // Refresh report data only when drawer closes if changes were made
          if (hasMergedControls && onMergeComplete) {
            setTimeout(() => {
              onMergeComplete();
              setHasMergedControls(false);
            }, 300);
          }
        }}
        PaperProps={{ sx: { width: 1100, p: 2 } }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6">
            Merge Suggestions
            {hasMergedControls && (
              <Typography component="span" variant="caption" sx={{ ml: 1, color: 'success.main' }}>
                (changes pending)
              </Typography>
            )}
          </Typography>
          <IconButton 
            onClick={() => {
              setDrawerOpen(false);
              if (hasMergedControls && onMergeComplete) {
                setTimeout(() => {
                  onMergeComplete();
                  setHasMergedControls(false);
                }, 300);
              }
            }} 
            size="small"
          >
            <CloseIcon />
          </IconButton>
        </Box>

        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress />
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {!loading && suggestions.length === 0 && (
          <Alert severity="info">
            No merge suggestions found. Controls are analyzed for duplicates based on description similarity and framework mappings.
          </Alert>
        )}

        {!loading && suggestions.length > 0 && (
          <>
            <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Button
                variant="contained"
                onClick={handleMergeAll}
                disabled={merging.size > 0}
                startIcon={<MergeIcon />}
              >
                Process All ({suggestions.length})
              </Button>
              <Button
                variant="outlined"
                onClick={handleRescan}
                disabled={loading}
              >
                Rescan
              </Button>
            </Box>
            <Alert severity="info" sx={{ mb: 2 }}>
              <strong>Action Options:</strong>
              <br />• <strong>Ignore:</strong> Remove from this view temporarily (no database changes)
              <br />• <strong>Dismiss:</strong> Accept as separate controls and don't show as merge candidate again
              <br />• <strong>Link:</strong> Keep as separate instances of the same control (for criteria/test variants)
              <br />• <strong>Merge:</strong> Combine into single record (for extraction artifacts/inadvertent splits)
              <br /><em>The report will refresh when you close this panel.</em>
            </Alert>

            <List>
              {suggestions.map((suggestion, idx) => {
                const actionLabel = suggestion.action === 'merge' ? 'Merge' : 
                                   suggestion.action === 'link_as_instances' ? 'Link as Instances' : 
                                   'Review Manually';
                const actionColor = suggestion.action === 'merge' ? 'primary' : 
                                   suggestion.action === 'link_as_instances' ? 'info' : 
                                   'warning';
                const actionIcon = suggestion.action === 'merge' ? <MergeIcon /> : 
                                  suggestion.action === 'link_as_instances' ? <LinkIcon /> : 
                                  null;
                
                return (
                  <React.Fragment key={`${suggestion.primary_db_id}-${suggestion.candidate_db_id}`}>
                    {idx > 0 && <Divider />}
                    <ListItem sx={{ flexDirection: 'column', alignItems: 'flex-start', py: 2 }}>
                      <Box sx={{ width: '100%', mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="subtitle1" fontWeight="bold" sx={{ flex: 1 }}>
                          {suggestion.control_id} - {Math.round(suggestion.merge_confidence * 100)}% confidence
                        </Typography>
                        <Chip 
                          label={suggestion.duplicate_type || 'DUPLICATE'} 
                          size="small" 
                          color={actionColor}
                        />
                      </Box>
                      
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                        Pages: {(suggestion.primary_pages || []).join(', ')} & {(suggestion.candidate_pages || []).join(', ')}
                      </Typography>

                      {suggestion.rationale && (
                        <Alert severity="info" sx={{ width: '100%', mb: 1, py: 0.5 }}>
                          <Typography variant="caption">{suggestion.rationale}</Typography>
                        </Alert>
                      )}

                      <Box sx={{ width: '100%', mb: 2, display: 'flex', gap: 2, maxHeight: '70vh', overflow: 'auto' }}>
                        <Box sx={{ flex: 1, p: 2, border: '2px solid', borderColor: 'primary.main', borderRadius: 1, bgcolor: 'action.hover' }}>
                          <Typography variant="caption" color="primary" fontWeight="bold" display="block" mb={1}>
                            PRIMARY CONTROL
                          </Typography>
                          
                          <Typography variant="caption" color="text.secondary" fontWeight="bold" display="block" mb={0.5}>
                            Description:
                          </Typography>
                          <Typography variant="body2" fontWeight="medium" mb={1.5} sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                            {suggestion.primary_desc}
                          </Typography>
                          
                          {suggestion.primary_test && (
                            <>
                              <Typography variant="caption" color="text.secondary" fontWeight="bold" display="block" mt={2} mb={0.5}>
                                Test Procedure:
                              </Typography>
                              <Typography variant="body2" display="block" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontStyle: 'italic', bgcolor: 'background.paper', p: 1, borderRadius: 1 }}>
                                {suggestion.primary_test}
                              </Typography>
                            </>
                          )}
                          
                          {suggestion.primary_has_deviation && suggestion.primary_deviation && (
                            <>
                              <Typography variant="caption" color="error" fontWeight="bold" display="block" mt={2} mb={0.5}>
                                Deviation/Exception:
                              </Typography>
                              <Typography variant="body2" display="block" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', bgcolor: 'error.light', color: 'error.contrastText', p: 1, borderRadius: 1 }}>
                                {suggestion.primary_deviation}
                              </Typography>
                            </>
                          )}
                        </Box>

                        <Box sx={{ flex: 1, p: 2, border: '2px solid', borderColor: 'warning.main', borderRadius: 1 }}>
                          <Typography variant="caption" color="warning.main" fontWeight="bold" display="block" mb={1}>
                            DUPLICATE CANDIDATE
                          </Typography>
                          
                          <Typography variant="caption" color="text.secondary" fontWeight="bold" display="block" mb={0.5}>
                            Description:
                          </Typography>
                          <Typography variant="body2" fontWeight="medium" mb={1.5} sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                            {suggestion.candidate_desc}
                          </Typography>
                          
                          {suggestion.candidate_test && (
                            <>
                              <Typography variant="caption" color="text.secondary" fontWeight="bold" display="block" mt={2} mb={0.5}>
                                Test Procedure:
                              </Typography>
                              <Typography variant="body2" display="block" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontStyle: 'italic', bgcolor: 'background.paper', p: 1, borderRadius: 1 }}>
                                {suggestion.candidate_test}
                              </Typography>
                            </>
                          )}
                          
                          {suggestion.candidate_has_deviation && suggestion.candidate_deviation && (
                            <>
                              <Typography variant="caption" color="error" fontWeight="bold" display="block" mt={2} mb={0.5}>
                                Deviation/Exception:
                              </Typography>
                              <Typography variant="body2" display="block" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', bgcolor: 'error.light', color: 'error.contrastText', p: 1, borderRadius: 1 }}>
                                {suggestion.candidate_deviation}
                              </Typography>
                            </>
                          )}
                        </Box>
                      </Box>

                      {(suggestion.criteria_differences || suggestion.test_differences || suggestion.deviation_differences) && (
                        <Box sx={{ width: '100%', mb: 1 }}>
                          <Typography variant="caption" color="text.secondary">Differences:</Typography>
                          {suggestion.criteria_differences && (
                            <Typography variant="caption" display="block" sx={{ pl: 1 }}>
                              • <strong>Criteria:</strong> {JSON.stringify(suggestion.criteria_differences)}
                            </Typography>
                          )}
                          {suggestion.test_differences && (
                            <Typography variant="caption" display="block" sx={{ pl: 1 }}>
                              • <strong>Test Procedures:</strong> {suggestion.test_differences.summary || 'See details'}
                            </Typography>
                          )}
                          {suggestion.deviation_differences && (
                            <Typography variant="caption" display="block" sx={{ pl: 1 }}>
                              • <strong>Deviations:</strong> Different deviation status
                            </Typography>
                          )}
                        </Box>
                      )}

                      {suggestion.confidence_breakdown && suggestion.confidence_breakdown.length > 0 && (
                        <Box sx={{ width: '100%', mb: 1 }}>
                          <Typography variant="caption" color="text.secondary">Confidence breakdown:</Typography>
                          {suggestion.confidence_breakdown.map((item, i) => (
                            <Typography key={i} variant="caption" display="block" sx={{ pl: 1 }}>
                              • {item}
                            </Typography>
                          ))}
                        </Box>
                      )}

                      <Box sx={{ display: 'flex', gap: 1, width: '100%', justifyContent: 'flex-end', pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
                        <Tooltip title="Remove from this view without taking action">
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => handleIgnore(suggestion)}
                            disabled={merging.has(suggestion.candidate_db_id)}
                          >
                            Ignore
                          </Button>
                        </Tooltip>
                        <Tooltip title="Accept as separate controls, don't show again">
                          <Button
                            size="small"
                            variant="outlined"
                            color="secondary"
                            onClick={() => handleDismiss(suggestion)}
                            disabled={merging.has(suggestion.candidate_db_id)}
                          >
                            Dismiss
                          </Button>
                        </Tooltip>
                        <Tooltip title="Keep as separate instances of the same control">
                          <Button
                            size="small"
                            variant="contained"
                            color="info"
                            onClick={() => handleLinkInstances(suggestion)}
                            disabled={merging.has(suggestion.candidate_db_id)}
                            startIcon={merging.has(suggestion.candidate_db_id) ? <CircularProgress size={16} /> : <LinkIcon />}
                          >
                            Link
                          </Button>
                        </Tooltip>
                        <Tooltip title="Combine into single record (extraction artifact)">
                          <Button
                            size="small"
                            variant="contained"
                            color="primary"
                            onClick={() => handleMerge(suggestion)}
                            disabled={merging.has(suggestion.candidate_db_id)}
                            startIcon={merging.has(suggestion.candidate_db_id) ? <CircularProgress size={16} /> : <MergeIcon />}
                          >
                            Merge
                          </Button>
                        </Tooltip>
                      </Box>
                    </ListItem>
                  </React.Fragment>
                );
              })}
            </List>
          </>
        )}
      </Drawer>
    </>
  );
};

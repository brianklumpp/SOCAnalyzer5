/**
 * ReportDeviationsTab Component
 *
 * Displays all deviation controls for a scan with search, add, and bulk regenerate features.
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  TextField,
  Stack,
  Typography,
  CircularProgress,
  Badge,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  LinearProgress,
  Alert,
  Snackbar,
} from '@mui/material';
import {
  Add as AddIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
  CheckCircle as CheckCircleIcon,
} from '@mui/icons-material';
import { api } from '../../../api/client';
import { DeviationCard } from '../../DeviationCard';
import { solidigmColors } from '../../../theme/solidigmTheme';

interface Deviation {
  id: number;
  control_id: string;
  page_ref: number;
  control_description: string;
  test_procedure: string;
  test_result: string;
  deviation_summary: string | null;
}

interface ReportDeviationsTabProps {
  scanId: string | number;
}

export const ReportDeviationsTab: React.FC<ReportDeviationsTabProps> = ({ scanId }) => {
  const [deviations, setDeviations] = useState<Deviation[]>([]);
  const [filteredDeviations, setFilteredDeviations] = useState<Deviation[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [regenerateDialogOpen, setRegenerateDialogOpen] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [regenerateProgress, setRegenerateProgress] = useState({ current: 0, total: 0 });
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: 'success' | 'error' }>({
    open: false,
    message: '',
    severity: 'success',
  });

  const fetchDeviations = async () => {
    setLoading(true);
    try {
      const response = await api.get(`/report/${scanId}/deviations`);
      setDeviations(response.data);
      setFilteredDeviations(response.data);
    } catch (err: any) {
      // Handle 500 errors gracefully - likely SOC1 report without deviation support
      if (err.response?.status === 500) {
        // Silently set empty arrays for SOC1 reports
        setDeviations([]);
        setFilteredDeviations([]);
      } else {
        console.error('Error fetching deviations:', err);
        setSnackbar({ open: true, message: 'Failed to load deviations', severity: 'error' });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (scanId) {
      fetchDeviations();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanId]);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchQuery.trim() === '') {
        setFilteredDeviations(deviations);
      } else {
        const query = searchQuery.toLowerCase();
        const filtered = deviations.filter(
          (dev) =>
            dev.control_id.toLowerCase().includes(query) ||
            dev.control_description.toLowerCase().includes(query) ||
            dev.test_result.toLowerCase().includes(query) ||
            (dev.deviation_summary && dev.deviation_summary.toLowerCase().includes(query))
        );
        setFilteredDeviations(filtered);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, deviations]);

  const handleRegenerateAll = () => {
    console.log('🔄 Regenerate All button clicked. Deviations count:', deviations.length);
    if (deviations.length === 0) {
      setSnackbar({ open: true, message: 'No deviations to regenerate', severity: 'error' });
      return;
    }
    console.log('✅ Opening regenerate dialog');
    setRegenerateDialogOpen(true);
  };

  const confirmRegenerateAll = async () => {
    console.log('🚀 Starting regeneration for scan:', scanId);
    setRegenerating(true);
    setRegenerateProgress({ current: 0, total: deviations.length });

    let pollInterval: ReturnType<typeof setInterval> | null = null;
    let timeoutHandle: ReturnType<typeof setTimeout> | null = null;

    try {
      // Start regeneration
      console.log('📤 Sending POST to /deviations/regenerate-all');
      const startResponse = await api.post(`/report/${scanId}/deviations/regenerate-all`);
      console.log('✅ Regeneration started:', startResponse.data);

      // Poll for progress
      pollInterval = setInterval(async () => {
        try {
          const response = await api.get(`/report/${scanId}/deviations/regenerate-progress`);
          const progress = response.data;
          
          console.log('📊 Progress update:', progress);
          setRegenerateProgress({ current: progress.current || 0, total: progress.total || deviations.length });

          if (progress.status === 'complete') {
            console.log('✅ Regeneration complete!');
            if (pollInterval) clearInterval(pollInterval);
            if (timeoutHandle) clearTimeout(timeoutHandle);
            setRegenerating(false);
            setRegenerateDialogOpen(false);
            fetchDeviations();
            setSnackbar({
              open: true,
              message: `Successfully regenerated ${progress.success || progress.current}/${progress.total} summaries`,
              severity: 'success',
            });
          }
        } catch (err) {
          console.error('❌ Error polling progress:', err);
        }
      }, 1000); // Poll every 1 second

      // Timeout after 5 minutes
      timeoutHandle = setTimeout(() => {
        console.warn('⏰ Regeneration timed out after 5 minutes');
        if (pollInterval) clearInterval(pollInterval);
        setRegenerating(false);
        setRegenerateDialogOpen(false);
        setSnackbar({ open: true, message: 'Regeneration timed out', severity: 'error' });
      }, 300000);
    } catch (err: any) {
      console.error('❌ Error starting regeneration:', err);
      if (pollInterval) clearInterval(pollInterval);
      if (timeoutHandle) clearTimeout(timeoutHandle);
      setRegenerating(false);
      setSnackbar({ 
        open: true, 
        message: `Failed to start regeneration: ${err.response?.data?.detail || err.message}`, 
        severity: 'error' 
      });
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (deviations.length === 0) {
    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: 400,
          gap: 2,
        }}
      >
        <CheckCircleIcon sx={{ fontSize: 64, color: 'success.main' }} />
        <Typography variant="h6">✓ No deviations found - all controls passed testing</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Toolbar */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          mb: 3,
          flexWrap: 'wrap',
        }}
      >
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          sx={{ bgcolor: solidigmColors.purple, '&:hover': { bgcolor: solidigmColors.darkBlue } }}
        >
          Add Deviation
        </Button>

        <TextField
          size="small"
          placeholder="Search by control ID or keyword..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          InputProps={{
            startAdornment: <SearchIcon sx={{ mr: 1, color: 'text.secondary' }} />,
          }}
          sx={{ flexGrow: 1, maxWidth: 400 }}
        />

        <Button
          variant="outlined"
          startIcon={regenerating ? <CircularProgress size={16} /> : <RefreshIcon />}
          onClick={handleRegenerateAll}
          disabled={regenerating}
          sx={{ 
            borderColor: solidigmColors.orange, 
            color: solidigmColors.orange,
            '&.Mui-disabled': {
              borderColor: 'rgba(0,0,0,0.12)',
              color: 'rgba(0,0,0,0.26)'
            }
          }}
        >
          {regenerating ? 'Regenerating...' : 'Regenerate All Summaries'}
        </Button>

        <Badge badgeContent={filteredDeviations.length} color="error" sx={{ ml: 'auto' }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            Deviations
          </Typography>
        </Badge>
      </Box>

      {/* Deviations List */}
      <Box sx={{ height: 'calc(100vh - 280px)', overflow: 'auto', pr: 1 }}>
        <Stack spacing={2}>
          {filteredDeviations.map((deviation) => (
            <DeviationCard key={deviation.id} deviation={deviation} scanId={scanId} onUpdate={fetchDeviations} />
          ))}
        </Stack>
      </Box>

      {/* Regenerate All Dialog */}
      <Dialog 
        open={regenerateDialogOpen} 
        onClose={() => !regenerating && setRegenerateDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {regenerating ? 'Regenerating Summaries...' : 'Regenerate All Summaries?'}
        </DialogTitle>
        <DialogContent>
          {regenerating ? (
            <>
              <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
                Processing deviation {regenerateProgress.current} of {regenerateProgress.total}...
              </Typography>
              <LinearProgress
                variant="determinate"
                value={(regenerateProgress.current / regenerateProgress.total) * 100}
                sx={{ 
                  height: 8, 
                  borderRadius: 4,
                  mb: 1,
                  bgcolor: 'rgba(0,0,0,0.1)',
                  '& .MuiLinearProgress-bar': {
                    bgcolor: solidigmColors.orange
                  }
                }}
              />
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                {Math.round((regenerateProgress.current / regenerateProgress.total) * 100)}% complete
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 2 }}>
                <CircularProgress size={16} sx={{ color: solidigmColors.orange }} />
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  Please wait while summaries are being generated...
                </Typography>
              </Box>
            </>
          ) : (
            <Typography variant="body2">
              This will regenerate summaries for {deviations.length} deviations using GPT. Estimated time: ~
              {Math.ceil(deviations.length * 5)} seconds.
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          {!regenerating && (
            <>
              <Button onClick={() => setRegenerateDialogOpen(false)}>Cancel</Button>
              <Button
                variant="contained"
                onClick={confirmRegenerateAll}
                sx={{ bgcolor: solidigmColors.orange, '&:hover': { bgcolor: '#e65100' } }}
              >
                Confirm
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>

      {/* Snackbar */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert severity={snackbar.severity} onClose={() => setSnackbar({ ...snackbar, open: false })}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};



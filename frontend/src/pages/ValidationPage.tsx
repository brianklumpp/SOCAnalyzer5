import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Paper,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Button,
  Alert,
  CircularProgress,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Tooltip
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CompareArrows as CompareIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Delete as DeleteIcon,
  Info as InfoIcon
} from '@mui/icons-material';
import axios from 'axios';
import { APP_CONFIG } from '../config';

interface Scan {
  scan_id: string;
  report_name: string;
  report_type: string;
  progress_status: string;
  as_of_date: string | null;
  created_at: string;
  control_count?: number;
}

interface Baseline {
  baseline_id: string;
  report_name: string;
  extractor_version: string;
  created_at: string;
  metrics: {
    total_controls: number;
    framework_breakdown: Record<string, number>;
    controls_with_assertions: number;
    total_assertions: number;
    ambiguous_count: number;
    partial_extraction_count: number;
  };
}

interface Regression {
  severity: string;
  metric: string;
  message: string;
  current: number;
  baseline: number;
  delta: {
    absolute: number;
    percentage: number;
  };
}

interface ComparisonResult {
  regression_detected: boolean;
  regressions: Regression[];
  current_metrics: any;
  baseline_metrics: any;
  deltas: Record<string, { absolute: number; percentage: number }>;
}

export const ValidationPage: React.FC = () => {
  const [scans, setScans] = useState<Scan[]>([]);
  const [baselines, setBaselines] = useState<Baseline[]>([]);
  const [selectedScan, setSelectedScan] = useState<string>('');
  const [selectedBaseline, setSelectedBaseline] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [createBaselineOpen, setCreateBaselineOpen] = useState(false);
  const [reviewerNotes, setReviewerNotes] = useState('');

  // Load scans on mount
  useEffect(() => {
    loadScans();
    loadBaselines();
  }, []);

  const loadScans = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_BASE}/list_scans`);
      
      // Filter for completed SOC 1 scans
      const completedScans = response.data.filter(
        (scan: Scan) => 
          scan.progress_status === 'completed' &&
          (scan.report_type === 'SOC1' || scan.report_type === 'COMBINED')
      );
      
      setScans(completedScans);
      setError(null);
    } catch (err: any) {
      setError(`Failed to load scans: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const loadBaselines = async () => {
    try {
      const response = await axios.get(`${API_BASE}/baseline/list`);
      setBaselines(response.data);
    } catch (err: any) {
      console.error('Failed to load baselines:', err);
    }
  };

  const handleCreateBaseline = async () => {
    if (!selectedScan) return;

    try {
      setLoading(true);
      const scan = scans.find(s => s.scan_id === selectedScan);
      
      await axios.post(`${API_BASE}/baseline/create`, {
        scan_id: selectedScan,
        extractor_version: 'v4_soc1',
        reviewer_notes: reviewerNotes
      });

      setCreateBaselineOpen(false);
      setReviewerNotes('');
      await loadBaselines();
      setError(null);
      
      // Show success message
      alert(`Baseline created successfully for ${scan?.report_name}`);
    } catch (err: any) {
      setError(`Failed to create baseline: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = async () => {
    if (!selectedScan || !selectedBaseline) return;

    try {
      setLoading(true);
      setComparison(null);
      
      const response = await axios.post(`${API_BASE}/baseline/compare`, {
        scan_id: selectedScan,
        baseline_id: selectedBaseline
      });

      setComparison(response.data);
      setError(null);
    } catch (err: any) {
      setError(`Comparison failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteBaseline = async (baselineId: string) => {
    if (!window.confirm('Are you sure you want to delete this baseline?')) return;

    try {
      await axios.delete(`${API_BASE}/baseline/${baselineId}`);
      await loadBaselines();
      
      if (selectedBaseline === baselineId) {
        setSelectedBaseline('');
        setComparison(null);
      }
    } catch (err: any) {
      setError(`Failed to delete baseline: ${err.message}`);
    }
  };

  const formatDelta = (delta: { absolute: number; percentage: number }) => {
    const sign = delta.absolute >= 0 ? '+' : '';
    const color = Math.abs(delta.percentage) > 5 
      ? (delta.absolute < 0 ? 'error' : 'success')
      : 'default';
    
    return (
      <Chip
        label={`${sign}${delta.absolute} (${delta.percentage.toFixed(1)}%)`}
        color={color}
        size="small"
      />
    );
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'high':
        return <ErrorIcon color="error" />;
      case 'medium':
        return <WarningIcon color="warning" />;
      default:
        return <InfoIcon color="info" />;
    }
  };

  // Get baselines for selected scan's report
  const selectedScanData = scans.find(s => s.scan_id === selectedScan);
  const relevantBaselines = selectedScanData
    ? baselines.filter(b => b.report_name === selectedScanData.report_name)
    : [];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          SOC 1 Validation & Baseline Management
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Compare extraction results against approved baselines to detect regressions
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Selection Controls */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
          <Box sx={{ flex: { xs: '1 1 100%', md: '1 1 40%' } }}>
            <FormControl fullWidth>
              <InputLabel>Select Scan</InputLabel>
              <Select
                value={selectedScan}
                onChange={(e) => {
                  setSelectedScan(e.target.value);
                  setSelectedBaseline('');
                  setComparison(null);
                }}
                label="Select Scan"
              >
                {scans.map(scan => (
                  <MenuItem key={scan.scan_id} value={scan.scan_id}>
                    {scan.report_name} - {scan.report_type} - {new Date(scan.created_at).toLocaleString()}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          <Box sx={{ flex: { xs: '1 1 100%', md: '1 1 40%' } }}>
            <FormControl fullWidth disabled={!selectedScan || relevantBaselines.length === 0}>
              <InputLabel>Select Baseline</InputLabel>
              <Select
                value={selectedBaseline}
                onChange={(e) => setSelectedBaseline(e.target.value)}
                label="Select Baseline"
              >
                {relevantBaselines.map(baseline => (
                  <MenuItem key={baseline.baseline_id} value={baseline.baseline_id}>
                    {baseline.extractor_version} - {new Date(baseline.created_at).toLocaleDateString()} 
                    ({baseline.metrics.total_controls} controls)
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          <Box sx={{ flex: { xs: '1 1 100%', md: '0 1 auto' }, minWidth: { md: '150px' } }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <Button
                variant="contained"
                startIcon={<CompareIcon />}
                onClick={handleCompare}
                disabled={!selectedScan || !selectedBaseline || loading}
                fullWidth
              >
                Compare
              </Button>
              <Button
                variant="outlined"
                startIcon={<CheckIcon />}
                onClick={() => setCreateBaselineOpen(true)}
                disabled={!selectedScan || loading}
                fullWidth
              >
                Create Baseline
              </Button>
            </Box>
          </Box>
        </Box>

        <Box sx={{ mt: 2, display: 'flex', gap: 2 }}>
          <Button
            startIcon={<RefreshIcon />}
            onClick={() => { loadScans(); loadBaselines(); }}
            size="small"
          >
            Refresh Data
          </Button>
          
          {selectedScan && (
            <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center' }}>
              {relevantBaselines.length} baseline(s) available (max 20 per report)
            </Typography>
          )}
        </Box>
      </Paper>

      {/* Comparison Results */}
      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      )}

      {comparison && (
        <>
          {/* Status Banner */}
          <Alert
            severity={comparison.regression_detected ? 'error' : 'success'}
            sx={{ mb: 3 }}
            icon={comparison.regression_detected ? <ErrorIcon /> : <CheckIcon />}
          >
            {comparison.regression_detected
              ? `⚠️ Regressions Detected: ${comparison.regressions.length} issue(s)`
              : '✅ No Regressions - All metrics within acceptable thresholds'}
          </Alert>

          {/* Regressions Table */}
          {comparison.regressions.length > 0 && (
            <Paper sx={{ p: 3, mb: 3 }}>
              <Typography variant="h6" gutterBottom>
                Regression Details
              </Typography>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Severity</TableCell>
                      <TableCell>Metric</TableCell>
                      <TableCell>Message</TableCell>
                      <TableCell>Current</TableCell>
                      <TableCell>Baseline</TableCell>
                      <TableCell>Delta</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {comparison.regressions.map((reg, idx) => (
                      <TableRow key={idx}>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            {getSeverityIcon(reg.severity)}
                            <Typography variant="caption">
                              {reg.severity.toUpperCase()}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>
                          <code>{reg.metric}</code>
                        </TableCell>
                        <TableCell>{reg.message}</TableCell>
                        <TableCell>{reg.current}</TableCell>
                        <TableCell>{reg.baseline}</TableCell>
                        <TableCell>{formatDelta(reg.delta)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          )}

          {/* Metrics Comparison */}
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            <Box sx={{ flex: { xs: '1 1 100%', md: '1 1 45%' } }}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Current Metrics
                  </Typography>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell>Total Controls</TableCell>
                        <TableCell align="right">
                          <strong>{comparison.current_metrics.total_controls}</strong>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>With Assertions</TableCell>
                        <TableCell align="right">
                          {comparison.current_metrics.controls_with_assertions}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Total Assertions</TableCell>
                        <TableCell align="right">
                          {comparison.current_metrics.total_assertions}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Ambiguous</TableCell>
                        <TableCell align="right">
                          {comparison.current_metrics.ambiguous_count}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Partial Extraction</TableCell>
                        <TableCell align="right">
                          {comparison.current_metrics.partial_extraction_count}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>

                  <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
                    Framework Breakdown
                  </Typography>
                  {Object.entries(comparison.current_metrics.framework_breakdown).map(([key, value]) => (
                    <Chip
                      key={key}
                      label={`${key}: ${value}`}
                      size="small"
                      sx={{ mr: 1, mb: 1 }}
                    />
                  ))}
                </CardContent>
              </Card>
            </Box>

            <Box sx={{ flex: { xs: '1 1 100%', md: '1 1 45%' } }}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Baseline Metrics
                  </Typography>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell>Total Controls</TableCell>
                        <TableCell align="right">
                          <strong>{comparison.baseline_metrics.total_controls}</strong>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>With Assertions</TableCell>
                        <TableCell align="right">
                          {comparison.baseline_metrics.controls_with_assertions}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Total Assertions</TableCell>
                        <TableCell align="right">
                          {comparison.baseline_metrics.total_assertions}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Ambiguous</TableCell>
                        <TableCell align="right">
                          {comparison.baseline_metrics.ambiguous_count}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Partial Extraction</TableCell>
                        <TableCell align="right">
                          {comparison.baseline_metrics.partial_extraction_count}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>

                  <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
                    Framework Breakdown
                  </Typography>
                  {Object.entries(comparison.baseline_metrics.framework_breakdown).map(([key, value]) => (
                    <Chip
                      key={key}
                      label={`${key}: ${value}`}
                      size="small"
                      sx={{ mr: 1, mb: 1 }}
                    />
                  ))}
                </CardContent>
              </Card>
            </Box>
          </Box>

          {/* Deltas Summary */}
          <Paper sx={{ p: 3, mt: 3 }}>
            <Typography variant="h6" gutterBottom>
              Metric Deltas
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
              {Object.entries(comparison.deltas).map(([metric, delta]) => (
                <Box key={metric} sx={{ flex: { xs: '1 1 100%', sm: '1 1 45%', md: '1 1 30%' } }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="body2">
                      {metric.replace(/_/g, ' ')}:
                    </Typography>
                    {formatDelta(delta as any)}
                  </Box>
                </Box>
              ))}
            </Box>
          </Paper>
        </>
      )}

      {/* Baseline List */}
      <Paper sx={{ p: 3, mt: 3 }}>
        <Typography variant="h6" gutterBottom>
          Available Baselines
        </Typography>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Report Name</TableCell>
                <TableCell>Version</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="right">Controls</TableCell>
                <TableCell align="right">Assertions</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {baselines.map(baseline => (
                <TableRow key={baseline.baseline_id}>
                  <TableCell>{baseline.report_name}</TableCell>
                  <TableCell>
                    <code>{baseline.extractor_version}</code>
                  </TableCell>
                  <TableCell>
                    {new Date(baseline.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell align="right">
                    {baseline.metrics.total_controls}
                  </TableCell>
                  <TableCell align="right">
                    {baseline.metrics.total_assertions}
                  </TableCell>
                  <TableCell>
                    <Tooltip title="Delete baseline">
                      <IconButton
                        size="small"
                        onClick={() => handleDeleteBaseline(baseline.baseline_id)}
                        color="error"
                      >
                        <DeleteIcon />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
              {baselines.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    <Typography variant="body2" color="text.secondary">
                      No baselines available. Create your first baseline from a validated scan.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {/* Create Baseline Dialog */}
      <Dialog
        open={createBaselineOpen}
        onClose={() => setCreateBaselineOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create Validation Baseline</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Creating a baseline will save the current extraction results as the approved
            standard for comparison. Up to 20 baselines are kept per report (FIFO).
          </Typography>
          
          {selectedScanData && (
            <Alert severity="info" sx={{ mb: 2 }}>
              <strong>Report:</strong> {selectedScanData.report_name}<br />
              <strong>Type:</strong> {selectedScanData.report_type}<br />
              <strong>Scan Date:</strong> {new Date(selectedScanData.created_at).toLocaleString()}
            </Alert>
          )}

          <TextField
            label="Reviewer Notes"
            multiline
            rows={4}
            fullWidth
            value={reviewerNotes}
            onChange={(e) => setReviewerNotes(e.target.value)}
            placeholder="Optional notes about this baseline (e.g., 'Initial validation', 'Updated after prompt tuning')"
            sx={{ mt: 2 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateBaselineOpen(false)}>Cancel</Button>
          <Button
            onClick={handleCreateBaseline}
            variant="contained"
            disabled={loading}
          >
            Create Baseline
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

import React, { useEffect, useState } from 'react';
import { Box, Typography, Paper, TextField, Button, Divider, Chip, Alert, CircularProgress, Switch, FormControlLabel, Table, TableBody, TableCell, TableHead, TableRow, Select, MenuItem, FormControl, InputLabel } from '@mui/material';
import api from '../api/client';

const RUNTIME_URL = '/config/runtime';
const BUDGETS_URL = '/config/budgets';
const SETTINGS_URL = '/settings';
const DOCKER_STATUS_URL = '/docker/status';
const DOCKER_STOP_URL = (name: string) => `/docker/stop/${encodeURIComponent(name)}`;
const DOCKER_RESTART_URL = (name: string) => `/docker/restart/${encodeURIComponent(name)}`;
const DOCKER_START_URL = (name: string) => `/docker/start/${encodeURIComponent(name)}`;
const QUICK_TEST_MODE_URL = '/config/quick-test-mode';
const MAX_CONCURRENT_URL = '/config/max-concurrent-scans';
const TEST_MODELS_URL = '/test/models';
const MODEL_ASSIGNMENTS_URL = '/test/model-assignments';

const Section: React.FC<{ title: string; children: React.ReactNode }>= ({ title, children }) => (
  <Paper sx={{ p: 2, mb: 2 }}>
    <Typography variant="h6" gutterBottom>{title}</Typography>
    {children}
  </Paper>
);

const SettingsPage: React.FC = () => {
  const [runtime, setRuntime] = useState<any>(null);
  const [budgets, setBudgets] = useState<any>(null);
  const [settings, setSettings] = useState<Record<string,string>>({});
  const [docker, setDocker] = useState<{services: {name: string; status: string;}[]} | {error: string} | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingRuntime, setLoadingRuntime] = useState<boolean>(true);
  const [loadingBudgets, setLoadingBudgets] = useState<boolean>(true);
  const [loadingSettings, setLoadingSettings] = useState<boolean>(true);
  const [loadingDocker, setLoadingDocker] = useState<boolean>(true);
  const [quickTestEnabled, setQuickTestEnabled] = useState<boolean>(false);
  const [quickTestMaxControls, setQuickTestMaxControls] = useState<number>(10);
  const [savingQuickTest, setSavingQuickTest] = useState<boolean>(false);
  const [maxConcurrentScans, setMaxConcurrentScans] = useState<number>(1);
  const [savingMaxConcurrent, setSavingMaxConcurrent] = useState<boolean>(false);
  
  // Model configuration state
  const [modelTestResults, setModelTestResults] = useState<any>(null);
  const [modelAssignments, setModelAssignments] = useState<any>(null);
  const [testingModels, setTestingModels] = useState<boolean>(false);
  const [loadingAssignments, setLoadingAssignments] = useState<boolean>(false);
  const [savingAssignments, setSavingAssignments] = useState<boolean>(false);
  const [assignmentChanges, setAssignmentChanges] = useState<Record<string, string>>({});

  const fetchRuntime = async () => {
    setLoadingRuntime(true);
    try {
      const r = await api.get(RUNTIME_URL);
      setRuntime(r.data);
      // Extract quick test mode settings from runtime
      if (r.data?.quick_test) {
        setQuickTestEnabled(r.data.quick_test.enabled || false);
        setQuickTestMaxControls(r.data.quick_test.max_controls || 10);
      }
      // Extract max concurrent scans from runtime
      if (r.data?.queue) {
        setMaxConcurrentScans(r.data.queue.max_concurrent_scans || 1);
      }
    } catch (e: any) {
  const msg = e?.response?.data?.error || e?.message || 'Unknown error';
  setError(prev => [prev, `Runtime: ${msg}`].filter(Boolean).join('\n'));
      setRuntime(null);
    } finally {
      setLoadingRuntime(false);
    }
  };

  const fetchBudgets = async () => {
    setLoadingBudgets(true);
    try {
      const r = await api.get(BUDGETS_URL);
      setBudgets(r.data);
    } catch (e: any) {
  const msg = e?.response?.data?.error || e?.message || 'Unknown error';
  setError(prev => [prev, `Budgets: ${msg}`].filter(Boolean).join('\n'));
      setBudgets(null);
    } finally {
      setLoadingBudgets(false);
    }
  };

  const fetchSettings = async () => {
    setLoadingSettings(true);
    try {
      const r = await api.get(SETTINGS_URL);
      setSettings(r.data || {});
    } catch (e: any) {
  const msg = e?.response?.data?.error || e?.message || 'Unknown error';
  setError(prev => [prev, `Settings: ${msg}`].filter(Boolean).join('\n'));
      setSettings({});
    } finally {
      setLoadingSettings(false);
    }
  };

  const fetchDocker = async () => {
    setLoadingDocker(true);
    try {
      const r = await api.get(DOCKER_STATUS_URL);
      setDocker(r.data);
    } catch (e: any) {
  const msg = e?.response?.data?.error || e?.message || 'Unavailable';
  setDocker({ error: msg });
  setError(prev => [prev, `Docker: ${msg}`].filter(Boolean).join('\n'));
    } finally {
      setLoadingDocker(false);
    }
  };

  const fetchAll = async () => {
    setError(null);
    await Promise.allSettled([fetchRuntime(), fetchBudgets(), fetchSettings(), fetchDocker(), fetchModelAssignments()]);
  };

  useEffect(() => {
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSettingChange = (k: string, v: string) => setSettings(prev => ({...prev, [k]: v }));
  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
  await api.post(SETTINGS_URL, settings);
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.message || 'Failed to save settings';
      setError(msg);
    } finally {
      setSaving(false);
      // refresh budgets/runtime to reflect any changes
      fetchRuntime();
      fetchBudgets();
    }
  };

  const requestDocker = async (url: string) => {
    try {
  await api.post(url);
      await fetchDocker();
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.message || 'Docker action failed';
      setError(msg);
    }
  };

  const handleQuickTestToggle = async () => {
    setSavingQuickTest(true);
    setError(null);
    try {
      const response = await api.post(QUICK_TEST_MODE_URL, {
        enabled: !quickTestEnabled,
        max_controls: quickTestMaxControls
      });
      if (response.data?.requires_restart) {
        setError('✓ Quick Test Mode updated. Backend restart required for changes to take effect.');
      }
      // Update local state
      setQuickTestEnabled(!quickTestEnabled);
      // Refresh runtime to confirm
      await fetchRuntime();
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.message || 'Failed to toggle quick test mode';
      setError(msg);
    } finally {
      setSavingQuickTest(false);
    }
  };

  const handleQuickTestMaxControlsChange = async (newValue: number) => {
    if (newValue < 1) return;
    setQuickTestMaxControls(newValue);
    if (quickTestEnabled) {
      setSavingQuickTest(true);
      setError(null);
      try {
        await api.post(QUICK_TEST_MODE_URL, {
          enabled: true,
          max_controls: newValue
        });
        setError('✓ Max controls updated. Backend restart required for changes to take effect.');
        await fetchRuntime();
      } catch (e: any) {
        const msg = e?.response?.data?.error || e?.message || 'Failed to update max controls';
        setError(msg);
      } finally {
        setSavingQuickTest(false);
      }
    }
  };

  const handleMaxConcurrentChange = async (newValue: number) => {
    if (newValue < 1 || newValue > 10) return;
    setSavingMaxConcurrent(true);
    setError(null);
    try {
      const response = await api.post(MAX_CONCURRENT_URL, {
        max_concurrent: newValue
      });
      setMaxConcurrentScans(newValue);
      if (response.data?.requires_restart === false) {
        setError('✓ Max concurrent scans updated successfully. No restart required.');
      } else {
        setError('✓ Max concurrent scans updated.');
      }
      await fetchRuntime();
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.message || 'Failed to update max concurrent scans';
      setError(msg);
    } finally {
      setSavingMaxConcurrent(false);
    }
  };

  const fetchModelAssignments = async () => {
    setLoadingAssignments(true);
    try {
      const r = await api.get(MODEL_ASSIGNMENTS_URL);
      setModelAssignments(r.data);
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.message || 'Failed to load model assignments';
      setError(msg);
    } finally {
      setLoadingAssignments(false);
    }
  };

  const handleTestModels = async () => {
    setTestingModels(true);
    setError(null);
    try {
      const r = await api.post(TEST_MODELS_URL);
      setModelTestResults(r.data);
      // Also refresh assignments to check availability
      await fetchModelAssignments();
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.message || 'Failed to test models';
      setError(msg);
    } finally {
      setTestingModels(false);
    }
  };

  const handleAssignmentChange = (extractor: string, model: string) => {
    setAssignmentChanges(prev => ({ ...prev, [extractor]: model }));
  };

  const handleSaveAssignments = async () => {
    if (Object.keys(assignmentChanges).length === 0) {
      setError('No changes to save');
      return;
    }
    setSavingAssignments(true);
    setError(null);
    try {
      const r = await api.put(MODEL_ASSIGNMENTS_URL, assignmentChanges);
      if (r.data?.errors && r.data.errors.length > 0) {
        setError(`Saved with errors:\n${r.data.errors.map((e: any) => `${e.extractor}: ${e.error}`).join('\n')}`);
      } else {
        setError(`✓ Successfully updated ${r.data?.updated || 0} model assignment(s)`);
      }
      setAssignmentChanges({});
      await fetchModelAssignments();
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.message || 'Failed to save model assignments';
      setError(msg);
    } finally {
      setSavingAssignments(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', p: 2 }}>
      <Typography variant="h4" gutterBottom>Settings & Runtime</Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 2, whiteSpace: 'pre-wrap' }}>
          {error}
          <Box sx={{ mt: 1 }}>
            <Button size="small" onClick={() => fetchAll()}>Retry</Button>
          </Box>
        </Alert>
      )}

      <Section title="Model & Provider">
        {loadingRuntime ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}><CircularProgress size={20} /> <Typography>Loading runtime…</Typography></Box>
        ) : runtime ? (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
            <Box sx={{ flex: '1 1 300px' }}><TextField label="Default Model" value={runtime.model.default_model} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 300px' }}><TextField label="Provider" value={runtime.model.provider} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 300px' }}><TextField label="Temperature" value={runtime.model.temperature} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 300px' }}><TextField label="Top P" value={runtime.model.top_p} fullWidth disabled /></Box>
          </Box>
        ) : (
          <Alert severity="warning">Runtime information is unavailable. Use Retry to attempt reconnect.</Alert>
        )}
      </Section>

      <Section title="Quick Test Mode">
        <Alert severity="info" sx={{ mb: 2 }}>
          Quick Test Mode extracts only a limited number of controls for faster development testing (typically ~5-10 minutes vs 40+ minutes for full extraction).
        </Alert>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
          <FormControlLabel
            control={
              <Switch
                checked={quickTestEnabled}
                onChange={handleQuickTestToggle}
                disabled={savingQuickTest}
                color="primary"
              />
            }
            label={quickTestEnabled ? "Quick Test Mode Enabled" : "Quick Test Mode Disabled"}
          />
          <TextField
            label="Max Controls to Extract"
            type="number"
            value={quickTestMaxControls}
            onChange={(e) => handleQuickTestMaxControlsChange(parseInt(e.target.value) || 10)}
            disabled={!quickTestEnabled || savingQuickTest}
            sx={{ width: 200 }}
            inputProps={{ min: 1, max: 100 }}
          />
          {quickTestEnabled && (
            <Chip
              label="Backend restart required"
              color="warning"
              size="small"
            />
          )}
        </Box>
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">
            {quickTestEnabled 
              ? `Current: Will extract ${quickTestMaxControls} control${quickTestMaxControls !== 1 ? 's' : ''} per scan`
              : 'Full extraction mode - all controls will be extracted'}
          </Typography>
        </Box>
      </Section>

      <Section title="Queue Settings">
        <Alert severity="info" sx={{ mb: 2 }}>
          Configure the maximum number of scans that can run concurrently. Changes take effect immediately without restart.
        </Alert>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
          <TextField
            label="Max Concurrent Scans"
            type="number"
            value={maxConcurrentScans}
            onChange={(e) => handleMaxConcurrentChange(parseInt(e.target.value) || 1)}
            disabled={savingMaxConcurrent}
            sx={{ width: 200 }}
            inputProps={{ min: 1, max: 10 }}
          />
          {savingMaxConcurrent && <CircularProgress size={20} />}
        </Box>
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">
            Current: Up to {maxConcurrentScans} scan{maxConcurrentScans !== 1 ? 's' : ''} can run simultaneously. Additional scans will queue.
          </Typography>
        </Box>
      </Section>

      <Section title="Model Configuration">
        <Alert severity="info" sx={{ mb: 2 }}>
          Test model availability and assign specific models to different extractors. Changes take effect immediately without restart.
        </Alert>
        
        {/* Warning banner for unavailable models */}
        {modelAssignments?.warnings && modelAssignments.warnings.length > 0 && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>⚠️ Model Availability Issues:</Typography>
            {modelAssignments.warnings.map((w: any, idx: number) => (
              <Typography key={idx} variant="body2">
                • {w.extractor}: {w.message}
              </Typography>
            ))}
          </Alert>
        )}

        {/* Test Models Button */}
        <Box sx={{ mb: 2 }}>
          <Button
            variant="contained"
            onClick={handleTestModels}
            disabled={testingModels}
            sx={{ mr: 2 }}
          >
            {testingModels ? 'Testing Models...' : 'Test Model Availability'}
          </Button>
          {modelTestResults && (
            <Chip
              label={`Last tested: ${new Date(modelTestResults.test_time).toLocaleTimeString()}`}
              size="small"
              color="default"
            />
          )}
        </Box>

        {/* Test Results Table */}
        {modelTestResults && (
          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle2" gutterBottom>Model Test Results</Typography>
            <Paper sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Model</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell align="right">Response Time</TableCell>
                    <TableCell>Cost Tier</TableCell>
                    <TableCell>Speed Tier</TableCell>
                    <TableCell>JSON Valid</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {modelTestResults.results?.map((result: any) => (
                    <TableRow key={result.model}>
                      <TableCell>{result.model}</TableCell>
                      <TableCell>
                        <Chip
                          label={result.available ? 'Available' : 'Unavailable'}
                          color={result.available ? 'success' : 'error'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="right">
                        {result.response_time_ms ? `${result.response_time_ms}ms` : '-'}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={result.cost_tier}
                          size="small"
                          color={result.cost_tier === 'low' ? 'success' : result.cost_tier === 'medium' ? 'warning' : 'default'}
                        />
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={result.speed_tier}
                          size="small"
                          color={result.speed_tier === 'fast' ? 'success' : result.speed_tier === 'medium' ? 'info' : 'default'}
                        />
                      </TableCell>
                      <TableCell>
                        {result.json_valid ? '✓' : result.available ? '✗' : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          </Box>
        )}

        {/* Recommendations */}
        {modelTestResults?.recommendations && Object.keys(modelTestResults.recommendations).length > 0 && (
          <Alert severity="success" sx={{ mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>💡 Recommended Assignments:</Typography>
            {Object.entries(modelTestResults.recommendations).map(([extractor, rec]: [string, any]) => (
              <Typography key={extractor} variant="body2">
                • <strong>{extractor}</strong>: {rec.model} ({rec.reason})
              </Typography>
            ))}
          </Alert>
        )}

        {/* Model Assignments */}
        {loadingAssignments ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={20} /> <Typography>Loading assignments...</Typography>
          </Box>
        ) : modelAssignments ? (
          <Box>
            <Typography variant="subtitle2" gutterBottom>Extractor Model Assignments</Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
              {modelAssignments.assignments?.map((assignment: any) => (
                <Box key={assignment.extractor} sx={{ flex: '1 1 300px' }}>
                  <FormControl fullWidth size="small">
                    <InputLabel>{assignment.extractor}</InputLabel>
                    <Select
                      value={assignmentChanges[assignment.extractor] || assignment.model}
                      onChange={(e) => handleAssignmentChange(assignment.extractor, e.target.value)}
                      label={assignment.extractor}
                    >
                      {modelAssignments.available_models?.map((model: string) => (
                        <MenuItem 
                          key={model} 
                          value={model}
                          disabled={modelTestResults?.results?.find((r: any) => r.model === model)?.available === false}
                        >
                          {model}
                          {modelTestResults?.results?.find((r: any) => r.model === model)?.available === false && ' (unavailable)'}
                          {assignment.model === model && assignment.is_default && ' (default)'}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  {assignment.availability === 'unavailable' && (
                    <Typography variant="caption" color="error">
                      ⚠️ Currently assigned model unavailable
                    </Typography>
                  )}
                </Box>
              ))}
            </Box>
            <Button
              variant="contained"
              onClick={handleSaveAssignments}
              disabled={savingAssignments || Object.keys(assignmentChanges).length === 0}
            >
              {savingAssignments ? 'Saving...' : `Save Changes (${Object.keys(assignmentChanges).length})`}
            </Button>
          </Box>
        ) : (
          <Alert severity="warning">Model assignments unavailable</Alert>
        )}
      </Section>

      <Section title="Token Windows & Budgets">
        {runtime && (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
            <Box sx={{ flex: '1 1 220px' }}><TextField label="Max Total Tokens" value={runtime.token_windows.max_total_tokens} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 220px' }}><TextField label="Max Input Tokens" value={runtime.token_windows.max_input_tokens} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 220px' }}><TextField label="Max Output Tokens" value={runtime.token_windows.max_output_tokens} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 180px' }}><TextField label="System Tokens" value={runtime.budgets.system_tokens} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 180px' }}><TextField label="User Tokens" value={runtime.budgets.user_tokens} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 180px' }}><TextField label="Response Tokens" value={runtime.budgets.response_tokens} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 180px' }}><TextField label="Available Tokens" value={runtime.budgets.available_tokens} fullWidth disabled /></Box>
          </Box>
        )}
        <Divider sx={{ my: 2 }}><Chip label="Computed sizes" /></Divider>
        {loadingBudgets ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}><CircularProgress size={20} /> <Typography>Loading budgets…</Typography></Box>
        ) : budgets ? (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
            <Box sx={{ flex: '1 1 240px' }}><TextField label="Default Chunk Size" value={budgets.derived_chunk_sizes.default} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 240px' }}><TextField label="Primary Chunk Size" value={budgets.derived_chunk_sizes.primary} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 240px' }}><TextField label="Description Chunk Size" value={budgets.derived_chunk_sizes.description} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 240px' }}><TextField label="Subservice Chunk Size" value={budgets.derived_chunk_sizes.subservice} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 240px' }}><TextField label="Text Overlap" value={budgets.overlap_chars} fullWidth disabled /></Box>
            <Box sx={{ flex: '1 1 240px' }}><TextField label="Chars per Token" value={budgets.chars_per_token} fullWidth disabled /></Box>
          </Box>
        ) : (
          <Alert severity="warning">Budget information is unavailable. Use Retry to attempt reconnect.</Alert>
        )}
      </Section>

      <Section title="Application Settings (non-env)">
        {loadingSettings ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}><CircularProgress size={20} /> <Typography>Loading settings…</Typography></Box>
        ) : (
          <>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
              {Object.entries(settings).map(([key, val]) => (
                <Box sx={{ flex: '1 1 340px' }} key={key}>
                  <TextField label={key} value={val} onChange={e => handleSettingChange(key, e.target.value)} fullWidth />
                </Box>
              ))}
            </Box>
            <Box sx={{ mt: 2 }}>
              <Button variant="contained" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save Settings'}</Button>
            </Box>
          </>
        )}
      </Section>

      <Section title="Docker Services">
        {runtime?.feature_toggles?.docker_control_enabled === false && (
          <Alert severity="info" sx={{ mb: 2 }}>Docker control is disabled by server configuration.</Alert>
        )}
        {loadingDocker ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}><CircularProgress size={20} /> <Typography>Loading docker status…</Typography></Box>
        ) : (
          <>
            {docker && 'services' in docker && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                {docker.services
                  .slice()
                  .sort((a: any,b: any) => a.name.localeCompare(b.name))
                  .map((svc: any) => (
                  <Paper key={svc.name} sx={{ p: 2, flex: '1 1 280px' }}>
                    <Typography variant="subtitle1">{svc.name}</Typography>
                    <Box sx={{ mb: 1 }}>
                      {(() => {
                        const raw = (svc.status || '').toString();
                        const isUp = raw.toLowerCase().includes('up');
                        return (
                          <Chip
                            label={raw || 'Unknown'}
                            color={isUp ? 'success' : undefined}
                            sx={{
                              backgroundColor: isUp ? 'success.main' : undefined,
                              color: isUp ? '#fff' : undefined,
                              fontWeight: 500,
                            }}
                          />
                        );
                      })()}
                    </Box>
                    {(() => {
                      const isUp = typeof svc.status === 'string' && svc.status.toLowerCase().includes('up');
                      const isFrontend = svc.name === 'socanalyzer-frontend';
                      return (
                        <Box>
                          <Button
                            size="small"
                            variant="outlined"
                            color="error"
                            sx={{ mr: 1 }}
                            disabled={!isUp || isFrontend}
                            onClick={() => requestDocker(DOCKER_STOP_URL(svc.name))}
                          >
                            Stop
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            sx={{ mr: 1 }}
                            disabled={!isUp}
                            onClick={() => requestDocker(DOCKER_RESTART_URL(svc.name))}
                          >
                            Restart
                          </Button>
                          {!isUp && (
                            <Button
                              size="small"
                              variant="contained"
                              onClick={() => requestDocker(DOCKER_START_URL(svc.name))}
                            >
                              Start
                            </Button>
                          )}
                        </Box>
                      );
                    })()}
                  </Paper>
                ))}
              </Box>
            )}
            {docker && 'error' in docker && (
              <Alert severity="warning">{(docker as any).error}</Alert>
            )}
          </>
        )}
      </Section>
    </Box>
  );
};

export default SettingsPage;

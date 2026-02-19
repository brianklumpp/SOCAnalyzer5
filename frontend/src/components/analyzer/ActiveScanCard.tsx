import React from 'react';
import {
  Card,
  CardContent,
  Box,
  Typography,
  LinearProgress,
  Chip,
  IconButton,
  Tooltip,
  Stack,
  Divider,
  Alert
} from '@mui/material';
import CancelIcon from '@mui/icons-material/Cancel';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import QueueIcon from '@mui/icons-material/Queue';
import PriorityHighIcon from '@mui/icons-material/PriorityHigh';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import BusinessIcon from '@mui/icons-material/Business';
import DescriptionIcon from '@mui/icons-material/Description';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import DateRangeIcon from '@mui/icons-material/DateRange';
import AssessmentIcon from '@mui/icons-material/Assessment';

interface ActiveScanCardProps {
  jobId: string;
  filename: string;
  reportType: string;
  status: 'RUNNING' | 'QUEUED' | 'PAUSED';
  priority: number; // 1=high, 2=medium, 3=low
  position: number; // 0=running, 1+=queued
  progress: number; // 0-100
  elapsedSeconds?: number;
  identifiedEntities?: {
    report_type?: string;
    company?: string;
    company_logo_url?: string;
    auditor?: string;
    product?: string;
  };
  detectedSubtype?: string;
  reportDate?: string;
  coveragePeriod?: string;
  counters?: {
    controls_count?: number;
    controls_total_estimate?: number;
    controls_percent?: number;
    controls_mapped_count?: number;
    controls_mapped_percent?: number;
    objectives_count?: number;
    objectives_percent?: number;
    cuecs_count?: number;
    subservice_orgs_count?: number;
  };
  error?: string;
  gptServiceWarning?: boolean;
  onCancel: (jobId: string) => void;
  onPause?: (jobId: string) => void;
  onResume?: (jobId: string) => void;
  onClick?: (jobId: string) => void;
}

const ActiveScanCard: React.FC<ActiveScanCardProps> = ({
  jobId,
  filename,
  reportType,
  status,
  priority,
  position,
  progress,
  elapsedSeconds,
  identifiedEntities,
  detectedSubtype,
  reportDate,
  coveragePeriod,
  counters,
  error,
  gptServiceWarning,
  onCancel,
  onPause,
  onResume,
  onClick
}) => {
  // Priority configuration
  const priorityConfig = {
    1: { label: 'High', color: 'error' as const, icon: <PriorityHighIcon fontSize="small" /> },
    2: { label: 'Medium', color: 'warning' as const, icon: null },
    3: { label: 'Low', color: 'default' as const, icon: null }
  };

  // Status configuration
  const statusConfig = {
    RUNNING: { label: 'Running', color: 'success' as const, icon: <PlayArrowIcon fontSize="small" /> },
    QUEUED: { label: `Queue #${position}`, color: 'info' as const, icon: <QueueIcon fontSize="small" /> },
    PAUSED: { label: 'Paused', color: 'warning' as const, icon: null }
  };

  const priorityInfo = priorityConfig[priority as 1 | 2 | 3] || priorityConfig[2];
  const statusInfo = statusConfig[status] || statusConfig.QUEUED;

  // Format elapsed time
  const formatElapsed = (seconds?: number): string => {
    if (!seconds) return '0s';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  // Calculate extraction stats
  const controlsProgress = counters?.controls_count && counters?.controls_total_estimate
    ? `${counters.controls_count}/${counters.controls_total_estimate}`
    : counters?.controls_count
    ? `${counters.controls_count}`
    : '0';

  return (
    <Card
      sx={{
        minHeight: 180,
        position: 'relative',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.2s',
        '&:hover': onClick ? {
          transform: 'translateY(-2px)',
          boxShadow: 4
        } : {},
        border: status === 'RUNNING' ? 2 : 1,
        borderColor: status === 'RUNNING' ? 'success.main' : 'divider'
      }}
      onClick={() => onClick?.(jobId)}
    >
      <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
        {/* GPT Service Warning Banner */}
        {gptServiceWarning && (
          <Alert severity="warning" sx={{ mb: 1, py: 0.5 }}>
            <strong>⚠️ GPT Service Degraded</strong>
            <br />
            The AI service is experiencing issues. Retries are happening automatically.
          </Alert>
        )}

        {/* Error Banner */}
        {error && (
          <Alert severity="error" sx={{ mb: 1, py: 0.5 }}>
            <strong>Analysis Failed</strong>
            <br />
            {error}
          </Alert>
        )}

        {/* Header: Filename, Status, and Actions */}
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
          <Box flex={1} mr={1}>
            <Tooltip title={filename}>
              <Typography variant="subtitle1" noWrap sx={{ fontWeight: 600, fontSize: '1rem' }}>
                {filename}
              </Typography>
            </Tooltip>
            <Stack direction="row" spacing={1} mt={0.5}>
              <Chip
                label={statusInfo.label}
                color={statusInfo.color}
                size="small"
                {...(statusInfo.icon && { icon: statusInfo.icon })}
              />
              <Chip
                label={priorityInfo.label}
                color={priorityInfo.color}
                size="small"
                {...(priorityInfo.icon && { icon: priorityInfo.icon })}
              />
              {elapsedSeconds !== undefined && (
                <Chip
                  label={formatElapsed(elapsedSeconds)}
                  size="small"
                  icon={<AccessTimeIcon fontSize="small" />}
                  variant="outlined"
                />
              )}
            </Stack>
          </Box>
          {/* Company Logo in upper right corner */}
          {identifiedEntities?.company_logo_url && (
            <Box
              component="img"
              src={identifiedEntities.company_logo_url}
              alt="Company logo"
              sx={{
                width: 48,
                height: 48,
                objectFit: 'contain',
                borderRadius: 1,
                backgroundColor: 'background.paper',
                border: '1px solid',
                borderColor: 'divider',
                mr: 1
              }}
              onError={(e) => {
                // Hide image if it fails to load
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
          )}
          <Stack direction="row" spacing={0.5}>
            {/* Pause/Resume button - only for RUNNING scans */}
            {status === 'RUNNING' && onPause && (
              <Tooltip title="Pause scan">
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    onPause(jobId);
                  }}
                  sx={{ color: 'warning.main' }}
                >
                  <PauseIcon />
                </IconButton>
              </Tooltip>
            )}
            {status === 'PAUSED' && onResume && (
              <Tooltip title="Resume scan">
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    onResume(jobId);
                  }}
                  sx={{ color: 'success.main' }}
                >
                  <PlayArrowIcon />
                </IconButton>
              </Tooltip>
            )}
            <Tooltip title="Cancel scan">
              <IconButton
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  onCancel(jobId);
                }}
                sx={{ color: 'error.main' }}
              >
                <CancelIcon />
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>

        {/* Overall Progress */}
        <Box mb={1}>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.25}>
            <Typography variant="caption" color="text.secondary" fontWeight={500}>
              Overall Progress
            </Typography>
            <Typography variant="caption" fontWeight={600} color="primary">
              {progress}%
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={progress}
            sx={{
              height: 6,
              borderRadius: 1,
              backgroundColor: 'action.hover',
              '& .MuiLinearProgress-bar': {
                borderRadius: 1
              }
            }}
          />
        </Box>



        <Divider sx={{ my: 1 }} />

        {/* Report Information Section */}
        <Box mb={1}>
          <Typography variant="caption" color="text.secondary" gutterBottom sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
            📄 Report Information
          </Typography>
          <Stack spacing={0.5} sx={{ mt: 0.5 }}>
            {/* Company Name - First */}
            {identifiedEntities?.company && (
              <Box display="flex" alignItems="center" gap={0.5}>
                {identifiedEntities.company_logo_url ? (
                  <Box
                    component="img"
                    src={identifiedEntities.company_logo_url}
                    alt={`${identifiedEntities.company} logo`}
                    sx={{
                      width: 20,
                      height: 20,
                      objectFit: 'contain',
                      borderRadius: 0.5
                    }}
                    onError={(e: React.SyntheticEvent<HTMLImageElement>) => {
                      e.currentTarget.style.display = 'none';
                      e.currentTarget.nextElementSibling?.removeAttribute('style');
                    }}
                  />
                ) : null}
                <BusinessIcon 
                  fontSize="small" 
                  sx={{ 
                    color: 'text.secondary',
                    display: identifiedEntities.company_logo_url ? 'none' : 'block'
                  }} 
                />
                <Typography variant="body2" color="text.primary" noWrap>
                  {identifiedEntities.company}
                </Typography>
              </Box>
            )}
            {/* Product - Second */}
            {identifiedEntities?.product && (
              <Box display="flex" alignItems="center" gap={0.5}>
                <DescriptionIcon fontSize="small" sx={{ color: 'text.secondary' }} />
                <Typography variant="body2" color="text.primary" noWrap>
                  Product: {identifiedEntities.product}
                </Typography>
              </Box>
            )}
            {/* Report Type - Third */}
            {identifiedEntities?.report_type && (
              <Box display="flex" alignItems="center" gap={0.5}>
                <AssessmentIcon fontSize="small" sx={{ color: 'text.secondary' }} />
                <Typography variant="body2" color="text.primary" fontWeight={500}>
                  {identifiedEntities.report_type}
                  {detectedSubtype && ` ${detectedSubtype}`}
                </Typography>
              </Box>
            )}
            {reportDate && (
              <Box display="flex" alignItems="center" gap={0.5}>
                <CalendarTodayIcon fontSize="small" sx={{ color: 'text.secondary' }} />
                <Typography variant="body2" color="text.primary">
                  Report Date: {reportDate}
                </Typography>
              </Box>
            )}
            {coveragePeriod && (
              <Box display="flex" alignItems="center" gap={0.5}>
                <DateRangeIcon fontSize="small" sx={{ color: 'text.secondary' }} />
                <Typography variant="body2" color="text.primary">
                  Coverage: {coveragePeriod}
                </Typography>
              </Box>
            )}
            {identifiedEntities?.auditor && (
              <Box display="flex" alignItems="center" gap={0.5}>
                <AccountBalanceIcon fontSize="small" sx={{ color: 'text.secondary' }} />
                <Typography variant="body2" color="text.primary" noWrap>
                  {identifiedEntities.auditor}
                </Typography>
              </Box>
            )}
          </Stack>
        </Box>

        {/* Extraction Progress Section */}
        {counters && (
          <>
            <Divider sx={{ my: 2 }} />
            <Box>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom sx={{ fontWeight: 600 }}>
                🔍 Extraction Progress
              </Typography>
              <Stack spacing={1.5} sx={{ mt: 1 }}>
                {/* Controls */}
                {(counters.controls_count !== undefined && (counters.controls_count > 0 || counters.controls_percent !== undefined && counters.controls_percent > 0)) && (
                  <Box>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                      <Typography variant="body2" color="text.secondary">
                        Extracting Controls
                      </Typography>
                      <Typography variant="body2" fontWeight={600}>
                        {counters.controls_percent ? `${counters.controls_percent}%` : `${counters.controls_count} extracted`}
                      </Typography>
                    </Box>
                    {counters.controls_total_estimate && counters.controls_percent !== undefined && (
                      <LinearProgress
                        variant="determinate"
                        value={Math.min(counters.controls_percent, 100)}
                        sx={{
                          height: 4,
                          borderRadius: 1,
                          backgroundColor: 'action.hover',
                          '& .MuiLinearProgress-bar': {
                            borderRadius: 1,
                            backgroundColor: 'success.main'
                          }
                        }}
                      />
                    )}
                  </Box>
                )}
                
                {/* Framework Mapping */}
                {counters.controls_mapped_count !== undefined && counters.controls_mapped_count > 0 && (
                  <Box>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                      <Typography variant="body2" color="text.secondary">
                        Framework Mapping
                      </Typography>
                      <Typography variant="body2" fontWeight={600}>
                        {counters.controls_mapped_percent ? `${counters.controls_mapped_percent}%` : `${counters.controls_mapped_count} mapped`}
                      </Typography>
                    </Box>
                    {counters.controls_mapped_percent !== undefined && (
                      <LinearProgress
                        variant="determinate"
                        value={Math.min(counters.controls_mapped_percent, 100)}
                        sx={{
                          height: 4,
                          borderRadius: 1,
                          backgroundColor: 'action.hover',
                          '& .MuiLinearProgress-bar': {
                            borderRadius: 1,
                            backgroundColor: 'info.main'
                          }
                        }}
                      />
                    )}
                  </Box>
                )}
                
                {/* Control Objectives */}
                {((counters.objectives_count !== undefined && counters.objectives_count > 0) || progress >= 90) && (
                  <Box>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                      <Typography variant="body2" color="text.secondary">
                        {(() => {
                          if (progress >= 100) return '✓ Control Objectives';
                          if (progress >= 98) return 'Identifying Objective Gaps';
                          if (progress >= 95) return 'Mapping Objectives to Controls';
                          if (progress >= 92) return 'Extracting Control Objectives';
                          return 'Control Objectives';
                        })()}
                      </Typography>
                      <Typography variant="body2" fontWeight={600}>
                        {counters.objectives_count ? `${counters.objectives_count} found` : progress >= 92 ? 'in progress...' : ''}
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={progress >= 100 ? 100 : (counters.objectives_percent ?? (counters.objectives_count ? 50 : 0))}
                      sx={{
                        height: 4,
                        borderRadius: 1,
                        backgroundColor: 'action.hover',
                        '& .MuiLinearProgress-bar': {
                          borderRadius: 1,
                          backgroundColor: progress >= 100 ? 'success.main' : 'warning.main'
                        }
                      }}
                    />
                  </Box>
                )}
                
                {/* CUECs */}
                {counters.cuecs_count !== undefined && counters.cuecs_count > 0 && (
                  <Box>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                      <Typography variant="body2" color="text.secondary">
                        CUECs (User Entity Controls)
                      </Typography>
                      <Typography variant="body2" fontWeight={600}>
                        {counters.cuecs_count} found
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={100}
                      sx={{
                        height: 4,
                        borderRadius: 1,
                        backgroundColor: 'action.hover',
                        '& .MuiLinearProgress-bar': {
                          borderRadius: 1,
                          backgroundColor: 'secondary.main'
                        }
                      }}
                    />
                  </Box>
                )}
                
                {/* Subservice Organizations */}
                {counters.subservice_orgs_count !== undefined && counters.subservice_orgs_count > 0 && (
                  <Box>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                      <Typography variant="body2" color="text.secondary">
                        Subservice Organizations
                      </Typography>
                      <Typography variant="body2" fontWeight={600}>
                        {counters.subservice_orgs_count} found
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={100}
                      sx={{
                        height: 4,
                        borderRadius: 1,
                        backgroundColor: 'action.hover',
                        '& .MuiLinearProgress-bar': {
                          borderRadius: 1,
                          backgroundColor: '#8d6e63'
                        }
                      }}
                    />
                  </Box>
                )}
              </Stack>
            </Box>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default ActiveScanCard;

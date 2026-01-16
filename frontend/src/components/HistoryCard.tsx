/**
 * HistoryCard Component
 * 
 * Material-UI Card component for displaying scan history with company information,
 * coverage dates, and scan metadata. Features hover effects and navigation.
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  CardContent,
  Avatar,
  Typography,
  Box,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Button,
} from '@mui/material';
import {
  Business as BusinessIcon,
  CalendarToday as CalendarIcon,
  Assessment as ReportIcon,
  Schedule as ClockIcon,
  Delete as DeleteIcon,
} from '@mui/icons-material';
import { solidigmColors } from '../theme/solidigmTheme';

// TypeScript interfaces
export interface CompanyInfo {
  name: string;
  logo_url?: string | null;
  domain?: string;
}

export interface ScanData {
  id: number | string;
  filename: string;
  company?: CompanyInfo | null;
  coverage_start_date?: string | null;
  coverage_end_date?: string | null;
  report_date?: string | null;
  report_type?: string;
  scan_timestamp?: string;
  created_at?: string;
  elapsed_seconds?: number | null;
  product?: string; // Add optional product field
}

interface HistoryCardProps {
  scan: ScanData;
  onDelete?: (scanId: number | string) => void;
}

/**
 * Format date string to localized format
 */
const formatDate = (dateString?: string | null, includeTime: boolean = false): string => {
  if (!dateString) return 'N/A';
  
  try {
    let date: Date;
    
    // Check if it's a date-only string (YYYY-MM-DD format)
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
      // Parse as local date to avoid timezone shifts
      const [year, month, day] = dateString.split('-').map(Number);
      date = new Date(year, month - 1, day);
    } else {
      // Parse as full datetime (will include timezone if present)
      date = new Date(dateString);
    }
    
    if (includeTime) {
      return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
        timeZoneName: 'short',
      });
    }
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch (error) {
    console.error('Error formatting date:', error);
    return 'Invalid Date';
  }
};

/**
 * Get company initials for avatar fallback
 */
const getCompanyInitials = (companyName?: string): string => {
  if (!companyName) return '?';
  
  const words = companyName.trim().split(/\s+/);
  if (words.length === 1) {
    return words[0].substring(0, 2).toUpperCase();
  }
  return (words[0][0] + words[1][0]).toUpperCase();
};

/**
 * Format elapsed time in human-readable format
 */
const formatElapsedTime = (seconds?: number | null): string => {
  if (!seconds || seconds <= 0) return 'N/A';
  
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  
  if (mins === 0) {
    return `${secs}s`;
  } else if (secs === 0) {
    return `${mins}m`;
  } else {
    return `${mins}m ${secs}s`;
  }
};

/**
 * HistoryCard Component
 */
export const HistoryCard: React.FC<HistoryCardProps> = ({ scan, onDelete }) => {
  const navigate = useNavigate();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  
  // Handle both nested (scan.company.name) and flat (scan.company as string) formats
  const companyName = typeof scan.company === 'object' && scan.company?.name 
    ? scan.company.name 
    : typeof scan.company === 'string' 
    ? scan.company 
    : 'Unknown Company';
  
  const logoUrl = typeof scan.company === 'object' ? scan.company?.logo_url : (scan as any).logo_url;
  const companyDomain = typeof scan.company === 'object' ? scan.company?.domain : (scan as any).company_domain;
  const companyInitials = getCompanyInitials(companyName);
  
  const coverageStart = formatDate((scan as any).coverage_start || scan.coverage_start_date);
  const coverageEnd = formatDate((scan as any).coverage_end || scan.coverage_end_date);
  const reportDate = formatDate(scan.report_date);
  const scanDate = formatDate((scan as any).timestamp || scan.scan_timestamp || scan.created_at, true);
  const elapsedTime = formatElapsedTime((scan as any).elapsed_seconds || scan.elapsed_seconds);
  
  // Format report type from enum (SOC1, SOC2, COMBINED) to display string
  const formatReportType = (type: string) => {
    if (type === 'SOC1') return 'SOC 1 Type 2';
    if (type === 'SOC2') return 'SOC 2 Type 2';
    if (type === 'COMBINED') return 'Combined SOC 1+2';
    return 'SOC 2 Type 2';
  };
  const reportTypeEnum = scan.report_type || 'SOC2';
  const reportType = formatReportType(reportTypeEnum);
  
  // Get color for report type badge
  const getReportTypeColor = (type: string) => {
    switch (type) {
      case 'SOC1':
        return solidigmColors.teal;
      case 'SOC2':
        return solidigmColors.purple;
      case 'COMBINED':
        return solidigmColors.orange;
      default:
        return solidigmColors.mediumGray;
    }
  };

  const handleClick = () => {
    navigate(`/app/report/${scan.id}`);
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click navigation
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (onDelete) {
      onDelete(scan.id);
    }
    setDeleteDialogOpen(false);
  };

  const handleDeleteCancel = () => {
    setDeleteDialogOpen(false);
  };

  const product = scan.product || 'Unknown Product'; // Default if product is not provided

  return (
    <Card
      onClick={handleClick}
      sx={{
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        cursor: 'pointer',
        transition: 'all 0.3s ease-in-out',
        elevation: 3,
        '&:hover': {
          elevation: 12,
          transform: 'translateY(-4px)',
          boxShadow: `0 12px 28px rgba(79, 0, 181, 0.25)`,
        },
        borderRadius: 2,
        border: `2px solid ${solidigmColors.purple}`,
        boxShadow: `0 4px 12px rgba(79, 0, 181, 0.15)`,
      }}
      elevation={3}
    >
      <CardContent sx={{ 
        p: 1.5, 
        display: 'flex',
        flexDirection: 'column',
        '&:last-child': { pb: 1.5 }, 
        position: 'relative',
        overflow: 'visible',
      }}>
        {/* Delete Button */}
        <IconButton
          onClick={handleDeleteClick}
          sx={{
            position: 'absolute',
            top: 8,
            right: 8,
            color: solidigmColors.mediumGray,
            '&:hover': {
              color: '#d32f2f',
              bgcolor: 'rgba(211, 47, 47, 0.08)',
            },
            zIndex: 10,
          }}
          size="small"
        >
          <DeleteIcon sx={{ fontSize: '1.1rem' }} />
        </IconButton>

        {/* Company Header */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mb: 1,
            pb: 1,
            borderBottom: `2px solid ${solidigmColors.purple}`,
          }}
        >
          <Avatar
            src={logoUrl || undefined}
            alt={companyName}
            sx={{
              width: 48,
              height: 48,
              bgcolor: logoUrl ? 'transparent' : solidigmColors.purple,
              color: 'white',
              fontSize: '1rem',
              fontWeight: 'bold',
            }}
          >
            {!logoUrl && companyInitials}
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 0, pr: 4 }}>
            <Typography
              variant="subtitle2"
              component="div"
              sx={{
                fontWeight: 600,
                fontSize: '0.875rem',
                lineHeight: 1.3,
                color: solidigmColors.darkBlue,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {companyName}
            </Typography>
            {companyDomain && (
              <Typography
                variant="caption"
                sx={{
                  fontSize: '0.7rem',
                  lineHeight: 1.2,
                  color: solidigmColors.mediumGray,
                  display: 'block',
                }}
              >
                {companyDomain}
              </Typography>
            )}
          </Box>
        </Box>

        {/* Scan Details */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          {/* Product Info */}
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75 }}>
            <BusinessIcon
              sx={{ color: solidigmColors.purple, fontSize: '1rem', mt: 0.25 }}
            />
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="caption" sx={{ fontSize: '0.7rem', lineHeight: 1.2, color: solidigmColors.mediumGray, display: 'block' }}>
                Product
              </Typography>
              <Typography variant="body2" sx={{ fontSize: '0.8rem', lineHeight: 1.3, fontWeight: 500 }}>
                {product}
              </Typography>
            </Box>
          </Box>

          {/* Coverage Period */}
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75 }}>
            <CalendarIcon
              sx={{ color: solidigmColors.teal, fontSize: '1rem', mt: 0.25 }}
            />
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="caption" sx={{ fontSize: '0.7rem', lineHeight: 1.2, color: solidigmColors.mediumGray, display: 'block' }}>
                Coverage Period
              </Typography>
              <Typography variant="body2" sx={{ fontSize: '0.8rem', lineHeight: 1.3, fontWeight: 500 }}>
                {coverageStart} - {coverageEnd}
              </Typography>
            </Box>
          </Box>

          {/* Report Date */}
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75 }}>
            <ReportIcon
              sx={{ color: solidigmColors.orange, fontSize: '1rem', mt: 0.25 }}
            />
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="caption" sx={{ fontSize: '0.7rem', lineHeight: 1.2, color: solidigmColors.mediumGray, display: 'block' }}>
                Report Date
              </Typography>
              <Typography variant="body2" sx={{ fontSize: '0.8rem', lineHeight: 1.3, fontWeight: 500 }}>
                {reportDate}
              </Typography>
            </Box>
          </Box>

          {/* Scan Date */}
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75 }}>
            <ClockIcon
              sx={{ color: solidigmColors.purple, fontSize: '1rem', mt: 0.25 }}
            />
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="caption" sx={{ fontSize: '0.7rem', lineHeight: 1.2, color: solidigmColors.mediumGray, display: 'block' }}>
                Scanned On
              </Typography>
              <Typography variant="body2" sx={{ fontSize: '0.8rem', lineHeight: 1.3, fontWeight: 500 }}>
                {scanDate}
              </Typography>
            </Box>
          </Box>

          {/* Elapsed Time */}
          {elapsedTime !== 'N/A' && (
            <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75 }}>
              <ClockIcon
                sx={{ color: solidigmColors.teal, fontSize: '1rem', mt: 0.25 }}
              />
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Typography variant="caption" sx={{ fontSize: '0.7rem', lineHeight: 1.2, color: solidigmColors.mediumGray, display: 'block' }}>
                  Processing Time
                </Typography>
                <Typography variant="body2" sx={{ fontSize: '0.8rem', lineHeight: 1.3, fontWeight: 500 }}>
                  {elapsedTime}
                </Typography>
              </Box>
            </Box>
          )}
        </Box>

        {/* Filename and Report Type */}
        <Box sx={{ 
          mt: 1,
          pt: 1, 
          borderTop: `1px solid ${solidigmColors.lightGray}`, 
          display: 'flex', 
          gap: 1, 
          flexWrap: 'wrap', 
          alignItems: 'center',
        }}>
          <Chip
            icon={<BusinessIcon sx={{ fontSize: '0.875rem' }} />}
            label={scan.filename}
            size="small"
            sx={{
              flex: 1,
              minWidth: 0,
              height: '24px',
              fontSize: '0.75rem',
              '& .MuiChip-label': {
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                px: 1,
              },
              bgcolor: `${solidigmColors.purple}10`,
              color: solidigmColors.purple,
              fontWeight: 500,
            }}
          />
          <Chip
            label={reportType}
            size="small"
            sx={{
              height: '24px',
              fontSize: '0.75rem',
              fontWeight: 600,
              bgcolor: getReportTypeColor(reportTypeEnum),
              color: 'white',
              '& .MuiChip-label': {
                px: 1,
              },
            }}
          />
        </Box>
      </CardContent>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteDialogOpen}
        onClose={handleDeleteCancel}
        onClick={(e) => e.stopPropagation()} // Prevent card click
      >
        <DialogTitle sx={{ color: solidigmColors.darkBlue }}>
          Delete Scan Report?
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to delete the scan for <strong>{companyName}</strong> ({scan.filename})?
            <br /><br />
            This will permanently delete the scan and all associated data including controls, CUECs, and subservice organizations.
            This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button 
            onClick={handleDeleteCancel}
            sx={{ color: solidigmColors.mediumGray }}
          >
            Cancel
          </Button>
          <Button 
            onClick={handleDeleteConfirm}
            variant="contained"
            color="error"
            autoFocus
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};

export default HistoryCard;

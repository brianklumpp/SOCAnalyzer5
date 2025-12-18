import React from 'react';
import { Box, Chip, Tooltip } from '@mui/material';
import { 
  Lock as LockIcon,
  Warning as WarningIcon,
  Star as StarIcon,
  AttachMoney as AttachMoneyIcon,
  Business as BusinessIcon,
  Security as SecurityIcon,
  Description as DescriptionIcon
} from '@mui/icons-material';

interface FrameworkMatch {
  id: string;
  confidence: number;
  reasoning?: string;
  aspect_addressed?: string;
  keywords_matched?: string[];
  deviation?: string | null;
}

interface FrameworkCriteria {
  framework_name: string;
  display_name: string;
  color: string;
  icon: string;
  sections?: any;
}

interface UniversalFrameworkMapperProps {
  control: any;
  activeFrameworks?: string[];
  frameworkCriteria: { [key: string]: FrameworkCriteria };
  onOpenMappingDetails: (control: any, frameworkType: string) => void;
}

// Icon mapping for framework types
const getFrameworkIcon = (iconName: string) => {
  const iconMap: { [key: string]: React.ReactElement } = {
    'lock': <LockIcon sx={{ fontSize: 16 }} />,
    'attach_money': <AttachMoneyIcon sx={{ fontSize: 16 }} />,
    'business': <BusinessIcon sx={{ fontSize: 16 }} />,
    'security': <SecurityIcon sx={{ fontSize: 16 }} />,
    'description': <DescriptionIcon sx={{ fontSize: 16 }} />,
  };
  return iconMap[iconName] || <SecurityIcon sx={{ fontSize: 16 }} />;
};

/**
 * Universal Framework Mapper Component
 * 
 * Displays framework mappings as clickable chips for any framework type.
 * Replaces the old TSC/COSO-specific FrameworkMappingInfo component.
 * 
 * Features:
 * - Dynamic chip display from framework_mappings JSON
 * - Framework-specific colors and icons
 * - Primary framework indicator (gold border + star)
 * - Deviation warnings
 * - Empty state for unmapped controls
 * - Click to open detailed mapping modal
 */
export const UniversalFrameworkMapper: React.FC<UniversalFrameworkMapperProps> = ({ 
  control, 
  activeFrameworks,
  frameworkCriteria,
  onOpenMappingDetails 
}) => {
  // Get framework mappings from control
  const frameworkMappings = control?.framework_mappings || {};
  const primaryFramework = control?.primary_framework;
  
  // Get list of frameworks that have mappings
  const mappedFrameworks = Object.keys(frameworkMappings).filter(
    fw => Array.isArray(frameworkMappings[fw]) && frameworkMappings[fw].length > 0
  );

  // Empty state - no mappings
  if (mappedFrameworks.length === 0) {
    return (
      <Tooltip title="No framework mappings found. Click Recompute to generate mappings.">
        <Chip
          icon={<WarningIcon sx={{ fontSize: 16 }} />}
          label="Not Mapped"
          size="small"
          sx={{ 
            backgroundColor: 'rgba(156, 163, 175, 0.2)',
            color: '#9CA3AF',
            fontSize: '0.75rem',
            height: 24,
            cursor: 'default'
          }}
        />
      </Tooltip>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, alignItems: 'center' }}>
      {mappedFrameworks.map((frameworkName) => {
        const mappings: FrameworkMatch[] = frameworkMappings[frameworkName] || [];
        const criteria = frameworkCriteria[frameworkName];
        const isPrimary = frameworkName === primaryFramework;
        const hasDeviations = mappings.some(m => m.deviation != null && m.deviation !== '');
        
        // Fallback if criteria not loaded
        const displayName = criteria?.display_name || frameworkName;
        const color = criteria?.color || '#1976d2';
        const icon = criteria?.icon || 'security';

        return (
          <Tooltip 
            key={frameworkName}
            title={
              isPrimary 
                ? `${displayName} - Primary Framework (Highest Confidence) - ${mappings.length} mapping${mappings.length !== 1 ? 's' : ''}`
                : `${displayName} - ${mappings.length} mapping${mappings.length !== 1 ? 's' : ''}. Click to view details.`
            }
          >
            <Chip
              icon={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25 }}>
                  {isPrimary && <StarIcon sx={{ fontSize: 14, color: '#FFD700' }} />}
                  {getFrameworkIcon(icon)}
                </Box>
              }
              label={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <span>{displayName}</span>
                  <span style={{ fontWeight: 600 }}>({mappings.length})</span>
                  {hasDeviations && <WarningIcon sx={{ fontSize: 14, color: '#FF9800' }} />}
                </Box>
              }
              size="small"
              onClick={() => onOpenMappingDetails(control, frameworkName)}
              sx={{
                backgroundColor: `${color}20`,
                color: color,
                fontSize: '0.75rem',
                height: 26,
                cursor: 'pointer',
                border: isPrimary ? `2px solid #FFD700` : `1px solid ${color}40`,
                fontWeight: isPrimary ? 600 : 400,
                '&:hover': {
                  backgroundColor: `${color}30`,
                  transform: 'translateY(-1px)',
                  boxShadow: `0 2px 4px ${color}40`
                },
                transition: 'all 0.2s ease-in-out'
              }}
            />
          </Tooltip>
        );
      })}
    </Box>
  );
};

export default UniversalFrameworkMapper;

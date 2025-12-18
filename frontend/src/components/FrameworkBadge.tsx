/**
 * FrameworkBadge Component
 * 
 * Displays framework category badges for controls and scans.
 * Supports SOC1, SOC2, COMBINED, AMBIGUOUS, PARTIAL_EXTRACTION.
 */

import React from 'react';
import { Chip, ChipProps } from '@mui/material';

type FrameworkType = 'SOC1' | 'SOC2' | 'COMBINED' | 'AMBIGUOUS' | 'PARTIAL_EXTRACTION' | string;

interface FrameworkBadgeProps {
  framework: FrameworkType;
  size?: 'small' | 'medium';
  variant?: ChipProps['variant'];
}

const FRAMEWORK_CONFIG: { [key: string]: { label: string; color: ChipProps['color'] } } = {
  SOC1: { label: 'SOC 1', color: 'primary' },
  SOC2: { label: 'SOC 2', color: 'secondary' },
  COMBINED: { label: 'Combined', color: 'info' },
  AMBIGUOUS: { label: 'Ambiguous', color: 'warning' },
  PARTIAL_EXTRACTION: { label: 'Partial', color: 'error' },
};

export const FrameworkBadge: React.FC<FrameworkBadgeProps> = ({
  framework,
  size = 'small',
  variant = 'filled'
}) => {
  const config = FRAMEWORK_CONFIG[framework] || { label: framework, color: 'default' as ChipProps['color'] };

  return (
    <Chip
      label={config.label}
      size={size}
      color={config.color}
      variant={variant}
      sx={{ fontSize: size === 'small' ? '0.75rem' : '0.875rem', fontWeight: 500 }}
    />
  );
};

export default FrameworkBadge;

/**
 * FinancialAssertionBadges Component
 * 
 * Displays SOC 1 financial assertions with confidence scores and reasoning.
 * Shows badges for 22 ICFR assertion categories.
 */

import React from 'react';
import { Box, Chip, Tooltip, Typography } from '@mui/material';

interface FinancialAssertion {
  code: string;
  confidence: number;
  reasoning?: string;
}

interface FinancialAssertionBadgesProps {
  assertions: FinancialAssertion[];
  maxDisplay?: number;
}

const ASSERTION_NAMES: { [key: string]: string } = {
  EO: 'Existence/Occurrence',
  C: 'Completeness',
  A: 'Accuracy',
  CO: 'Cutoff',
  CL: 'Classification',
  E: 'Existence',
  R: 'Rights/Obligations',
  CV: 'Completeness/Valuation',
  OC: 'Occurrence',
  CD: 'Completeness (Disclosures)',
  CU: 'Understandability',
  AV: 'Accuracy/Valuation',
  REV: 'Revenue Recognition',
  AP: 'Accounts Payable',
  AR: 'Accounts Receivable',
  INV: 'Inventory',
  PPE: 'Property/Plant/Equipment',
  PAY: 'Payroll',
  CASH: 'Cash/Cash Equivalents',
  JE: 'Journal Entries',
  FR: 'Financial Reporting',
  TAX: 'Tax Compliance'
};

export const FinancialAssertionBadges: React.FC<FinancialAssertionBadgesProps> = ({
  assertions,
  maxDisplay = 5
}) => {
  if (!assertions || assertions.length === 0) {
    return <Typography variant="caption" color="text.secondary">No assertions mapped</Typography>;
  }

  const sortedAssertions = [...assertions].sort((a, b) => b.confidence - a.confidence);
  const displayAssertions = sortedAssertions.slice(0, maxDisplay);
  const remaining = sortedAssertions.length - maxDisplay;

  const getConfidenceColor = (confidence: number): 'success' | 'warning' | 'error' | 'default' => {
    if (confidence >= 0.80) return 'success';
    if (confidence >= 0.60) return 'warning';
    if (confidence >= 0.40) return 'error';
    return 'default';
  };

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
      {displayAssertions.map((assertion, idx) => {
        const fullName = ASSERTION_NAMES[assertion.code] || assertion.code;
        const tooltipText = `${fullName}\nConfidence: ${(assertion.confidence * 100).toFixed(0)}%${
          assertion.reasoning ? `\n${assertion.reasoning}` : ''
        }`;

        return (
          <Tooltip key={idx} title={tooltipText} arrow>
            <Chip
              label={`${assertion.code} (${(assertion.confidence * 100).toFixed(0)}%)`}
              size="small"
              color={getConfidenceColor(assertion.confidence)}
              sx={{ fontSize: '0.75rem' }}
            />
          </Tooltip>
        );
      })}
      {remaining > 0 && (
        <Tooltip title={`${remaining} more assertion${remaining > 1 ? 's' : ''}`}>
          <Chip
            label={`+${remaining}`}
            size="small"
            variant="outlined"
            sx={{ fontSize: '0.75rem' }}
          />
        </Tooltip>
      )}
    </Box>
  );
};

export default FinancialAssertionBadges;

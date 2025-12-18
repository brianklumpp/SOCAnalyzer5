import { useState, useEffect, useCallback } from 'react';
import api from '../../api/client';
import { EXEC_SUMMARY_PATH } from '../../config/report/constants';

interface UseExecutiveSummaryReturn {
  executiveSummary: any;
  executiveSummaryStale: boolean;
  executiveSummaryLoading: boolean;
  setExecutiveSummary: React.Dispatch<React.SetStateAction<any>>;
  setExecutiveSummaryStale: React.Dispatch<React.SetStateAction<boolean>>;
  regenerateSummary: (scanId: string) => Promise<void>;
  saveSummary: (scanId: string, summary: any) => Promise<{success: boolean}>;
}

export function useExecutiveSummary(scanId: string | undefined): UseExecutiveSummaryReturn {
  const [executiveSummary, setExecutiveSummary] = useState<any>(null);
  const [executiveSummaryStale, setExecutiveSummaryStale] = useState(false);
  const [executiveSummaryLoading, setExecutiveSummaryLoading] = useState(false);

  useEffect(() => {
    if (!scanId) return;
    setExecutiveSummaryLoading(true);
    // Longer timeout for executive summary (30 seconds) - should return cached version quickly
    api.get(`/report/${scanId}/${EXEC_SUMMARY_PATH}`, { timeout: 30000 })
      .then(res => {
        setExecutiveSummary(res.data.executive_summary || null);
        setExecutiveSummaryStale(res.data.is_stale || false);
        setExecutiveSummaryLoading(false);
      })
      .catch(err => {
        console.error('Failed to load executive summary:', err);
        setExecutiveSummaryLoading(false);
      });
  }, [scanId]);

  const regenerateSummary = useCallback(async (scanId: string) => {
    setExecutiveSummaryLoading(true);
    try {
      const res = await api.post(`/report/${scanId}/${EXEC_SUMMARY_PATH}/regenerate`, {}, { timeout: 120000 });
      setExecutiveSummary(res.data.executive_summary);
      setExecutiveSummaryStale(false);
      setExecutiveSummaryLoading(false);
    } catch (err) {
      console.error('Failed to regenerate executive summary:', err);
      setExecutiveSummaryLoading(false);
      throw err;
    }
  }, []);

  const saveSummary = useCallback(async (scanId: string, summary: any) => {
    try {
      await api.patch(`/report/${scanId}/${EXEC_SUMMARY_PATH}`, { executive_summary: summary });
      setExecutiveSummary(summary);
      return { success: true };
    } catch (err) {
      console.error('Failed to save executive summary:', err);
      throw err;
    }
  }, []);

  return {
    executiveSummary,
    executiveSummaryStale,
    executiveSummaryLoading,
    setExecutiveSummary,
    setExecutiveSummaryStale,
    regenerateSummary,
    saveSummary
  };
}

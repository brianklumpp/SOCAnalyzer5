import { useState, useEffect, useCallback } from 'react';
import api from '../../api/client';
import { API_URL } from '../../config/report/constants';

interface UseReportDataReturn {
  report: any;
  setReport: React.Dispatch<React.SetStateAction<any>>;
  loading: boolean;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  refreshReport: (scanId: string) => Promise<void>;
}

export function useReportData(scanId: string | undefined): UseReportDataReturn {
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const refreshReport = useCallback(async (id: string) => {
    setLoading(true);
    try {
      // Use longer timeout for initial report load (60 seconds instead of default 6)
      const res = await api.get(`${API_URL}${id}`, { timeout: 60000 });
      setReport(res.data);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load report:', err);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!scanId) return;
    refreshReport(scanId);
  }, [scanId, refreshReport]);

  return {
    report,
    setReport,
    loading,
    setLoading,
    refreshReport
  };
}

// Helpers to normalize report fields across varying schemas

export function getCoverageStart(report: any): string | null {
  if (!report) return null;
  return (
    report.coverage_start ||
    report?.coverage_period?.start ||
    report?.coverage_period?.start_date ||
    report.start_date ||
    null
  );
}

export function getCoverageEnd(report: any): string | null {
  if (!report) return null;
  return (
    report.coverage_end ||
    report?.coverage_period?.end ||
    report?.coverage_period?.end_date ||
    report.end_date ||
    null
  );
}

export function getReportDate(report: any): string | null {
  if (!report) return null;
  // report_date might be a string or an object with a 'date' property
  const rd = report.report_date;
  if (!rd) return null;
  if (typeof rd === 'string') return rd;
  if (typeof rd?.date === 'string') return rd.date;
  return null;
}

// Normalized scan date (timestamp) from report objects with varying shapes
export function getScanDate(report: any): string | null {
  if (!report) return null;
  // Try common variants
  return (
    report.scan_date ||
    report.scanDate ||
    report.timestamp ||
    report.created_at ||
    report.createdAt ||
    null
  );
}

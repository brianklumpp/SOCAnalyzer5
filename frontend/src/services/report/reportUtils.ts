/**
 * Report Utility Functions
 * 
 * Helper functions for report data processing.
 */

/**
 * Deduplicate CUECs based on ID and description
 */
export function deduplicateCuecs(cuecs: any[]): any[] {
  const seen = new Set<string>();
  return cuecs.filter(cuec => {
    const key = `${cuec.cuec_id || cuec.id}-${cuec.cuec_description}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

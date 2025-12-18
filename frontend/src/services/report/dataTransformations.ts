// Data transformation utilities for report processing

export const normalizeConfidence = (val: any): number | undefined => {
  if (val == null) return val;
  if (typeof val === 'number') {
    // If a user typed 95, assume 95%
    return val > 1 ? val / 100 : val;
  }
  if (typeof val === 'string') {
    const s = val.trim();
    if (s.endsWith('%')) {
      const n = parseFloat(s.replace('%', ''));
      return isNaN(n) ? undefined : n / 100;
    }
    const n = parseFloat(s);
    if (isNaN(n)) return undefined;
    return n > 1 ? n / 100 : n;
  }
  return undefined;
};

export const filterLowConfidence = (arr: any[], key = "confidence", threshold = 0.75) => 
  arr.filter(item => {
    // Include items with low confidence OR items that have been merged away (secondary controls)
    const confidence = item[key] ?? 1;
    const isMergedSecondary = item.merged_to_control_id != null;
    return confidence < threshold || isMergedSecondary;
  });

export const filterHighConfidence = (arr: any[], key = "confidence", threshold = 0.75) => 
  arr.filter(item => {
    // Include items with high confidence that haven't been merged away (primary controls only)
    const confidence = item[key] ?? 1;
    const isPrimary = item.merged_to_control_id == null;
    return confidence >= threshold && isPrimary;
  });

export const parseMapping = (mapping: any): Array<{id: string; confidence: number; reasoning: string; deviation?: string}> => {
  if (Array.isArray(mapping)) return mapping;
  if (typeof mapping === 'string') {
    try {
      const parsed = JSON.parse(mapping);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
};

export const processCuecData = (row: any) => {
  let newRow = { ...row };
  
  // If cuec_confidence_justification is present, re-stringify as JSON array
  if (typeof newRow.cuec_confidence_justification === 'string') {
    let arr: string[] = [];
    try {
      arr = JSON.parse(newRow.cuec_confidence_justification);
      if (!Array.isArray(arr)) throw new Error();
    } catch {
      arr = newRow.cuec_confidence_justification
        .split(/[\n,]/)
        .map((s: string) => s.trim())
        .filter((s: string) => s.length > 0);
    }
    newRow.cuec_confidence_justification = JSON.stringify(arr);
  } else if (Array.isArray(newRow.cuec_confidence_justification)) {
    newRow.cuec_confidence_justification = JSON.stringify(newRow.cuec_confidence_justification);
  }
  
  // Convert percentage-like values to normalized numbers for database
  if (typeof newRow.cuec_confidence === 'string') {
    const s = newRow.cuec_confidence.trim();
    if (s.endsWith('%')) {
      const n = parseFloat(s.replace('%', ''));
      if (!isNaN(n)) newRow.cuec_confidence = n / 100;
    } else {
      const n = parseFloat(s);
      if (!isNaN(n)) newRow.cuec_confidence = n > 1 ? n / 100 : n;
    }
  } else if (typeof newRow.cuec_confidence === 'number') {
    newRow.cuec_confidence = newRow.cuec_confidence > 1 ? newRow.cuec_confidence / 100 : newRow.cuec_confidence;
  }
  
  // Only include fields backend supports for CUEC PATCH
  const payload: any = {};
  if (newRow.cuec_confidence !== undefined) payload.cuec_confidence = newRow.cuec_confidence;
  if (newRow.cuec_confidence_justification !== undefined) payload.cuec_confidence_justification = newRow.cuec_confidence_justification;
  if (newRow.annotation !== undefined) payload.annotation = newRow.annotation;
  if (newRow.analyst_notes !== undefined) payload.analyst_notes = newRow.analyst_notes;
  if (newRow.edit_log !== undefined) payload.edit_log = newRow.edit_log;
  if (newRow.control_strength !== undefined) payload.control_strength = newRow.control_strength;
  if (newRow.cuec_description !== undefined) payload.cuec_description = newRow.cuec_description;
  if (newRow.cuec_gpt_reasoning !== undefined) payload.cuec_gpt_reasoning = newRow.cuec_gpt_reasoning;
  if (newRow.cuec_justification !== undefined) payload.cuec_justification = newRow.cuec_justification;
  return payload;
};

// Duplicate name detection helpers
export const normalizeSoName = (s: string | null | undefined) => (s || '').trim().toLowerCase();

export const isDuplicateSoName = (name: string | null | undefined, highConfNameCounts: Map<string, number>) => {
  const key = normalizeSoName(name);
  return key ? ((highConfNameCounts.get(key) || 0) > 1) : false;
};

export const computeHighConfNameCounts = (highConfSubOrgs: any[]) => {
  const m = new Map<string, number>();
  (highConfSubOrgs || []).forEach((so: any) => {
    const key = normalizeSoName(so?.name);
    if (!key) return;
    m.set(key, (m.get(key) || 0) + 1);
  });
  return m;
};

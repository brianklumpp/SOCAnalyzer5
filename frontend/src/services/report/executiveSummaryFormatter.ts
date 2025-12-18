/**
 * Executive Summary Formatter
 * 
 * Formats executive summary data (JSON or legacy string format) into rich HTML.
 * Handles SOX-specific sections, recommendations categorization, and deviation display.
 */

/**
 * Format executive summary data to rich HTML
 * Supports both legacy string format and new JSON structure
 */
export function formatExecutiveSummaryRich(summaryData: any, filteredHighConfControls: any[]): string {
  if (!summaryData) return '';
  
  // Attempt to parse JSON if the summary is a JSON string
  if (typeof summaryData === 'string') {
    const raw = summaryData.trim();
    let cleaned = raw;
    if (cleaned.startsWith('```json')) cleaned = cleaned.slice(7);
    else if (cleaned.startsWith('```')) cleaned = cleaned.slice(3);
    if (cleaned.endsWith('```')) cleaned = cleaned.slice(0, -3);
    const looksLikeJson = cleaned.startsWith('{') && cleaned.endsWith('}');
    if (looksLikeJson) {
      try {
        const parsed = JSON.parse(cleaned);
        summaryData = parsed;
      } catch {
        // fall through to legacy string formatting
      }
    }
  }

  // If still a string (legacy format), handle it the old way
  if (typeof summaryData === 'string') {
    return formatLegacyStringSummary(summaryData);
  }
  
  // Handle new JSON format
  return formatJsonSummary(summaryData, filteredHighConfControls);
}

/**
 * Format legacy string-based executive summary
 */
function formatLegacyStringSummary(text: string): string {
  // Bold **text** anywhere in the string
  text = text.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
  
  // Extract sections by headings
  const sectionRegex = /(?:About the Company|Key Findings|Areas of Concern|Recommendations)/gi;
  const sections: Record<string, string> = {};
  let current = '';
  let buffer: string[] = [];

  const lines = text.split('\n');
  for (const line of lines) {
    const match = line.match(sectionRegex);
    if (match) {
      if (current && buffer.length > 0) {
        sections[current] = buffer.join('\n').trim();
      }
      current = match[0];
      buffer = [];
    } else if (current) {
      buffer.push(line);
    }
  }
  if (current && buffer.length > 0) {
    sections[current] = buffer.join('\n').trim();
  }

  // Format sections, split Recommendations into two blocks heuristically
  let html = '';
  for (const [heading, content] of Object.entries(sections)) {
    if (!content.trim()) continue;
    if (/^Recommendations$/i.test(heading)) {
      html += formatRecommendationsSplit(content);
    } else {
      html += `<div class="exec-section"><h4>${heading}</h4><div class="exec-content">${content.replace(/\n/g, '<br>')}</div></div>`;
    }
  }
  
  return html;
}

/**
 * Format JSON-structured executive summary
 */
function formatJsonSummary(summaryData: any, filteredHighConfControls: any[]): string {
  let html = '';
  
  if (summaryData.about_company) {
    html += `<div class="exec-section"><h4>About the Company</h4><div class="exec-content">${summaryData.about_company}</div></div>`;
  }
  
  // SOX-specific Objective section
  if (summaryData.sox_objective) {
    html += `<div class="exec-section"><h4>Objective (SOX Review)</h4><div class="exec-content">${summaryData.sox_objective}</div></div>`;
  }
  
  if (summaryData.key_findings && Array.isArray(summaryData.key_findings)) {
    html += `<div class="exec-section"><h4>Key Findings</h4><div class="exec-content"><ul>`;
    summaryData.key_findings.forEach((finding: string) => {
      html += `<li>${finding}</li>`;
    });
    html += `</ul></div></div>`;
  }
  
  if (summaryData.areas_of_concern && Array.isArray(summaryData.areas_of_concern)) {
    html += `<div class="exec-section"><h4>Areas of Concern</h4><div class="exec-content"><ul>`;
    summaryData.areas_of_concern.forEach((concern: string) => {
      html += `<li>${concern}</li>`;
    });
    html += `</ul></div></div>`;
  }
  
  // Handle recommendations (split or unified)
  html += formatRecommendationsJson(summaryData);
  
  // SOX-specific Assessor's Conclusion section
  if (summaryData.sox_assessors_conclusion) {
    html += formatSoxConclusion(summaryData.sox_assessors_conclusion);
  }
  
  // Optional unknown coverage gaps
  if (Array.isArray(summaryData.unknown_coverage_gaps) && summaryData.unknown_coverage_gaps.length > 0) {
    html += `<div class="exec-section"><h4>Unknown Coverage Gaps</h4><div class="exec-content"><ul>`;
    summaryData.unknown_coverage_gaps.forEach((g: string) => { html += `<li>${g}</li>`; });
    html += `</ul></div></div>`;
  }
  
  // Derive deviations from high-confidence controls
  html += formatDeviations(filteredHighConfControls);
  
  return html;
}

/**
 * Split recommendations by contract vs risk keywords
 */
function formatRecommendationsSplit(content: string): string {
  const lines = content.split(/\n+/).map(s => s.trim()).filter(Boolean);
  const contractKeywords = /(contract|dpa|data processing agreement|sla|service level|audit right|right to audit|agreement|clause|obligation|amend|negotiate|penalt|indemn|liabilit|term|notice|consent)/i;
  const riskKeywords = /(implement|monitor|segmentation|mfa|logging|minimiz|hardening|review|validate|backup|classification|restriction|alert|detect|configure|policy|procedure|control|test|assess|encrypt)/i;
  const risk: string[] = [];
  const contract: string[] = [];
  
  lines.forEach(item => {
    if (contractKeywords.test(item)) contract.push(item);
    else if (riskKeywords.test(item)) risk.push(item);
    else risk.push(item);
  });
  
  let html = '';
  if (risk.length > 0) {
    html += `<div class="exec-section"><h4>Recommendations — Risk Mitigations (Customer-Actionable)</h4><div class="exec-content"><ul>${risk.map(i => `<li>${i}</li>`).join('')}</ul></div></div>`;
  }
  if (contract.length > 0) {
    html += `<div class="exec-section"><h4>Recommendations — Contract Enhancements</h4><div class="exec-content"><ul>${contract.map(i => `<li>${i}</li>`).join('')}</ul></div></div>`;
  }
  
  return html;
}

/**
 * Format recommendations from JSON (with split support)
 */
function formatRecommendationsJson(summaryData: any): string {
  let riskRecs = Array.isArray(summaryData.recommendations_risk_mitigations) ? summaryData.recommendations_risk_mitigations : [];
  let contractRecs = Array.isArray(summaryData.recommendations_contract_enhancements) ? summaryData.recommendations_contract_enhancements : [];
  
  // If no split recommendations, try to derive from legacy single list
  if ((riskRecs.length === 0 && contractRecs.length === 0) && Array.isArray(summaryData.recommendations)) {
    const legacy: string[] = summaryData.recommendations.filter((x: any) => typeof x === 'string');
    const contractKeywords = /(contract|dpa|data processing agreement|sla|service level|audit right|right to audit|agreement|clause|obligation|amend|negotiate|penalt|indemn|liabilit|term|notice|consent)/i;
    const riskKeywords = /(implement|monitor|segmentation|mfa|logging|minimiz|hardening|review|validate|backup|classification|restriction|alert|detect|configure|policy|procedure|control|test|assess|encrypt)/i;
    const tmpRisk: string[] = [];
    const tmpContract: string[] = [];
    
    legacy.forEach((item: string) => {
      if (contractKeywords.test(item)) tmpContract.push(item);
      else if (riskKeywords.test(item)) tmpRisk.push(item);
      else tmpRisk.push(item);
    });
    
    if (tmpRisk.length > 0 || tmpContract.length > 0) {
      riskRecs = tmpRisk;
      contractRecs = tmpContract;
    }
  }
  
  let html = '';
  if (riskRecs.length > 0 || contractRecs.length > 0) {
    if (riskRecs.length > 0) {
      html += `<div class="exec-section"><h4>Recommendations — Risk Mitigations (Customer-Actionable)</h4><div class="exec-content"><ul>`;
      riskRecs.forEach((r: string) => { html += `<li>${r}</li>`; });
      html += `</ul></div></div>`;
    }
    if (contractRecs.length > 0) {
      html += `<div class="exec-section"><h4>Recommendations — Contract Enhancements</h4><div class="exec-content"><ul>`;
      contractRecs.forEach((r: string) => { html += `<li>${r}</li>`; });
      html += `</ul></div></div>`;
    }
  } else if (summaryData.recommendations && Array.isArray(summaryData.recommendations)) {
    // Fallback to legacy single list
    html += `<div class="exec-section"><h4>Recommendations</h4><div class="exec-content"><ul>`;
    summaryData.recommendations.forEach((recommendation: string) => {
      html += `<li>${recommendation}</li>`;
    });
    html += `</ul></div></div>`;
  }
  
  return html;
}

/**
 * Format SOX Assessor's Conclusion section
 */
function formatSoxConclusion(conclusion: any): string {
  let html = `<div class="exec-section"><h4>Assessor's Conclusion (SOX Review)</h4><div class="exec-content">`;
  
  if (conclusion.adequacy) {
    html += `<div style="margin-bottom: 12px;"><strong>Adequacy of Control Coverage:</strong><br>${conclusion.adequacy}</div>`;
  }
  
  if (conclusion.operating_effectiveness) {
    html += `<div style="margin-bottom: 12px;"><strong>Operating Effectiveness:</strong><br>${conclusion.operating_effectiveness}</div>`;
  }
  
  if (conclusion.material_weaknesses) {
    html += `<div style="margin-bottom: 12px;"><strong>Material Weaknesses:</strong><br>${conclusion.material_weaknesses}</div>`;
  }
  
  html += `</div></div>`;
  return html;
}

/**
 * Format deviations from high-confidence controls
 * Extracts deviation text from control_test_results field
 */
function formatDeviations(filteredHighConfControls: any[]): string {
  const negPatterns = [
    /no\s+deviation(s)?\s+noted/i,
    /no\s+exception(s)?\s+noted/i,
    /none\s+noted/i,
    /no\s+issues?\s+noted/i,
    /no\s+finding(s)?/i,
    /no\s+error(s)?\s+noted/i
  ];
  const isNegative = (s: string) => negPatterns.some(p => p.test((s || '').toLowerCase()));
  const norm = (s: string) => (s || '').trim().toLowerCase().replace(/\s+/g, ' ');

  // Helper to extract deviation text from control_test_results (fallback)
  const extractDeviation = (testResults: string): string => {
    if (!testResults) return '';
    
    // Look for "Deviation noted." followed by the actual deviation text
    const deviationMatch = testResults.match(/Deviation noted\.\s*(.+?)(?:\n\n|$)/is);
    if (deviationMatch && deviationMatch[1]) {
      return deviationMatch[1].trim();
    }
    
    // Fallback: if "deviation" appears, extract sentence containing it
    if (/deviation|exception/i.test(testResults)) {
      const sentences = testResults.split(/(?<=[.!?])\s+/);
      const devSentence = sentences.find(s => /deviation|exception/i.test(s));
      if (devSentence) return devSentence.trim();
    }
    
    return '';
  };

  const computed: Array<{ control_id: string; deviation_summary: string }> = (filteredHighConfControls || [])
    .filter((c: any) => c && c.has_deviation === true)
    .map((c: any) => {
      // Use deviation_desc if available, otherwise extract from test results
      let deviationText = (c.deviation_desc || '').trim();
      if (!deviationText) {
        deviationText = extractDeviation(c.control_test_results || c.test_results || '');
      }
      return { control_id: String(c.control_id), deviation_summary: deviationText };
    })
    .filter((d: any) => d.deviation_summary && d.deviation_summary.trim());
  
  const seen = new Set<string>();
  const onlyDevs = computed
    .filter((d: { control_id: string; deviation_summary: string }) => d.deviation_summary && !isNegative(d.deviation_summary))
    .filter((d: { control_id: string; deviation_summary: string }) => { 
      const k = `${String(d.control_id)}|${norm(String(d.deviation_summary))}`; 
      if (seen.has(k)) return false; 
      seen.add(k); 
      return true; 
    });
  
  if (onlyDevs.length > 0) {
    let html = `<div class="exec-section"><h4>Deviations Noted</h4><div class="exec-content"><ul>`;
    onlyDevs.forEach((deviation: any) => {
      html += `<li><strong>${deviation.control_id}:</strong> ${deviation.deviation_summary}</li>`;
    });
    html += `</ul></div></div>`;
    return html;
  }
  
  return '';
}

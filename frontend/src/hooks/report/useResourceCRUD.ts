import { useCallback } from 'react';
import api from '../../api/client';
import { API_URL } from '../../config/report/constants';
import { normalizeConfidence, processCuecData } from '../../services/report/dataTransformations';

type ResourceType = 'suborgs' | 'cuecs' | 'controls';

interface UseResourceCRUDProps {
  scanId: string | undefined;
  setReport: React.Dispatch<React.SetStateAction<any>>;
  showToast: (message: string, severity?: 'success' | 'error' | 'info' | 'warning') => void;
  setRecentlyChangedIds: React.Dispatch<React.SetStateAction<Set<number>>>;
}

export function useResourceCRUD({
  scanId,
  setReport,
  showToast,
  setRecentlyChangedIds
}: UseResourceCRUDProps) {

  // CREATE handlers
  const handleCreate = useCallback(async (
    type: ResourceType,
    data: any,
    onClose: () => void,
    onReset: () => void
  ) => {
    if (!scanId) return;

    try {
      let endpoint = '';
      let payload: any = {};

      if (type === 'suborgs') {
        const name = (data.name || '').trim();
        if (!name) { showToast('Name is required', 'warning'); return; }
        endpoint = `${API_URL}${scanId}/suborgs`;
        payload = { name };
        if (data.confidence !== undefined && data.confidence !== '') {
          const norm = normalizeConfidence(data.confidence);
          if (norm !== undefined) payload.confidence = norm;
        }
        if (data.third_party_description) payload.third_party_description = data.third_party_description;
        if (data.third_party_page_ref) payload.third_party_page_ref = data.third_party_page_ref;
      } else if (type === 'cuecs') {
        const desc = (data.cuec_description || '').trim();
        if (!desc) { showToast('Description is required', 'warning'); return; }
        endpoint = `${API_URL}${scanId}/cuecs`;
        payload = { cuec_description: desc };
        if (data.cuec_confidence !== undefined && data.cuec_confidence !== '') {
          const norm = normalizeConfidence(data.cuec_confidence);
          if (norm !== undefined) payload.cuec_confidence = norm;
        }
        if (data.framework_mappings) payload.framework_mappings = data.framework_mappings;
        if (data.primary_framework) payload.primary_framework = data.primary_framework;
        if (data.primary_criterion_id) payload.primary_criterion_id = data.primary_criterion_id;
        if (data.primary_confidence !== undefined) payload.primary_confidence = data.primary_confidence;
        if (data.control_strength) payload.control_strength = data.control_strength;
      } else if (type === 'controls') {
        const hasDesc = (data.control_desc || '').trim().length > 0;
        const hasId = (data.control_id || '').trim().length > 0;
        if (!hasDesc && !hasId) { showToast('Control ID or Description required', 'warning'); return; }
        endpoint = `${API_URL}${scanId}/controls`;
        if (hasId) payload.control_id = (data.control_id || '').trim();
        if (hasDesc) payload.control_desc = (data.control_desc || '').trim();
        if (data.framework_mappings) payload.framework_mappings = data.framework_mappings;
        if (data.primary_framework) payload.primary_framework = data.primary_framework;
        if (data.primary_criterion_id) payload.primary_criterion_id = data.primary_criterion_id;
        if (data.primary_confidence !== undefined) payload.primary_confidence = data.primary_confidence;
        if (data.control_page_ref) payload.control_page_ref = data.control_page_ref;
        if (data.control_confidence !== undefined && data.control_confidence !== '') {
          const norm = normalizeConfidence(data.control_confidence);
          if (norm !== undefined) payload.control_confidence = norm;
        }
      }

      const { data: created } = await api.post(endpoint, payload);

      // Update local state
      setReport((prev: any) => {
        if (!prev) return prev;
        if (type === 'suborgs') {
          const pushTo = (arr: any[]) => ([...(arr || []), created]);
          const next: any = { ...prev };
          if (prev.subservice_organizations) next.subservice_organizations = pushTo(prev.subservice_organizations);
          if (prev.subservice_orgs) next.subservice_orgs = pushTo(prev.subservice_orgs);
          if (!prev.subservice_organizations && !prev.subservice_orgs) next.subservice_orgs = pushTo([]);
          return next;
        } else if (type === 'cuecs') {
          return { ...prev, cuecs: [...(prev?.cuecs || []), created] };
        } else if (type === 'controls') {
          return { ...prev, controls: [...(prev?.controls || []), created] };
        }
        return prev;
      });

      onClose();
      onReset();
      const labels = { suborgs: 'Subservice org', cuecs: 'CUEC', controls: 'Control' };
      showToast(`${labels[type]} created`, 'success');
    } catch (e: any) {
      console.error(e);
      const msg = e?.response?.data || e?.message || `Failed to create ${type}`;
      showToast(typeof msg === 'string' ? msg : `Failed to create ${type}`, 'error');
    }
  }, [scanId, setReport, showToast]);

  // EDIT handlers
  const handleEdit = useCallback(async (type: ResourceType, row: any, idx?: number) => {
    if (!scanId) return;

    try {
      let endpoint = '';
      let payload: any = {};

      if (type === 'suborgs') {
        endpoint = row.id != null
          ? `${API_URL}${scanId}/suborgs/id/${encodeURIComponent(row.id)}`
          : `${API_URL}${scanId}/suborgs/${encodeURIComponent(row.name)}`;
        if (row.confidence !== undefined) {
          const norm = normalizeConfidence(row.confidence);
          if (norm !== undefined) payload.confidence = norm;
        }
        if (row.name !== undefined) payload.name = String(row.name || '').trim();
        if (row.confidence_justification !== undefined) payload.confidence_justification = row.confidence_justification;
        if (row.annotation !== undefined) payload.annotation = row.annotation;
        if (row.analyst_notes !== undefined) payload.analyst_notes = row.analyst_notes;
        if (row.edit_log !== undefined) payload.edit_log = row.edit_log;
        if (row.third_party_description !== undefined) payload.third_party_description = row.third_party_description;
        if (row.third_party_page_ref !== undefined) payload.third_party_page_ref = row.third_party_page_ref;
      } else if (type === 'cuecs') {
        endpoint = `${API_URL}${scanId}/cuecs/${row.id}`;
        payload = processCuecData(row);
      } else if (type === 'controls') {
        endpoint = row.id != null
          ? `${API_URL}${scanId}/controls/id/${encodeURIComponent(row.id)}`
          : `${API_URL}${scanId}/controls/${encodeURIComponent(row.control_id)}`;
        console.log('[useResourceCRUD] Building controls payload from row:', {
          hasAnalystNotes: 'analyst_notes' in row,
          analystNotesValue: row.analyst_notes,
          analystNotesType: typeof row.analyst_notes
        });
        if (row.control_confidence !== undefined) {
          const norm = normalizeConfidence(row.control_confidence);
          if (norm !== undefined) payload.control_confidence = norm;
        }
        if (row.control_id !== undefined) payload.control_id = String(row.control_id || '').trim();
        if (row.control_desc !== undefined) payload.control_desc = row.control_desc;
        if (row.control_test !== undefined) payload.control_test = row.control_test;
        if (row.control_test_results !== undefined) payload.control_test_results = row.control_test_results;
        if (row.has_deviation !== undefined) {
          // Convert string "Yes" back to boolean true, empty string to false
          if (typeof row.has_deviation === 'string') {
            payload.has_deviation = row.has_deviation.toLowerCase() === 'yes' || row.has_deviation === 'true';
          } else {
            payload.has_deviation = Boolean(row.has_deviation);
          }
        }
        if (row.deviation_desc !== undefined) payload.deviation_desc = row.deviation_desc;
        if (row.annotation !== undefined) payload.annotation = row.annotation;
        if (row.analyst_notes !== undefined) payload.analyst_notes = row.analyst_notes;
        if (row.framework_mappings !== undefined) payload.framework_mappings = row.framework_mappings;
        if (row.primary_framework !== undefined) payload.primary_framework = row.primary_framework;
        if (row.primary_criterion_id !== undefined) payload.primary_criterion_id = row.primary_criterion_id;
        if (row.primary_confidence !== undefined) payload.primary_confidence = row.primary_confidence;
        if (row.control_page_ref !== undefined) payload.control_page_ref = row.control_page_ref;
        if (row.confidence_calc !== undefined) payload.confidence_calc = row.confidence_calc;
        if (row.edit_log !== undefined) payload.edit_log = row.edit_log;
        console.log('[useResourceCRUD] Final payload keys:', Object.keys(payload), 'has analyst_notes:', 'analyst_notes' in payload);
      }

      const response = await api.patch(endpoint, payload);
      const updatedData = response.data;

      // Optimistic local update - use response data for controls to get confidence_calc
      setReport((prev: any) => {
        if (!prev) return prev;
        if (type === 'suborgs') {
          // Use response data if available (includes backend-generated fields like edit_log)
          const mergeData = updatedData && updatedData.id ? updatedData : payload;
          const apply = (arr: any[]) => (arr || []).map((so: any) => {
            const match = (row.id != null && so.id != null)
              ? String(so.id) === String(row.id)
              : String(so.name) === String(row.name);
            return match ? { ...so, ...mergeData } : so;
          });
          const result: any = { ...prev };
          if (prev.subservice_organizations) result.subservice_organizations = apply(prev.subservice_organizations);
          if (prev.subservice_orgs) result.subservice_orgs = apply(prev.subservice_orgs);
          return result;
        } else if (type === 'cuecs') {
          // Use response data if available (includes backend-generated fields like edit_log)
          const mergeData = updatedData && updatedData.id ? updatedData : payload;
          const updatedCuecs = (prev.cuecs || []).map((c: any) => 
            String(c.id) === String(row.id) ? { ...c, ...mergeData } : c
          );
          return { ...prev, cuecs: updatedCuecs };
        } else if (type === 'controls') {
          // Use response data if available (includes backend-generated fields like confidence_calc)
          const mergeData = updatedData && updatedData.id ? updatedData : payload;
          const updatedControls = (prev.controls || []).map((ctrl: any) => {
            const match = row.id != null
              ? String(ctrl.id) === String(row.id)
              : String(ctrl.control_id) === String(row.control_id);
            return match ? { ...ctrl, ...mergeData } : ctrl;
          });
          return { ...prev, controls: updatedControls };
        }
        return prev;
      });

      // Highlight the changed row
      if (row.id) {
        setRecentlyChangedIds(new Set([row.id]));
        setTimeout(() => setRecentlyChangedIds(new Set()), 3000);
      }

      const labels = { suborgs: 'Subservice org', cuecs: 'CUEC', controls: 'Control' };
      showToast(`${labels[type]} saved`, 'success');
    } catch (e: any) {
      const status = e?.response?.status;
      const text = e?.response?.data;
      if (status === 409 && type === 'suborgs') {
        console.warn('Suborg name collision (409):', text);
        showToast('Name already exists for this scan. Please choose a unique name.', 'warning');
      } else {
        console.error(`Failed to save ${type} row:`, text || e);
        showToast(`Failed to save ${type}`, 'error');
      }
    }
  }, [scanId, setReport, showToast]);

  // BATCH EDIT handlers
  const handleBatchEdit = useCallback(async (
    type: ResourceType,
    changes: { [rowIdx: number]: any },
    rowsUsed: any[]
  ) => {
    if (!scanId) return;

    try {
      const entries = Object.entries(changes);
      const changedIds = entries.map(([rowIdx]) => rowsUsed[parseInt(rowIdx)]?.id).filter(Boolean);

      const savePromises = entries.map(async ([rowIdx, changedFields]) => {
        const originalRow = rowsUsed[parseInt(rowIdx)];
        if (!originalRow) return;

        let endpoint = '';
        let payload: any = {};

        if (type === 'suborgs') {
          const suborgName = originalRow.id != null
            ? `id/${encodeURIComponent(originalRow.id)}`
            : `${encodeURIComponent(originalRow.name)}`;
          endpoint = `${API_URL}${scanId}/suborgs/${suborgName}`;
          if (changedFields.confidence !== undefined) {
            const norm = normalizeConfidence(changedFields.confidence);
            if (norm !== undefined) payload.confidence = norm;
          }
          if (changedFields.name !== undefined) payload.name = String(changedFields.name || '').trim();
          if (changedFields.confidence_justification !== undefined) payload.confidence_justification = changedFields.confidence_justification;
          if (changedFields.annotation !== undefined) payload.annotation = changedFields.annotation;
          if (changedFields.analyst_notes !== undefined) payload.analyst_notes = changedFields.analyst_notes;
          if (changedFields.third_party_description !== undefined) payload.third_party_description = changedFields.third_party_description;
          if (changedFields.third_party_page_ref !== undefined) payload.third_party_page_ref = changedFields.third_party_page_ref;
        } else if (type === 'cuecs') {
          endpoint = `${API_URL}${scanId}/cuecs/${originalRow.id}`;
          payload = processCuecData(changedFields);
        } else if (type === 'controls') {
          endpoint = originalRow.id != null
            ? `${API_URL}${scanId}/controls/id/${encodeURIComponent(originalRow.id)}`
            : `${API_URL}${scanId}/controls/${encodeURIComponent(originalRow.control_id)}`;
          if (changedFields.control_confidence !== undefined) {
            const norm = normalizeConfidence(changedFields.control_confidence);
            if (norm !== undefined) payload.control_confidence = norm;
          }
          if (changedFields.control_id !== undefined) payload.control_id = String(changedFields.control_id || '').trim();
          if (changedFields.control_desc !== undefined) payload.control_desc = changedFields.control_desc;
          if (changedFields.control_test !== undefined) payload.control_test = changedFields.control_test;
          if (changedFields.control_test_results !== undefined) payload.control_test_results = changedFields.control_test_results;
          if (changedFields.has_deviation !== undefined) {
            // Convert string "Yes" back to boolean true, empty string to false
            if (typeof changedFields.has_deviation === 'string') {
              payload.has_deviation = changedFields.has_deviation.toLowerCase() === 'yes' || changedFields.has_deviation === 'true';
            } else {
              payload.has_deviation = Boolean(changedFields.has_deviation);
            }
          }
          if (changedFields.deviation_desc !== undefined) payload.deviation_desc = changedFields.deviation_desc;
          if (changedFields.control_page_refs !== undefined) payload.control_page_refs = changedFields.control_page_refs;
          if (changedFields.control_page_ref !== undefined) payload.control_page_ref = changedFields.control_page_ref;
          if (changedFields.annotation !== undefined) payload.annotation = changedFields.annotation;
          if (changedFields.analyst_notes !== undefined) payload.analyst_notes = changedFields.analyst_notes;
        }

        try {
          const response = await api.patch(endpoint, payload);
          return { ok: true, rowIdx: parseInt(rowIdx), payload, response: response.data };
        } catch (err: any) {
          err.status = err?.response?.status;
          err.row = originalRow;
          throw err;
        }
      });

      const results = await Promise.allSettled(savePromises);
      const succeededIdx = new Set<number>();
      let hadConflict = false;

      results.forEach((res, i) => {
        if (res.status === 'fulfilled' && res.value) {
          succeededIdx.add(res.value.rowIdx);
        } else if ((res as any).reason && (res as any).reason.status === 409) {
          hadConflict = true;
        }
      });

      // Optimistic update for succeeded rows
      setReport((prev: any) => {
        if (!prev) return prev;

        if (type === 'suborgs') {
          const apply = (arr: any[]) => (arr || []).map((so: any) => {
            for (let i = 0; i < entries.length; i++) {
              if (!succeededIdx.has(i)) continue;
              const [rowIdxStr, changedFields] = entries[i];
              const orig = rowsUsed[parseInt(rowIdxStr)];
              if (!orig) continue;
              const match = (orig.id != null && so.id != null)
                ? String(so.id) === String(orig.id)
                : String(so.name) === String(orig.name);
              if (!match) continue;
              
              const payload: any = {};
              if (changedFields.confidence !== undefined) {
                const norm = normalizeConfidence(changedFields.confidence);
                if (norm !== undefined) payload.confidence = norm;
              }
              if (changedFields.name !== undefined) payload.name = String(changedFields.name || '').trim();
              if (changedFields.confidence_justification !== undefined) payload.confidence_justification = changedFields.confidence_justification;
              if (changedFields.annotation !== undefined) payload.annotation = changedFields.annotation;
              if (changedFields.third_party_description !== undefined) payload.third_party_description = changedFields.third_party_description;
              if (changedFields.third_party_page_ref !== undefined) payload.third_party_page_ref = changedFields.third_party_page_ref;
              return { ...so, ...payload };
            }
            return so;
          });
          const next: any = { ...prev };
          if (prev.subservice_organizations) next.subservice_organizations = apply(prev.subservice_organizations);
          if (prev.subservice_orgs) next.subservice_orgs = apply(prev.subservice_orgs);
          return next;
        } else if (type === 'cuecs') {
          const updatedCuecs = (prev.cuecs || []).map((cuec: any) => {
            const entry = entries.find(([rowIdx]) => {
              const orig = rowsUsed[parseInt(rowIdx)];
              return orig && String(orig.id) === String(cuec.id) && succeededIdx.has(parseInt(rowIdx));
            });
            if (!entry) return cuec;
            const [, changedFields] = entry;
            const processedChanges = processCuecData(changedFields);
            return { ...cuec, ...processedChanges };
          });
          return { ...prev, cuecs: updatedCuecs };
        } else if (type === 'controls') {
          const updatedControls = (prev.controls || []).map((ctrl: any) => {
            const entry = entries.find(([rowIdx]) => {
              const orig = rowsUsed[parseInt(rowIdx)];
              const match = orig && (
                orig.id != null
                  ? String(orig.id) === String(ctrl.id)
                  : String(orig.control_id) === String(ctrl.control_id)
              );
              return match && succeededIdx.has(parseInt(rowIdx));
            });
            if (!entry) return ctrl;
            const [rowIdxStr] = entry;
            const result = results[entries.findIndex(([r]) => r === rowIdxStr)];
            if (result.status === 'fulfilled' && result.value?.response) {
              // Use the API response data instead of manually constructing the payload
              return { ...ctrl, ...result.value.response };
            }
            // Fallback to old behavior if response not available
            const [, changedFields] = entry;
            const payload: any = {};
            if (changedFields.control_confidence !== undefined) {
              const norm = normalizeConfidence(changedFields.control_confidence);
              if (norm !== undefined) payload.control_confidence = norm;
            }
            if (changedFields.control_id !== undefined) payload.control_id = String(changedFields.control_id || '').trim();
            if (changedFields.control_desc !== undefined) payload.control_desc = changedFields.control_desc;
            if (changedFields.control_test !== undefined) payload.control_test = changedFields.control_test;
            if (changedFields.control_test_results !== undefined) payload.control_test_results = changedFields.control_test_results;
            if (changedFields.has_deviation !== undefined) payload.has_deviation = changedFields.has_deviation;
            if (changedFields.deviation_desc !== undefined) payload.deviation_desc = changedFields.deviation_desc;
            if (changedFields.control_page_refs !== undefined) payload.control_page_refs = changedFields.control_page_refs;
            if (changedFields.control_page_ref !== undefined) payload.control_page_ref = changedFields.control_page_ref;
            if (changedFields.annotation !== undefined) payload.annotation = changedFields.annotation;
            return { ...ctrl, ...payload };
          });
          return { ...prev, controls: updatedControls };
        }
        return prev;
      });

      // Highlight changed rows
      setRecentlyChangedIds(new Set(changedIds));
      setTimeout(() => setRecentlyChangedIds(new Set()), 3000);

      const successCount = Array.from(succeededIdx).length;
      const failCount = results.length - successCount;
      const labels = { suborgs: 'Subservice orgs', cuecs: 'CUECs', controls: 'Controls' };
      
      if (failCount === 0) {
        showToast(`${labels[type]} updated`, 'success');
      } else if (hadConflict) {
        showToast(`Some names already exist. Updated ${successCount}, ${failCount} failed.`, 'warning');
      } else {
        showToast(`Updated ${successCount} ${type}. ${failCount} failed.`, 'warning');
      }
    } catch (e) {
      console.error(`Failed to batch save ${type}`, e);
      showToast(`Failed to update ${type}`, 'error');
    }
  }, [scanId, setReport, showToast, setRecentlyChangedIds]);

  // IGNORE handler
  const handleIgnore = useCallback(async (type: ResourceType, row: any) => {
    if (!scanId) return;

    try {
      let endpoint = '';
      let updateData: any = {};

      if (type === 'suborgs') {
        endpoint = row.id != null
          ? `${API_URL}${scanId}/suborgs/id/${encodeURIComponent(row.id)}`
          : `${API_URL}${scanId}/suborgs/${encodeURIComponent(row.name)}`;
        updateData = {
          confidence: 0,
          confidence_justification: (row.confidence_justification || '') + '; Manually ignored in UI - confidence set to 0'
        };
      } else if (type === 'cuecs') {
        endpoint = `${API_URL}${scanId}/cuecs/${row.id}`;
        updateData = {
          cuec_confidence: 0,
          cuec_confidence_justification: (row.cuec_confidence_justification || '') + '; Manually ignored in UI - confidence set to 0'
        };
      } else if (type === 'controls') {
        endpoint = row.id != null
          ? `${API_URL}${scanId}/controls/id/${encodeURIComponent(row.id)}`
          : `${API_URL}${scanId}/controls/${encodeURIComponent(row.control_id)}`;
        updateData = {
          control_confidence: 0,
          confidence_calc: (row.confidence_calc || '') + '; Manually ignored in UI - confidence set to 0'
        };
      }

      await api.patch(endpoint, updateData);

      // Optimistic update
      setReport((prev: any) => {
        if (!prev) return prev;
        if (type === 'controls') {
          const updatedControls = (prev.controls || []).map((ctrl: any) => {
            const isMatch = row.id != null
              ? String(ctrl.id) === String(row.id)
              : String(ctrl.control_id) === String(row.control_id);
            return isMatch ? { ...ctrl, control_confidence: 0, confidence_calc: updateData.confidence_calc } : ctrl;
          });
          return { ...prev, controls: updatedControls, _lastUpdate: Date.now() };
        } else if (type === 'cuecs') {
          const updatedCuecs = (prev.cuecs || []).map((c: any) => 
            String(c.id) === String(row.id) 
              ? { ...c, cuec_confidence: 0, cuec_confidence_justification: updateData.cuec_confidence_justification }
              : c
          );
          return { ...prev, cuecs: updatedCuecs };
        } else if (type === 'suborgs') {
          const updateArray = (arr: any[]) => (arr || []).map((so: any) => {
            const isMatch = row.id != null
              ? String(so.id) === String(row.id)
              : String(so.name) === String(row.name);
            return isMatch ? { ...so, confidence: 0, confidence_justification: updateData.confidence_justification } : so;
          });
          const next: any = { ...prev };
          if (prev.subservice_organizations) next.subservice_organizations = updateArray(prev.subservice_organizations);
          if (prev.subservice_orgs) next.subservice_orgs = updateArray(prev.subservice_orgs);
          return next;
        }
        return prev;
      });

      const labels = { suborgs: 'Subservice org', cuecs: 'CUEC', controls: 'Control' };
      setTimeout(() => showToast(`${labels[type]} ignored`, 'success'), 100);
    } catch (error) {
      console.error(`Failed to ignore ${type}:`, error);
      showToast(`Failed to update ${type}`, 'error');
      throw error;
    }
  }, [scanId, setReport, showToast]);

  // CONFIRM handler
  const handleConfirm = useCallback(async (type: ResourceType, row: any) => {
    if (!scanId) return;

    try {
      let endpoint = '';
      let updateData: any = {};

      if (type === 'suborgs') {
        endpoint = row.id != null
          ? `${API_URL}${scanId}/suborgs/id/${encodeURIComponent(row.id)}`
          : `${API_URL}${scanId}/suborgs/${encodeURIComponent(row.name)}`;
        updateData = {
          confidence: 1.0,
          confidence_justification: (row.confidence_justification || '') + '; Manually confirmed in UI - confidence set to 100%'
        };
      } else if (type === 'cuecs') {
        endpoint = `${API_URL}${scanId}/cuecs/${row.id}`;
        updateData = {
          cuec_confidence: 1.0,
          cuec_confidence_justification: (row.cuec_confidence_justification || '') + '; Manually confirmed in UI - confidence set to 100%'
        };
      } else if (type === 'controls') {
        endpoint = row.id != null
          ? `${API_URL}${scanId}/controls/id/${encodeURIComponent(row.id)}`
          : `${API_URL}${scanId}/controls/${encodeURIComponent(row.control_id)}`;
        updateData = {
          control_confidence: 1.0,
          confidence_calc: (row.confidence_calc || '') + '; Manually confirmed in UI - confidence set to 100%'
        };
      }

      await api.patch(endpoint, updateData);

      // Optimistic update
      setReport((prev: any) => {
        if (!prev) return prev;
        if (type === 'controls') {
          const updatedControls = (prev.controls || []).map((ctrl: any) => {
            const isMatch = row.id != null
              ? String(ctrl.id) === String(row.id)
              : String(ctrl.control_id) === String(row.control_id);
            return isMatch ? { ...ctrl, control_confidence: 1.0, confidence_calc: updateData.confidence_calc } : ctrl;
          });
          return { ...prev, controls: updatedControls, _lastUpdate: Date.now() };
        } else if (type === 'cuecs') {
          const updatedCuecs = (prev.cuecs || []).map((c: any) => 
            String(c.id) === String(row.id) 
              ? { ...c, cuec_confidence: 1.0, cuec_confidence_justification: updateData.cuec_confidence_justification }
              : c
          );
          return { ...prev, cuecs: updatedCuecs };
        } else if (type === 'suborgs') {
          const updateArray = (arr: any[]) => (arr || []).map((so: any) => {
            const isMatch = row.id != null
              ? String(so.id) === String(row.id)
              : String(so.name) === String(row.name);
            return isMatch ? { ...so, confidence: 1.0, confidence_justification: updateData.confidence_justification } : so;
          });
          const next: any = { ...prev };
          if (prev.subservice_organizations) next.subservice_organizations = updateArray(prev.subservice_organizations);
          if (prev.subservice_orgs) next.subservice_orgs = updateArray(prev.subservice_orgs);
          return next;
        }
        return prev;
      });

      // Highlight changed row
      setRecentlyChangedIds(prev => {
        const next = new Set(prev);
        next.add(row.id);
        setTimeout(() => {
          setRecentlyChangedIds(p => {
            const n = new Set(p);
            n.delete(row.id);
            return n;
          });
        }, 3000);
        return next;
      });

      const labels = { suborgs: 'Subservice org', cuecs: 'CUEC', controls: 'Control' };
      setTimeout(() => showToast(`${labels[type]} confirmed`, 'success'), 100);
    } catch (error) {
      console.error(`Failed to confirm ${type}:`, error);
      showToast(`Failed to update ${type}`, 'error');
      throw error;
    }
  }, [scanId, setReport, showToast, setRecentlyChangedIds]);

  // RECOMPUTE handler
  const handleRecompute = useCallback(async (type: 'cuecs' | 'controls', row: any) => {
    if (!scanId) return;

    try {
      let endpoint = '';
      if (type === 'cuecs') {
        endpoint = `${API_URL}${scanId}/cuecs/${row.id}/recompute_frameworks`;
      } else {
        endpoint = `${API_URL}${scanId}/controls/id/${row.id}/recompute_frameworks`;
      }

      const resp = await api.post(endpoint);
      const data = resp.data;
      const upd = type === 'cuecs' ? data?.cuec || {} : data?.control || {};

      setReport((prev: any) => {
        if (!prev) return prev;
        if (type === 'cuecs') {
          const nextCuecs = (prev.cuecs || []).map((c: any) => {
            if (String(c.id) !== String(row.id)) return c;
            return {
              ...c,
              // Phase 1 multi-framework fields (NO cuec_ prefix - matches database model)
              framework_mappings: upd.framework_mappings,
              primary_framework: upd.primary_framework,
              primary_criterion_id: upd.primary_criterion_id,
              primary_confidence: upd.primary_confidence,
            };
          });
          return { ...prev, cuecs: nextCuecs };
        } else {
          const nextControls = (prev.controls || []).map((c: any) => {
            if (String(c.id) !== String(row.id)) return c;
            return {
              ...c,
              framework_mappings: upd.framework_mappings,
              primary_framework: upd.primary_framework,
              primary_criterion_id: upd.primary_criterion_id,
              primary_confidence: upd.primary_confidence,
            };
          });
          return { ...prev, controls: nextControls };
        }
      });

      const label = type === 'cuecs' ? 'CUEC' : 'control';
      const message = data?.message || `Recomputed ${label} mapping`;
      const mappingCount = data?.mapping_count;
      
      if (mappingCount === 0) {
        showToast(`No framework mappings found for ${label}`, 'warning');
      } else if (message) {
        showToast(message, 'success');
      } else {
        showToast(`Recomputed ${label} mapping`, 'success');
      }
    } catch (e: any) {
      console.error(e);
      const errorMsg = e?.response?.data?.error || e?.response?.data?.message || 'Failed to recompute mapping';
      showToast(errorMsg, 'error');
    }
  }, [scanId, setReport, showToast]);

  // BULK RECOMPUTE handler for high confidence items
  const handleRecomputeAllHighConfidence = useCallback(async (type: 'cuecs' | 'controls') => {
    if (!scanId) return;

    try {
      let endpoint = '';
      if (type === 'cuecs') {
        endpoint = `${API_URL}${scanId}/cuecs/recompute_all_high_confidence`;
      } else {
        endpoint = `${API_URL}${scanId}/controls/recompute_all_high_confidence`;
      }

      showToast('Recomputing framework mappings for high confidence items...', 'info');
      
      const resp = await api.post(endpoint);
      const data = resp.data;

      if (data.success) {
        // Update local state with all results
        if (data.results && data.results.length > 0) {
          setReport((prev: any) => {
            if (!prev) return prev;
            
            if (type === 'cuecs') {
              const resultsMap = new Map(data.results.filter((r: any) => r.success && r.cuec).map((r: any) => [r.cuec.id, r.cuec]));
              const nextCuecs = (prev.cuecs || []).map((c: any) => {
                const upd = resultsMap.get(c.id);
                if (!upd) return c;
                return {
                  ...c,
                  framework_mappings: upd.framework_mappings,
                  primary_framework: upd.primary_framework,
                  primary_criterion_id: upd.primary_criterion_id,
                  primary_confidence: upd.primary_confidence,
                };
              });
              return { ...prev, cuecs: nextCuecs };
            } else {
              const resultsMap = new Map(data.results.filter((r: any) => r.success && r.control).map((r: any) => [r.control.id, r.control]));
              const nextControls = (prev.controls || []).map((c: any) => {
                const upd = resultsMap.get(c.id);
                if (!upd) return c;
                return {
                  ...c,
                  framework_mappings: upd.framework_mappings,
                  primary_framework: upd.primary_framework,
                  primary_criterion_id: upd.primary_criterion_id,
                  primary_confidence: upd.primary_confidence,
                };
              });
              return { ...prev, controls: nextControls };
            }
          });
        }

        const label = type === 'cuecs' ? 'CUECs' : 'controls';
        const message = data.message || `Recomputed ${data.success_count} of ${data.total} high confidence ${label}`;
        
        if (data.total === 0) {
          showToast(`No high confidence ${label} found (confidence > 70%)`, 'info');
        } else if (data.failed_count > 0) {
          showToast(`${message} (${data.failed_count} failed)`, 'warning');
        } else {
          showToast(message, 'success');
        }
      } else {
        throw new Error(data.error || 'Bulk recompute failed');
      }
    } catch (e: any) {
      console.error(e);
      const errorMsg = e?.response?.data?.error || e?.response?.data?.message || 'Failed to recompute mappings';
      showToast(errorMsg, 'error');
    }
  }, [scanId, setReport, showToast]);

  // TOGGLE DEVIATION handler
  const handleToggleDeviation = useCallback(async (row: any, hasDeviation: boolean) => {
    if (!scanId) return;

    try {
      const endpoint = `${API_URL}${scanId}/controls/id/${row.id}`;
      
      const resp = await api.patch(endpoint, {
        has_deviation: hasDeviation,
        deviation_desc: hasDeviation ? (row.deviation_desc || '') : null
      });
      
      const updatedControl = resp.data;
      
      // Update local state
      setReport((prev: any) => {
        if (!prev) return prev;
        const nextControls = (prev.controls || []).map((c: any) => {
          if (String(c.id) !== String(row.id)) return c;
          return {
            ...c,
            has_deviation: updatedControl.has_deviation,
            deviation_desc: updatedControl.deviation_desc
          };
        });
        return { ...prev, controls: nextControls };
      });

      showToast(hasDeviation ? 'Control marked as deviation' : 'Deviation flag removed', 'success');
    } catch (e: any) {
      console.error(e);
      const errorMsg = e?.response?.data?.error || e?.response?.data?.message || 'Failed to update deviation';
      showToast(errorMsg, 'error');
    }
  }, [scanId, setReport, showToast]);

  // MAP ALL FRAMEWORKS handler - maps controls/CUECs to all available frameworks
  // (scan pipeline only maps to TSC+COSO by default for speed)
  const handleMapAllFrameworks = useCallback(async (type: 'cuecs' | 'controls') => {
    if (!scanId) return;

    try {
      let endpoint = '';
      if (type === 'cuecs') {
        endpoint = `${API_URL}${scanId}/cuecs/map_all_frameworks`;
      } else {
        endpoint = `${API_URL}${scanId}/controls/map_all_frameworks`;
      }

      const label = type === 'cuecs' ? 'CUECs' : 'controls';
      showToast(`Mapping ${label} to all available frameworks... This may take a few minutes.`, 'info');
      
      const resp = await api.post(endpoint, {});
      const data = resp.data;

      if (data.success) {
        // Refresh the full report data to get updated framework_mappings
        // Since map_all_frameworks updates DB directly, we need to reload
        try {
          const reportResp = await api.get(`${API_URL}${scanId}`);
          if (reportResp.data) {
            setReport(reportResp.data);
          }
        } catch (refreshErr) {
          console.warn('Could not refresh report after framework mapping:', refreshErr);
        }

        const frameworks = data.frameworks ? data.frameworks.join(', ') : 'all';
        const message = data.message || `Mapped ${data.success_count} of ${data.total} ${label} to frameworks: ${frameworks}`;
        
        if (data.total === 0) {
          showToast(`No ${label} found to map`, 'info');
        } else if (data.failed_count > 0) {
          showToast(`${message} (${data.failed_count} failed)`, 'warning');
        } else {
          showToast(message, 'success');
        }
      } else {
        throw new Error(data.error || 'Framework mapping failed');
      }
    } catch (e: any) {
      console.error(e);
      const errorMsg = e?.response?.data?.error || e?.response?.data?.message || 'Failed to map frameworks';
      showToast(errorMsg, 'error');
    }
  }, [scanId, setReport, showToast]);

  return {
    handleCreate,
    handleEdit,
    handleBatchEdit,
    handleIgnore,
    handleConfirm,
    handleRecompute,
    handleRecomputeAllHighConfidence,
    handleMapAllFrameworks,
    handleToggleDeviation
  };
}

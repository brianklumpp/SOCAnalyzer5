/**
 * useFrameworkCoverage Hook
 * 
 * Calculates TSC and COSO framework coverage from controls and CUECs.
 * Detects missing framework IDs that appear in extracted text but aren't mapped.
 */

import { useMemo } from 'react';
import { CONFIDENCE_THRESHOLD } from '../../config/report/constants';

interface FrameworkCriteria {
  tsc: { [section: string]: Array<{ id: string; description: string }> };
  coso: { [section: string]: Array<{ id: string; description: string }> };
}

interface IgnoredIds {
  controls: Set<number>;
  cuecs: Set<number>;
  suborgs: Set<number>;
}

interface CoverageResult {
  tscIdsFound: Set<string>;
  cosoIdsFound: Set<string>;
  tscIdsByCuecs: Set<string>;
  cosoIdsByCuecs: Set<string>;
  missingTscIds: string[];
  missingCosoIds: string[];
  tscCoveredByControls: number;
  tscCoveredByCuecs: number;
  tscLikelyCovered: number;
  tscTotal: number;
  tscMissed: number;
  cosoCoveredByControls: number;
  cosoCoveredByCuecs: number;
  cosoLikelyCovered: number;
  cosoTotal: number;
  cosoMissed: number;
  getCoverageStatus: (frameworkId: any, controls: any[], idKey: string, missingIds: string[], cuecIds: Set<string>) => {
    covered: boolean;
    exception: boolean;
    cuecCovered: boolean;
    likelyCovered: boolean;
    coverageType: string;
  };
}

export function useFrameworkCoverage(
  controls: any[],
  cuecs: any[],
  frameworkCriteria: FrameworkCriteria | null,
  extractedText: string,
  ignored: IgnoredIds
): CoverageResult {
  // Memoize high-confidence controls for coverage (exclude ignored)
  const highConfControlsForCoverage = useMemo(() => {
    return controls.filter((ctrl: any) => 
      (ctrl.control_confidence ?? 0) >= CONFIDENCE_THRESHOLD && 
      !ignored.controls.has(ctrl.id)
    );
  }, [controls, ignored.controls]);

  // Collect TSC/COSO IDs from controls (support single-match and multi-match)
  const { tscIdsFromControls, cosoIdsFromControls } = useMemo(() => {
    const tscIds = new Set<string>();
    const cosoIds = new Set<string>();

    highConfControlsForCoverage.forEach((ctrl: any) => {
      // Extract from unified framework_mappings structure
      if (ctrl.framework_mappings) {
        if (ctrl.framework_mappings.TSC) {
          ctrl.framework_mappings.TSC.forEach((m: any) => {
            if (m.id) tscIds.add(m.id);
          });
        }
        if (ctrl.framework_mappings.COSO) {
          ctrl.framework_mappings.COSO.forEach((m: any) => {
            if (m.id) cosoIds.add(m.id);
          });
        }
      }
    });

    return { tscIdsFromControls: tscIds, cosoIdsFromControls: cosoIds };
  }, [highConfControlsForCoverage]);

  // Memoize high-confidence CUECs for coverage (exclude ignored)
  const highConfCuecsFiltered = useMemo(() => {
    return cuecs.filter((cuec: any) => 
      (cuec.cuec_confidence ?? 0) >= CONFIDENCE_THRESHOLD && 
      !ignored.cuecs.has(cuec.id)
    );
  }, [cuecs, ignored.cuecs]);

  // Collect TSC/COSO IDs from CUECs using framework_mappings
  const { tscIdsFromCuecs, cosoIdsFromCuecs } = useMemo(() => {
    const tscIds = new Set<string>();
    const cosoIds = new Set<string>();

    highConfCuecsFiltered.forEach((cuec: any) => {
      // Use framework_mappings (current architecture)
      if (cuec.framework_mappings) {
        const mappings = typeof cuec.framework_mappings === 'string'
          ? JSON.parse(cuec.framework_mappings)
          : cuec.framework_mappings;
        
        if (mappings.TSC) {
          mappings.TSC.forEach((m: any) => tscIds.add(m.id));
        }
        if (mappings.COSO) {
          mappings.COSO.forEach((m: any) => cosoIds.add(m.id));
        }
      }
    });

    return { tscIdsFromCuecs: tscIds, cosoIdsFromCuecs: cosoIds };
  }, [highConfCuecsFiltered]);

  // Helper to find missing framework IDs in extracted text
  const findMissingFrameworkIds = useMemo(() => {
    return (extractedTextParam: string, foundIds: Set<string>, allIds: string[]): string[] => {
      if (!extractedTextParam) return [];
      
      const missingIds: string[] = [];
      const variations = (id: string) => {
        // Generate variations like CC1.1, CC.1.1, CC 1.1, etc.
        const base = id.replace(/[.\s]/g, '');
        return [
          id,
          id.replace('.', ' '),
          id.replace(/(\d)\.(\d)/, '$1.$2'),
          id.replace(/(\d)\.(\d)/, '$1 $2'),
          base.replace(/(\w+)(\d+)(\d+)/, '$1.$2.$3'),
          base.replace(/(\w+)(\d+)(\d+)/, '$1 $2.$3'),
          base.replace(/(\w+)(\d+)(\d+)/, '$1.$2 $3'),
          base.replace(/(\w+)(\d+)(\d+)/, '$1 $2 $3'),
        ];
      };
      
      for (const id of allIds) {
        if (!foundIds.has(id)) {
          // Check if any variation of this ID appears in the text
          const idVariations = variations(id);
          const found = idVariations.some(variation => {
            const regex = new RegExp(`\\b${variation.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i');
            return regex.test(extractedTextParam);
          });
          
          if (found) {
            missingIds.push(id);
          }
        }
      }
      
      return missingIds;
    };
  }, []);

  // Find missing IDs that appear in extracted text
  const { missingTscIds, missingCosoIds } = useMemo(() => {
    const allTscIds = frameworkCriteria ? Object.values(frameworkCriteria.tsc).flat().map((crit: any) => crit.id) : [];
    const allCosoIds = frameworkCriteria ? Object.values(frameworkCriteria.coso).flat().map((crit: any) => crit.id) : [];
    const missingTsc = findMissingFrameworkIds(extractedText || '', tscIdsFromControls, allTscIds);
    const missingCoso = findMissingFrameworkIds(extractedText || '', cosoIdsFromControls, allCosoIds);
    return { missingTscIds: missingTsc, missingCosoIds: missingCoso };
  }, [extractedText, tscIdsFromControls, cosoIdsFromControls, frameworkCriteria, findMissingFrameworkIds]);

  // Calculate coverage statistics
  const coverageStats = useMemo(() => {
    const tscTotal = frameworkCriteria ? Object.values(frameworkCriteria.tsc).flat().length : 0;
    const cosoTotal = frameworkCriteria ? Object.values(frameworkCriteria.coso).flat().length : 0;

    const tscCoveredByControls = frameworkCriteria 
      ? Object.values(frameworkCriteria.tsc).flat().filter((crit: any) => tscIdsFromControls.has(crit.id)).length 
      : 0;
    const tscCoveredByCuecs = frameworkCriteria 
      ? Object.values(frameworkCriteria.tsc).flat().filter((crit: any) => !tscIdsFromControls.has(crit.id) && tscIdsFromCuecs.has(crit.id)).length 
      : 0;
    const tscLikelyCovered = missingTscIds.filter((id: string) => !tscIdsFromControls.has(id) && !tscIdsFromCuecs.has(id)).length;
    const tscMissed = tscTotal - tscCoveredByControls - tscCoveredByCuecs - tscLikelyCovered;

    const cosoCoveredByControls = frameworkCriteria 
      ? Object.values(frameworkCriteria.coso).flat().filter((crit: any) => cosoIdsFromControls.has(crit.id)).length 
      : 0;
    const cosoCoveredByCuecs = frameworkCriteria 
      ? Object.values(frameworkCriteria.coso).flat().filter((crit: any) => !cosoIdsFromControls.has(crit.id) && cosoIdsFromCuecs.has(crit.id)).length 
      : 0;
    const cosoLikelyCovered = missingCosoIds.filter((id: string) => !cosoIdsFromControls.has(id) && !cosoIdsFromCuecs.has(id)).length;
    const cosoMissed = cosoTotal - cosoCoveredByControls - cosoCoveredByCuecs - cosoLikelyCovered;

    return {
      tscCoveredByControls,
      tscCoveredByCuecs,
      tscLikelyCovered,
      tscTotal,
      tscMissed,
      cosoCoveredByControls,
      cosoCoveredByCuecs,
      cosoLikelyCovered,
      cosoTotal,
      cosoMissed,
    };
  }, [frameworkCriteria, tscIdsFromControls, tscIdsFromCuecs, cosoIdsFromControls, cosoIdsFromCuecs, missingTscIds, missingCosoIds]);

  // Coverage status helper function
  const getCoverageStatus = useMemo(() => {
    return (frameworkId: any, controlsParam: any[], idKey: string, missingIds: string[], cuecIds: Set<string>) => {
      const eqId = (a: any, b: any) => String(a ?? '').replace(/\s+/g, '').toUpperCase() === String(b ?? '').replace(/\s+/g, '').toUpperCase();
      const covered = controlsParam.some((ctrl: any) => eqId(ctrl[idKey], frameworkId));
      const exception = controlsParam.some((ctrl: any) => eqId(ctrl[idKey], frameworkId) && (ctrl.control_status || '').toLowerCase().includes('exception'));
      const cuecCovered = cuecIds.has(frameworkId);
      const likelyCovered = missingIds.includes(frameworkId);
      
      // Priority order: control > cuec > likely > missed
      let coverageType = 'missed';
      if (covered) {
        coverageType = 'control';
      } else if (cuecCovered) {
        coverageType = 'cuec';
      } else if (likelyCovered) {
        coverageType = 'likely';
      }
      
      return { covered, exception, cuecCovered, likelyCovered, coverageType };
    };
  }, []);

  return {
    tscIdsFound: tscIdsFromControls,
    cosoIdsFound: cosoIdsFromControls,
    tscIdsByCuecs: tscIdsFromCuecs,
    cosoIdsByCuecs: cosoIdsFromCuecs,
    missingTscIds,
    missingCosoIds,
    ...coverageStats,
    getCoverageStatus,
  };
}

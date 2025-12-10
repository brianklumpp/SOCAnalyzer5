"""
Framework Registry

Defines all supported attestation frameworks with their metadata, including:
- Framework identification (name, type)
- Applicable report types (SOC1, SOC2, COMBINED)
- Related standards (SSAE, ISAE, CSAE, etc.)
- Criteria source files
- UI presentation (color, icon)
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


class FrameworkType(str, Enum):
    """Framework categories"""
    TRUST_SERVICES = "trust_services"
    INTERNAL_CONTROL = "internal_control"
    FINANCIAL_ASSERTIONS = "financial_assertions"
    ISO_STANDARD = "iso_standard"
    NIST_FRAMEWORK = "nist_framework"


class ReportType(str, Enum):
    """Report types that frameworks can apply to"""
    SOC1 = "SOC1"
    SOC2 = "SOC2"
    COMBINED = "COMBINED"


@dataclass
class FrameworkInfo:
    """Metadata for a single framework"""
    name: str
    display_name: str
    type: FrameworkType
    report_types: List[ReportType]
    standards: List[str]  # e.g., ["SSAE 18", "AT-C 105", "AT-C 205"]
    categories: List[str]  # e.g., ["Security", "Availability"] for TSC
    criteria_file: Optional[str]  # Path to JSON file with criteria definitions
    color: str  # Hex color for UI visualization
    icon: str  # Icon identifier for UI
    description: str
    priority: int  # Lower = higher priority for display ordering


# Framework Registry: Central definition of all supported frameworks
FRAMEWORK_REGISTRY: Dict[str, FrameworkInfo] = {
    "TSC": FrameworkInfo(
        name="TSC",
        display_name="Trust Services Criteria",
        type=FrameworkType.TRUST_SERVICES,
        report_types=[ReportType.SOC2, ReportType.COMBINED],
        standards=["SSAE 18", "AT-C 105", "AT-C 205"],
        categories=["Security", "Availability", "Processing Integrity", "Confidentiality", "Privacy"],
        criteria_file="tsc_criteria.json",
        color="#2196F3",  # Blue
        icon="shield",
        description="AICPA Trust Services Criteria for SOC 2 reports",
        priority=1
    ),
    
    "COSO": FrameworkInfo(
        name="COSO",
        display_name="COSO 2013 Framework",
        type=FrameworkType.INTERNAL_CONTROL,
        report_types=[ReportType.SOC1, ReportType.SOC2, ReportType.COMBINED],
        standards=["COSO 2013"],
        categories=["Control Environment", "Risk Assessment", "Control Activities", 
                   "Information & Communication", "Monitoring Activities"],
        criteria_file="coso_criteria.json",
        color="#4CAF50",  # Green
        icon="account_tree",
        description="COSO Internal Control - Integrated Framework (2013)",
        priority=2
    ),
    
    "FINANCIAL_ASSERTIONS": FrameworkInfo(
        name="FINANCIAL_ASSERTIONS",
        display_name="Financial Statement Assertions",
        type=FrameworkType.FINANCIAL_ASSERTIONS,
        report_types=[ReportType.SOC1, ReportType.COMBINED],
        standards=["SSAE 18", "AT-C 320"],
        categories=["Existence or Occurrence", "Completeness", "Rights and Obligations",
                   "Valuation or Allocation", "Presentation and Disclosure"],
        criteria_file="financial_assertions.json",
        color="#FF9800",  # Orange
        icon="attach_money",
        description="Financial statement assertions for SOC 1 Type II reports",
        priority=3
    ),
    
    "COSO_ICFR": FrameworkInfo(
        name="COSO_ICFR",
        display_name="COSO Internal Control over Financial Reporting",
        type=FrameworkType.INTERNAL_CONTROL,
        report_types=[ReportType.SOC1, ReportType.COMBINED],
        standards=["COSO 2013", "PCAOB AS 2201"],
        categories=["Financial Reporting Objectives", "Operations Objectives", "Compliance Objectives"],
        criteria_file="coso_icfr.json",
        color="#9C27B0",  # Purple
        icon="assessment",
        description="COSO framework specialized for financial reporting controls",
        priority=4
    ),
    
    "ISAE3402": FrameworkInfo(
        name="ISAE3402",
        display_name="ISAE 3402",
        type=FrameworkType.INTERNAL_CONTROL,
        report_types=[ReportType.SOC1, ReportType.COMBINED],
        standards=["ISAE 3402", "IAASB"],
        categories=["Control Objectives", "Control Activities"],
        criteria_file="isae3402.json",
        color="#E91E63",  # Pink
        icon="public",
        description="International Standard on Assurance Engagements (international SOC 1 equivalent)",
        priority=5
    ),
    
    "CSAE3416": FrameworkInfo(
        name="CSAE3416",
        display_name="CSAE 3416",
        type=FrameworkType.INTERNAL_CONTROL,
        report_types=[ReportType.SOC1, ReportType.SOC2, ReportType.COMBINED],
        standards=["CSAE 3416", "CPA Canada"],
        categories=["Control Environment", "Risk Assessment", "Control Activities"],
        criteria_file="csae3416.json",
        color="#F44336",  # Red
        icon="flag",
        description="Canadian Standard on Assurance Engagements",
        priority=6
    ),
    
    "AAF0106": FrameworkInfo(
        name="AAF0106",
        display_name="AAF 01/06",
        type=FrameworkType.INTERNAL_CONTROL,
        report_types=[ReportType.SOC1, ReportType.SOC2, ReportType.COMBINED],
        standards=["AAF 01/06", "AUASB"],
        categories=["Control Objectives", "Control Procedures"],
        criteria_file="aaf0106.json",
        color="#00BCD4",  # Cyan
        icon="verified_user",
        description="Australian Auditing Framework (Australian SOC equivalent)",
        priority=7
    ),
    
    "GS007": FrameworkInfo(
        name="GS007",
        display_name="GS 007",
        type=FrameworkType.INTERNAL_CONTROL,
        report_types=[ReportType.SOC1, ReportType.SOC2, ReportType.COMBINED],
        standards=["GS 007", "IDW"],
        categories=["Control Environment", "Control Activities"],
        criteria_file="gs007.json",
        color="#673AB7",  # Deep Purple
        icon="security",
        description="German auditing standard (German SOC equivalent)",
        priority=8
    ),
    
    "ISO27001": FrameworkInfo(
        name="ISO27001",
        display_name="ISO 27001",
        type=FrameworkType.ISO_STANDARD,
        report_types=[ReportType.SOC2, ReportType.COMBINED],
        standards=["ISO/IEC 27001:2013", "ISO/IEC 27001:2022"],
        categories=["Information Security Management", "Risk Management", "Asset Management"],
        criteria_file="iso27001.json",
        color="#607D8B",  # Blue Grey
        icon="lock",
        description="Information Security Management System standard",
        priority=9
    ),
    
    "NIST": FrameworkInfo(
        name="NIST",
        display_name="NIST Cybersecurity Framework",
        type=FrameworkType.NIST_FRAMEWORK,
        report_types=[ReportType.SOC2, ReportType.COMBINED],
        standards=["NIST CSF 1.1", "NIST CSF 2.0"],
        categories=["Identify", "Protect", "Detect", "Respond", "Recover"],
        criteria_file="nist_csf.json",
        color="#795548",  # Brown
        icon="verified",
        description="NIST Cybersecurity Framework",
        priority=10
    ),
}


def get_framework_info(framework_name: str) -> Optional[FrameworkInfo]:
    """
    Get framework metadata by name.
    
    Args:
        framework_name: Framework identifier (e.g., "TSC", "COSO")
        
    Returns:
        FrameworkInfo object or None if not found
    """
    return FRAMEWORK_REGISTRY.get(framework_name)


def get_frameworks_by_report_type(report_type: ReportType) -> Dict[str, FrameworkInfo]:
    """
    Get all frameworks applicable to a specific report type.
    
    Args:
        report_type: ReportType enum value (SOC1, SOC2, COMBINED)
        
    Returns:
        Dictionary of framework_name -> FrameworkInfo for applicable frameworks
    """
    return {
        name: info
        for name, info in FRAMEWORK_REGISTRY.items()
        if report_type in info.report_types
    }


def get_frameworks_by_standard(standard: str) -> Dict[str, FrameworkInfo]:
    """
    Find frameworks that reference a specific standard.
    
    Args:
        standard: Standard identifier (e.g., "ISAE 3402", "SSAE 18")
        
    Returns:
        Dictionary of framework_name -> FrameworkInfo
    """
    standard_upper = standard.upper()
    return {
        name: info
        for name, info in FRAMEWORK_REGISTRY.items()
        if any(standard_upper in s.upper() for s in info.standards)
    }


def get_all_framework_names() -> List[str]:
    """Get list of all registered framework names."""
    return list(FRAMEWORK_REGISTRY.keys())


def get_frameworks_sorted_by_priority() -> List[tuple[str, FrameworkInfo]]:
    """Get frameworks sorted by priority (lower number = higher priority)."""
    return sorted(FRAMEWORK_REGISTRY.items(), key=lambda x: x[1].priority)

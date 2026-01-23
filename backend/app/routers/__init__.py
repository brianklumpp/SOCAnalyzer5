"""
Router modules for SOCAnalyzer backend.

Import all routers for easy registration in main.py:
    from .routers import (
        scan_router, report_router, control_router, cuec_router,
        suborg_router, deviation_router, executive_summary_router,
        baseline_router, config_router
    )
"""
from . import (
    scan_router,
    report_router,
    control_router,
    cuec_router,
    suborg_router,
    deviation_router,
    executive_summary_router,
    baseline_router,
    config_router,
    auth_router,
    users_router,
    grace_router,
    objective_router,
)

__all__ = [
    "scan_router",
    "report_router",
    "control_router",
    "cuec_router",
    "suborg_router",
    "deviation_router",
    "executive_summary_router",
    "baseline_router",
    "config_router",
    "auth_router",
    "users_router",
    "grace_router",
    "objective_router",
]

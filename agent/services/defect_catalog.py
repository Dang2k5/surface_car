from __future__ import annotations

from typing import Any, Protocol


class DefectCatalogService(Protocol):
    def match(self, cv_label: str) -> list[dict[str, Any]]: ...


class StaticDefectCatalog:
    """Deterministic fallback used by graph unit tests and offline demos."""

    # `rule_type`/`min_mm`/`max_mm`/`min_detection_count` are the structured counterpart to
    # `classification_rule` that agent/services/defect_rule_engine.py actually evaluates
    # (classification_rule stays free text, for humans to read) -- mirrors the same one-time
    # backfill backend/app/database.py's _backfill_default_defect_code_rules() applies to the
    # real DB catalog, so tests/offline demos using this fallback see identical behavior.
    _ITEMS = (
        {"defect_code": "DENT01", "defect_type": "dent", "cv_label": "dent", "defect_family": "PANEL_DENT", "display_name": "Vết móp nhỏ", "classification_rule": "estimated_width_mm <= 25", "default_severity": "C", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "THRESHOLD_MM", "min_mm": None, "max_mm": 25},
        {"defect_code": "DENT02", "defect_type": "dent", "cv_label": "dent", "defect_family": "PANEL_DENT", "display_name": "Vết móp trung bình", "classification_rule": "25 < estimated_width_mm <= 50", "default_severity": "B", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "THRESHOLD_MM", "min_mm": 25, "max_mm": 50},
        {"defect_code": "DENT03", "defect_type": "dent", "cv_label": "dent", "defect_family": "PANEL_DENT", "display_name": "Vết móp lớn", "classification_rule": "estimated_width_mm > 50", "default_severity": "A", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "THRESHOLD_MM", "min_mm": 50, "max_mm": None},
        {"defect_code": "DENT04", "defect_type": "dent", "cv_label": "dent", "defect_family": "PANEL_DENT_CREASE", "display_name": "Móp có nếp gấp", "classification_rule": "bbox aspect ratio >= 2 and QC confirmation", "default_severity": "A", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "REQUIRES_HUMAN", "min_mm": None, "max_mm": None},
        {"defect_code": "DENT05", "defect_type": "dent", "cv_label": "dent", "defect_family": "PANEL_DENT_CLUSTER", "display_name": "Cụm nhiều vết móp", "classification_rule": "at least 2 dent detections", "default_severity": "A", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "MIN_COUNT", "min_detection_count": 2},
        {"defect_code": "SCRATCH01", "defect_type": "scratch", "cv_label": "scratch", "defect_family": "SURFACE_SCRATCH", "display_name": "Vết xước nhỏ", "classification_rule": "estimated_width_mm <= 50", "default_severity": "C", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "THRESHOLD_MM", "min_mm": None, "max_mm": 50},
        {"defect_code": "SCRATCH02", "defect_type": "scratch", "cv_label": "scratch", "defect_family": "SURFACE_SCRATCH", "display_name": "Vết xước trung bình", "classification_rule": "50 < estimated_width_mm <= 100", "default_severity": "B", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "THRESHOLD_MM", "min_mm": 50, "max_mm": 100},
        {"defect_code": "SCRATCH03", "defect_type": "scratch", "cv_label": "scratch", "defect_family": "SURFACE_SCRATCH", "display_name": "Vết xước dài", "classification_rule": "estimated_width_mm > 100", "default_severity": "A", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "THRESHOLD_MM", "min_mm": 100, "max_mm": None},
        {"defect_code": "SCRATCH04", "defect_type": "scratch", "cv_label": "scratch", "defect_family": "SURFACE_SCRATCH_CLUSTER", "display_name": "Cụm nhiều vết xước", "classification_rule": "at least 2 scratch detections", "default_severity": "B", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "MIN_COUNT", "min_detection_count": 2},
        {"defect_code": "SCRATCH05", "defect_type": "scratch", "cv_label": "scratch", "defect_family": "SURFACE_SCRATCH_EDGE", "display_name": "Vết xước vùng mép", "classification_rule": "left/right edge position", "default_severity": "B", "measurement_required": 1, "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL", "rule_type": "REQUIRES_HUMAN"},
    )

    def match(self, cv_label: str) -> list[dict[str, Any]]:
        label = cv_label.strip().lower()
        return [dict(item) for item in self._ITEMS if item["cv_label"] == label]


class DatabaseDefectCatalog:
    def __init__(self, database: Any) -> None:
        self.database = database

    def match(self, cv_label: str) -> list[dict[str, Any]]:
        return self.database.match_defect_codes(cv_label)

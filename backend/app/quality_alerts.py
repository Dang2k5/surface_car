from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from pydantic import BaseModel


class InspectionFinding(BaseModel):
    inspection_id: str
    thread_id: str
    vehicle_id: str
    inspected_at: str
    defect_type: str
    classified_defect_code: str
    defect_family: str
    zone_name: str
    camera_id: str
    confidence: float
    severity: str
    decision: str
    final_status: str
    recommendation_code: str
    recommendation: str
    image_url: str


class DefectAggregate(BaseModel):
    defect_type: str
    occurrence_count: int
    affected_vehicle_count: int
    zones: list[str]
    camera_ids: list[str]
    average_confidence: float
    maximum_confidence: float
    first_seen: str
    last_seen: str


class QualityAlert(BaseModel):
    id: str
    severity: str
    status: str = "OPEN"
    defect_type: str
    zone_name: str
    camera_id: str
    occurrence_count: int
    affected_vehicle_count: int
    affected_vehicle_ids: list[str]
    related_defect_codes: list[str]
    similar_code_warning: bool
    average_confidence: float
    maximum_confidence: float
    first_seen: str
    last_seen: str
    window_hours: int
    window_size: int
    consecutive_count: int
    trigger_type: str
    predicted_root_cause: str
    upstream_target_shop: str
    actionable_routing_command: str
    message_en: str
    message_vi: str
    recommendation_en: str
    recommendation_vi: str
    upstream_checks_en: list[str]
    upstream_checks_vi: list[str]
    occurrences: list[InspectionFinding]
    policy_decision: dict[str, Any]
    ai_analysis: dict[str, Any]


class QualityAlertSummary(BaseModel):
    generated_at: str
    window_hours: int
    window_size: int
    minimum_occurrences: int
    in_window_threshold: int
    analyzed_inspections: int
    defect_breakdown: list[DefectAggregate]
    findings: list[InspectionFinding]
    alerts: list[QualityAlert]


class RepetitionAlertService:
    """Deterministic quality trend monitor over persisted LangGraph results."""

    def __init__(self, repository: Any, policy_catalog: Any, reasoning: Any) -> None:
        self.repository = repository
        self.policy_catalog = policy_catalog
        self.reasoning = reasoning

    def analyze(
        self,
        *,
        window_hours: int = 24,
        window_size: int = 10,
        minimum_occurrences: int = 3,
        in_window_threshold: int = 4,
    ) -> QualityAlertSummary:
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=window_hours)
        candidates = []
        for state in self.repository.list_with_metadata():
            persisted_at = _parse_timestamp(state.get("_persisted_at"))
            if persisted_at < cutoff or not state.get("defect_detected"):
                continue
            if state.get("defect_type") not in {"scratch", "dent"}:
                continue
            if state.get("decision") == "PASS":
                continue
            candidates.append(state)

        candidates.sort(
            key=lambda item: _parse_timestamp(item.get("_persisted_at")),
            reverse=True,
        )
        records = candidates[:window_size]

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for state in records:
            key = (
                str(state.get("defect_type", "unknown")),
                _zone_name(state),
            )
            grouped[key].append(state)

        findings = sorted(
            (_finding_from_state(state) for state in records),
            key=lambda item: item.inspected_at,
            reverse=True,
        )
        defect_breakdown = _build_defect_breakdown(records)

        alerts: list[QualityAlert] = []
        for (defect_type, zone_name), items in grouped.items():
            vehicle_ids = sorted({str(item.get("vehicle_id", "UNKNOWN")) for item in items})
            consecutive_count = _leading_consecutive_count(records, defect_type, zone_name)
            triggered_by_consecutive = consecutive_count >= minimum_occurrences
            triggered_by_window = len(vehicle_ids) >= in_window_threshold
            if not triggered_by_consecutive and not triggered_by_window:
                continue
            camera_ids = sorted({str(item.get("camera_id") or "unknown_camera") for item in items})
            camera_id = camera_ids[0] if len(camera_ids) == 1 else "MULTI_CAMERA"
            confidences = [float(item.get("confidence") or 0) for item in items]
            related_codes = sorted(
                {str(item.get("classified_defect_code")) for item in items if item.get("classified_defect_code")}
            )
            similar_code_warning = len(related_codes) > 1
            timestamps = sorted(_parse_timestamp(item.get("_persisted_at")) for item in items)
            severity = "CRITICAL" if triggered_by_consecutive else "WARNING"
            trigger_type = "CONSECUTIVE" if triggered_by_consecutive else "WINDOW_FREQUENCY"
            root_cause, target_shop = _predicted_root_cause(defect_type)
            routing_command = "ROUTE_AFFECTED_BATCH_TO_OFFLINE_INSPECTION_BUFFER"
            key_text = f"{defect_type}|{zone_name}|{window_size}"
            alert_id = hashlib.sha256(key_text.encode("utf-8")).hexdigest()[:16]
            trend_state = {
                "defect_type": defect_type,
                "confidence": round(sum(confidences) / len(confidences), 4),
                "zone_name": zone_name,
                "camera_id": camera_id,
                "severity": severity,
                "evidence_tags": [
                    "affected_vehicle_list",
                    "time_window",
                    "camera_and_zone_group",
                ],
                "trend_context": {
                    "affected_vehicle_count": len(vehicle_ids),
                    "affected_vehicle_ids": vehicle_ids,
                    "window_hours": window_hours,
                    "window_size": window_size,
                    "consecutive_count": consecutive_count,
                    "trigger_type": trigger_type,
                },
            }
            policy = self.policy_catalog.evaluate_named("FNS-TREND-001", trend_state)
            # Dashboard trend aggregation must remain low-latency. LLM reasoning
            # is reserved for an explicit inspection; trend cards use the same
            # deterministic policy fallback instead of issuing N sequential API calls.
            trend_reasoning = getattr(self.reasoning, "fallback", self.reasoning)
            analysis = trend_reasoning.analyze(trend_state, policy)
            alerts.append(
                QualityAlert(
                    id=alert_id,
                    severity=severity,
                    defect_type=defect_type,
                    zone_name=zone_name,
                    camera_id=camera_id,
                    occurrence_count=len(items),
                    affected_vehicle_count=len(vehicle_ids),
                    affected_vehicle_ids=vehicle_ids,
                    related_defect_codes=related_codes,
                    similar_code_warning=similar_code_warning,
                    average_confidence=round(sum(confidences) / len(confidences), 4),
                    maximum_confidence=round(max(confidences), 4),
                    first_seen=timestamps[0].isoformat(),
                    last_seen=timestamps[-1].isoformat(),
                    window_hours=window_hours,
                    window_size=window_size,
                    consecutive_count=consecutive_count,
                    trigger_type=trigger_type,
                    predicted_root_cause=root_cause,
                    upstream_target_shop=target_shop,
                    actionable_routing_command=routing_command,
                    message_en=(
                        f"Repeated {defect_type} detections were found in {zone_name}: "
                        f"{consecutive_count} consecutive and {len(vehicle_ids)}/{window_size} recent vehicles. "
                        f"Related QC codes: {', '.join(related_codes) or 'unclassified'}."
                    ),
                    message_vi=(
                        f"Phát hiện lỗi {defect_type} lặp lại tại {zone_name}: "
                        f"{consecutive_count} xe liên tiếp và {len(vehicle_ids)}/{window_size} xe gần nhất. "
                        f"Mã lỗi liên quan: {', '.join(related_codes) or 'chưa phân loại'}."
                    ),
                    recommendation_en=(
                        "Keep affected vehicles controlled, confirm the trend with a named QC reviewer, "
                        "and escalate to the upstream process owner before release."
                    ),
                    recommendation_vi=(
                        "Kiểm soát các xe liên quan, yêu cầu QC xác nhận xu hướng và thông báo chủ công đoạn "
                        "phía trước trước khi cho phép release."
                    ),
                    upstream_checks_en=_upstream_checks("en", zone_name, camera_id),
                    upstream_checks_vi=_upstream_checks("vi", zone_name, camera_id),
                    occurrences=sorted(
                        (_finding_from_state(item) for item in items),
                        key=lambda item: item.inspected_at,
                        reverse=True,
                    ),
                    policy_decision=policy.model_dump(mode="json"),
                    ai_analysis=analysis.model_dump(mode="json"),
                )
            )
        alerts.sort(key=lambda item: (item.severity != "CRITICAL", -item.affected_vehicle_count))
        return QualityAlertSummary(
            generated_at=now.isoformat(),
            window_hours=window_hours,
            window_size=window_size,
            minimum_occurrences=minimum_occurrences,
            in_window_threshold=in_window_threshold,
            analyzed_inspections=len(records),
            defect_breakdown=defect_breakdown,
            findings=findings,
            alerts=alerts,
        )


def _finding_from_state(state: dict[str, Any]) -> InspectionFinding:
    return InspectionFinding(
        inspection_id=str(state.get("inspection_id") or "UNKNOWN"),
        thread_id=str(state.get("thread_id") or "UNKNOWN"),
        vehicle_id=str(state.get("vehicle_id") or "UNKNOWN"),
        inspected_at=_parse_timestamp(state.get("_persisted_at")).isoformat(),
        defect_type=str(state.get("defect_type") or "unknown"),
        classified_defect_code=str(state.get("classified_defect_code") or ""),
        defect_family=str(state.get("defect_family") or ""),
        zone_name=_zone_name(state),
        camera_id=str(state.get("camera_id") or "unknown_camera"),
        confidence=round(float(state.get("confidence") or 0), 4),
        severity=str(state.get("severity") or "UNASSESSED"),
        decision=str(state.get("decision") or "UNKNOWN"),
        final_status=str(state.get("final_status") or "UNKNOWN"),
        recommendation_code=str(state.get("recommendation_code") or ""),
        recommendation=str(state.get("recommendation") or ""),
        image_url=str(state.get("image_url") or ""),
    )


def _zone_name(state: dict[str, Any]) -> str:
    return str(state.get("zone_name") or "unknown_zone")


def _leading_consecutive_count(
    records: list[dict[str, Any]],
    defect_type: str,
    zone_name: str,
) -> int:
    count = 0
    for state in records:
        if str(state.get("defect_type")) != defect_type or _zone_name(state) != zone_name:
            break
        count += 1
    return count


def _predicted_root_cause(defect_type: str) -> tuple[str, str]:
    if defect_type == "dent":
        return (
            "Possible stamping-die debris, fixture contact, or robot-gripper interference; QC verification required.",
            "Stamping / Body Shop",
        )
    return (
        "Possible conveyor guide, handling fixture, or contact-surface abrasion; QC verification required.",
        "Body / Paint Handling Process",
    )


def _build_defect_breakdown(records: list[dict[str, Any]]) -> list[DefectAggregate]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for state in records:
        grouped[str(state.get("defect_type") or "unknown")].append(state)

    result: list[DefectAggregate] = []
    for defect_type, items in grouped.items():
        confidences = [float(item.get("confidence") or 0) for item in items]
        timestamps = sorted(_parse_timestamp(item.get("_persisted_at")) for item in items)
        result.append(
            DefectAggregate(
                defect_type=defect_type,
                occurrence_count=len(items),
                affected_vehicle_count=len({str(item.get("vehicle_id") or "UNKNOWN") for item in items}),
                zones=sorted({_zone_name(item) for item in items}),
                camera_ids=sorted({str(item.get("camera_id") or "unknown_camera") for item in items}),
                average_confidence=round(sum(confidences) / len(confidences), 4),
                maximum_confidence=round(max(confidences), 4),
                first_seen=timestamps[0].isoformat(),
                last_seen=timestamps[-1].isoformat(),
            )
        )
    return sorted(result, key=lambda item: (-item.occurrence_count, item.defect_type))


def _parse_timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _upstream_checks(language: str, zone_name: str, camera_id: str) -> list[str]:
    if language == "vi":
        return [
            f"Xác nhận camera {camera_id}: tiêu cự, ánh sáng, vị trí gá và độ sạch của lens.",
            f"Kiểm tra đồ gá, dụng cụ tiếp xúc và thao tác có thể ảnh hưởng tới {zone_name}.",
            "Đối chiếu thời điểm lỗi với ca sản xuất và lịch sử bảo trì thiết bị.",
            "Cách ly mẫu liên quan và thực hiện kiểm tra xác nhận dưới ánh sáng kiểm soát.",
            "Ghi nhận người phụ trách, hành động khắc phục và tiêu chí release sau kiểm tra lại.",
        ]
    return [
        f"Verify {camera_id}: focus, lighting, fixture position, and lens cleanliness.",
        f"Inspect fixtures, contact tools, and handling operations that may affect {zone_name}.",
        "Correlate occurrence times with shift and equipment maintenance history.",
        "Contain affected samples and perform confirmation inspection under controlled lighting.",
        "Record the owner, corrective action, and release criteria after reinspection.",
    ]


def build_quality_alert_report(summary: QualityAlertSummary) -> BytesIO:
    """Create an operator-ready DOCX using the compact_reference_guide preset."""
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25
    for name, size, color, before, after in (
        ("Heading 1", 16, "2E74B5", 18, 10),
        ("Heading 2", 13, "2E74B5", 14, 7),
        ("Heading 3", 12, "1F4D78", 10, 5),
    ):
        style = styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)

    header = section.header.paragraphs[0]
    header.text = "VISUAL QC AGENT  |  FNS QUALITY TREND ALERT"
    header.runs[0].font.size = Pt(8)
    header.runs[0].font.bold = True
    header.runs[0].font.color.rgb = RGBColor.from_string("607B8D")
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run("Internal QC working report  |  Generated by deterministic trend rules").font.size = Pt(8)

    kicker = document.add_paragraph()
    kicker.paragraph_format.space_after = Pt(3)
    run = kicker.add_run("QUALITY ESCALATION REPORT")
    run.bold = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor.from_string("C24D5A")
    title = document.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    title_run = title.add_run("Repeated Defect Alert")
    title_run.bold = True
    title_run.font.size = Pt(24)
    title_run.font.color.rgb = RGBColor.from_string("0B2940")
    subtitle = document.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(14)
    subtitle_run = subtitle.add_run("Agent-generated signal for upstream process verification")
    subtitle_run.font.size = Pt(11)
    subtitle_run.font.color.rgb = RGBColor.from_string("607B8D")

    metadata = document.add_table(rows=2, cols=4)
    set_table_geometry(metadata, [1350, 3330, 1350, 3330])
    metadata_values = [
        ("Generated", _format_dt(summary.generated_at), "Window", f"{summary.window_hours} hours"),
        ("Inspections", str(summary.analyzed_inspections), "Open alerts", str(len(summary.alerts))),
    ]
    for row, values in zip(metadata.rows, metadata_values):
        for index, value in enumerate(values):
            cell = row.cells[index]
            cell.text = value
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if index % 2 == 0:
                shade_cell(cell, "EAF1F5")
                cell.paragraphs[0].runs[0].bold = True
            cell.paragraphs[0].runs[0].font.size = Pt(9)

    document.add_heading("Agent assessment", level=1)
    lead = document.add_paragraph()
    lead.paragraph_format.space_after = Pt(8)
    if summary.alerts:
        critical = sum(item.severity == "CRITICAL" for item in summary.alerts)
        lead.add_run(
            f"The trend monitor found {len(summary.alerts)} repeated-defect group(s), including "
            f"{critical} critical alert(s). QC must verify the upstream process before release."
        ).bold = True
    else:
        lead.add_run("No repeated-defect group crossed the configured threshold in this window.").bold = True

    document.add_heading("Defect summary from inspection history", level=1)
    if summary.defect_breakdown:
        defect_table = document.add_table(rows=1, cols=5)
        set_table_geometry(defect_table, [1500, 1000, 1000, 4000, 1860])
        for cell, value in zip(
            defect_table.rows[0].cells,
            ("Defect", "Events", "Vehicles", "Zones / cameras", "Confidence"),
        ):
            cell.text = value
            shade_cell(cell, "DCEAF1")
            cell.paragraphs[0].runs[0].bold = True
        for item in summary.defect_breakdown:
            row = defect_table.add_row()
            values = (
                item.defect_type,
                str(item.occurrence_count),
                str(item.affected_vehicle_count),
                f"{', '.join(item.zones)}\n{', '.join(item.camera_ids)}",
                f"Avg {item.average_confidence:.1%}\nMax {item.maximum_confidence:.1%}",
            )
            for cell, value in zip(row.cells, values):
                cell.text = value
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                for run in cell.paragraphs[0].runs:
                    run.font.size = Pt(8)
    else:
        document.add_paragraph("No defect finding is retained in the selected monitoring window.")

    document.add_heading("Inspection-level findings", level=1)
    if summary.findings:
        finding_table = document.add_table(rows=1, cols=7)
        set_table_geometry(finding_table, [1250, 1100, 1100, 1700, 850, 1050, 2310])
        for cell, value in zip(
            finding_table.rows[0].cells,
            ("Time", "Inspection", "Vehicle", "Defect / location", "Conf.", "Severity", "Decision / route"),
        ):
            cell.text = value
            shade_cell(cell, "DCEAF1")
            cell.paragraphs[0].runs[0].bold = True
        for finding in summary.findings:
            row = finding_table.add_row()
            values = (
                _format_dt(finding.inspected_at),
                finding.inspection_id,
                finding.vehicle_id,
                f"{finding.defect_type}\n{finding.zone_name} / {finding.camera_id}",
                f"{finding.confidence:.1%}",
                finding.severity,
                f"{finding.decision}\n{finding.final_status}\n{finding.recommendation_code}",
            )
            for cell, value in zip(row.cells, values):
                cell.text = value
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                for run in cell.paragraphs[0].runs:
                    run.font.size = Pt(7.5)
    else:
        document.add_paragraph("No inspection-level finding is available for this report.")

    for index, alert in enumerate(summary.alerts, start=1):
        document.add_heading(f"Alert {index}: {alert.defect_type.upper()} - {alert.zone_name}", level=2)
        alert_table = document.add_table(rows=5, cols=2)
        set_table_geometry(alert_table, [2160, 7200])
        rows = [
            ("Severity", alert.severity),
            ("Detection source", alert.camera_id),
            ("Affected vehicles", f"{alert.affected_vehicle_count} ({', '.join(alert.affected_vehicle_ids)})"),
            ("Confidence", f"Average {alert.average_confidence:.1%} | Maximum {alert.maximum_confidence:.1%}"),
            ("Observed window", f"{_format_dt(alert.first_seen)} to {_format_dt(alert.last_seen)}"),
        ]
        for row, (label, value) in zip(alert_table.rows, rows):
            row.cells[0].text = label
            row.cells[1].text = value
            shade_cell(row.cells[0], "EAF1F5")
            row.cells[0].paragraphs[0].runs[0].bold = True
            for cell in row.cells:
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                cell.paragraphs[0].runs[0].font.size = Pt(9)

        document.add_heading("Inspections contributing to this alert", level=3)
        occurrence_table = document.add_table(rows=1, cols=6)
        set_table_geometry(occurrence_table, [1450, 1450, 1450, 1550, 1100, 2360])
        for cell, value in zip(
            occurrence_table.rows[0].cells,
            ("Time", "Inspection", "Vehicle", "Confidence", "Severity", "Final route"),
        ):
            cell.text = value
            shade_cell(cell, "F3E4E7")
            cell.paragraphs[0].runs[0].bold = True
        for occurrence in alert.occurrences:
            row = occurrence_table.add_row()
            values = (
                _format_dt(occurrence.inspected_at),
                occurrence.inspection_id,
                occurrence.vehicle_id,
                f"{occurrence.confidence:.1%}",
                occurrence.severity,
                occurrence.final_status,
            )
            for cell, value in zip(row.cells, values):
                cell.text = value
                for run in cell.paragraphs[0].runs:
                    run.font.size = Pt(8)

        document.add_heading("Required upstream checks", level=3)
        for check in alert.upstream_checks_en:
            paragraph = document.add_paragraph(style="List Number")
            paragraph.paragraph_format.space_after = Pt(4)
            paragraph.paragraph_format.line_spacing = 1.2
            paragraph.add_run(check)
        recommendation = document.add_paragraph()
        recommendation.paragraph_format.space_before = Pt(6)
        recommendation.paragraph_format.space_after = Pt(10)
        label = recommendation.add_run("Disposition: ")
        label.bold = True
        label.font.color.rgb = RGBColor.from_string("A73343")
        recommendation.add_run(alert.recommendation_en)

        document.add_heading("Policy and reasoning provenance", level=3)
        provenance = document.add_paragraph()
        policy = alert.policy_decision
        analysis = alert.ai_analysis
        provenance.add_run(
            f"Policy: {policy.get('policy_id')} @ {policy.get('policy_revision')} "
            f"({policy.get('policy_status')})\n"
        ).bold = True
        provenance.add_run(
            f"Reasoning: {analysis.get('provider')} / {analysis.get('model')}\n"
            f"Analysis: {analysis.get('summary_en')}"
        )
        for reference in policy.get("references", []):
            paragraph = document.add_paragraph(style="List Bullet")
            paragraph.add_run(
                f"{reference.get('id')}: {reference.get('title')} — {reference.get('url')}"
            )

    document.add_heading("QC sign-off", level=1)
    signoff = document.add_table(rows=3, cols=2)
    set_table_geometry(signoff, [2700, 6660])
    for row, (label, value) in zip(
        signoff.rows,
        (("QC reviewer", ""), ("Upstream process owner", ""), ("Corrective action / release evidence", "")),
    ):
        row.cells[0].text = label
        row.cells[1].text = value
        shade_cell(row.cells[0], "EAF1F5")
        row.cells[0].paragraphs[0].runs[0].bold = True

    output = BytesIO()
    document.save(output)
    output.seek(0)
    return output


def _format_dt(value: str) -> str:
    return _parse_timestamp(value).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def shade_cell(cell: Any, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def set_table_geometry(table: Any, widths: list[int]) -> None:
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    table.style = "Table Grid"
    properties = table._tbl.tblPr
    table_width = properties.find(qn("w:tblW"))
    if table_width is None:
        table_width = OxmlElement("w:tblW")
        properties.append(table_width)
    table_width.set(qn("w:type"), "dxa")
    table_width.set(qn("w:w"), str(sum(widths)))
    indent = properties.find(qn("w:tblInd"))
    if indent is None:
        indent = OxmlElement("w:tblInd")
        properties.append(indent)
    indent.set(qn("w:type"), "dxa")
    indent.set(qn("w:w"), "120")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        column = OxmlElement("w:gridCol")
        column.set(qn("w:w"), str(width))
        grid.append(column)
    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            cell.width = Inches(width / 1440)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            tc_properties = cell._tc.get_or_add_tcPr()
            tc_width = tc_properties.get_or_add_tcW()
            tc_width.set(qn("w:type"), "dxa")
            tc_width.set(qn("w:w"), str(width))
            margins = tc_properties.first_child_found_in("w:tcMar")
            if margins is None:
                margins = OxmlElement("w:tcMar")
                tc_properties.append(margins)
            for side, value in (("top", 80), ("bottom", 80), ("start", 120), ("end", 120)):
                node = margins.find(qn(f"w:{side}"))
                if node is None:
                    node = OxmlElement(f"w:{side}")
                    margins.append(node)
                node.set(qn("w:w"), str(value))
                node.set(qn("w:type"), "dxa")

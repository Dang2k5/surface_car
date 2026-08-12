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


class QualityAlert(BaseModel):
    id: str
    severity: str
    status: str = "OPEN"
    defect_type: str
    panel: str
    camera_id: str
    occurrence_count: int
    affected_vehicle_count: int
    affected_vehicle_ids: list[str]
    average_confidence: float
    maximum_confidence: float
    first_seen: str
    last_seen: str
    window_hours: int
    message_en: str
    message_vi: str
    recommendation_en: str
    recommendation_vi: str
    upstream_checks_en: list[str]
    upstream_checks_vi: list[str]


class QualityAlertSummary(BaseModel):
    generated_at: str
    window_hours: int
    minimum_occurrences: int
    analyzed_inspections: int
    alerts: list[QualityAlert]


class RepetitionAlertService:
    """Deterministic quality trend monitor over persisted LangGraph results."""

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def analyze(self, *, window_hours: int = 24, minimum_occurrences: int = 3) -> QualityAlertSummary:
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=window_hours)
        records = []
        for state in self.repository.list_with_metadata():
            persisted_at = _parse_timestamp(state.get("_persisted_at"))
            if persisted_at < cutoff or not state.get("defect_detected"):
                continue
            if not state.get("defect_type") or state.get("decision") == "PASS":
                continue
            records.append(state)

        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for state in records:
            key = (
                str(state.get("defect_type", "unknown")),
                str(state.get("panel", "unknown_panel")),
                str(state.get("camera_id", "unknown_camera")),
            )
            grouped[key].append(state)

        alerts: list[QualityAlert] = []
        for (defect_type, panel, camera_id), items in grouped.items():
            vehicle_ids = sorted({str(item.get("vehicle_id", "UNKNOWN")) for item in items})
            if len(vehicle_ids) < minimum_occurrences:
                continue
            confidences = [float(item.get("confidence") or 0) for item in items]
            timestamps = sorted(_parse_timestamp(item.get("_persisted_at")) for item in items)
            severity = "CRITICAL" if len(vehicle_ids) >= max(5, minimum_occurrences + 2) else "WARNING"
            key_text = f"{defect_type}|{panel}|{camera_id}|{window_hours}"
            alert_id = hashlib.sha256(key_text.encode("utf-8")).hexdigest()[:16]
            alerts.append(
                QualityAlert(
                    id=alert_id,
                    severity=severity,
                    defect_type=defect_type,
                    panel=panel,
                    camera_id=camera_id,
                    occurrence_count=len(items),
                    affected_vehicle_count=len(vehicle_ids),
                    affected_vehicle_ids=vehicle_ids,
                    average_confidence=round(sum(confidences) / len(confidences), 4),
                    maximum_confidence=round(max(confidences), 4),
                    first_seen=timestamps[0].isoformat(),
                    last_seen=timestamps[-1].isoformat(),
                    window_hours=window_hours,
                    message_en=(
                        f"Repeated {defect_type} detections were found on {panel} from {camera_id} "
                        f"across {len(vehicle_ids)} vehicles. The previous process must be checked."
                    ),
                    message_vi=(
                        f"Phát hiện lỗi {defect_type} lặp lại tại {panel}, camera {camera_id}, "
                        f"trên {len(vehicle_ids)} xe. QC cần kiểm tra lại công đoạn phía trước."
                    ),
                    recommendation_en=(
                        "Keep affected vehicles controlled, confirm the trend with a named QC reviewer, "
                        "and escalate to the upstream process owner before release."
                    ),
                    recommendation_vi=(
                        "Kiểm soát các xe liên quan, yêu cầu QC xác nhận xu hướng và thông báo chủ công đoạn "
                        "phía trước trước khi cho phép release."
                    ),
                    upstream_checks_en=_upstream_checks("en", panel, camera_id),
                    upstream_checks_vi=_upstream_checks("vi", panel, camera_id),
                )
            )
        alerts.sort(key=lambda item: (item.severity != "CRITICAL", -item.affected_vehicle_count))
        return QualityAlertSummary(
            generated_at=now.isoformat(),
            window_hours=window_hours,
            minimum_occurrences=minimum_occurrences,
            analyzed_inspections=len(records),
            alerts=alerts,
        )


def _parse_timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _upstream_checks(language: str, panel: str, camera_id: str) -> list[str]:
    if language == "vi":
        return [
            f"Xác nhận camera {camera_id}: tiêu cự, ánh sáng, vị trí gá và độ sạch của lens.",
            f"Kiểm tra đồ gá, dụng cụ tiếp xúc và thao tác có thể ảnh hưởng tới {panel}.",
            "Đối chiếu thời điểm lỗi với ca sản xuất, lô vật liệu và lịch sử bảo trì thiết bị.",
            "Cách ly mẫu liên quan và thực hiện kiểm tra xác nhận dưới ánh sáng kiểm soát.",
            "Ghi nhận người phụ trách, hành động khắc phục và tiêu chí release sau kiểm tra lại.",
        ]
    return [
        f"Verify {camera_id}: focus, lighting, fixture position, and lens cleanliness.",
        f"Inspect fixtures, contact tools, and handling operations that may affect {panel}.",
        "Correlate occurrence times with shift, material lot, and equipment maintenance history.",
        "Contain affected samples and perform confirmation inspection under controlled lighting.",
        "Record the owner, corrective action, and release criteria after reinspection.",
    ]


def build_quality_alert_report(summary: QualityAlertSummary) -> BytesIO:
    """Create an operator-ready DOCX using the compact_reference_guide preset."""
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.72)
    section.bottom_margin = Inches(0.72)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)
    section.header_distance = Inches(0.35)
    section.footer_distance = Inches(0.35)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.2
    for name, size, color, before, after in (
        ("Heading 1", 16, "1D5F7A", 16, 8),
        ("Heading 2", 13, "1D5F7A", 12, 6),
        ("Heading 3", 11.5, "24465B", 9, 4),
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
    _set_table_geometry(metadata, [1350, 3330, 1350, 3330])
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
                _shade_cell(cell, "EAF1F5")
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

    for index, alert in enumerate(summary.alerts, start=1):
        document.add_heading(f"Alert {index}: {alert.defect_type.upper()} - {alert.panel}", level=2)
        alert_table = document.add_table(rows=5, cols=2)
        _set_table_geometry(alert_table, [2160, 7200])
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
            _shade_cell(row.cells[0], "EAF1F5")
            row.cells[0].paragraphs[0].runs[0].bold = True
            for cell in row.cells:
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                cell.paragraphs[0].runs[0].font.size = Pt(9)

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

    document.add_heading("QC sign-off", level=1)
    signoff = document.add_table(rows=3, cols=2)
    _set_table_geometry(signoff, [2700, 6660])
    for row, (label, value) in zip(
        signoff.rows,
        (("QC reviewer", ""), ("Upstream process owner", ""), ("Corrective action / release evidence", "")),
    ):
        row.cells[0].text = label
        row.cells[1].text = value
        _shade_cell(row.cells[0], "EAF1F5")
        row.cells[0].paragraphs[0].runs[0].bold = True

    output = BytesIO()
    document.save(output)
    output.seek(0)
    return output


def _format_dt(value: str) -> str:
    return _parse_timestamp(value).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _shade_cell(cell: Any, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def _set_table_geometry(table: Any, widths: list[int]) -> None:
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
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
            tc_width = cell._tc.get_or_add_tcPr().get_or_add_tcW()
            tc_width.set(qn("w:type"), "dxa")
            tc_width.set(qn("w:w"), str(width))

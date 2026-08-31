from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

# Severity ladder, worst-first — mirrors the WATCH/WARNING/CRITICAL convention already used by
# backend/app/quality_alerts.py's RepetitionAlertService, kept in a separate service/file on
# purpose: that service analyzes defect *type* trends across zones/cameras, this one analyzes
# the *operational* HITL escalation rate per production line/station. Different signals,
# different questions — merging them would make one analyze() do two unrelated jobs.
_SEVERITY_RANK = {"CRITICAL": 0, "WARNING": 1, "WATCH": 2}


class HitlRateAlert(BaseModel):
    station_id: str
    severity: str  # WATCH | WARNING | CRITICAL
    trigger_type: str  # CONSECUTIVE_BURST | SUSTAINED_RATE
    consecutive_count: int
    hitl_rate: float
    sample_size: int
    window_size: int
    message_vi: str
    message_en: str
    recommend_mandatory_review: bool
    recommend_stop_line: bool


def _requires_hitl(state: dict[str, Any]) -> bool:
    """A case needed a human at some point iff assess_result ever routed it to HITL.

    Deliberately NOT `agent_graph_runs.status` (PASS/FAIL/WAITING_FOR_HITL) — that column is
    overwritten with the final outcome once a pending HITL case is resumed, so by the time a
    later request reads it, a *resolved* HITL case is indistinguishable from one that never
    needed a human. `assessment_route` inside the persisted state is set once in
    QCNodes.assess_result and is never reset by human_review/supervisor_review/
    generate_recommendation, so it survives resolution.
    """
    return state.get("assessment_route") == "HITL"


class HitlRateAlertService:
    """Detects an abnormal Human-In-The-Loop escalation rate for one production line/station.

    Two independent signals, worst wins (same principle as RepetitionAlertService's
    consecutive-streak + window-share pair for defect trends):

    - `consecutive_count`: how many of the most recent inspections IN A ROW needed HITL,
      counting back from the newest until the first one that didn't. Reacts immediately to a
      sudden burst (e.g. 8 vehicles in a row all failing model confidence) even with few total
      samples — a burst spread out over a much larger window would otherwise get diluted into
      a harmless-looking rate.
    - `hitl_rate`: share of HITL cases over a LARGER window (default 100, not the same small
      window used for the streak). Catches a sustained elevated baseline that never bursts hard
      enough to trip the streak trigger. Requires `min_sample_for_rate` records before it's
      evaluated at all, so a handful of inspections at the start of a shift can't produce a
      statistically meaningless "80% HITL" reading.

    Nothing here is persisted: calling `analyze()` while nothing changed simply returns the
    same result. There is no "mandatory review" flag to remember to clear later.
    """

    def __init__(self, database: Any) -> None:
        self.database = database

    def analyze(
        self,
        *,
        station_id: str,
        window_size: int = 100,
        min_sample_for_rate: int = 20,
        watch_consecutive: int = 3,
        warning_consecutive: int = 5,
        critical_consecutive: int = 8,
        watch_rate: float = 0.25,
        warning_rate: float = 0.40,
        critical_rate: float = 0.55,
    ) -> HitlRateAlert | None:
        # Keep the three tiers monotonically ordered even if a caller passes inconsistent
        # thresholds — mirrors RepetitionAlertService.analyze()'s same guard for its own ladder.
        watch_consecutive = min(watch_consecutive, warning_consecutive, critical_consecutive)
        warning_consecutive = min(warning_consecutive, critical_consecutive)
        watch_rate = min(watch_rate, warning_rate, critical_rate)
        warning_rate = min(warning_rate, critical_rate)

        rows = self.database.get_recent_outcomes_by_station(station_id, limit=window_size)
        states = [json.loads(row["state_json"]) for row in rows]
        sample_size = len(states)
        if sample_size == 0:
            return None

        consecutive_count = 0
        for state in states:  # newest first
            if not _requires_hitl(state):
                break
            consecutive_count += 1

        hitl_count = sum(1 for state in states if _requires_hitl(state))
        rate = hitl_count / sample_size

        consecutive_severity = self._severity_from_threshold(
            consecutive_count, watch_consecutive, warning_consecutive, critical_consecutive
        )
        rate_severity = (
            self._severity_from_threshold(rate, watch_rate, warning_rate, critical_rate)
            if sample_size >= min_sample_for_rate
            else None
        )

        severity = self._worst(consecutive_severity, rate_severity)
        if severity is None:
            return None

        trigger_type = (
            "CONSECUTIVE_BURST"
            if consecutive_severity is not None
            and _SEVERITY_RANK[consecutive_severity] <= _SEVERITY_RANK.get(rate_severity, 99)
            else "SUSTAINED_RATE"
        )

        return HitlRateAlert(
            station_id=station_id,
            severity=severity,
            trigger_type=trigger_type,
            consecutive_count=consecutive_count,
            hitl_rate=round(rate, 3),
            sample_size=sample_size,
            window_size=window_size,
            message_vi=(
                f"Trạm {station_id}: {consecutive_count} xe liên tiếp cần QC xét duyệt "
                f"({hitl_count}/{sample_size} = {rate:.0%} trong {sample_size} lần kiểm tra gần nhất)."
            ),
            message_en=(
                f"Station {station_id}: {consecutive_count} consecutive vehicles required HITL "
                f"({hitl_count}/{sample_size} = {rate:.0%} over the last {sample_size} inspections)."
            ),
            recommend_mandatory_review=severity in {"WARNING", "CRITICAL"},
            recommend_stop_line=severity == "CRITICAL",
        )

    @staticmethod
    def _severity_from_threshold(
        value: float, watch: float, warning: float, critical: float
    ) -> str | None:
        if value >= critical:
            return "CRITICAL"
        if value >= warning:
            return "WARNING"
        if value >= watch:
            return "WATCH"
        return None

    @staticmethod
    def _worst(a: str | None, b: str | None) -> str | None:
        candidates = [s for s in (a, b) if s is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda s: _SEVERITY_RANK[s])


__all__ = ("HitlRateAlert", "HitlRateAlertService")

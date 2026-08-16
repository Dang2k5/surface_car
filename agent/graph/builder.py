from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agent.graph.nodes import QCNodes
from agent.graph.routes import route_assessment
from agent.graph.state import QCState
from agent.services.defect_catalog import DefectCatalogService, StaticDefectCatalog
from agent.services.detector import DetectorService, MockDetector
from agent.services.policy import PolicyCatalog
from agent.services.reasoning import DeterministicReasoningService, ReasoningService
from agent.services.repository import MockQCRepository, QCRepository
from agent.services.verifier import MockVerifier, VerifierService


def build_qc_graph(
    *,
    detector: DetectorService | None = None,
    verifier: VerifierService | None = None,
    reasoning: ReasoningService | None = None,
    policy_catalog: PolicyCatalog | None = None,
    repository: QCRepository | None = None,
    checkpointer: Any | None = None,
    defect_catalog: DefectCatalogService | None = None,
):
    """Compile the Visual QC graph with swappable services and persistence."""
    nodes = QCNodes(
        detector=detector or MockDetector(),
        verifier=verifier or MockVerifier(),
        reasoning=reasoning or DeterministicReasoningService(),
        policy_catalog=policy_catalog or PolicyCatalog(),
        repository=repository or MockQCRepository(),
        defect_catalog=defect_catalog or StaticDefectCatalog(),
    )
    builder = StateGraph(QCState)
    builder.add_node("prepare_input", nodes.prepare_input)
    builder.add_node("detect_defect", nodes.detect_defect)
    builder.add_node("assess_result", nodes.assess_result)
    builder.add_node("verify_defect", nodes.verify_defect)
    builder.add_node("human_review", nodes.human_review)
    builder.add_node("generate_recommendation", nodes.generate_recommendation)
    builder.add_node("save_result", nodes.save_result)

    builder.add_edge(START, "prepare_input")
    builder.add_edge("prepare_input", "detect_defect")
    builder.add_edge("detect_defect", "assess_result")
    builder.add_conditional_edges(
        "assess_result",
        route_assessment,
        {
            "PASS": "save_result",
            "CONFIRMED": "generate_recommendation",
            "VERIFY": "verify_defect",
            "HITL": "human_review",
        },
    )
    builder.add_edge("verify_defect", "assess_result")
    builder.add_edge("human_review", "generate_recommendation")
    builder.add_edge("generate_recommendation", "save_result")
    builder.add_edge("save_result", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def export_graph_mermaid(graph: Any, output_path: str | Path = "agent_flow.mmd") -> str:
    mermaid = graph.get_graph().draw_mermaid()
    Path(output_path).write_text(mermaid, encoding="utf-8")
    print(mermaid)
    return mermaid

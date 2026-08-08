# LangGraph Visual QC Agent

The production-shaped MVP graph lives in `agent/graph`; external capabilities are
behind adapters in `agent/services`.

## State

`QCState` is the shared, checkpointed contract passed between nodes. It contains
inspection/image metadata, detector output, confidence and severity, verification
state, HITL input, recommendation, final status, retry/error metadata, and an
append-only execution trace.

## Nodes and routing

```text
START -> prepare_input -> detect_defect -> assess_result
```

`assess_result` returns one of four route labels:

- `PASS`: no defect; save and release to the next quality gate.
- `CONFIRMED`: generate a concrete policy method, then save.
- `VERIFY`: run a second mock inspection and loop to `assess_result`.
- `HITL`: pause at `human_review` using LangGraph `interrupt()`.

The loop guard is `verify_count >= 2`. An uncertain result can therefore never
loop forever; it is routed to HITL on the second unsuccessful verification.

## HITL and persistence

The graph is compiled with `InMemorySaver` for local development. Every invocation
must use `configurable.thread_id`. Resume the same thread with:

```python
from langgraph.types import Command

graph.invoke(
    Command(resume={
        "action": "APPROVE",
        "reviewer": "qc-inspector-01",
        "reason": "Defect confirmed under controlled lighting.",
    }),
    config={"configurable": {"thread_id": thread_id}},
)
```

Final results are also written through `QCRepository`; FastAPI uses the SQLite
implementation and tests may use `MockQCRepository`. To move checkpoints to
PostgreSQL, install `langgraph-checkpoint-postgres`, construct `PostgresSaver`, run
its one-time `setup()`, and pass it to `build_qc_graph(checkpointer=...)`. No node
needs to change.

## Replacing mocks

- Implement the `Detector` protocol in `services/detector.py` with a YOLO or
  segmentation adapter, then inject it into `QCNodes`/`build_qc_graph`.
- Implement `Verifier` for a second camera, crop, or model pass.
- Replace `DeterministicReasoningService` only with another controlled,
  deterministic policy formatter. Detection and safety routing remain auditable.
- Implement `QCRepository` for a production database without changing graph logic.

See [`AGENT_FLOW.md`](../AGENT_FLOW.md), generated Mermaid in
[`agent_flow.mmd`](../agent_flow.mmd), and the API at `/docs`.

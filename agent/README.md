# Visual QC Agent

Contains the deterministic `MockQCAgent` orchestration for the demo workflow. It runs persisted mock YOLO detections through classify and decide, then either completes or waits for HITL. LangGraph is intentionally deferred until this REST contract is stable.

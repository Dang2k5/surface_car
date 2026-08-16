from agent.graph.builder import build_qc_graph, export_graph_mermaid

if __name__ == "__main__":
    export_graph_mermaid(build_qc_graph(), "agent_flow.mmd")

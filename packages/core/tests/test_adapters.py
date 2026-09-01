import networkx as nx
from streamlit_graph_canvas import from_networkx


def test_networkx_adapter_preserves_multigraph_keys_and_ports() -> None:
    source = nx.MultiDiGraph()
    source.add_node("a", node_type="service", name="API")
    source.add_node("b", node_type="service", name="Worker")
    source.add_edge("a", "b", key="queue", edge_type="calls", source_port="out")
    converted = from_networkx(source)
    assert converted.nodes[0].label == "API"
    assert converted.edges[0].id == "queue"
    assert converted.edges[0].source_port == "out"


def test_networkx_adapter_preserves_unused_fallback_attributes() -> None:
    source = nx.MultiDiGraph()
    source.add_node(
        "a",
        type="service",
        node_type="legacy-service",
        label="API",
        name="legacy-name",
    )
    source.add_node("b", type="service", label="Worker")
    source.add_edge("a", "b", key="calls", type="request", edge_type="legacy-request")

    converted = from_networkx(source)

    assert converted.nodes[0].type == "service"
    assert converted.nodes[0].label == "API"
    assert converted.nodes[0].data == {
        "node_type": "legacy-service",
        "name": "legacy-name",
    }
    assert converted.edges[0].type == "request"
    assert converted.edges[0].data == {"edge_type": "legacy-request"}

from typing import Set, Tuple

from shared.models import GraphSnapshot


def bfs_subgraph(
    snapshot: GraphSnapshot,
    start: str,
    direction: str,
    depth: int,
) -> Tuple[Set[str], Set[str]]:
    nodes = snapshot.nodes
    edges = snapshot.edges
    out_adj = snapshot.out_adj
    in_adj = snapshot.in_adj

    if start not in nodes:
        return set(), set()

    visited_nodes = {start}
    visited_edges: Set[str] = set()
    frontier = {start}

    def step(current: Set[str]) -> Set[str]:
        next_frontier: Set[str] = set()
        for node_id in current:
            if direction in {"down", "both"}:
                for edge_id in out_adj.get(node_id, set()):
                    visited_edges.add(edge_id)
                    target = edges[edge_id]["target"]
                    if target not in visited_nodes:
                        visited_nodes.add(target)
                        next_frontier.add(target)
            if direction in {"up", "both"}:
                for edge_id in in_adj.get(node_id, set()):
                    visited_edges.add(edge_id)
                    source = edges[edge_id]["source"]
                    if source not in visited_nodes:
                        visited_nodes.add(source)
                        next_frontier.add(source)
        return next_frontier

    if depth < 0:
        while frontier:
            frontier = step(frontier)
    else:
        for _ in range(max(depth, 0)):
            frontier = step(frontier)
            if not frontier:
                break

    return visited_nodes, visited_edges

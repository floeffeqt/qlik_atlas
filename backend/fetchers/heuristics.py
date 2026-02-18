from typing import List

from shared.models import GraphSnapshot


def never_referenced(snapshot: GraphSnapshot) -> List[str]:
    nodes = snapshot.nodes
    in_adj = snapshot.in_adj
    out_adj = snapshot.out_adj

    ids = []
    for node_id in nodes:
        degree = len(in_adj.get(node_id, set())) + len(out_adj.get(node_id, set()))
        if degree == 0:
            ids.append(node_id)
    return ids


def dead_ends(snapshot: GraphSnapshot) -> List[str]:
    nodes = snapshot.nodes
    edges = snapshot.edges
    in_adj = snapshot.in_adj
    out_adj = snapshot.out_adj

    ids = []
    for node_id in nodes:
        has_incoming_load = any(edges[eid]["relation"] == "LOAD" for eid in in_adj.get(node_id, set()))
        has_outgoing_store = any(edges[eid]["relation"] == "STORE" for eid in out_adj.get(node_id, set()))
        if has_incoming_load and not has_outgoing_store:
            ids.append(node_id)
    return ids


def orphan_outputs(
    snapshot: GraphSnapshot,
    depth: int = 3,
) -> List[str]:
    nodes = snapshot.nodes
    edges = snapshot.edges
    in_adj = snapshot.in_adj
    out_adj = snapshot.out_adj

    ids = []
    for node_id in nodes:
        has_incoming_store = any(edges[eid]["relation"] == "STORE" for eid in in_adj.get(node_id, set()))
        if not has_incoming_store:
            continue
        if len(out_adj.get(node_id, set())) == 0:
            ids.append(node_id)
            continue
        if not _has_downstream_load_depends(node_id, snapshot, depth):
            ids.append(node_id)
    return ids


def _has_downstream_load_depends(start: str, snapshot: GraphSnapshot, depth: int) -> bool:
    edges = snapshot.edges
    out_adj = snapshot.out_adj
    frontier = {start}
    visited = {start}

    for _ in range(max(depth, 0)):
        next_frontier = set()
        for node_id in frontier:
            for edge_id in out_adj.get(node_id, set()):
                relation = edges[edge_id]["relation"]
                if relation in {"LOAD", "DEPENDS"}:
                    return True
                target = edges[edge_id]["target"]
                if target not in visited:
                    visited.add(target)
                    next_frontier.add(target)
        frontier = next_frontier
        if not frontier:
            break

    return False

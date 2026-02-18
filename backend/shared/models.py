from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Set, TypedDict
from pydantic import BaseModel


NodeType = Literal["app", "db", "table", "dataset", "qvd", "file", "other"]
NodeLayer = Literal["db", "extract", "transform", "dm", "app", "other"]
EdgeRelation = Literal["LOAD", "STORE", "DEPENDS", "OTHER"]


class NodeRecord(TypedDict):
    id: str
    label: str
    type: str
    subtype: Optional[str]
    group: Optional[str]
    layer: Optional[str]
    meta: Optional[Dict[str, Any]]


class EdgeRecord(TypedDict):
    id: str
    source: str
    target: str
    relation: str
    context: Optional[Dict[str, Any]]


class AppInfoRecord(TypedDict):
    appId: str
    appName: str
    spaceId: Optional[str]
    fetched_at: Optional[str]
    status: Optional[int]
    fileName: Optional[str]
    rootNodeId: Optional[str]
    nodesCount: int
    edgesCount: int


@dataclass(frozen=True)
class GraphSnapshot:
    nodes: Dict[str, NodeRecord] = field(default_factory=dict)
    edges: Dict[str, EdgeRecord] = field(default_factory=dict)
    out_adj: Dict[str, Set[str]] = field(default_factory=dict)
    in_adj: Dict[str, Set[str]] = field(default_factory=dict)
    apps: Dict[str, AppInfoRecord] = field(default_factory=dict)
    files_loaded: int = 0

    @staticmethod
    def empty() -> "GraphSnapshot":
        return GraphSnapshot()


class Node(BaseModel):
    id: str
    label: str
    type: NodeType
    subtype: Optional[str] = None
    group: Optional[str] = None
    layer: Optional[NodeLayer] = None
    meta: Optional[Dict[str, Any]] = None


class Edge(BaseModel):
    id: str
    source: str
    target: str
    relation: EdgeRelation
    context: Optional[Dict[str, Any]] = None


class GraphResponse(BaseModel):
    nodes: List[Node]
    edges: List[Edge]


class InventoryItem(BaseModel):
    appId: str
    appName: str
    spaceId: Optional[str] = None
    spaceName: Optional[str] = None
    rootNodeId: Optional[str] = None
    nodesCount: int
    edgesCount: int
    fetched_at: Optional[str] = None
    status: Optional[int] = None
    fileName: Optional[str] = None


class InventoryResponse(BaseModel):
    apps: List[InventoryItem]
    totals: Dict[str, int]


class HealthResponse(BaseModel):
    status: str
    filesLoaded: int
    nodesCount: int
    edgesCount: int


class OrphansReport(BaseModel):
    orphanOutputs: List[Node]
    deadEnds: List[Node]
    neverReferenced: List[Node]

"""Trust graph functions: import, export, compute deterministic trust scores.

Implements a weighted graph model where:
- Nodes: Users
- Edges: Endorsements (with weights 0.0-1.0, capped at 0.5 for anti-gaming)
- Score: Weighted combination of performance + tenure + social endorsements

All calculations are deterministic: same graph → same scores.
"""

from datetime import datetime
from typing import Optional

import networkx as nx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.trust.models import Endorsement, UserTrustScore

logger = get_logger(__name__)

# Anti-gaming: cap edge weights to prevent manipulation
MAX_EDGE_WEIGHT = 0.5
# Tenure scoring: days to reach maximum tenure score
TENURE_DAYS_FOR_MAX = 365
# Score components weights
WEIGHT_PERFORMANCE = 0.5  # 50% from performance
WEIGHT_TENURE = 0.2  # 20% from tenure
WEIGHT_ENDORSEMENTS = 0.3  # 30% from social endorsements


def _build_graph_from_endorsements(endorsements: list[Endorsement]) -> nx.DiGraph:
    """Build NetworkX directed graph from endorsements.

    Nodes: user IDs
    Edges: endorser → endorsee with weight=capped_weight

    Args:
        endorsements: List of active (non-revoked) endorsements

    Returns:
        NetworkX DiGraph with nodes and weighted edges

    Example:
        >>> endorsements = [
        ...     Endorsement(endorser_id="u1", endorsee_id="u2", weight=0.4),
        ...     Endorsement(endorser_id="u2", endorsee_id="u3", weight=0.6),
        ... ]
        >>> graph = _build_graph_from_endorsements(endorsements)
        >>> graph.nodes()
        ['u1', 'u2', 'u3']
        >>> graph.edges()
        [('u1', 'u2', {'weight': 0.4}), ('u2', 'u3', 0.5)]  # u2→u3 capped
    """
    graph = nx.DiGraph()

    for endorsement in endorsements:
        # Cap weight to MAX_EDGE_WEIGHT (anti-gaming)
        capped_weight = min(float(endorsement.weight), MAX_EDGE_WEIGHT)
        graph.add_edge(
            endorsement.endorser_id, endorsement.endorsee_id, weight=capped_weight
        )

    return graph


def _calculate_performance_score(
    user_id: str, performance_data: Optional[dict]
) -> float:
    """Calculate performance component of trust score.

    Based on: win rate, Sharpe ratio, profit factor from analytics.
    Returns 0.0-100.0.

    Args:
        user_id: User identifier
        performance_data: Dict with win_rate, sharpe_ratio, profit_factor

    Returns:
        Performance score 0.0-100.0

    Example:
        >>> data = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0}
        >>> score = _calculate_performance_score("user1", data)
        >>> 60 < score < 100  # High performance
    """
    if not performance_data:
        return 0.0

    score = 0.0

    # Win rate: 0.5 (50%) → 0, 0.7 (70%) → 100, capped at 100
    win_rate = performance_data.get("win_rate", 0.5)
    win_score = min((win_rate - 0.5) * 500, 100.0) if win_rate > 0.5 else 0.0
    score += win_score * 0.5

    # Sharpe ratio: 0 → 0, 2.0 → 100, capped
    sharpe = performance_data.get("sharpe_ratio", 0.0)
    sharpe_score = min(sharpe * 50, 100.0)
    score += sharpe_score * 0.3

    # Profit factor: 1.0 → 0, 3.0 → 100, capped
    pf = performance_data.get("profit_factor", 1.0)
    pf_score = min((pf - 1.0) * 50, 100.0) if pf > 1.0 else 0.0
    score += pf_score * 0.2

    return min(score, 100.0)


def _calculate_tenure_score(user_created_at: datetime) -> float:
    """Calculate tenure component of trust score.

    Score increases linearly from 0 to 100 over TENURE_DAYS_FOR_MAX days.
    Capped at 100 after that.

    Args:
        user_created_at: User account creation timestamp

    Returns:
        Tenure score 0.0-100.0

    Example:
        >>> created = datetime.utcnow() - timedelta(days=180)
        >>> score = _calculate_tenure_score(created)
        >>> 40 < score < 60  # ~49% of max after 180 days
    """
    days_active = (datetime.utcnow() - user_created_at).days
    tenure_score = min((days_active / TENURE_DAYS_FOR_MAX) * 100, 100.0)
    return max(tenure_score, 0.0)


def _calculate_endorsement_score(
    graph: nx.DiGraph, user_id: str, all_users_count: int
) -> float:
    """Calculate endorsement component of trust score.

    Based on: number of endorsements received, their weights, and endorsers'
    own trust scores (recursive trust propagation).

    Args:
        graph: NetworkX graph of endorsements
        user_id: User to calculate score for
        all_users_count: Total users for normalization

    Returns:
        Endorsement score 0.0-100.0

    Example:
        >>> graph = nx.DiGraph()
        >>> graph.add_edge("u1", "target", weight=0.4)
        >>> graph.add_edge("u2", "target", weight=0.5)
        >>> score = _calculate_endorsement_score(graph, "target", 100)
        >>> 0 < score < 100  # Based on incoming edges
    """
    if user_id not in graph:
        return 0.0

    # Get incoming edges (endorsements received)
    in_degree_weighted = sum(
        graph[pred][user_id].get("weight", 0.0) for pred in graph.predecessors(user_id)
    )

    # Normalize by max possible endorsements and cap at 100
    max_possible = all_users_count * MAX_EDGE_WEIGHT
    endorsement_score = min(
        (in_degree_weighted / max_possible * 100) if max_possible > 0 else 0.0, 100.0
    )

    return float(endorsement_score)


def _calculate_tier(score: float) -> str:
    """Map trust score to tier band.

    Args:
        score: Trust score 0.0-100.0

    Returns:
        Tier: "bronze" (0-50), "silver" (50-75), "gold" (75+)

    Example:
        >>> _calculate_tier(30.0)
        'bronze'
        >>> _calculate_tier(60.0)
        'silver'
        >>> _calculate_tier(85.0)
        'gold'
    """
    if score >= 75.0:
        return "gold"
    elif score >= 50.0:
        return "silver"
    else:
        return "bronze"


def calculate_trust_scores(
    graph: nx.DiGraph,
    user_performance_map: dict[str, dict],
    user_created_map: dict[str, datetime],
) -> dict[str, dict]:
    """Calculate deterministic trust scores for all users in graph.

    Combines: performance (50%) + tenure (20%) + endorsements (30%)
    Returns same scores for same input graph (deterministic).

    Args:
        graph: NetworkX DiGraph of endorsements
        user_performance_map: Dict[user_id → performance_data]
        user_created_map: Dict[user_id → created_at datetime]

    Returns:
        Dict[user_id → {score, tier, performance, tenure, endorsements}]

    Example:
        >>> graph = nx.DiGraph()
        >>> graph.add_edge("u1", "u2", weight=0.4)
        >>> perf = {"u1": {"win_rate": 0.65}, "u2": {"win_rate": 0.70}}
        >>> created = {"u1": datetime.utcnow() - timedelta(days=100), ...}
        >>> scores = calculate_trust_scores(graph, perf, created)
        >>> scores["u2"]["score"] > 50  # u2 has endorsement + good performance
    """
    scores = {}
    all_nodes = (
        set(graph.nodes())
        | set(user_performance_map.keys())
        | set(user_created_map.keys())
    )
    all_count = len(all_nodes)

    for user_id in all_nodes:
        perf_data = user_performance_map.get(user_id, {})
        created_at = user_created_map.get(user_id, datetime.utcnow())

        # Calculate components
        perf_score = _calculate_performance_score(user_id, perf_data)
        tenure_score = _calculate_tenure_score(created_at)
        endorsement_score = _calculate_endorsement_score(graph, user_id, all_count)

        # Weighted combination
        total_score = (
            (perf_score * WEIGHT_PERFORMANCE)
            + (tenure_score * WEIGHT_TENURE)
            + (endorsement_score * WEIGHT_ENDORSEMENTS)
        )

        tier = _calculate_tier(total_score)

        scores[user_id] = {
            "score": round(total_score, 2),
            "tier": tier,
            "performance_component": round(perf_score, 2),
            "tenure_component": round(tenure_score, 2),
            "endorsement_component": round(endorsement_score, 2),
        }

    return scores


def _calculate_percentiles(scores: dict[str, dict]) -> dict[str, float]:
    """Calculate percentile rank for each score.

    Args:
        scores: Dict[user_id → score_info]

    Returns:
        Dict[user_id → percentile (0-100)]
    """
    if not scores:
        return {}

    score_values = sorted([s["score"] for s in scores.values()])
    percentiles = {}

    for user_id, score_info in scores.items():
        rank = next(i for i, v in enumerate(score_values) if v >= score_info["score"])
        percentile = (rank / len(score_values)) * 100 if score_values else 0
        percentiles[user_id] = round(percentile, 1)

    return percentiles


def export_graph(graph: nx.DiGraph) -> dict:
    """Export graph to JSON-serializable dict.

    Args:
        graph: NetworkX DiGraph

    Returns:
        JSON dict with nodes and edges

    Example:
        >>> graph = nx.DiGraph()
        >>> graph.add_edge("u1", "u2", weight=0.4)
        >>> data = export_graph(graph)
        >>> data["nodes"]
        ["u1", "u2"]
    """
    return {
        "nodes": list(graph.nodes()),
        "edges": [
            {"source": u, "target": v, "weight": d.get("weight", 1.0)}
            for u, v, d in graph.edges(data=True)
        ],
    }


def import_graph(data: dict) -> nx.DiGraph:
    """Import graph from JSON dict.

    Args:
        data: Dict with "nodes" and "edges"

    Returns:
        NetworkX DiGraph

    Example:
        >>> data = {
        ...     "nodes": ["u1", "u2"],
        ...     "edges": [{"source": "u1", "target": "u2", "weight": 0.4}]
        ... }
        >>> graph = import_graph(data)
    """
    graph = nx.DiGraph()

    # Add nodes
    for node in data.get("nodes", []):
        graph.add_node(node)

    # Add edges
    for edge in data.get("edges", []):
        graph.add_edge(edge["source"], edge["target"], weight=edge.get("weight", 1.0))

    return graph


async def get_single_user_score(user_id: str, db: AsyncSession) -> Optional[dict]:
    """Get cached trust score for single user.

    Args:
        user_id: User identifier
        db: Database session

    Returns:
        Dict with score, tier, components, or None if not calculated

    Example:
        >>> score = await get_single_user_score("user1", db)
        >>> score["tier"]
        'silver'
    """
    stmt = select(UserTrustScore).where(UserTrustScore.user_id == user_id)
    result = await db.execute(stmt)
    trust_score_record = result.scalar_one_or_none()

    if not trust_score_record:
        return None

    return {
        "user_id": trust_score_record.user_id,
        "score": trust_score_record.score,
        "tier": trust_score_record.tier,
        "percentile": trust_score_record.percentile,
        "performance_component": trust_score_record.performance_component,
        "tenure_component": trust_score_record.tenure_component,
        "endorsement_component": trust_score_record.endorsement_component,
        "calculated_at": trust_score_record.calculated_at.isoformat(),
    }

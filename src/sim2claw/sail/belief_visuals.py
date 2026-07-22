"""Read-only deterministic renderers for SAIL belief-graph revisions."""

from __future__ import annotations

import html
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..learning_factory_artifacts import atomic_write_json, sha256_file


TYPE_COLORS = {
    "workcell": "#1d4ed8",
    "session": "#2563eb",
    "context": "#0ea5e9",
    "evidence": "#0891b2",
    "dataset": "#0f766e",
    "residual_channel": "#059669",
    "mechanism": "#65a30d",
    "parameter_posterior": "#ca8a04",
    "intervention": "#d97706",
    "candidate": "#ea580c",
    "simulator_version": "#dc2626",
    "evaluator_verdict": "#be123c",
    "counterexample": "#9333ea",
    "twin_worthiness_certificate": "#7c3aed",
    "checkpoint": "#64748b",
    "policy": "#475569",
}


def _render_svg(graph: Mapping[str, Any], *, title: str) -> str:
    nodes = list(graph["nodes"])
    edges = list(graph["edges"])
    by_type: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for node in nodes:
        by_type[str(node["type"])].append(node)
    ordered_types = [kind for kind in graph["node_types"] if by_type.get(kind)]
    positions: dict[str, tuple[int, int]] = {}
    column_width = 235
    row_height = 62
    for column, kind in enumerate(ordered_types):
        for row, node in enumerate(sorted(by_type[kind], key=lambda item: str(item["id"]))):
            positions[str(node["id"])] = (35 + column * column_width, 105 + row * row_height)
    max_rows = max((len(rows) for rows in by_type.values()), default=1)
    width = max(920, 70 + len(ordered_types) * column_width)
    height = max(360, 155 + max_rows * row_height)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="28" y="38" font-family="system-ui" font-size="22" font-weight="700" fill="#0f172a">{html.escape(title)}</text>',
        f'<text x="28" y="64" font-family="ui-monospace" font-size="11" fill="#475569">graph {html.escape(str(graph["graph_digest"])[:16])} · {len(nodes)} nodes · {len(edges)} edges</text>',
        '<defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 Z" fill="#94a3b8"/></marker></defs>',
    ]
    for edge in edges:
        start = positions.get(str(edge["source"]))
        end = positions.get(str(edge["target"]))
        if not start or not end:
            continue
        x1, y1 = start
        x2, y2 = end
        lines.append(
            f'<path d="M{x1 + 190},{y1 + 18} C{x1 + 215},{y1 + 18} {x2 - 25},{y2 + 18} {x2},{y2 + 18}" fill="none" stroke="#cbd5e1" stroke-width="1" marker-end="url(#arrow)"/>'
        )
    for kind in ordered_types:
        column_nodes = sorted(by_type[kind], key=lambda item: str(item["id"]))
        if not column_nodes:
            continue
        x, _ = positions[str(column_nodes[0]["id"])]
        lines.append(
            f'<text x="{x}" y="91" font-family="system-ui" font-size="12" font-weight="700" fill="#334155">{html.escape(kind.replace("_", " "))}</text>'
        )
        for node in column_nodes:
            x, y = positions[str(node["id"])]
            color = TYPE_COLORS.get(kind, "#334155")
            status = html.escape(str(node["status"]))
            label = html.escape(str(node["label"]))
            if len(label) > 30:
                label = label[:27] + "…"
            lines.extend(
                [
                    f'<rect x="{x}" y="{y}" width="190" height="40" rx="6" fill="white" stroke="{color}" stroke-width="1.5"/>',
                    f'<text x="{x + 8}" y="{y + 16}" font-family="system-ui" font-size="10" font-weight="650" fill="#0f172a">{label}</text>',
                    f'<text x="{x + 8}" y="{y + 31}" font-family="ui-monospace" font-size="9" fill="{color}">{status}</text>',
                ]
            )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def write_belief_visuals(
    *,
    output_root: Path,
    before_graph: Mapping[str, Any],
    after_graph: Mapping[str, Any],
    revisions: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, str]]:
    output_root.mkdir(parents=True, exist_ok=True)
    before_path = output_root / "graph_before.svg"
    after_path = output_root / "graph_after.svg"
    timeline_path = output_root / "revision_timeline.json"
    before_path.write_text(
        _render_svg(before_graph, title="SAIL belief graph — retained foundations"),
        encoding="utf-8",
    )
    after_path.write_text(
        _render_svg(after_graph, title="SAIL belief graph — chronological retained history"),
        encoding="utf-8",
    )
    atomic_write_json(timeline_path, list(revisions))
    return {
        "graph_before_svg": {"path": before_path.name, "sha256": sha256_file(before_path)},
        "graph_after_svg": {"path": after_path.name, "sha256": sha256_file(after_path)},
        "revision_timeline": {"path": timeline_path.name, "sha256": sha256_file(timeline_path)},
    }


__all__ = ["write_belief_visuals"]

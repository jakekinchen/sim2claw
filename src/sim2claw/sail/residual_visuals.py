"""Deterministic, read-only residual heatmap and drilldown artifacts."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..learning_factory_artifacts import atomic_write_json, sha256_file


def build_heatmap(
    summaries: Sequence[Mapping[str, Any]], channels: Sequence[str]
) -> dict[str, Any]:
    selected = {
        (str(row["episode_id"]), str(row["channel"])): row
        for row in summaries
        if row.get("phase") == "all" and row.get("channel") in channels
    }
    episodes = sorted({episode for episode, _ in selected})
    maxima: dict[str, float] = {}
    for channel in channels:
        values = [
            float(selected[(episode, channel)]["rmse"])
            for episode in episodes
            if (episode, channel) in selected and selected[(episode, channel)].get("rmse") is not None
        ]
        maxima[channel] = max(values) if values else 0.0
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        cells = []
        for channel in channels:
            summary = selected.get((episode, channel))
            value = None if summary is None else summary.get("rmse")
            maximum = maxima[channel]
            normalized = None if value is None else (float(value) / maximum if maximum > 0.0 else 0.0)
            cells.append(
                {
                    "channel": channel,
                    "unit": None if summary is None else summary.get("unit"),
                    "rmse": value,
                    "normalized_within_channel": normalized,
                }
            )
        rows.append({"episode_id": episode, "cells": cells})
    return {
        "schema_version": "sim2claw.sail_residual_heatmap.v1",
        "normalization": "per_channel_max_for_visual_color_only_raw_rmse_preserved",
        "channels": list(channels),
        "episodes": episodes,
        "rows": rows,
        "authority": {"metric_promotion": False, "physical_authority": False},
    }


def render_heatmap_svg(
    heatmap: Mapping[str, Any], *, cell_width: int, cell_height: int
) -> str:
    episodes = list(heatmap["episodes"])
    channels = list(heatmap["channels"])
    left = 255
    top = 185
    width = left + cell_width * len(channels) + 20
    height = top + cell_height * len(episodes) + 45
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#101418"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,monospace;fill:#e7edf2;font-size:11px}.muted{fill:#9aabb8}.title{font-size:17px;font-weight:700}</style>',
        '<text class="title" x="18" y="28">SAIL phase-aligned residual RMSE</text>',
        '<text class="muted" x="18" y="48">Color is normalized within each channel; cells retain raw RMSE in the bound JSON.</text>',
    ]
    for index, channel in enumerate(channels):
        x = left + index * cell_width + 8
        label = html.escape(channel)
        lines.append(
            f'<text class="muted" transform="translate({x},{top - 10}) rotate(-55)">{label}</text>'
        )
    for row_index, row in enumerate(heatmap["rows"]):
        y = top + row_index * cell_height
        episode = html.escape(str(row["episode_id"]))
        lines.append(f'<text x="18" y="{y + cell_height - 8}">{episode}</text>')
        for column_index, cell in enumerate(row["cells"]):
            x = left + column_index * cell_width
            normalized = cell["normalized_within_channel"]
            if normalized is None:
                fill = "#39434a"
                label = "NA"
            else:
                value = max(0.0, min(1.0, float(normalized)))
                red = int(42 + 195 * value)
                green = int(156 - 95 * value)
                blue = int(208 - 146 * value)
                fill = f"#{red:02x}{green:02x}{blue:02x}"
                label = f"{float(cell['rmse']):.4g}"
            lines.append(
                f'<rect x="{x}" y="{y}" width="{cell_width - 2}" height="{cell_height - 2}" rx="3" fill="{fill}"/>'
            )
            lines.append(
                f'<text x="{x + 7}" y="{y + cell_height - 8}" fill="#ffffff">{html.escape(label)}</text>'
            )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def write_residual_visuals(
    *,
    output_root: Path,
    summaries: Sequence[Mapping[str, Any]],
    episodes: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    settings = config["visualization"]
    heatmap = build_heatmap(summaries, settings["heatmap_channels"])
    heatmap_path = output_root / "heatmap.json"
    atomic_write_json(heatmap_path, heatmap)
    svg_path = output_root / "heatmap.svg"
    svg_path.write_text(
        render_heatmap_svg(
            heatmap,
            cell_width=int(settings["svg_cell_width"]),
            cell_height=int(settings["svg_cell_height"]),
        ),
        encoding="utf-8",
    )
    drilldown = {
        "schema_version": "sim2claw.sail_residual_episode_drilldowns.v1",
        "episodes": list(episodes),
        "authority": {"read_only": True, "physical_authority": False},
    }
    drilldown_path = output_root / "episode_drilldowns.json"
    atomic_write_json(drilldown_path, drilldown)
    return {
        "heatmap_json": {"path": "heatmap.json", "sha256": sha256_file(heatmap_path)},
        "heatmap_svg": {"path": "heatmap.svg", "sha256": sha256_file(svg_path)},
        "episode_drilldowns": {
            "path": "episode_drilldowns.json",
            "sha256": sha256_file(drilldown_path),
        },
    }

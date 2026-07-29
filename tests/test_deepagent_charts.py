import json

import pytest
from PIL import Image

from midas.deepagents import charts
from midas.deepagents.charts import (
    ChartDatum,
    ChartSeries,
    ScatterPoint,
)
from midas.deepagents.tools import MIDAS_TOOLS


@pytest.fixture
def chart_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(charts, "CHARTS_DIR", tmp_path / "charts")
    return charts.CHARTS_DIR


def _assert_png_response(response: str, output_dir) -> dict:
    payload = json.loads(response)
    assert payload["ok"] is True
    path = output_dir / payload["path"].split("/")[-1]
    assert path.exists()
    with Image.open(path) as image:
        assert image.format == "PNG"
        assert image.size == (charts.CHART_WIDTH, charts.CHART_HEIGHT)
    return payload


def test_chart_tools_are_registered() -> None:
    expected = {
        "generate_bar_chart",
        "generate_horizontal_bar_chart",
        "generate_line_chart",
        "generate_pie_chart",
        "generate_stacked_bar_chart",
        "generate_area_chart",
        "generate_scatter_chart",
        "generate_heatmap_chart",
    }
    names = {item.name for item in MIDAS_TOOLS}
    assert expected <= names


def test_bar_and_pie_tools_save_pngs(chart_output_dir) -> None:
    data = [{"label": "Revenue", "value": 100}, {"label": "Profit", "value": 25}]

    bar = charts.generate_bar_chart.invoke(
        {"title": "Company figures", "data": data, "filename": "../Company figures"}
    )
    pie = charts.generate_pie_chart.invoke({"title": "Mix", "data": data})

    bar_payload = _assert_png_response(bar, chart_output_dir)
    pie_payload = _assert_png_response(pie, chart_output_dir)
    assert bar_payload["chart_kind"] == "bar"
    assert pie_payload["chart_kind"] == "pie"
    assert bar_payload["relative_path"].startswith("file:")
    assert "independently verify" in bar_payload["data_note"]


def test_multi_series_and_matrix_tools_save_pngs(chart_output_dir) -> None:
    labels = ["Q1", "Q2", "Q3"]
    series = [
        {"name": "Revenue", "values": [10, 12, 15]},
        {"name": "Costs", "values": [6, 7, 8], "color": "#D64545"},
    ]
    calls = [
        (charts.generate_line_chart, {"title": "Line", "labels": labels, "series": series}),
        (charts.generate_area_chart, {"title": "Area", "labels": labels, "series": series}),
        (
            charts.generate_stacked_bar_chart,
            {"title": "Stacked", "labels": labels, "series": series},
        ),
        (
            charts.generate_scatter_chart,
            {
                "title": "Scatter",
                "points": [
                    {"x": 1, "y": 2, "label": "A"},
                    {"x": 2, "y": 4, "label": "B"},
                ],
            },
        ),
        (
            charts.generate_heatmap_chart,
            {
                "title": "Heatmap",
                "rows": ["Revenue", "Costs"],
                "columns": ["Q1", "Q2"],
                "cells": [
                    {"row": "Revenue", "column": "Q1", "value": 10},
                    {"row": "Revenue", "column": "Q2", "value": 12},
                    {"row": "Costs", "column": "Q1", "value": 6},
                ],
            },
        ),
    ]
    for chart_tool, arguments in calls:
        _assert_png_response(chart_tool.invoke(arguments), chart_output_dir)


def test_horizontal_bar_and_chart_models_validate(chart_output_dir) -> None:
    response = charts.generate_horizontal_bar_chart.invoke(
        {
            "title": "Long labels",
            "data": [
                {"label": "A very long category label", "value": -10},
                {"label": "Another category", "value": 20},
            ],
        }
    )
    _assert_png_response(response, chart_output_dir)

    with pytest.raises(ValueError, match="finite"):
        ChartDatum(label="bad", value=float("inf"))
    with pytest.raises(ValueError, match="six-digit"):
        ChartSeries(name="bad", values=[1], color="red")
    with pytest.raises(ValueError, match="finite"):
        ScatterPoint(x=1, y=float("nan"))


def test_chart_tools_return_structured_errors(chart_output_dir) -> None:
    negative_pie = charts.generate_pie_chart.invoke(
        {"title": "Invalid", "data": [{"label": "Bad", "value": -1}]}
    )
    assert json.loads(negative_pie)["ok"] is False

    duplicate_heatmap = charts.generate_heatmap_chart.invoke(
        {
            "title": "Invalid matrix",
            "rows": ["A"],
            "columns": ["B"],
            "cells": [
                {"row": "A", "column": "B", "value": 1},
                {"row": "A", "column": "B", "value": 2},
            ],
        }
    )
    assert "duplicate heatmap cell" in json.loads(duplicate_heatmap)["error"]

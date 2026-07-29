"""Static research chart PNG tools for the Midas DeepAgent."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
from io import BytesIO
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, field_validator

CHART_WIDTH = 1200
CHART_HEIGHT = 750
TITLE_HEIGHT = 56
FOOTER_HEIGHT = 36
MARGIN_LEFT = 90
MARGIN_RIGHT = 36
MARGIN_TOP = TITLE_HEIGHT + 24
MARGIN_BOTTOM = FOOTER_HEIGHT + 56
LEGEND_HEIGHT = 40
MAX_CATEGORIES = 40
MAX_SERIES = 8
MAX_SERIES_POINTS = 40
MAX_SCATTER_POINTS = MAX_CATEGORIES * 2
MAX_HEATMAP_CELLS = MAX_CATEGORIES * MAX_CATEGORIES

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_PALETTE = (
    "#2867B2",
    "#D64545",
    "#14866D",
    "#E07A1F",
    "#8A4FB5",
    "#3C7A3E",
    "#C45C8A",
    "#5C7A9A",
)
_CHARTS_RELATIVE_DIR = Path("output/charts")
CHARTS_DIR = Path(os.environ.get("MIDAS_CHARTS_DIR", _CHARTS_RELATIVE_DIR))
ai_log = logging.getLogger(__name__)
_SAVE_LOCK = threading.Lock()


class ChartSeries(BaseModel):
    """One named data series for a line, area, or stacked bar chart."""

    name: str = Field(min_length=1, max_length=80)
    values: list[float] = Field(min_length=1, max_length=MAX_SERIES_POINTS)
    color: str | None = None

    @field_validator("color")
    @classmethod
    def valid_color(cls, value: str | None) -> str | None:
        if value is not None and not _HEX_COLOR_RE.fullmatch(value):
            raise ValueError("color must be a six-digit hex value such as #2867B2")
        return value

    @field_validator("values")
    @classmethod
    def finite_values(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(item) for item in values):
            raise ValueError("series values must be finite numbers")
        return values


class ChartDatum(BaseModel):
    """One labelled value for a single-series bar or pie chart."""

    label: str = Field(min_length=1, max_length=80)
    value: float
    color: str | None = None

    @field_validator("color")
    @classmethod
    def valid_color(cls, value: str | None) -> str | None:
        if value is not None and not _HEX_COLOR_RE.fullmatch(value):
            raise ValueError("color must be a six-digit hex value such as #2867B2")
        return value

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be a finite number")
        return value


class ScatterPoint(BaseModel):
    """One labelled (x, y) observation for a scatter chart."""

    x: float
    y: float
    label: str | None = Field(default=None, max_length=40)
    color: str | None = None

    @field_validator("color")
    @classmethod
    def valid_color(cls, value: str | None) -> str | None:
        if value is not None and not _HEX_COLOR_RE.fullmatch(value):
            raise ValueError("color must be a six-digit hex value such as #2867B2")
        return value

    @field_validator("x", "y")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("scatter coordinates must be finite numbers")
        return value


class HeatmapCell(BaseModel):
    """One numeric cell in a heatmap grid."""

    row: str = Field(min_length=1, max_length=40)
    column: str = Field(min_length=1, max_length=40)
    value: float

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("heatmap values must be finite numbers")
        return value


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    names = ("DejaVuSans-Bold.ttf", "Arial Bold.ttf") if bold else ("DejaVuSans.ttf", "Arial.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[index : index + 2], 16) for index in (1, 3, 5))


def _format_number(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 10_000:
        return f"{value / 1_000:.1f}k"
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    if abs(value) >= 100:
        return f"{value:.1f}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _nice_ticks(minimum: float, maximum: float, count: int = 5) -> list[float]:
    if not math.isfinite(minimum) or not math.isfinite(maximum):
        raise ValueError("axis bounds must be finite")
    if maximum < minimum:
        minimum, maximum = maximum, minimum
    if math.isclose(minimum, maximum):
        if minimum == 0:
            return [0.0, 1.0]
        pad = abs(minimum) * 0.1 or 1.0
        minimum -= pad
        maximum += pad
    span = maximum - minimum
    raw_step = span / max(count - 1, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step > 0 else 1.0
    residual = raw_step / magnitude
    if residual <= 1:
        step = magnitude
    elif residual <= 2:
        step = 2 * magnitude
    elif residual <= 5:
        step = 5 * magnitude
    else:
        step = 10 * magnitude
    start = math.floor(minimum / step) * step
    end = math.ceil(maximum / step) * step
    ticks: list[float] = []
    value = start
    for _ in range(count * 4):
        ticks.append(round(value, 10))
        if value >= end - step * 1e-9:
            break
        value += step
    return ticks or [minimum, maximum]


def _draw_header_footer(draw: ImageDraw.ImageDraw, title: str) -> None:
    draw.rectangle((0, 0, CHART_WIDTH, TITLE_HEIGHT), fill=(20, 42, 67))
    draw.text((22, 16), title, font=_font(22, bold=True), fill=(255, 255, 255))
    draw.rectangle(
        (0, CHART_HEIGHT - FOOTER_HEIGHT, CHART_WIDTH, CHART_HEIGHT),
        fill=(245, 247, 250),
    )
    draw.text(
        (12, CHART_HEIGHT - FOOTER_HEIGHT + 10),
        "Chart generated from research figures",
        font=_font(12),
        fill=(53, 66, 79),
    )


def _draw_axis_frame(
    draw: ImageDraw.ImageDraw,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> None:
    draw.rectangle((left, top, right, bottom), outline=(180, 190, 200), width=1)
    draw.line((left, bottom, right, bottom), fill=(90, 104, 120), width=2)
    draw.line((left, top, left, bottom), fill=(90, 104, 120), width=2)


def _draw_y_axis(
    draw: ImageDraw.ImageDraw,
    left: int,
    top: int,
    right: int,
    bottom: int,
    ticks: list[float],
    y_min: float,
    y_max: float,
    y_label: str | None,
) -> None:
    font = _font(13)
    span = y_max - y_min or 1.0
    plot_height = bottom - top
    for tick in ticks:
        ratio = (tick - y_min) / span
        y = bottom - ratio * plot_height
        draw.line((left, y, right, y), fill=(230, 234, 239), width=1)
        label = _format_number(tick)
        box = draw.textbbox((0, 0), label, font=font)
        draw.text(
            (left - (box[2] - box[0]) - 10, y - (box[3] - box[1]) / 2),
            label,
            font=font,
            fill=(70, 84, 98),
        )
    if y_label:
        draw.text((14, top - 4), y_label[:28], font=_font(14, bold=True), fill=(53, 66, 79))


def _draw_x_labels(
    draw: ImageDraw.ImageDraw,
    centers: list[float],
    labels: list[str],
    bottom: int,
    x_label: str | None,
) -> None:
    font = _font(13)
    for center, label in zip(centers, labels, strict=True):
        text = label if len(label) <= 14 else f"{label[:12]}…"
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (center - (box[2] - box[0]) / 2, bottom + 10),
            text,
            font=font,
            fill=(53, 66, 79),
        )
    if x_label:
        label_font = _font(14, bold=True)
        box = draw.textbbox((0, 0), x_label, font=label_font)
        draw.text(
            (
                (CHART_WIDTH - (box[2] - box[0])) / 2,
                CHART_HEIGHT - FOOTER_HEIGHT - 22,
            ),
            x_label,
            font=label_font,
            fill=(53, 66, 79),
        )


def _draw_legend(
    draw: ImageDraw.ImageDraw,
    items: list[tuple[str, str]],
    top: int,
) -> None:
    if not items:
        return
    font = _font(13)
    x = MARGIN_LEFT
    for name, color in items:
        draw.rounded_rectangle((x, top, x + 14, top + 14), radius=3, fill=_rgb(color))
        text = name[:24]
        draw.text((x + 20, top - 1), text, font=font, fill=(40, 52, 64))
        box = draw.textbbox((0, 0), text, font=font)
        x += 34 + (box[2] - box[0])
        if x > CHART_WIDTH - 120:
            break


def _plot_bounds(*, legend: bool = False) -> tuple[int, int, int, int]:
    return (
        MARGIN_LEFT,
        MARGIN_TOP + (LEGEND_HEIGHT if legend else 0),
        CHART_WIDTH - MARGIN_RIGHT,
        CHART_HEIGHT - MARGIN_BOTTOM,
    )


def _validate_single_series(data: list[ChartDatum]) -> list[ChartDatum]:
    if not data:
        raise ValueError("at least one data point is required")
    if len(data) > MAX_CATEGORIES:
        raise ValueError(f"at most {MAX_CATEGORIES} categories are supported")
    return data


def _validate_multi_series(
    labels: list[str],
    series: list[ChartSeries],
) -> tuple[list[str], list[ChartSeries]]:
    if not labels:
        raise ValueError("at least one category label is required")
    if len(labels) > MAX_CATEGORIES:
        raise ValueError(f"at most {MAX_CATEGORIES} categories are supported")
    if not series:
        raise ValueError("at least one series is required")
    if len(series) > MAX_SERIES:
        raise ValueError(f"at most {MAX_SERIES} series are supported")
    if any(not label.strip() for label in labels):
        raise ValueError("category labels must not be blank")
    for item in series:
        if len(item.values) != len(labels):
            raise ValueError(
                f"series '{item.name}' has {len(item.values)} values but "
                f"{len(labels)} category labels were provided"
            )
    return labels, series


def _new_canvas(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    canvas = Image.new("RGB", (CHART_WIDTH, CHART_HEIGHT), "#FFFFFF")
    draw = ImageDraw.Draw(canvas)
    _draw_header_footer(draw, title)
    return canvas, draw


def _png_bytes(canvas: Image.Image) -> bytes:
    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _render_bar_chart_png(
    title: str,
    data: list[ChartDatum],
    *,
    horizontal: bool = False,
    x_label: str | None = None,
    y_label: str | None = None,
) -> bytes:
    data = _validate_single_series(data)
    canvas, draw = _new_canvas(title)
    values = [item.value for item in data]
    ticks = _nice_ticks(min(0.0, min(values)), max(0.0, max(values)))
    y_min, y_max = ticks[0], ticks[-1]
    left, top, right, bottom = _plot_bounds()

    if horizontal:
        x_min, x_max = y_min, y_max
        span = x_max - x_min or 1.0
        plot_width = right - left
        plot_height = bottom - top
        row_height = plot_height / max(len(data), 1)
        bar_height = row_height * 0.62
        zero_x = left + ((0 - x_min) / span) * plot_width
        _draw_axis_frame(draw, left, top, right, bottom)
        for tick in ticks:
            x = left + ((tick - x_min) / span) * plot_width
            draw.line((x, top, x, bottom), fill=(230, 234, 239), width=1)
            label = _format_number(tick)
            box = draw.textbbox((0, 0), label, font=_font(12))
            draw.text(
                (x - (box[2] - box[0]) / 2, bottom + 8),
                label,
                font=_font(12),
                fill=(70, 84, 98),
            )
        for index, item in enumerate(data):
            color = item.color or _PALETTE[index % len(_PALETTE)]
            center_y = top + (index + 0.5) * row_height
            value_x = left + ((item.value - x_min) / span) * plot_width
            bar_left, bar_right = min(zero_x, value_x), max(zero_x, value_x)
            draw.rounded_rectangle(
                (bar_left, center_y - bar_height / 2, bar_right, center_y + bar_height / 2),
                radius=4,
                fill=_rgb(color),
            )
            text = item.label if len(item.label) <= 16 else f"{item.label[:14]}…"
            box = draw.textbbox((0, 0), text, font=_font(13))
            draw.text(
                (left - (box[2] - box[0]) - 10, center_y - (box[3] - box[1]) / 2),
                text,
                font=_font(13),
                fill=(53, 66, 79),
            )
        if x_label:
            box = draw.textbbox((0, 0), x_label, font=_font(14, bold=True))
            draw.text(
                (
                    (CHART_WIDTH - (box[2] - box[0])) / 2,
                    CHART_HEIGHT - FOOTER_HEIGHT - 22,
                ),
                x_label,
                font=_font(14, bold=True),
                fill=(53, 66, 79),
            )
        if y_label:
            draw.text((14, top - 4), y_label[:28], font=_font(14, bold=True), fill=(53, 66, 79))
    else:
        span = y_max - y_min or 1.0
        plot_width = right - left
        plot_height = bottom - top
        slot = plot_width / max(len(data), 1)
        bar_width = slot * 0.62
        zero_y = bottom - ((0 - y_min) / span) * plot_height
        _draw_axis_frame(draw, left, top, right, bottom)
        _draw_y_axis(draw, left, top, right, bottom, ticks, y_min, y_max, y_label)
        centers: list[float] = []
        for index, item in enumerate(data):
            color = item.color or _PALETTE[index % len(_PALETTE)]
            center_x = left + (index + 0.5) * slot
            centers.append(center_x)
            value_y = bottom - ((item.value - y_min) / span) * plot_height
            draw.rounded_rectangle(
                (
                    center_x - bar_width / 2,
                    min(zero_y, value_y),
                    center_x + bar_width / 2,
                    max(zero_y, value_y),
                ),
                radius=4,
                fill=_rgb(color),
            )
        _draw_x_labels(draw, centers, [item.label for item in data], bottom, x_label)
    return _png_bytes(canvas)


def _series_points(
    values: list[float],
    xs: list[float],
    *,
    bottom: int,
    y_min: float,
    y_max: float,
    plot_height: int,
) -> list[tuple[float, float]]:
    span = y_max - y_min or 1.0
    return [
        (x, bottom - ((value - y_min) / span) * plot_height)
        for x, value in zip(xs, values, strict=True)
    ]


def _render_line_chart_png(
    title: str,
    labels: list[str],
    series: list[ChartSeries],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
) -> bytes:
    labels, series = _validate_multi_series(labels, series)
    canvas, draw = _new_canvas(title)
    all_values = [value for item in series for value in item.values]
    ticks = _nice_ticks(min(0.0, min(all_values)), max(0.0, max(all_values)))
    y_min, y_max = ticks[0], ticks[-1]
    left, top, right, bottom = _plot_bounds(legend=len(series) > 1)
    plot_width, plot_height = right - left, bottom - top
    _draw_axis_frame(draw, left, top, right, bottom)
    _draw_y_axis(draw, left, top, right, bottom, ticks, y_min, y_max, y_label)
    xs = (
        [left + plot_width / 2]
        if len(labels) == 1
        else [left + index / (len(labels) - 1) * plot_width for index in range(len(labels))]
    )
    legend_items: list[tuple[str, str]] = []
    for series_index, item in enumerate(series):
        color = item.color or _PALETTE[series_index % len(_PALETTE)]
        legend_items.append((item.name, color))
        points = _series_points(
            item.values,
            xs,
            bottom=bottom,
            y_min=y_min,
            y_max=y_max,
            plot_height=plot_height,
        )
        if len(points) >= 2:
            draw.line(points, fill=_rgb(color), width=3)
        for x, y in points:
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=_rgb(color), outline="white", width=2)
    _draw_x_labels(draw, xs, labels, bottom, x_label)
    if len(series) > 1:
        _draw_legend(draw, legend_items, TITLE_HEIGHT + 10)
    return _png_bytes(canvas)


def _render_pie_chart_png(title: str, data: list[ChartDatum]) -> bytes:
    data = _validate_single_series(data)
    if any(item.value < 0 for item in data):
        raise ValueError("pie chart values must be non-negative")
    total = sum(item.value for item in data)
    if total <= 0:
        raise ValueError("pie chart requires a positive total")

    canvas, draw = _new_canvas(title)
    diameter = min(CHART_WIDTH - 420, CHART_HEIGHT - TITLE_HEIGHT - FOOTER_HEIGHT - 80)
    cx = CHART_WIDTH * 0.38
    cy = TITLE_HEIGHT + (CHART_HEIGHT - TITLE_HEIGHT - FOOTER_HEIGHT) / 2
    bbox = (cx - diameter / 2, cy - diameter / 2, cx + diameter / 2, cy + diameter / 2)
    start = -90.0
    legend_x = int(cx + diameter / 2 + 48)
    legend_y = TITLE_HEIGHT + 40
    font = _font(14)
    for index, item in enumerate(data):
        color = item.color or _PALETTE[index % len(_PALETTE)]
        sweep = item.value / total * 360.0
        end = start + sweep
        if sweep > 0:
            draw.pieslice(bbox, start=start, end=end, fill=_rgb(color), outline="white", width=2)
        if sweep >= 12:
            mid = math.radians(start + sweep / 2)
            label_r = diameter * 0.32
            lx, ly = cx + math.cos(mid) * label_r, cy + math.sin(mid) * label_r
            percent = f"{item.value / total * 100:.0f}%"
            box = draw.textbbox((0, 0), percent, font=_font(13, bold=True))
            draw.text(
                (lx - (box[2] - box[0]) / 2, ly - (box[3] - box[1]) / 2),
                percent,
                font=_font(13, bold=True),
                fill="white",
            )
        draw.rounded_rectangle(
            (legend_x, legend_y, legend_x + 14, legend_y + 14), radius=3, fill=_rgb(color)
        )
        draw.text(
            (legend_x + 22, legend_y - 1),
            f"{item.label} — {_format_number(item.value)}"[:42],
            font=font,
            fill=(40, 52, 64),
        )
        legend_y += 28
        start = end
    return _png_bytes(canvas)


def _render_stacked_bar_chart_png(
    title: str,
    labels: list[str],
    series: list[ChartSeries],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
) -> bytes:
    labels, series = _validate_multi_series(labels, series)
    if any(value < 0 for item in series for value in item.values):
        raise ValueError("stacked bar values must be non-negative")
    canvas, draw = _new_canvas(title)
    totals = [sum(item.values[index] for item in series) for index in range(len(labels))]
    ticks = _nice_ticks(0.0, max(totals) if totals else 1.0)
    y_min, y_max = ticks[0], ticks[-1]
    left, top, right, bottom = _plot_bounds(legend=True)
    plot_width, plot_height = right - left, bottom - top
    span = y_max - y_min or 1.0
    slot, bar_width = plot_width / max(len(labels), 1), plot_width / max(len(labels), 1) * 0.62
    _draw_axis_frame(draw, left, top, right, bottom)
    _draw_y_axis(draw, left, top, right, bottom, ticks, y_min, y_max, y_label)
    centers: list[float] = []
    for category_index in range(len(labels)):
        center_x = left + (category_index + 0.5) * slot
        centers.append(center_x)
        running = 0.0
        for series_index, item in enumerate(series):
            color = item.color or _PALETTE[series_index % len(_PALETTE)]
            value = item.values[category_index]
            y0 = bottom - ((running - y_min) / span) * plot_height
            y1 = bottom - ((running + value - y_min) / span) * plot_height
            draw.rectangle(
                (center_x - bar_width / 2, min(y0, y1), center_x + bar_width / 2, max(y0, y1)),
                fill=_rgb(color),
            )
            running += value
    _draw_x_labels(draw, centers, labels, bottom, x_label)
    _draw_legend(
        draw,
        [
            (item.name, item.color or _PALETTE[index % len(_PALETTE)])
            for index, item in enumerate(series)
        ],
        TITLE_HEIGHT + 10,
    )
    return _png_bytes(canvas)


def _render_area_chart_png(
    title: str,
    labels: list[str],
    series: list[ChartSeries],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
) -> bytes:
    labels, series = _validate_multi_series(labels, series)
    canvas, draw = _new_canvas(title)
    all_values = [value for item in series for value in item.values]
    ticks = _nice_ticks(min(0.0, min(all_values)), max(0.0, max(all_values)))
    y_min, y_max = ticks[0], ticks[-1]
    left, top, right, bottom = _plot_bounds(legend=len(series) > 1)
    plot_width, plot_height = right - left, bottom - top
    _draw_axis_frame(draw, left, top, right, bottom)
    _draw_y_axis(draw, left, top, right, bottom, ticks, y_min, y_max, y_label)
    xs = (
        [left + plot_width / 2]
        if len(labels) == 1
        else [left + index / (len(labels) - 1) * plot_width for index in range(len(labels))]
    )
    legend_items: list[tuple[str, str]] = []
    for series_index, item in enumerate(series):
        color = item.color or _PALETTE[series_index % len(_PALETTE)]
        legend_items.append((item.name, color))
        points = _series_points(
            item.values,
            xs,
            bottom=bottom,
            y_min=y_min,
            y_max=y_max,
            plot_height=plot_height,
        )
        if len(points) >= 2:
            r, g, b = _rgb(color)
            fill = (int(r + (255 - r) * 0.55), int(g + (255 - g) * 0.55), int(b + (255 - b) * 0.55))
            draw.polygon([(points[0][0], bottom), *points, (points[-1][0], bottom)], fill=fill)
            draw.line(points, fill=_rgb(color), width=3)
        for x, y in points:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=_rgb(color), outline="white", width=1)
    _draw_x_labels(draw, xs, labels, bottom, x_label)
    if len(series) > 1:
        _draw_legend(draw, legend_items, TITLE_HEIGHT + 10)
    return _png_bytes(canvas)


def _render_scatter_chart_png(
    title: str,
    points: list[ScatterPoint],
    *,
    x_label: str | None = None,
    y_label: str | None = None,
) -> bytes:
    if not points:
        raise ValueError("at least one scatter point is required")
    if len(points) > MAX_SCATTER_POINTS:
        raise ValueError(f"at most {MAX_SCATTER_POINTS} scatter points are supported")
    canvas, draw = _new_canvas(title)
    xs, ys = [point.x for point in points], [point.y for point in points]
    x_ticks, y_ticks = _nice_ticks(min(xs), max(xs)), _nice_ticks(min(ys), max(ys))
    x_min, x_max, y_min, y_max = x_ticks[0], x_ticks[-1], y_ticks[0], y_ticks[-1]
    left, top, right, bottom = _plot_bounds()
    x_span, y_span = x_max - x_min or 1.0, y_max - y_min or 1.0
    plot_width, plot_height = right - left, bottom - top
    _draw_axis_frame(draw, left, top, right, bottom)
    _draw_y_axis(draw, left, top, right, bottom, y_ticks, y_min, y_max, y_label)
    font = _font(13)
    for tick in x_ticks:
        x = left + ((tick - x_min) / x_span) * plot_width
        draw.line((x, top, x, bottom), fill=(230, 234, 239), width=1)
        label = _format_number(tick)
        box = draw.textbbox((0, 0), label, font=font)
        draw.text((x - (box[2] - box[0]) / 2, bottom + 10), label, font=font, fill=(53, 66, 79))
    if x_label:
        label_font = _font(14, bold=True)
        box = draw.textbbox((0, 0), x_label, font=label_font)
        draw.text(
            ((CHART_WIDTH - (box[2] - box[0])) / 2, CHART_HEIGHT - FOOTER_HEIGHT - 22),
            x_label,
            font=label_font,
            fill=(53, 66, 79),
        )
    label_font = _font(11)
    for index, point in enumerate(points):
        color = point.color or _PALETTE[index % len(_PALETTE)]
        x = left + ((point.x - x_min) / x_span) * plot_width
        y = bottom - ((point.y - y_min) / y_span) * plot_height
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=_rgb(color), outline="white", width=2)
        if point.label:
            text = point.label[:16]
            box = draw.textbbox((0, 0), text, font=label_font)
            draw.text((x + 10, y - (box[3] - box[1]) / 2), text, font=label_font, fill=(40, 52, 64))
    return _png_bytes(canvas)


def _heatmap_color(value: float, minimum: float, maximum: float) -> tuple[int, int, int]:
    t = 0.5 if math.isclose(minimum, maximum) else (value - minimum) / (maximum - minimum)
    t = max(0.0, min(1.0, t))
    return (
        int(245 + (180 - 245) * t),
        int(248 + (40 - 248) * t),
        int(252 + (50 - 252) * t),
    )


def _render_heatmap_png(
    title: str,
    rows: list[str],
    columns: list[str],
    cells: list[HeatmapCell],
) -> bytes:
    if not rows or not columns:
        raise ValueError("heatmap requires at least one row and one column")
    if len(rows) > MAX_CATEGORIES or len(columns) > MAX_CATEGORIES:
        raise ValueError(f"at most {MAX_CATEGORIES} heatmap rows and columns are supported")
    if len(rows) != len(set(rows)) or len(columns) != len(set(columns)):
        raise ValueError("heatmap row and column labels must be unique")
    if len(cells) > MAX_HEATMAP_CELLS:
        raise ValueError(f"at most {MAX_HEATMAP_CELLS} heatmap cells are supported")

    row_index, col_index = (
        {label: i for i, label in enumerate(rows)},
        {label: i for i, label in enumerate(columns)},
    )
    grid: list[list[float | None]] = [[None for _ in columns] for _ in rows]
    for cell in cells:
        if cell.row not in row_index:
            raise ValueError(f"unknown heatmap row '{cell.row}'")
        if cell.column not in col_index:
            raise ValueError(f"unknown heatmap column '{cell.column}'")
        row_i, col_i = row_index[cell.row], col_index[cell.column]
        if grid[row_i][col_i] is not None:
            raise ValueError(f"duplicate heatmap cell '{cell.row}/{cell.column}'")
        grid[row_i][col_i] = cell.value
    values = [value for row in grid for value in row if value is not None]
    if not values:
        raise ValueError("heatmap requires at least one numeric cell")
    minimum, maximum = min(values), max(values)

    canvas, draw = _new_canvas(title)
    left, top, right, bottom = (
        40,
        TITLE_HEIGHT + 36,
        CHART_WIDTH - 40,
        CHART_HEIGHT - FOOTER_HEIGHT - 24,
    )
    corner_w = 140
    cell_w = (right - left - corner_w) / max(len(columns), 1)
    cell_h = (bottom - top) / max(len(rows) + 1, 1)
    header_font, cell_font = _font(12, bold=True), _font(12)
    draw.rectangle((left, top, left + corner_w, top + cell_h), fill=(230, 234, 239))
    for col_i, column in enumerate(columns):
        x0, x1 = left + corner_w + col_i * cell_w, left + corner_w + (col_i + 1) * cell_w
        draw.rectangle((x0, top, x1, top + cell_h), fill=(20, 42, 67))
        text = column if len(column) <= 12 else f"{column[:11]}…"
        box = draw.textbbox((0, 0), text, font=header_font)
        draw.text(
            (x0 + (cell_w - (box[2] - box[0])) / 2, top + (cell_h - (box[3] - box[1])) / 2),
            text,
            font=header_font,
            fill="white",
        )
    for row_i, row in enumerate(rows):
        y0, y1 = top + (row_i + 1) * cell_h, top + (row_i + 2) * cell_h
        draw.rectangle((left, y0, left + corner_w, y1), fill=(245, 247, 250))
        text = row if len(row) <= 16 else f"{row[:15]}…"
        box = draw.textbbox((0, 0), text, font=header_font)
        draw.text(
            (left + 8, y0 + (cell_h - (box[3] - box[1])) / 2),
            text,
            font=header_font,
            fill=(30, 41, 54),
        )
        for col_i, value in enumerate(grid[row_i]):
            x0, x1 = left + corner_w + col_i * cell_w, left + corner_w + (col_i + 1) * cell_w
            if value is None:
                fill, text, text_fill = (238, 241, 244), "—", (120, 130, 140)
            else:
                fill = _heatmap_color(value, minimum, maximum)
                text = _format_number(value)
                brightness = 0.299 * fill[0] + 0.587 * fill[1] + 0.114 * fill[2]
                text_fill = (30, 41, 54) if brightness > 140 else (255, 255, 255)
            draw.rectangle((x0, y0, x1, y1), fill=fill, outline=(220, 225, 230))
            box = draw.textbbox((0, 0), text, font=cell_font)
            draw.text(
                (x0 + (cell_w - (box[2] - box[0])) / 2, y0 + (cell_h - (box[3] - box[1])) / 2),
                text,
                font=cell_font,
                fill=text_fill,
            )
    return _png_bytes(canvas)


def _slugify(value: str) -> str:
    value = Path(value).stem
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:100] or "research-chart"


def _unique_path(stem: str) -> Path:
    base = _slugify(stem)
    for index in range(1, 1000):
        suffix = "" if index == 1 else f"-{index}"
        path = CHARTS_DIR / f"{base}{suffix}.png"
        if not path.exists():
            return path
    raise RuntimeError("unable to allocate a unique chart filename")


def _save_chart_png(
    title: str, png: bytes, *, chart_kind: str, filename: str | None, detail: str
) -> str:
    with _SAVE_LOCK:
        CHARTS_DIR.mkdir(parents=True, exist_ok=True)
        path = _unique_path(filename or title)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(png)
        temporary.replace(path)
    try:
        relative_path = path.resolve().relative_to(Path.cwd().resolve())
        markdown_path = relative_path.as_posix()
    except ValueError:
        markdown_path = path.resolve().as_uri()
    return json.dumps(
        {
            "ok": True,
            "chart_kind": chart_kind,
            "title": title,
            "path": str(path.resolve()),
            "relative_path": markdown_path,
            "markdown_embed": f"![{title.replace(']', r'\\]')}]({markdown_path})",
            "detail": detail,
            "data_note": (
                "Values were supplied by the caller and are rendered as reported; "
                "the chart tool does not independently verify them."
            ),
        },
        ensure_ascii=False,
    )


def _run_chart_tool(name: str, operation) -> str:
    try:
        return operation()
    except (OSError, ValueError, RuntimeError) as exc:
        ai_log.exception("Chart tool %s failed", name)
        return json.dumps({"ok": False, "tool": name, "error": str(exc)}, ensure_ascii=False)


@tool("generate_bar_chart")
def generate_bar_chart(
    title: Annotated[str, Field(min_length=1, max_length=160, description="Chart title")],
    data: Annotated[
        list[ChartDatum],
        Field(min_length=1, max_length=MAX_CATEGORIES, description="Labelled values"),
    ],
    x_label: Annotated[str | None, Field(description="Optional x-axis label")] = None,
    y_label: Annotated[str | None, Field(description="Optional y-axis label")] = None,
    filename: Annotated[str | None, Field(description="Optional safe PNG basename")] = None,
) -> str:
    """Generate a vertical bar chart PNG from labelled research figures."""
    return _run_chart_tool(
        "generate_bar_chart",
        lambda: _save_chart_png(
            title,
            _render_bar_chart_png(title, data, x_label=x_label, y_label=y_label),
            chart_kind="bar",
            filename=filename,
            detail=f"categories={len(data)}",
        ),
    )


@tool("generate_horizontal_bar_chart")
def generate_horizontal_bar_chart(
    title: Annotated[str, Field(min_length=1, max_length=160, description="Chart title")],
    data: Annotated[
        list[ChartDatum],
        Field(min_length=1, max_length=MAX_CATEGORIES, description="Labelled values"),
    ],
    x_label: Annotated[str | None, Field(description="Optional value-axis label")] = None,
    y_label: Annotated[str | None, Field(description="Optional category-axis label")] = None,
    filename: Annotated[str | None, Field(description="Optional safe PNG basename")] = None,
) -> str:
    """Generate a horizontal bar chart PNG for long category labels."""
    return _run_chart_tool(
        "generate_horizontal_bar_chart",
        lambda: _save_chart_png(
            title,
            _render_bar_chart_png(title, data, horizontal=True, x_label=x_label, y_label=y_label),
            chart_kind="horizontal_bar",
            filename=filename,
            detail=f"categories={len(data)}",
        ),
    )


@tool("generate_line_chart")
def generate_line_chart(
    title: Annotated[str, Field(min_length=1, max_length=160, description="Chart title")],
    labels: Annotated[
        list[str], Field(min_length=1, max_length=MAX_CATEGORIES, description="X-axis labels")
    ],
    series: Annotated[
        list[ChartSeries], Field(min_length=1, max_length=MAX_SERIES, description="Named series")
    ],
    x_label: Annotated[str | None, Field(description="Optional x-axis label")] = None,
    y_label: Annotated[str | None, Field(description="Optional y-axis label")] = None,
    filename: Annotated[str | None, Field(description="Optional safe PNG basename")] = None,
) -> str:
    """Generate a line chart PNG with one or more series."""
    return _run_chart_tool(
        "generate_line_chart",
        lambda: _save_chart_png(
            title,
            _render_line_chart_png(title, labels, series, x_label=x_label, y_label=y_label),
            chart_kind="line",
            filename=filename,
            detail=f"categories={len(labels)}, series={len(series)}",
        ),
    )


@tool("generate_pie_chart")
def generate_pie_chart(
    title: Annotated[str, Field(min_length=1, max_length=160, description="Chart title")],
    data: Annotated[
        list[ChartDatum],
        Field(min_length=1, max_length=MAX_CATEGORIES, description="Non-negative labelled shares"),
    ],
    filename: Annotated[str | None, Field(description="Optional safe PNG basename")] = None,
) -> str:
    """Generate a pie chart PNG from non-negative labelled shares."""
    return _run_chart_tool(
        "generate_pie_chart",
        lambda: _save_chart_png(
            title,
            _render_pie_chart_png(title, data),
            chart_kind="pie",
            filename=filename,
            detail=f"slices={len(data)}",
        ),
    )


@tool("generate_stacked_bar_chart")
def generate_stacked_bar_chart(
    title: Annotated[str, Field(min_length=1, max_length=160, description="Chart title")],
    labels: Annotated[
        list[str], Field(min_length=1, max_length=MAX_CATEGORIES, description="X-axis labels")
    ],
    series: Annotated[
        list[ChartSeries],
        Field(min_length=1, max_length=MAX_SERIES, description="Non-negative named series"),
    ],
    x_label: Annotated[str | None, Field(description="Optional x-axis label")] = None,
    y_label: Annotated[str | None, Field(description="Optional y-axis label")] = None,
    filename: Annotated[str | None, Field(description="Optional safe PNG basename")] = None,
) -> str:
    """Generate a stacked vertical bar chart PNG from multi-series figures."""
    return _run_chart_tool(
        "generate_stacked_bar_chart",
        lambda: _save_chart_png(
            title,
            _render_stacked_bar_chart_png(title, labels, series, x_label=x_label, y_label=y_label),
            chart_kind="stacked_bar",
            filename=filename,
            detail=f"categories={len(labels)}, series={len(series)}",
        ),
    )


@tool("generate_area_chart")
def generate_area_chart(
    title: Annotated[str, Field(min_length=1, max_length=160, description="Chart title")],
    labels: Annotated[
        list[str], Field(min_length=1, max_length=MAX_CATEGORIES, description="X-axis labels")
    ],
    series: Annotated[
        list[ChartSeries], Field(min_length=1, max_length=MAX_SERIES, description="Named series")
    ],
    x_label: Annotated[str | None, Field(description="Optional x-axis label")] = None,
    y_label: Annotated[str | None, Field(description="Optional y-axis label")] = None,
    filename: Annotated[str | None, Field(description="Optional safe PNG basename")] = None,
) -> str:
    """Generate a filled area chart PNG from one or more series."""
    return _run_chart_tool(
        "generate_area_chart",
        lambda: _save_chart_png(
            title,
            _render_area_chart_png(title, labels, series, x_label=x_label, y_label=y_label),
            chart_kind="area",
            filename=filename,
            detail=f"categories={len(labels)}, series={len(series)}",
        ),
    )


@tool("generate_scatter_chart")
def generate_scatter_chart(
    title: Annotated[str, Field(min_length=1, max_length=160, description="Chart title")],
    points: Annotated[
        list[ScatterPoint],
        Field(min_length=1, max_length=MAX_SCATTER_POINTS, description="X/Y observations"),
    ],
    x_label: Annotated[str | None, Field(description="Optional x-axis label")] = None,
    y_label: Annotated[str | None, Field(description="Optional y-axis label")] = None,
    filename: Annotated[str | None, Field(description="Optional safe PNG basename")] = None,
) -> str:
    """Generate a scatter plot PNG from research observations."""
    return _run_chart_tool(
        "generate_scatter_chart",
        lambda: _save_chart_png(
            title,
            _render_scatter_chart_png(title, points, x_label=x_label, y_label=y_label),
            chart_kind="scatter",
            filename=filename,
            detail=f"points={len(points)}",
        ),
    )


@tool("generate_heatmap_chart")
def generate_heatmap_chart(
    title: Annotated[str, Field(min_length=1, max_length=160, description="Chart title")],
    rows: Annotated[
        list[str], Field(min_length=1, max_length=MAX_CATEGORIES, description="Row labels")
    ],
    columns: Annotated[
        list[str], Field(min_length=1, max_length=MAX_CATEGORIES, description="Column labels")
    ],
    cells: Annotated[
        list[HeatmapCell],
        Field(min_length=1, max_length=MAX_HEATMAP_CELLS, description="Numeric cells"),
    ],
    filename: Annotated[str | None, Field(description="Optional safe PNG basename")] = None,
) -> str:
    """Generate a numeric heatmap PNG from a research matrix."""
    return _run_chart_tool(
        "generate_heatmap_chart",
        lambda: _save_chart_png(
            title,
            _render_heatmap_png(title, rows, columns, cells),
            chart_kind="heatmap",
            filename=filename,
            detail=f"rows={len(rows)}, columns={len(columns)}, cells={len(cells)}",
        ),
    )


CHART_TOOLS = (
    generate_bar_chart,
    generate_horizontal_bar_chart,
    generate_line_chart,
    generate_pie_chart,
    generate_stacked_bar_chart,
    generate_area_chart,
    generate_scatter_chart,
    generate_heatmap_chart,
)

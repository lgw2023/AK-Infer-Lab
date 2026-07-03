#!/usr/bin/env python3
"""Render the LLM inference hardware map as a motherboard-style architecture diagram.

Outputs:
- 大模型推理硬件体系主板俯视图.svg
- 大模型推理硬件体系主板俯视图.excalidraw
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape


HERE = Path(__file__).resolve().parent
SVG_OUT = HERE / "大模型推理硬件体系主板俯视图.svg"
EXCALIDRAW_OUT = HERE / "大模型推理硬件体系主板俯视图.excalidraw"

W = 2200
H = 1400
FONT = "-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Noto Sans CJK SC', 'Microsoft YaHei', Arial, sans-serif"


def esc(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def svg_text(
    x: float,
    y: float,
    text: str,
    size: int = 24,
    fill: str = "#0f172a",
    weight: int | str = 500,
    anchor: str = "middle",
    line_gap: float = 1.22,
    extra: str = "",
) -> str:
    lines = text.splitlines() or [""]
    y0 = y - ((len(lines) - 1) * size * line_gap) / 2
    parts = []
    for i, line in enumerate(lines):
        line_y = y0 + i * size * line_gap
        parts.append(
            f'<text x="{x:.1f}" y="{line_y:.1f}" text-anchor="{anchor}" '
            f'font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" {extra}>{esc(line)}</text>'
        )
    return "\n".join(parts)


def rect(
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str,
    stroke: str = "#1f2937",
    sw: float = 2,
    rx: float = 14,
    extra: str = "",
) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'rx="{rx:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>'
    )


def line(x1: float, y1: float, x2: float, y2: float, color: str, width: float = 5, dash: str = "") -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
        f'marker-end="url(#{marker_for(color)})"{dash_attr}/>'
    )


def path(d: str, color: str, width: float = 5, dash: str = "") -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round" marker-end="url(#{marker_for(color)})"{dash_attr}/>'
    )


def marker_for(color: str) -> str:
    return {
        "#e4572e": "arrow-hot",
        "#0b7285": "arrow-warm",
        "#7b2cbf": "arrow-cold",
        "#475569": "arrow-control",
        "#b7791f": "arrow-copper",
    }.get(color, "arrow-control")


def chip(x: float, y: float, w: float, h: float, title: str, subtitle: str, fill: str, stroke: str) -> list[str]:
    parts = []
    parts.append(rect(x, y, w, h, fill, stroke, 3, 22, 'filter="url(#chip-shadow)"'))
    pin_color = "#64748b"
    for i in range(12):
        px = x + 16 + i * ((w - 32) / 11)
        parts.append(rect(px - 4, y - 13, 8, 13, pin_color, pin_color, 0, 1))
        parts.append(rect(px - 4, y + h, 8, 13, pin_color, pin_color, 0, 1))
    for i in range(8):
        py = y + 18 + i * ((h - 36) / 7)
        parts.append(rect(x - 13, py - 4, 13, 8, pin_color, pin_color, 0, 1))
        parts.append(rect(x + w, py - 4, 13, 8, pin_color, pin_color, 0, 1))
    parts.append(svg_text(x + w / 2, y + 54, title, 31, "#ffffff", 760))
    parts.append(svg_text(x + w / 2, y + 94, subtitle, 19, "#dbeafe", 560))
    return parts


def small_label(x: float, y: float, w: float, h: float, text: str, fill: str, stroke: str = "#334155") -> list[str]:
    return [rect(x, y, w, h, fill, stroke, 1.4, 8), svg_text(x + w / 2, y + h / 2 + 2, text, 16, "#0f172a", 650)]


def callout(x: float, y: float, w: float, h: float, title: str, body: str, color: str) -> list[str]:
    parts = [
        rect(x, y, w, h, "#ffffff", color, 2.2, 12, 'filter="url(#soft-shadow)"'),
        rect(x, y, 10, h, color, color, 0, 8),
        svg_text(x + 24, y + 34, title, 21, color, 760, "start"),
        svg_text(x + 24, y + 82, body, 14, "#334155", 500, "start", 1.34),
    ]
    return parts


def draw_svg() -> str:
    hot = "#e4572e"
    warm = "#0b7285"
    cold = "#7b2cbf"
    control = "#475569"
    copper = "#b7791f"
    parts: list[str] = []

    parts.append(
        f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <filter id="chip-shadow" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="14" stdDeviation="12" flood-color="#0f172a" flood-opacity="0.22"/>
  </filter>
  <filter id="soft-shadow" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#0f172a" flood-opacity="0.12"/>
  </filter>
  <pattern id="trace-grid" width="52" height="52" patternUnits="userSpaceOnUse">
    <path d="M 52 0 L 0 0 0 52" fill="none" stroke="#77a37d" stroke-width="1" opacity="0.22"/>
  </pattern>
  <marker id="arrow-hot" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
    <path d="M2,2 L10,6 L2,10 Z" fill="{hot}"/>
  </marker>
  <marker id="arrow-warm" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
    <path d="M2,2 L10,6 L2,10 Z" fill="{warm}"/>
  </marker>
  <marker id="arrow-cold" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
    <path d="M2,2 L10,6 L2,10 Z" fill="{cold}"/>
  </marker>
  <marker id="arrow-control" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
    <path d="M2,2 L10,6 L2,10 Z" fill="{control}"/>
  </marker>
  <marker id="arrow-copper" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth">
    <path d="M2,2 L10,6 L2,10 Z" fill="{copper}"/>
  </marker>
</defs>
<rect x="0" y="0" width="{W}" height="{H}" fill="#f8fafc"/>
'''
    )

    parts.append(svg_text(110, 76, "大模型推理硬件体系主板俯视图", 34, "#0f172a", 800, "start"))
    parts.append(svg_text(110, 118, "从热路径、温层状态、冷层存储、远端数据面与仿真观测五条线看代表性工作到底动了哪些硬件。", 19, "#475569", 520, "start"))
    parts.append(svg_text(1950, 76, "A+K / Ascend + Kunpeng", 24, "#0f766e", 800, "middle"))
    parts.append(svg_text(1950, 112, "基于《大模型推理硬件层面对照地图》", 15, "#64748b", 520, "middle"))

    board_x, board_y, board_w, board_h = 230, 160, 1540, 1090
    parts.append(rect(board_x, board_y, board_w, board_h, "#dfeedd", "#2f6f4e", 4, 32, 'filter="url(#soft-shadow)"'))
    parts.append(f'<rect x="{board_x+18}" y="{board_y+18}" width="{board_w-36}" height="{board_h-36}" rx="22" fill="url(#trace-grid)" opacity="0.75"/>')
    for sx, sy in [(260, 190), (1735, 190), (260, 1218), (1735, 1218)]:
        parts.append(f'<circle cx="{sx}" cy="{sy}" r="20" fill="#cbd5c0" stroke="#2f6f4e" stroke-width="3"/>')
        parts.append(f'<circle cx="{sx}" cy="{sy}" r="8" fill="#f8fafc" stroke="#6b7280" stroke-width="1.5"/>')

    # Main components.
    parts.extend(chip(650, 430, 430, 320, "Ascend NPU / GPU", "AI Core / Cube / Attention / FFN / MoE gate", "#174e63", "#0f2f3c"))
    parts.extend(chip(1185, 460, 330, 270, "Kunpeng CPU", "scheduler / metadata / SVE / fallback", "#58317d", "#34204d"))
    parts.append(rect(1005, 790, 205, 90, "#fff7ed", "#c2410c", 2.3, 12))
    parts.append(svg_text(1107, 824, "PCIe / DMA", 22, "#9a3412", 800))
    parts.append(svg_text(1107, 856, "D2H / H2D / stream", 15, "#7c2d12", 600))
    parts.append(rect(325, 255, 280, 135, "#e0f2fe", "#0369a1", 2.3, 14))
    parts.append(svg_text(465, 302, "Runtime 控制面", 24, "#075985", 800))
    parts.append(svg_text(465, 340, "scheduler / sampler\ncache manager / connector", 15, "#0f172a", 560))
    parts.append(rect(345, 500, 210, 120, "#fef9c3", "#a16207", 2, 14))
    parts.append(svg_text(450, 540, "请求 / 会话", 23, "#854d0e", 800))
    parts.append(svg_text(450, 578, "prompt / output\nprefix reuse / SLO", 15, "#334155", 560))

    # HBM stacks around NPU.
    hbm_specs = [
        (540, 455, "HBM\nweights"),
        (540, 560, "HBM\nKV hot"),
        (820, 360, "L2/SRAM\nworkspace"),
        (820, 775, "HBM\nactivation"),
        (1098, 535, "NPU mem\npaged KV"),
    ]
    for x, y, label in hbm_specs:
        parts.append(rect(x, y, 98, 72, "#bae6fd", "#0284c7", 1.8, 8))
        parts.append(svg_text(x + 49, y + 36, label, 15, "#0c4a6e", 800))

    # AI core grid.
    for row in range(3):
        for col in range(5):
            parts.append(rect(708 + col * 64, 555 + row * 43, 42, 28, "#256d85", "#9bd7e6", 1, 4))
    parts.append(svg_text(865, 681, "prefill 算力密集 / decode 读 KV", 16, "#e0f2fe", 650))

    # CPU cores.
    for row in range(3):
        for col in range(4):
            parts.append(rect(1235 + col * 58, 555 + row * 42, 38, 28, "#7249a2", "#d8b4fe", 1, 4))
    parts.extend(small_label(1235, 648, 112, 34, "NUMA", "#f3e8ff", "#7e22ce"))
    parts.extend(small_label(1360, 648, 112, 34, "SVE/SME", "#f3e8ff", "#7e22ce"))

    # DDR DIMMs.
    parts.append(svg_text(1420, 255, "CPU DDR / NUMA / pinned memory / host KV pool", 19, "#166534", 800))
    for i, y in enumerate([285, 340, 395, 450]):
        parts.append(rect(1255, y, 455, 34, "#bbf7d0", "#15803d", 1.8, 7))
        for j in range(12):
            parts.append(rect(1270 + j * 34, y + 7, 18, 20, "#65a30d", "#3f6212", 0.5, 2))
        parts.append(svg_text(1685, y + 22, f"DDR{i}", 13, "#14532d", 800))

    # NVMe and external storage.
    parts.append(svg_text(1438, 920, "NVMe / SSD / local object store", 19, "#6d28d9", 800))
    for i, y in enumerate([945, 1002, 1059]):
        parts.append(rect(1195, y, 520, 38, "#ede9fe", "#7c3aed", 1.8, 8))
        parts.append(rect(1215, y + 10, 68, 18, "#a78bfa", "#6d28d9", 0.8, 4))
        parts.append(svg_text(1455, y + 24, ["KV cold tier", "expert cold tier", "SSD/NFS/3FS backend"][i], 15, "#3b0764", 700))
    parts.append(rect(760, 1010, 350, 110, "#f5f3ff", "#6d28d9", 2, 14))
    parts.append(svg_text(935, 1052, "CXL / Fabric Mem / remote memory", 20, "#5b21b6", 800))
    parts.append(svg_text(935, 1089, "capacity tier / warm-cold boundary", 15, "#334155", 560))

    # NIC and telemetry.
    parts.append(rect(315, 830, 300, 150, "#dcfce7", "#15803d", 2.2, 14))
    parts.append(svg_text(465, 874, "NIC / RDMA", 24, "#166534", 800))
    parts.append(svg_text(465, 914, "NIXL / Mooncake\nP/D transfer / remote H2D", 15, "#0f172a", 560))
    parts.append(rect(325, 1030, 330, 130, "#e2e8f0", "#475569", 2.2, 14))
    parts.append(svg_text(490, 1070, "Profiler + Simulator", 23, "#334155", 800))
    parts.append(svg_text(490, 1110, "timeline / counters / power\nTTFT / TPOT / P99 / stall_reason", 15, "#0f172a", 560))

    # State ledger.
    parts.append(rect(700, 205, 495, 135, "#fff1f2", "#be123c", 2.2, 14))
    parts.append(svg_text(948, 247, "统一 State Object Ledger", 24, "#9f1239", 800))
    parts.append(svg_text(948, 288, "KV / expert / prefix / weight / activation / latent", 16, "#334155", 650))
    parts.append(svg_text(948, 316, "bytes · tier · hotness · next_use · load/evict/recompute cost", 14, "#475569", 500))

    # Board-internal traces.
    parts.append(line(555, 560, 650, 560, hot, 7))
    parts.append(line(605, 323, 650, 468, control, 4))
    parts.append(path("M 605 340 C 705 345, 700 268, 700 268", control, 3.5, "7 8"))
    parts.append(line(1080, 632, 1185, 603, hot, 6))
    parts.append(path("M 990 735 C 1030 770, 1060 790, 1107 790", warm, 6))
    parts.append(line(1107, 790, 1280, 730, warm, 6))
    parts.append(path("M 1210 835 C 1285 830, 1320 760, 1360 730", warm, 5))
    parts.append(path("M 1395 730 C 1455 820, 1500 890, 1500 945", cold, 5))
    parts.append(path("M 1220 975 C 1120 975, 1035 1010, 985 1010", cold, 4.5))
    parts.append(path("M 935 1010 C 780 955, 670 920, 615 900", "#0b7285", 4.5))
    parts.append(path("M 615 900 C 760 845, 980 855, 1005 835", "#0b7285", 5))
    parts.append(path("M 1515 590 C 1620 650, 1640 795, 1515 945", cold, 4.5, "10 8"))
    parts.append(path("M 655 1095 C 800 1060, 905 925, 1005 850", control, 3.5, "8 8"))
    parts.append(path("M 655 1095 C 940 1155, 1320 1110, 1440 1097", control, 3.5, "8 8"))

    # Trace labels.
    parts.append(rect(705, 840, 250, 42, "#fff7ed", hot, 1.5, 20))
    parts.append(svg_text(830, 867, "热路径：NPU/HBM/token", 16, hot, 800))
    parts.append(rect(965, 900, 280, 42, "#ecfeff", warm, 1.5, 20))
    parts.append(svg_text(1105, 927, "温路径：HBM ⇄ DDR", 16, warm, 800))
    parts.append(rect(1305, 1130, 320, 42, "#f5f3ff", cold, 1.5, 20))
    parts.append(svg_text(1465, 1157, "冷路径：DDR ⇄ SSD/remote", 16, cold, 800))
    parts.append(rect(420, 1168, 315, 42, "#f8fafc", control, 1.5, 20))
    parts.append(svg_text(578, 1195, "观测：trace/counter/power", 16, control, 800))

    # Layer strips.
    layers = [
        ("L0", "workload", 260),
        ("L1", "accelerator compute", 430),
        ("L2-L3", "HBM + state layout", 610),
        ("L4-L7", "DMA / PCIe / fabric", 790),
        ("L8-L9", "SSD / RDMA / remote", 970),
        ("L10-L11", "runtime / telemetry", 1150),
    ]
    for tag, label, y in layers:
        parts.append(rect(185, y - 24, 90, 34, "#ffffff", "#64748b", 1.4, 17))
        parts.append(svg_text(230, y - 2, tag, 15, "#0f172a", 800))
        parts.append(svg_text(286, y - 1, label, 13, "#475569", 550, "start"))

    # Edge callouts.
    parts.extend(callout(55, 190, 285, 150, "L0 / L10 控制面", "ServeGen：真实负载\nMooncake / Bidaw：队列\nvLLM connector：cache 命中", control))
    parts.extend(callout(55, 390, 285, 170, "L1 / L2 主算与 HBM", "prefill：算力密集\ndecode：频繁读 KV\nKV / weights / workspace 争 HBM", hot))
    parts.extend(callout(55, 795, 285, 168, "L9 远端数据面", "RDMA / NIXL / Mooncake\nP/D transfer / KV exchange\nremote H2D 必须可重叠", warm))
    parts.extend(callout(1815, 230, 330, 178, "NEO 硬件切面", "KV 留在 CPU DDR\nCPU 跑部分 decode attention\nPCIe 只搬必要小张量\nCPU/GPU pipeline 隐藏慢路径", "#dc2626"))
    parts.extend(callout(1815, 455, 330, 192, "Tutti / SSD 切面", "SSD-backed KV 的核心风险：\ntiny random I/O\nCPU control path\nDRAM-HBM bounce 与 NPU stall", cold))
    parts.extend(callout(1815, 705, 330, 190, "Ascend + Kunpeng 路线", "P0：CPU KV warm tier\nP1：UCM / KV Pool / Mooncake\nP2：SSD cold tier\nP3：NPU-native storage path", "#0f766e"))
    parts.extend(callout(1815, 955, 330, 178, "仿真器最小字段", "object_id / tier / bytes\nnext_use / load_cost\nevict / recompute / overlap\nstall_reason / TTFT / TPOT / P99", "#334155"))

    # Callout connector lines.
    parts.append(line(340, 305, 325, 315, control, 3))
    parts.append(line(340, 470, 650, 520, hot, 3))
    parts.append(line(340, 880, 315, 900, warm, 3))
    parts.append(line(1815, 318, 1515, 595, "#e4572e", 3))
    parts.append(line(1815, 540, 1510, 965, cold, 3))
    parts.append(line(1815, 780, 1510, 730, "#0b7285", 3))
    parts.append(line(1815, 1040, 655, 1095, control, 3, "8 8"))

    # Legend.
    parts.append(rect(780, 1272, 770, 74, "#ffffff", "#cbd5e1", 1.5, 16))
    legend = [
        (820, hot, "热路径：主算/本地 HBM"),
        (1045, warm, "温路径：CPU DDR / DMA"),
        (1290, cold, "冷路径：SSD / remote"),
    ]
    for x, c, label in legend:
        parts.append(f'<circle cx="{x}" cy="1310" r="9" fill="{c}"/>')
        parts.append(svg_text(x + 18, 1315, label, 15, "#334155", 650, "start"))
    parts.append(rect(1585, 1272, 540, 74, "#ffffff", "#cbd5e1", 1.5, 16))
    parts.append(svg_text(1615, 1310, "判定规则：对象是什么、跨哪条链路、\n是否可被主流水线隐藏。", 16, "#0f172a", 800, "start"))

    parts.append("</svg>")
    return "\n".join(parts)


class ExcalidrawBuilder:
    def __init__(self) -> None:
        self.elements: list[dict[str, object]] = []
        self.next_id = 1

    def _id(self) -> str:
        value = f"hwmap-{self.next_id:04d}"
        self.next_id += 1
        return value

    def rect(self, x: float, y: float, w: float, h: float, text: str, bg: str, stroke: str) -> None:
        rid = self._id()
        self.elements.append(
            {
                "id": rid,
                "type": "rectangle",
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "angle": 0,
                "strokeColor": stroke,
                "backgroundColor": bg,
                "fillStyle": "solid",
                "strokeWidth": 2,
                "strokeStyle": "solid",
                "roughness": 1,
                "opacity": 100,
                "groupIds": [],
                "frameId": None,
                "roundness": {"type": 3},
                "seed": 1000 + self.next_id,
                "versionNonce": 2000 + self.next_id,
                "isDeleted": False,
                "boundElements": None,
                "updated": 1,
                "link": None,
                "locked": False,
            }
        )
        self.text(x + w / 2, y + h / 2, text, min(w - 20, 300), min(h - 12, 120), 22 if h > 90 else 17, "#0f172a")

    def text(self, x: float, y: float, text: str, w: float, h: float, size: int, color: str, align: str = "center") -> None:
        self.elements.append(
            {
                "id": self._id(),
                "type": "text",
                "x": x - w / 2 if align == "center" else x,
                "y": y - h / 2,
                "width": w,
                "height": h,
                "angle": 0,
                "strokeColor": color,
                "backgroundColor": "transparent",
                "fillStyle": "solid",
                "strokeWidth": 1,
                "strokeStyle": "solid",
                "roughness": 1,
                "opacity": 100,
                "groupIds": [],
                "frameId": None,
                "roundness": None,
                "seed": 1000 + self.next_id,
                "versionNonce": 2000 + self.next_id,
                "isDeleted": False,
                "boundElements": None,
                "updated": 1,
                "link": None,
                "locked": False,
                "text": text,
                "fontSize": size,
                "fontFamily": 5,
                "textAlign": align,
                "verticalAlign": "middle",
                "containerId": None,
                "originalText": text,
                "lineHeight": 1.25,
                "baseline": h * 0.75,
            }
        )

    def arrow(self, x1: float, y1: float, x2: float, y2: float, color: str, label: str = "") -> None:
        self.elements.append(
            {
                "id": self._id(),
                "type": "arrow",
                "x": x1,
                "y": y1,
                "width": x2 - x1,
                "height": y2 - y1,
                "angle": 0,
                "strokeColor": color,
                "backgroundColor": "transparent",
                "fillStyle": "solid",
                "strokeWidth": 3,
                "strokeStyle": "solid",
                "roughness": 1,
                "opacity": 100,
                "groupIds": [],
                "frameId": None,
                "roundness": {"type": 2},
                "seed": 1000 + self.next_id,
                "versionNonce": 2000 + self.next_id,
                "isDeleted": False,
                "boundElements": None,
                "updated": 1,
                "link": None,
                "locked": False,
                "points": [[0, 0], [x2 - x1, y2 - y1]],
                "lastCommittedPoint": None,
                "startBinding": None,
                "endBinding": None,
                "startArrowhead": None,
                "endArrowhead": "arrow",
            }
        )
        if label:
            self.text((x1 + x2) / 2, (y1 + y2) / 2 - 16, label, 180, 34, 15, color)


def write_excalidraw() -> None:
    b = ExcalidrawBuilder()
    b.text(100, 70, "大模型推理硬件体系主板俯视图", 620, 50, 30, "#0f172a", "left")
    b.rect(230, 160, 1540, 1090, "", "#dfeedd", "#2f6f4e")
    b.rect(650, 430, 430, 320, "Ascend NPU / GPU\nAI Core / Cube\nprefill / decode / attention", "#bae6fd", "#0369a1")
    b.rect(1185, 460, 330, 270, "Kunpeng CPU\nscheduler / metadata\nSVE / fallback", "#f3e8ff", "#7e22ce")
    b.rect(1255, 285, 455, 200, "CPU DDR / NUMA\nhost KV pool / pinned memory", "#bbf7d0", "#15803d")
    b.rect(1005, 790, 205, 90, "PCIe / DMA\nD2H / H2D / stream", "#fff7ed", "#c2410c")
    b.rect(1195, 945, 520, 155, "NVMe / SSD / object store\nKV cold tier / expert cold tier", "#ede9fe", "#7c3aed")
    b.rect(315, 830, 300, 150, "NIC / RDMA\nNIXL / Mooncake\nP/D transfer", "#dcfce7", "#15803d")
    b.rect(325, 255, 280, 135, "Runtime 控制面\nscheduler / cache manager", "#e0f2fe", "#0369a1")
    b.rect(700, 205, 495, 135, "统一 State Object Ledger\nKV / expert / prefix / weight / activation", "#fff1f2", "#be123c")
    b.rect(325, 1030, 330, 130, "Profiler + Simulator\ntrace / counters / power\nTTFT / TPOT / P99", "#e2e8f0", "#475569")
    b.rect(1815, 230, 330, 178, "NEO\nKV 留 CPU DDR；CPU 跑部分 decode attention；PCIe 只搬小张量", "#ffffff", "#dc2626")
    b.rect(1815, 455, 330, 192, "Tutti / SSD\nobject I/O；避免 tiny random I/O、CPU control path、DRAM-HBM bounce", "#ffffff", "#7b2cbf")
    b.rect(1815, 705, 330, 190, "Ascend + Kunpeng 路线\nP0 CPU KV warm tier\nP1 UCM/KV Pool/Mooncake\nP2 SSD cold tier", "#ffffff", "#0f766e")
    b.arrow(605, 323, 650, 468, "#475569", "control")
    b.arrow(555, 560, 650, 560, "#e4572e", "hot")
    b.arrow(1080, 632, 1185, 603, "#e4572e", "GPU/NPU + CPU")
    b.arrow(1107, 790, 1280, 730, "#0b7285", "HBM ⇄ DDR")
    b.arrow(1395, 730, 1500, 945, "#7b2cbf", "DDR ⇄ SSD")
    b.arrow(615, 900, 1005, 835, "#0b7285", "RDMA / Mooncake")
    b.arrow(655, 1095, 1005, 850, "#475569", "telemetry")
    b.arrow(1815, 318, 1515, 595, "#e4572e")
    b.arrow(1815, 540, 1510, 965, "#7b2cbf")
    payload = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": b.elements,
        "appState": {"viewBackgroundColor": "#f8fafc", "gridSize": 20},
        "files": {},
    }
    EXCALIDRAW_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    SVG_OUT.write_text(draw_svg(), encoding="utf-8")
    write_excalidraw()
    print(SVG_OUT)
    print(EXCALIDRAW_OUT)


if __name__ == "__main__":
    main()

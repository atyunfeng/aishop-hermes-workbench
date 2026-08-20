#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
STORYBOARD_PATH = ROOT / "demo-video" / "storyboard.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "demo-video"
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
)

COLORS = {
    "background": "#071019",
    "panel": "#101D29",
    "panel_alt": "#142535",
    "stroke": "#263B4C",
    "text": "#F5F9FC",
    "muted": "#91A6B7",
    "cyan": "#25D6C6",
    "blue": "#548DFF",
    "purple": "#9A7CFF",
    "orange": "#FFAA52",
    "red": "#FF6B6B",
    "green": "#56D58B",
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = list(FONT_CANDIDATES)
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size, index=1 if bold else 0)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int):
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for character in paragraph:
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > width:
                lines.append(current)
                current = character
            else:
                current = candidate
        lines.append(current)
    return lines


def _rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str,
    radius: int = 28,
    outline: str | None = None,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _gradient(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), COLORS["background"])
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = (
            int(7 + 7 * ratio),
            int(16 + 10 * ratio),
            int(25 + 19 * ratio),
        )
        draw.line((0, y, width, y), fill=color)
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-220, 80, 720, 1020), fill=(37, 214, 198, 36))
    glow_draw.ellipse((540, 480, 1420, 1360), fill=(84, 141, 255, 32))
    glow = glow.filter(ImageFilter.GaussianBlur(110))
    return Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    size: int,
    fill: str = COLORS["text"],
    bold: bool = False,
    max_width: int | None = None,
    spacing: int = 12,
) -> int:
    font = _font(size, bold)
    lines = _wrap(draw, value, font, max_width) if max_width else [value]
    y = xy[1]
    for line in lines:
        draw.text((xy[0], y), line, font=font, fill=fill)
        bbox = draw.textbbox((xy[0], y), line, font=font)
        y = bbox[3] + spacing
    return y


def _centered(draw: ImageDraw.ImageDraw, y: int, value: str, size: int, fill: str, bold=False):
    font = _font(size, bold)
    bbox = draw.textbbox((0, 0), value, font=font)
    draw.text(((1080 - (bbox[2] - bbox[0])) / 2, y), value, font=font, fill=fill)


def _header(draw: ImageDraw.ImageDraw, scene: dict[str, Any], index: int, count: int) -> None:
    _rounded(draw, (54, 58, 368, 120), COLORS["panel"], 24, COLORS["stroke"])
    draw.ellipse((76, 77, 101, 102), fill=COLORS["cyan"])
    _text(draw, (118, 73), "AIShop · Hermes", 25, bold=True)
    _rounded(draw, (820, 58, 1026, 120), "#1F1A12", 24, COLORS["orange"])
    _centered_in_box(draw, (820, 58, 1026, 120), "SIMULATED", 22, COLORS["orange"], True)
    _text(draw, (56, 162), f"{index:02d} / {count:02d}", 22, COLORS["muted"], bold=True)
    _text(draw, (56, 212), scene["title"], 56, bold=True, max_width=960, spacing=8)


def _centered_in_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    value: str,
    size: int,
    fill: str,
    bold: bool = False,
) -> None:
    font = _font(size, bold)
    bbox = draw.textbbox((0, 0), value, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = box[0] + (box[2] - box[0] - width) / 2
    y = box[1] + (box[3] - box[1] - height) / 2 - bbox[1]
    draw.text((x, y), value, font=font, fill=fill)


def _footer(
    draw: ImageDraw.ImageDraw, scene: dict[str, Any], index: int, count: int
) -> None:
    _rounded(draw, (54, 1508, 1026, 1792), "#0B1722", 34, COLORS["stroke"])
    _text(draw, (88, 1548), "旁白 / 字幕", 21, COLORS["cyan"], bold=True)
    _text(draw, (88, 1592), scene["narration"], 35, bold=True, max_width=900, spacing=12)
    draw.rounded_rectangle((54, 1853, 1026, 1867), radius=7, fill="#233748")
    progress = 54 + int(972 * index / count)
    draw.rounded_rectangle((54, 1853, progress, 1867), radius=7, fill=COLORS["cyan"])
    _text(draw, (54, 1884), "功能模拟 · 非真实平台执行录屏", 20, COLORS["muted"])


def _bullet_panel(draw: ImageDraw.ImageDraw, bullets: list[str], y: int = 1135) -> None:
    _rounded(draw, (92, y, 988, y + 290), COLORS["panel"], 30, COLORS["stroke"])
    for item_index, item in enumerate(bullets):
        row_y = y + 38 + item_index * 78
        draw.ellipse((130, row_y + 7, 151, row_y + 28), fill=COLORS["cyan"])
        _text(draw, (174, row_y), item, 31, bold=item_index == 0, max_width=760)


def _draw_hook(draw: ImageDraw.ImageDraw, scene: dict[str, Any], metrics: dict[str, int]):
    center = (540, 730)
    draw.ellipse((356, 546, 724, 914), fill="#102E3A", outline=COLORS["cyan"], width=5)
    draw.ellipse((410, 600, 670, 860), fill="#183B4A", outline="#62FFF0", width=2)
    _centered(draw, 685, "AI", 92, COLORS["text"], True)
    _centered(draw, 790, "桌面大脑", 28, COLORS["cyan"], True)
    channels = [
        ("千牛", 105, 455, COLORS["blue"]),
        ("抖店", 745, 455, COLORS["orange"]),
        ("微信", 78, 900, COLORS["green"]),
        ("企业微信", 385, 1000, COLORS["blue"]),
        ("QQ", 790, 900, COLORS["purple"]),
    ]
    for label, x, y, color in channels:
        box = (x, y, x + (230 if label == "企业微信" else 180), y + 82)
        draw.line((center[0], center[1], (box[0] + box[2]) // 2, y + 41), fill="#34566B", width=4)
        _rounded(draw, box, COLORS["panel_alt"], 24, color, 3)
        _centered_in_box(draw, box, label, 31, color, True)
    _text(draw, (92, 1210), f"本次模拟已完成 {metrics['completed']} / {metrics['total']} 条核心流程", 31, COLORS["cyan"], True)
    _bullet_panel(draw, scene["bullets"], 1248)


def _desktop_window(draw: ImageDraw.ImageDraw, title: str):
    _rounded(draw, (72, 390, 1008, 1120), "#0D1924", 32, COLORS["stroke"], 3)
    draw.rounded_rectangle((72, 390, 1008, 478), radius=32, fill="#152536")
    draw.rectangle((72, 438, 1008, 478), fill="#152536")
    for index, color in enumerate((COLORS["red"], COLORS["orange"], COLORS["green"])):
        draw.ellipse((110 + index * 38, 420, 128 + index * 38, 438), fill=color)
    _text(draw, (244, 411), title, 26, COLORS["muted"], bold=True)


def _draw_inbound(draw: ImageDraw.ImageDraw, scene: dict[str, Any], metrics: dict[str, int]):
    _desktop_window(draw, "Hermes · AI 员工作台")
    _rounded(draw, (112, 520, 708, 686), COLORS["panel_alt"], 25, COLORS["blue"])
    _text(draw, (142, 546), "千牛 · 新咨询", 25, COLORS["blue"], True)
    _text(draw, (142, 592), "AIShop 测试客户：我的订单发出了吗？", 31, bold=True, max_width=520)
    _rounded(draw, (742, 520, 958, 686), "#102B25", 25, COLORS["green"])
    _centered_in_box(draw, (742, 520, 958, 590), "已接管", 28, COLORS["green"], True)
    _centered_in_box(draw, (742, 596, 958, 658), "0.8 秒", 26, COLORS["text"], True)
    cards = [
        ("客户", "AIShop 测试客户"),
        ("订单", "DEMO-QN-1001"),
        ("意图", "物流进度咨询"),
    ]
    for index, (label, value) in enumerate(cards):
        y = 748 + index * 104
        _rounded(draw, (112, y, 958, y + 78), COLORS["panel"], 20, COLORS["stroke"])
        _text(draw, (142, y + 20), label, 24, COLORS["muted"], bold=True)
        _text(draw, (308, y + 17), value, 29, bold=True)
    _bullet_panel(draw, scene["bullets"])


def _draw_planning(draw: ImageDraw.ImageDraw, scene: dict[str, Any], metrics: dict[str, int]):
    nodes = [
        ("识别意图", "物流咨询", COLORS["blue"]),
        ("检索知识", "命中 3 条", COLORS["purple"]),
        ("风险判断", "低风险", COLORS["green"]),
        ("生成计划", "App Skill v1", COLORS["cyan"]),
    ]
    for index, (title, value, color) in enumerate(nodes):
        y = 408 + index * 166
        if index:
            draw.line((540, y - 54, 540, y - 12), fill="#42657A", width=5)
            draw.polygon(((530, y - 22), (550, y - 22), (540, y - 8)), fill="#42657A")
        _rounded(draw, (174, y, 906, y + 112), COLORS["panel"], 28, color, 3)
        draw.ellipse((214, y + 35, 254, y + 75), fill=color)
        _text(draw, (286, y + 22), title, 27, COLORS["muted"], bold=True)
        _text(draw, (286, y + 60), value, 31, bold=True)
        _rounded(draw, (748, y + 34, 858, y + 78), "#102B25", 18)
        _centered_in_box(draw, (748, y + 34, 858, y + 78), "完成", 20, COLORS["green"], True)
    _bullet_panel(draw, scene["bullets"])


def _phone_frame(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str):
    _rounded(draw, box, "#050A0F", 48, "#607588", 4)
    x1, y1, x2, y2 = box
    _rounded(draw, (x1 + 17, y1 + 17, x2 - 17, y2 - 17), "#F1F5F7", 36)
    draw.rounded_rectangle(((x1 + x2) // 2 - 52, y1 + 28, (x1 + x2) // 2 + 52, y1 + 41), 7, fill="#1E2B35")
    _text(draw, (x1 + 45, y1 + 72), label, 25, "#152534", True)
    return (x1 + 32, y1 + 124, x2 - 32, y2 - 46)


def _draw_phone(draw: ImageDraw.ImageDraw, scene: dict[str, Any], metrics: dict[str, int]):
    screen = _phone_frame(draw, (120, 382, 650, 1128), "千牛 · 测试会话")
    x1, y1, x2, _ = screen
    _rounded(draw, (x1, y1, x2 - 90, y1 + 94), "#DCE6EC", 22)
    _text(draw, (x1 + 24, y1 + 20), "我的测试订单发出了吗？", 24, "#1F3443", max_width=350)
    _rounded(draw, (x1 + 74, y1 + 132, x2, y1 + 302), "#C8F6E6", 22)
    _text(draw, (x1 + 98, y1 + 155), "已发出，物流单号为\nSF-DEMO-001。", 24, "#143529", bold=True)
    _rounded(draw, (x1 + 74, y1 + 338, x2, y1 + 405), "#179C72", 20)
    _centered_in_box(draw, (x1 + 74, y1 + 338, x2, y1 + 405), "回复已验证", 23, "#FFFFFF", True)
    steps = [("01", "打开 App"), ("02", "定位会话"), ("03", "输入回复"), ("04", "验证结果")]
    for index, (number, value) in enumerate(steps):
        y = 438 + index * 138
        color = COLORS["green"] if index < 4 else COLORS["muted"]
        draw.ellipse((720, y, 774, y + 54), fill=color)
        _centered_in_box(draw, (720, y, 774, y + 54), number, 19, "#071019", True)
        _text(draw, (804, y + 7), value, 29, bold=True)
        _text(draw, (804, y + 50), "SUCCEEDED", 20, color, bold=True)
    _bullet_panel(draw, scene["bullets"])


def _draw_approval(draw: ImageDraw.ImageDraw, scene: dict[str, Any], metrics: dict[str, int]):
    screen = _phone_frame(draw, (88, 406, 520, 1085), "抖店 · 售后")
    x1, y1, x2, _ = screen
    _rounded(draw, (x1, y1, x2, y1 + 120), "#FFE7D0", 20)
    _text(draw, (x1 + 20, y1 + 18), "客户申请退货", 24, "#68401E", True)
    _text(draw, (x1 + 20, y1 + 62), "DEMO-DD-2001", 21, "#8A684A")
    _rounded(draw, (x1, y1 + 160, x2, y1 + 360), "#E8EEF2", 20)
    _text(draw, (x1 + 20, y1 + 184), "AI 已生成售后答复，\n实际退货动作等待审批。", 23, "#243846", max_width=320)
    _rounded(draw, (564, 426, 984, 1028), "#251B12", 32, COLORS["orange"], 4)
    _text(draw, (610, 470), "需要操作员审批", 31, COLORS["orange"], True)
    details = [
        ("动作", "创建退货申请"),
        ("目标", "DEMO-DD-2001"),
        ("有效期", "5 分钟"),
        ("范围", "仅本次任务"),
    ]
    for index, (label, value) in enumerate(details):
        y = 560 + index * 88
        _text(draw, (610, y), label, 22, "#BE9A72", True)
        _text(draw, (728, y - 3), value, 25, COLORS["text"], True)
    _rounded(draw, (610, 912, 938, 976), "#4D351C", 20, COLORS["orange"])
    _centered_in_box(draw, (610, 912, 938, 976), "等待人工确认", 24, COLORS["orange"], True)
    _bullet_panel(draw, scene["bullets"])


def _mini_phone(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, app: str, color: str):
    _rounded(draw, (x, y, x + 250, y + 430), "#091019", 35, "#536C7F", 3)
    _rounded(draw, (x + 14, y + 14, x + 236, y + 416), "#EAF0F3", 27)
    draw.ellipse((x + 93, y + 72, x + 157, y + 136), fill=color)
    _centered_in_box(draw, (x + 65, y + 156, x + 185, y + 200), app, 22, "#1D303D", True)
    _centered_in_box(draw, (x + 38, y + 230, x + 212, y + 278), label, 20, "#60717C", True)
    _rounded(draw, (x + 38, y + 314, x + 212, y + 368), "#D7F5E8", 18)
    _centered_in_box(draw, (x + 38, y + 314, x + 212, y + 368), "执行中", 21, "#187255", True)


def _draw_orchestration(
    draw: ImageDraw.ImageDraw, scene: dict[str, Any], metrics: dict[str, int]
):
    _rounded(draw, (360, 382, 720, 528), "#142C38", 36, COLORS["cyan"], 4)
    _centered_in_box(draw, (360, 396, 720, 460), "HERMES", 34, COLORS["text"], True)
    _centered_in_box(draw, (360, 458, 720, 512), "并行任务编排", 23, COLORS["cyan"], True)
    devices = [
        (76, "员工 09", "千牛", COLORS["blue"]),
        (415, "员工 12", "抖店", COLORS["orange"]),
        (754, "协调员", "企微", COLORS["purple"]),
    ]
    for x, label, app, color in devices:
        draw.line((540, 528, x + 125, 652), fill="#365A70", width=5)
        _mini_phone(draw, x, 652, label, app, color)
    _bullet_panel(draw, scene["bullets"])


def _draw_channels(draw: ImageDraw.ImageDraw, scene: dict[str, Any], metrics: dict[str, int]):
    channels = [
        ("千牛", "已接入", COLORS["blue"]),
        ("抖店", "已接入", COLORS["orange"]),
        ("微信", "已接入", COLORS["green"]),
        ("企业微信", "已接入", COLORS["blue"]),
        ("QQ", "已接入", COLORS["purple"]),
    ]
    positions = [(86, 414), (554, 414), (86, 642), (554, 642), (320, 870)]
    for (label, status, color), (x, y) in zip(channels, positions, strict=True):
        _rounded(draw, (x, y, x + 440, y + 176), COLORS["panel"], 28, color, 3)
        draw.ellipse((x + 34, y + 42, x + 92, y + 100), fill=color)
        _text(draw, (x + 122, y + 34), label, 31, bold=True)
        _text(draw, (x + 122, y + 88), status, 22, COLORS["green"], bold=True)
    _rounded(draw, (154, 1084, 926, 1160), "#2C1719", 22, COLORS["red"])
    _centered_in_box(draw, (154, 1084, 926, 1160), "验证码 / 登录失效 / 未知页面 → 人工接管", 25, COLORS["red"], True)
    _bullet_panel(draw, scene["bullets"], 1200)


def _draw_audit(draw: ImageDraw.ImageDraw, scene: dict[str, Any], metrics: dict[str, int]):
    states = [
        ("EXECUTING", "手机员工执行语义动作", COLORS["blue"]),
        ("VERIFYING", "核对页面与必需证据", COLORS["purple"]),
        ("SUCCEEDED", "验证后完成任务", COLORS["green"]),
    ]
    for index, (state, description, color) in enumerate(states):
        y = 414 + index * 190
        if index:
            draw.line((150, y - 84, 150, y - 20), fill="#42657A", width=6)
        draw.ellipse((116, y, 184, y + 68), fill=color)
        _rounded(draw, (224, y - 12, 966, y + 110), COLORS["panel"], 26, COLORS["stroke"])
        _text(draw, (266, y + 8), state, 28, color, True)
        _text(draw, (266, y + 54), description, 25, COLORS["muted"])
    _rounded(draw, (116, 1020, 966, 1190), "#0D202A", 28, COLORS["cyan"])
    _text(draw, (160, 1050), "证据摘要", 24, COLORS["cyan"], True)
    _text(draw, (160, 1096), "SHA-256  8f3a…d12c", 27, bold=True)
    _text(
        draw,
        (160, 1140),
        f"模拟流程 {metrics['completed']} 条 · 步骤 {metrics.get('steps', 0)} 个",
        22,
        COLORS["muted"],
    )
    _bullet_panel(draw, scene["bullets"], 1220)


def _draw_closing(draw: ImageDraw.ImageDraw, scene: dict[str, Any], metrics: dict[str, int]):
    draw.ellipse((336, 380, 744, 788), fill="#102E3A", outline=COLORS["cyan"], width=5)
    _centered(draw, 486, "AIShop", 74, COLORS["text"], True)
    _centered(draw, 592, "HERMES", 38, COLORS["cyan"], True)
    _centered(draw, 670, "一体化工作台", 28, COLORS["muted"], True)
    capabilities = ["自动客服", "售后协同", "多手机调度", "人工审批", "证据审计", "人工接管"]
    for index, label in enumerate(capabilities):
        column = index % 2
        row = index // 2
        x = 92 + column * 462
        y = 880 + row * 116
        _rounded(draw, (x, y, x + 430, y + 82), COLORS["panel"], 22, COLORS["stroke"])
        draw.ellipse((x + 28, y + 29, x + 52, y + 53), fill=COLORS["cyan"])
        _text(draw, (x + 78, y + 19), label, 29, bold=True)
    _bullet_panel(draw, scene["bullets"], 1230)


VISUAL_RENDERERS: dict[str, Callable[[ImageDraw.ImageDraw, dict[str, Any], dict[str, int]], None]] = {
    "hook": _draw_hook,
    "inbound": _draw_inbound,
    "planning": _draw_planning,
    "phone": _draw_phone,
    "approval": _draw_approval,
    "orchestration": _draw_orchestration,
    "channels": _draw_channels,
    "audit": _draw_audit,
    "closing": _draw_closing,
}


def validate_simulation_results(results: list[dict[str, Any]]) -> dict[str, int]:
    if not results:
        raise ValueError("simulation returned no results")
    if any(result.get("mode") != "SIMULATED" for result in results):
        raise ValueError("video data must contain SIMULATED results only")
    completed = sum(result.get("task", {}).get("state") == "SUCCEEDED" for result in results)
    if completed != len(results):
        raise ValueError("every simulated flow must complete successfully")
    steps = sum(len(result.get("job", {}).get("steps", [])) for result in results)
    return {"completed": completed, "total": len(results), "steps": steps}


def capture_simulation(output_path: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    with tempfile.TemporaryDirectory(prefix="aishop-video-") as data_dir:
        command = [
            str(ROOT / ".venv" / "bin" / "python"),
            str(ROOT / "scripts" / "run-demo.py"),
            "--flow",
            "all",
            "--mode",
            "simulated",
            "--data-dir",
            data_dir,
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    results = json.loads(completed.stdout)
    metrics = validate_simulation_results(results)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results, metrics


def _srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def write_srt(scenes: list[dict[str, Any]], path: Path) -> Path:
    offset = 0.0
    blocks = []
    for index, scene in enumerate(scenes, start=1):
        end = offset + float(scene["duration"])
        blocks.append(
            f"{index}\n{_srt_time(offset)} --> {_srt_time(end)}\n"
            f"{scene['narration']}\n[SIMULATED 模拟演示]\n"
        )
        offset = end
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def render_scene(scene: dict[str, Any], metrics: dict[str, int], output_path: Path) -> Path:
    storyboard = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
    scenes = storyboard["scenes"]
    index = next(i for i, item in enumerate(scenes, start=1) if item["id"] == scene["id"])
    image = _gradient(storyboard["width"], storyboard["height"])
    draw = ImageDraw.Draw(image)
    _header(draw, scene, index, len(scenes))
    VISUAL_RENDERERS[scene["visual"]](draw, scene, metrics)
    _footer(draw, scene, index, len(scenes))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return output_path


def render_cover(scene: dict[str, Any], metrics: dict[str, int], output_path: Path) -> Path:
    image = _gradient(1080, 1920)
    draw = ImageDraw.Draw(image)
    _rounded(draw, (70, 80, 352, 144), "#1F1A12", 24, COLORS["orange"])
    _centered_in_box(draw, (70, 80, 352, 144), "SIMULATED", 24, COLORS["orange"], True)
    _text(draw, (70, 250), "一个 AI 大脑", 74, COLORS["text"], True, 940)
    _text(draw, (70, 350), "调度五个平台", 74, COLORS["cyan"], True, 940)
    _draw_hook(draw, scene, metrics)
    _rounded(draw, (70, 1670, 1010, 1790), "#0B1722", 30, COLORS["stroke"])
    _centered_in_box(draw, (70, 1670, 1010, 1790), "AIShop · Hermes 功能模拟演示", 34, COLORS["text"], True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG", optimize=True)
    return output_path


def load_storyboard() -> dict[str, Any]:
    storyboard = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
    unknown_visuals = {scene["visual"] for scene in storyboard["scenes"]} - set(
        VISUAL_RENDERERS
    )
    if unknown_visuals:
        raise ValueError(f"unknown visual renderers: {sorted(unknown_visuals)}")
    return storyboard


def render_assets(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    storyboard = load_storyboard()
    _, metrics = capture_simulation(output_dir / "demo-data.json")
    scenes_dir = output_dir / "scenes"
    for scene in storyboard["scenes"]:
        render_scene(scene, metrics, scenes_dir / f"{scene['id']}.png")
    write_srt(storyboard["scenes"], output_dir / "subtitles.srt")
    narration = "\n\n".join(
        f"{index}. {scene['title']}\n{scene['narration']}"
        for index, scene in enumerate(storyboard["scenes"], start=1)
    )
    (output_dir / "narration.txt").write_text(narration + "\n", encoding="utf-8")
    render_cover(storyboard["scenes"][0], metrics, output_dir / "cover.png")
    return {
        "cover": output_dir / "cover.png",
        "subtitles": output_dir / "subtitles.srt",
        "narration": output_dir / "narration.txt",
        "data": output_dir / "demo-data.json",
        "scenes": scenes_dir,
    }


def probe_video(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _audio_duration(path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(completed.stdout.strip())


def _render_voice(scene: dict[str, Any], path: Path) -> bool:
    say = shutil.which("say")
    duration = float(scene["duration"])
    if say:
        rate = 340
        for _ in range(2):
            subprocess.run(
                [
                    say,
                    "-v",
                    "Tingting",
                    "-r",
                    str(rate),
                    "-o",
                    str(path),
                    scene["narration"],
                ],
                check=True,
                capture_output=True,
            )
            actual = _audio_duration(path)
            if actual <= duration - 0.25:
                return True
            rate = min(500, math.ceil(rate * actual / (duration - 0.25) * 1.03))
        return True
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            str(duration),
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return False


def _render_segment(
    scene: dict[str, Any], scene_image: Path, voice_path: Path, output_path: Path
) -> None:
    duration = float(scene["duration"])
    fade_out = max(duration - 0.28, 0)
    video_filter = (
        "[0:v]scale=1080:1920,"
        "zoompan=z='min(zoom+0.00010,1.025)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920:fps=30,"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out}:d=0.28,"
        "format=yuv420p[v]"
    )
    audio_filter = (
        f"[1:a]aresample=48000,apad=pad_dur={duration},atrim=0:{duration},"
        f"afade=t=in:st=0:d=0.12,afade=t=out:st={fade_out}:d=0.2[voice];"
        f"[2:a]volume=0.045,adelay=180|180,apad=pad_dur={duration},"
        f"atrim=0:{duration}[tone];"
        "[voice][tone]amix=inputs=2:duration=longest:normalize=0[a]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(scene_image),
            "-i",
            str(voice_path),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=0.12:sample_rate=48000",
            "-filter_complex",
            video_filter + ";" + audio_filter,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            str(duration),
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def _write_checksums(output_dir: Path, targets: list[Path]) -> Path:
    lines = []
    for path in sorted(targets, key=lambda item: item.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    manifest = output_dir / "SHA256SUMS"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def verify_checksums(output_dir: Path) -> None:
    manifest = output_dir / "SHA256SUMS"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, filename = line.split("  ", maxsplit=1)
        path = output_dir / filename
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"checksum mismatch for {filename}")


def assemble_video(storyboard: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    video_path = output_dir / "AIShop-Hermes-simulated-demo.mp4"
    used_local_voice = True
    with tempfile.TemporaryDirectory(prefix="aishop-video-render-") as work_dir_value:
        work_dir = Path(work_dir_value)
        segments = []
        for index, scene in enumerate(storyboard["scenes"]):
            voice = work_dir / f"voice-{index:02d}.aiff"
            used_local_voice = _render_voice(scene, voice) and used_local_voice
            segment = work_dir / f"segment-{index:02d}.mp4"
            _render_segment(
                scene,
                output_dir / "scenes" / f"{scene['id']}.png",
                voice,
                segment,
            )
            segments.append(segment)
        concat_file = work_dir / "segments.txt"
        concat_file.write_text(
            "\n".join(f"file '{segment}'" for segment in segments) + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(video_path),
            ],
            check=True,
            capture_output=True,
        )
    targets = [
        video_path,
        output_dir / "cover.png",
        output_dir / "subtitles.srt",
        output_dir / "narration.txt",
        output_dir / "demo-data.json",
    ]
    checksum_path = _write_checksums(output_dir, targets)
    verify_checksums(output_dir)
    return {
        "video": video_path,
        "checksums": checksum_path,
        "voice": "Tingting" if used_local_voice else "silent-fallback",
        "probe": probe_video(video_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the AIShop simulated demo video")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--assets-only", action="store_true")
    arguments = parser.parse_args()
    assets = render_assets(arguments.output_dir.resolve())
    result: dict[str, Any] = {key: str(value) for key, value in assets.items()}
    if not arguments.assets_only:
        assembled = assemble_video(load_storyboard(), arguments.output_dir.resolve())
        result.update(
            {
                "video": str(assembled["video"]),
                "checksums": str(assembled["checksums"]),
                "voice": assembled["voice"],
                "duration": assembled["probe"]["format"]["duration"],
            }
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

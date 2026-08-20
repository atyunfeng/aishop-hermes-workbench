import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STORYBOARD_PATH = ROOT / "demo-video" / "storyboard.json"
RENDERER_PATH = ROOT / "scripts" / "render-demo-video.py"
VIDEO_OUTPUT = ROOT / "artifacts" / "demo-video"


def load_storyboard():
    return json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))


def load_renderer():
    spec = importlib.util.spec_from_file_location("aishop_demo_video", RENDERER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_storyboard_contract_and_duration():
    storyboard = load_storyboard()
    assert (storyboard["width"], storyboard["height"], storyboard["fps"]) == (
        1080,
        1920,
        30,
    )
    scenes = storyboard["scenes"]
    assert len(scenes) == 9
    assert len({scene["id"] for scene in scenes}) == len(scenes)
    assert 60 <= sum(scene["duration"] for scene in scenes) <= 85
    for scene in scenes:
        assert set(scene) == {
            "id",
            "duration",
            "title",
            "narration",
            "visual",
            "bullets",
        }
        visible_copy = json.dumps(scene, ensure_ascii=False)
        assert "SIMULATED" in visible_copy or "模拟" in visible_copy


def test_storyboard_covers_required_capabilities():
    storyboard = load_storyboard()
    content = json.dumps(storyboard, ensure_ascii=False)
    for label in ("千牛", "抖店", "微信", "企业微信", "QQ", "审批", "证据", "人工接管"):
        assert label in content


def test_renderer_rejects_non_simulated_results():
    renderer = load_renderer()
    valid = [{"flow_id": "one", "mode": "SIMULATED", "task": {"state": "SUCCEEDED"}}]
    metrics = renderer.validate_simulation_results(valid)
    assert metrics["completed"] == 1
    with pytest.raises(ValueError, match="SIMULATED"):
        renderer.validate_simulation_results(
            [{"flow_id": "one", "mode": "DEVICE", "task": {"state": "SUCCEEDED"}}]
        )


def test_srt_timestamps_are_monotonic(tmp_path):
    renderer = load_renderer()
    scenes = load_storyboard()["scenes"][:2]
    output = renderer.write_srt(scenes, tmp_path / "subtitles.srt")
    content = output.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:05,000" in content
    assert "00:00:05,000 --> 00:00:12,000" in content


def test_every_visual_type_renders_full_size_scene(tmp_path):
    renderer = load_renderer()
    storyboard = load_storyboard()
    visual_types = {scene["visual"] for scene in storyboard["scenes"]}
    assert visual_types == set(renderer.VISUAL_RENDERERS)
    for scene in storyboard["scenes"]:
        output = tmp_path / f"{scene['id']}.png"
        renderer.render_scene(scene, {"completed": 5, "total": 5}, output)
        with Image.open(output) as image:
            assert image.size == (1080, 1920)


def test_video_assembly_interface_exists():
    renderer = load_renderer()
    assert callable(renderer.assemble_video)
    assert callable(renderer.probe_video)


@pytest.mark.skipif(
    not (VIDEO_OUTPUT / "AIShop-Hermes-simulated-demo.mp4").exists(),
    reason="full rendered artifact is verified after video generation",
)
def test_rendered_video_artifacts_and_checksums():
    renderer = load_renderer()
    expected = {
        "AIShop-Hermes-simulated-demo.mp4",
        "cover.png",
        "subtitles.srt",
        "narration.txt",
        "demo-data.json",
        "SHA256SUMS",
    }
    assert expected.issubset({path.name for path in VIDEO_OUTPUT.iterdir()})
    probe = renderer.probe_video(VIDEO_OUTPUT / "AIShop-Hermes-simulated-demo.mp4")
    video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in probe["streams"] if stream["codec_type"] == "audio")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert video["codec_name"] == "h264"
    assert video["pix_fmt"] == "yuv420p"
    assert video["r_frame_rate"] == "30/1"
    assert audio["codec_name"] == "aac"
    assert 60 <= float(probe["format"]["duration"]) <= 85
    renderer.verify_checksums(VIDEO_OUTPUT)

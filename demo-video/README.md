# AIShop 模拟功能演示视频

该目录保存竖屏演示视频的分镜配置。成片由仓库现有模拟工作流数据驱动，始终标注 `SIMULATED / 模拟演示`，不能替代 Windows、Hermes Desktop、Android 真机及真实平台账号验收。

## 生成

环境要求：Python 3.11、Pillow 12、FFmpeg/ffprobe。macOS 会使用本地 `Tingting` 中文语音；其他环境没有兼容语音时生成器会保留音轨、字幕和提示音，但旁白降级为静音。

```bash
uv pip install --python .venv/bin/python 'pillow>=12,<13'
.venv/bin/python scripts/render-demo-video.py
```

只生成场景图、封面、字幕和模拟数据：

```bash
.venv/bin/python scripts/render-demo-video.py --assets-only
```

## 输出

默认输出目录为 `artifacts/demo-video/`：

- `AIShop-Hermes-simulated-demo.mp4`：1080×1920、30 fps、H.264/AAC 成片。
- `cover.png`：竖屏封面。
- `subtitles.srt`：独立字幕文件。
- `narration.txt`：中文旁白稿。
- `demo-data.json`：本次隔离模拟运行结果。
- `SHA256SUMS`：上述交付文件的 SHA-256。

## 验证

```bash
.venv/bin/python -m pytest tests/test_demo_video.py -q
ffprobe -v error -show_streams -show_format \
  artifacts/demo-video/AIShop-Hermes-simulated-demo.mp4
(cd artifacts/demo-video && shasum -a 256 -c SHA256SUMS)
```

渲染器会拒绝 `DEVICE` 数据、失败的模拟任务和未知视觉类型。每次正式交付前应抽取开场、执行、审批、多渠道和片尾画面，确认中文字形、字幕安全区、常驻模拟标识和状态颜色。

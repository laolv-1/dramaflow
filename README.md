# DramaFlow

> AI-powered short drama automation pipeline. From script to screen in one click.

A lightweight, Manifest-driven CLI tool for automating AI-generated short drama production. Inspired by [AI-CanvasPro](https://github.com/ashuoAI/AI-CanvasPro), but simplified for personal use and learning.

## Features

- **Manifest-driven architecture**: Define AI models in JSON, add new providers without code changes
- **Adapter pattern**: Unified interface for multiple AI providers (image/video/audio)
- **Linear pipeline**: Script → Images → Videos → Audio → Synthesis
- **Vertical video support**: 1080x1920 (9:16) optimized for TikTok/Reels/Shorts
- **Free-first stack**: Edge TTS (free) + agnes-ai API + FFmpeg
- **Virtual path abstraction**: Solves FFmpeg path resolution issues
- **Atomic file naming**: `gen_YYYYMMDD_NNNN.mp4` format prevents filename collisions
- **Dry-run mode**: Preview your pipeline before spending API credits

## Architecture

```
script/episode.json
    │
    ▼
manifests/          ← AI model registry (JSON definitions)
    │
    ▼
adapters/           ← Provider adapters (agnes-ai, free alternatives...)
    │
    ▼
pipeline/           ← Linear execution: text → image → video → audio → synthesize
    │
    ▼
output/             ← gen_YYYYMMDD_NNNN.mp4 (auto-numbered, no collisions)
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
pip install python-dotenv  # for .env file support
```

### 2. Configure API Key

```bash
# Copy the example and add your key
cp .env.example .env

# Edit .env with your AGNES_API_KEY
```

Or set as environment variable:
```bash
export AGNES_API_KEY="your-key-here"
```

### 3. Run

```bash
# Preview mode (no API calls)
python main.py episode 2 --dry-run

# Full pipeline execution
python main.py episode 2

# Skip specific steps
python main.py episode 2 --skip-image --skip-video
```

### 4. Custom episode data

Replace the sample `get_sample_episode_info()` in `main.py` with your own episode JSON, or load from a file:

```python
# Load from JSON file
from pipeline.step_text import load_episode_from_file
parser = load_episode_from_file("episode_2.json")
episode_info = parser.info
```

## Project Structure

```
DramaFlow/
├── main.py                  # CLI entry point
├── config.example.yaml      # Configuration template
├── manifests/               # AI model registry
│   ├── image_models.json    # Image generation models
│   ├── video_models.json    # Video generation models
│   └── audio_models.json    # Audio/TTS models
├── adapters/
│   ├── base.py              # Abstract adapter interface
│   └── agnes_ai.py          # Agnes AI provider adapter
├── pipeline/
│   ├── step_text.py         # Episode data parsing
│   ├── step_image.py        # Character & scene image generation
│   ├── step_video.py        # Image-to-video generation
│   ├── step_audio.py        # TTS audio generation
│   └── step_synthesize.py   # FFmpeg video synthesis
├── media/
│   ├── processor.py         # FFmpeg/Pillow wrappers
│   └── utils.py             # Virtual paths, file naming, dedup
└── tests/
```

## Supported AI Providers

| Category | Current | Planned |
|----------|---------|---------|
| Image | Agnes AI (agnes-image-2.1-flash) | Free alternatives |
| Video | Agnes AI (agnes-video-v2.0) | Free alternatives |
| Audio | Microsoft Edge TTS (free) | - |
| Synthesis | FFmpeg 8.x | - |

## Technical Debt / TODO

- [ ] FFmpeg subtitle addition (path resolution fix needed)
- [ ] Vertical video blur-expand (currently black-bar fill)
- [ ] Scene transition effects (fade in/out)
- [ ] Parallel execution (currently serial)
- [ ] Retry mechanism for API failures
- [ ] Load episode data from external JSON/YAML file

## Inspired By

- [AI-CanvasPro](https://github.com/ashuoAI/AI-CanvasPro) — Node-based AI canvas editor (1078 stars)
  - Learned: Manifest registration system, adapter pattern, virtual path abstraction, atomic writes

## License

MIT License — for personal use and learning. Not for commercial purposes.

## Stack

- Python 3.10+
- httpx / aiohttp
- edge-tts
- FFmpeg 8.x
- Pillow
- PyYAML

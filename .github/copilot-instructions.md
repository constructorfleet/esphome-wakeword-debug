# Copilot Instructions for ESPHome Wake Word Debug Pipeline

## Repository Overview

This repository provides a comprehensive audio capture and processing pipeline for wake word debugging. It consists of:

- **ESPHome Configuration** (`esphome/`): Captures I2S microphone audio and streams base64-encoded PCM chunks over MQTT
- **Python FastAPI Ingest Service** (`ingest_service/`): Buffers audio, extracts clips around wake events, writes WAV files, and publishes MQTT events
- **TypeScript Web UI** (`ingest_service/web_ui/`): Frontend for reviewing audio clips
- **Docker Compose Setup**: MQTT broker (Mosquitto) and ingest service orchestration

**Key Technologies**: Python 3.11, FastAPI, MQTT, ESPHome, Docker, TypeScript, Node.js 20

## Build and Test Instructions

### Python Service

**Install dependencies:**
```bash
pip install -r ingest_service/requirements.txt
```

**Run tests:**
```bash
# From repository root
PYTHONPATH=. python -m pytest tests/ -v

# With coverage
pytest tests/ --cov=ingest_service --cov-report=html
```

**Important Notes:**
- Always run pytest from the repository root with `PYTHONPATH=.` to ensure proper module resolution
- The `pytest.ini` file configures `pythonpath = .` and `asyncio_mode = auto`
- Tests are located in `tests/` directory with structure mirroring `ingest_service/`

### Web UI (TypeScript/Node.js)

**Location:** `ingest_service/web_ui/`

**Install dependencies:**
```bash
cd ingest_service/web_ui
npm ci  # Use 'ci' for reproducible builds, not 'install'
```

**Quality checks (run in order):**
```bash
npm run typecheck  # TypeScript type checking
npm run lint       # ESLint
npm run format:check  # Prettier format check
```

**Development:**
```bash
npm run dev   # Watch mode for development
npm run build # Production build (outputs to ../app/static/)
```

**Important Notes:**
- Always use `npm ci` instead of `npm install` for consistent dependency versions
- The build output goes to `ingest_service/app/static/` directory
- Run all three quality checks (typecheck, lint, format:check) before committing

### Full Validation

**Quick validation script:**
```bash
chmod +x validate.sh
./validate.sh
```

This script:
1. Checks Python dependencies
2. Runs unit tests
3. Validates Docker Compose config
4. Verifies project structure and key files

### Docker

**Build and run:**
```bash
docker compose up -d
docker compose ps
curl http://localhost:8000/health
```

**Important Notes:**
- The Docker image is built from `ingest_service/Dockerfile`
- MQTT broker runs on port 1883
- FastAPI service runs on port 8000

## Project Structure

### Key Directories

```
esphome-wakeword-debug/
├── .github/
│   └── workflows/
│       ├── pr.yml           # PR validation workflow
│       └── release.yml      # Release workflow
├── esphome/
│   └── example-config.yaml  # ESPHome device configuration template
├── ingest_service/
│   ├── app/
│   │   ├── main.py          # FastAPI application entry point
│   │   ├── config.py        # Configuration management
│   │   ├── audio_buffer.py  # Audio buffering logic
│   │   ├── wav_writer.py    # WAV file generation
│   │   └── mqtt_publisher.py # MQTT integration
│   ├── web_ui/              # TypeScript frontend
│   │   ├── src/             # TypeScript source files
│   │   ├── package.json     # Node.js dependencies
│   │   └── tsconfig.json    # TypeScript configuration
│   ├── requirements.txt     # Python dependencies
│   ├── setup.py            # Python package setup
│   └── Dockerfile          # Container image definition
├── tests/
│   └── ingest_service/     # Unit tests mirroring app structure
├── pytest.ini              # Pytest configuration
├── validate.sh             # Quick validation script
└── docker-compose.yml      # Service orchestration
```

### CI/CD Pipeline

**PR Validation** (`.github/workflows/pr.yml`):
1. **Python tests**: Installs dependencies and runs `validate.sh`
2. **Web UI quality**: Runs typecheck, lint, and format check
3. **Docker build**: Builds and pushes image to GitHub Container Registry

**All three jobs must pass** for a PR to be merged.

## Architecture and Dependencies

### Multi-Assistant Support

The ingest service supports multiple assistants simultaneously:
- Each assistant has its own audio buffer
- MQTT topics use wildcard patterns: `assist/debug/+/pcm`, `assist/debug/+/events`, `assist/debug/+/audio_info`
- Audio configuration is per-assistant via retained MQTT messages

### Key Audio Configuration

Must match between ESPHome device and ingest service:
- Sample rate: 48000 Hz (configurable)
- Sample width: 4 bytes (32-bit PCM)
- Channels: 1 (mono)

### Important Files to Review

When making changes:
- **Audio processing**: `ingest_service/app/audio_buffer.py`, `ingest_service/app/wav_writer.py`
- **API endpoints**: `ingest_service/app/main.py`
- **MQTT integration**: `ingest_service/app/mqtt_publisher.py`
- **Configuration**: `ingest_service/app/config.py`, `.env.example`
- **Tests**: Files in `tests/ingest_service/` mirror the structure in `ingest_service/app/`

## Development Workflow

1. **Setup**: Install Python and Node.js dependencies
2. **Make changes**: Edit code in appropriate directories
3. **Test**: Run pytest for Python, npm scripts for TypeScript
4. **Validate**: Run `./validate.sh` for quick validation
5. **Format**: Use `npm run format` for TypeScript files
6. **Commit**: Ensure all CI checks will pass

## Common Validation Commands

```bash
# Python tests from root
PYTHONPATH=. python -m pytest tests/ -v

# Web UI validation
cd ingest_service/web_ui
npm ci
npm run typecheck && npm run lint && npm run format:check

# Full validation
./validate.sh

# Docker validation
docker compose config
docker compose up -d
curl http://localhost:8000/health
```

## Tips for Contributors

- **Python imports**: Use `from ingest_service.app.module import ...` format in tests
- **Async tests**: pytest-asyncio is configured with `asyncio_mode = auto`
- **Type hints**: Use type hints in Python code; TypeScript must pass strict checks
- **MQTT topics**: Use wildcard pattern `+` for assistant ID in subscriptions
- **Error handling**: Log errors appropriately; MQTT failures should not crash the service
- **Testing**: Add tests for new features in `tests/ingest_service/` mirroring `ingest_service/app/` structure

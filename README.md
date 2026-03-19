# BirdNET 鸟类识别 FastAPI 后端

基于 BirdNET-Analyzer 的鸟类叫声识别 REST API 服务。

## 环境要求

- Python 3.10+
- WSL Ubuntu 22.04 (或类似 Linux 环境)

## 依赖安装

```bash
pip install fastapi uvicorn python-multipart pydantic pyarrow "numpy<2"
```

## BirdNET-Analyzer 设置

1. 克隆 BirdNET-Analyzer 仓库:
```bash
git clone --depth 1 https://github.com/kahst/BirdNET-Analyzer.git /tmp/BirdNET-Analyzer
```

2. 首次运行时会自动下载模型文件 (约 224MB)

## 运行服务

```bash
python3 main.py
```

服务将在 http://0.0.0.0:8000 启动

## API 接口

### 1. 健康检查

```bash
curl http://localhost:8000/health
```

响应:
```json
{
  "status": "healthy",
  "temp_dir": "/tmp/birdnet_audio",
  "current_week": 11
}
```

### 2. 鸟类识别分析

**端点:** `POST /analyze`

**参数 (multipart/form-data):**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| file | File | 是 | - | 音频文件 (wav, mp3, flac, ogg, m4a, wma, aac) |
| latitude | float | 否 | -1 | 纬度 (-90 到 90), -1 忽略位置筛选 |
| longitude | float | 否 | -1 | 经度 (-180 到 180), -1 忽略位置筛选 |
| week | int | 否 | 当前周 | 周数 (1-48) |
| min_conf | float | 否 | 0.25 | 最小置信度 (0.0-1.0) |
| top_n | int | 否 | 3 | 返回结果数量 (默认返回前3个不同物种) |

**简化调用 (只需音频文件):**
```bash
curl -s -X POST http://localhost:8000/analyze -F "file=@/path/to/audio.wav"
```

**完整参数调用:**
```bash
curl -s -X POST http://localhost:8000/analyze \
  -F "file=@/path/to/audio.wav" \
  -F "latitude=42.5" \
  -F "longitude=-76.45" \
  -F "week=12" \
  -F "min_conf=0.25"
```

**格式化输出 (使用 jq):**
```bash
# 安装 jq: apt install jq 或 brew install jq
curl -s -X POST http://localhost:8000/analyze -F "file=@/path/to/audio.wav" | jq .
```

**响应示例:**
```json
{
  "success": true,
  "message": "分析完成",
  "detections": [
    {
      "species": "Passer domesticus_House Sparrow",
      "scientific_name": "Passer domesticus",
      "common_name": "House Sparrow",
      "confidence": 0.5056
    }
  ],
  "location": {
    "latitude": 42.5,
    "longitude": -76.45,
    "week": 12
  },
  "audio_file": "abc12345_test.wav"
}
```

## 文件存储

- **临时音频**: `/tmp/birdnet_audio/*.mp3` (分析后自动清理)
- **CSV 结果**: `/tmp/birdnet_audio/output_xxx/*.BirdNET.results.csv` (默认保留)
- **日志输出**: 服务启动时会在控制台打印实际执行的 BirdNET 命令

## 日志说明

服务运行时会输出以下日志:
```
[BirdNET Command] python3 -m birdnet_analyzer.analyze /tmp/birdnet_audio/xxx.mp3 -o ... --lat 42.5 --lon -76.45 ...
[BirdNET Working Directory] /tmp/BirdNET-Analyzer
```

## 注意事项

1. 首次运行会自动下载 BirdNET 模型 (约 224MB)
2. 分析时间取决于音频文件长度，一般几秒到几十秒
3. 经纬度用于筛选特定地区的鸟类物种列表
4. 周数用于筛选特定季节的鸟类物种列表

## 模型位置

BirdNET 模型文件存储在:
```
/tmp/BirdNET-Analyzer/birdnet_analyzer/checkpoints/V2.4/
```

包含以下模型文件:
- `BirdNET_GLOBAL_6K_V2.4_Model_FP32.tflite` (51.7MB) - 默认使用
- `BirdNET_GLOBAL_6K_V2.4_Model_FP16.tflite` (25.9MB)
- `BirdNET_GLOBAL_6K_V2.4_Model_INT8.tflite` (41MB)
- `BirdNET_GLOBAL_6K_V2.4_Labels.txt` - 物种标签文件
"""
BirdNET 鸟类叫声识别 FastAPI 后端服务

提供 REST API 接口，接受音频文件和位置信息，返回鸟类识别结果
"""

import os
import uuid
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 创建 FastAPI 应用实例
app = FastAPI(
    title="BirdNET 鸟类识别 API",
    description="基于 BirdNET-Analyzer 的鸟类叫声识别服务",
    version="1.0.0"
)

# 添加 CORS 中间件，允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)

# 配置常量
TEMP_DIR = Path("/tmp/birdnet_audio")
TEMP_DIR.mkdir(exist_ok=True)

# BirdNET-Analyzer 路径 (根据实际情况修改)
BIRDNET_ANALYZER_PATH = "/tmp/BirdNET-Analyzer"

# 当前周数 (1-48, 4周/月)
def get_current_week() -> int:
    """获取当前周数 (1-48)"""
    now = datetime.now()
    week = (now.month - 1) * 4 + (now.day // 7) + 1
    return min(max(week, 1), 48)


class BirdDetection(BaseModel):
    """鸟类检测结果模型"""
    species: str
    scientific_name: str
    common_name: str
    confidence: float


class AnalysisResponse(BaseModel):
    """分析响应模型"""
    success: bool
    message: str
    detections: list[BirdDetection]
    location: Optional[dict] = None
    audio_file: Optional[str] = None


@app.get("/")
async def root():
    """健康检查接口"""
    return {"status": "ok", "service": "BirdNET Bird Detection API"}


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "temp_dir": str(TEMP_DIR),
        "current_week": get_current_week()
    }


def run_birdnet_analysis(
    audio_path: str,
    lat: float,
    lon: float,
    week: int,
    min_conf: float = 0.25
) -> list:
    """
    运行 BirdNET 分析

    Args:
        audio_path: 音频文件路径
        lat: 纬度
        lon: 经度
        week: 周数 (1-48)
        min_conf: 最小置信度阈值

    Returns:
        检测结果列表
    """
    # 创建临时输出目录
    output_dir = TEMP_DIR / f"output_{uuid.uuid4().hex[:8]}"
    output_dir.mkdir(exist_ok=True)

    try:
        # 构建 BirdNET 分析命令
        # 使用 csv 格式输出，方便解析
        # 需要从 BirdNET-Analyzer 目录运行
        cmd = [
            "python3", "-m", "birdnet_analyzer.analyze",
            audio_path,
            "-o", str(output_dir),
            "--lat", str(lat),
            "--lon", str(lon),
            "--week", str(week),
            "--min_conf", str(min_conf),
            "--rtype", "csv"
        ]
        
        # 设置工作目录为 BirdNET-Analyzer 路径
        cwd = BIRDNET_ANALYZER_PATH

        # 打印实际运行的命令 (用于日志)
        cmd_str = " ".join(cmd)
        print(f"[BirdNET Command] {cmd_str}")
        print(f"[BirdNET Working Directory] {cwd}")

        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
            cwd=cwd
        )

        # 检查执行结果
        if result.returncode != 0:
            print(f"BirdNET error: {result.stderr}")
            return []

        # 读取输出结果 - BirdNET 2.4 输出文件名格式为 .BirdNET.results.csv
        output_file = output_dir / f"{Path(audio_path).stem}.BirdNET.results.csv"
        if not output_file.exists():
            # 尝试旧格式
            output_file = output_dir / f"{Path(audio_path).stem}.BirdNET.csv"
        if not output_file.exists():
            return []

        # 解析 CSV 结果
        # CSV 格式: Start (s),End (s),Scientific name,Common name,Confidence,File
        detections = []
        with open(output_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if len(lines) > 1:  # 有数据行
                for line in lines[1:]:  # 跳过表头
                    parts = line.strip().split(',')
                    if len(parts) >= 5:
                        scientific_name = parts[2].strip()
                        common_name = parts[3].strip()
                        confidence_str = parts[4].strip()
                        if scientific_name and confidence_str:
                            try:
                                confidence = float(confidence_str)
                                species = f"{scientific_name}_{common_name}"
                                detections.append({
                                    "species": species,
                                    "scientific_name": scientific_name,
                                    "common_name": common_name,
                                    "confidence": confidence
                                })
                            except ValueError:
                                continue

        # 按置信度排序
        detections.sort(key=lambda x: x['confidence'], reverse=True)

        # 去重: 同一物种只保留置信度最高的那条
        unique_species = {}
        for d in detections:
            species = d['scientific_name']
            if species not in unique_species:
                unique_species[species] = d
        
        # 返回去重后的结果 (已按置信度排序)
        return list(unique_species.values())

    except subprocess.TimeoutExpired:
        print("BirdNET analysis timeout")
        return []
    except Exception as e:
        print(f"BirdNET analysis error: {e}")
        return []
    finally:
        # 默认不清理，保留 CSV 文件在 /tmp/birdnet_audio/output_xxx/
        # 如需自动清理，取消注释以下代码:
        # if output_dir.exists():
        #     import shutil
        #     try:
        #         shutil.rmtree(output_dir)
        #     except Exception:
        #         pass
        pass


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_audio(
    file: UploadFile = File(..., description="音频文件 (支持 wav, mp3, flac 等格式)"),
    latitude: Optional[float] = Form(-1, description="纬度 (-90 到 90), 默认 -1 忽略"),
    longitude: Optional[float] = Form(-1, description="经度 (-180 到 180), 默认 -1 忽略"),
    week: Optional[int] = Form(None, description="周数 (1-48), 默认当前周"),
    min_conf: Optional[float] = Form(0.25, description="最小置信度 (0.0-1.0), 默认 0.25"),
    top_n: Optional[int] = Form(3, description="返回结果数量, 默认 3")
):
    """
    分析音频文件，识别鸟类叫声

    - **file**: 音频文件 (必填)
    - **latitude**: 纬度 (可选, 默认 -1 忽略位置筛选)
    - **longitude**: 经度 (可选, 默认 -1 忽略位置筛选)
    - **week**: 周数 (可选, 默认当前周)
    - **min_conf**: 最小置信度 (可选, 默认 0.25)

    Returns:
        JSON 格式的识别结果
    """
    # 验证经纬度 (如果是有效值)
    if latitude is not None and latitude != -1 and not -90 <= latitude <= 90:
        raise HTTPException(status_code=400, detail="纬度必须在 -90 到 90 之间")
    if longitude is not None and longitude != -1 and not -180 <= longitude <= 180:
        raise HTTPException(status_code=400, detail="经度必须在 -180 到 180 之间")

    # 验证置信度
    if min_conf is not None and not 0 <= min_conf <= 1:
        raise HTTPException(status_code=400, detail="置信度必须在 0 到 1 之间")

    # 获取周数
    analysis_week = week if week else get_current_week()
    if analysis_week < 1 or analysis_week > 48:
        analysis_week = get_current_week()

    # 验证文件类型
    allowed_extensions = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.wma', '.aac'}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
            raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型。支持: {', '.join(allowed_extensions)}"
        )

    # 生成唯一文件名
    file_id = uuid.uuid4().hex[:8]
    safe_filename = f"{file_id}_{file.filename}"
    audio_path = TEMP_DIR / safe_filename

    # 保存上传的音频文件
    try:
        content = await file.read()
        with open(audio_path, "wb") as f:
            f.write(content)

        # 检查文件是否有效
        if audio_path.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

    # 运行 BirdNET 分析
    try:
        # 确保参数有默认值
        lat_val = latitude if latitude is not None else -1
        lon_val = longitude if longitude is not None else -1
        conf_val = min_conf if min_conf is not None else 0.25

        detections = run_birdnet_analysis(
            audio_path=str(audio_path),
            lat=lat_val,
            lon=lon_val,
            week=analysis_week,
            min_conf=conf_val
        )

        # 限制返回结果数量
        n_val = top_n if top_n is not None and top_n > 0 else 3
        detections = detections[:n_val]

        return AnalysisResponse(
            success=True,
            message="分析完成",
            detections=detections,
            location={
                "latitude": lat_val,
                "longitude": lon_val,
                "week": analysis_week
            },
            audio_file=safe_filename
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")

    finally:
        # 清理临时音频文件
        if audio_path.exists():
            try:
                audio_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    import uvicorn
    # 启动服务
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
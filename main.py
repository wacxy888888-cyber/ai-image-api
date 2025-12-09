# main.py - AI生图代理API（使用即梦AI官方额度查询）
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
from datetime import datetime

app = FastAPI(
    title="ArtFlow AI 生图API",
    description="基于即梦AI（api.apicore.ai）的图文生成与额度查询接口",
    version="1.0"
)

# ==================== 允许前端网页访问 ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://image8888.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# =======================================================

# ==================== 配置区 ====================
UPSTREAM_API_URL = "https://api.apicore.ai/v1/images/generations"
UPSTREAM_MODEL = "doubao-seedream-4-0-250828"

# 用户鉴权方式
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
# ==============================================

class GenerateRequest(BaseModel):
    prompt: str
    image_url: str
    size: str = "2K"

@app.post("/v1/images/generations")
async def generate_image(data: GenerateRequest, request: Request):
    # 获取用户传入的充值码（他们的 sk-xxx）
    api_key = request.headers.get("X-API-Key")
    if not api_key or not api_key.startswith("sk-"):
        raise HTTPException(status_code=403, detail="无效API Key")

    # 转发请求给即梦AI
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": UPSTREAM_MODEL,
        "prompt": data.prompt,
        "image": [data.image_url],
        "response_format": "url",
        "size": data.size,
        "stream": False,
        "watermark": False
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(UPSTREAM_API_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": "生成失败", "detail": response.text, "status": response.status_code}

@app.get("/v1/user/balance")
async def get_user_balance(request: Request):
    """查询该充值码的实际可用额度（转换为‘张’）"""
    api_key = request.headers.get("X-API-Key")
    if not api_key or not api_key.startswith("sk-"):
        raise HTTPException(status_code=400, detail="无效的充值码格式")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 获取总订阅额度
            sub_resp = await client.get(
                "https://api.apicore.ai/v1/dashboard/billing/subscription",
                headers=headers
            )
            if sub_resp.status_code != 200:
                raise HTTPException(status_code=402, detail="充值码无效或无权限")

            sub_data = sub_resp.json()
            hard_limit_usd = float(sub_data.get("hard_limit_usd", 0))  # 总额 USD

            # 获取本月已用金额
            from datetime import datetime
            now = datetime.now()
            start_date = f"{now.year}-{now.month:02d}-01"
            end_date = f"{now.year}-{now.month:02d}-28"

            usage_resp = await client.get(
                f"https://api.apicore.ai/v1/dashboard/billing/usage?start_date={start_date}&end_date={end_date}",
                headers=headers
            )

            total_usage_cents = 0
            if usage_resp.status_code == 200:
                usage_data = usage_resp.json()
                total_usage_cents = int(usage_data.get("total_usage", 0))

            used_usd = total_usage_cents / 100.0
            remaining_usd = max(hard_limit_usd - used_usd, 0)

            # 按每张图 $0.1 计算
            cost_per_image = 0.1
            total_images = int(hard_limit_usd / cost_per_image)
            used_images = int(used_usd / cost_per_image)
            remaining_images = int(remaining_usd / cost_per_image)

            return {
                "total": total_images,
                "used": used_images,
                "remaining": remaining_images,
                "currency_unit": "张"
            }
    except Exception as e:
        return {"error": "查询失败", "detail": str(e)}

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

@app.get("/")
def home():
    return {
        "message": "AI 生图 API 服务已上线！",
        "docs": "/docs",
        "status": "ok"
    }

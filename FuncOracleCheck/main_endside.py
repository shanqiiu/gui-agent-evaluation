"""
@File        : main.py
@Project     : FuncOracleCheck
@Time        : 2025/7/31 上午11:55
@Author      : Lin Dayu
@Description : 
"""
# main.py
import uvicorn
from fastapi import FastAPI
from api.server_api import server_router
from func_check import func_checker


app = FastAPI(
    title="功能检查服务",
    description="提供功能检查API接口",
    version="1.0.0"
)


app.include_router(server_router)

if __name__ == "__main__":
    # 预初始化检查器（可选，但确保服务启动时已完成初始化）
    _ = func_checker

    # 启动服务
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8011
    )

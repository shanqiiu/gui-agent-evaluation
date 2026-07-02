# api/server_api.py
from fastapi import APIRouter, HTTPException

from external_apis.logging_config import Logger
from func_check import func_checker

server_router = APIRouter()
logger = Logger()

@server_router.post("/func/oraclecheck")
async def oracle_check(test_suites: dict):
    """
    功能检查接口

    参数:
    test_suites: 测试套件JSON数据

    返回:
    {
        "status": "success" | "error",
        "result": {检查结果},
        "error": "错误信息(仅当status为error时存在)"
    }
    """
    try:
        # 调用check方法
        result = func_checker.check(test_suites)
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        import traceback
        logger.error(f"Oracle check failed: {str(e)}\n{traceback.format_exc()}")

        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "error": f"检查失败: {str(e)}"
            }
        )

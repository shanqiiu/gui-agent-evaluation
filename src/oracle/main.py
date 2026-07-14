import json
import multiprocessing
import time
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Form

from app.models import AIAssistedScenarioDeterminationModel, ActionList, BatchItem, DataInfo
from config import *
from library.logger import logger
from oracle.function_oracle import function_oracle_checker
from oracle_service import build_single_step_payload, run_sequence_payload, run_single_step
from utils.database import OBSDatabaseClient, RedisClusterClient


app = FastAPI()
redis_cluster_client = None
s3_client = OBSDatabaseClient(AK, SK, REGION_NAME, BUCKETNAME)


def _get_redis():
    """懒初始化 Redis 客户端，避免启动时强制连接 Redis。"""
    global redis_cluster_client
    if redis_cluster_client is None:
        redis_cluster_client = RedisClusterClient(
            host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD
        )
    return redis_cluster_client


@app.post("/get_oracle_check_result")
async def get_oracle_check_result(para: AIAssistedScenarioDeterminationModel):
    logger.info(f"Para: {para}")

    functional_oracle_checker = function_oracle_checker.FunctionalOracleCheckerV1(operation_data=para)
    oracle_result = functional_oracle_checker.oracle()
    return {
        "status": 200,
        "result": oracle_result["result"],
        "checkPointList": oracle_result["checkPointList"],
    }


@app.post("/upload_funcheck_task")
async def upload_funcheck_task(task_id: str = Form(...), scene_id: str = Form(...)):
    logger.info(f"提交功能检测任务，task_id:{task_id}--scene_id:{scene_id}\n")
    current_length = _get_redis().get_len_from_list(MESSAGE_QUEUE_NAME)
    logger.info(f"当前任务队列长度:{current_length}")
    if current_length >= QUEUE_LIMIT_LENGTH:
        logger.error(f"超出最大任务队列数量限制，请等待。当前长度{current_length}")
        return {"code": 400, "error": "超出最大任务队列数量限制，请等待。"}

    this_task_id = task_id + "_" + scene_id
    formatted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_name = this_task_id + ".zip"
    task_infos = {
        "task_id": this_task_id,
        "task_status": "等待",
        "task_progress": 0.0,
        "task_processing_results": {},
        "task_submit_time": formatted_time,
        "file_name": file_name,
    }

    push_status = _get_redis().push_to_list(MESSAGE_QUEUE_NAME, json.dumps(task_infos, ensure_ascii=False))
    if push_status:
        logger.info(f"{task_infos}消息队列保存成功！")
        return {"code": 200, "task_id": task_id, "scene_id": scene_id, "submit_status": True}

    logger.info(f"{task_infos}消息队列保存失败！")
    return {"code": 200, "task_id": task_id, "scene_id": scene_id, "submit_status": False}


@app.post("/get_upload_params")
async def get_upload_params(task_id: str = Form(...), scene_id: str = Form(...)):
    logger.info(f"task_id:{task_id} -- scene_id:{scene_id} 获取上传链接")
    file_name = f"{task_id}_{scene_id}.zip"
    return {"region_name": REGION_NAME, "bucket_name": BUCKETNAME, "file_name": file_name, "ak": AK, "sk": SK}


@app.post("/get_check_result")
async def check_result(task_id: str = Form(...), scene_id: str = Form(...)):
    task_id = task_id + "_" + scene_id
    value = _get_redis().get_value(task_id)
    if value:
        return {"code": 200, "taskId": task_id, "value": value}
    return {"code": 200, "taskId": task_id, "value": json.dumps({"process": 0.0})}


@app.post("/get_check_batch_result")
async def check_batch_result(item: BatchItem):
    results = []
    for task in item.task_list:
        task_id = task["task_id"]
        scene_id = task["scene_id"]
        my_task_id = task_id + "_" + scene_id
        value = _get_redis().get_value(my_task_id)
        if value:
            results.append({"taskId": my_task_id, "value": value})
        else:
            results.append({"taskId": my_task_id, "value": json.dumps({"process": 0.0})})
    return {"code": 200, "result_list": results}


@app.post("/check_single_funck")
async def check_single_funck(items: ActionList):
    logger.info("check_single_funck 收到请求")
    action_items = [action.dict() for action in items.actionList]
    if len(action_items) != 2:
        return {"code": 404, "error": "传输的不是两张截图"}

    start_time = time.time()
    check_result = run_single_step(build_single_step_payload(action_items))
    end_time = time.time()
    logger.info(f"check_single_funck 消耗时间：{end_time-start_time}")
    logger.info(f"check_single_funck 返回结果：{check_result}")
    return {"code": 200, "check_result": check_result}


@app.post("/check_e2e")
async def check_e2e(item: DataInfo):
    logger.info("check_e2e 收到请求")
    start_time = time.time()
    res = run_sequence_payload(item.dict())
    end_time = time.time()
    logger.info(f"check_e2e 消耗时间：{end_time-start_time}")
    logger.info(f"check_e2e 返回结果：{res}")
    return {"code": 200, "check_result": res}


if __name__ == "__main__":
    _get_redis().get_key_vlaues()
    for no in range(CONSUMER_NUMBER):
        functional_oracle_checker = function_oracle_checker.FunctionalOracleCheckerV3(
            logger, no, _get_redis(), s3_client
        )
        process = multiprocessing.Process(target=functional_oracle_checker.oracle, args=())
        process.start()
    uvicorn.run(app, host="0.0.0.0", port=20025, limit_concurrency=10)

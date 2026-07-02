import json
import time
import uvicorn
import multiprocessing
from fastapi import FastAPI, Form
from library.logger import logger
from datetime import datetime
from app.models import AIAssistedScenarioDeterminationModel, BatchItem, DataInfo, ActionList
from oracle.function_oracle import function_oracle_checker
from utils.database import RedisClusterClient, OBSDatabaseClient
from config import *
from GUI_TestFramework_v1 import scripts


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
    response = {
        "status": 200,
        "result": oracle_result["result"],
        "checkPointList": oracle_result["checkPointList"]
    }
    return response


# 任务上传接口
@app.post("/upload_funcheck_task")
async def upload(task_id: str = Form(...), scene_id: str = Form(...)):
    # 判断队列的长度是否超过预定设置的长度
    logger.info(f"提交功能检测任务，task_id:{task_id}--scene_id:{scene_id}\n")
    current_length = _get_redis().get_len_from_list(MESSAGE_QUEUE_NAME)
    logger.info(f"当前任务队列长度:{current_length}")
    if current_length >= QUEUE_LIMIT_LENGTH:
        logger.error(f"超出最大任务队列数量限制，请等待。当前长度{current_length}")
        return {"code": 400, "error": "超出最大任务队列数量限制，请等待。"}
    # 创建唯一目录
    this_task_id = task_id + "_" + scene_id
    current_time = datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    file_name = this_task_id + ".zip"
    # 任务存入消息队列
    task_infos = {
        "task_id": this_task_id,
        "task_status": "等待",
        "task_progress": 0.,
        "task_processing_results": {},
        "task_submit_time": formatted_time,
        "file_name": file_name
    }

    push_status = _get_redis().push_to_list(MESSAGE_QUEUE_NAME, json.dumps(task_infos, ensure_ascii=False))
    if push_status:
        logger.info(f"{task_infos}消息队列保存成功！")
        return {"code": 200, "task_id": task_id, "scene_id": scene_id, "submit_status": True}
    else:
        logger.info(f"{task_infos}消息队列保存失败！")
        return {"code": 200, "task_id": task_id, "scene_id": scene_id, "submit_status": False}


@app.post("/get_upload_params")
async def upload(task_id: str = Form(...), scene_id: str = Form(...)):
    logger.info(f"task_id:{task_id} -- scene_id:{scene_id} 获取上传链接")
    file_name = f"{task_id}_{scene_id}.zip"
    return {"region_name": REGION_NAME, "bucket_name": BUCKETNAME, "file_name": file_name, "ak": AK, "sk": SK}


# 单个任务查询任务
@app.post('/get_check_result')
async def check_result(task_id: str = Form(...), scene_id: str = Form(...)):
    task_id = task_id + "_" + scene_id
    value = _get_redis().get_value(task_id)
    if value:
        return {"code": 200, "taskId": task_id, "value": value}
    else:
        return {"code": 200, "taskId": task_id, "value": json.dumps({"process": 0.})}


# 批量查询任务
@app.post('/get_check_batch_result')
async def check_batch_result(item: BatchItem):
    task_list = item.task_list
    results = []
    for tl in task_list:
        task_id = tl['task_id']
        scene_id = tl['scene_id']
        my_task_id = task_id + "_" + scene_id
        value = _get_redis().get_value(my_task_id)
        if value:
            # reformattedResultDict  taskId
            results.append({"taskId": my_task_id, "value": value})
        else:
            results.append({"taskId": my_task_id, "value": json.dumps({"process": 0.})})
    return {"code": 200, "result_list": results}


def sequence_test(sample_dict: dict):
    from GUI_TestFramework_v1.scripts.config import Config as FrameworkConfig

    fc = FrameworkConfig()
    fc.project.PREDICATE_MODE = 'production'
    fc.data.METADATA = sample_dict

    e2eTest = scripts.sequence.HarmonyAppTest(fc)
    e2eTest.ab_pages_validate()
    e2eTest.child_sequence_router()
    e2eTest.test_result()
    return e2eTest.result_format_align()


def page_test(sample_dict: dict):
    newtest = scripts.single_step.HarmonyAPPSingleStepTest(sample_dict)
    return newtest.run()


# 单步功能正确性判定接口
@app.post('/check_single_funck')
async def check_single_funck(items: ActionList):
    # jar_parser.load_jar_pkg()
    # copy_items = copy.deepcopy(items)
    # copy_items = [item.dict() for item in copy_items]
    # copy_items[0]["layoutPath"] = "layout/0.json"
    # copy_items[0]["screenshotPath"] = "screenshot/0.jpeg"
    # copy_items[0]["bounds"] = copy_items[0]["startBox"]
    # copy_items[1]["layoutPath"] = "layout/1.json"
    # copy_items[1]["screenshotPath"] = "screenshot/1.jpeg"
    # copy_items[1]["bounds"] = copy_items[1]["startBox"]
    # test_suites = {
    #     "actionInfos": [{
    #         "actionList": copy_items,
    #         "instruction": "",
    #         "videoEndTime": "",
    #         "videoPath": "",
    #         "videoStartTime": ""
    #     }
    #     ],
    #     "deepExplore": False,
    #     "sceneTestCaseId": "",
    #     "taskId": "check_single_funck_task_id",
    #     "endSide": True,
    #     "simple": False,
    # }
    # rule_based_res = functional_oracleChecker.processing_flow(test_suites)
    logger.info(f"check_single_funck 收到请求")
    actionList = items.actionList
    items = [action.dict() for action in actionList]
    if len(items) != 2:
        return {"code": 404, "error": "传输的不是两张截图"}

    # data_format = [
    #     {
    #         "img1_path": items[0].get("img", ""),
    #         "img2_path": items[1].get("img", ""),
    #         "action_info":
    #             {
    #                 "action_type": items[0].get("operType", ""),
    #                 "start_box": items[0].get("startBox", ""),
    #                 "end_box": items[0].get("endBox", ""),
    #                 "text": items[0].get("text", ""),
    #                 "direction": items[0].get("direction", "")
    #             }
    #     }
    #
    # ]
    data_format = {"seq_info": [
        {"index": 0,
         "image_relative_path": items[0].get("img", ""),
         "planning_output": {
             "parsed_action": {
                 "action_type": items[0].get("operType", ""),
                 "start_box": items[0].get("startBox", ""),
                 "end_box": items[0].get("endBox", ""),
                 "text": items[0].get("text", ""),
                 "direction": items[0].get("direction", "")}
         }},
        {"index": 1,
         "image_relative_path": items[1].get("img", "")}
    ]}
    # with open("./request_single_funck_result.txt", "w", encoding="utf-8") as f:
    #     f.write(json.dumps(data_format, ensure_ascii=False))
    start_time = time.time()
    check_result = page_test(data_format)
    end_time = time.time()
    logger.info(f"check_single_funck 消耗时间：{end_time-start_time}")
    logger.info(f"check_single_funck 返回结果：{check_result}")
    return {"code": 200, "check_result": check_result}


@app.post('/check_e2e')
async def check_e2e(item: DataInfo):
    # with open("./check_e2e.txt", "w", encoding="utf-8") as f:
    #     f.write(json.dumps(item.dict(), ensure_ascii=False))
    logger.info(f"check_e2e 收到请求")
    start_time = time.time()
    json_data = item.dict()
    res = sequence_test(json_data)
    end_time = time.time()
    logger.info(f"check_e2e 消耗时间：{end_time-start_time}")
    logger.info(f"check_e2e 返回结果：{res}")
    return {"code": 200, "check_result": res}



if __name__ == '__main__':
    # 程序启动需要轮播一下redis数据库看看没有没有进度不是1.0的任务 如果存在就要添加到任务队列中去
    _get_redis().get_key_vlaues()
    for no in range(CONSUMER_NUMBER):
        functional_oracleChecker = function_oracle_checker.FunctionalOracleCheckerV3(logger, no, _get_redis(),
                                                                                     s3_client)
        p = multiprocessing.Process(target=functional_oracleChecker.oracle, args=())
        p.start()
    uvicorn.run(app, host="0.0.0.0", port=20025, limit_concurrency=10)

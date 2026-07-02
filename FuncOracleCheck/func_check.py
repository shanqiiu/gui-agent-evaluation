# import unittest
# import os, json
# from oracle.function_oracle import function_oracle_checker
# from library.logger import logger
# from external_apis import jar_parser
# from utils_1 import json_utils, cv_utils , layout_utils
#
# jar_parser.load_jar_pkg()

# functional_oracleChecker = function_oracle_checker.FunctionalOracleCheckerV3(logger, 0)
#
#
# screenshots_path = "/home/limengqi/data/bad_cases_0815"
# layout_path = "/home/limengqi/data/bad_cases_0815"
# # testsuites_basedir = '/home/limengqi/data/json文件/页面显示白屏'
# testsuites_basedir = '/home/limengqi/data/json文件/点击提示错误'
#
#
# # screenshots_path = "/home/limengqi/data/加载中&加载失败/data"
# # layout_path = "/home/limengqi/data/加载中&加载失败/data"
# # testsuites_basedir = '/home/limengqi/data/加载中&加载失败'
#
#
# files = os.listdir(testsuites_basedir)
#
# loujian = []
# for file in files:
#     # if "testSuites_9.json" not in file:
#     #     continue
#     if not file.endswith(".json"):
#         continue
#     test_suites = json_utils.load_json(os.path.join(testsuites_basedir, file))
#     actionInfos = test_suites['actionInfos'][0]
#     actionList = actionInfos['actionList']
#     for action in actionList:
#         screenshotPath = action['screenshotPath']
#         action['layoutPath'] = ""
#         # layoutPath = action['layoutPath']
#         layoutPath = ""
#         action['img'] = cv_utils.encode_image_to_base64(os.path.join(screenshots_path, screenshotPath))
#         # layout_dict = json_utils.load_json(os.path.join(layout_path, layoutPath))
#         # action['layout'] = json.dumps(layout_dict)
#         action['layout'] = ""
#
#     test_suites['simple'] = False
#     test_suites['endSide'] = True
#     result = functional_oracleChecker.processing_flow(test_suites)
#     print('res')
#     print(result)
#     screenshotPath = ''
#     for funCheck in result['funCheckResult']:
#         errorPageList = funCheck['errorPageList']
#         for errorPage in errorPageList:
#             screenshotPath = errorPage['screenshotPath']
#             errorfuncCheckType = errorPage['errorfuncCheckType']
#     if not screenshotPath:
#         loujian.append(file)
# print(loujian)
# print(len(loujian), len(files))
# # 64 96
#
#
#
#
#
#
# # import os
# # import json
# # import base64
# # import requests
# #
# # bad_case_dir = "/home/limengqi/data/bad_case"
# #
# # LAYOUT_PATH = os.path.join(bad_case_dir, "1754993074000.json")
# # IMAGE_PATH  = os.path.join(bad_case_dir, "1754993074000.jpeg")
# #
# # LAYOUT_PATH_2 = os.path.join(bad_case_dir, "1754993078000.json")
# # IMAGE_PATH_2  = os.path.join(bad_case_dir, "1754993078000.jpeg")
# #
# #
# #
# # def read_image_as_base64(path: str) -> str:
# #     """把图片转成 base64 字符串"""
# #     with open(path, "rb") as f:
# #         return base64.b64encode(f.read()).decode()
# #
# # def read_json_as_string(path: str) -> str:
# #     """读取layout"""
# #     with open(path, "r", encoding="utf-8") as f:
# #         return f.read()
# #
# #
# #
# # import json
# # test_suites_path = r"C:\Users\l30037787\Downloads\1158073214999448700_haibaozhizuo\testSuites.json"
# #
# # data_dir = r"C:\Users\l30037787\Downloads\1158073214999448700_haibaozhizuo"
# # with open(test_suites_path, "r", encoding="utf-8") as f:
# #     json_data = json.load(f)
# #
# #
# #
# # actionList = json_data["actionInfos"][0]['actionList']
# #
# # newactionList = []
# #
# # for action in actionList:
# #     screenshot = action["screenshotPath"]
# #     layout = action["layoutPath"]
# #     screenshotPath = os.path.join(data_dir, screenshot)
# #     layoutPath = os.path.join(data_dir, layout)
# #     img = read_image_as_base64(os.path.join(data_dir, screenshotPath))
# #     layout = read_json_as_string(os.path.join(data_dir, layoutPath))
# #     action["img"] = img
# #     action["layout"] = layout
# #     newactionList.append(action)
# #
# #
# # action_info = {
# #     "actionList": newactionList,
# #     "instruction": "",
# #     "videoPath": ""
# # }
# #
# # test_suites = {
# #     "actionInfos": [action_info],
# #     "deepExplore": True,
# #     "sceneTestCaseId": "",
# #     "taskId": "1155111338487158243",
# #     "simple": False,
# #     "endSide": True
# # }
# #
# # result = functional_oracleChecker.processing_flow(test_suites)
# # print('res')
# # print(result)
#
#
# from utils_1.database import RedisClusterClient
# from config import *
#
# redis_cluster_client = RedisClusterClient(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)
# for i in range(0,1500):
#     res = redis_cluster_client.delete_key(f"1158073203368643663_haikanghulian_{i}")
#     print(res)

# while True:
#     task_infos = redis_cluster_client.pop_from_list(MESSAGE_QUEUE_NAME)
#     if not task_infos:
#         continue
#     else:
#         print('123')



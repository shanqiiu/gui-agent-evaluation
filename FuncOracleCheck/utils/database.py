import json
import requests
from obs import ObsClient
from redis.cluster import RedisCluster, ClusterNode
from config import *


# redis数据库
class RedisClusterClient:
    def __init__(self, host, port, password=None):
        startup_nodes = [ClusterNode(host, port)]
        self.client = RedisCluster(
            startup_nodes=startup_nodes,
            decode_responses=True,
            password=password
        )

    def set_value(self, key, value):
        try:
            self.client.set(key, value)
            print(f"Key '{key}' set to '{value}'")
        except Exception as e:
            print(f"Error setting key '{key}': {e}")

    def get_value(self, key):
        try:
            value = self.client.get(key)
            print(f"Value for key '{key}': {value}")
            return value
        except Exception as e:
            print(f"Error getting key '{key}': {e}")
            return None

    def delete_key(self, key):
        try:
            self.client.delete(key)
            print(f"Key '{key}' deleted")
        except Exception as e:
            print(f"Error deleting key '{key}': {e}")

    def key_exists(self, key):
        try:
            exists = self.client.exists(key)
            print(f"Key '{key}' exists: {exists}")
            return exists
        except Exception as e:
            print(f"Error checking if key '{key}' exists: {e}")
            return False

    def expire_key(self, key, time):
        try:
            self.client.expire(key, time)
            print(f"Key '{key}' set to expire in {time} seconds")
        except Exception as e:
            print(f"Error setting expire for key '{key}': {e}")

    # 列表操作
    def push_to_list(self, key, *values):
        try:
            self.client.rpush(key, *values)
        except Exception as e:
            return False
        return True

    def pop_from_list(self, key):
        try:
            value = self.client.lpop(key)
            return value
        except Exception as e:
            return False
        return True

    def get_len_from_list(self, key):
        length = self.client.llen(key)
        return length

    def get_list_range(self, key, start=0, end=-1):
        try:
            values = self.client.lrange(key, start, end)
            return values
        except Exception as e:
            return []

    def get_key_vlaues(self):

        cursor, keys = self.client.scan(cursor=0)
        for key in keys:
            if len(key.split("-")) == 5:
                value = self.client.get(key)
                value = json.loads(value)
                task_infos = value.get('task_infos', '')
                process = value.get('process', 0.)
                if task_infos and process < 1.0:
                    # task_infos_json = json.loads(task_infos)
                    # task_id = task_infos_json.get('task_id', '')
                    # if task_id == "68c14b4c-7248-4105-bca2-d3092dd13933":
                    self.push_to_list(MESSAGE_QUEUE_NAME, task_infos)

    def rm_all_data(self):
        self.client.flushall()
        print("删除所有数据")


# # s3存储数据数据库
# class S3DatabaseClient:
#     def __init__(self, ):
#         self.dataSetName = 'featureTree'
#         self.dataSetVersion = 'v1'
#         self.projectId = 'test_00'
#         self.uploadStatus = 'full_upload'
#
#     def upload(self, file_stream, file_name, upload_id):
#         url = "http://aifortesting.huawei.com/aiplatform/common_server/uploadFiles"
#
#         payload = {'dataSetName': self.dataSetName,
#                    'dataSetVersion': self.dataSetVersion,
#                    'projectId': self.projectId,
#                    'uploadStatus': self.uploadStatus}
#         files = [
#             ('dataSourceFiles', (upload_id + '_' + file_name, file_stream, 'application/zip'))
#         ]
#         headers = {}
#
#         response = requests.request("POST", url, headers=headers, data=payload, files=files, verify=False)
#         if response.json()['status'] == 200:
#             return 'success'
#         else:
#             return 'fail'
#
#     def download(self, file_name, upload_id):
#         url = f"http://aifortesting.huawei.com/aiplatform/common_server/downloadFileToPath?filePath=project/{self.projectId}/data/{self.dataSetName}/{self.dataSetVersion}/{upload_id + '_' + file_name}"
#         payload = {}
#         headers = {}
#         response = requests.request("GET", url, headers=headers, data=payload, verify=False)
#         return response.content
#
#     def delete(self, file_name, upload_id):
#         url = f"http://aifortesting.huawei.com/aiplatform/common_server/deleteFile?projectId={self.projectId}&dataSetName={self.dataSetName}&dataSetVersion={self.dataSetVersion}&fileName={upload_id + '_' + file_name}"
#
#         payload = {}
#         headers = {}
#
#         response = requests.request("GET", url, headers=headers, data=payload, verify=False)
#
#         if response.json()['status'] == 200:
#             return "success"
#         else:
#             return "fail"

import os


# # 本地存储
class S3DatabaseClient:
    def __init__(self, ):
        self.dataSetName = 'funcOracleCheck'
        self.dataSetVersion = 'v1'
        self.projectId = 'test_01'
        self.uploadStatus = 'full_upload'
        self.dir = "./virtual_database"
        os.makedirs(self.dir, exist_ok=True)

    def upload(self, file_stream, file_name, upload_id):
        save_filename = self.dir + "/" + upload_id + '_' + file_name
        try:
            with open(save_filename, 'wb') as f:
                f.write(file_stream)
        except Exception as e:
            print(f"Error uploading file '{save_filename}': {e}")
            return 'fail'
        return 'success'

    def download(self, file_name, upload_id):
        save_filename = self.dir + "/" + upload_id + '_' + file_name
        with open(save_filename, 'rb') as f:
            content = f.read()
        return content

    def delete(self, file_name, upload_id):
        save_filename = self.dir + "/" + upload_id + '_' + file_name
        os.remove(save_filename)
        return "success"


# Obs存储
class OBSDatabaseClient:
    def __init__(self, ak, sk, region_name, bucketname):
        self.obsClient = ObsClient(
            access_key_id=ak,
            secret_access_key=sk,
            server=region_name,
            path_style=True,
            signature="v2",
            is_signature_negotiation=True
        )
        self.bucketname = bucketname

    def upload(self, file_stream, file_name, upload_id):
        pass

    def download(self, file_name, save_path):
        partSize = 8 * 1024 * 1024
        taskNum = 3
        try:
            resp = self.obsClient.downloadFile(self.bucketname,
                                               file_name,
                                               save_path,
                                               partSize,
                                               taskNum,
                                               True)

            if resp.status < 300:
                print('requestId:', resp.requestId)
                print('url:', resp.body.url)
            else:
                print('errorCode:', resp.errorCode)
                print('errorMessage:', resp.errorMessage)
        except Exception as e:
            print(e.__str__())
            return False
        return True

    def delete(self, file_name, upload_id):
        pass


# 使用示例
if __name__ == "__main__":
    redis_client = RedisClusterClient(host="10.28.117.138", port=6379, password='pC7~zT9)rU4{zG1>aB')
    redis_client.get_key_vlaues()
    # keys = redis_client.get_list_range('TASK_QUEUE')
    # print(keys)
    # redis_client.set_value('key', 'value')
    # redis_client.get_value('key')
    # redis_client.key_exists('key')
    # redis_client.expire_key('key', 60)
    # redis_client.delete_key('key')
    #
    # # 列表操作示例
    # redis_client.push_to_list('mylist', 'a', 'b', 'c')
    # redis_client.get_list_range('TASK_QUEUE')
    # redis_client.pop_from_list('task_queue')
    # redis_client.get_list_range('TASK_QUEUE')
    # res = redis_client.rm_all_data()
    #
    # print(res)
    # s3_database_client = S3DatabaseClient()
    # file_stream = open(r'C:/Users/l30037787/AppData/Roaming/eSpace_Desktop/UserData/l30037787/ReceiveFile/EF5C27C8A1BCDB5C60E0380CE8A4E8B9.zip','rb')
    # file_name = "EF5C27C8A1BCDB5C60E0380CE8A4E8B9.zip"
    # # res = s3_database_client.upload(file_stream, file_name)
    # # print(res)
    # res = s3_database_client.download(file_name)
    # print(res)
    # res = s3_database_client.delete(file_name)
    # print(res)

    # s3_database_client = S3DatabaseClient()
    # file_name = "graph.zip"
    # task_id = "68c14b4c-7248-4105-bca2-d3092dd13933"
    # content = s3_database_client.download(file_name, task_id)
    # print(content)

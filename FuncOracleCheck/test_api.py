import requests
import base64
import os

os.environ["no_proxy"] = "localhost,127.0.0.1,.huawei.com"

headers = {
       'Content-Type': 'application/json',
       'Authorization': 'Bearer sk-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2NvdW50SWQiOiJqMDA5NTYyNDQiLCJhY2NvdW50TmFtZSI6ImppYW5nYm93ZWkiLCJkZXBhcnRtZW50TmFtZSI6InVua25vd24iLCJ0ZW5hbnRJZCI6ImU0YTQ0NTcxYTlmYzE0MTE1ZmViYmJhNWRhNzZhNmEzIiwia2V5VmVyc2lvbiI6IjIuMCJ9.08kKW8bkq4eU2LabqXb4c51ZJ5EGBQcELhovG_0HVrw'
   }

with open("./screenshots/1.JPG", "rb") as image_file:
       image_data = base64.b64encode(image_file.read()).decode('utf-8')

json_data = {
       "model": "qwen36-27b-vl", 
       "messages": [
           {
               "role": "user",
               "content": [
                   {
                       "type": "text",
                       "text": "图片里的内容是什么？"
                   },
                   {
                       "type": "image_url",
                       "image_url": {
                           "url": f"data:image/jpeg;base64,{image_data}"
                       }
                   }
               ]
           }
       ],
       "max_tokens": 2048
   }
url = 'http://mlops.huawei.com/mlops-service/api/v2/agentService/v1/chat/completions'
response = requests.post(url, headers=headers, json=json_data)
print(response.text)

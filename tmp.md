root@L20-10-85-177-3:/data/FuncOracleCheck# uvicorn main:app --host 0.0.0.0 --port 8000  --reload
INFO:     Will watch for changes in these directories: ['/data/FuncOracleCheck']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [195131] using WatchFiles
INFO:     Started server process [195141]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
2026-07-03 16:35:57,823 123660266932032 main.py[line:108] - INFO: check_single_funck 收到请求
----------------- configuration is read from: /data/FuncOracleCheck/conf/run_benchmark_config.conf -----------------
HarmonyAPPSingleStepTest: run: API服务出现问题，重试...
error: HTTPConnectionPool(host='localhost', port=8000): Read timed out. (read timeout=120)
message: None

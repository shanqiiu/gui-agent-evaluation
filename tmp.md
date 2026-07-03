2026-07-03 15:27:31,934 137091988518720 main.py[line:116] - INFO: check_single_funck 消耗时间：1.075995922088623
2026-07-03 15:27:31,934 137091988518720 main.py[line:117] - INFO: check_single_funck 返回结果：{'判定结果': None, '判定依据': None}
INFO:     127.0.0.1:48422 - "POST /check_single_funck HTTP/1.1" 200 OK
2026-07-03 15:27:31,958 137091988518720 main.py[line:108] - INFO: check_single_funck 收到请求
HarmonyAPPSingleStepTest: run: API服务出现问题，重试...
error: 'choices'
message: None
HarmonyAPPSingleStepTest: run: API服务出现问题，重试...
error: 'choices'
message: None
HarmonyAPPSingleStepTest: run: API服务出现问题，重试...
error: 'choices'
message: None
2026-07-03 15:27:33,053 137091988518720 main.py[line:116] - INFO: check_single_funck 消耗时间：1.094527006149292
2026-07-03 15:27:33,053 137091988518720 main.py[line:117] - INFO: check_single_funck 返回结果：{'判定结果': None, '判定依据': None}
INFO:     127.0.0.1:48428 - "POST /check_single_funck HTTP/1.1" 200 OK
2026-07-03 15:27:33,085 137091988518720 main.py[line:123] - INFO: check_e2e 收到请求
1
Exception in thread Thread-1 (_worker):
Traceback (most recent call last):
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/rsync_multi_threads_ab_validator.py", line 151, in _call_single_api
    message = mllm.request_vlm_ab_test(img1_path=img_a,
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/api_service/mllm.py", line 215, in request_vlm_ab_test
    return request_vlm(user_query=None,
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/api_service/mllm_data_collector/data_collector.py", line 24, in wrapper
    output_data = func(*args, **kwargs)
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/api_service/mllm.py", line 160, in request_vlm
    return result_json["choices"][0]["message"]["content"]
KeyError: 'choices'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/threading.py", line 1016, in _bootstrap_inner
    self.run()
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/threading.py", line 953, in run
    self._target(*self._args, **self._kwargs)
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/rsync_multi_threads_ab_validator.py", line 202, in _worker
    self._call_single_api(image_pair=this_image_pair, ab_test_results=ab_test_results)
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/rsync_multi_threads_ab_validator.py", line 184, in _call_single_api
    f'message: {message}')
UnboundLocalError: local variable 'message' referenced before assignment
Exception in thread Thread-2 (_worker):
Traceback (most recent call last):
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/rsync_multi_threads_ab_validator.py", line 151, in _call_single_api
    message = mllm.request_vlm_ab_test(img1_path=img_a,
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/api_service/mllm.py", line 215, in request_vlm_ab_test
    return request_vlm(user_query=None,
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/api_service/mllm_data_collector/data_collector.py", line 24, in wrapper
    output_data = func(*args, **kwargs)
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/api_service/mllm.py", line 160, in request_vlm
    return result_json["choices"][0]["message"]["content"]
KeyError: 'choices'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/threading.py", line 1016, in _bootstrap_inner
    self.run()
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/threading.py", line 953, in run
    self._target(*self._args, **self._kwargs)
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/rsync_multi_threads_ab_validator.py", line 202, in _worker
    self._call_single_api(image_pair=this_image_pair, ab_test_results=ab_test_results)
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/rsync_multi_threads_ab_validator.py", line 184, in _call_single_api
    f'message: {message}')
UnboundLocalError: local variable 'message' referenced before assignment
Exception in thread Thread-3 (_worker):
Traceback (most recent call last):
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/rsync_multi_threads_ab_validator.py", line 151, in _call_single_api
    message = mllm.request_vlm_ab_test(img1_path=img_a,
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/api_service/mllm.py", line 215, in request_vlm_ab_test
    return request_vlm(user_query=None,
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/api_service/mllm_data_collector/data_collector.py", line 24, in wrapper
    output_data = func(*args, **kwargs)
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/api_service/mllm.py", line 160, in request_vlm
    return result_json["choices"][0]["message"]["content"]
KeyError: 'choices'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/threading.py", line 1016, in _bootstrap_inner
    self.run()
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/threading.py", line 953, in run
    self._target(*self._args, **self._kwargs)
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/rsync_multi_threads_ab_validator.py", line 202, in _worker
    self._call_single_api(image_pair=this_image_pair, ab_test_results=ab_test_results)
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/rsync_multi_threads_ab_validator.py", line 184, in _call_single_api
    f'message: {message}')
UnboundLocalError: local variable 'message' referenced before assignment
{}
INFO:     127.0.0.1:48436 - "POST /check_e2e HTTP/1.1" 500 Internal Server Error
ERROR:    Exception in ASGI application
Traceback (most recent call last):
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/uvicorn/protocols/http/httptools_impl.py", line 435, in run_asgi
    result = await app(  # type: ignore[func-returns-value]
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/uvicorn/middleware/proxy_headers.py", line 78, in __call__
    return await self.app(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/fastapi/applications.py", line 1163, in __call__
    await super().__call__(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/applications.py", line 90, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/middleware/errors.py", line 186, in __call__
    raise exc
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/middleware/errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/routing.py", line 660, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/fastapi/routing.py", line 2543, in app
    await route.handle(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/fastapi/routing.py", line 1241, in handle
    await super().handle(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/routing.py", line 276, in handle
    await self.app(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/fastapi/routing.py", line 150, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/fastapi/routing.py", line 136, in app
    response = await f(request)
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/fastapi/routing.py", line 690, in app
    raw_response = await run_endpoint_function(
  File "/home/ethan/anaconda3/envs/FuncOracleCheck/lib/python3.10/site-packages/fastapi/routing.py", line 344, in run_endpoint_function
    return await dependant.call(**values)
  File "/data/FuncOracleCheck/main.py", line 125, in check_e2e
    res = run_sequence_payload(item.dict())
  File "/data/FuncOracleCheck/oracle_service.py", line 33, in run_sequence_payload
    return run_sequence(config)
  File "/data/FuncOracleCheck/oracle_service.py", line 22, in run_sequence
    test.child_sequence_router()
  File "/data/FuncOracleCheck/GUI_TestFramework_v1/scripts/sequence.py", line 103, in child_sequence_router
    child_page_des[str(page_idx)] = self.page_des[str(page_idx)]
KeyError: '0'
2026-07-03 15:27:33,556 137091988518720 main.py[line:108] - INFO: check_single_funck 收到请求
HarmonyAPPSingleStepTest: run: API服务出现问题，重试...
error: 'choices'
message: None
HarmonyAPPSingleStepTest: run: API服务出现问题，重试...
error: 'choices'
message: None
HarmonyAPPSingleStepTest: run: API服务出现问题，重试...
error: 'choices'
message: None
2026-07-03 15:27:33,879 137091988518720 main.py[line:116] - INFO: check_single_funck 消耗时间：0.3221156597137451
2026-07-03 15:27:33,879 137091988518720 main.py[line:117] - INFO: check_single_funck 返回结果：{'判定结果': None, '判定依据': None}
INFO:     127.0.0.1:48442 - "POST /check_single_funck HTTP/1.1" 200 OK

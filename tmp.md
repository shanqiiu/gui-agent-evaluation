{'2': {'thought': 'action type: preCheckDone is illegal!', 'label': '无法判定', 'action_des': None, 'pagea_description': None, 'pageb_description': None}, '0': {'thought': 'action type: edit is illegal!', 'label': '无法判定', 'action_des': None, 'pagea_description': '这是一个手机的设置界面，显示了多个功能选项。界面顶部有一个搜索框，用于搜索设置项。用户信息部分显示了用户名知秋，以及与华为账号、付款和云空间相关的功能。下方展示了设备存储（49 GB/50 GB）、查找设备等功能。接着列出了多个网络相关选项，包括WLAN（连接到Huawei-Guest）、星闪和蓝牙（已开启）、移动网络、卫星网络和多设备协同。此外，还有桌面和个性化、显示和亮度、声音和振动等设置选项。界面中没有明显的tab栏，因此无需识别被选中的tab。', 'pageb_description': None}, '1': {'thought': '在上一个页面中，红色圈标识的位置是搜索结果中的定时开关机选项。根据操作动作信息，用户点击了这个选项。预期结果是进入与定时开关机相关的设置页面。nn在下一个页面中，确实显示了定时开关机的详细设置界面，包括开关状态、开机时间、关机时间和重复设置等选项。页面布局和功能与预期一致，显示了用户可以调整定时开关机的具体设置。nn因此，前后页面的切换符合预期。', 'label': '符合预期', 'action_des': '点击搜索结果中的定时开关机选项', 'pagea_description': None, 'pageb_description': '定时开关机设置界面，当前界面显示了定时开关机的功能选项，包括开机时间、关机时间以及重复设置。开机时间为上午7:00，关机时间为下午11:00，重复设置为每周。'}}
request VLM server error! response status: 400
response: {"error":{"message":"cannot identify image file <_io.BytesIO object>","type":"BadRequestError","param":null,"code":400}}
2026-07-07 21:03:23 - default - INFO - sequence:363 - _sequence_predicate: API 请求错误，重试...
e: 'NoneType' object is not subscriptable
message: None
INFO:     127.0.0.1:40410 - "POST /check_e2e HTTP/1.1" 500 Internal Server Error
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
  File "/data/gui-agent-evaluation/FuncOracleCheck/main.py", line 125, in check_e2e
    res = run_sequence_payload(item.dict())
  File "/data/gui-agent-evaluation/FuncOracleCheck/oracle_service.py", line 54, in run_sequence_payload
    return run_sequence(config)
  File "/data/gui-agent-evaluation/FuncOracleCheck/oracle_service.py", line 27, in run_sequence
    aligned_result = test.result_format_align()
  File "/data/gui-agent-evaluation/FuncOracleCheck/GUI_TestFramework_v1/scripts/sequence.py", line 618, in result_format_align
    self._step_result_format_align(result_dict='llm', align_result=align_result)
  File "/data/gui-agent-evaluation/FuncOracleCheck/GUI_TestFramework_v1/scripts/sequence.py", line 584, in _step_result_format_align
    '存在bug的执行步骤': info['wrong_steps']})
KeyError: 'wrong_steps

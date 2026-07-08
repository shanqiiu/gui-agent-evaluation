(FuncOracleCheck) root@L20-10-85-177-3:/data/gui-agent-evaluation/FuncOracleCheck# uvicorn main:app --host 0.0.0.0 --port 20026
INFO:     Started server process [611258]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:20026 (Press CTRL+C to quit)
2026-07-08 10:02:24,066 126020779792192 main.py[line:123] - INFO: check_e2e 收到请求
----------------- configuration is read from: /data/gui-agent-evaluation/FuncOracleCheck/conf/run_benchmark_config.conf -----------------
1
2026-07-08 10:02:24 - default - WARNING - rsync_multi_threads_ab_validator:149 - ABPageValidator：API服务出现问题，重试...
e: 'content'
message: None
2026-07-08 10:02:24 - default - WARNING - rsync_multi_threads_ab_validator:149 - ABPageValidator：API服务出现问题，重试...
e: 'content'
message: None
2026-07-08 10:02:24 - default - WARNING - rsync_multi_threads_ab_validator:149 - ABPageValidator：API服务出现问题，重试...
e: 'content'
message: None
request VLM server error! response status: 400
response: {"error":{"message":"cannot identify image file <_io.BytesIO object>","type":"BadRequestError","param":null,"code":400}}
2026-07-08 10:02:24 - default - WARNING - rsync_multi_threads_ab_validator:88 - ABPageValidator：API服务出现问题，重试...
e: 模型返回为空或不是可解析JSON
message: None
request VLM server error! response status: 400
response: {"error":{"message":"cannot identify image file <_io.BytesIO object>","type":"BadRequestError","param":null,"code":400}}
2026-07-08 10:02:24 - default - WARNING - rsync_multi_threads_ab_validator:88 - ABPageValidator：API服务出现问题，重试...
e: 模型返回为空或不是可解析JSON
message: None
request VLM server error! response status: 400
response: {"error":{"message":"cannot identify image file <_io.BytesIO object>","type":"BadRequestError","param":null,"code":400}}
2026-07-08 10:02:24 - default - WARNING - rsync_multi_threads_ab_validator:88 - ABPageValidator：API服务出现问题，重试...
e: 模型返回为空或不是可解析JSON
message: None
{'2': {'thought': 'API服务出现问题', 'label': '无法判定', 'action_des': None, 'pagea_description': None, 'pageb_description': None}, '0': {'thought': 'API服务出现问题', 'label': '无法判定', 'action_des': None, 'pagea_description': '这是一个设备的设置界面，显示了多个功能选项。当前界面没有明显的tab栏，但可以观察到多个功能模块，包括账户信息、云空间、设备管理、网络设置（WLAN、星闪和蓝牙、移动网络、卫星网络）、多设备协同、桌面和个性化、显示和亮度以及声音和振动等。界面顶部显示了用户名称知秋，以及云空间的使用情况（49 GB/50 GB）。', 'pageb_description': None}, '1': {'thought': '在上一个页面中，红色圈标识的位置是搜索结果中的定时开关机选项。根据操作动作信息，用户点击了这个选项。预期结果是进入与定时开关机相关的设置页面。nn在下一个页面中，确实显示了定时开关机的详细设置界面，包括开关状态、开机时间、关机时间和重复设置等选项。页面布局和功能与预期一致，显示了用户可以调整定时开关机的具体设置。nn因此，前后页面的切换符合预期。', 'label': '符合预期', 'action_des': '点击搜索结果中的定时开关机选项', 'pagea_description': None, 'pageb_description': '定时开关机设置界面，当前界面显示了定时开关机的功能选项，包括开机时间、关机时间以及重复设置。开机时间为上午7:00，关机时间为下午11:00，重复设置为每周。'}}
INFO:     127.0.0.1:41818 - "POST /check_e2e HTTP/1.1" 500 Internal Server Error
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
  File "/data/gui-agent-evaluation/FuncOracleCheck/oracle_service.py", line 23, in run_sequence
    test.ab_pages_validate()
  File "/data/gui-agent-evaluation/FuncOracleCheck/GUI_TestFramework_v1/scripts/sequence.py", line 160, in ab_pages_validate
    self.action_des[str(idx)] = prompt_utils.make_action_description(
  File "/data/gui-agent-evaluation/FuncOracleCheck/utils/prompt_utils.py", line 19, in make_action_description
    f"输入内容：{data_item['parsed_action']['content']}")
KeyError: 'content'

(FuncOracleCheck) root@L20-10-85-177-3:/data/gui-agent-evaluation/FuncOracleCheck# uvicorn main:app --host 0.0.0.0 --port 20026
INFO:     Started server process [617658]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:20026 (Press CTRL+C to quit)
2026-07-08 10:10:38,423 124703327983424 main.py[line:123] - INFO: check_e2e 收到请求
----------------- configuration is read from: /data/gui-agent-evaluation/FuncOracleCheck/conf/run_benchmark_config.conf -----------------
1
request VLM server error! response status: 400
response: {"error":{"message":"cannot identify image file <_io.BytesIO object>","type":"BadRequestError","param":null,"code":400}}
2026-07-08 10:10:38 - default - WARNING - rsync_multi_threads_ab_validator:88 - ABPageValidator：API服务出现问题，重试...
e: 模型返回为空或不是可解析JSON
message: None
request VLM server error! response status: 400
response: {"error":{"message":"cannot identify image file <_io.BytesIO object>","type":"BadRequestError","param":null,"code":400}}
2026-07-08 10:10:38 - default - WARNING - rsync_multi_threads_ab_validator:88 - ABPageValidator：API服务出现问题，重试...
e: 模型返回为空或不是可解析JSON
message: None
request VLM server error! response status: 400
response: {"error":{"message":"cannot identify image file <_io.BytesIO object>","type":"BadRequestError","param":null,"code":400}}
2026-07-08 10:10:38 - default - WARNING - rsync_multi_threads_ab_validator:88 - ABPageValidator：API服务出现问题，重试...
e: 模型返回为空或不是可解析JSON
message: None
{'2': {'thought': 'API服务出现问题', 'label': '无法判定', 'action_des': None, 'pagea_description': None, 'pageb_description': None}, '1': {'thought': '在上一个页面中，红色圈标识的位置是搜索结果中的定时开关机选项。根据操作动作信息，用户点击了这个选项。预期结果是进入与定时开关机相关的设置页面。nn在下一个页面中，确实显示了定时开关机的详细设置界面，包括开关状态、开机时间、关机时间和重复设置等选项。页面布局和功能与预期一致，显示了用户可以调整定时开关机的具体设置。nn因此，前后页面的切换符合预期。', 'label': '符合预期', 'action_des': '点击搜索结果中的定时开关机选项', 'pagea_description': None, 'pageb_description': '定时开关机设置界面，当前界面显示了定时开关机的功能选项，包括开机时间、关机时间以及重复设置。开机时间为上午7:00，关机时间为下午11:00，重复设置为每周。'}, '0': {'thought': '在上一个页面中，用户执行了输入操作，输入内容为定时开关机。根据操作动作信息，预期结果是进入与定时开关机相关的设置页面。从下一个页面的截图来看，页面显示了搜索结果，其中包含定时开关机的相关设置选项，且页面顶部的搜索栏显示了输入的关键词定时开关机。这表明页面成功跳转到了与输入内容相关的搜索结果页面，符合用户的操作预期。页面布局和数据内容也与预期一致，显示了正确的搜索结果。', 'label': '符合预期', 'action_des': None, 'pagea_description': '这是一个设备的设置界面，显示了多个功能选项。当前界面没有明显的tab栏，但可以观察到多个功能模块，包括账户信息、云空间、设备管理、网络设置（WLAN、星闪和蓝牙、移动网络、卫星网络）、多设备协同、桌面和个性化、显示和亮度以及声音和振动等。界面顶部显示了用户名称知秋，以及云空间的使用情况（49 GB/50 GB）。', 'pageb_description': '搜索结果页面，显示与定时开关机相关的设置选项，当前选中的内容为定时开关机，位于系统 > 定时开关机下。'}}

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

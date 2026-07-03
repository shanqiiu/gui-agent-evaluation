python inference.py --serve --port 8000 --tp 2 
Launching vLLM server: /home/ethan/anaconda3/envs/FuncOracleCheck/bin/python -m vllm.entrypoints.openai.api_server --model /data/FuncOracleCheck/model/qwen --dtype bfloat16 --tensor-parallel-size 2 --max-model-len 32768 --gpu-memory-utilization 0.9 --host 0.0.0.0 --port 8000
(APIServer pid=187072) INFO 07-03 16:27:41 [utils.py:299] 
(APIServer pid=187072) INFO 07-03 16:27:41 [utils.py:299]        █     █     █▄   ▄█
(APIServer pid=187072) INFO 07-03 16:27:41 [utils.py:299]  ▄▄ ▄█ █     █     █ ▀▄▀ █  version 0.19.0
(APIServer pid=187072) INFO 07-03 16:27:41 [utils.py:299]   █▄█▀ █     █     █     █  model   /data/FuncOracleCheck/model/qwen
(APIServer pid=187072) INFO 07-03 16:27:41 [utils.py:299]    ▀▀  ▀▀▀▀▀ ▀▀▀▀▀ ▀     ▀
(APIServer pid=187072) INFO 07-03 16:27:41 [utils.py:299] 
(APIServer pid=187072) INFO 07-03 16:27:41 [utils.py:233] non-default args: {'host': '0.0.0.0', 'model': '/data/FuncOracleCheck/model/qwen', 'dtype': 'bfloat16', 'max_model_len': 32768, 'tensor_parallel_size': 2}
(APIServer pid=187072) INFO 07-03 16:27:41 [model.py:549] Resolved architecture: Qwen2_5_VLForConditionalGeneration
(APIServer pid=187072) INFO 07-03 16:27:41 [model.py:1678] Using max model len 32768
(APIServer pid=187072) INFO 07-03 16:27:41 [vllm.py:790] Asynchronous scheduling is enabled.
(APIServer pid=187072) The image processor of type `Qwen2VLImageProcessor` is now loaded as a fast processor by default, even if the model checkpoint was saved with a slow processor. This is a breaking change and may produce slightly different outputs. To continue using the

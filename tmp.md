  先按你的模型路径过滤，最可靠：

  ps -eo pid,ppid,user,lstart,cmd | grep "/data/FuncOracleCheck/model/qwen" | grep -v grep

  看启动命令里是否有：

  --model /data/FuncOracleCheck/model/qwen
  --port 8009
  --tensor-parallel-size 2

  再看端口 8009 是谁占用：

  ss -lntp | grep 8009

  如果输出里 PID 是 197022 或相关 Python 进程，就是你这次启动的 API server。

  查看进程树：

  pstree -ap 197022

  你日志里的相关 PID 是：

  APIServer pid=197022
  EngineCore pid=197377
  Worker pid=197717
  Worker pid=197718

  确认这些 PID：

  ps -fp 197022 197377 197717 197718

  看 GPU 进程详情：

  nvidia-smi

  如果只显示 python，不好区分，可以拿 nvidia-smi 里的 PID 再查：

  ps -fp <PID>

  或查看完整命令：

  tr '\0' ' ' < /proc/<PID>/cmdline

  最推荐的一组命令：

  ps -eo pid,ppid,user,lstart,cmd | grep "/data/FuncOracleCheck/model/qwen" | grep -v grep
  ss -lntp | grep 8009
  ps -fp 197022 197377 197717 197718
  nvidia-smi

  只要模型路径、端口、启动时间都对上，就能确认是你启动的。

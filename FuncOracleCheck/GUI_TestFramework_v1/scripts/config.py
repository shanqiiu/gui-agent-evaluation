# -*- coding: utf-8 -*-

import os
import configparser


# --------------------------
# 项目基本配置
# --------------------------
class ProjectConfig(object):

    def __init__(self, root_dir: str = None, mode: str = 'test', sliding_mode: str = 'MIX'):
        # 判定模式，生产模式/测试模式，默认为测试模式
        self.PREDICATE_MODE = mode
        self.CANDIDATE_MODES = ('test', 'production')

        # 项目根目录（自动获取当前文件所在目录）
        self.ROOT_DIR = root_dir

        # 日志目录
        self.LOG_DIR = os.path.join(self.ROOT_DIR, "logs")

        # 滑窗模式：LLM/VLM/混合模式，默认为混合模式
        # 'LLM' | ‘VLM' | 'MIX'
        self.SLIDING_MODE = sliding_mode


# --------------------------
# 模型配置
# --------------------------
class ModelConfig(object):
    def __init__(self,
                 vlm_model_name: str = None,
                 vlm_model_url: str = None,
                 llm_model_name: str = None,
                 llm_model_url: str = None,
                 vlm_api_key: str = None,
                 llm_api_key: str = None,
                 vlm_api_key_env: str = None,
                 llm_api_key_env: str = None,
                 include_top_k: bool = True,
                 request_timeout: int = 120):
        # OpenAI-compatible chat completion endpoint settings.
        self.VLM_MODEL_NAME = vlm_model_name
        self.VLM_MODEL_URL = vlm_model_url
        self.LLM_MODEL_NAME = llm_model_name
        self.LLM_MODEL_URL = llm_model_url
        self.VLM_API_KEY = vlm_api_key
        self.LLM_API_KEY = llm_api_key
        self.VLM_API_KEY_ENV = vlm_api_key_env
        self.LLM_API_KEY_ENV = llm_api_key_env
        self.INCLUDE_TOP_K = include_top_k
        self.REQUEST_TIMEOUT = request_timeout


# --------------------------
# 数据配置
# --------------------------
class DataConfig:
    # 数据目录，仅测试模式下使用，根据实际目录所在路径修改
    # Example:
    # -DATA_DIR
    #   -images
    #   -metadata.json


    # 待测样本json，仅生产模式下使用
    # example:
    # {
    #     "instruction": "",
    #     "step_level_instruction": "",
    #     "seq_info": [{
    #         "index": 0,
    #         "image_relative_path": "",  # base64
    #         "planning_output": {
    #             "parsed_action": {
    #                 "action_type": "CLICK",
    #                 "start_box": [94, 2416],
    #                 "end_box": [],
    #                 "text": "",
    #                 "direction": ""}
    #         }
    #     },
    #         {
    #             "index": 1,
    #             "image_relative_path": "",
    #             "planning_output": {
    #                 "parsed_action": {
    #                     "action_type": "CLICK",
    #                     "start_box": [94, 2416],
    #                     "end_box": [],
    #                     "text": "",
    #                     "direction": ""}
    #             }
    #         },
    #         {
    #             "index": 2,
    #             "image_relative_path": "",
    #             "planning_output": {
    #                 "parsed_action": {
    #                     "action_type": "",
    #                     "start_box": [],
    #                     "end_box": [],
    #                     "text": "",
    #                     "direction": ""}
    #
    #             }
    #         }
    #     ]
    # }


    def __init__(self, mode: str = None, root_dir: str = None, sliding_mode: str = None, output_suffix: str = None):
        self.DATA_DIR = None

        self.METADATA = None

        if mode == 'test':
            # 是否保存结果
            self.SAVE_RESULT = True

            # 输出结果目录， 仅当保存结果时使用
            if output_suffix:
                output_folder_name = f"output_SLD{sliding_mode}_{output_suffix}"
            else:
                output_folder_name = f"output_SLD{sliding_mode}"
            self.OUTPUT_DIR = os.path.join(root_dir, output_folder_name)


class MLLMDataCollectorConfig(object):

    def __init__(self,
                 collected_data_root_dir: str = None,
                 llm_saved_folder_name: str = 'LLM_request_log_0916',
                 vlm_saved_folder_name: str = 'VLM_request_log_0916',
                 enable_log: bool = True):

        self.enable_log = enable_log

        self.collected_data_root_dir = None
        self.llm_log_saved_dir = None
        self.vlm_log_saved_dir = None

        self.set_saved_folder_name(collected_data_root_dir=collected_data_root_dir,
                                   llm_saved_folder_name=llm_saved_folder_name,
                                   vlm_saved_folder_name=vlm_saved_folder_name)

    def set_saved_folder_name(self, collected_data_root_dir: str = None, llm_saved_folder_name: str = None, vlm_saved_folder_name: str = None):
        if not collected_data_root_dir:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
            self.collected_data_root_dir = os.path.join(root_dir, 'collected_mllm_data')
        else:
            self.collected_data_root_dir = collected_data_root_dir
        self.llm_log_saved_dir = os.path.join(self.collected_data_root_dir, llm_saved_folder_name) if self.enable_log else None
        self.vlm_log_saved_dir = os.path.join(self.collected_data_root_dir, vlm_saved_folder_name) if self.enable_log else None


def singleton(cls):
    # 用字典存储类与对应实例的映射
    instances = {}

    def wrapper(*args, **kwargs):
        # 如果类未实例化，则创建并缓存；否则返回缓存的实例
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return wrapper

@singleton
class ConfigurationReader(object):

    def __init__(self):
        self.root_dir = os.path.dirname(os.path.realpath(__file__))

        self.run_mode_configuration = configparser.ConfigParser()
        self.configuration = configparser.ConfigParser()

        try:
            run_mode_configuration_path = os.path.join(os.path.dirname(os.path.dirname(self.root_dir)), 'conf/run_mode_config.conf')
            self.run_mode_configuration.read(run_mode_configuration_path, encoding='utf-8')

            configuration_file_name = "run_benchmark_config.conf" if self.run_mode_configuration.get('RunConfig', 'mode') == 'test' else 'run_server_config.conf'
            configuration_path = os.path.join(os.path.dirname(os.path.dirname(self.root_dir)), f'conf/{configuration_file_name}')
            self.configuration.read(configuration_path, encoding='utf-8')
            print(f'----------------- configuration is read from: {configuration_path} -----------------')
        except FileNotFoundError:
            print("配置文件不存在！")
            exit(1)

class Config(object):

    def __init__(self):

        self.configuration_reader = ConfigurationReader()


        self.sliding_mode = self.configuration_reader.configuration.get('EvalConfig', 'sliding_mode')
        self.project = ProjectConfig(
            root_dir=self.configuration_reader.root_dir,
            mode = self.configuration_reader.configuration.get('ProjectConfig', 'mode'),
            sliding_mode=self.sliding_mode)

        model_config = self.configuration_reader.configuration
        self.model = ModelConfig(
            vlm_model_name=model_config.get('MLLMConfig', 'vlm_model_name'),
            vlm_model_url=model_config.get('MLLMConfig', 'vlm_model_url'),
            llm_model_name=model_config.get('MLLMConfig', 'llm_model_name'),
            llm_model_url=model_config.get('MLLMConfig', 'llm_model_url'),
            vlm_api_key=model_config.get('MLLMConfig', 'vlm_api_key', fallback=''),
            llm_api_key=model_config.get('MLLMConfig', 'llm_api_key', fallback=''),
            vlm_api_key_env=model_config.get('MLLMConfig', 'vlm_api_key_env', fallback='MLOPS_API_KEY'),
            llm_api_key_env=model_config.get('MLLMConfig', 'llm_api_key_env', fallback='MLOPS_API_KEY'),
            include_top_k=model_config.getboolean('MLLMConfig', 'include_top_k', fallback=True),
            request_timeout=model_config.getint('MLLMConfig', 'request_timeout', fallback=120),
        )
        if self.project.PREDICATE_MODE == 'test':
            self.benchmark_dir = self.configuration_reader.configuration.get('EvalConfig', 'benchmark_dir')
            self.max_workers = self.configuration_reader.configuration.getint('EvalConfig', 'max_workers')
            self.max_samples = self.configuration_reader.configuration.getint('EvalConfig', 'max_samples')
            self.data = DataConfig(mode=self.configuration_reader.configuration.get('ProjectConfig', 'mode'),
                                   root_dir=self.configuration_reader.configuration.get('EvalConfig', 'eval_output_dir'),
                                   sliding_mode=self.sliding_mode,
                                   output_suffix=self.configuration_reader.configuration.get('EvalConfig', 'output_suffix'))

            llm_saved_folder_base_name = f"LLM_SLD{self.sliding_mode}_{self.configuration_reader.configuration.get('MLLMDataCollectorConfig', 'llm_saved_folder_suffix')}"
            vlm_saved_folder_base_name = f"VLM_SLD{self.sliding_mode}_{self.configuration_reader.configuration.get('MLLMDataCollectorConfig', 'vlm_saved_folder_suffix')}"
            self.mllm_data_collector = MLLMDataCollectorConfig(
                collected_data_root_dir=self.configuration_reader.configuration.get('MLLMDataCollectorConfig', 'collected_data_root_dir'),
                llm_saved_folder_name=llm_saved_folder_base_name,
                vlm_saved_folder_name=vlm_saved_folder_base_name,
                enable_log=self.configuration_reader.configuration.getboolean('MLLMDataCollectorConfig', 'enable_log')
            )
        else:
            self.data = DataConfig(mode=self.configuration_reader.configuration.get('ProjectConfig', 'mode'),
                                   sliding_mode=self.sliding_mode)


if __name__ == '__main__':
    pass

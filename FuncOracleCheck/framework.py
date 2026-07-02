import os
from logging.config import DictConfigurator
from GUI_TestFramework_v1 import scripts
from utils import json_utils


def sequence_test(config: scripts.config.Config):
    if config.project.PREDICATE_MODE == 'test':
        saved_path = os.path.join(config.data.OUTPUT_DIR, f'{os.path.basename(config.data.DATA_DIR)}.json')
        if os.path.exists(saved_path):
            print(f"path: {saved_path} already exists, skip this task!")
            return

        print(f"running single sequence bench-test from: {config.data.OUTPUT_DIR}...")

    e2eTest = scripts.sequence.HarmonyAppTest(config)
    if len(e2eTest.json_data['seq_info']) == 1:
        e2eTest.single_image_processing(sequence_id=0)
        print(e2eTest.result_format_align())
    else:
        e2eTest.ab_pages_validate()
        e2eTest.child_sequence_router()
        e2eTest.test_result()
        print(e2eTest.result_format_align())


def page_test(sample_dict: dict):
    newtest = scripts.single_step.HarmonyAPPSingleStepTest(sample_dict)
    print(newtest.run())


if __name__ == '__main__':
    config_main = scripts.config.Config()
    json_data = json_utils.load_json(r'D:\FuncOracleCheck\GUI_TestFramework_v1\examples\00ba4f13-c721-4491-83c1-b1c22db30e91#1755832141541\data1.json')
    config_main.data.METADATA = json_data
    sequence_test(config_main)

    pass

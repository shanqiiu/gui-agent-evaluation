import pandas as pd
import json
import os
from utils import json_utils

def json_to_excel(excel_file_path=None):
    """
    读取JSON文件并将app和任务id信息写入Excel文件

    参数:
        json_file_path (str): JSON文件的路径
        excel_file_path (str, 可选): 输出的Excel文件路径，默认为与JSON文件同名的xlsx文件
    """
    # 如果未指定Excel文件路径，则使用与JSON文件相同的名称和位置


    extracted_data = []

    #try:
        # 读取JSON文件
    root_dir = r'/home/zhehuan/Harmony_APP_TestFramework/benchmark_0827'
    for sample_dir in os.listdir(root_dir):
        json_name = sample_dir.split('#')[0]
        if os.path.exists(os.path.join(root_dir, sample_dir, json_name + '.json')):
            data = json_utils.load_json(os.path.join(root_dir, sample_dir, json_name + '.json'))


        # 检查是否包含必要的键
        if os.path.exists(os.path.join(root_dir, sample_dir, 'result', '8_28_9.json')):
            pd_data = json_utils.load_json(os.path.join(root_dir, sample_dir, 'result', '8_28_9.json'))
            for page in data[0]['seq_info']:
                if 'sign_step_verify' in page:
                    label = True if page['sign_step_verify'] else False
                    id = page['index']
                    pdt = True if pd_data['ab_pages_result'][str(id)]['label'] == '符合预期' else False
                    if pdt != label:
                        app = data[0].get('app_package_name', '')
                        task_id = data[0].get('任务id', '') or data[0].get('task_id', '')  # 支持两种可能的键名
                        page_index = page['index']
                        human_label = label
                        predict_value = pdt

                        extracted_data.append({'app': app, '任务id': task_id, '页面序号': page_index, '人类标签': human_label, '预测值': predict_value})

    # 创建DataFrame
    df = pd.DataFrame(extracted_data)

    # 写入Excel文件
    df.to_excel(excel_file_path, index=False)
    print(f"成功生成Excel文件: {excel_file_path}")

    #except Exception as e:
     #   print(f"发生错误: {str(e)}")

if __name__ == "__main__":
    # 示例用法
    # 请将此处的路径替换为你的JSON文件路径

    excel_file = r"/home/zhehuan/Harmony_APP_TestFramework/benchmark_0827_results/ab_page_false_data.xlsx"  # 输出的Excel文件

    # 调用函数进行转换
    json_to_excel(excel_file)

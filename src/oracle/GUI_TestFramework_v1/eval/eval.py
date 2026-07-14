import os
import sys
sys.path.append(r'D:\FuncOracleCheck')

from utils import json_utils
import traceback
from tqdm import tqdm
import argparse

result_dir = r'D:\benchmark\Benchmark_100_results\0925_mix\output_SLDMIX_bench0904_eval0917'
labeled_dir = r'D:\benchmark\Benchmark_100'



parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter  # 显示默认值
)
parser.add_argument(
    "--single_image_exc_flag",
    action="store_true",  # 是否排除单张图片的序列
)
parser.add_argument(
    "--no_problem_flag",
    action="store_true",  # 是否只测评小艺决策正确的序列
)
parser.add_argument(
    "--intention_flag",
    action="store_true",  # 存在该参数则为True，否则False
)

parser.add_argument(
    "--mode",
    default="llm",  # 滑窗模式:llm/vlm/mix
)

args = parser.parse_args()

MODE = args.mode if args.mode != 'mix' else 'llm'


total_intention_ok = 0
total_intention_nok = 0

total_step_ok = 0
total_step_nok = 0

total_step_all_ok = 0
total_step_not_all_ok = 0

total_ab_ok = 0
total_ab_nok = 0

intention_tp = 0
intention_fp = 0
intention_tn = 0
intention_fn = 0

step_tp = 0
step_tn = 0
step_fp = 0
step_fn = 0

total_step_tp = 0
total_step_tf = 0
total_step_fp = 0
total_step_fn = 0

ab_tp = 0
ab_tn = 0
ab_fp = 0
ab_fn = 0

cnt = 0

cnt_t = 0
cnt_f = 0

cnt_ab_f = 0


def join_path_if_exists(path_list: list[str], a: str) -> str | None:
    """
    检查文件/目录A是否存在于path_list中的某个路径下，
    如果存在则返回os.path.join(path, A)的结果，否则返回None

    参数:
        path_list: 路径列表，如 ['/home/user', '/tmp', 'data/']
        a: 要检查的文件/目录名，如 'file.txt'

    返回:
        拼接后的完整路径（第一个匹配的路径），或None（如果均不存在）
    """
    for path in path_list:
        # 拼接路径
        full_path = os.path.join(path, a)
        # 检查拼接后的路径是否存在
        if os.path.exists(full_path):
            return full_path
    # 如果所有路径都不包含A，返回None
    return None


cnt_intention_ = 0
cnt_step_ = 0
cnt_page_ = 0
for sample in tqdm(os.listdir(labeled_dir)):
    ALL_STEP_FLAG_GT = False
    label_json = json_utils.load_json(os.path.join(labeled_dir, sample, f'{sample.split("#")[0]}.json'))
    if os.path.exists(os.path.join(labeled_dir, sample, f'{sample.split("#")[0]}.json')):
        if 'seq_info_correctness' not in label_json[0]:
            cnt_intention_ += 1
            continue
        if label_json[0]['seq_info_correctness'] == '':
            cnt_intention_ += 1
            continue
        if any('step_verify' not in step for step in label_json[0]['step_maps']):
            cnt_step_ += 1
            continue
        if any(label['step_verify'] == '' for label in label_json[0]['step_maps']):
            cnt_step_ += 1
            continue
        if len(label_json[0]['seq_info']) >= 1:
            if any('sign_step_verify' not in seq for seq in label_json[0]['seq_info'][:-1]):
                cnt_page_ += 1
                continue
            if any(label['sign_step_verify'] == '' for label in label_json[0]['seq_info'][:-1]):
                cnt_page_ += 1
                continue

        if args.single_image_exc_flag and len(label_json[0]['seq_info']) <= 1:
            continue
        if args.no_problem_flag and label_json[0]['ex_parm'] != '存疑_1':
            continue
        for step in label_json[0]['step_maps']:
            if any(keyword in step['step_text'].lower() for keyword in ['金刚', 'feed', '信息流']):
                label_json[0]['step_maps'].remove(step)
        try:
            if label_json[0]['seq_info_correctness']:
                total_intention_ok += 1
            else:
                total_intention_nok += 1
            for step in label_json[0]['step_maps']:
                if step['step_verify']:
                    total_step_ok += 1
                else:
                    total_step_nok += 1
            if all(step['step_verify'] for step in label_json[0]['step_maps']):
                total_step_all_ok += 1
                ALL_STEP_FLAG_GT = True
            else:
                total_step_not_all_ok += 1

            if len(label_json[0]['seq_info']) > 1:
                for seq in label_json[0]['seq_info'][:-1]:
                    if seq['sign_step_verify']:
                        total_ab_ok += 1
                    else:
                        total_ab_nok += 1

            if os.path.exists(os.path.join(result_dir, f'{sample}.json')):
                result_json = json_utils.load_json(os.path.join(result_dir, f'{sample}.json'))
                #vlm_result_json = json_utils.load_json(os.path.join(vlm_result_dir, f'{sample}.json'))
                # result_json = json_utils.load_json(join_path_if_exists(result_dir, f'{sample}.json'))
                if label_json[0]['seq_info_correctness']:
                    if args.mode != 'mix':
                        if result_json['intention']['label'] == 'nok':
                            intention_fn += 1
                            # print(sample)
                        else:
                            intention_tp += 1
                    else:
                        if result_json['intention']['label'] == 'nok' or \
                                result_json['vlm_intention_step'][f'step_{len(label_json[0]["step_maps"])}']['label'] == 'nok':
                            intention_fn += 1
                        else:
                            intention_tp += 1
                if not label_json[0]['seq_info_correctness']:
                    # if result_json['intention']['label'] == 'nok' or not \
                    # vlm_result_json['intention_step'][f'step_{len(label_json[0]["step_maps"])}']['label'] == 'nok':
                    if args.mode != 'mix':
                        if result_json['intention']['label'] == 'nok':
                            intention_tn += 1
                        else:
                            intention_fp += 1
                    else:
                        if result_json['intention']['label'] == 'nok' or not \
                            result_json['vlm_intention_step'][f'step_{len(label_json[0]["step_maps"])}']['label'] == 'nok':
                            intention_tn += 1
                        else:
                            intention_fp += 1

                step_id = 1
                for step in label_json[0]['step_maps']:
                    if step['step_verify']:
                        if result_json[f'{MODE}_intention_step'][f'step_{step_id}']['label'] == 'nok':
                            if args.mode != 'mix':
                                step_fn += 1
                            else:
                                if result_json[f'vlm_intention_step'][f'step_{step_id}']['label'] == 'nok':
                                    step_fn += 1
                                else:
                                    step_tp += 1
                        else:
                            step_tp += 1
                    else:
                        if result_json[f'{MODE}_intention_step'][f'step_{step_id}']['label'] == 'nok':
                            step_tn += 1
                        else:
                            step_fp += 1
                    step_id += 1

                if len(label_json[0]['seq_info']) > 1:
                    for i, seq in enumerate(label_json[0]['seq_info'][:-1]):
                        if seq['sign_step_verify']:
                            if result_json['ab_pages_result'][str(seq['index'])]['label'] in ['符合预期', '无法判定']:
                                ab_tp += 1

                            else:
                                ab_fn += 1

                                cnt_ab_f += 1

                        if not seq['sign_step_verify']:
                            if result_json['ab_pages_result'][str(seq['index'])]['label'] == '符合预期':
                                ab_fp += 1
                                cnt_ab_f += 1

                            else:
                                ab_tn += 1

                if ALL_STEP_FLAG_GT:

                    if result_json[f'{MODE}_intention_step_identity']['label'] == 'nok':
                        #if vlm_result_json[f'{MODE}_intention_step_identity']['label'] == 'nok':
                        if args.mode != 'mix':
                            total_step_fn += 1
                        else:
                            if result_json[f'vlm_intention_step_identity']['label'] == 'nok':
                                total_step_fn += 1
                            else:
                                total_step_tp += 1
                        # else:
                        #     total_step_tp += 1
                        # if label_json[0]['ex_parm'] == '存疑':
                        #    print(sample.split("#")[0])
                    else:
                        total_step_tp += 1

                else:
                    if result_json[f'{MODE}_intention_step_identity']['label'] == 'ok':
                        total_step_fp += 1
                    else:
                        total_step_tf += 1
        except Exception as e:
            pass
            # print(sample, e)

            cnt += 1


# 计算评价指标（处理分母为0的情况）
def safe_divide(numerator, denominator):
    """安全除法，避免除零错误"""
    return numerator / denominator if denominator != 0 else 0.0


# 意图层面指标
intention_true_precision = safe_divide(intention_tp, intention_tp + intention_fp)
intention_true_recall = safe_divide(intention_tp, intention_tp + intention_fn)
intention_false_precision = safe_divide(intention_tn, intention_tn + intention_fn)
intention_false_recall = safe_divide(intention_tn, intention_tn + intention_fp)
intention_accuracy = safe_divide(intention_tp + intention_tn,
                                 intention_tp + intention_tn + intention_fp + intention_fn)

# 步骤层面指标
step_true_precision = safe_divide(step_tp, step_tp + step_fp)
step_true_recall = safe_divide(step_tp, step_tp + step_fn)
step_false_precision = safe_divide(step_tn, step_tn + step_fn)
step_false_recall = safe_divide(step_tn, step_tn + step_fp)
step_accuracy = safe_divide(step_tp + step_tn,
                            step_tp + step_tn + step_fp + step_fn)

# 路径一致性指标
total_step_true_precision = safe_divide(total_step_tp, total_step_tp + total_step_fp)
total_step_true_recall = safe_divide(total_step_tp, total_step_tp + total_step_fn)
total_step_false_precision = safe_divide(total_step_tf, total_step_tf + total_step_fn)
total_step_false_recall = safe_divide(total_step_tf, total_step_tf + total_step_fp)
total_step_accuracy = safe_divide(total_step_tp + total_step_tf,
                                  total_step_tp + total_step_tf + total_step_fp + total_step_fn)

# 单步层面指标
ab_true_precision = safe_divide(ab_tp, ab_tp + ab_fp)
ab_true_recall = safe_divide(ab_tp, ab_tp + ab_fn)
ab_false_precision = safe_divide(ab_tn, ab_tn + ab_fn)
ab_false_recall = safe_divide(ab_tn, ab_tn + ab_fp)
ab_accuracy = safe_divide(ab_tp + ab_tn,
                          ab_tp + ab_tn + ab_fp + ab_fn)

print(cnt_intention_, cnt_step_, cnt_page_)

# 格式化打印结果
print(cnt_ab_f)
print(f'共有{cnt}样本未被统计')
print("=" * 60)
print("测试结果统计指标")
print("=" * 60)

print("\n【意图层面统计】")
print(f"总意图正确样本数: {total_intention_ok}")
print(f"总意图错误样本数: {total_intention_nok}")
print(f"意图TP（真阳性）: {intention_tp}")
print(f"意图TN（真阴性）: {intention_tn}")
print(f"意图FP（假阳性）: {intention_fp}")
print(f"意图FN（假阴性）: {intention_fn}")
print(f"意图正样本精确率（Precision）: {intention_true_precision:.4f}")
print(f"意图正样本召回率（Recall）: {intention_true_recall:.4f}")
print(f"意图负样本精确率（Precision）: {intention_false_precision:.4f}")
print(f"意图负样本召回率（Recall）: {intention_false_recall:.4f}")
print(f"意图准确率（Accuracy）: {intention_accuracy:.4f}")

print("\n【子意图功能完备度统计】")
print(f"步骤正确数: {total_step_ok}")
print(f"步骤错误数: {total_step_nok}")
print(f"步骤TP（真阳性）: {step_tp}")
print(f"步骤TN（真阴性）: {step_tn}")
print(f"步骤FP（假阳性）: {step_fp}")
print(f"步骤FN（假阴性）: {step_fn}")
print(f"步骤正样本精确率（Precision）: {step_true_precision:.4f}")
print(f"步骤正样本召回率（Recall）: {step_true_recall:.4f}")
print(f"步骤负样本精确率（Precision）: {step_false_precision:.4f}")
print(f"步骤负样本召回率（Recall）: {step_false_recall:.4f}")
print(f"步骤准确率（Accuracy）: {step_accuracy:.4f}")

print("\n【功能路径体验一致性完备度统计】")
print(f"路径体验一致正确样本数: {total_step_all_ok}")
print(f"路径体验一致错误样本数: {total_step_not_all_ok}")
print(f"路径体验一致预测TP: {total_step_tp}")
print(f"路径体验一致预测TN: {total_step_tf}")
print(f"路径体验一致预测FP: {total_step_fp}")
print(f"路径体验一致预测FN: {total_step_fn}")
print(f"路径体验一致正样本精确率（Precision）: {total_step_true_precision:.4f}")
print(f"路径体验一致正样本召回率（Recall）: {total_step_true_recall:.4f}")
print(f"路径体验一致负样本精确率（Precision）: {total_step_false_precision:.4f}")
print(f"路径体验一致负样本召回率（Recall）: {total_step_false_recall:.4f}")
print(f"路径体验一致准确率（Accuracy）: {total_step_accuracy:.4f}")

print("\n【单步跳转可用性统计】")
print(f"AB正确跳转数: {total_ab_ok}")
print(f"AB错误跳转数: {total_ab_nok}")
print(f"AB预测TP: {ab_tp}")
print(f"AB预测TN: {ab_tn}")
print(f"AB预测FP: {ab_fp}")
print(f"AB预测FN: {ab_fn}")
print(f"AB正样本精确率（Precision）: {ab_true_precision:.4f}")
print(f"AB正样本召回率（Recall）: {ab_true_recall:.4f}")
print(f"AB负样本精确率（Precision）: {ab_false_precision:.4f}")
print(f"AB负样本召回率（Recall）: {ab_false_recall:.4f}")
print(f"AB准确率（Accuracy）: {ab_accuracy:.4f}")

print("\n" + "=" * 60)

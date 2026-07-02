import re


def parse_steps(step_string):
    """
    解析包含多个步骤的字符串，支持多种分隔方式

    参数:
        step_string (str): 包含多个步骤的字符串

    返回:
        list: 解析后的步骤列表
    """
    # 去除字符串首尾的空白字符
    step_string = step_string.strip()

    # 检查是否使用->作为分隔符
    if '->' in step_string:
        steps = [step.strip() for step in step_string.split('->') if step.strip()]
        return steps

    # 检查是否使用数字加点(1. 2.)作为分隔符
    if re.search(r'\d+\.', step_string):
        # 使用正则表达式分割，保留步骤内容
        steps = re.split(r'\d+\.\s*', step_string)
        # 过滤空字符串并去除每个步骤的空白
        return [step.strip() for step in steps if step.strip()]

    # 检查是否使用数字加顿号(1、2、)作为分隔符
    if re.search(r'\d+、', step_string):
        # 使用正则表达式分割，保留步骤内容
        steps = re.split(r'\d+、\s*', step_string)
        # 过滤空字符串并去除每个步骤的空白
        return [step.strip() for step in steps if step.strip()]

    # 如果没有识别到任何分隔符，返回包含整个字符串的列表
    return [step_string]

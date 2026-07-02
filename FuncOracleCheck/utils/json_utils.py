import os
import re
import sys
import time
import json
import random
import numpy as np
import jpype
from json.decoder import JSONDecodeError


def default_serializer(obj):
    # 检查对象是否是 Java 类型
    if isinstance(obj, jpype.JClass("java.lang.String")):
        return str(obj)  # 转换为 Python 字符串
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def load_json(src_=None):
    with open(src_, 'r', encoding='utf-8') as f:
        data_ = json.load(f)
    f.close()
    return data_


def dump_json(data_=None, tar_=None, indent_=4, ensure_ascii=False, default=None):
    json.dumps(data_)
    with open(tar_, 'w', encoding='utf-8') as f:
        if indent_ is not None:
            json.dump(data_, f, indent=indent_, default=default, ensure_ascii=ensure_ascii)
        else:
            json.dump(data_, f, default=default, ensure_ascii=ensure_ascii)
    f.close()


def save_as_npy(tar_path: str = None,
                data: np.ndarray = None):
    np.save(tar_path, data)


def load_from_npy(src_path: str = None):
    data = np.load(src_path)
    return data


def extract_json_from_string(text: str = None):
    """
    终极版JSON解析函数，通过精确位置追踪解决嵌套引号导致的截断问题
    即使格式严重错误也能提取完整内容
    """
    if not text:
        return None

    # 定位JSON对象边界
    start_brace = text.find('{')
    end_brace = text.rfind('}')
    if start_brace == -1 or end_brace == -1 or start_brace >= end_brace:
        print(f"没有找到有效的JSON结构")
        return None  # 没有找到有效的JSON结构
    json_content = text[start_brace:end_brace + 1]

    # 定位所有键值对
    key_value_pairs = {}
    current_pos = 0  # 跟踪当前解析位置，避免重复解析

    # 找到所有可能的键，改进正则表达式以更好地匹配键
    key_pattern = re.compile(r'["“]([^"“”]+)["”]\s*:')

    while True:
        # 从当前位置开始查找下一个键
        key_match = key_pattern.search(json_content, current_pos)
        if not key_match:
            break  # 没有更多键了

        key = key_match.group(1).strip()
        key_start = key_match.start()
        key_end = key_match.end()
        current_pos = key_end  # 更新当前位置

        # 找到值的起始位置（跳过可能的空格）
        value_start = key_end
        while value_start < len(json_content) and json_content[value_start].isspace():
            value_start += 1

        if value_start >= len(json_content):
            break  # 超出范围

        # 处理不同类型的值
        value = None
        value_end = -1
        current_char = json_content[value_start]

        # 处理字符串类型的值（带引号）
        if current_char in ['"', '“']:
            quote_type = current_char
            end_pos = value_start + 1
            escape_mode = False
            nested_quote_count = 0  # 跟踪嵌套引号数量

            while end_pos < len(json_content):
                current_char = json_content[end_pos]

                if escape_mode:
                    escape_mode = False
                    end_pos += 1
                    continue

                if current_char == '\\':
                    escape_mode = True
                    end_pos += 1
                    continue

                # 处理引号
                if current_char in ['"', '“', '”']:
                    if current_char == quote_type or (quote_type == '"' and current_char == '”'):
                        if nested_quote_count == 0:
                            break  # 找到匹配的结束引号
                        else:
                            nested_quote_count -= 1
                    else:
                        nested_quote_count += 1

                end_pos += 1

            # 提取值内容
            value = json_content[value_start + 1:end_pos].strip()
            value_end = end_pos + 1  # 移动到引号之后

            # 清理值中的转义符和多余引号
            value = value.replace('\\', '').replace('"', '').replace('“', '').replace('”', '').replace("'", "")

        # 处理非字符串类型的值（数字、布尔值、null、对象、数组）
        else:
            # 查找值的结束位置（逗号或右括号）
            end_pattern = re.compile(r'[,}]')
            end_match = end_pattern.search(json_content, value_start)
            if end_match:
                value_end = end_match.start()
                value = json_content[value_start:value_end].strip()
            else:
                value_end = len(json_content)
                value = json_content[value_start:].strip()

        # 将提取的值添加到字典
        if value is not None:
            key_value_pairs[key] = value

        # 更新当前位置到值的结束之后
        if value_end != -1:
            current_pos = value_end
        else:
            break  # 无法确定值的结束位置，退出循环

    return key_value_pairs if key_value_pairs else None


def extract_thought_and_answer(text: str) -> dict:
    """
    从文本中提取Thought（思考过程）和Answer（结果）
    :param text: 包含Thought和Answer的原始文本
    :return: 字典，键为"thought"和"answer"，值为对应提取内容
    """
    result = {"ActionDescription": "", "Thought": "", "Answer": ""}
    if not text:
        return result  # 处理空文本情况

    # 1. 提取Thought：从"Thought:"开始，到"Answer:"之前结束
    ad_start = text.find("ActionDescription:")
    thought_start = text.find("Thought:")
    answer_start = text.find("Answer:")
    if ad_start != -1 and thought_start != -1:
        result["ActionDescription"] = text[ad_start + len("ActionDescription:"): thought_start].strip()
    if thought_start != -1 and answer_start != -1:
        # 截取"Thought:"之后、"Answer:"之前的内容，并去除前后多余空格/换行
        result["Thought"] = text[thought_start + len("Thought:"): answer_start].strip()

    # 2. 提取Answer：从"Answer:"开始到文本结束
    if answer_start != -1:
        result["Answer"] = text[answer_start + len("Answer:"):].strip()

    return result


if __name__ == '__main__':
    string_main1 = """message: ```json
{
    "page_description": "这是一个社交媒体界面的截图，显示了一张照片和相关评论。照片中有两个人，一个穿着粉色连衣裙的女性和一个穿着黑色无袖上衣和白色短裤的男性，男性手臂上有纹身。照片上方有一个女性厕所的标识。界面底部有一个标签栏，当前选中的标签是“精选”。界面右侧显示了点赞数（8.5万）、评论数（5578）和转发数（8593）。评论区显示了用户名“@倩姐(收徒)”以及评论内容：'女孩这样打扮，是会被别人误会的 #喜爱度激励计划 #太搞笑 #看一遍笑一...展开'。底部还显示了相关搜索关键词：'打扮像男生的女生'。"
}
```"""

    string_main2 = """message: ```json
    {
        "page_description": "这是一个社交媒体界面的截图，显示了一张照片和相关评论。照片中有两个人，一个穿着粉色连衣裙的女性和一个穿着黑色无袖上衣和白色短裤的男性，男性手臂上有纹身。照片上方有一个女性厕所的标识。界面底部有一个标签栏，当前选中的标签是“精选”。界面右侧显示了点赞数（8.5万）、评论数（5578）和转发数（8593）。评论区显示了用户名“@倩姐(收徒)”以及评论内容：'女孩这样打扮，是会被别人误会的 #喜爱度激励计划 #太搞笑 #看一遍笑一...展开'。底部还显示了相关搜索关键词：'打扮像男生的女生'。
        "
    }
    ```"""

    string_main3 = """### 分析与推理过程

#### **1. 操作意图拆解**
用户的操作意图是：**在首页短剧模块长按屏幕选择功能**。
这个意图可以拆解为以下子步骤：
- **进入短剧模块**：用户需要从首页进入短剧模块。
- **选择短剧**：用户需要点击某个短剧的封面进入短剧详情页面。
- **长按屏幕**：在短剧详情页面，用户需要执行长按屏幕的操作。

因此，拆解后的子意图是：
```
进入短剧模块 -> 选择短剧 -> 长按屏幕
```

#### **2. 操作序列分析**
根据提供的操作序列：
- **第一步**：用户在首页点击了短剧《将军府茶香四溢》的封面控件，进入了短剧详情页面。
- **第二步**：用户在短剧详情页面执行了长按屏幕的操作。

#### **3. 预期结果分析**
- **预期最后一步操作**：长按屏幕。
- **预期页面内容**：长按屏幕后，页面应该显示与长按功能相关的选项或菜单。例如，可能弹出一个浮动菜单，提供诸如“投屏”、“收藏”、“分享”等功能选项。

#### **4. 实际结果分析**
- **最后一步操作**：用户确实执行了长按屏幕的操作。
- **最后页面内容**：从提供的页面截图来看，长按屏幕后，页面背景发生了变化（从红色蜡烛变为金色珠帘），但页面的功能布局、右侧的追剧、评论、点赞按钮，以及底部的“选集 · 已完结 · 全62集”标签均未发生变化。此外，页面上没有出现任何与长按功能相关的选项或菜单。

#### **5. 比较预期与实际**
- **预期操作**：长按屏幕后，应该出现与长按功能相关的选项或菜单。
- **实际操作**：长按屏幕后，页面背景发生变化，但未出现任何功能选项或菜单。

#### **6. 用户数据缺失分析**
- 本操作意图不涉及用户数据（如订单、收藏、缓存、点赞记录、消息等）。因此，无需考虑用户数据缺失的问题。

### **最终判断**
- **预期最后一步操作是否被执行**：是的，用户执行了长按屏幕的操作。
- **是否进入预期页面**：否，长按屏幕后未出现预期的功能选项或菜单。

### **输出结果**
```json
{
    "intention": "进入短剧模块 -> 选择短剧 -> 长按屏幕",
    "expected_action": "执行",
    "expected_page": "长按屏幕后，页面应显示与长按功能相关的选项或菜单，例如投屏、收藏、分享等功能。",
    "data_preset": "无",
    "thought": "用户意图被拆解为三个子步骤：进入短剧模块、选择短剧、长按屏幕。用户成功执行了前两步，进入了短剧详情页面，并执行了长按屏幕操作。然而，长按屏幕后未出现预期的功能选项或菜单，因此未满足操作意图。",
    "answer": "未达成意图"
}
```"""

    string_main4 = """```json
{
    "page_description": "界面显示了一个社交媒体页面，包含两条帖子。第一条帖子标题为'比亚迪海洋（赣州金顺4S店）'，内容与车机导航设置相关，显示了一个车机屏幕，屏幕上有一个红色的信号图标。第二条帖子标题为'Driven997'，内容与抖音导航栏教程相关，显示了一个车机屏幕的导航栏。",
    "Thought": "首先，界面内容清晰，没有显示任何'页面正在加载'的提示或加载图标，因此可以排除'加载中'的情况。其次，界面也没有显示'页面加载失败'或网络报错的提示，因此可以排除'加载失败'的情况。再次，界面内容清晰，没有模糊或半透明的质感，因此可以排除'毛玻璃'的情况。最后，界面内容完整，显示了两条帖子及其相关信息，没有异常，因此判定为'正常'。",
    "Answer": "正常"
}
```"""

    print(extract_json_from_string(text=string_main1))
    print(extract_json_from_string(text=string_main2))
    print(extract_json_from_string(text=string_main3))
    print(extract_json_from_string(text=string_main4))
    pass


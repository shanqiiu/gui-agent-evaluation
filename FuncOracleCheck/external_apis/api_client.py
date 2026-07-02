import os
import json
import time
import requests
from config import SCENE_CLS_URL, OBJECT_DETECT_URL, OCR_URL, POPUP_TEXT_CLS
from utils.cv_utils import encode_image_to_base64

os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""


# 访问场景分类模型
def get_scene_cls(obj={}):
    """

    :param obj: 这个是个字典类型的参数，例子：{"text": "首页 发现 搜索 我的", "path":"图像的存储路径"}
    Returns: 示例 [{'scene': '加载页', 'score': 0.998}]， 可能是多个标签，所以用list

    """
    para = {"text": obj["text"], "image_base64": encode_image_to_base64(obj["path"])}
    label = {
        0: '短视频', 1: '朋友圈', 2: '扫一扫', 3: '小窗口视频播放', 4: '语音通话', 5: '全屏视频播放', 6: '权限申请',
        7: '拍照', 8: '隐私-内容', 9: '搜索', 10: '嵌入式广告', 11: '商品列表-两列', 12: '导航', 13: '弹窗广告',
        14: '引导页', 15: '隐私-弹窗', 16: '新闻列表', 17: '地图浏览', 18: '商品列表-单列', 19: '新闻详情',
        20: '视频通话', 21: '全屏广告', 22: '登录', 23: '加载页', 24: '弹窗', 25: '视频播放'
    }
    for reply in range(3):
        try:
            response = requests.request("post", SCENE_CLS_URL, json=para, timeout=100, verify=False)
            # [{'scene': '加载页', 'score': 0.998}]
            return [i for i in response.json()['data']['results']]
        except Exception as e:
            print(e.__str__())
            print("调用场景分类模型失败，尝试{}次".format(reply + 1))
            time.sleep(1)
    return None


# 访问目标检测模型
def get_obj(image_path_list=[], image_base64_list=[]):
    """
    :param image_path_list:图像路径
    :param image_base64_list:图像的base64
    :return: 例子[[{'bottom': 477, 'class': 'channel', 'class_zh': '频道列表', 'left': 96, 'probability': 0.85, 'right': 1131, 'top': 317}]]
    """
    headers = {'Content-Type': 'application/json'}
    if image_base64_list:
        para = json.dumps({"images": image_base64_list})
    elif image_path_list:
        para = json.dumps({"images": [encode_image_to_base64(image) for image in image_path_list]})
    else:
        return None
    for reply in range(3):
        try:
            response = requests.request("post", OBJECT_DETECT_URL, headers=headers, data=para, timeout=100,
                                        verify=False).json()
            return response["data"]["results"]
        except Exception as e:
            print(e.__str__())
            print("调用目标检测模型失败，尝试{}次".format(reply + 1))
            time.sleep(1)
    return None


def format_internal_ocr(ocr_text, ocr_type):
    """
    按以前的格式输出OCR内容，保证结果兼容调用的服务
    :param ocr_text:
    :param ocr_type:
    :return:
    """
    ocr_result = {"model": ocr_type, "words_result": []}
    ocr_text = json.loads(ocr_text)
    if ocr_text.get('err_no', 1) == 0:
        value = ocr_text.get('value', '')
        for v in value:
            item_count = 0
            target_item_list = []
            if isinstance(v, list):
                ocr_list = v
            elif isinstance(v, str):
                ocr_list = json.loads(v)
            else:
                continue

            for item in ocr_list:
                if len(item) > 0:
                    target_item = {'words': item[0]['text'],
                                   'confidence': item[0]['confidence'],
                                   'location': item[0]['box']}
                    target_item_list.append(target_item)
                    item_count = item_count + 1
            ocr_result.get('words_result').extend(target_item_list)
            # 因为只调用了一张图片，所以取到一个结果后 break
            break

    return ocr_result


def get_ocr(image_path=None, image_base64=None, is_text=False):
    image_base64 = image_base64 or encode_image_to_base64(image_path)

    payload = json.dumps({
        # "lang": ["korean"],
        "key": ["image"],
        "value": [image_base64]
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = None
    for i in range(10):
        response = requests.request("POST", OCR_URL, headers=headers, data=payload, timeout=100)
        if response.status_code == 200:
            break
        time.sleep(1)
    if response is None:
        raise ValueError("获取文本信息失败")
    result = format_internal_ocr(str(response.content, encoding='utf-8'), 'video_department')
    if is_text:
        text = [r["words"] for r in result['words_result']]
        text = sorted(list(set(text)), key=lambda word: (len(word), word))
        return " ".join(text)
    return result


def get_popuptext_cls(text):
    payload = json.dumps({'text': f'{text}'})

    headers = {
        'Content-Type': 'application/json'
    }
    for i in range(3):
        try:
            response = requests.request("POST", url=POPUP_TEXT_CLS, headers=headers, data=payload)
            result = json.loads(response.text)
            class_name = result.get("result")
            return class_name
        except Exception as e:
            print(e.__str__())
            time.sleep(1)
            print(f"访问弹窗文本分类模型报错，重试{i+1}次")
    return "normal"


if __name__ == '__main__':
    # text = "您的设备存储空间不足，无法下载该文件呀"
    # rs = get_popuptext_cls(text)
    # print(rs)
    # # path = "../screenshots/group-o-b05f550092ad410892850fda480a3baf.jpeg"
    path = "/home/limengqi/data/output_images/image_22.png"
    # # obj = {"text": "加载未成功（-5002） 如长时间未解决请反馈给我们 在试一次", "path": path}
    # # image_path_list = get_scene_cls(obj=obj)
    # # print(image_path_list)
    image_path_list = [path]
    result = get_obj(image_path_list=image_path_list)
    print(result)
    # res = get_ocr(image_path=path, is_text=False)
    # print(res)
    # pass

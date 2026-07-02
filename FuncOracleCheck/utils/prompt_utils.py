from . import cv_utils
import numpy as np
import os
import time

_VISUAL_PROMPT_SAVE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
    "visual_prompt_debug"
)
os.makedirs(_VISUAL_PROMPT_SAVE_DIR, exist_ok=True)

def make_action_description(data_item: dict = None):
    if data_item['parsed_action']['action_type'] == 'click':
        action_description = f"操作类型：点击"
    elif data_item['parsed_action']['action_type'] == 'long_press':
        action_description = f"操作类型：长按"
    elif data_item['parsed_action']['action_type'] in ['type', 'set_text']:
        action_description = (f"操作类型：输入\n"
                              f"输入内容：{data_item['parsed_action']['content']}")
    elif data_item['parsed_action']['action_type'] in ['scroll', 'drag', 'swipe']:
        action_description = f"操作类型：滑动"
    elif data_item['parsed_action']['action_type'] in ['wait', 'clarify','do-nothing']:
        action_description = f"操作类型：等待(即什么也不做，等待页面加载或切换完毕)"
    elif data_item['parsed_action']['action_type'] in ['finished', 'done']:
        action_description = f"操作类型：操作完成(不会进行任何操作)"
    elif data_item['parsed_action']['action_type'] == 'press_home':
        action_description = f"操作类型：返回手机桌面"
    elif data_item['parsed_action']['action_type'] == 'press_back':
        action_description = f"操作类型：返回上一页"
    else:
        action_description = f"操作类型：点击"
    return action_description


def make_label(original_label: [str, bool] = None):
    return "不符合预期" if original_label in ['点击无响应', '跳转错误', '不符合预期', False] else '符合预期'


def is_positive_label(label: [str, bool] = None):
    return label in ['跳转正确', '符合预期', True]


def make_visual_prompt(image: np.ndarray = None, parsed_action: dict = None, save_hint: str = ""):
    if "start_box" in parsed_action and parsed_action['start_box']:
        x1 = parsed_action["start_box"][0]
        y1 = parsed_action["start_box"][1]
        image_cv2_draw_circle_mask, color = cv_utils.draw_visible_circle(image=image,
                                                               x1=x1,
                                                               y1=y1,
                                                               radius=60)
        if "end_box" in parsed_action and parsed_action['end_box']:
            x2 = parsed_action["end_box"][0]
            y2 = parsed_action["end_box"][1]
            image_cv2_draw_circle_mask = cv_utils.draw_arrow(image=image_cv2_draw_circle_mask,
                                                             start_point=[x1, y1],
                                                             end_point=[x2, y2])
        # 保存标记图，方便检验标记结果
        if save_hint:
            import cv2
            ts = int(time.time() * 1000)
            filename = f"{save_hint}_{ts}.jpeg"
            cv2.imwrite(os.path.join(_VISUAL_PROMPT_SAVE_DIR, filename), image_cv2_draw_circle_mask)
        return image_cv2_draw_circle_mask, color

    else:
        if parsed_action['action_type'] in ['scroll', 'swipe'] and "direction" in parsed_action:
            if parsed_action["direction"] == 'down':
                image_cv2_draw_circle_mask = cv_utils.draw_arrow(image=image,
                                                                 start_point=[int(image.shape[1] / 2),
                                                                            int(image.shape[0] / 2)],
                                                                 end_point=[int(image.shape[1] / 2),
                                                                            int(image.shape[0] / 4)])
            elif parsed_action["direction"] == 'up':
                image_cv2_draw_circle_mask = cv_utils.draw_arrow(image=image,
                                                                 start_point=[int(image.shape[1] / 2),
                                                                              int(image.shape[0] / 2)],
                                                                 end_point=[int(image.shape[1] / 2),
                                                                            int(image.shape[0] * 3 / 4)])
            elif parsed_action["direction"] == 'right':
                image_cv2_draw_circle_mask = cv_utils.draw_arrow(image=image,
                                                                 start_point=[int(image.shape[1] / 2),
                                                                              int(image.shape[0] / 2)],
                                                                 end_point=[int(image.shape[1] / 4),
                                                                            int(image.shape[0] / 2)])
            elif parsed_action["direction"] == 'left':
                image_cv2_draw_circle_mask = cv_utils.draw_arrow(image=image,
                                                                 start_point=[int(image.shape[1] / 2),
                                                                              int(image.shape[0] / 2)],
                                                                 end_point=[int(image.shape[1] * 3 / 4),
                                                                            int(image.shape[0] / 2)])
            else:
                return image, None
            return image_cv2_draw_circle_mask, None

        else:
            # print('yes', parsed_action['action_type'])
            return image, None


if __name__ == '__main__':
    pass

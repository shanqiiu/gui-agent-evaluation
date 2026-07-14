from PIL import Image
from io import BytesIO
import base64
from collections import defaultdict
from external_apis import jar_parser, api_client
from library.logger import logger
from utils import layout_utils, json_utils, cv_utils


def crop_and_convert_to_base64(image_path, bound):
    # 打开图像
    with Image.open(image_path) as img:
        height, width = img.size
        # 裁剪图像
        cropped_img = img.crop(bound)
        # 将图像转换为字节流
        buffered = BytesIO()
        cropped_img.save(buffered, format="JPEG")
        # 转换为base64
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return img_base64, height, width


def split_crop_box(crop_box, n):
    x1, y1, x2, y2 = crop_box
    width = x2 - x1
    height = y2 - y1
    result = {"horizontal": [], "vertical": []}
    horizontal = []
    vertical = []
    if height > width:
        # 横向切分
        slice_height = height / n
        for i in range(n):
            new_y1 = y1 + i * slice_height
            new_y2 = new_y1 + slice_height
            vertical.append([x1, int(new_y1), x2, int(new_y2)])
        result["vertical"] = [[vertical]]
    else:
        # 纵向切分
        slice_width = width / n
        for i in range(n):
            new_x1 = x1 + i * slice_width
            new_x2 = new_x1 + slice_width
            horizontal.append([int(new_x1), y1, int(new_x2), y2])
        result["horizontal"] = [[horizontal]]
    return result


def get_menu_item_info(last_page_path, last_layout_path, obj_detect_reuslts, oper_widget_bounds, is_simple):
    layout_data = json_utils.load_json(last_layout_path)
    # 这个是解析layout中的所有的
    # bounds_list = layout_utils.get_bounds_from_layout(layout_data)
    # 这个是走的jar规则解析出来的bounds
    widget_info_list = jar_parser.filter_elements_v3(last_page_path, last_layout_path)

    obj_detect_reuslt = obj_detect_reuslts[0]
    obj_name_list = ["channel", "v_channel"]
    obj_names = [odr["class"] for odr in obj_detect_reuslt if odr["class"] in obj_name_list]
    obj_detect_reuslt = [odr for odr in obj_detect_reuslt if odr["class"] in obj_name_list]
    crop_box_list = []
    for odr in obj_detect_reuslt:
        crop_box = [odr['left'], odr['top'], odr['right'], odr['bottom']]
        crop_box_list.append(crop_box)
    # 如果不是简单模式而且widgetlist中没有解析出来控件，调用ocr服务辅助判断
    if not is_simple and not widget_info_list:
        for obj_name, crop_box in zip(obj_names, crop_box_list):
            widget_base64, img_height, img_width = crop_and_convert_to_base64(last_page_path, crop_box)
            ocr_result = api_client.get_ocr(image_base64=widget_base64, is_text=False)
            logger.info(
                f"{last_page_path}切割目标检测识别出来的tab bar bound的ocr的结果：{ocr_result}, {obj_name}, {crop_box}")
            words_result = ocr_result.get("words_result", [])
            avg_quantity = len(words_result)
            logger.info(f"{last_page_path}需要切割的份数量：{avg_quantity}。")
            if avg_quantity == 0:
                return {"horizontal": [], "vertical": []}
            result_menu_item_info = split_crop_box(crop_box, avg_quantity)
            logger.info(f"{last_page_path}基于ocr识别结果切割的bound结果：{result_menu_item_info}。")
            return result_menu_item_info

    bounds_list = [info['bounds'] for info in widget_info_list]
    bounds_list = cv_utils.filter_invalid_bounds(bounds_list, last_page_path)
    horizontal, vertical = find_aligned_boxes(bounds_list)
    result_data = {"horizontal": [horizontal], "vertical": []}
    logger.info(f"{last_page_path}规则从layout中找到的在同一条线上的bounds列表：{result_data}")
    return result_data

    logger.info(f"{last_page_path}使用规则识别的控件列表：{bounds_list}")
    crop_box_list_set = find_intersections(bounds_list, crop_box_list)
    result_menu_item_info = {"horizontal": [], "vertical": []}
    # [[[], []], [[], []]]  最外层是与channel1， channel2有交集的控件
    for crop_box in crop_box_list_set:
        result_horizontal, result_vertical = find_aligned_boxes(crop_box)
        if result_horizontal:
            result_menu_item_info["horizontal"].append(result_horizontal)
        if result_vertical:
            result_menu_item_info["vertical"].append(result_vertical)

    # {"horizontal": [], "vertical": []}
    return result_menu_item_info


def has_intersection(box1, box2):
    # box1 和 box2 格式为 [x1, y1, x2, y2]
    x1, y1, x2, y2 = box1
    x1_b, y1_b, x2_b, y2_b = box2

    # 判断是否有交集
    return not (x2 < x1_b or x2_b < x1 or y2 < y1_b or y2_b < y1)


def find_intersections(bounds_list, crop_box_list):
    results = []
    for crop_box in crop_box_list:
        intersecting_bounds = []
        for bounds in bounds_list:
            if has_intersection(crop_box, bounds):
                intersecting_bounds.append(bounds)
        results.append(intersecting_bounds)

    # [[[], []], [[], []]]  最外层是与channel1， channel1有交集的控件
    return results


def find_aligned_boxes(bounds_list):
    tolerance = 7
    # Step 1: Calculate area
    area_dict = defaultdict(list)
    for box in bounds_list:
        x1, y1, x2, y2 = box
        # area = (x2 - x1) * (y2 - y1)
        area = 1
        area_dict[area].append(box)

    # Step 2 and 3: Find aligned boxes
    result_horizontal = []
    result_vertical = []
    for boxes in area_dict.values():
        if len(boxes) > 1:
            # Check for horizontal alignment
            horizontal_align = defaultdict(list)
            for box in boxes:
                _, y1, _, y2 = box
                mid_idx = (y1 + y2) / 2
                # horizontal_align[(mid_idx, mid_idx)].append(box)
                found = False
                for key in horizontal_align:
                    if key[0] <= mid_idx <= key[1]:
                        horizontal_align[key].append(box)
                        found = True
                        break

                # If not found, create a new group
                if not found:
                    horizontal_align[(mid_idx - tolerance, mid_idx + tolerance)].append(box)

            for aligned_boxes in horizontal_align.values():
                if len(aligned_boxes) > 1:
                    result_horizontal.append(aligned_boxes)

            # Check for vertical alignment
            vertical_align = defaultdict(list)
            for box in boxes:
                x1, _, x2, _ = box
                mid_idx = (x1 + x2) / 2
                # vertical_align[(mid_idx, mid_idx)].append(box)
                found = False
                for key in vertical_align:
                    if key[0] <= mid_idx <= key[1]:
                        vertical_align[key].append(box)
                        found = True
                        break

                # If not found, create a new group
                if not found:
                    vertical_align[(mid_idx - tolerance, mid_idx + tolerance)].append(box)

            for aligned_boxes in vertical_align.values():
                if len(aligned_boxes) > 1:
                    result_vertical.append(aligned_boxes)

    return result_horizontal, result_vertical


def is_in_edge(image_path, bounds):
    # 打开图像以获取其尺寸
    image = Image.open(image_path)
    width, height = image.size

    # 提取边界框的坐标
    x1, y1, x2, y2 = bounds

    # 计算上下边缘的比例
    top_threshold = height * 0.04180
    bottom_threshold = height * 0.985

    # 判断是否在上边缘或下边缘
    is_top_edge = y1 <= top_threshold
    is_bottom_edge = y2 >= bottom_threshold

    is_edge = is_top_edge or is_bottom_edge
    return is_edge


# 求点击控件的bound与页面中控件列表存在交集的个数
def count_intersections(bound_list, bound):
    def has_intersection(b1, b2):
        # 检查两个框是否有交集
        x1, y1, x2, y2 = b1
        x3, y3, x4, y4 = b2
        return not (x2 < x3 or x4 < x1 or y2 < y3 or y4 < y1)

    count = 0
    for b in bound_list:
        if has_intersection(b, bound):
            count += 1
    return count


def empty_searchbar(layout_path, oper_widget_bounds):
    layout_json = json_utils.load_json(layout_path)
    layout_infos = layout_utils.get_information_from_layout(layout_json)
    bounds = layout_infos.get("bounds", [])
    texts = layout_infos.get("texts", [])
    types = layout_infos.get("types", [])
    hints = layout_infos.get("hints", [])

    oper_contain_text = ""
    for i, box in enumerate(bounds):
        if box == oper_widget_bounds:
            oper_contain_text += texts[i]
    searchfieldtext = ""
    for j, type in enumerate(types):
        if type == "SearchField":
            searchfieldtext += hints[j]
    logger.info(f"{layout_path}, 操作控件内的文本：{oper_contain_text}, 搜索输入框中的文本：{searchfieldtext}")
    if "搜索" in oper_contain_text and "请输入搜索内容" in searchfieldtext:
        return True
    else:
        return False






if __name__ == '__main__':
    bounds_list = [[423, 311, 629, 370], [785, 311, 941, 370], [217, 311, 423, 370], [629, 311, 785, 370],
                   [54, 301, 217, 380]]
    res = find_aligned_boxes(bounds_list)
    print(res)

from datetime import datetime
import os
import json
import time
import shutil
import zipfile
from utils import json_utils, layout_utils, cv_utils, handling_utils
from library.logger import logger
from config import *
from external_apis import api_client
from external_apis import jar_parser


class FunctionalOracleCheckerV3(object):

    def __init__(self, logger, no='1', redis_client=None, s3_client=None):
        self.logger = logger
        self.no_process = no
        self.in_process_task_id = ""
        self.redis_client = redis_client
        self.s3_client = s3_client

        # 弹窗错误的字典
        # with open("./vocab/popup_error.txt", "r", encoding="utf-8") as f:
        #     lines = f.readlines()
        # self.popup_error_keywords = [line.strip() for line in lines]
        self.popup_error_keywords = ['错误提示', 'UNAUTHORIZED', '网络连接错误', '服务器无响应', '请求超时', '无法加载',
                                     '未知错误', '解析错误', '操作失败', '稍后重试', '更新失败', '文件格式不支持',
                                     '存储空间不足', '无法访问此功能', '应用程序崩溃', '服务器错误', '无法连接到服务器',
                                     '版本不兼容', '数据同步失败', '上传失败', '下载失败', '无法操作', '错误码',
                                     'code:', 'not found']
        # 页面加载失败字典
        # with open("./vocab/load_error.txt", "r", encoding="utf-8") as f:
        #     lines = f.readlines()
        # self.load_error_keywords = [line.strip() for line in lines]
        self.load_error_keywords = ['加载失败', '这里竟然啥都没显示', '重新加载', '加载失败！', '加载失败!', '系统遇到问题']

    def oracle(self):
        jar_parser.load_jar_pkg()
        while True:
            task_infos = self.redis_client.pop_from_list(MESSAGE_QUEUE_NAME)
            if not task_infos:
                continue
            # try:
            self.logger.info(f"进程：{self.no_process}，消费者提取的数据：{task_infos}")
            pop_infos_json = json.loads(task_infos)
            task_id = pop_infos_json.get("task_id", "")
            self.in_process_task_id = task_id
            file_name = pop_infos_json.get("file_name", "")
            start_time = time.time()
            # obs下载文件
            save_dir = os.path.join(SVE_DIR, task_id)
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, file_name)

            self.logger.info(f"{task_id} - 正在下载文件：{file_name}")
            down_sucess = self.s3_client.download(file_name, save_path)
            if not down_sucess:
                logger.info(f"{task_id}下载失败！！！！")

                results_info = {
                    "reformattedResultDict": "",
                    "taskOther": "任务下载失败，请重新提交",
                }
                self.redis_client.set_value(task_id, json.dumps(results_info))

                continue
            self.logger.info(
                f"进程：{self.no_process}，task_id:{self.in_process_task_id},下载文件耗时:{time.time() - start_time}")
            extract_dir = os.path.join(save_dir, file_name.split('.')[0])
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(save_path, 'r') as zip_ref:
                # 解压文件到指定目录
                zip_ref.extractall(extract_dir)
            after_zip_time = time.time()
            diff_extracr = after_zip_time - start_time
            self.logger.info(
                f"进程：{self.no_process}，task_id:{self.in_process_task_id},解压文件耗时:{diff_extracr}")
            self.logger.info(
                f"进程：{self.no_process}，task_id:{self.in_process_task_id},ZIP文件解压完成:{extract_dir}")
            test_suites_path = os.path.join(extract_dir, "testSuites.json")
            # 进入oracle判定环节
            package_data = self.processing_flow(test_suites_path, extract_dir, task_id)
            self.logger.info(
                f"进程：{self.no_process}，task_id:{self.in_process_task_id},-检测总耗时:{time.time() - after_zip_time}")

            results_info = {
                "reformattedResultDict": package_data,
            }
            self.redis_client.set_value(task_id, json.dumps(results_info))

            # except Exception as e:
            #     print(f"进程：{self.no_process}，task_id:{self.in_process_task_id}, 捕捉异常:{e}")
            #     self.logger.info(f"进程：{self.no_process}，task_id:{self.in_process_task_id}, 捕捉异常:{e}")
            #     results_info = {
            #         "reformattedResultDict": "",
            #         "taskOther": e.__str__(),
            #     }
            #     self.redis_client.set_value(task_id, json.dumps(results_info))
            # finally:
            #     shutil.rmtree(save_dir)
            #     self.logger.info(f"进程：{self.no_process}，task_id:{self.in_process_task_id}, 成功删除文件:{save_dir}")

    def operation_chain_grouping(self, action_list):
        true_groups = []
        false_groups = []
        current_group = [action_list[0]]
        if len(action_list) == 1:
            if action_list[0]['deleteStep']:
                true_groups.append(current_group)
            else:
                false_groups.append(current_group)

        for i in range(1, len(action_list)):
            if action_list[i]['deleteStep'] == action_list[i - 1]['deleteStep']:
                current_group.append(action_list[i])
            else:
                if current_group[0]['deleteStep']:
                    true_groups.append(current_group)
                else:
                    false_groups.append(current_group)
                current_group = [action_list[i]]

        if current_group:
            if current_group[0]['deleteStep']:
                true_groups.append(current_group)
            else:
                false_groups.append(current_group)

        return false_groups

    def label_nodes(self, action_infos, extract_dir, task_id):
        for i, action_info in enumerate(action_infos):
            action_List = action_info.get('actionList', [])
            instruction = action_info.get('instruction', '')
            sub_video_path = action_info.get('videoPath', '')
            self.logger.info(
                f"进程：{self.no_process}，task_id:{self.in_process_task_id},处理第{i + 1}个用例，序列长度为：{len(action_List)}。")
            for step, action_item in enumerate(action_List):
                # 判断页面是否是加载中
                image_sub_path = action_item.get('screenshotPath', '')
                layout_sub_path = action_item.get('layoutPath', '')
                image_path = os.path.join(extract_dir, image_sub_path)
                if layout_sub_path:
                    layout_path = os.path.join(extract_dir, layout_sub_path)
                else:
                    layout_path = None

                # 黑白屏检测
                white_or_black = cv_utils.detect_monochrome_image(image_path, threshold=WHITE_BLACK_THRESHOLD)
                self.logger.info(f"{image_path}黑白屏检测结果：{white_or_black}")
                if white_or_black != "normal":
                    action_item['white_or_black'] = True
                    action_item['loading_page'] = False
                    action_item['load_error_page'] = False
                    action_item['popup_error'] = ""
                else:
                    action_item['white_or_black'] = False
                    scene_check_result = self.processing_scene(image_path, layout_path)
                    if scene_check_result == "加载中页面":
                        action_item['loading_page'] = True
                        action_item['load_error_page'] = False
                    elif scene_check_result == "加载失败页面":
                        action_item['load_error_page'] = True
                        action_item['loading_page'] = False
                    else:
                        action_item['loading_page'] = False
                        action_item['load_error_page'] = False

                    self.logger.info(
                        f"进程：{self.no_process}，task_id:{self.in_process_task_id}，{image_sub_path}的场景标签：{scene_check_result}")
                    # 页面弹窗报错检测
                    if not scene_check_result:
                        popup_error, popup_flag = self.processing_popup(image_path, layout_path)
                        action_item['popup_error'] = popup_error

                        # 如果当前页面没有弹窗当前页面到上一张截图直接的视频就是重点关注对象
                        # if not popup_flag and step != 0 and sub_video_path:
                        #     video_path = os.path.join(extract_dir, sub_video_path)
                        #     if os.path.exists(video_path):
                        #         sub_video_start_time = action_List[step - 1].get('videoScreenshotTime')
                        #         sub_video_end_time = action_List[step].get('videoScreenshotTime')
                        #         error_type, time_location = self.processing_frame(video_path, sub_video_start_time,
                        #                                                           sub_video_end_time,
                        #                                                           step_length=FRAME_STEP_LENGTH)
                        #         self.logger.info(
                        #             f"进程：{self.no_process}，task_id:{self.in_process_task_id}，帧的错误类型：{error_type}, 发生时间：{time_location}")
                        #         action_item['frame_error'] = error_type
                        #         action_item['frame_error_time_location'] = time_location
                    else:
                        action_item['popup_error'] = ""

    def oracle_loading(self, action_infos):

        instruct2reload_res = {}
        for i, action_info in enumerate(action_infos):
            action_List = action_info.get('actionList', [])
            if len(action_List) == 0:
                continue
            false_groups = self.operation_chain_grouping(action_List)
            for false_group in false_groups:
                if len(false_group) == 0:
                    continue
                if NUMBER_OF_ITEMS_IN_LOADING > len(false_group):
                    continue
                for l in range(0, len(false_group) - NUMBER_OF_ITEMS_IN_LOADING + 1):
                    sub_action_info = false_group[l:l + NUMBER_OF_ITEMS_IN_LOADING]
                    window_list = [ai['loading_page'] for ai in sub_action_info]
                    if all(window_list):
                        if i not in instruct2reload_res:
                            instruct2reload_res[i] = [(ai.get('screenshotPath', ''), ai.get('layoutPath', '')) for ai in
                                                      sub_action_info]
                        else:
                            instruct2reload_res[i].extend(
                                [(ai.get('screenshotPath', ''), ai.get('layoutPath', '')) for ai in sub_action_info])
        return instruct2reload_res

    def oracle_click_no_feedback(self, action_infos, extract_dir):
        instruct2click_res = {}
        for i, action_info in enumerate(action_infos):
            action_List = action_info.get('actionList', [])
            video_file_name = action_info.get("videoPath", "")
            task_start_time = action_info.get("videoStartTime", "")
            if not action_List:
                return {}
            false_groups = self.operation_chain_grouping(action_List)

            for false_group in false_groups:
                for step in range(0, len(false_group) - 1):
                    last_page_info = false_group[step]
                    next_page_info = false_group[step + 1]
                    oper_type = last_page_info.get('operType', "")
                    oper_widget_bounds_str = last_page_info.get('bounds', '')

                    if oper_type not in ["CLICK"]:
                        continue
                    if not last_page_info['loading_page'] and not last_page_info['popup_error'] and not next_page_info[
                        'loading_page'] and not next_page_info['popup_error']:
                        last_page_screen_file = last_page_info.get('screenshotPath')
                        last_page_layout_file = last_page_info.get('layoutPath')
                        next_page_screen_file = next_page_info.get('screenshotPath')
                        last_page_path = os.path.join(extract_dir, last_page_screen_file)
                        if last_page_layout_file:
                            last_layout_path = os.path.join(extract_dir, last_page_layout_file)
                        else:
                            last_layout_path = None
                        next_page_path = os.path.join(extract_dir, next_page_screen_file)
                        sim = self.get_sim_two_pic(last_page_path, next_page_path)
                        self.logger.info(
                            f"{last_page_screen_file}与{next_page_screen_file}的相似度是：{sim}, 阈值是：{SIM_THRESHOLD}")
                        if sim >= SIM_THRESHOLD:
                            # 滑动的操作不能走下面的点击判定流程
                            if oper_type == "SWIPE":
                                if i not in instruct2click_res:
                                    instruct2click_res[i] = [(last_page_screen_file, last_page_layout_file)]
                                else:
                                    instruct2click_res[i].append((last_page_screen_file, last_page_layout_file))
                                continue

                            # 一、过滤处于当前的页面点击控件后还是跳到当前页面的情况
                            oper_widget_bounds = layout_utils.covert_bounds(oper_widget_bounds_str)
                            if last_layout_path:
                                menu_item_info = jar_parser.get_menu_item_info(last_page_path, last_layout_path)
                                bounds_list = [layout_utils.covert_bounds(item["bounds"]) for item in menu_item_info]
                            else:
                                bounds_list = []
                            self.logger.info(f"{last_page_screen_file}, 规则识别的tabar bounds: {bounds_list}")
                            predict_checkble_bounds = cv_utils.compare_widgets_styles(image_path=last_page_path,
                                                                                      bounds_list=bounds_list)
                            self.logger.info(f"{last_page_screen_file}, 预测的 bounds: {predict_checkble_bounds}")
                            iou = 0.
                            if oper_widget_bounds and predict_checkble_bounds:
                                iou = cv_utils.calculate_iou(oper_widget_bounds, predict_checkble_bounds)
                            self.logger.info(f"{last_page_screen_file}, iou: {iou}")
                            if iou >= IOU_THRESHOLD:
                                self.logger.info(
                                    f"{last_page_screen_file}, {oper_widget_bounds_str}, 点击了当前页面对应的入口控件， IOU：{iou}")
                                continue
                            # 二、这个地方通过目标检测来辅助检测弹窗
                            continue_flag = False
                            if not self.simple:
                                obj_detect_reuslts = api_client.get_obj(image_path_list=[last_page_path])
                                self.logger.info(f"{last_page_screen_file}, 目标检测结果是：{obj_detect_reuslts}")
                                if last_layout_path:
                                    result_menu_item_info = handling_utils.get_menu_item_info(last_page_path,
                                                                                              last_layout_path,
                                                                                              obj_detect_reuslts,
                                                                                              oper_widget_bounds,
                                                                                              self.simple)
                                    horizontal = result_menu_item_info['horizontal']
                                    vertical = result_menu_item_info['vertical']
                                else:
                                    horizontal = []
                                    vertical = []
                                self.logger.info(f"{last_page_screen_file}, 水平的：{horizontal}, 垂直的：{vertical}")
                                if horizontal:
                                    for hs in horizontal:
                                        for h in hs:
                                            self.logger.info(f"{last_page_screen_file}中的{h}")
                                            predict_checkble_bounds = cv_utils.compare_widgets_styles(
                                                image_path=last_page_path,
                                                bounds_list=h)
                                            iou = cv_utils.calculate_iou(oper_widget_bounds, predict_checkble_bounds)
                                            is_contained = cv_utils.is_bound_contained(oper_widget_bounds,
                                                                                       predict_checkble_bounds)
                                            if is_contained:
                                                continue_flag = True
                                            self.logger.info(
                                                f"{last_page_screen_file}， is_contained: {is_contained}, 水平的预测的框：{predict_checkble_bounds}， iou: {iou}，{oper_widget_bounds}")
                                            if iou >= IOU_THRESHOLD:
                                                continue_flag = True
                                if vertical:
                                    for vs in vertical:
                                        for v in vs:
                                            self.logger.info(f"{last_page_screen_file}中的{v}")
                                            predict_checkble_bounds = cv_utils.compare_widgets_styles(
                                                image_path=last_page_path,
                                                bounds_list=v)
                                            iou = cv_utils.calculate_iou(oper_widget_bounds, predict_checkble_bounds)
                                            is_contained = cv_utils.is_bound_contained(oper_widget_bounds,
                                                                                       predict_checkble_bounds)
                                            if is_contained:
                                                continue_flag = True
                                            self.logger.info(
                                                f"{last_page_screen_file}， is_contained: {is_contained}, 垂直的预测的框：{predict_checkble_bounds}， iou: {iou}， is_contained: {is_contained}")
                                            if iou >= IOU_THRESHOLD:
                                                continue_flag = True
                            if continue_flag:
                                continue
                            # 三、判断点击的区域是不是个控件
                            white_flag = cv_utils.is_region_almost_white(last_page_path, oper_widget_bounds,
                                                                         threshold=WHITE_PIXEL_VALUE_THRESHOLD,
                                                                         buffer=WHITE_PIXEL_NUM_THRESHOLD)
                            if white_flag:
                                continue
                            # 四、调用目标检测 检测弹框 点击的位置不在弹窗上的排除在外
                            if not self.simple:
                                obj_detect_reuslts = api_client.get_obj([last_page_path])
                                obj_detect_reuslt = obj_detect_reuslts[0]
                                obj_detect_reuslt = [odr for odr in obj_detect_reuslt if odr["class"] == "popup"]
                                if obj_detect_reuslt:
                                    crop_box_list = []
                                    for odr in obj_detect_reuslt:
                                        crop_box = [odr['left'], odr['top'], odr['right'], odr['bottom']]
                                        crop_box_list.append(crop_box)

                                    coord = cv_utils.get_center(oper_widget_bounds)
                                    background_flag = cv_utils.is_coordinate_in_bounds(coord, crop_box_list)
                                    self.logger.info(
                                        f"{last_page_path}检测的弹窗结果是：{crop_box_list}，点击控件的中心位置是：{coord}，中心位置与弹框的包含关系是：{background_flag}")
                                    if not background_flag:
                                        continue
                            # 五、对点击控件的宽度做限制
                            with_flag = cv_utils.is_bounds_centered(last_page_path, oper_widget_bounds,
                                                                    TOLERANCE, LEFT_DISTANCE_THRESHOLD,
                                                                    RIGHT_DISTANCE_THRESHOLD)
                            if with_flag:
                                continue

                            # 六、计算点击区域的灰度方差
                            gray_variance = cv_utils.calculate_gray_variance(last_page_path, oper_widget_bounds)
                            self.logger.info(
                                f"{last_page_screen_file}中控件{oper_widget_bounds}的灰度方差是：{gray_variance}")
                            if gray_variance <= GRAY_VARIANCE:
                                continue

                            # 七、点击的控件靠近截图的边缘也要豁免点击无响应
                            is_edge = handling_utils.is_in_edge(last_page_path, oper_widget_bounds)
                            self.logger.info(
                                f"{last_page_screen_file}中控件{oper_widget_bounds}是否是在截图的边缘：{is_edge}")
                            if is_edge:
                                continue
                            # 八、控件列表中与操作控件存在交集的个数 大于等两个的排除在外  操作的就不是个控件
                            num = handling_utils.count_intersections(bounds_list, oper_widget_bounds)
                            self.logger.info(
                                f"{last_page_screen_file}的控件列表中与所操作控件{oper_widget_bounds}存在交集的个数是：{num}")
                            if num >= 2:
                                continue
                            # 九、加入对框的不准确框的过滤
                            filter_flag = cv_utils.calculate_variance(last_page_path, oper_widget_bounds)
                            self.logger.info(f"{last_page_path}框的等分判断结果是：{filter_flag}")
                            if filter_flag:
                                continue
                            # 十、加入过滤扁平控件的逻辑
                            flat_bound_flag = cv_utils.check_bound(last_page_path, oper_widget_bounds)
                            if flat_bound_flag:
                                continue
                            # 十一、加入过滤点搜索按钮，搜索框中没内容的情况
                            if last_layout_path:
                                is_empty_searchfield = handling_utils.empty_searchbar(last_layout_path,
                                                                                      oper_widget_bounds)
                            else:
                                is_empty_searchfield = False
                            if is_empty_searchfield:
                                continue
                            # # 十二、过滤中间截图存在弹窗的  如果不是简单模式，然后还有video的情况下走下面的流程
                            # video_path_absolute = os.path.join(extract_dir, video_file_name)
                            # if not self.simple and os.path.exists(video_path_absolute) and task_start_time:
                            #
                            #     task_start_time = int(task_start_time)
                            #
                            #     last_screen_file_name = os.path.split(last_page_screen_file)[1]
                            #     start_timestamp, ext = os.path.splitext(last_screen_file_name)
                            #     start_time = int(str((int(start_timestamp) - task_start_time))[:-3])
                            #
                            #     next_screen_file_name = os.path.split(next_page_screen_file)[1]
                            #     end_timestamp, ext = os.path.splitext(next_screen_file_name)
                            #     end_time = int(str((int(end_timestamp) - task_start_time))[:-3])
                            #     self.logger.info(f"{last_page_screen_file}-开始时间：{start_time}，结束时间：{end_time}")
                            #     error_type, times = self.processing_frame(video_path_absolute, start_time, end_time,
                            #                                               step_length=FRAME_STEP_LENGTH)
                            #     self.logger.info(f"{last_page_screen_file}截取帧判断结果：{error_type}、{times}")
                            #     if not error_type and times != 0:
                            #         continue

                            if i not in instruct2click_res:
                                instruct2click_res[i] = [(last_page_screen_file, last_page_layout_file)]
                            else:
                                instruct2click_res[i].append((last_page_screen_file, last_page_layout_file))

        return instruct2click_res

    def preprocessing(self, action_infos):
        # 对输入的数据进行预处理  A-B-C 当B上有多步操作时，截断B-C的判断
        for action_info in action_infos:
            new_action_list = []
            for action in action_info.get('actionList', []):
                if not new_action_list:
                    new_action_list.append(action)
                else:
                    last_action_in_list = new_action_list[-1]
                    list_last_stepId = last_action_in_list.get("stepId")
                    step_id = action.get("stepId")
                    if list_last_stepId == step_id:
                        action["deleteStep"] = True
                    new_action_list.append(action)
            action_info['actionList'] = new_action_list

        return action_infos

    def frosted_glass(self, extract_dir, action_infos):
        # 对输入的数据进行预处理
        for action_info in action_infos:
            for action in action_info.get('actionList', []):
                screenshotPath = action['screenshotPath']
                page_path = os.path.join(extract_dir, screenshotPath)
                score = cv_utils.calculate_blur_score(page_path)
                self.logger.info(f"{screenshotPath}的上半部分的拉普拉斯变化值是：{score}")
                if score <= FROSTED_GLASS_THRESHOLD:
                    action["frostedGlass"] = True
                    action["deleteStep"] = True
                else:
                    action["frostedGlass"] = False
                    action["deleteStep"] = False

    def launch_app(self, action_infos):
        for action_info in action_infos:
            action_list = action_info.get('actionList', [])
            action_list_len = len(action_list)
            idx = 0
            while idx < action_list_len:
                action = action_list[idx]
                oper_type = action.get('operType', "")
                step_id = action.get('stepId')

                delete_step = action['deleteStep']
                if delete_step:
                    idx += 1
                    continue
                if oper_type == "LAUNCH":
                    action["deleteStep"] = True
                    if idx < action_list_len - 1:
                        next_action = action_list[idx + 1]
                        next_oper_type = next_action.get('operType', "")
                        next_step_id = next_action.get('stepId', "")
                        if next_step_id == step_id:
                            if next_oper_type in ["PRESS_BACK", "KILL_APP"]:
                                next_action["deleteStep"] = True
                                idx += 1
                else:
                    action["deleteStep"] = False
                    if idx < action_list_len - 1:
                        next_action = action_list[idx + 1]
                        next_oper_type = next_action.get('operType', "")
                        next_step_id = next_action.get('stepId', "")
                        if next_step_id == step_id:
                            next_action["deleteStep"] = True
                            idx += 1
                idx += 1

    def processing_flow(self, test_suites_path, extract_dir=None, task_id=None):
        self.simple = False
        end_side = False
        if isinstance(test_suites_path, dict):
            # 简单模式
            self.simple = test_suites_path.get("simple", False)
            # endSide端侧
            end_side = test_suites_path.get("endSide", False)
        if not end_side:
            test_suites = json_utils.load_json(test_suites_path)
        else:
            test_suites = test_suites_path
            # 端测是保存图像到本地
            extract_dir = "./datas"
            actionInfos = test_suites.get("actionInfos", [])
            for actionInfo in actionInfos:
                actionList = actionInfo.get("actionList", [])
                for action in actionList:
                    layout = action.get("layout", "")
                    img = action.get("img", "")

                    layoutPath = action.get("layoutPath", "")
                    screenshotPath = action.get("screenshotPath", "")

                    save_layout_path = os.path.join(extract_dir, "layout")
                    save_screen_path = os.path.join(extract_dir, "screenshot")

                    os.makedirs(save_layout_path, exist_ok=True)
                    os.makedirs(save_screen_path, exist_ok=True)

                    save_layout_file_path = os.path.join(extract_dir, layoutPath)
                    save_screen_file_path = os.path.join(extract_dir, screenshotPath)
                    if layoutPath:
                        layout = json.loads(layout)
                        json_utils.dump_json(layout, save_layout_file_path)
                    else:
                        self.logger.info(f"{screenshotPath}没有对应的layout数据，识别模式简单模式：{self.simple}")
                    cv_utils.base64_to_image(img, save_screen_file_path)

                    # self.logger.info(f"{layoutPath}保存成功！")
                    # self.logger.info(f"{screenshotPath}保存成功！")

        action_infos = test_suites.get('actionInfos', [])
        self.logger.info("毛玻璃判断")
        # 对模糊显示的毛玻璃屏幕打标签 action["frostedGlass"] = True
        self.frosted_glass(extract_dir, action_infos)
        self.logger.info("启动筛选")
        # 打标签是启动app的步骤
        self.launch_app(action_infos)
        self.logger.info("节点归一")
        # 同一个页面上的操作归为一个节点
        # new_action_infos = self.preprocessing(action_infos)
        new_action_infos = action_infos
        self.logger.info(f"节点归一结束")
        deep_explore = test_suites.get('deepExplore', False)
        # self.logger.info(
        #     f"进程：{self.no_process}， task_id:{self.in_process_task_id},执行的用例个数: {len(new_action_infos)}")
        # 给节点打标签，打上加载中，弹窗报错信息的标签
        self.label_nodes(new_action_infos, extract_dir, task_id)
        # 判断连续是加载中页面的个数
        instruct2reload = self.oracle_loading(new_action_infos)
        # 拿出无加载中、无弹窗报错的AB页面, 规则判断点击无响应

        instruct2click = self.oracle_click_no_feedback(new_action_infos, extract_dir)
        if deep_explore:
            # 深度探索
            pass
        # 整理输出结果
        package_data = self.format_data(instruct2reload, instruct2click, new_action_infos, test_suites)
        formatted_json = json.dumps(package_data, indent=4, ensure_ascii=False)
        self.logger.info(f"模型返回结果：{formatted_json}。")

        if end_side:
            shutil.rmtree(save_layout_path)
            shutil.rmtree(save_screen_path)

        return package_data

    def processing_scene(self, image_path, layout_path):
        # 如果有layout文件直接读取
        if layout_path:
            tree_root = json_utils.load_json(layout_path)
            texts = layout_utils.get_texts_from_layout(tree_root)
        # 如果没有layout文件，而且不走简单模式
        elif not layout_path and not self.simple:
            self.logger.info(f"{image_path}")
            ocr_result = api_client.get_ocr(image_path=image_path)
            words_result = ocr_result['words_result']
            texts = [item.get('words', "") for item in words_result]
        # 如没有layout文件，而且走简单模式
        else:
            if not layout_path and self.simple:
                return ""

        load_error = self.ruler_load_error(texts)
        if load_error:
            return load_error
        # text = "".join(texts)
        # image_layout_infos = {"path": image_path, "text": text}
        # start_time = time.time()
        # if self.simple:
        #     return ""
        # scene_clses = api_client.get_scene_cls(image_layout_infos)
        # end_time = time.time()
        # self.logger.info(
        #     f"进程：{self.no_process}，task_id:{self.in_process_task_id}，请求场景分类模型耗时:{end_time - start_time}, 场景分类返回结果:{scene_clses}")
        # predict_labels = [scene_cls['scene'] for scene_cls in scene_clses]
        # if "加载页" in predict_labels:
        #     return "加载中页面"
        loading_keywords = ["加载中", "正在加载", "拼命加载中", "正在诊断问题", "加载订单详情"]
        page_text_content = ''.join(texts)
        for keyword in loading_keywords:
            if keyword in page_text_content:
                self.logger.info(f"{image_path}命中{keyword},返回加载中页面")
                return "加载中页面"
        else:
            reload_label_list = ["video_white_background", "video_black_background", "placeholder",
                                 "black_map_area", "white_map_area"]
            if not self.simple:
                obj_detect_reuslts = api_client.get_obj(image_path_list=[image_path])
                obj_detect_reuslt = obj_detect_reuslts[0]
                for odr in obj_detect_reuslt:
                    if odr["class"] in reload_label_list:
                        self.logger.info(f"{image_path}目标检测命中{odr['class']},返回加载中页面")
                        return "加载中页面"
                return ""
            else:
                return ""

    def processing_popup(self, image_path, layout_path):
        if layout_path:
            # 先进行jar包的规则匹配
            texts = jar_parser.get_popup_texts(image_path, layout_path)
        else:
            texts = []
        pop_flag = False
        content = ''
        # 规则匹配出来是弹窗不走模型
        if texts:
            content = ''.join(texts)
            self.logger.info(
                f"进程：{self.no_process}，task_id:{self.in_process_task_id}，{image_path},jar识别出弹窗，弹窗中内容是:{content}")
        # 规则未识别走模型
        else:
            if not self.simple:
                texts = []
                obj_detect_reuslts = api_client.get_obj(image_path_list=[image_path])
                obj_detect_reuslt = obj_detect_reuslts[0]
                obj_detect_reuslt = [odr for odr in obj_detect_reuslt if odr["class"] == "popup"]
                for odr in obj_detect_reuslt:
                    crop_box = [odr['left'], odr['top'], odr['right'], odr['bottom']]
                    crop_base64 = cv_utils.crop_and_encode_image(image_path, crop_box=crop_box)
                    ocr_start_time = time.time()
                    ocr_result = api_client.get_ocr(image_base64=crop_base64)
                    self.logger.info(f"task_id:{self.in_process_task_id}，ocr 耗时：{time.time() - ocr_start_time}")
                    words_result = ocr_result['words_result']
                    ocr_text_list = [item.get('words', "") for item in words_result]
                    content = content + " ".join(ocr_text_list)
                    texts.extend(ocr_text_list)
                if obj_detect_reuslt:
                    self.logger.info(
                        f"进程：{self.no_process}，task_id:{self.in_process_task_id}，{image_path},模型识别出弹窗，弹窗中内容是:{content}")
        error_type = ''
        if content:
            pop_flag = True
            # 规则匹配弹窗错误   等待开发
        if pop_flag:
            error_type = self.ruler_pop_error(texts)
        # 返回错误类型
        return error_type, pop_flag

    def processing_frame(self, video_path, start, end, step_length):
        frames_base64, times_list = cv_utils.extract_frames_base64(video_path, start, end, step_length)

        # cv_utils.save_images_from_base64(frames_base64)

        content = ''
        if self.simple:
            return content, 0.
        frames_base64_obj_result = api_client.get_obj(image_base64_list=frames_base64)
        if not frames_base64_obj_result:
            return content, 0.
        row_texts = []
        obj_detect_reuslt_ = []
        for i, obj_detect_reuslt in enumerate(frames_base64_obj_result):
            obj_detect_reuslt_ = [odr for odr in obj_detect_reuslt if odr["class"] == "popup"]
            if obj_detect_reuslt_:
                break
        if not obj_detect_reuslt_:
            return content, 0.
        for odr in obj_detect_reuslt_:
            crop_box = [odr['left'], odr['top'], odr['right'], odr['bottom']]
            crop_base64 = cv_utils.crop_and_encode_image_base64(frames_base64[i], crop_box=crop_box)
            ocr_result = api_client.get_ocr(image_base64=crop_base64)
            words_result = ocr_result['words_result']
            ocr_text_list = [item.get('words', '') for item in words_result]
            content = content + " ".join(ocr_text_list)
            row_texts.extend(ocr_text_list)
        self.logger.info(f"video_path:{video_path}, 识别的文本是:{row_texts}，时间是：{times_list[i]}")
        # 这里编写规则识别弹窗错误的
        error_type = self.ruler_pop_error(row_texts)
        return error_type, times_list[i]

    def get_sim_two_pic(self, last_page, next_page):
        return cv_utils.calculate_ssim(last_page, next_page)

    def ruler_pop_error(self, texts):
        # 弹框中午内容
        if not texts:
            return "弹窗报错"
        for keyword in self.popup_error_keywords:
            for text in texts:
                if keyword in text:
                    return "弹窗报错"
        return ''
        # content = ''.join(texts)
        # class_name = api_client.get_popuptext_cls(content)
        # if class_name == 'normal':
        #     return ''
        # else:
        #     return "弹窗报错"

    def ruler_load_error(self, texts):
        # if len(texts) <= 10:
        for keyword in self.load_error_keywords:
            for text in texts:
                if keyword == text:
                    return "加载失败页面"
        return ''

    def format_data(self, instruct2reload, instruct2click, action_infos, test_suites):
        taskId = test_suites.get("taskId", "")
        sceneTestCaseId = test_suites.get("sceneTestCaseId", "")
        format_json = {
            "taskId": taskId,
            "sceneTestCaseId": sceneTestCaseId
        }
        funCheckResult = []
        for i, action_info in enumerate(action_infos):
            action_List = action_info.get('actionList', [])
            instruction = action_info.get('instruction', '')
            videoPath = action_info.get('videoPath', '')
            i_reload = instruct2reload.get(i, [])
            i_click = instruct2click.get(i, [])
            errorPageList_1 = [{"screenshotPath": ir[0], "layoutPath": ir[1], "errorfuncCheckType": "页面加载异常",
                                "ruleCode": "2.40.4", "problemDescription": ""} for ir in i_reload]
            errorPageList_2 = [{"screenshotPath": ic[0], "layoutPath": ic[1], "errorfuncCheckType": "控件点击无响应",
                                "ruleCode": "2.40.1", "problemDescription": ""} for ic in i_click]
            errorPageList_3 = []
            errorPageList_4 = []
            errorVideoKeyframeList = []
            for step, action_item in enumerate(action_List):
                if action_item.get("frame_error", ""):
                    errorVideoKeyframeList.append({"videoClipTime": [action_List[step - 1]["videoScreenshotTime"],
                                                                     action_List[step]["videoScreenshotTime"]],
                                                   "errorKeyFrameTime": action_item['frame_error_time_location'],
                                                   "errorfuncCheckType": "弹窗错误",
                                                   "ruleCode": "2.40.2", "problemDescription": ""})
                if action_item.get("popup_error", ""):
                    errorPageList_3.append(
                        {"screenshotPath": action_item["screenshotPath"], "layoutPath": action_item["layoutPath"],
                         "errorfuncCheckType": "弹窗错误", "ruleCode": "2.40.2", "problemDescription": ""})

                if action_item.get("load_error_page", False):
                    errorPageList_3.append(
                        {"screenshotPath": action_item["screenshotPath"], "layoutPath": action_item["layoutPath"],
                         "errorfuncCheckType": "页面加载失败", "ruleCode": "2.40.3", "problemDescription": ""})

                if action_item.get("white_or_black", False):
                    errorPageList_4.append({"screenshotPath": action_item["screenshotPath"], "layoutPath": action_item["layoutPath"],
                         "errorfuncCheckType": "黑白屏异常", "ruleCode": "2.40.5", "problemDescription": ""})

            errorPageList = errorPageList_1 + errorPageList_2 + errorPageList_3 + errorPageList_4
            funCheckResult.append({
                "instruction": instruction,
                "videoPath": videoPath,
                "errorPageList": errorPageList,
                "errorVideoKeyframeList": errorVideoKeyframeList,
            })

        format_json["funCheckResult"] = funCheckResult
        return format_json


if __name__ == '__main__':
    # foc = FunctionalOracleCheckerV1()
    # print(foc.generate_app_screenshot_caption(
    #     screenshot=r"D:\PersonalCodehub\APPilotAgent_OracleChecker\tmp_files\1731591033000.jpeg"))
    pass

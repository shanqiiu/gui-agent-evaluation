import os
import json
import jpype
import config

opj = os.path.join


def load_jar_pkg():
    jar_path_1 = opj(config.JAR_PATH_1)
    jar_path_2 = opj(config.JAR_PATH_2)
    java_path = jpype.getDefaultJVMPath()
    jpype.startJVM(java_path, "-ea", "-XX:+CreateMinidumpOnCrash", classpath=[jar_path_1, jar_path_2])


def get_popup_texts(img_p, layout_p):
    AnalyseLayout = jpype.JClass('com.huawei.hitest.apptester.engine.utils.WindowUtil')
    dialLogWindowInfo = AnalyseLayout.getDiaLogWindowInfo(img_p, layout_p)
    dialLogWindowInfo = json.loads(str(dialLogWindowInfo))
    text_list = []
    for dialLogWindow in dialLogWindowInfo:
        text = dialLogWindow['text']
        text_list.append(text)
    return text_list


def get_menu_item_info(img_p, layout_p):
    AnalyseLayout = jpype.JClass('com.huawei.hitest.apptester.engine.utils.WindowUtil')
    dialLogWindowInfo = AnalyseLayout.getMenuItemInfo(img_p, layout_p)
    dialLogWindowInfo = json.loads(str(dialLogWindowInfo))
    return dialLogWindowInfo


def filter_elements_v3(img_p, layout_p):
    AnalyseLayout = jpype.JClass('com.huawei.hitest.apptester.engine.utils.WindowUtil')
    widgetsInfo = AnalyseLayout.getGraphWidgetsInfo(layout_p, img_p)
    elem_list = []
    for wid, widget in widgetsInfo.items():
        # import pdb; pdb.set_trace()
        bound_str = widget.getBounds()[1:-1].replace('][', ',').split(',')
        x1, y1, x2, y2 = map(int, bound_str)
        elem = {
            'xpath': str(widget.getXpath()),
            'bounds': [x1, y1, x2, y2],
            'area': (x2 - x1) * (y2 - y1),
        }
        elem_list.append(elem)
    return elem_list


if __name__ == '__main__':
    load_jar_pkg()
    # image_path, layout_path = "/home/limengqi/group-o-52c7dde04efa46b591c358bad7397c4b.jpeg", "/home/limengqi/group-o-25dcb069865e40e0b3805b439e438def.json"
    # image_path, layout_path = "/home/limengqi/0C247DDD644AF8A7DA5F25C2079F6A8C.jpeg", "/home/limengqi/0C247DDD644AF8A7DA5F25C2079F6A8C.json"
    image_path, layout_path = "/home/limengqi/temp.jpeg", "/home/limengqi/temp.json"
    # image_path, layout_path = "/home/limengqi/1753363660000.jpeg", "/home/limengqi/1753363660000.json"
    # dialLogWindowInfo = get_popup_texts(image_path, layout_path)
    # print(dialLogWindowInfo)
    dialLogWindowInfo = get_menu_item_info(image_path, layout_path)
    print(dialLogWindowInfo)
    for item in dialLogWindowInfo:
        bounds = item['bounds']
        print(bounds)

    # widget_infos = filter_elements_v3(image_path, layout_path)
    #
    # for wid in widget_infos:
    #     print(wid)

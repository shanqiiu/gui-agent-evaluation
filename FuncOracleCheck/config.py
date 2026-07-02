# jar包路径配置
# D:\PycharmProjects2\FuncOracleCheck
# JAR_PATH_1 = r"./external_apis/assets/apptester-engine-1.4.33-2025070401-SNAPSHOT-shaded(1).jar"
JAR_PATH_1 = r"./external_apis/assets/apptester-engine-1.4.33-SNAPSHOT-shaded.jar"
JAR_PATH_2 = r"./external_apis/assets/apptester-engine-1.4.5-2024041601-SNAPSHOT.jar"
# 场景分类地址链接
SCENE_CLS_URL = "http://7.185.125.184:8443/apptest/ai/SceneClsDevice/scene_cls"
# 目标检测地址链接
# OBJECT_DETECT_URL = "http://7.185.125.184:8443/apptest/ai/block/yolo" # 生产地址
OBJECT_DETECT_URL = "http://10.90.86.141:17977/yolo"  # 测试地址
# OCR地址链接
OCR_URL = "http://7.185.25.92:8093/pps_ocr/recognize"
# 弹窗文本分类模型地址
# POPUP_TEXT_CLS = "http://10.108.69.102:5555/bert/text"  # 开发地址
POPUP_TEXT_CLS = "http://10.90.86.141:5555/bert/text"  # 测试地址

# OCR_URL = "https://hitest.huawei.com/storage-api/ctest/pps_ocr/recognize"
# 连续n个截图是加载中的页面
NUMBER_OF_ITEMS_IN_LOADING = 1
# NUMBER_OF_ITEMS_IN_LOADING = 3
# 图像相似判断点击无响应，相似度阈值 控制在[-1,1]
SIM_THRESHOLD = 0.9999
# 视频抽帧的间隔 单位是s
FRAME_STEP_LENGTH = 1.2
# 点击无响应规则判断tab栏交并比
IOU_THRESHOLD = 0.95

# 毛玻璃界面的阈值
FROSTED_GLASS_THRESHOLD = 100
# FROSTED_GLASS_THRESHOLD = 195
# 被操作控件灰度方差的阈值
GRAY_VARIANCE = 330

# 点击控件的白色区域配置参数
WHITE_PIXEL_VALUE_THRESHOLD = 250
WHITE_PIXEL_NUM_THRESHOLD = 1000

# 控件在页面的中位置
TOLERANCE = 10  # 允许的偏差
LEFT_DISTANCE_THRESHOLD = 5
RIGHT_DISTANCE_THRESHOLD = 5

# 黑白屏设置的阈值
WHITE_BLACK_THRESHOLD = 0.99
# WHITE_BLACK_THRESHOLD = 0.98


# ==========================================
# 消息队列名称
MESSAGE_QUEUE_NAME = "FUNC_CHECK_TASK_QUEUE_develop"
# MESSAGE_QUEUE_NAME = "FUNC_CHECK_TASK_QUEUE"
# 消费者个数
CONSUMER_NUMBER = 48
# S3数据库配置
BASEURL = "https://aifortesting.huawei.com/aiplatform/common_server"
# S3下载的数据存放路径
SVE_DIR = "./DOWNLOAD_DATA_FROM_S3"
# 排队队列长度
QUEUE_LIMIT_LENGTH = 20000
# redis测试环境配置
REDIS_HOST = "10.28.117.138"
REDIS_PORT = 6379
REDIS_PASSWORD = "pC7~zT9)rU4{zG1>aB"
# Obs桶的信息
AK = "5RUi5n3byAmNWbebzMFA2GISFOwNSu7r"
SK = "tB7NKYen3N7RokqmMlbqtV32Gaa3vUrD"
REGION_NAME = "http://s3-hc-dgg.hics.huawei.com"
BUCKETNAME = "apptest-fdfs-beta"

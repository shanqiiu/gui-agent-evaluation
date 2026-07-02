import re
import os
import cv2
from library.logger import logger
import base64
from io import BytesIO
import numpy as np
import copy
import time
from PIL import Image
from skimage.metrics import structural_similarity as ssim
from math import sqrt, cos, sin, pi


def is_base64_format(s):
    pattern = r'^[A-Za-z0-9+/]+={0,2}$'
    return re.fullmatch(pattern, s) is not None and len(s) % 4 == 0


def base64_content_validation(s):
    try:
        # 去除末尾可能存在的填充符后统一处理
        decoded = base64.b64decode(s, validate=True)
        re_encoded = base64.b64encode(decoded).decode()
        # 填充符可能被省略，需兼容两种情况
        return s.rstrip('=') == re_encoded.rstrip('=')
    except ValueError:
        return False


def is_valid_base64(s):
    return is_base64_format(s) and base64_content_validation(s)


def encode_image_to_base64_from_cv2(image=None):
    # 将图像编码为内存中的字节数组
    _, buffer = cv2.imencode('.jpg', image)
    # 转换为字节类型
    image_bytes = buffer.tobytes()
    # 将字节数据编码为base64字符串
    base64image_ = base64.b64encode(image_bytes).decode('utf-8')
    return base64image_


def encode_image_to_base64(image=None):
    if isinstance(image, str):
        if os.path.exists(image):
            with open(image, "rb") as image_file:
                base64image_ = base64.b64encode(image_file.read()).decode('utf-8')
            image_file.close()
        elif is_valid_base64(image):
            # 默认已经是base64了
            return image
        else:
            raise ValueError(f"image type should in [np.ndarray, image_path, image_base64]!")
    else:
        base64image_ = encode_image_to_base64_from_cv2(image)
    return base64image_


def encode_image_to_base64_by_pil(image=None):
    if isinstance(image, str):
        # image为本地.jpeg图片路径
        with open(image, 'rb') as image_file:
            pil_image = copy.deepcopy(Image.open(image_file))
    elif isinstance(image, Image.Image):
        # image为Image.Image格式
        pil_image = copy.deepcopy(image)
    elif isinstance(image, np.ndarray):
        # image为cv2读取出来的np.ndarray格式
        # 将 BGR 转为 RGB
        rgb_img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # 转换为 PIL.Image
        pil_image = Image.fromarray(rgb_img)
    else:
        raise ValueError(f"input image type should in ['image_path', 'Image.Image', 'np.ndarray']!")

    # 保证图片为RGB通道顺序
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")

        # 将图片转为二进制数据
    buffered = BytesIO()
    pil_image.save(buffered, format="JPEG")
    # 编码为base64字符串
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return img_base64


def decode_rbg_image_base64_to_pil_image(rbg_image_base64=None):
    if isinstance(rbg_image_base64, str):
        # 解码base64字符串为二进制数据
        binary_img_data = base64.b64decode(rbg_image_base64)
        # 转换为PIL图片对象
        img = Image.open(BytesIO(binary_img_data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img
    raise ValueError(f"input rbg_image_base64 should be rgb image base64 string!")
    pass


def open_image_in_pil(image_path: str = None):
    with open(image_path, 'rb') as image_file:
        pil_image = copy.deepcopy(Image.open(image_file))
    return pil_image


def open_image_in_cv2(image_path: str = None):
    return cv2.imread(image_path)


def convert_base64_to_cv2(base64_code=None):
    try:
        img_data = base64.b64decode(base64_code)
        img_array = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(img_array, cv2.COLOR_RGB2BGR)
        return img
    except ValueError:
        return None


def convert_pil_image_to_cv2(image: Image.Image = None):
    image = image.convert('RGB')
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def compare_images(image1: [str, np.ndarray] = None, image2: [str, np.ndarray] = None, method: str = 'ssim'):
    """
    计算两张图片的相似度

    参数:
    image1: 第一张图片的路径或已加载的图片数组
    image2: 第二张图片的路径或已加载的图片数组
    method: 相似度计算方法，可选值为 'ssim'、'mse'、'psnr'、'histogram'

    返回:
    相似度得分（不同方法的得分范围不同）
    """
    # 如果输入是图片路径，则加载图片
    if isinstance(image1, str):
        image1 = cv2.imread(image1)
    if isinstance(image2, str):
        image2 = cv2.imread(image2)

    # 确保两张图片具有相同的尺寸
    if image1.shape != image2.shape:
        image2 = cv2.resize(image2, (image1.shape[1], image1.shape[0]))

    # 转换为灰度图（如果需要）
    if len(image1.shape) == 3:
        gray1 = cv2.cvtColor(image1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(image2, cv2.COLOR_BGR2GRAY)
    else:
        gray1 = image1
        gray2 = image2

    # 根据指定的方法计算相似度
    if method == 'ssim':
        # 结构相似性指数，值范围从-1到1，越接近1越相似
        score = ssim(gray1, gray2)
    elif method == 'mse':
        # 均方误差，值越小越相似
        err = np.sum((gray1.astype("float") - gray2.astype("float")) ** 2)
        err /= float(gray1.shape[0] * gray1.shape[1])
        score = -err  # 取负值，使值越大越相似
    elif method == 'psnr':
        # 峰值信噪比，值越大越相似
        mse_val = np.mean((gray1 - gray2) ** 2)
        if mse_val == 0:
            score = float('inf')
        else:
            score = 20 * np.log10(255.0 / np.sqrt(mse_val))
    elif method == 'histogram':
        # 直方图相关性，值范围从-1到1，越接近1越相似
        hist1 = cv2.calcHist([image1], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist1 = cv2.normalize(hist1, hist1).flatten()
        hist2 = cv2.calcHist([image2], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist2 = cv2.normalize(hist2, hist2).flatten()
        score = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    else:
        raise ValueError("不支持的相似度计算方法")

    return score


def draw_circle(image=None, x=None, y=None, radius=100, thickness=3, color=(0, 0, 255)):
    # 绘制圆圈
    cv2.circle(image, (x, y), radius, color, thickness)
    return image


def draw_circle_mask(image: np.ndarray = None, x1=None, y1=None, radius=60, darken_factor=0.8, thickness=5,
                     color=(0, 0, 255)):
    # 创建一个与图像大小相同的遮罩
    mask = np.zeros_like(image, dtype=np.uint8)

    # 在遮罩上绘制一个白色的圆圈，圆心为给定坐标，半径为指定值
    cv2.circle(mask, (x1, y1), radius, (255, 255, 255), -1)

    # 将遮罩反转
    inverted_mask = cv2.bitwise_not(mask)

    # 将图像与反转的遮罩进行按位与运算，暗化圆圈外的区域
    darkened_image = cv2.bitwise_and(image, inverted_mask)

    # 降低暗化区域的亮度
    darkened_image = (darkened_image * darken_factor).astype(np.uint8)

    # 将原始图像的圆圈区域与暗化后的图像合并
    result = cv2.add(darkened_image, cv2.bitwise_and(image, mask))
    # 画圆
    # 圆心坐标和半径
    center_coordinates = (x1, y1)  # 例如 (100, 100)
    # 画圆
    cv2.circle(result, center_coordinates, radius, color, thickness)
    return result


def draw_arrow(image: np.ndarray = None, start_point=None, end_point=None, thickness=10, color=(0, 255, 0)):
    # 画箭头
    cv2.arrowedLine(image, start_point, end_point, color, thickness)
    return image


def crop_and_encode_image(image_path, crop_box):
    # 打开图片
    with Image.open(image_path) as img:
        # 截取指定区域
        cropped_img = img.crop(crop_box)

        # 将图片保存到内存中
        buffered = BytesIO()
        cropped_img.save(buffered, format="PNG")

        # 编码为 Base64
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        return img_base64


def crop_and_encode_image_base64(base64_str, crop_box):
    # 解码base64字符串
    image_data = base64.b64decode(base64_str)
    image = Image.open(BytesIO(image_data))

    # 截取图像
    cropped_image = image.crop(crop_box)

    # 将截取的图像编码为base64
    buffered = BytesIO()
    cropped_image.save(buffered, format="PNG")
    cropped_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return cropped_base64


def extract_frames_base64(video_path, start_time, end_time, interval):
    """
    从视频中提取帧并将其转换为base64编码。

    :param video_path: 视频文件的路径
    :param start_time: 开始时间（以秒为单位）
    :param end_time: 结束时间（以秒为单位）
    :param interval: 帧提取的时间间隔（以秒为单位）
    :return: 包含每一帧base64编码的列表
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)

    # 将时间转换为帧数
    start_frame = int(start_time * fps)
    end_frame = int(end_time * fps)
    interval_frames = int(interval * fps)

    frames_base64 = []
    times_list = []
    current_frame = start_frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)

    while current_frame <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        # 转换为RGB格式
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)

        # 转换为base64
        buffered = BytesIO()
        pil_img.save(buffered, format="JPEG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        frames_base64.append(img_base64)
        times_list.append(current_frame / fps)
        current_frame += interval_frames
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)

    cap.release()
    return frames_base64, times_list


#
# # 判断页面是不是毛玻璃状态
# def calculate_blur_score(image_path):
#     # 读取图像
#     image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
#
#     # 计算拉普拉斯变换
#     laplacian_var = cv2.Laplacian(image, cv2.CV_64F).var()
#
#     return laplacian_var

# 判断页面是不是毛玻璃状态
def calculate_blur_score(image_path):
    # 打开图像
    with Image.open(image_path) as img:
        # 获取图像的宽度和高度
        width, height = img.size

        # 计算中间位置
        middle = height // 2

        # 裁剪出上半部分
        upper_half = img.crop((0, 0, width, middle))

        # 将上半部分转换为 OpenCV 格式
        upper_half_cv = cv2.cvtColor(np.array(upper_half), cv2.COLOR_RGB2BGR)

        # 计算拉普拉斯变化
        laplacian_var = cv2.Laplacian(upper_half_cv, cv2.CV_64F).var()

        return laplacian_var


def softmax(x):
    # 计算输入的指数
    exp_x = np.exp(x - np.max(x))
    # 计算Softmax
    return exp_x / exp_x.sum(axis=0)


def calculate_histogram(image, title: str = None, render: bool = False):
    # 将图像从BGR转换为RGB
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    # 获取图像的总像素数
    total_pixels = image.shape[0] * image.shape[1]

    # 计算每个颜色通道的直方图
    hist_r = cv2.calcHist([image_rgb], [0], None, [256], [0, 256])
    hist_g = cv2.calcHist([image_rgb], [1], None, [256], [0, 256])
    hist_b = cv2.calcHist([image_rgb], [2], None, [256], [0, 256])

    # 归一化
    # hist_r /= hist_r.sum()
    # hist_g /= hist_g.sum()
    # hist_b /= hist_b.sum()
    hist_r /= total_pixels
    hist_g /= total_pixels
    hist_b /= total_pixels

    return hist_r, hist_g, hist_b


def chi_square_distance(hist1, hist2):
    # 计算卡方距离
    return cv2.compareHist(hist1, hist2, cv2.HISTCMP_KL_DIV)


def find_outlier_images(images=None, render=False):
    histograms = []
    for image in images:
        histograms.append(calculate_histogram(image, render=render))

    # 计算每对图像之间的距离
    distances = np.zeros((len(images), len(images)))
    for i in range(len(histograms)):
        for j in range(i + 1, len(histograms)):
            dist_r = chi_square_distance(histograms[i][0], histograms[j][0])
            dist_g = chi_square_distance(histograms[i][1], histograms[j][1])
            dist_b = chi_square_distance(histograms[i][2], histograms[j][2])
            distances[i, j] = dist_r + dist_g + dist_b
            distances[j, i] = distances[i, j]

    # 计算每张图片的平均距离
    mean_distances = distances.sum(axis=1) / (len(images) - 1)
    # 对mean_distances进行Softmax操作
    mean_distances = softmax(mean_distances)
    print(f"mean_distances: {mean_distances}")

    # 找出平均距离最大的图片
    outlier_index = np.argmax(mean_distances)
    # 计算除最大值之外的平均值
    average_of_remaining = np.mean(np.delete(mean_distances, outlier_index))

    second_largest = np.sort(mean_distances)[-2]

    return outlier_index, mean_distances[outlier_index], 1 - (
            average_of_remaining / mean_distances[outlier_index]), 1 - (
                                                                 second_largest / mean_distances[outlier_index])


def compare_widgets_styles(image_path=None, bounds_list=None, scale=1.0, render=False):
    if not image_path or not bounds_list:
        return []
    if len(bounds_list) == 1:
        return []
    image = cv2.imread(image_path)

    image = cv2.resize(image, (int(image.shape[1] * scale), int(image.shape[0] * scale)))
    widget_images = list()
    for idx, bounds in enumerate(bounds_list):
        x1, y1, x2, y2 = int(bounds[0] * scale), int(bounds[1] * scale), int(bounds[2] * scale), int(bounds[3] * scale),
        widget_image = image[y1: y2, x1: x2]
        widget_images.append(widget_image)

    if len(bounds_list) == 2:
        outlier_images_index = find_clicked_control(image_path, bounds_list)
        bounds = bounds_list[outlier_images_index]
        return bounds

    outlier_images_index, outlier_images_mean_distance, score_avg, score_greedy = find_outlier_images(
        images=widget_images, render=render)
    bounds = bounds_list[outlier_images_index]
    return bounds


# 计算IoU
def calculate_iou(box1, box2):
    # box1 和 box2 的格式为 [x1, y1, x2, y2]
    x1_inter = max(box1[0], box2[0])
    y1_inter = max(box1[1], box2[1])
    x2_inter = min(box1[2], box2[2])
    y2_inter = min(box1[3], box2[3])

    # 计算交集的面积
    inter_width = max(0, x2_inter - x1_inter)
    inter_height = max(0, y2_inter - y1_inter)
    inter_area = inter_width * inter_height

    # 计算各个框的面积
    area_box1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area_box2 = (box2[2] - box2[0]) * (box2[3] - box2[1])

    # 计算并集的面积
    union_area = area_box1 + area_box2 - inter_area

    # 计算交并比
    iou = inter_area / union_area if union_area != 0 else 0

    return iou


def base64_to_image(base64_string, output_path):
    with open(output_path, "wb") as image_file:
        image_file.write(base64.b64decode(base64_string))


def is_region_almost_white(image_path, bounds, threshold=250, buffer=200):
    # 打开图像
    image = Image.open(image_path)

    # 裁剪图像到指定的边界框
    cropped_image = image.crop(bounds)

    # 转换为NumPy数组
    image_array = np.array(cropped_image)

    # 检查是否接近白色
    # 对于RGB图像，白色为(255, 255, 255)
    if image_array.ndim == 3:
        # RGB图像
        white_region = np.all(image_array >= threshold, axis=-1)
    else:
        # 灰度图像
        white_region = image_array >= threshold

    # 计算非白色像素的数量
    non_white_count = np.size(white_region) - np.sum(white_region)

    # 如果非白色像素数量小于等于buffer，则认为接近白色
    return non_white_count <= buffer


def get_center(bounds):
    x1, y1, x2, y2 = bounds
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2
    return [center_x, center_y]


def is_coordinate_in_bounds(coord, bounds_list):
    x, y = coord
    for bounds in bounds_list:
        x1, y1, x2, y2 = bounds
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True
    return False


def is_bounds_centered(image_path, bounds, tolerance, left_distance_th, right_distance_th):
    # 打开图像
    with Image.open(image_path) as img:
        width, height = img.size

    # 解包边界框
    x1, y1, x2, y2 = bounds

    # 计算边界框的中心
    bbox_center = (x1 + x2) / 2

    # 计算图像的中心
    image_center = width / 2

    # 计算边界框与图像左右边缘的距离
    left_distance = x1
    right_distance = width - x2

    # 判断是否水平居中（可以设置一个容忍度）
    is_centered = abs(bbox_center - image_center) <= tolerance

    if is_centered and (left_distance <= left_distance_th) and (right_distance <= right_distance_th):
        return True
    else:
        return False


def calculate_ssim(img_path1, img_path2, win_size=11, is_gray=True):
    """
    纯cv2实现SSIM计算（不依赖任何第三方库）

    参数:
        img_path1: 第一张图像路径
        img_path2: 第二张图像路径
        win_size: 局部窗口大小（需为奇数，默认11x11）
        is_gray: 是否用灰度图计算（默认True，彩色图会按通道计算后平均）

    返回:
        ssim_score: SSIM相似度（0~1）
    """
    # 1. 读取图像并预处理
    img1 = cv2.imread(img_path1)
    img2 = cv2.imread(img_path2)

    # 检查图像读取成功
    if img1 is None or img2 is None:
        raise ValueError("图像读取失败，请检查路径")

    # 统一尺寸（将img2调整为img1的尺寸）
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]), interpolation=cv2.INTER_AREA)

    # 转换为float32类型（避免整数运算溢出）
    img1 = img1.astype(np.float32)
    img2 = img2.astype(np.float32)

    # 2. 彩色图处理（分通道计算SSIM后取平均）
    if not is_gray:
        # 分离BGR通道（OpenCV默认BGR格式）
        b1, g1, r1 = cv2.split(img1)
        b2, g2, r2 = cv2.split(img2)
        # 分别计算三通道SSIM并平均
        ssim_b = calculate_ssim_single_channel(b1, b2, win_size)
        ssim_g = calculate_ssim_single_channel(g1, g2, win_size)
        ssim_r = calculate_ssim_single_channel(r1, r2, win_size)
        return (ssim_b + ssim_g + ssim_r) / 3

    # 灰度图处理
    else:
        img1_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        img2_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        return calculate_ssim_single_channel(img1_gray, img2_gray, win_size)


def calculate_ssim_single_channel(x, y, win_size):
    """辅助函数：计算单通道（灰度）图像的SSIM"""
    # 图像动态范围（8位图像为255）
    L = 255.0
    K1 = 0.01
    K2 = 0.03
    C1 = (K1 * L) ** 2
    C2 = (K2 * L) ** 2

    # 确保窗口大小为奇数，且不超过图像尺寸
    win_size = min(win_size, x.shape[0], x.shape[1])
    if win_size % 2 == 0:
        win_size += 1  # 转为奇数

    # 高斯核参数（sigma根据窗口大小自适应）
    sigma = 1.0 if win_size <= 3 else 1.0 * (win_size - 1) / 6.0

    # 1. 计算局部均值（用高斯滤波实现加权局部均值）
    # 高斯核：win_size x win_size，sigma=sigma，归一化
    gauss_kernel = cv2.getGaussianKernel(win_size, sigma)
    gauss_kernel = np.outer(gauss_kernel, gauss_kernel)  # 转为2D核
    mu_x = cv2.filter2D(x, -1, gauss_kernel)  # 图像x的局部均值
    mu_y = cv2.filter2D(y, -1, gauss_kernel)  # 图像y的局部均值

    # 2. 计算均值的平方和乘积
    mu_x_sq = mu_x ** 2
    mu_y_sq = mu_y ** 2
    mu_xy = mu_x * mu_y

    # 3. 计算局部方差和协方差
    sigma_x_sq = cv2.filter2D(x ** 2, -1, gauss_kernel) - mu_x_sq  # E[x²] - (E[x])²
    sigma_y_sq = cv2.filter2D(y ** 2, -1, gauss_kernel) - mu_y_sq  # E[y²] - (E[y])²
    sigma_xy = cv2.filter2D(x * y, -1, gauss_kernel) - mu_xy  # E[xy] - E[x]E[y]

    # 4. 计算SSIM的三个分量（亮度、对比度、结构）
    numerator = (2 * mu_xy + C1) * (2 * sigma_xy + C2)
    denominator = (mu_x_sq + mu_y_sq + C1) * (sigma_x_sq + sigma_y_sq + C2)
    ssim_map = numerator / denominator  # 每个像素的SSIM值

    # 5. 全局SSIM为所有像素的平均值
    return np.mean(ssim_map)


def calculate_channel_means(image_array):
    """
    计算每个通道的平均像素值。

    参数:
    image_array (ndarray): 大小为 (width, height, 3) 的图像数组。

    返回:
    tuple: 每个通道的平均值 (mean_R, mean_G, mean_B)。
    """
    # 确保输入是一个三维数组
    if image_array.ndim != 3 or image_array.shape[2] != 3:
        raise ValueError("输入数组必须是 (width, height, 3) 的形状")

    # 计算每个通道的平均值
    mean_R = np.mean(image_array[:, :, 0])
    mean_G = np.mean(image_array[:, :, 1])
    mean_B = np.mean(image_array[:, :, 2])

    return mean_R, mean_G, mean_B


def calculate_brightness_from_array(image_array):
    """
    计算图像的平均亮度。

    参数:
    image_array (ndarray): 大小为 (width, height, 3) 的图像数组。

    返回:
    float: 图像的平均亮度。
    """
    # 确保输入是一个三维数组
    if image_array.ndim != 3 or image_array.shape[2] != 3:
        raise ValueError("输入数组必须是 (width, height, 3) 的形状")

    # 将图像转换为 YUV 颜色空间
    yuv_image = cv2.cvtColor(image_array, cv2.COLOR_BGR2YUV)

    # 提取 Y 通道
    y_channel = yuv_image[:, :, 0]

    # 计算 Y 通道的平均值，作为亮度
    brightness = np.mean(y_channel)

    return brightness


def calculate_gray_variance(image_path, bounds):
    # 打开图像
    image = Image.open(image_path)

    # 裁剪图像到指定的边界框
    cropped_image = image.crop(bounds)

    # 转换为NumPy数组
    image_array = np.array(cropped_image)
    if not isinstance(image_array, np.ndarray):
        raise ValueError("Input must be a NumPy array")

        # 转换为灰度图像
    gray_image = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)

    # 计算灰度方差
    variance = gray_image.var()

    return variance


def calculate_size(datas):
    dist_1 = datas[0]
    dist_2 = datas[1]
    if dist_1 >= dist_2:
        idx = 0
    else:
        idx = 1
    return idx


def find_outlier_images_from_pair(images=None, render=False):
    histograms = []
    for i, image in enumerate(images):
        # 确保数组是uint8类型，并且是三通道
        if image.dtype != np.uint8:
            image = image.astype(np.uint8)
        if image.shape[2] != 3:
            raise ValueError("输入数组必须是三通道的")

        # 创建图像对象
        image = Image.fromarray(image)
        image = image.convert('RGB')

        # 保存图像
        image.save(f"/home/limengqi/{i}.jpeg")
        # histograms.append(calculate_channel_means(image))
    # histograms_red_avg = [histogram[0] for histogram in histograms]
    # idx = calculate_size(histograms_red_avg)
    # return idx


from PIL import Image, ImageDraw


def draw_bounding_boxes(image_path, bounds_list, output_path):
    # 打开图像
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)

    # 遍历每个边界框并绘制
    for bounds in bounds_list:
        x1, y1, x2, y2 = bounds
        draw.rectangle([x1, y1, x2, y2], outline="red", width=2)

    # 保存带有边界框的图像
    image.save(output_path)


from PIL import Image


def crop_and_save(image_path, bounds_list):
    # 打开图像文件
    image = Image.open(image_path)
    # 遍历每个坐标区域并裁剪
    metrixs = []
    for i, bounds in enumerate(bounds_list):
        # 裁剪图像
        cropped_image = image.crop(bounds)
        # 保存裁剪后的图像
        cropped_image.save(f'/home/limengqi/datas/cropped_image_{i}.jpg')
        image_matrix = np.array(cropped_image)
        metrixs.append(image_matrix)
    return metrixs


def split_and_save_upper_half(image_path, output_path):
    # 打开图像
    with Image.open(image_path) as img:
        # 获取图像的宽度和高度
        width, height = img.size

        # 计算中间位置
        middle = height // 2

        # 裁剪出上半部分
        upper_half = img.crop((0, 0, width, middle))

        # 保存上半部分
        upper_half.save(output_path)


# 计算控件区域亮度
def cal_lightness(image: np.ndarray = None):
    # 检查输入图像是否有效
    if image is None:
        raise ValueError("输入图像不能为空")

    # 检查图像维度是否正确
    if len(image.shape) != 3 or image.shape[2] != 3:
        raise ValueError("输入图像必须是3通道的BGR图像")

    # 将BGR图像转换为HSV色彩空间
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # 提取V通道（亮度通道）
    v_channel = hsv_image[:, :, 2]

    # 计算亮度通道的平均值作为图像亮度
    lightness = np.mean(v_channel)

    return lightness


# 求控件框线经过的地方像素值方差
def widget_line_variance(image_path, bounds):
    # 读取图像
    image = cv2.imread(image_path)
    H, W, C = image.shape
    # 转换为灰度图像
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 提取边界框的坐标
    x1, y1, x2, y2 = bounds
    if x1 >= W or x2 >= W:
        x1 -= 1
        x2 -= 1
    if y1 >= H or y2 >= H:
        y1 -= 1
        y2 -= 1
    # 获取四条线段的灰度值
    top_line = gray_image[y1, x1:x2 + 1]
    bottom_line = gray_image[y2, x1:x2 + 1]
    left_line = gray_image[y1:y2 + 1, x1]
    right_line = gray_image[y1:y2 + 1, x2]

    # 合并所有线条的灰度值
    all_lines = np.concatenate((top_line, bottom_line, left_line, right_line))

    # 计算方差
    variance = np.var(all_lines)

    return variance


def calculate_variance(image_path, bound):
    # 读取图像
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("图像加载失败，请检查路径。")

    x1, y1, x2, y2 = bound
    # 裁剪图像到指定区域
    cropped_image = image[y1:y2, x1:x2]

    # 获取裁剪区域的宽度和高度
    height, width = cropped_image.shape

    # 按宽度三等分
    third_width = width // 3
    left_region = cropped_image[:, :third_width]
    middle_region = cropped_image[:, third_width:2 * third_width]
    right_region = cropped_image[:, 2 * third_width:]

    # 计算中间区域灰度方差
    middle_variance = np.var(middle_region)
    logger.info(f"image_path:{image_path}的中间区域灰度方差是：{middle_variance}，{bound}")
    if middle_variance <= 310:
        return True

    # 计算左右区域灰度方差
    left_variance = np.var(left_region)
    right_variance = np.var(right_region)
    logger.info(f"image_path:{image_path}的左边区域灰度方差是：{left_variance}，{bound}")
    logger.info(f"image_path:{image_path}的右边区域灰度方差是：{right_variance}，{bound}")
    left_variance_is_0 = left_variance <= 610
    right_variance_is_0 = right_variance <= 610

    if left_variance_is_0 ^ right_variance_is_0:
        return True

    # 按高度二等分
    half_height = height // 2
    top_region = cropped_image[:half_height, :]
    bottom_region = cropped_image[half_height:, :]

    # 计算上下区域灰度方差
    top_variance = np.var(top_region)
    bottom_variance = np.var(bottom_region)

    logger.info(f"image_path:{image_path}的上边区域灰度方差是：{top_variance}，{bound}")
    logger.info(f"image_path:{image_path}的下边区域灰度方差是：{bottom_variance}，{bound}")

    top_variance_is_0 = top_variance <= 20
    bottom_variance_is_0 = bottom_variance == 0
    if top_variance_is_0 ^ bottom_variance_is_0:
        return True
    return False


#
def load_image(image_path):
    return cv2.imread(image_path)


def crop_control(image, bounds):
    x1, y1, x2, y2 = bounds
    return image[y1:y2, x1:x2]


def count_unique_colors(control_image):
    control_image_rgb = cv2.cvtColor(control_image, cv2.COLOR_BGR2RGB)
    pixels = control_image_rgb.reshape(-1, 3)
    unique_colors = np.unique(pixels, axis=0)
    return len(unique_colors)


def find_clicked_control(image_path, controls_bounds):
    image = load_image(image_path)
    max_colors = -1
    clicked_index = None

    for index, bounds in enumerate(controls_bounds):
        control_image = crop_control(image, bounds)
        unique_color_count = count_unique_colors(control_image)

        if unique_color_count > max_colors:
            max_colors = unique_color_count
            clicked_index = index

    return clicked_index


def check_bound(image_path, bound):
    # 读取图像
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("图像加载失败，请检查路径。")

    # 获取图像的宽度
    image_height, image_width = image.shape[:2]

    x1, y1, x2, y2 = bound
    bound_width = x2 - x1
    bound_height = y2 - y1
    logger.info(f"{image_path}中操作控件的高度是：{bound_height}，宽度是：{bound_width}，图像的宽度是：{image_width}")
    # 检查条件
    if bound_height <= 50 and bound_width > (image_width * 3 / 4):
        return True
    else:
        return False


def is_bound_contained(bound1, bound2):
    x1, y1, x2, y2 = bound1
    x1_, y1_, x2_, y2_ = bound2

    # Check if bound1 is contained within bound2
    contained1 = x1_ <= x1 <= x2_ and x1_ <= x2 <= x2_ and y1_ <= y1 <= y2_ and y1_ <= y2 <= y2_

    # Check if bound2 is contained within bound1
    contained2 = x1 <= x1_ <= x2 and x1 <= x2_ <= x2 and y1 <= y1_ <= y2 and y1 <= y2_ <= y2

    return contained1 or contained2


def filter_invalid_bounds(bounds_list, image_path):
    # Load the image to get its dimensions
    with Image.open(image_path) as img:
        width, height = img.size
    total_area = width * height
    valid_bounds = []
    for bound in bounds_list:
        x1, y1, x2, y2 = bound
        # Check if coordinates are non-negative, within image bounds, and valid
        if (0 <= x1 < x2 <= width) and (0 <= y1 < y2 <= height):
            bound_area = (x2 - x1) * (y2 - y1)
            if bound_area / total_area < 0.5:
                valid_bounds.append(bound)

    unique_bounds = set(map(tuple, bounds_list))
    # Convert back to list of lists
    return [list(bound) for bound in unique_bounds]


def save_images_from_base64(base64_list, output_folder='/home/limengqi/data/output_images'):
    import os

    # 创建输出文件夹
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for i, b64_string in enumerate(base64_list):
        # 解码 Base64 字符串
        image_data = base64.b64decode(b64_string)

        # 转换为图像对象
        image = Image.open(BytesIO(image_data))

        # 保存图像
        image_path = os.path.join(output_folder, f'image_{i}.png')
        image.save(image_path)


# 黑白屏检测
def detect_monochrome_image(image_path, threshold=0.98):
    """
    检测图像是否为全黑或全白页面

    参数:
    image_path (str): 图像文件路径
    threshold (float): 判断阈值，范围0-1，值越大要求越严格

    返回:
    str: 'white' 表示全白, 'black' 表示全黑, 'normal' 表示正常图像
    """
    # 读取图像
    img = cv2.imread(image_path)

    if img is None:
        raise ValueError(f"Unable to read the image: {image_path}")

    # 转换为灰度图
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 计算图像像素总数
    total_pixels = gray.size

    # 计算黑色像素(0)和白色像素(255)的数量
    black_pixels = np.count_nonzero(gray == 0)
    white_pixels = np.count_nonzero(gray == 255)
    black_pixels_total_pixels = black_pixels / total_pixels
    white_pixels_total_pixels = white_pixels / total_pixels
    logger.info(
        f"{image_path}黑色比值：{black_pixels_total_pixels}，白色比值：{white_pixels_total_pixels}，阈值：{threshold}")
    # 判断是否为全黑页面
    if black_pixels_total_pixels >= threshold:
        return 'black'
    # 判断是否为全白页面
    if white_pixels_total_pixels >= threshold:
        return 'white'
        # 正常图像
    return 'normal'


def calculate_color_distance(color1, color2):
    """计算两个RGB颜色的欧氏距离（值越大，差异越大）"""
    r1, g1, b1 = color1
    r2, g2, b2 = color2
    return sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def get_circle_sample_points(x0, y0, radius, sample_count=20):
    """
    生成圆上均匀分布的采样点坐标
    :param center: 圆心 [x, y]
    :param radius: 半径
    :param sample_count: 采样点数量（默认20个，足够覆盖圆的所有方向）
    :return: 采样点列表 [(x1,y1), (x2,y2), ...]
    """
    sample_points = []
    # 按角度均匀生成采样点（0~2π弧度，即0~360度）
    for i in range(sample_count):
        angle = 2 * pi * i / sample_count  # 每个采样点的角度
        x = int(x0 + radius * cos(angle))  # 圆上点的x坐标
        y = int(y0 + radius * sin(angle))  # 圆上点的y坐标
        sample_points.append((x, y))
    return sample_points


def draw_visible_circle(image: np.ndarray = None, x1=None, y1=None, radius=60, thickness=5):
    """
    根据圆心位置颜色选择显眼框色，绘制圆形框并输出结果
    :param image_path: 输入图片路径
    :param center: 圆心坐标 [x, y]（注意：OpenCV 坐标为 (宽, 高)，需确保在图片范围内）
    :param radius: 框的半径（默认50）
    :param output_path: 输出图片路径
    :return: 选择的框色类别（"红色"/"绿色"/"蓝色"）
    """
    h, w, _ = image.shape
    sample_points = get_circle_sample_points(x1, y1, radius, 20)
    valid_points = []
    for (x, y) in sample_points:
        if 0 <= x < w and 0 <= y < h:  # 确保采样点在图片内
            valid_points.append((x, y))

    total_r, total_g, total_b = 0, 0, 0
    for (x, y) in valid_points:
        b, g, r = map(int, image[y, x])  # OpenCV读取顺序：BGR → 转为RGB
        total_r += r
        total_g += g
        total_b += b
    # 计算平均RGB颜色（四舍五入为整数）

    if len(valid_points) == 0:
        avg_r, avg_g, avg_b = 128, 128, 128
    else:
        avg_r = int(total_r / len(valid_points))
        avg_g = int(total_g / len(valid_points))
        avg_b = int(total_b / len(valid_points))
    avg_rgb = (avg_r, avg_g, avg_b)

    # 4. 定义候选框色（RGB格式）及类别，选择差异最大的颜色
    candidate_colors = [
        ((255, 0, 0), "红色"),  # 红色：RGB(255,0,0) → OpenCV BGR(0,0,255)
        ((0, 255, 0), "绿色"),  # 绿色：RGB(0,255,0) → OpenCV BGR(0,255,0)
        ((0, 0, 255), "蓝色")  # 蓝色：RGB(0,0,255) → OpenCV BGR(255,0,0)
    ]

    max_distance = -1
    selected_rgb = None
    selected_color_name = None
    for color_rgb, color_name in candidate_colors:
        distance = calculate_color_distance(avg_rgb, color_rgb)
        if distance > max_distance:
            max_distance = distance
            selected_rgb = color_rgb
            selected_color_name = color_name

    # 5. 绘制圆形框（OpenCV需用BGR格式，线宽设为2确保清晰）
    selected_bgr = (selected_rgb[2], selected_rgb[1], selected_rgb[0])  # RGB→BGR
    cv2.circle(image, (x1, y1), radius, selected_bgr, thickness=thickness)

    return image, selected_color_name


# 示例使用
if __name__ == "__main__":
    # [81,1146][493,1281] [493,1146][817,1281]
    # bounds_list = [[81,1146,493,1281], [493,1146,817,1281]]
    # imagepath = "/home/limengqi/datas/1754043043000.jpeg"
    # crop_and_save(imagepath, bounds_list)
    mage1_main = cv2.imread(r"/home/limengqi/datas/cropped_image_0.jpg")
    image2_main = cv2.imread(r"/home/limengqi/datas/cropped_image_1.jpg")
    img_1 = cal_lightness(mage1_main)
    img_2 = cal_lightness(image2_main)
    print(img_1, img_2)

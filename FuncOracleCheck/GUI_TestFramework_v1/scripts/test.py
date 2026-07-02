import cv2

from utils import cv_utils
import os

img_path = r"D:\GUI_TestFramework_Benchmark_0827\00ba4f13-c721-4491-83c1-b1c22db30e91#1755832141541\images\1158107831423533148_F98231F3BF7B436D9A6A05AB5F17B0F3_1754925008000.jpeg"

img=cv2.imread(img_path)

img_base64 = cv_utils.encode_image_to_base64_from_cv2(img)
print(img_base64.type())
img_cv2 = cv_utils.convert_base64_to_cv2(img_base64)
cv2.imwrite(os.path.join(os.path.dirname(img_path), '1.jpeg'), img_cv2)

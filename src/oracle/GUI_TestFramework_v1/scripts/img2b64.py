
import os
import json
import pdb

from utils import cv_utils

with open(r'D:\GUI_TestFramework_v1\examples\00ba4f13-c721-4491-83c1-b1c22db30e91#1755832141541\data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
#data = json_utils.load_json(r'D:\GUI_TestFramework_v1\examples\0d18920e-1db0-4a46-a64d-17b59c1de6f1#1755847026352\data.json')
pdb.set_trace()


pdb.set_trace()

for item in data['seq_info']:
    import pdb
    pdb.set_trace()
    img = cv_utils.encode_image_to_base64_by_pil(os.path.join(r'D:\GUI_TestFramework_v1\examples\00ba4f13-c721-4491-83c1-b1c22db30e91#1755832141541\images',item['image_relative_path']))
    item['image_relative_path'] = img

import pdb
pdb.set_trace()
with open(r'D:\GUI_TestFramework_v1\examples\00ba4f13-c721-4491-83c1-b1c22db30e91#1755832141541\data1.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)

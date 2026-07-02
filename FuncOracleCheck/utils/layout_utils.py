def get_texts_from_layout(tree_root):
    queues = []
    queues.append(tree_root)
    texts = []
    while queues:
        root = queues.pop(0)
        attributes = root.get('attributes')
        childrens = root.get('children')
        texts.append(attributes['text'])
        for i, children in enumerate(childrens):
            queues.append(children)
    return texts


def get_bounds_from_layout(tree_root):
    queues = []
    queues.append(tree_root)
    bounds = []
    while queues:
        root = queues.pop(0)
        attributes = root.get('attributes')
        childrens = root.get('children')
        bounds.append(covert_bounds(attributes['bounds']))
        for i, children in enumerate(childrens):
            queues.append(children)
    return bounds


def covert_bounds(input_string):
    output_list = eval(input_string.replace("][", ","))
    return output_list


def get_information_from_layout(tree_root):
    queues = []
    queues.append(tree_root)
    bounds = []
    texts = []
    node_types = []
    hints = []
    while queues:
        root = queues.pop(0)
        attributes = root.get('attributes')
        childrens = root.get('children')
        bounds.append(covert_bounds(attributes['bounds']))
        texts.append(attributes['text'])
        node_types.append(attributes['type'])
        hints.append(attributes.get('hint', ""))
        for i, children in enumerate(childrens):
            queues.append(children)
    assert len(texts) == len(node_types) == len(bounds), "属性个数不一致"
    return {"bounds": bounds, "texts": texts, "types": node_types, "hints": hints}


if __name__ == '__main__':
    from utils import json_utils
    datas = json_utils.load_json("/home/limengqi/data/bad_case/1754993078000.json")
    result = get_texts_from_layout(datas)
    print(result)

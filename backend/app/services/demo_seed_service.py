from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TRAINING_CLASSES_PATHS = [
    PROJECT_ROOT / "config" / "locount_93_classes.txt",
    PROJECT_ROOT / "datasets" / "classes.txt",
]


def load_training_labels() -> list[str]:
    for classes_path in TRAINING_CLASSES_PATHS:
        if not classes_path.exists():
            continue
        labels = [
            line.strip()
            for line in classes_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if labels:
            return labels

    searched = ", ".join(str(path) for path in TRAINING_CLASSES_PATHS)
    raise FileNotFoundError(f"No training class list found. Searched: {searched}")



TRANSLATED_ITEM_NAMES_BY_LABEL = {
    "Adult Diapers": "成人纸尿裤",
    "Adult hat": "成人帽子",
    "Adult milk powder": "成人奶粉",
    "Adult shoes": "成人鞋",
    "Adult socks": "成人袜子",
    "Baby Furniture": "婴儿家具",
    "Baby Toys": "婴儿玩具",
    "Baby diapers": "婴儿纸尿裤",
    "Baby handkerchiefs": "婴儿手帕",
    "Baby milk powder": "婴儿奶粉",
    "Baby slippers": "婴儿拖鞋",
    "Baby tableware": "婴儿餐具",
    "Baby washing and nursing supplie": "婴儿洗护用品",
    "Badminton": "羽毛球",
    "Basin": "盆",
    "Basketball": "篮球",
    "Biscuits": "饼干",
    "Bowl": "碗",
    "Cake": "蛋糕",
    "Can": "罐头",
    "Carbonated drinks": "碳酸饮料",
    "Chewing gum": "口香糖",
    "Children Socks": "儿童袜子",
    "Children Toys": "儿童玩具",
    "Chocolates": "巧克力",
    "Chopping block": "砧板",
    "Chopsticks": "筷子",
    "Coat hanger": "衣架",
    "Cocktail": "鸡尾酒",
    "Coffee": "咖啡",
    "Cooking wine": "料酒",
    "Cotton swab": "棉签",
    "Dairy": "乳制品",
    "Desk lamp": "台灯",
    "Dinner plate": "餐盘",
    "Disposable bag": "一次性袋子",
    "Disposable cups": "一次性杯子",
    "Draw bar box": "拉杆箱",
    "Dried meat": "肉干",
    "Electric kettle": "电热水壶",
    "Electromagnetic furnace": "电磁炉",
    "Emulsion": "乳液",
    "Facial Cleanser": "洗面奶",
    "Facial mask": "面膜",
    "Flour": "面粉",
    "Football": "足球",
    "Guozhen": "果珍",
    "Hair dye": "染发剂",
    "Herbal tea": "凉茶",
    "Ice cream": "冰淇淋",
    "Jacket": "外套",
    "Lingerie": "女士内衣",
    "Liquor and Spirits": "烈酒",
    "Makeup tools": "化妆工具",
    "Microwave Oven": "微波炉",
    "Mixed congee": "杂粮粥",
    "Mug": "马克杯",
    "Noodle": "挂面",
    "Notebook": "笔记本",
    "Oats": "燕麦",
    "Pasta": "意大利面",
    "Pen": "笔",
    "Pencil case": "笔袋",
    "Pie": "派",
    "Pot shovel": "锅铲",
    "Potato chips": "薯片",
    "Quick-frozen Tangyuan": "速冻汤圆",
    "Quick-frozen Wonton": "速冻馄饨",
    "Quick-frozen dumplings": "速冻饺子",
    "Razor": "剃须刀",
    "Red wine": "红酒",
    "Rice cooker": "电饭煲",
    "Rise": "大米",
    "Rubber ball": "橡皮球",
    "Sauce": "酱料",
    "Sesame paste": "芝麻酱",
    "Shampoo": "洗发水",
    "Skin care set": "护肤套装",
    "Soap": "香皂",
    "Socket": "插座",
    "Soup ladle": "汤勺",
    "Sports cup": "运动水杯",
    "Stool": "凳子",
    "Storage box": "收纳箱",
    "Tampon": "卫生棉条",
    "Tea": "茶叶",
    "Tea beverage": "茶饮料",
    "Thermos bottle": "保温瓶",
    "Toothbrush": "牙刷",
    "Toothpaste": "牙膏",
    "Trash": "垃圾桶",
    "Trousers": "裤子",
    "Vinegar": "醋",
}

CURATED_ITEMS_BY_LABEL = {
    "Carbonated drinks": {
        "id": "ITEM101",
        "name": TRANSLATED_ITEM_NAMES_BY_LABEL["Carbonated drinks"],
        "category": "饮料",
        "aisle": "A1",
        "threshold": 8,
    },
    "Biscuits": {
        "id": "ITEM103",
        "name": TRANSLATED_ITEM_NAMES_BY_LABEL["Biscuits"],
        "category": "零食",
        "aisle": "C1",
        "threshold": 8,
    },
    "Potato chips": {
        "id": "ITEM104",
        "name": TRANSLATED_ITEM_NAMES_BY_LABEL["Potato chips"],
        "category": "零食",
        "aisle": "C2",
        "threshold": 6,
    },
    "Chocolates": {
        "id": "ITEM105",
        "name": TRANSLATED_ITEM_NAMES_BY_LABEL["Chocolates"],
        "category": "零食",
        "aisle": "C3",
        "threshold": 8,
    },
    "Shampoo": {
        "id": "ITEM106",
        "name": TRANSLATED_ITEM_NAMES_BY_LABEL["Shampoo"],
        "category": "日用品",
        "aisle": "D1",
        "threshold": 4,
    },
    "Toothpaste": {
        "id": "ITEM107",
        "name": TRANSLATED_ITEM_NAMES_BY_LABEL["Toothpaste"],
        "category": "日用品",
        "aisle": "D2",
        "threshold": 5,
    },
}


def build_inventory_item(label: str, class_index: int) -> dict:
    curated = CURATED_ITEMS_BY_LABEL.get(label)
    if curated:
        return {
            **curated,
            "current_stock": 0,
            "status": "out",
        }

    return {
        "id": f"CLASS{class_index + 1:03d}",
        "name": TRANSLATED_ITEM_NAMES_BY_LABEL[label],
        "category": "自动映射",
        "aisle": "AUTO",
        "threshold": 3,
        "current_stock": 0,
        "status": "out",
    }


def build_full_demo_seed_catalog() -> tuple[list[dict], list[dict]]:
    labels = load_training_labels()
    missing_labels = [
        label for label in labels if label not in TRANSLATED_ITEM_NAMES_BY_LABEL
    ]
    if missing_labels:
        raise ValueError(
            "Missing Chinese translations for labels: "
            + ", ".join(sorted(missing_labels))
        )

    items = []
    mappings = []

    for index, label in enumerate(labels):
        item = build_inventory_item(label, index)
        items.append(item)
        mappings.append(
            {
                "detection_label": label,
                "item_id": item["id"],
            }
        )

    return items, mappings

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportCategory:
    key: str
    name: str
    color: str


class ReportCategoryService:
    FOOD_BEVERAGE = ReportCategory("food_beverage", "食品饮料", "#2563eb")
    PERSONAL_CARE = ReportCategory("personal_care", "个护日化", "#16a34a")
    MATERNAL_CHILD = ReportCategory("maternal_child", "母婴儿童", "#f97316")
    HOME_KITCHEN = ReportCategory("home_kitchen", "家居厨具", "#7c3aed")
    CLOTHING = ReportCategory("clothing", "服饰鞋帽", "#db2777")
    SPORTS_STATIONERY_TOYS = ReportCategory(
        "sports_stationery_toys",
        "文体玩具",
        "#0891b2",
    )
    APPLIANCES = ReportCategory("appliances", "家用电器", "#dc2626")
    OTHER = ReportCategory("other", "其他", "#6b7280")

    CATEGORIES = (
        FOOD_BEVERAGE,
        PERSONAL_CARE,
        MATERNAL_CHILD,
        HOME_KITCHEN,
        CLOTHING,
        SPORTS_STATIONERY_TOYS,
        APPLIANCES,
        OTHER,
    )

    LABEL_TO_CATEGORY_KEY = {
        "Adult Diapers": PERSONAL_CARE.key,
        "Adult hat": CLOTHING.key,
        "Adult milk powder": FOOD_BEVERAGE.key,
        "Adult shoes": CLOTHING.key,
        "Adult socks": CLOTHING.key,
        "Baby Furniture": MATERNAL_CHILD.key,
        "Baby Toys": MATERNAL_CHILD.key,
        "Baby diapers": PERSONAL_CARE.key,
        "Baby handkerchiefs": PERSONAL_CARE.key,
        "Baby milk powder": MATERNAL_CHILD.key,
        "Baby slippers": MATERNAL_CHILD.key,
        "Baby tableware": MATERNAL_CHILD.key,
        "Baby washing and nursing supplie": PERSONAL_CARE.key,
        "Badminton": SPORTS_STATIONERY_TOYS.key,
        "Basin": HOME_KITCHEN.key,
        "Basketball": SPORTS_STATIONERY_TOYS.key,
        "Biscuits": FOOD_BEVERAGE.key,
        "Bowl": HOME_KITCHEN.key,
        "Cake": FOOD_BEVERAGE.key,
        "Can": FOOD_BEVERAGE.key,
        "Carbonated drinks": FOOD_BEVERAGE.key,
        "Chewing gum": FOOD_BEVERAGE.key,
        "Children Socks": CLOTHING.key,
        "Children Toys": MATERNAL_CHILD.key,
        "Chocolates": FOOD_BEVERAGE.key,
        "Chopping block": HOME_KITCHEN.key,
        "Chopsticks": HOME_KITCHEN.key,
        "Coat hanger": HOME_KITCHEN.key,
        "Cocktail": FOOD_BEVERAGE.key,
        "Coffee": FOOD_BEVERAGE.key,
        "Cooking wine": FOOD_BEVERAGE.key,
        "Cotton swab": PERSONAL_CARE.key,
        "Dairy": FOOD_BEVERAGE.key,
        "Desk lamp": APPLIANCES.key,
        "Dinner plate": HOME_KITCHEN.key,
        "Disposable bag": HOME_KITCHEN.key,
        "Disposable cups": HOME_KITCHEN.key,
        "Draw bar box": HOME_KITCHEN.key,
        "Dried meat": FOOD_BEVERAGE.key,
        "Electric kettle": APPLIANCES.key,
        "Electromagnetic furnace": APPLIANCES.key,
        "Emulsion": PERSONAL_CARE.key,
        "Facial Cleanser": PERSONAL_CARE.key,
        "Facial mask": PERSONAL_CARE.key,
        "Flour": FOOD_BEVERAGE.key,
        "Football": SPORTS_STATIONERY_TOYS.key,
        "Guozhen": FOOD_BEVERAGE.key,
        "Hair dye": PERSONAL_CARE.key,
        "Herbal tea": FOOD_BEVERAGE.key,
        "Ice cream": FOOD_BEVERAGE.key,
        "Jacket": CLOTHING.key,
        "Lingerie": CLOTHING.key,
        "Liquor and Spirits": FOOD_BEVERAGE.key,
        "Makeup tools": PERSONAL_CARE.key,
        "Microwave Oven": APPLIANCES.key,
        "Mixed congee": FOOD_BEVERAGE.key,
        "Mug": HOME_KITCHEN.key,
        "Noodle": FOOD_BEVERAGE.key,
        "Notebook": SPORTS_STATIONERY_TOYS.key,
        "Oats": FOOD_BEVERAGE.key,
        "Pasta": FOOD_BEVERAGE.key,
        "Pen": SPORTS_STATIONERY_TOYS.key,
        "Pencil case": SPORTS_STATIONERY_TOYS.key,
        "Pie": FOOD_BEVERAGE.key,
        "Pot shovel": HOME_KITCHEN.key,
        "Potato chips": FOOD_BEVERAGE.key,
        "Quick-frozen Tangyuan": FOOD_BEVERAGE.key,
        "Quick-frozen Wonton": FOOD_BEVERAGE.key,
        "Quick-frozen dumplings": FOOD_BEVERAGE.key,
        "Razor": PERSONAL_CARE.key,
        "Red wine": FOOD_BEVERAGE.key,
        "Rice cooker": APPLIANCES.key,
        "Rise": FOOD_BEVERAGE.key,
        "Rubber ball": SPORTS_STATIONERY_TOYS.key,
        "Sauce": FOOD_BEVERAGE.key,
        "Sesame paste": FOOD_BEVERAGE.key,
        "Shampoo": PERSONAL_CARE.key,
        "Skin care set": PERSONAL_CARE.key,
        "Soap": PERSONAL_CARE.key,
        "Socket": APPLIANCES.key,
        "Soup ladle": HOME_KITCHEN.key,
        "Sports cup": HOME_KITCHEN.key,
        "Stool": HOME_KITCHEN.key,
        "Storage box": HOME_KITCHEN.key,
        "Tampon": PERSONAL_CARE.key,
        "Tea": FOOD_BEVERAGE.key,
        "Tea beverage": FOOD_BEVERAGE.key,
        "Thermos bottle": HOME_KITCHEN.key,
        "Toothbrush": PERSONAL_CARE.key,
        "Toothpaste": PERSONAL_CARE.key,
        "Trash": HOME_KITCHEN.key,
        "Trousers": CLOTHING.key,
        "Vinegar": FOOD_BEVERAGE.key,
    }

    @classmethod
    def category_key_for_label(cls, detection_label: str | None) -> str:
        if not detection_label:
            return cls.OTHER.key
        return cls.LABEL_TO_CATEGORY_KEY.get(detection_label, cls.OTHER.key)

    @classmethod
    def api_categories(cls) -> list[dict[str, str]]:
        return [
            {
                "key": category.key,
                "name": category.name,
                "color": category.color,
            }
            for category in cls.CATEGORIES
        ]

    @classmethod
    def empty_values(cls) -> dict[str, int]:
        return {category.key: 0 for category in cls.CATEGORIES}


report_category_service = ReportCategoryService()

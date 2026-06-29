VALID_INTENTS = {"search", "recommendation", "order", "compare", "unknown", "product_search", "product_recommendation", "brand_search", "category_search", "refine_recommendation", "compare_options", "compare_plans", "create_order", "checkout", "history"}

VALID_CATEGORIES = {
    "Laptop", "Monitor", "Keyboard", "Mouse", "Headset", "Webcam",
    "Printer", "Office Chair", "Standing Desk", "Tablet", "Projector",
    "Router", "Docking Station", "External SSD", "Conference Speaker",
}

CATEGORY_ALIASES = {
    "电脑": "Laptop", "笔记本": "Laptop", "笔记本电脑": "Laptop",
    "显示器": "Monitor", "屏幕": "Monitor",
    "键盘": "Keyboard",
    "鼠标": "Mouse",
    "耳机": "Headset", "耳麦": "Headset",
    "摄像头": "Webcam", "相机": "Webcam",
    "打印机": "Printer",
    "办公椅": "Office Chair", "椅子": "Office Chair",
    "升降桌": "Standing Desk", "站立桌": "Standing Desk", "桌子": "Standing Desk",
    "平板": "Tablet", "平板电脑": "Tablet",
    "投影仪": "Projector",
    "路由器": "Router",
    "扩展坞": "Docking Station", "拓展坞": "Docking Station",
    "固态硬盘": "External SSD", "移动硬盘": "External SSD",
    "会议音箱": "Conference Speaker", "音箱": "Conference Speaker",
    "手机": "Phone",
}

BRAND_ALIASES = {
    "戴尔": "Dell", "DELL": "Dell",
    "联想": "Lenovo",
    "惠普": "HP",
    "苹果": "Apple",
    "三星": "Samsung",
    "索尼": "Sony",
    "华硕": "Asus",
    "宏碁": "Acer",
    "微软": "Microsoft",
    "罗技": "Logitech",
    "小米": "Xiaomi",
}

def validate_intent_schema(payload: dict) -> tuple[bool, list[str]]:
    errors = []

    intent = payload.get("intent")
    if intent is not None and intent not in VALID_INTENTS:
        errors.append("intent_not_in_valid_enum")

    budget = payload.get("budget")
    if budget is not None:
        try:
            b = float(budget)
            if b <= 0:
                errors.append("budget_must_be_positive")
        except (TypeError, ValueError):
            errors.append("budget_must_be_numeric")

    categories = payload.get("categories")
    if categories is not None:
        if not isinstance(categories, list):
            errors.append("categories_must_be_array")
        else:
            for cat in categories:
                if cat not in VALID_CATEGORIES and cat not in CATEGORY_ALIASES:
                    errors.append("category_not_recognized:" + str(cat))

    quantity = payload.get("quantity")
    if quantity is not None:
        try:
            q = int(quantity)
            if q <= 0:
                errors.append("quantity_must_be_positive")
        except (TypeError, ValueError):
            errors.append("quantity_must_be_integer")

    per_cat_qty = payload.get("per_category_quantities") or payload.get("quantity_per_category") or {}
    if per_cat_qty and isinstance(per_cat_qty, dict):
        for cat, qty in per_cat_qty.items():
            if cat not in VALID_CATEGORIES and cat not in CATEGORY_ALIASES:
                errors.append("per_category_quantities_key_not_recognized:" + str(cat))
            try:
                if int(qty) <= 0:
                    errors.append("per_category_quantities_value_not_positive:" + str(cat))
            except (TypeError, ValueError):
                errors.append("per_category_quantities_value_not_numeric:" + str(cat))

    return len(errors) == 0, errors

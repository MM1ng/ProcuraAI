from app.agent.category_normalizer import get_allowed_categories, normalize_category


def test_normalize_chinese_monitor_to_catalog_monitor():
    result = normalize_category("显示器", ["Laptop", "Monitor", "Keyboard"])

    assert result.normalized_category == "Monitor"
    assert result.normalization_method == "alias"
    assert result.warning is None


def test_normalize_case_insensitive_catalog_match():
    result = normalize_category("monitor", ["Laptop", "Monitor", "Keyboard"])

    assert result.normalized_category == "Monitor"
    assert result.normalization_method == "case_insensitive"
    assert result.warning is None


def test_allowed_categories_are_loaded_from_catalog(tmp_path):
    catalog = tmp_path / "products.csv"
    catalog.write_text(
        "\n".join(
            [
                "product_id,name,category,brand,price,rating,stock,supplier,delivery_days,warranty_months,compliance_level,description,tags",
                "P-1,Core Monitor,Monitor,Dell,200,4.7,10,Acme,3,12,Business,Monitor,monitor",
                "P-2,Meeting Hub,Meeting Display,ViewSonic,900,4.5,5,Acme,5,24,Business,Display,meeting-display",
                "P-3,Access Switch,Network Switch,Cisco,400,4.6,8,Acme,4,24,Business,Switch,network",
            ]
        ),
        encoding="utf-8",
    )

    assert get_allowed_categories(catalog) == ["Meeting Display", "Monitor", "Network Switch"]


def test_unknown_category_low_confidence_keeps_original():
    result = normalize_category("咖啡机", ["Laptop", "Monitor", "Keyboard"])

    assert result.normalized_category == "咖啡机"
    assert result.normalization_method == "unmatched"
    assert result.warning == "low_confidence_category_match"

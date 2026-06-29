from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from main import app


client = TestClient(app)


def test_export_excel_contains_selected_plan_rows_and_total():
    response = client.post(
        "/api/export/excel",
        json={
            "plan": {
                "items": [
                    {
                        "product_id": "dock-1",
                        "name": "Dell Dock",
                        "category": "Docking Station",
                        "brand": "Dell",
                        "supplier": "Contoso",
                        "quantity": 3,
                        "unit_price": 120.0,
                        "subtotal": 360.0,
                        "rating": 4.6,
                        "stock": 40,
                        "delivery_days": 2,
                        "reason": "Selected for Dell compatibility.",
                    }
                ],
                "total_amount": 360.0,
                "budget_status": "within_budget",
                "inventory_status": "valid",
                "constraint_satisfaction": "satisfied",
            }
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "procurement_plan.xlsx" in response.headers["content-disposition"]

    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook.active
    headers = [cell.value for cell in sheet[1]]
    assert headers == [
        "Product",
        "Category",
        "Brand",
        "Supplier",
        "Quantity",
        "Unit Price",
        "Subtotal",
        "Rating",
        "Stock",
        "Delivery Days",
        "Why Selected",
        "Total Cost",
    ]
    assert sheet["A2"].value == "Dell Dock"
    assert sheet["L2"].value == 360.0
    assert sheet["L3"].value == 360.0

from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel


router = APIRouter(prefix="/api/export", tags=["export"])


class ExcelExportRequest(BaseModel):
    plan: dict[str, Any]


HEADERS = [
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


def build_procurement_workbook(plan: dict[str, Any]) -> BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Procurement Plan"
    sheet.append(HEADERS)

    total_cost = float(plan.get("total_amount", 0) or 0)
    items = plan.get("items") or plan.get("selected_items") or []
    for item in items:
        sheet.append(
            [
                item.get("name", ""),
                item.get("category", ""),
                item.get("brand", ""),
                item.get("supplier", ""),
                int(item.get("quantity", 0) or 0),
                float(item.get("unit_price", 0) or 0),
                float(item.get("subtotal", 0) or 0),
                float(item.get("rating", 0) or 0),
                int(item.get("stock", 0) or 0),
                int(item.get("delivery_days", 0) or 0),
                item.get("reason", ""),
                total_cost,
            ]
        )

    total_row = len(items) + 2
    sheet.cell(row=total_row, column=11, value="Total Cost")
    sheet.cell(row=total_row, column=12, value=total_cost)
    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 48)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


@router.post("/excel")
def export_excel(request: ExcelExportRequest) -> StreamingResponse:
    output = build_procurement_workbook(request.plan)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="procurement_plan.xlsx"'},
    )

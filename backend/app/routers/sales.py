from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import storage
from ..models import SaleRecord

router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("")
def list_sales():
    return storage.list_sales()


@router.post("")
def upsert_sale(sale: SaleRecord):
    if not sale.id:
        sale.id = storage.new_id()
    saved = storage.upsert_sale(sale.model_dump(mode="json"))
    return saved


@router.delete("/{sale_id}")
def delete_sale(sale_id: str):
    storage.delete_sale(sale_id)
    return {"ok": True}

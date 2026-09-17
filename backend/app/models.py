"""Pydantic data models shared across the Buy Setup backend."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BuyeeCredentials(BaseModel):
    """Credentials are only ever held in memory for the duration of one
    scrape request. They are never written to disk, logged, or persisted
    in any database/config file."""

    username: str
    password: str


class Article(BaseModel):
    id: str
    source_invoice_id: str
    name: str
    photo_url: Optional[str] = None
    photo_local_path: Optional[str] = None
    item_price_jpy: float = 0.0
    japan_domestic_shipping_jpy: float = 0.0
    category: str = "default"
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CostInputs(BaseModel):
    """Everything needed to compute a landed cost in EUR for one article."""

    article_id: str
    item_price_jpy: float
    japan_domestic_shipping_jpy: float
    international_shipping_eur: float = 0.0
    jpy_to_eur_rate: float
    category: str = "default"
    customs_duty_rate_override: Optional[float] = None  # e.g. 0.025 for 2.5%
    vat_rate_override: Optional[float] = None  # e.g. 0.20 for 20%


class CostBreakdown(BaseModel):
    article_id: str
    item_price_eur: float
    japan_domestic_shipping_eur: float
    international_shipping_eur: float
    customs_duty_rate: float
    vat_rate: float
    dutiable_base_eur: float
    customs_duty_eur: float
    vat_eur: float
    total_landed_cost_eur: float


class WhatnotStrategy(BaseModel):
    article_id: str
    total_landed_cost_eur: float
    safety_margin_rate: float
    min_viable_price_eur: float
    can_start_at_1_eur: bool
    suggested_start_price_eur: float
    x2_threshold_eur: float
    x3_threshold_eur: float
    notes: str


class SalePlatform(str, Enum):
    whatnot = "whatnot"
    vinted = "vinted"
    ebay = "ebay"
    leboncoin = "leboncoin"
    autre = "autre"


class SaleStatus(str, Enum):
    a_lister = "a_lister"
    en_vente = "en_vente"
    vendu = "vendu"
    invendu = "invendu"


class SaleRecord(BaseModel):
    id: str
    article_id: str
    platform: SalePlatform
    status: SaleStatus = SaleStatus.a_lister
    listed_price_eur: Optional[float] = None
    sold_price_eur: Optional[float] = None
    sold_date: Optional[date] = None
    fees_eur: float = 0.0
    notes: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CustomsRate(BaseModel):
    category: str
    label: str
    duty_rate: float  # fraction, e.g. 0.025
    vat_rate: float = 0.20

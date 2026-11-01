import json
import sqlite3

import httpx
import pytest

from app import config, db, knowledge, site_sync


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "WC_CONSUMER_KEY", "")
    monkeypatch.setattr(config, "WC_CONSUMER_SECRET", "")
    db.init()
    with db.connect() as conn:
        site_sync._store(conn, {**site_sync.DEFAULTS, "url": "https://shop.test"})
        yield conn


def _prices(amount, cur="IRT", minor=0):
    return {"price": str(amount), "currency_code": cur, "currency_minor_unit": minor}


STORE = {
    "/wp-json/wc/store/v1/products": [
        {"id": 1, "type": "simple", "name": "AirPods Pro &amp; Case", "permalink": "https://shop.test/p/airpods",
         "prices": _prices(12_000_000), "is_in_stock": True, "categories": [{"name": "لوازم جانبی"}]},
        {"id": 2, "type": "variable", "name": "iPhone 15 Pro", "permalink": "https://shop.test/p/ip15",
         "categories": [{"name": "گوشی کارکرده"}], "prices": _prices(0),
         "variations": [{"id": 21, "attributes": [{"name": "حافظه", "value": "256GB"}, {"name": "رنگ", "value": "آبی"}]},
                        {"id": 22, "attributes": [{"name": "حافظه", "value": "512GB"}, {"name": "گارانتی", "value": "۱۸ ماه"}]}]},
    ],
    "/wp-json/wc/store/v1/products/21": {"id": 21, "prices": _prices(65_000_000), "is_in_stock": True},
    "/wp-json/wc/store/v1/products/22": {"id": 22, "prices": _prices(78_000_000), "is_in_stock": False},
}


def transport(routes, seen=None):
    def handler(req):
        if seen is not None:
            seen.append(req)
        body = routes.get(req.url.path)
        if body is None:
            return httpx.Response(404, json={"code": "rest_no_route"})
        if req.url.params.get("page", "1") != "1":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=body)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_store_api_simple_and_variable(c):
    knowledge.save_product(c, {"name": "دستی", "price": "1000"})
    st = await site_sync.sync(c, transport=transport(STORE))
    assert st["last_error"] == "" and st["last_count"] == 3 and st["last_api"] == "store"
    rows = {(r["name"], r["storage"]): r for r in knowledge.list_products(c)}
    air = rows[("AirPods Pro & Case", "")]
    assert air["price"] == 12_000_000 and air["condition"] == "new" and air["source"] == "site"
    v256 = rows[("iPhone 15 Pro", "256GB")]
    assert v256["color"] == "آبی" and v256["price"] == 65_000_000 and v256["condition"] == "used" and v256["in_stock"] == 1
    v512 = rows[("iPhone 15 Pro", "512GB")]
    assert v512["in_stock"] == 0 and "گارانتی" in v512["notes"]
    assert ("دستی", "") in rows   # محصول دستی می‌ماند
    assert "https://shop.test/p/ip15" in knowledge.products_text(c)

    # همگام‌سازی دوباره جایگزین می‌کند، تکرار نمی‌سازد
    await site_sync.sync(c, transport=transport(STORE))
    assert len(knowledge.list_products(c)) == 4


@pytest.mark.asyncio
async def test_rial_and_minor_units(c):
    routes = {"/wp-json/wc/store/v1/products": [
        {"id": 1, "type": "simple", "name": "x", "prices": _prices(1_234_567_800, "IRR", 2), "is_in_stock": True}]}
    await site_sync.sync(c, transport=transport(routes))
    # ۱۲٬۳۴۵٬۶۷۸ ریال = ۱٬۲۳۴٬۵۶۸ تومان (گرد)
    assert knowledge.list_products(c)[0]["price"] == 1_234_568
    site_sync.save_settings(c, {"currency": "IRT"})
    await site_sync.sync(c, transport=transport(routes))
    assert knowledge.list_products(c)[0]["price"] == 12_345_678


@pytest.mark.asyncio
async def test_failure_or_empty_keeps_previous_list(c):
    await site_sync.sync(c, transport=transport(STORE))
    st = await site_sync.sync(c, transport=transport({}))
    assert "Store API" in st["last_error"] and st["last_count"] == 3
    st = await site_sync.sync(c, transport=transport({"/wp-json/wc/store/v1/products": []}))
    assert "هیچ محصولی" in st["last_error"]
    assert len(knowledge.list_products(c)) == 3


@pytest.mark.asyncio
async def test_rest_v3_fallback_with_keys(c, monkeypatch):
    monkeypatch.setattr(config, "WC_CONSUMER_KEY", "ck_x")
    monkeypatch.setattr(config, "WC_CONSUMER_SECRET", "cs_x")
    routes = {
        "/wp-json/wc/v3/data/currencies/current": {"code": "IRR"},
        "/wp-json/wc/v3/products": [
            {"id": 5, "type": "variable", "name": "iPad Air", "permalink": "https://shop.test/ipad", "categories": []},
            {"id": 6, "type": "simple", "name": "Pencil", "price": "50000000", "stock_status": "outofstock"}],
        "/wp-json/wc/v3/products/5/variations": [
            {"price": "300000000", "stock_status": "instock", "attributes": [{"name": "pa_storage", "option": "128"}]}],
    }
    seen = []
    st = await site_sync.sync(c, transport=transport(routes, seen))
    assert st["last_api"] == "v3" and st["last_error"] == ""
    rows = {r["name"]: r for r in knowledge.list_products(c)}
    assert rows["iPad Air"]["price"] == 30_000_000 and rows["iPad Air"]["storage"] == "128"
    assert rows["Pencil"]["in_stock"] == 0
    assert any("authorization" in r.headers for r in seen if "/v3/" in r.url.path)


def test_url_validation(c):
    for bad in ("ftp://shop.test", "https://127.0.0.1", "http://localhost", "https://10.0.0.5"):
        with pytest.raises(ValueError):
            site_sync.save_settings(c, {"url": bad})
    with pytest.raises(ValueError):
        site_sync.save_settings(c, {"url": "", "enabled": True})


def test_migration_adds_columns(tmp_path):
    p = str(tmp_path / "old.db")
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, storage TEXT NOT NULL "
                "DEFAULT '', color TEXT NOT NULL DEFAULT '', condition TEXT NOT NULL DEFAULT 'new', price INTEGER, "
                "in_stock INTEGER NOT NULL DEFAULT 1, notes TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, "
                "updated_at REAL NOT NULL)")
    con.execute("INSERT INTO products(name, updated_at) VALUES ('قدیمی', 0)")
    con.commit(); con.close()
    db.init(p)
    with db.connect(p) as conn:
        r = conn.execute("SELECT name, source, url FROM products").fetchone()
        assert tuple(r) == ("قدیمی", "", "")

from __future__ import annotations

from wildberries_agent_mcp.calculations import (
    aggregate_sales_by_region,
    competitive_price_analysis,
    competitor_analysis,
    seo_score,
    weather_sales_impact,
)


def test_competitive_price_analysis_builds_interquartile_corridor() -> None:
    result = competitive_price_analysis(
        seller_price=120,
        competitor_prices=[80, 90, 100, 110, 120],
    )

    assert result["price_corridor"] == {
        "low": 90.0,
        "high": 110.0,
        "method": "25th–75th percentile of valid positive competitor prices",
    }
    assert result["position"] == "above_corridor"
    assert result["difference_to_median_percent"] == 20.0
    assert result["target_price"] == 100.0


def test_competitive_price_analysis_respects_explicit_cost_floor() -> None:
    result = competitive_price_analysis(
        seller_price=100,
        competitor_prices=[80, 90, 100],
        cost_price=90,
        target_margin_percent=25,
    )

    assert result["corridor_target_price"] == 90.0
    assert result["minimum_viable_price"] == 120.0
    assert result["target_price"] == 120.0


def test_competitor_analysis_extracts_prices_and_reports_bad_rows() -> None:
    result = competitor_analysis(
        seller_price=100,
        competitor_rows=[
            {"price": 90},
            {"discountedPrice": "110"},
            {"price": 0},
            {"name": "missing price"},
        ],
    )

    assert result["competitor_count"] == 2
    assert result["source_row_count"] == 4
    assert result["malformed_row_count"] == 2
    assert result["position"] == "within_corridor"


def test_aggregate_sales_by_region_returns_totals_and_shares() -> None:
    result = aggregate_sales_by_region(
        rows=[
            {"region": "Central", "sales": 2, "revenue": 200},
            {"regionName": "Central", "quantity": 1, "finishedPrice": 100},
            {"region": "Volga", "sales": 1, "revenue": 100},
            {"region": "Ignored"},
        ]
    )

    assert result["totals"] == {"sales": 4, "revenue": 400.0, "region_count": 2}
    assert result["skipped_row_count"] == 1
    assert result["regions"][0]["region"] == "Central"
    assert result["regions"][0]["sales_share_percent"] == 75.0
    assert result["regions"][0]["revenue_share_percent"] == 75.0


def test_weather_sales_impact_reports_correlation_with_causality_caveat() -> None:
    result = weather_sales_impact(
        observations=[
            {"temperature_c": 10, "sales": 20},
            {"temperature_c": 12, "sales": 24},
            {"temperature_c": 14, "sales": 28},
            {"temperature_c": 16, "sales": 32},
        ]
    )

    assert result["status"] == "observed_correlation"
    assert result["correlation"] == 1.0
    assert result["direction"] == "positive"
    assert result["strength"] == "strong"
    assert "does not establish" in result["caveat"]


def test_weather_sales_impact_is_conservative_for_small_samples() -> None:
    result = weather_sales_impact(
        observations=[
            {"temperature": 10, "sales": 20},
            {"temperature": 12, "sales": 24},
            {"temperature": 14, "sales": 28},
        ]
    )

    assert result["status"] == "insufficient_data"
    assert result["correlation"] is None


def test_seo_score_exposes_full_breakdown_and_marketplace_caveat() -> None:
    result = seo_score(
        title="Умная лампа LED для дома",
        description=(
            "Умная лампа LED даёт мягкий свет для дома, управляется со смартфона "
            "и помогает настроить комфортное освещение в каждой комнате."
        ),
        keywords=["умная лампа", "LED", "для дома"],
        characteristics={
            "power": "10 W",
            "color": "white",
            "socket": "E27",
            "app": True,
        },
    )

    assert result["score"] == 100
    assert result["breakdown"]["characteristics"] == 20
    assert result["suggestions"] == []
    assert "not a prediction" in result["caveat"]

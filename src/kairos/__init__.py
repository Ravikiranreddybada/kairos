"""Kairos: supply-chain decision intelligence.

Layers (dependencies only point downward):

    api / mcp_server / cli      <- delivery
    agent                       <- orchestration (LangGraph)
    rag / llm                   <- language layer
    forecasting / inventory / anomaly   <- decision science
    data                        <- warehouse, contracts, synthetic generator
    config / observability      <- cross-cutting
"""

__version__ = "0.1.0"

"""``kairos`` command line.

    kairos seed                 generate + load synthetic data
    kairos train [--no-promote] backtest, select, calibrate, register, promote
    kairos ask "question"       one copilot turn (prints JSON)
    kairos eval [--gate]        run the golden-set eval; --gate exits 1 on regression
    kairos serve                start the REST API
    kairos mcp                  start the MCP server on stdio
    kairos rollback             restore the previous champion
    kairos health               model drift / staleness report (JSON)
    kairos stress S01 SKU002 [--delay 7] [--shock 30]   Monte-Carlo supply-risk stress test
"""

from __future__ import annotations

import argparse
import json
import sys

from kairos.config import get_settings
from kairos.observability import configure_logging


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kairos")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    t = sub.add_parser("train")
    t.add_argument("--no-promote", action="store_true")
    a = sub.add_parser("ask")
    a.add_argument("question")
    a.add_argument("--session", default="cli")
    e = sub.add_parser("eval")
    e.add_argument("--gate", action="store_true")
    e.add_argument("--out", default="var/eval_report.json")
    s = sub.add_parser("serve")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    sub.add_parser("mcp")
    sub.add_parser("rollback")
    sub.add_parser("health")
    st = sub.add_parser("stress")
    st.add_argument("store_id")
    st.add_argument("sku_id")
    st.add_argument("--delay", type=float, default=0.0, help="supplier delay in days")
    st.add_argument("--shock", type=float, default=0.0, help="demand shock in percent")
    st.add_argument("--service-level", type=float, default=0.95)
    args = p.parse_args(argv)

    settings = get_settings()
    configure_logging("WARNING" if args.cmd in ("ask", "mcp", "eval", "health", "stress") else "INFO")

    if args.cmd == "seed":
        from kairos.bootstrap import seed

        wh = seed(settings)
        print(json.dumps({"seeded": str(settings.warehouse_path),
                          "rows": int(wh.query("SELECT COUNT(*) n FROM fact_sales").n[0])}))
    elif args.cmd == "train":
        from kairos.data.warehouse import Warehouse
        from kairos.forecasting.pipeline import train

        r = train(Warehouse(settings.warehouse_path), settings, promote=not args.no_promote)
        print(json.dumps({"run_id": r.run_id, "promoted": r.promoted, "spec": r.spec, "metrics": r.metrics,
                          "gates": r.gates}, indent=2))
    elif args.cmd == "ask":
        from kairos.bootstrap import build

        res = build(settings).copilot.ask(args.question, session_id=args.session)
        print(json.dumps(res.to_dict(), indent=2, default=str))
    elif args.cmd == "eval":
        from kairos.bootstrap import build
        from kairos.evals.runner import run

        report = run(build(settings, use_cache=False), out_path=args.out)
        print(json.dumps(report["summary"], indent=2))
        if args.gate and not report["summary"]["gate_passed"]:
            print("EVAL GATE FAILED", file=sys.stderr)
            return 1
    elif args.cmd == "serve":
        import uvicorn

        uvicorn.run("kairos.api.main:app", host=args.host, port=args.port, log_config=None)
    elif args.cmd == "mcp":
        from kairos.mcp_server import server

        server.mcp.run("stdio")
    elif args.cmd == "rollback":
        from kairos.data.warehouse import Warehouse
        from kairos.forecasting.pipeline import rollback

        print(json.dumps({"champion": rollback(Warehouse(settings.warehouse_path), settings)}))
    elif args.cmd in ("health", "stress"):
        from kairos.data.warehouse import Warehouse
        from kairos.forecasting.service import ForecastService

        svc = ForecastService(Warehouse(settings.warehouse_path, read_only=True), settings)
        out = svc.model_health() if args.cmd == "health" else svc.stress_test(
            args.store_id.upper(), args.sku_id.upper(), args.service_level, args.delay, args.shock)
        print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

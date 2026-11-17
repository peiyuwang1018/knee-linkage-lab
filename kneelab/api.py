"""Shared request dispatcher for the local server and the browser Python runtime."""
import json
from .model import Config, cycle
from .scan import DEFAULT_GRID, DEFAULT_LIMITS, scan
from .export import cycle_csv, scan_csv
from . import chain

GET_PATHS = {"/api/defaults", "/api/chain/defaults", "/api/health"}
POST_PATHS = {"/api/cycle", "/api/cycle.csv", "/api/scan", "/api/scan.csv",
              "/api/chain/cycle", "/api/chain/cycle.csv", "/api/chain/scan"}


def dispatch(path, data=None):
    if path == "/api/health":
        return {"app": "knee-linkage-lab", "version": "0.9.0"}
    if path == "/api/defaults":
        return dict(config=Config().to_dict(), grid=DEFAULT_GRID, limits=DEFAULT_LIMITS)
    if path == "/api/chain/defaults":
        return dict(config=chain.ChainConfig().to_dict(), catalog=chain.CATALOG)
    if path not in POST_PATHS:
        raise ValueError("Unknown solver request.")
    if not isinstance(data, dict):
        raise ValueError("Request body must be an object.")
    config = data.get("config", {})
    if path.startswith("/api/chain/"):
        if path == "/api/chain/scan":
            return chain.scan(config, data.get("chain_ids"))
        result = chain.evaluate(config)
        return chain.cycle_csv(result) if path.endswith(".csv") else result
    if path.startswith("/api/scan"):
        result = scan(config, data.get("grid"), data.get("limits"))
        return scan_csv(result) if path.endswith(".csv") else result
    result = cycle(config)
    return cycle_csv(result) if path.endswith(".csv") else result


def dispatch_json(path, payload):
    """JSON boundary avoids leaking Python proxies into worker messages."""
    return json.dumps(dispatch(path, json.loads(payload)), allow_nan=False)

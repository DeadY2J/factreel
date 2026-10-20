"""Cloudflare Workers AI helper with a daily "neurons" budget.

Workers AI gives 10,000 free neurons per day. Every call made by FactReel is counted in
``.factreel/cloudflare_neurons.json`` (UTC day, as Cloudflare bills it) and stops before
``[cloudflare] daily_neuron_cap`` so you never get an unexpected bill.
"""
from __future__ import annotations

import json
import time

import requests

from .config import Channel, read_secret
from .log import log


class CloudflareError(RuntimeError):
    pass


class Cloudflare:
    def __init__(self, channel: Channel):
        c = channel["cloudflare"]
        self.account = read_secret(c["account_id_env"])
        self.token = read_secret(c["api_token_env"])
        self.cap = float(c["daily_neuron_cap"])
        self.ledger = channel.state_dir / "cloudflare_neurons.json"

    @property
    def available(self) -> bool:
        return bool(self.account and self.token)

    def used_today(self) -> float:
        try:
            data = json.loads(self.ledger.read_text(encoding="utf-8"))
            return float(data["neurons"]) if data.get("date") == time.strftime("%Y-%m-%d", time.gmtime()) else 0.0
        except (OSError, ValueError, KeyError, TypeError):
            return 0.0

    def add(self, neurons: float) -> None:
        total = round(self.used_today() + neurons, 2)
        self.ledger.write_text(json.dumps({"date": time.strftime("%Y-%m-%d", time.gmtime()), "neurons": total}),
                               encoding="utf-8")

    def check_budget(self, estimate: float) -> None:
        if not self.available:
            raise CloudflareError("missing CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN")
        used = self.used_today()
        if used + estimate > self.cap:
            raise CloudflareError(f"daily neuron cap reached ({used:.0f}/{self.cap:.0f})")

    def run(self, model: str, *, estimate: float, json_body: dict | None = None, files: dict | None = None,
            timeout: float = 120) -> requests.Response:
        """POST to ``/ai/run/{model}`` after checking the budget, and record the real cost."""
        self.check_budget(estimate)
        try:
            res = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{self.account}/ai/run/{model}",
                                headers={"Authorization": f"Bearer {self.token}"}, json=json_body, files=files,
                                timeout=timeout)
        except requests.RequestException as e:
            raise CloudflareError(str(e)[:150]) from e
        try:
            cost = float(res.headers.get("cf-ai-neurons"))
        except (TypeError, ValueError):
            cost = estimate
        if res.status_code == 200:
            self.add(cost)
            log(f"  Cloudflare {model.split('/')[-1]}: {cost:.0f} neurons (today {self.used_today():.0f}/{self.cap:.0f})")
        return res

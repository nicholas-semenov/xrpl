"""Label-free, bounded first-four AML motif descriptions; never suspicion labels."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from feature_workspace.build_wallet_graph import WalletGraph
from feature_workspace.prepare_transactions import COLUMNS, require

WINDOWS = {"1h": 3600, "24h": 86400, "7d": 604800}
PATTERNS = {1: "fan_in", 2: "fan_out", 3: "scatter_gather", 4: "gather_scatter"}


@dataclass(frozen=True)
class Thresholds:
    fan_in_min_senders: int = 3
    fan_out_min_receivers: int = 3
    scatter_gather_min_intermediaries: int = 3
    gather_scatter_min_senders: int = 3
    gather_scatter_min_receivers: int = 3
    min_group_usd: float = 100.
    min_path_leg_usd: float = 10.
    min_flow_ratio: float = .5
    max_flow_ratio: float = 1.5
    max_candidate_path_pairs: int = 5_000_000
    max_retained_paths: int = 2_000_000
    max_gather_scatter_candidates: int = 5_000_000
    max_scatter_gather_path_checks: int = 100_000_000
    max_witness_memberships: int = 100_000_000

    def validate(self) -> None:
        for name, value in asdict(self).items():
            require(isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value) and value > 0,
                    f"Invalid threshold: {name}")
            if "_min_" in name or name.startswith("max_") and name != "max_flow_ratio":
                require(isinstance(value, int), f"Threshold must be integral: {name}")
        for name in ["fan_in_min_senders", "fan_out_min_receivers", "scatter_gather_min_intermediaries",
                     "gather_scatter_min_senders", "gather_scatter_min_receivers"]:
            require(getattr(self, name) >= 2, f"Need multiple distinct wallets: {name}")
        require(self.min_flow_ratio <= self.max_flow_ratio, "Inverted flow-ratio range")


class Budget:
    """Fail explicitly on limits; never return silently sampled/truncated motifs."""
    def __init__(self, thresholds: Thresholds):
        self.thresholds = thresholds
        self.counts = {k: 0 for k in ["candidate_path_pairs", "retained_paths", "gather_scatter_candidates",
                                     "scatter_gather_path_checks", "witness_memberships"]}

    def add(self, key: str, count: int) -> None:
        self.counts[key] += int(count)
        require(self.counts[key] <= getattr(self.thresholds, f"max_{key}"),
                f"Resource limit exceeded: {key}; raise the configured limit or use a smaller graph context")


class Features:
    """Numerical arrays and deterministic strongest-witness support per edge."""
    def __init__(self, n: int, budget: Budget):
        self.n, self.budget = n, budget
        self.data, self.descriptions, self.scores = {}, {}, {}
        self.witness_counts = {}

    def add(self, name: str, values: np.ndarray, description: str) -> None:
        self.data[name] = values
        self.descriptions[name] = description

    def witness(self, prefix: str, fields: dict[str, str]) -> None:
        self.scores[prefix] = np.full(self.n, -1, dtype="int64")
        self.witness_counts[prefix] = 0
        self.add(f"{prefix}_detected", np.zeros(self.n, dtype="int8"), f"Membership in any qualifying {prefix} witness")
        for field, description in fields.items():
            is_count = field.endswith("count")
            self.add(f"{prefix}_{field}", np.full(self.n, -1. if "delay" in field else 0.,
                                                dtype="int64" if is_count else "float64"), description)

    def record(self, prefix: str, ids: np.ndarray, rank: int, **metrics) -> None:
        ids = np.unique(ids)
        self.budget.add("witness_memberships", len(ids))
        self.witness_counts[prefix] += 1
        self.data[f"{prefix}_detected"][ids] = 1
        chosen = ids[rank > self.scores[prefix][ids]]
        self.scores[prefix][chosen] = rank
        for field, value in metrics.items():
            self.data[f"{prefix}_{field}"][chosen] = value


class Events:
    """Arrays/indexes from one wallet graph; self-payments never supply motif evidence."""
    def __init__(self, graph: WalletGraph):
        e = graph.edges
        self.edges = e
        self.t = e.TIMESTAMP.to_numpy(dtype="int64")
        self.source = e.SENDER.to_numpy()
        self.dest = e.RECEIVER.to_numpy()
        self.paid = e.SOURCE_AMOUNT_USD.to_numpy()
        self.credit = e.DESTINATION_AMOUNT_USD.to_numpy()
        self.external = self.source != self.dest
        self.incoming = {w: ids[self.external[ids]] for w, ids in graph._incoming.items()}
        self.outgoing = {w: ids[self.external[ids]] for w, ids in graph._outgoing.items()}
        self.empty = np.array([], dtype="int64")

    def window_stats(self, wallets: np.ndarray, incoming: bool, window: int, mode: str) -> tuple:
        """Modes: past [t-W,t], prior [t-W,t), future (t,t+W]."""
        groups = self.incoming if incoming else self.outgoing
        counterpart = self.source if incoming else self.dest
        amounts = self.credit if incoming else self.paid
        counts = np.zeros(len(self.t), dtype="int64")
        distinct = counts.copy()
        volume = np.zeros(len(self.t))
        delay = np.full(len(self.t), -1.)
        query_groups = pd.Series(np.arange(len(wallets))).groupby(wallets, sort=True)
        for wallet, positions in query_groups:
            query = positions.to_numpy()
            ids = groups.get(wallet, self.empty)
            times = self.t[ids]
            if mode == "future":
                lo = np.searchsorted(times, self.t[query], side="right")
                hi = np.searchsorted(times, self.t[query] + window, side="right")
            else:
                lo = np.searchsorted(times, self.t[query] - window, side="left")
                hi = np.searchsorted(times, self.t[query], side="right" if mode == "past" else "left")
            for q, left, right in zip(query, lo, hi):
                selected = ids[left:right]
                counts[q] = len(selected)
                if len(selected):
                    distinct[q] = len(np.unique(counterpart[selected]))
                    volume[q] = amounts[selected].sum()
                    delay[q] = self.t[selected[0]] - self.t[q] if mode == "future" else self.t[q] - self.t[selected[-1]]
        return counts, distinct, volume, delay


def ratio_in_range(ratio: float | np.ndarray, cfg: Thresholds):
    return (ratio >= cfg.min_flow_ratio - 1e-12) & (ratio <= cfg.max_flow_ratio + 1e-12)


def compatible_paths(e: Events, cfg: Thresholds, budget: Budget) -> pd.DataFrame:
    """All compatible, strictly time-respecting two-hop event pairs, bounded to 7d.

    Ratios compare second-leg actual USD spend against first-leg delivered USD.
    This is observable amount similarity, not proof of ownership of specific funds.
    """
    first, second = [], []
    for middle, incoming in sorted(e.incoming.items()):
        outgoing = e.outgoing.get(middle, e.empty)
        times = e.t[outgoing]
        for i in incoming:
            lo = np.searchsorted(times, e.t[i], side="right")
            hi = np.searchsorted(times, e.t[i] + WINDOWS["7d"], side="right")
            candidates = outgoing[lo:hi]
            budget.add("candidate_path_pairs", len(candidates))
            if e.credit[i] < cfg.min_path_leg_usd:
                continue
            ratios = e.paid[candidates] / e.credit[i]
            candidates = candidates[(e.source[i] != e.dest[candidates]) &
                                    (e.paid[candidates] >= cfg.min_path_leg_usd) & ratio_in_range(ratios, cfg)]
            budget.add("retained_paths", len(candidates))
            if len(candidates):
                first.append(np.full(len(candidates), i, dtype="int64"))
                second.append(candidates)
    i = np.concatenate(first) if first else e.empty
    j = np.concatenate(second) if second else e.empty
    return pd.DataFrame({"first": i, "second": j, "source": e.source[i], "destination": e.dest[j],
                         "middle": e.dest[i], "start": e.t[i], "end": e.t[j], "delay": e.t[j] - e.t[i]})


def context_features(e: Events, store: Features, label: str, window: int) -> None:
    for role, wallets, incoming, mode in [
        ("sender_out", e.source, False, "past"), ("receiver_in", e.dest, True, "past"),
        ("sender_prior_in", e.source, True, "prior"), ("receiver_future_out", e.dest, False, "future"),
    ]:
        count, distinct, usd, delay = e.window_stats(wallets, incoming, window, mode)
        store.add(f"{role}_count_{label}", count, f"External {role} transactions in {mode} {label} window")
        store.add(f"{role}_unique_wallets_{label}", distinct, f"Distinct external counterparties in {role} {label} window")
        store.add(f"{role}_usd_{label}", usd, f"Delivered USD for incoming / spent USD for outgoing {role} window")
        if mode in ("prior", "future"):
            store.add(f"{role}_delay_seconds_{label}", delay, f"Nearest strict {mode} event delay; -1 if absent within {label}")
    prior = store.data[f"sender_prior_in_usd_{label}"]
    future = store.data[f"receiver_future_out_usd_{label}"]
    store.add(f"sender_spend_to_prior_inflow_ratio_{label}", np.divide(e.paid, prior, out=np.zeros(len(prior)), where=prior > 0),
              "Current source USD / preceding sender credits; zero if absent (use count to distinguish)")
    store.add(f"receiver_future_out_to_payment_ratio_{label}", future / e.credit,
              "Receiver future outgoing USD / current delivered USD; observable flow proxy, not fund attribution")


def detect_fans(e: Events, store: Features, cfg: Thresholds, label: str, window: int) -> None:
    for pattern, groups, counterpart, amount, minimum in [
        ("fan_in", e.incoming, e.source, e.credit, cfg.fan_in_min_senders),
        ("fan_out", e.outgoing, e.dest, e.paid, cfg.fan_out_min_receivers),
    ]:
        prefix = f"{pattern}_{label}"
        store.witness(prefix, {"counterparty_count": "Distinct counterparties in strongest fan witness",
                               "volume_usd": "Total credited/spent USD in strongest fan witness"})
        for wallet, ids in sorted(groups.items()):
            times = e.t[ids]
            for end in np.unique(times):
                selected = ids[np.searchsorted(times, end - window, side="left"):np.searchsorted(times, end, side="right")]
                if len(selected) < minimum:
                    continue
                distinct = len(np.unique(counterpart[selected]))
                volume = float(amount[selected].sum())
                if distinct >= minimum and volume >= cfg.min_group_usd:
                    store.record(prefix, selected, distinct * (store.n + 1) + len(selected),
                                 counterparty_count=distinct, volume_usd=volume)


def path_features(e: Events, paths: pd.DataFrame, store: Features, label: str) -> None:
    i, j = paths["first"].to_numpy(dtype="int64"), paths.second.to_numpy(dtype="int64")
    delay = paths.delay.to_numpy()
    ratios = e.paid[j] / e.credit[i]
    for side, ids in [("forward", i), ("received", j)]:
        count = np.bincount(ids, minlength=store.n)
        minimum = np.full(store.n, np.inf)
        np.minimum.at(minimum, ids, delay)
        minimum[~np.isfinite(minimum)] = -1.
        mean_ratio = np.divide(np.bincount(ids, weights=ratios, minlength=store.n), count,
                               out=np.zeros(store.n), where=count > 0)
        store.add(f"{side}_compatible_path_count_{label}", count, "Count of amount-compatible strict two-hop event paths")
        store.add(f"{side}_path_min_delay_seconds_{label}", minimum, "Minimum compatible path delay; -1 if none")
        store.add(f"{side}_path_mean_flow_ratio_{label}", mean_ratio, "Mean middle-wallet spend/credit ratio; zero if no compatible paths")


def detect_scatter_gather(e: Events, paths: pd.DataFrame, store: Features, cfg: Thresholds,
                          label: str, window: int) -> None:
    prefix = f"scatter_gather_{label}"
    store.witness(prefix, {"path_count": "Number of compatible two-hop paths in strongest SG witness",
                           "intermediary_count": "Distinct intermediaries in strongest SG witness",
                           "flow_ratio": "Unique gathered destination USD / unique scattered source USD",
                           "min_delay_seconds": "Minimum branch forwarding delay in strongest SG witness"})
    for _, group in paths.groupby(["source", "destination"], sort=True):
        if len(group) < cfg.scatter_gather_min_intermediaries or group.middle.nunique() < cfg.scatter_gather_min_intermediaries:
            continue
        group = group.sort_values(["end", "start", "first", "second"])
        starts, ends = group.start.to_numpy(), group.end.to_numpy()
        first, second = group["first"].to_numpy(), group.second.to_numpy()
        middles, delays = group.middle.to_numpy(), group.delay.to_numpy()

        def evaluate(mask: np.ndarray) -> bool:
            store.budget.add("scatter_gather_path_checks", len(mask))
            if int(mask.sum()) < cfg.scatter_gather_min_intermediaries:
                return False
            distinct = len(np.unique(middles[mask]))
            if distinct < cfg.scatter_gather_min_intermediaries:
                return False
            ii, jj = np.unique(first[mask]), np.unique(second[mask])
            source_usd, destination_usd = e.paid[ii].sum(), e.credit[jj].sum()
            ratio = destination_usd / source_usd
            if min(source_usd, destination_usd) < cfg.min_group_usd or not ratio_in_range(ratio, cfg):
                return False
            store.record(prefix, np.concatenate([ii, jj]), int(mask.sum()), path_count=int(mask.sum()),
                         intermediary_count=distinct, flow_ratio=float(ratio), min_delay_seconds=int(delays[mask].min()))
            return True

        # A valid whole-group witness dominates all sub-witnesses by path count.
        if ends.max() - starts.min() <= window and evaluate(np.ones(len(group), dtype=bool)):
            continue
        for end in np.unique(ends):
            evaluate((starts >= end - window) & (ends <= end))


def detect_gather_scatter(e: Events, store: Features, cfg: Thresholds, label: str, window: int) -> None:
    """Whole-span <=W, with collection at/before a cut and redistribution strictly after it."""
    prefix = f"gather_scatter_{label}"
    store.witness(prefix, {"sender_count": "Distinct donors in strongest GS witness",
                           "receiver_count": "Distinct recipients in strongest GS witness",
                           "path_count": "Incoming-event count × outgoing-event count in strict GS phases",
                           "flow_ratio": "Unique outgoing source USD / unique incoming delivered USD",
                           "min_delay_seconds": "First redistribution minus last collection timestamp"})
    for hub, incoming in sorted(e.incoming.items()):
        outgoing = e.outgoing.get(hub, e.empty)
        if len(incoming) < cfg.gather_scatter_min_senders or len(outgoing) < cfg.gather_scatter_min_receivers:
            continue
        it, ot = e.t[incoming], e.t[outgoing]
        in_sum = np.r_[0., np.cumsum(e.credit[incoming])]
        out_sum = np.r_[0., np.cumsum(e.paid[outgoing])]
        for cut in np.unique(it):
            ih = np.searchsorted(it, cut, side="right")
            ol = np.searchsorted(ot, cut, side="right")
            upper = np.searchsorted(ot, cut + window, side="right")
            for end in np.unique(ot[ol:upper]):
                store.budget.add("gather_scatter_candidates", 1)
                il = np.searchsorted(it, end - window, side="left")
                oh = np.searchsorted(ot, end, side="right")
                if ih - il < cfg.gather_scatter_min_senders or oh - ol < cfg.gather_scatter_min_receivers:
                    continue
                collected, distributed = in_sum[ih] - in_sum[il], out_sum[oh] - out_sum[ol]
                ratio = distributed / collected
                if min(collected, distributed) < cfg.min_group_usd or not ratio_in_range(ratio, cfg):
                    continue
                ii, jj = incoming[il:ih], outgoing[ol:oh]
                senders, receivers = len(np.unique(e.source[ii])), len(np.unique(e.dest[jj]))
                if senders >= cfg.gather_scatter_min_senders and receivers >= cfg.gather_scatter_min_receivers:
                    count = len(ii) * len(jj)
                    store.record(prefix, np.concatenate([ii, jj]), count, sender_count=senders,
                                 receiver_count=receivers, path_count=count, flow_ratio=float(ratio),
                                 min_delay_seconds=int(e.t[jj[0]] - e.t[ii[-1]]))


def detect_patterns(graph: WalletGraph, cfg: Thresholds) -> tuple[pd.DataFrame, dict]:
    """Extend this split only; return chronological transactions and numerical schema."""
    cfg.validate()
    e = Events(graph)
    budget = Budget(cfg)
    store = Features(len(e.t), budget)
    paths = compatible_paths(e, cfg, budget)
    for label, window in WINDOWS.items():
        context_features(e, store, label, window)
        detect_fans(e, store, cfg, label, window)
        window_paths = paths.loc[paths.delay.le(window)]
        path_features(e, window_paths, store, label)
        detect_scatter_gather(e, window_paths, store, cfg, label, window)
        detect_gather_scatter(e, store, cfg, label, window)
    numeric = pd.DataFrame(store.data, index=graph.edges.index)
    require(np.isfinite(numeric.to_numpy()).all(), "Non-finite AML features")
    memberships = [np.logical_or.reduce([store.data[f"{name}_{w}_detected"].astype(bool) for w in WINDOWS])
                   for name in PATTERNS.values()]
    labels = [[pid for pid, mask in zip(PATTERNS, memberships) if mask[i]] for i in range(store.n)]
    result = pd.concat([graph.edges.loc[:, COLUMNS].copy(), pd.Series(labels, name="aml_pattern"), numeric], axis=1)
    require(result.loc[:, COLUMNS].equals(graph.edges.loc[:, COLUMNS]), "Original 15 fields changed")
    info = {"numeric_feature_columns": numeric.columns.tolist(), "feature_descriptions": store.descriptions,
            "resource_counts": budget.counts, "qualifying_witness_counts": store.witness_counts,
            "pattern_transaction_counts": {str(pid): int(mask.sum()) for pid, mask in zip(PATTERNS, memberships)},
            "pattern_counts_by_window": {w: {str(pid): int(store.data[f"{name}_{w}_detected"].sum())
                                                for pid, name in PATTERNS.items()} for w in WINDOWS},
            "transactions_with_any_pattern": sum(bool(x) for x in labels),
            "transactions_with_multiple_patterns": sum(len(x) > 1 for x in labels)}
    return result, info

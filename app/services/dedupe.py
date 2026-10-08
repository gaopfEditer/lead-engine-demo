from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Iterable

from sqlalchemy.orm import Session

from app.db.models import Company, MergeCluster
from app.services.normalize import extract_domain, normalize_address, normalize_phone


def _union_find(ids: list[int], pairs: list[tuple[int, int]]) -> dict[int, int]:
    parent = {i: i for i in ids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in pairs:
        union(a, b)
    return {i: find(i) for i in ids}


def build_merge_clusters(db: Session) -> list[MergeCluster]:
    companies = db.query(Company).order_by(Company.id).all()
    if not companies:
        return []

    by_domain: dict[str, list[int]] = defaultdict(list)
    by_phone: dict[str, list[int]] = defaultdict(list)
    by_address: dict[str, list[int]] = defaultdict(list)

    for c in companies:
        dom = c.domain or extract_domain(c.website_url)
        if dom:
            by_domain[dom].append(c.id)
        if c.phone_e164:
            by_phone[c.phone_e164].append(c.id)
        addr_key = normalize_address(c.address, c.city, c.state, c.zip_code)
        if addr_key:
            by_address[addr_key].append(c.id)

    pairs: list[tuple[int, int]] = []
    for bucket in (by_domain, by_phone, by_address):
        for ids in bucket.values():
            if len(ids) < 2:
                continue
            primary = min(ids)
            for other in ids:
                if other != primary:
                    pairs.append((primary, other))

    roots = _union_find([c.id for c in companies], pairs)
    groups: dict[int, list[int]] = defaultdict(list)
    for cid, root in roots.items():
        groups[root].append(cid)

    db.query(MergeCluster).delete()
    created: list[MergeCluster] = []
    today = dt.date.today().isoformat()

    for root, ids in groups.items():
        if len(ids) < 2:
            continue
        ids_sorted = sorted(ids)
        cluster = MergeCluster(
            match_keys={
                "domain": next((c.domain for c in companies if c.id in ids and c.domain), None),
                "phone": next((c.phone_e164 for c in companies if c.id in ids and c.phone_e164), None),
            },
            company_ids=ids_sorted,
            created_at=today,
        )
        db.add(cluster)
        db.flush()
        created.append(cluster)
        primary_id = ids_sorted[0]
        for c in companies:
            if c.id in ids:
                c.merge_cluster_id = cluster.id
                c.is_primary_in_cluster = c.id == primary_id

    db.commit()
    return created


def merge_cluster_members(db: Session, cluster_id: int) -> Iterable[Company]:
    return db.query(Company).filter(Company.merge_cluster_id == cluster_id).order_by(Company.id)

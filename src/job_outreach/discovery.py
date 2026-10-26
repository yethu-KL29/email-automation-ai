import asyncio
import html
import random
import re
from typing import Protocol

import httpx
from bs4 import BeautifulSoup

from job_outreach.domain import JobData, parse_date


class JobSource(Protocol):
    async def fetch(self) -> list[JobData]: ...


def plain(value: str) -> str:
    soup = BeautifulSoup(html.unescape(value), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)[:200000]


class BoardSource:
    """Only allow fixed provider hosts. Redirects are never followed."""

    def __init__(self, config: dict, client: httpx.AsyncClient):
        self.config = config
        self.client = client
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", config["board"]):
            raise ValueError("Invalid board name")

    async def get(self, url: str, **params):
        for attempt in range(3):
            try:
                async with self.client.stream(
                    "GET", url, params=params, follow_redirects=False, timeout=20
                ) as response:
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        await asyncio.sleep(2**attempt + random.random())
                        continue
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 32_000_000:
                            raise ValueError("Provider response exceeds 32 MB")
                    import json

                    return json.loads(data)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise
                await asyncio.sleep(2**attempt + random.random())
        raise ValueError("Provider retries exhausted")

    async def fetch(self) -> list[JobData]:
        source, board = self.config["source"], self.config["board"]
        if source == "ashby":
            payload = await self.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{board}", includeCompensation="true"
            )
            items = payload["jobs"]
        elif source == "greenhouse":
            payload = await self.get(
                f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", content="true"
            )
            items = payload["jobs"]
        elif source == "lever":
            items = []
            for page in range(20):
                batch = await self.get(
                    f"https://api.lever.co/v0/postings/{board}",
                    mode="json",
                    skip=page * 100,
                    limit=100,
                )
                if not isinstance(batch, list):
                    raise ValueError("Malformed Lever response")
                items.extend(batch)
                if len(batch) < 100:
                    break
                await asyncio.sleep(0.3)
            else:
                raise ValueError("Lever page cap reached; narrow board configuration")
        else:
            raise ValueError("Unsupported source")
        if not isinstance(items, list):
            raise ValueError("Malformed jobs response")
        jobs = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Malformed job item")
            if item.get("isListed") is False:
                continue
            company = self.config.get("company", board)
            common = {
                "source": source,
                "company": company,
                "company_domain": self.config.get("domain", ""),
                "raw": item,
            }
            if source == "ashby":
                url = item["jobUrl"]
                jobs.append(
                    JobData(
                        **common,
                        external_id=str(item.get("id") or url.rstrip("/").split("/")[-1]),
                        title=item["title"],
                        canonical_url=url,
                        apply_url=item["applyUrl"],
                        description=plain(
                            item.get("descriptionPlain") or item.get("descriptionHtml", "")
                        ),
                        location=item.get("location", ""),
                        remote_policy=(
                            item.get("workplaceType")
                            or ("remote" if item.get("isRemote") else "unknown")
                        ).lower(),
                        posting_date=parse_date(item.get("publishedAt")),
                        date_confidence="last_published" if item.get("publishedAt") else "unknown",
                        salary=(item.get("compensation") or {}).get("compensationTierSummary")
                        or "",
                        employment_type=item.get("employmentType", ""),
                    )
                )
            elif source == "greenhouse":
                jobs.append(
                    JobData(
                        **common,
                        external_id=str(item["id"]),
                        title=item["title"],
                        canonical_url=item["absolute_url"],
                        apply_url=item["absolute_url"],
                        description=plain(item.get("content", "")),
                        location=item.get("location", {}).get("name", ""),
                    )
                )
            else:
                jobs.append(
                    JobData(
                        **common,
                        external_id=str(item["id"]),
                        title=item["text"],
                        canonical_url=item["hostedUrl"],
                        apply_url=item["applyUrl"],
                        description=plain(
                            item.get("descriptionPlain") or item.get("description", "")
                        )
                        + " "
                        + " ".join(plain(x.get("content", "")) for x in item.get("lists", [])),
                        location=item.get("categories", {}).get("location", ""),
                        remote_policy=item.get("workplaceType", "unknown").lower(),
                        employment_type=item.get("categories", {}).get("commitment", ""),
                    )
                )
        return jobs

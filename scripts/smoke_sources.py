"""Opt-in live GET-only adapter check. No jobs saved, no email or LLM calls."""

import asyncio
import json

import httpx

from job_outreach.discovery import BoardSource


async def main():
    results = []
    async with httpx.AsyncClient(timeout=30) as client:
        for board in [
            {"source": "ashby", "board": "openai", "company": "OpenAI"},
            {"source": "greenhouse", "board": "anthropic", "company": "Anthropic"},
        ]:
            try:
                jobs = await BoardSource(board, client).fetch()
                results.append(
                    {
                        "source": board["source"],
                        "board": board["board"],
                        "retrieved": len(jobs),
                        "with_publication_date": sum(j.posting_date is not None for j in jobs),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "source": board["source"],
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:250],
                    }
                )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

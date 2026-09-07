"""
Web agent (spec section 14).

search_web uses a pluggable backend so it works out of the box without an
API key (DuckDuckGo HTML scraping, best-effort) but upgrades automatically
to Brave Search API if BRAVE_API_KEY is set — DuckDuckGo scraping is not a
stable contract and can break if their markup changes, so a real search API
key is the recommended path for production use. This is documented in
README.md.
"""

import httpx
from bs4 import BeautifulSoup

from backend.core.config import get_settings
from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult

_HEADERS = {"User-Agent": "Mozilla/5.0 (Solution AI Agent)"}


async def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient(headers=_HEADERS, timeout=15) as client:
        resp = await client.get("https://html.duckduckgo.com/html/", params={"q": query})
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for result in soup.select(".result")[:max_results]:
        link = result.select_one(".result__a")
        snippet = result.select_one(".result__snippet")
        if link:
            results.append({
                "title": link.get_text(strip=True),
                "url": link.get("href"),
                "snippet": snippet.get_text(strip=True) if snippet else "",
            })
    return results


async def _search_brave(query: str, max_results: int, api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        )
        resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description", "")}
        for r in data.get("web", {}).get("results", [])[:max_results]
    ]


class SearchWebTool(Tool):
    name = "web.search_web"
    description = "Search the web and return a list of results (title, url, snippet)."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 5}},
        "required": ["query"],
    }
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        settings = get_settings()
        brave_key = getattr(settings, "brave_api_key", "") or ""
        try:
            if brave_key:
                results = await _search_brave(query, max_results, brave_key)
            else:
                results = await _search_duckduckgo(query, max_results)
            return ToolResult(success=True, data=results)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc), error_code="SEARCH_FAILED")


class OpenUrlTool(Tool):
    name = "web.open_url"
    description = "Open a URL in the user's default browser."
    input_schema = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, url: str) -> ToolResult:
        import webbrowser
        opened = webbrowser.open(url)
        return ToolResult(success=opened, data={"url": url}, error=None if opened else "Could not open browser")


class ReadWebpageTool(Tool):
    name = "web.read_webpage"
    description = "Fetch a URL and return its visible text content (HTML stripped)."
    input_schema = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, url: str) -> ToolResult:
        try:
            async with httpx.AsyncClient(headers=_HEADERS, timeout=15, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = " ".join(soup.get_text(separator=" ").split())
            return ToolResult(success=True, data={"url": url, "text": text[:50_000]})
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc), error_code="FETCH_FAILED")


class FindOnPageTool(Tool):
    name = "web.find_on_page"
    description = "Fetch a URL and check whether a phrase appears in its text, returning surrounding context."
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}, "phrase": {"type": "string"}},
        "required": ["url", "phrase"],
    }
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, url: str, phrase: str) -> ToolResult:
        reader = ReadWebpageTool()
        page = await reader.execute(url=url)
        if not page.success:
            return page
        text = page.data["text"]
        idx = text.lower().find(phrase.lower())
        if idx == -1:
            return ToolResult(success=True, data={"found": False})
        start, end = max(0, idx - 200), min(len(text), idx + len(phrase) + 200)
        return ToolResult(success=True, data={"found": True, "context": text[start:end]})


ALL_WEB_TOOLS = [SearchWebTool(), OpenUrlTool(), ReadWebpageTool(), FindOnPageTool()]

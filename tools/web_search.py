import httpx
import asyncio
import logging
from typing import Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


async def web_search(query: str, num_results: int = 8) -> dict:
    """Search using DuckDuckGo (free, no API key)."""
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20, follow_redirects=True
        ) as client:
            encoded = quote_plus(query)
            resp = await client.get(
                f"https://html.duckduckgo.com/html/?q={encoded}&kl=us-en"
            )
            resp.raise_for_status()

            from html.parser import HTMLParser

            class DDGParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.results = []
                    self._in_result = False
                    self._in_title = False
                    self._in_snippet = False
                    self._current = {}

                def handle_starttag(self, tag, attrs):
                    attrs_d = dict(attrs)
                    cls = attrs_d.get("class", "")
                    if "result__title" in cls:
                        self._in_title = True
                        self._current = {}
                    elif "result__snippet" in cls:
                        self._in_snippet = True
                    elif tag == "a" and "result__url" in cls:
                        self._current["url"] = attrs_d.get("href", "")

                def handle_data(self, data):
                    data = data.strip()
                    if self._in_title and data:
                        self._current["title"] = data
                        self._in_title = False
                    elif self._in_snippet and data:
                        self._current["snippet"] = self._current.get("snippet", "") + data

                def handle_endtag(self, tag):
                    if self._in_snippet and tag in ("a", "span"):
                        self._in_snippet = False
                        if self._current.get("title") and self._current.get("snippet"):
                            self.results.append(dict(self._current))
                            self._current = {}

            parser = DDGParser()
            parser.feed(resp.text)
            results = parser.results[:num_results]

            if not results:
                return {"success": True, "results": [], "query": query, "note": "No results found"}

            formatted = "\n\n".join(
                f"**{i+1}. {r.get('title','?')}**\n{r.get('url','')}\n{r.get('snippet','')}"
                for i, r in enumerate(results)
            )
            return {"success": True, "results": results, "formatted": formatted, "query": query}

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return {"success": False, "error": str(e), "results": []}


async def fetch_url(url: str, max_chars: int = 12000) -> dict:
    """Fetch and extract text content from a URL."""
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=30, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "text" not in content_type and "html" not in content_type:
                return {"success": False, "content": f"Non-text content type: {content_type}"}

            from html.parser import HTMLParser

            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text_parts = []
                    self._skip = False

                def handle_starttag(self, tag, attrs):
                    if tag in ("script", "style", "nav", "footer", "header"):
                        self._skip = True

                def handle_endtag(self, tag):
                    if tag in ("script", "style", "nav", "footer", "header"):
                        self._skip = False

                def handle_data(self, data):
                    if not self._skip:
                        stripped = data.strip()
                        if stripped:
                            self.text_parts.append(stripped)

            extractor = TextExtractor()
            extractor.feed(resp.text)
            text = "\n".join(extractor.text_parts)

            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n[... content truncated ...]"

            return {"success": True, "url": url, "content": text, "chars": len(text)}

    except Exception as e:
        return {"success": False, "url": url, "error": str(e)}


async def search_github(query: str, search_type: str = "repositories", limit: int = 5) -> dict:
    """Search GitHub for repos or code snippets."""
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            params = {"q": query, "per_page": limit, "sort": "stars"}
            url = f"https://api.github.com/search/{search_type}"
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            results = []
            for item in items:
                if search_type == "repositories":
                    results.append({
                        "name": item["full_name"],
                        "url": item["html_url"],
                        "description": item.get("description", ""),
                        "stars": item.get("stargazers_count", 0),
                        "language": item.get("language", ""),
                    })
                else:
                    results.append({
                        "path": item.get("path", ""),
                        "url": item.get("html_url", ""),
                        "repo": item.get("repository", {}).get("full_name", ""),
                    })
            return {"success": True, "results": results}
    except Exception as e:
        return {"success": False, "error": str(e), "results": []}

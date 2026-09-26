"""Web search results and cloud routing stay available to every model."""
import io
import json
import unittest
from unittest.mock import patch

from app import server


class WebSearchTests(unittest.TestCase):
    def test_general_web_results_are_parsed_and_filtered(self):
        feed = b"""<?xml version="1.0"?><rss><channel>
            <item><title>Example &amp; Guide</title><link>https://example.com/guide</link>
            <description>Useful &lt;b&gt;current&lt;/b&gt; details</description></item>
            <item><title>Unsafe</title><link>file:///secret</link></item>
            </channel></rss>"""
        with patch.object(server.urllib.request, "urlopen", return_value=io.BytesIO(feed)):
            results = server.search_bing_rss("example", max_results=2)
        self.assertEqual(results, [{"title": "Example & Guide", "url": "https://example.com/guide",
                                    "snippet": "Useful current details"}])

    def test_fallback_search_when_general_feed_is_unavailable(self):
        source = {"title": "Reference", "url": "https://example.com", "snippet": "Info"}
        with patch.object(server, "search_bing_rss", return_value=[]), \
             patch.object(server, "search_wikipedia", return_value=[source]), \
             patch.object(server, "search_news", return_value=[source]), \
             patch.object(server, "search_ddg_instant", return_value=[]):
            self.assertEqual(server.perform_combined_search("example"), [source])

    def test_recent_queries_prioritize_news(self):
        news = {"title": "Latest update", "url": "https://news.example.com", "snippet": "Today"}
        generic = {"title": "Homepage", "url": "https://example.com", "snippet": "General"}
        with patch.object(server, "search_bing_rss", return_value=[generic]), \
             patch.object(server, "search_wikipedia", return_value=[]), \
             patch.object(server, "search_news", return_value=[news]), \
             patch.object(server, "search_ddg_instant", return_value=[]):
            self.assertEqual(server.perform_combined_search("latest model news"), [news, generic])

    def test_both_cloud_providers_receive_web_context(self):
        messages = [{"role": "system", "content": "[Live Web Search Results] [Source 1]"},
                    {"role": "user", "content": "What happened?"}]
        captured = []

        class Handler:
            def stream_request(self, request, opener, stream=True):
                captured.append(request)

        settings = {"nvidia_api_key": "nkey", "openrouter_api_key": "okey"}
        with patch.object(server, "load_host_settings", return_value=settings), \
             patch.object(server.urllib.request, "build_opener", return_value=object()):
            for path, model in (("/api/nvidia/chat", "nvidia/nemotron-3-ultra-550b-a55b"),
                                ("/api/openrouter/chat", "inclusionai/ling-3.0-flash-fin:free")):
                server.LocalAIHandler.proxy_cloud(Handler(), path, {"model": model, "messages": messages})

        self.assertEqual(len(captured), 2)
        for request in captured:
            self.assertEqual(json.loads(request.data)["messages"], messages)
        self.assertIn("integrate.api.nvidia.com", captured[0].full_url)
        self.assertIn("openrouter.ai", captured[1].full_url)

    def test_local_model_receives_web_context(self):
        captured = []

        class Handler:
            def stream_request(self, request, opener, stream=True):
                captured.append(request)

        messages = [{"role": "system", "content": "[Live Web Search Results]"}]
        with patch.object(server, "OLLAMA_TARGET", "http://127.0.0.1:11434"):
            server.LocalAIHandler.proxy_local(Handler(), "POST", "/api/chat",
                                              {"model": "qwen2.5:3b", "messages": messages})
        self.assertEqual(json.loads(captured[0].data)["messages"], messages)


if __name__ == "__main__":
    unittest.main()

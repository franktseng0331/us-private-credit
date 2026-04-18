"""
LLM 行业分类器
使用 Claude claude-haiku-4-5 批量对借款人公司名称进行 GICS 行业分类

特性:
- 本地 JSON 缓存，避免重复 API 调用
- 批量处理（50 names/call）控制 API 成本
- 健壮的 JSON 解析（处理 LLM 输出格式不规范）
- 支持断点续传（已缓存的跳过）

使用方式:
    from llm_industry_classifier import LLMIndustryClassifier
    classifier = LLMIndustryClassifier()
    result = classifier.classify_batch(["Company A", "Company B"])
    # {"Company A": "Industrials", "Company B": "Health Care"}
"""

import json
import os
import re
import time
from pathlib import Path

try:
    import anthropic
except ImportError:
    raise ImportError("请先安装 anthropic: pip install anthropic>=0.20.0")


GICS_SECTORS = [
    "Information Technology",
    "Health Care",
    "Financials",
    "Consumer Discretionary",
    "Industrials",
    "Communication Services",
    "Consumer Staples",
    "Energy",
    "Materials",
    "Real Estate",
    "Utilities",
    "Other",
]

# 用于 LLM 回答验证的集合
_VALID_SECTORS = set(GICS_SECTORS)

SYSTEM_PROMPT = (
    "You are a financial industry analyst specializing in GICS sector classification. "
    "Classify company names into GICS sectors based on their names and common knowledge of their business. "
    "Respond ONLY with a valid JSON array — no commentary, no markdown fences."
)


class LLMIndustryClassifier:
    """批量 LLM 行业分类器，带本地缓存"""

    def __init__(
        self,
        model: str = None,
        cache_path: str = "data/llm_cache/industry_cache.json",
        batch_size: int = 50,
        sleep_between_batches: float = 0.5,
    ):
        # Support both Anthropic and OpenAI-compatible APIs (e.g. DeepSeek)
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
        anthropic_key = (os.environ.get("ANTHROPIC_AUTH_TOKEN")
                         or os.environ.get("ANTHROPIC_API_KEY")
                         or "")

        if deepseek_key:
            self._api_key = deepseek_key
            self._base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
            self._api_style = "openai"
            self.model = model or "deepseek-chat"
        else:
            self._api_key = anthropic_key
            self._base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
            self._api_style = "anthropic"
            self.model = model or "claude-haiku-4-5"
        self.batch_size = batch_size
        self.sleep_between_batches = sleep_between_batches
        self.cache_path = Path(cache_path)
        self.cache = self._load_cache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_batch(self, names: list) -> dict:
        """
        对公司名称列表进行 GICS 行业分类（带缓存）。

        Args:
            names: 公司名称列表（去重后传入效率更高）

        Returns:
            {company_name: gics_sector} 映射，未能分类的返回 "Other"
        """
        to_classify = [n for n in names if n and n not in self.cache]

        if to_classify:
            print(f"  LLM 分类: {len(to_classify):,} 个新借款人（缓存命中: {len(names) - len(to_classify):,}）")
            self._classify_in_batches(to_classify)
            self._save_cache()
        else:
            print(f"  LLM 分类: 100% 缓存命中（{len(names):,} 个借款人，0 次 API 调用）")

        return {n: self.cache.get(n, "Other") for n in names if n}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify_in_batches(self, names: list) -> None:
        total_batches = (len(names) + self.batch_size - 1) // self.batch_size
        for i in range(0, len(names), self.batch_size):
            batch = names[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            print(f"    Batch {batch_num}/{total_batches} ({len(batch)} names)...", end=" ", flush=True)
            result = self._call_api(batch)
            hits = len(result)
            self.cache.update(result)
            # Fill any names not returned by LLM with "Other"
            for name in batch:
                if name not in self.cache:
                    self.cache[name] = "Other"
            print(f"✓ {hits}/{len(batch)} classified")
            if i + self.batch_size < len(names):
                time.sleep(self.sleep_between_batches)

    def _call_api(self, names: list, max_retries: int = 5) -> dict:
        """Call Claude API with a batch of names; returns {name: sector} dict.
        Retries up to max_retries times with exponential backoff on transient errors."""
        user_prompt = (
            f"Classify each of the following company names into exactly one GICS sector.\n"
            f"Valid sectors: {json.dumps(GICS_SECTORS)}\n\n"
            f"Company names:\n{json.dumps(names)}\n\n"
            f'Respond ONLY with a JSON array of objects: [{{"name":"...","sector":"..."}}]'
        )

        for attempt in range(max_retries):
            try:
                import httpx
                if self._api_style == "openai":
                    headers = {
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "model": self.model,
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                    }
                    resp = httpx.post(
                        f"{self._base_url}/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=60,
                    )
                    resp.raise_for_status()
                    raw_text = resp.json()["choices"][0]["message"]["content"].strip()
                else:
                    headers = {
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    }
                    payload = {
                        "model": self.model,
                        "max_tokens": 2048,
                        "system": SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": user_prompt}],
                    }
                    resp = httpx.post(
                        f"{self._base_url}/v1/messages",
                        headers=headers,
                        json=payload,
                        timeout=60,
                    )
                    resp.raise_for_status()
                    raw_text = resp.json()["content"][0]["text"].strip()
                return self._parse_response(raw_text, names)
            except Exception as e:
                err_str = str(e)
                # Transient errors: 502, 529, overload, rate limit → retry
                is_transient = any(code in err_str for code in ['502', '529', '529', 'overload', 'rate_limit', 'timeout'])
                if is_transient and attempt < max_retries - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
                    print(f"\n    API 临时错误 (attempt {attempt+1}/{max_retries}), 等待 {wait}s: {e}")
                    time.sleep(wait)
                else:
                    print(f"\n    API 错误: {e}")
                    return {}
        return {}

    def _parse_response(self, raw_text: str, names: list) -> dict:
        """
        Robustly parse LLM JSON response.
        Handles: bare array, markdown fences, truncated output, invalid sectors.
        """
        # Strip markdown fences if present
        text = re.sub(r"```(?:json)?", "", raw_text).strip()

        # Extract the JSON array (find first '[' ... last ']')
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return {}

        json_str = text[start : end + 1]

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            # Attempt to recover truncated JSON by dropping the last incomplete object
            last_comma = json_str.rfind(",")
            if last_comma != -1:
                json_str = json_str[:last_comma] + "]"
                try:
                    parsed = json.loads(json_str)
                except json.JSONDecodeError:
                    return {}
            else:
                return {}

        result = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip()
            sector = item.get("sector", "Other").strip()
            # Validate sector against allowed list; default to "Other"
            if sector not in _VALID_SECTORS:
                sector = "Other"
            if name:
                result[name] = sector

        return result

    def _load_cache(self) -> dict:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_cache(self) -> None:
        self.cache_path.write_text(
            json.dumps(self.cache, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  缓存已保存: {len(self.cache):,} 条 → {self.cache_path}")

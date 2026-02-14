# -*- coding: utf-8 -*-
"""代理 URL 批量测试引擎 — 基于 aiohttp 异步并发

支持:
    - 直连（无代理）
    - HTTP 代理
    - SOCKS5 代理
"""

import asyncio
import time
import ssl as _ssl

import aiohttp
from aiohttp_socks import ProxyConnector


def build_proxy_url(proxy_type, host, port, username='', password=''):
    """根据 UI 参数拼装代理 URL。

    返回 None 表示直连，返回字符串用于 ProxyConnector.from_url()。
    """
    if not proxy_type or proxy_type == '无代理':
        return None
    scheme = {
        'HTTP':   'http',
        'HTTPS':  'http',
        'SOCKS5': 'socks5',
        'SOCKS4': 'socks4',
    }.get(proxy_type, 'http')

    host = host.strip()
    if not host:
        raise ValueError("代理地址不能为空")

    auth = ''
    if username:
        auth = f"{username}:{password}@" if password else f"{username}@"

    return f"{scheme}://{auth}{host}:{port}"


async def test_single_url(session, url, timeout):
    """测试单个 URL，返回结果字典。"""
    start = time.monotonic()
    try:
        # 禁用 SSL 校验，只关心连通性
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE

        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            ssl=ssl_ctx,
            allow_redirects=True,
        ) as resp:
            elapsed = time.monotonic() - start
            # 只读少量内容获取大小信息
            body = await resp.read()
            content_len = len(body)
            content_type = resp.headers.get('Content-Type', '')
            server = resp.headers.get('Server', '')
            return {
                'url': url,
                'status': resp.status,
                'reason': resp.reason or '',
                'time_ms': round(elapsed * 1000),
                'size': content_len,
                'content_type': content_type,
                'server': server,
                'error': '',
                'ok': True,
            }
    except asyncio.CancelledError:
        raise
    except aiohttp.ClientConnectorError as e:
        elapsed = time.monotonic() - start
        return _err(url, elapsed, f"连接失败: {e}")
    except aiohttp.ClientProxyConnectionError as e:
        elapsed = time.monotonic() - start
        return _err(url, elapsed, f"代理连接失败: {e}")
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        return _err(url, elapsed, "超时")
    except Exception as e:
        elapsed = time.monotonic() - start
        return _err(url, elapsed, f"{type(e).__name__}: {e}")


async def batch_test(urls, proxy_url=None, timeout=10,
                     concurrency=10, stop_event=None,
                     on_result=None, on_progress=None):
    """批量测试 URL。

    Args:
        urls:        URL 列表
        proxy_url:   代理 URL (None = 直连)
        timeout:     单个请求超时(秒)
        concurrency: 并发数
        stop_event:  asyncio.Event, set 时停止
        on_result:   回调 fn(result_dict)
        on_progress: 回调 fn(done, total)
    """
    connector = None
    if proxy_url:
        connector = ProxyConnector.from_url(proxy_url)

    sem = asyncio.Semaphore(concurrency)
    done_count = 0
    total = len(urls)
    results = []

    async def _test_one(url):
        nonlocal done_count
        if stop_event and stop_event.is_set():
            return
        async with sem:
            if stop_event and stop_event.is_set():
                return
            result = await test_single_url(session, url, timeout)
            done_count += 1
            results.append(result)
            if on_result:
                on_result(result)
            if on_progress:
                on_progress(done_count, total)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [asyncio.create_task(_test_one(u)) for u in urls]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results


def _err(url, elapsed, msg):
    return {
        'url': url,
        'status': 0,
        'reason': '',
        'time_ms': round(elapsed * 1000),
        'size': 0,
        'content_type': '',
        'server': '',
        'error': msg,
        'ok': False,
    }

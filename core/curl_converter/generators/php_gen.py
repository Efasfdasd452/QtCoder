# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest


class PHPCurlGenerator(BaseGenerator):
    name = "PHP (cURL)"
    language = "php"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method
        lines = ["<?php", "$ch = curl_init();", ""]
        lines.append(f'curl_setopt($ch, CURLOPT_URL, "{req.url}");')
        lines.append("curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);")

        if method == "POST":
            lines.append("curl_setopt($ch, CURLOPT_POST, true);")
        elif method not in ("GET", "POST"):
            lines.append(f'curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "{method}");')

        if req.data:
            lines.append(f"curl_setopt($ch, CURLOPT_POSTFIELDS, '{self._escape(req.data, chr(39))}');")

        if req.headers:
            lines.append("curl_setopt($ch, CURLOPT_HTTPHEADER, [")
            for k, v in req.headers.items():
                lines.append(f'    "{k}: {self._escape(v)}",')
            lines.append("]);")

        if req.auth:
            lines.append(f'curl_setopt($ch, CURLOPT_USERPWD, "{req.auth[0]}:{self._escape(req.auth[1])}");')

        if req.cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in req.cookies.items())
            lines.append(f'curl_setopt($ch, CURLOPT_COOKIE, "{cookie_str}");')

        if req.follow_redirects:
            lines.append("curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);")

        if not req.verify_ssl:
            lines.append("curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);")
            lines.append("curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 0);")

        if req.proxy:
            lines.append(f'curl_setopt($ch, CURLOPT_PROXY, "{req.proxy}");')

        if req.timeout is not None:
            lines.append(f"curl_setopt($ch, CURLOPT_TIMEOUT, {int(req.timeout)});")

        lines.append("")
        lines.append("$response = curl_exec($ch);")
        lines.append("curl_close($ch);")
        lines.append("echo $response;")
        return "\n".join(lines)

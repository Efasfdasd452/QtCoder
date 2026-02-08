# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest


class RubyGenerator(BaseGenerator):
    name = "Ruby (net/http)"
    language = "ruby"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method.capitalize()
        lines = [
            "require 'net/http'",
            "require 'uri'",
            "require 'json'",
            "",
            f'uri = URI.parse("{req.url}")',
            "http = Net::HTTP.new(uri.host, uri.port)",
        ]

        lines.append('http.use_ssl = true if uri.scheme == "https"')

        if not req.verify_ssl:
            lines.append("http.verify_mode = OpenSSL::SSL::VERIFY_NONE")

        lines.append("")
        lines.append(f"request = Net::HTTP::{method}.new(uri.request_uri)")

        for k, v in req.headers.items():
            lines.append(f'request["{k}"] = "{self._escape(v)}"')

        if req.auth:
            lines.append(f'request.basic_auth("{req.auth[0]}", "{self._escape(req.auth[1])}")')

        if req.cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in req.cookies.items())
            lines.append(f'request["Cookie"] = "{cookie_str}"')

        if req.data:
            lines.append(f"request.body = '{self._escape(req.data, chr(39))}'")

        lines.append("")
        lines.append("response = http.request(request)")
        lines.append('puts "Status: #{response.code}"')
        lines.append("puts response.body")
        return "\n".join(lines)

# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest
import json


class JavaScriptFetchGenerator(BaseGenerator):
    name = "JavaScript (fetch)"
    language = "javascript"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method
        opts = {}

        if method != "GET":
            opts["method"] = method

        if req.headers:
            opts["headers"] = req.headers

        if req.json_data is not None:
            body_str = f"JSON.stringify({json.dumps(req.json_data, ensure_ascii=False)})"
        elif req.data:
            body_str = json.dumps(req.data)
        else:
            body_str = None

        lines = []
        lines.append(f'fetch("{req.url}", {{')

        if "method" in opts:
            lines.append(f'  method: "{method}",')

        if req.headers:
            lines.append("  headers: {")
            for k, v in req.headers.items():
                lines.append(f'    "{k}": "{self._escape(v)}",')
            lines.append("  },")

        if req.auth:
            btoa = f'btoa("{req.auth[0]}:{req.auth[1]}")'
            lines.append(f'  headers: {{ ...headers, "Authorization": "Basic " + {btoa} }},')

        if body_str:
            if req.json_data is not None:
                lines.append(f"  body: JSON.stringify({json.dumps(req.json_data, indent=2, ensure_ascii=False)}),")
            else:
                lines.append(f"  body: {json.dumps(req.data)},")

        if req.cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in req.cookies.items())
            lines.append(f'  credentials: "include",')

        if not req.follow_redirects:
            lines.append('  redirect: "manual",')

        lines.append("})")
        lines.append(".then(response => response.text())")
        lines.append(".then(data => console.log(data))")
        lines.append(".catch(error => console.error(error));")
        return "\n".join(lines)

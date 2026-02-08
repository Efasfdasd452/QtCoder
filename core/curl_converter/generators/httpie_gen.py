# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest
import json


class HTTPieGenerator(BaseGenerator):
    name = "HTTPie"
    language = "bash"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method
        parts = ["http"]

        if method != "GET":
            parts.append(method)

        parts.append(f'"{req.url}"')

        for k, v in req.headers.items():
            parts.append(f'  "{k}:{v}"')

        if req.auth:
            parts.append(f'  --auth "{req.auth[0]}:{req.auth[1]}"')

        if req.json_data is not None:
            if isinstance(req.json_data, dict):
                for k, v in req.json_data.items():
                    if isinstance(v, str):
                        parts.append(f'  {k}="{v}"')
                    else:
                        parts.append(f"  {k}:={json.dumps(v)}")
            else:
                parts.append(f"  --raw '{json.dumps(req.json_data)}'")
        elif req.data:
            if req.data_type == 'form':
                for pair in req.data.split('&'):
                    if '=' in pair:
                        parts.append(f"  {pair}")
            else:
                parts.append(f"  --raw '{req.data}'")

        if not req.verify_ssl:
            parts.append("  --verify=no")

        if req.proxy:
            parts.append(f'  --proxy=http:"{req.proxy}"')

        if req.timeout is not None:
            parts.append(f"  --timeout={req.timeout}")

        if req.follow_redirects:
            parts.append("  --follow")

        if req.output_file:
            parts.append(f'  --output "{req.output_file}"')

        return " \\\n".join(parts)

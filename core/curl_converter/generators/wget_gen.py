# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest


class WgetGenerator(BaseGenerator):
    name = "Wget"
    language = "bash"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method
        parts = ["wget"]

        if method != "GET":
            parts.append(f"  --method={method}")

        for k, v in req.headers.items():
            parts.append(f'  --header="{k}: {v}"')

        if req.auth:
            parts.append(f'  --user="{req.auth[0]}"')
            parts.append(f'  --password="{req.auth[1]}"')

        if req.data:
            parts.append(f"  --body-data='{req.data}'")

        if not req.verify_ssl:
            parts.append("  --no-check-certificate")

        if req.proxy:
            parts.append(f'  -e use_proxy=yes -e http_proxy="{req.proxy}"')

        if req.timeout is not None:
            parts.append(f"  --timeout={int(req.timeout)}")

        if req.output_file:
            parts.append(f'  -O "{req.output_file}"')
        else:
            parts.append("  -O -")

        parts.append(f'  "{req.url}"')
        return " \\\n".join(parts)

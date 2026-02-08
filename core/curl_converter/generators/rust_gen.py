# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest


class RustGenerator(BaseGenerator):
    name = "Rust (reqwest)"
    language = "rust"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method.lower()
        lines = [
            "// Cargo.toml dependencies:",
            '// reqwest = { version = "0.11", features = ["blocking"] }',
            "",
            "use reqwest;",
            "",
            "fn main() -> Result<(), Box<dyn std::error::Error>> {",
        ]

        if not req.verify_ssl:
            lines.append("    let client = reqwest::blocking::Client::builder()")
            lines.append("        .danger_accept_invalid_certs(true)")
            lines.append("        .build()?;")
        else:
            lines.append("    let client = reqwest::blocking::Client::new();")

        lines.append(f'    let response = client.{method}("{req.url}")')

        for k, v in req.headers.items():
            lines.append(f'        .header("{k}", "{self._escape(v)}")')

        if req.auth:
            lines.append(f'        .basic_auth("{req.auth[0]}", Some("{self._escape(req.auth[1])}"))')

        if req.data:
            lines.append(f'        .body(r#"{req.data}"#)')

        if req.timeout is not None:
            lines.append(f"        .timeout(std::time::Duration::from_secs({int(req.timeout)}))")

        lines.append("        .send()?;")
        lines.append("")
        lines.append('    println!("Status: {}", response.status());')
        lines.append("    println!(\"{}\", response.text()?);")
        lines.append("    Ok(())")
        lines.append("}")
        return "\n".join(lines)

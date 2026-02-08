# -*- coding: utf-8 -*-
from .base import BaseGenerator, ParsedRequest


class JavaGenerator(BaseGenerator):
    name = "Java (HttpURLConnection)"
    language = "java"

    def generate(self, req: ParsedRequest) -> str:
        method = req.effective_method
        lines = [
            "import java.net.HttpURLConnection;",
            "import java.net.URL;",
            "import java.io.*;",
            "",
            "public class Main {",
            "    public static void main(String[] args) throws Exception {",
            f'        URL url = new URL("{req.url}");',
            "        HttpURLConnection conn = (HttpURLConnection) url.openConnection();",
            f'        conn.setRequestMethod("{method}");',
        ]

        for k, v in req.headers.items():
            lines.append(f'        conn.setRequestProperty("{k}", "{self._escape(v)}");')

        if req.auth:
            lines.append(f'        String auth = java.util.Base64.getEncoder().encodeToString("{req.auth[0]}:{req.auth[1]}".getBytes());')
            lines.append('        conn.setRequestProperty("Authorization", "Basic " + auth);')

        if req.cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in req.cookies.items())
            lines.append(f'        conn.setRequestProperty("Cookie", "{cookie_str}");')

        if req.follow_redirects:
            lines.append("        conn.setInstanceFollowRedirects(true);")

        if req.timeout is not None:
            ms = int(req.timeout * 1000)
            lines.append(f"        conn.setConnectTimeout({ms});")
            lines.append(f"        conn.setReadTimeout({ms});")

        if req.data:
            lines.append("        conn.setDoOutput(true);")
            lines.append("        try (OutputStream os = conn.getOutputStream()) {")
            lines.append(f'            os.write("{self._escape(req.data)}".getBytes("UTF-8"));')
            lines.append("        }")

        lines.append("")
        lines.append("        int code = conn.getResponseCode();")
        lines.append('        System.out.println("Status: " + code);')
        lines.append("        try (BufferedReader br = new BufferedReader(")
        lines.append("                new InputStreamReader(conn.getInputStream()))) {")
        lines.append("            String line;")
        lines.append("            while ((line = br.readLine()) != null) {")
        lines.append("                System.out.println(line);")
        lines.append("            }")
        lines.append("        }")
        lines.append("    }")
        lines.append("}")
        return "\n".join(lines)

#!/usr/bin/env python3
"""把符合要求的 issue 合并进 sites.json。

支持两种 issue 内容：
1) 软件「分享到公共站点库」生成的 ```json 代码块
2) GitHub Issue 表单生成的「### 站点名称 / ### 站点地址 / ### 站点类型」markdown

校验：地址必须是 http(s)、host 合法、只取白名单字段（绝不写入账号密码）。
去重：按域名归一化（去协议、去 www、去尾斜杠、小写）。
"""
import json
import os
import re
import sys
from urllib.parse import urlparse

ALLOWED = {"name", "baseUrl", "kind", "rechargeRate", "note"}


def normalize(url: str) -> str:
    s = (url or "").strip().rstrip("/").lower()
    for prefix in ("https://", "http://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s[4:] if s.startswith("www.") else s


def from_json_block(body: str):
    m = re.search(r"```json\s*(.*?)```", body, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except Exception:
        return None
    if isinstance(data, dict) and isinstance(data.get("site"), dict):
        data = data["site"]
    return data if isinstance(data, dict) else None


def from_form(body: str):
    def field(*names):
        for name in names:
            # 表单标题可能带括号说明，例如「### 充值比例（1 元买多少美元额度）」
            m = re.search(r"###\s*" + name + r"[^\n]*\n+\s*(.+)", body)
            if m:
                value = m.group(1).strip()
                if value and not value.startswith("_No response_"):
                    return value
        return None

    url = field("站点地址", "地址", "Site URL", "URL")
    if not url:
        return None
    rate = field("充值比例", "Recharge rate")
    try:
        rate_value = float(rate) if rate else 1
    except ValueError:
        rate_value = 1
    return {
        "name": field("站点名称", "名称", "Site name") or "",
        "baseUrl": url,
        "kind": (field("站点类型", "类型", "Site kind") or "NewApi").split()[0],
        "rechargeRate": rate_value,
        "note": field("备注", "Note") or "",
    }


def main() -> int:
    body = os.environ.get("ISSUE_BODY", "")
    data = from_json_block(body) or from_form(body)
    if not data:
        print("::error::没有从 issue 里解析到站点信息")
        return 1

    url = str(data.get("baseUrl") or data.get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.hostname or "." not in parsed.hostname:
        print("::error::站点地址不合法")
        return 1

    site = {k: data[k] for k in data if k in ALLOWED}
    site["baseUrl"] = url.rstrip("/")
    site["name"] = (site.get("name") or parsed.hostname)[:60]

    with open("sites.json", encoding="utf-8") as fh:
        payload = json.load(fh)
    items = payload.setdefault("sites", [])

    key = normalize(site["baseUrl"])
    if any(normalize(i.get("baseUrl", "")) == key for i in items):
        print("::notice::站点已存在，跳过")
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write("added=0\nreason=duplicate\n")
        return 0

    items.append(site)
    payload["updatedAt"] = __import__("datetime").date.today().isoformat()
    with open("sites.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write("added=1\nreason=ok\n")
    print(f"added {site['baseUrl']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

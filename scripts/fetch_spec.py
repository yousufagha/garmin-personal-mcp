"""Re-extract Garmin's official Personal API OpenAPI spec into docs/openapi.json.

The spec is embedded in the JS bundle of
https://developer.garmin.com/gc-developer-program/personal/swagger-docs/ .
It is Garmin's content, so it is fetched locally rather than committed.
"""

import ast
import json
import re
import urllib.request
from pathlib import Path

PAGE = "https://developer.garmin.com/gc-developer-program/personal/swagger-docs/"
OUT = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")


def main() -> None:
    html = get(PAGE)
    bundle = re.search(r'src="(/component---src-pages-gc-developer-program-personal-swagger-docs-js-[^"]+\.js)"', html)
    if not bundle:
        raise SystemExit("Spec bundle not found; the docs page layout has changed.")
    js = get("https://developer.garmin.com" + bundle.group(1))
    i = js.index("JSON.parse('{\"openapi\"") + len("JSON.parse(")
    j = i + 1
    while js[j] != "'":
        j += 2 if js[j] == "\\" else 1
    spec = json.loads(ast.literal_eval(js[i : j + 1]))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(spec, indent=1))
    print(f"{spec['info']['title']} {spec['info']['version']}: {len(spec['paths'])} paths -> {OUT}")


if __name__ == "__main__":
    main()

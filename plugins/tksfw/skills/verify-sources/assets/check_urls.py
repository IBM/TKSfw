#!/usr/bin/env python3
"""URL liveness check for source verification (the mechanical part of "confirm by looking it up").

Reports HTTP status, final URL (after redirects), and whether the host changed — flags dead links
and cross-host redirects that warrant a closer look. It does NOT judge recency/relevance/reputation
or whether the cited figure is present — do those with WebFetch + judgment (see the SKILL).

Usage:  python3 check_urls.py <url> [url ...]
        python3 check_urls.py --file urls.txt        # one URL per line ('#' comments ignored)
Std lib only; network access required.
"""
import sys, urllib.request, urllib.error
from urllib.parse import urlparse

UA = "Mozilla/5.0 (compatible; source-verify/1.0)"

def check(url, timeout=25):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final = r.geturl()
            same = urlparse(url).netloc.lower().lstrip("www.") == urlparse(final).netloc.lower().lstrip("www.")
            flag = "" if same else "  [redirected off-host]"
            return f"{r.status}  {url}{'' if final==url else '  -> '+final}{flag}"
    except urllib.error.HTTPError as e:
        return f"{e.code}  {url}  [HTTP error]"
    except Exception as e:
        return f"ERR  {url}  [{type(e).__name__}: {e}]"

def main():
    args = sys.argv[1:]
    if args and args[0] == "--file":
        urls = [l.strip() for l in open(args[1]) if l.strip() and not l.lstrip().startswith("#")]
    else:
        urls = args
    if not urls:
        raise SystemExit("give one or more URLs, or --file <path>")
    ok = 0
    for u in urls:
        line = check(u)
        print(line)
        if line[:1] == "2":
            ok += 1
    print(f"\n{ok}/{len(urls)} reachable (2xx). Non-2xx / off-host redirects need manual review.")
    sys.exit(0 if ok == len(urls) else 1)

if __name__ == "__main__":
    main()

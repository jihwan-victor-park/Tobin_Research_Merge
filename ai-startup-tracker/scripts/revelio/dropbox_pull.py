"""
Reliable Dropbox downloader for the Revelio shared link.

Streams a file from the professor's shared folder to data/revelio_raw/ with
chunked writes, resume-on-failure (HTTP Range against the .part file), and
progress. Used both interactively and by the streaming extraction loop.

    python scripts/revelio/dropbox_pull.py --list
    python scripts/revelio/dropbox_pull.py revelio_company_mapping-000000.parquet
    python scripts/revelio/dropbox_pull.py revelio_individual_positions-000005.parquet

Token + shared link are read from the git-ignored files under data/revelio_raw/.
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RAW = os.path.join(ROOT, "data", "revelio_raw")
SUBFOLDER = "/linkedin_v20260612"
CONTENT_API = "https://content.dropboxapi.com/2/sharing/get_shared_link_file"

_tok = None
_url = None


def _creds():
    global _tok, _url
    if _tok is None:
        _tok = open(os.path.join(RAW, ".dropbox_token")).read().strip()
        _url = open(os.path.join(RAW, "dropbox_share_link.txt")).read().strip()
    return _tok, _url


def list_files(subfolder: str = SUBFOLDER):
    import dropbox
    from dropbox.files import SharedLink
    tok, url = _creds()
    dbx = dropbox.Dropbox(tok)
    link = SharedLink(url=url)
    out, res = [], dbx.files_list_folder(path=subfolder, shared_link=link)
    out += res.entries
    while res.has_more:
        res = dbx.files_list_folder_continue(res.cursor)
        out += res.entries
    return out


def pull(name: str, subfolder: str = SUBFOLDER, dest: str = RAW,
         retries: int = 6) -> str:
    """Download one file with resume. Returns the final path."""
    tok, url = _creds()
    out = os.path.join(dest, name)
    tmp = out + ".part"
    if os.path.exists(out):
        print(f"✓ {name} already present")
        return out

    for attempt in range(1, retries + 1):
        start = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        headers = {
            "Authorization": f"Bearer {tok}",
            "Dropbox-API-Arg": json.dumps({"url": url, "path": f"{subfolder}/{name}"}),
        }
        if start:
            headers["Range"] = f"bytes={start}-"
        try:
            with requests.post(CONTENT_API, headers=headers, stream=True,
                               timeout=(30, 300)) as r:
                if start and r.status_code == 200:
                    # server ignored Range — restart clean
                    start = 0
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0)) + start
                with open(tmp, "ab" if start else "wb") as f:
                    done, t0, last = start, time.time(), time.time()
                    for chunk in r.iter_content(4 * 1024 * 1024):
                        f.write(chunk)
                        done += len(chunk)
                        if time.time() - last > 5:
                            spd = (done - start) / (time.time() - t0) / 1e6
                            pct = f"{done/total*100:.0f}%" if total else "?"
                            print(f"  {name}: {done/1e9:.2f}/{total/1e9:.2f} GB "
                                  f"({pct}, {spd:.1f} MB/s)", flush=True)
                            last = time.time()
            os.rename(tmp, out)
            print(f"✓ {name} -> {out} ({os.path.getsize(out)/1e9:.2f} GB)")
            return out
        except (requests.RequestException, OSError) as e:
            wait = min(30, 2 ** attempt)
            got = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            print(f"  ! {name} attempt {attempt}/{retries} failed at "
                  f"{got/1e9:.2f} GB ({type(e).__name__}); retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed to download {name} after {retries} attempts")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "--list":
        sf = args[1] if len(args) > 1 else SUBFOLDER
        from dropbox.files import FileMetadata
        for e in sorted(list_files(sf), key=lambda x: x.name):
            sz = f"{e.size/1e9:.2f}GB" if isinstance(e, FileMetadata) else "DIR"
            print(f"  {e.name}  {sz}")
    else:
        for name in args:
            pull(name)

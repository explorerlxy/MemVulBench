"""Pull PoCs and reference binaries out of ARVO images without docker.

An ``n132/arvo:<id>-vul`` image is ~1.9 GB, but everything we need sits in the
one layer ARVO commits after running the crash: ``tmp/poc`` and the prebuilt
ASan harness under ``out/``. Fetching that single blob through the registry API
costs ~17 MB instead of the whole image, needs no docker daemon, and works the
same on a machine that cannot spare 50 GB of overlay.

The image config carries a second free gift: its build history contains the
``git reset --hard <sha>`` that pinned the vulnerable commit. ARVO-Meta only
records the fix commit, so this is the other end of the window.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REGISTRY = "https://registry-1.docker.io/v2"
AUTH = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
MANIFEST_ACCEPT = (
    "application/vnd.docker.distribution.manifest.v2+json,"
    "application/vnd.oci.image.manifest.v1+json"
)
_PIN_RE = re.compile(r"git (?:reset --hard|checkout(?: -f)?) ([0-9a-f]{7,40})")


class FetchError(RuntimeError):
    pass


def _get(url: str, headers: dict[str, str], raw: bool = False, timeout: int = 300):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as f:
        data = f.read()
    return data if raw else json.loads(data)


@dataclass
class Image:
    repo: str
    tag: str
    token: str
    manifest: dict
    config: dict

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def layers(self) -> list[dict]:
        return self.manifest["layers"]

    @property
    def total_size(self) -> int:
        return sum(l["size"] for l in self.layers)

    def vuln_commit(self) -> str | None:
        """The commit the image was pinned to, from its build history."""
        for entry in reversed(self.config.get("history", [])):
            if m := _PIN_RE.search(entry.get("created_by", "")):
                return m.group(1)
        return None

    def blob(self, layer: dict) -> tarfile.TarFile:
        raw = _get(f"{REGISTRY}/{self.repo}/blobs/{layer['digest']}", self.auth, raw=True)
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
        return tarfile.open(fileobj=io.BytesIO(raw))


def open_image(repo: str, tag: str) -> Image:
    token = _get(AUTH.format(repo=repo), {})["token"]
    auth = {"Authorization": f"Bearer {token}"}
    manifest = _get(f"{REGISTRY}/{repo}/manifests/{tag}",
                    auth | {"Accept": MANIFEST_ACCEPT})
    config = _get(f"{REGISTRY}/{repo}/blobs/{manifest['config']['digest']}", auth)
    return Image(repo, tag, token, manifest, config)


def extract(oss_id: int, dest: Path, want_binary: bool = False,
            scan_layers: int = 6, max_bytes: int = 300_000_000) -> dict:
    """Fetch ``tmp/poc`` (and optionally the harness) for one ARVO issue.

    Layers are scanned newest first because ARVO appends the crash artefacts
    last; the search stops at the first layer that carries the PoC.
    """
    img = open_image("n132/arvo", f"{oss_id}-vul")
    out: dict = {
        "oss_id": oss_id,
        "vuln_commit": img.vuln_commit(),
        "image_size": img.total_size,
        "poc": None,
        "binary": None,
        "fetched_bytes": 0,
    }
    dest.mkdir(parents=True, exist_ok=True)

    for layer in reversed(img.layers[-scan_layers:]):
        if out["fetched_bytes"] + layer["size"] > max_bytes:
            continue
        out["fetched_bytes"] += layer["size"]
        tf = img.blob(layer)
        names = set(tf.getnames())
        if "tmp/poc" not in names:
            continue
        member = tf.getmember("tmp/poc")
        if not member.isfile():
            continue
        payload = tf.extractfile(member)
        if payload is None:
            continue
        poc = dest / "poc"
        poc.write_bytes(payload.read())
        out["poc"] = {"path": str(poc), "size": member.size}

        if want_binary:
            bins = [n for n in names
                    if n.startswith("out/") and tf.getmember(n).isfile()
                    and tf.getmember(n).mode & 0o111]
            if bins:
                pick = max(bins, key=lambda n: tf.getmember(n).size)
                data = tf.extractfile(pick)
                if data is not None:
                    ref = dest / Path(pick).name
                    ref.write_bytes(data.read())
                    ref.chmod(0o755)
                    out["binary"] = {"path": str(ref), "name": Path(pick).name}
        break

    if out["poc"] is None:
        raise FetchError(f"tmp/poc not found in last {scan_layers} layers "
                         f"of n132/arvo:{oss_id}-vul")
    return out

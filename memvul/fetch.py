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
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REGISTRY = "https://registry-1.docker.io/v2"
AUTH = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
# Hub pull tokens expire in ~300s. Refresh before that, and again on 401/403.
TOKEN_REFRESH_S = 240
MANIFEST_ACCEPT = (
    "application/vnd.docker.distribution.manifest.v2+json,"
    "application/vnd.oci.image.manifest.v1+json"
)
_PIN_RE = re.compile(r"git (?:reset --hard|checkout(?: -f)?) ([0-9a-f]{7,40})")
# Layer cache + docker-archive scratch live on the Data disk so a 2 GB
# builder never fills the 86 GB system partition. Finished images are
# kept as tarballs under IMAGE_STORE; dockerd only holds the one in use.
CACHE_ROOT = Path(os.environ.get("MEMVUL_CACHE_ROOT",
                                   "/media/hahafish/Data/ForUbuntu/memvul-cache"))
BLOB_CACHE = CACHE_ROOT / "blobs"
IMAGE_STORE = Path(os.environ.get("MEMVUL_IMAGE_STORE",
                                    "/media/hahafish/Data/ForUbuntu/arvo-images"))


class FetchError(RuntimeError):
    pass


def _get(url: str, headers: dict[str, str], raw: bool = False,
         timeout: int = 60, retries: int = 3,
         deadline_s: int | None = None):
    last: Exception | None = None
    wall = deadline_s if deadline_s is not None else max(timeout * 3, 120)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as f:
                # A socket timeout only bounds an idle read; a registry/proxy
                # can otherwise keep a response alive indefinitely by sending
                # tiny fragments.  Read in chunks and enforce a wall-clock
                # deadline for the whole layer response.
                deadline = time.monotonic() + wall
                chunks: list[bytes] = []
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"response deadline exceeded: {url}")
                    chunk = f.read(256 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                data = b"".join(chunks)
            return data if raw else json.loads(data)
        except urllib.error.HTTPError as e:
            last = e
            # Same Bearer token will keep failing; caller must mint a new one.
            if e.code in (401, 403):
                raise
            if attempt + 1 < retries:
                time.sleep(min(2 ** attempt, 16))
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt + 1 < retries:
                time.sleep(min(2 ** attempt, 16))
    raise last if last else FetchError(f"GET failed: {url}")


def _token(repo: str) -> str:
    return _get(AUTH.format(repo=repo), {})["token"]


@dataclass
class Image:
    repo: str
    tag: str
    token: str
    manifest: dict
    config: dict
    token_at: float = 0.0

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def refresh_token(self) -> None:
        self.token = _token(self.repo)
        self.token_at = time.time()

    def ensure_token(self) -> None:
        if not self.token or time.time() - self.token_at > TOKEN_REFRESH_S:
            self.refresh_token()

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
        """Open a layer from the on-disk blob cache; download only on a miss.

        Shared digests across ARVO IDs must not hit the network again. Open
        the cached gzip/tar from disk instead of decompressing into RAM.
        """
        digest = layer["digest"]
        size = int(layer.get("size") or 0)
        self.ensure_token()
        path, n, token = _cached_blob(self.repo, digest, self.token, size or None)
        self.token = token
        if n:
            self.token_at = time.time()
        try:
            return tarfile.open(path, mode="r:*")
        except (tarfile.TarError, OSError):
            path.unlink(missing_ok=True)
            path, n, token = _cached_blob(self.repo, digest, self.token, size or None)
            self.token = token
            return tarfile.open(path, mode="r:*")


def open_image(repo: str, tag: str) -> Image:
    img = Image(repo, tag, "", {}, {}, token_at=0.0)
    img.refresh_token()
    last: Exception | None = None
    for attempt in range(3):
        auth = img.auth
        try:
            manifest = _get(f"{REGISTRY}/{repo}/manifests/{tag}",
                            auth | {"Accept": MANIFEST_ACCEPT})
            config = _get(f"{REGISTRY}/{repo}/blobs/{manifest['config']['digest']}",
                          auth)
            img.manifest = manifest
            img.config = config
            return img
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403) and attempt + 1 < 3:
                img.refresh_token()
                continue
            raise
    raise last if last else FetchError(f"open {repo}:{tag} failed")


# Skip any single layer above this size. A 1GB+ blob is almost never a
# tiny ``tmp/poc`` commit; downloading it stalls the queue for tens of minutes.
MAX_LAYER_BYTES = 1_000_000_000


_HARNESS_JUNK = (".zip", ".options", ".dict", ".txt", ".md")
_ANSI_HARNESS = re.compile(r"^(?:\x1b\[|\^\[\[?)[A-Za-z]")


def clean_harness_name(name: str | None) -> str | None:
    """Strip accidental CSI leftovers such as ``^[[Bencoder_mvg_fuzzer``."""
    if not name:
        return None
    return _ANSI_HARNESS.sub("", name) or None


def extract(oss_id: int, dest: Path, want_binary: bool = False,
            scan_layers: int = 40, max_bytes: int = 1_600_000_000,
            max_layer_bytes: int = MAX_LAYER_BYTES,
            retries: int = 1, harness: str | None = None) -> dict:
    """Fetch ``tmp/poc`` and, when present, the named ``out/`` harness.

    Layers are scanned newest first because ARVO appends the crash artefacts
    last; the search stops at the first layer that carries the PoC.  Some ARVO
    images put ``tmp/poc`` in a large source/build layer rather than a tiny
    final layer, so the bounded scan covers more layers and a larger aggregate
    blob budget than the original fast path.  A layer larger than
    ``max_layer_bytes`` is not downloaded, and the scan stops there: older
    build layers never contain the PoC once a newer >1GB layer has been
    skipped, and continuing used to pull 700–900MB per failed ID.
    """
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return _extract_once(oss_id, dest, want_binary, scan_layers,
                                 max_bytes, max_layer_bytes, harness)
        except Exception as e:  # noqa: BLE001
            last = e
            for leftover in (dest / "poc", dest / "harness"):
                leftover.unlink(missing_ok=True)
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise last if last else FetchError(f"extract {oss_id} failed")


def _pick_out_binary(tf: tarfile.TarFile, names: set[str],
                     harness: str | None,
                     want_binary: bool) -> tuple[str, tarfile.TarInfo] | None:
    """Take the catalog harness from the already-open PoC layer.

    ARVO's crash layer is almost always ``tmp/poc`` plus a dump of ``/out``.
    Harness *source* is not there.  Never pick seed zips or AFL helpers.
    """
    ordered: list[str] = []
    cleaned = clean_harness_name(harness)
    for cand in (harness, cleaned):
        if cand and cand not in ordered:
            ordered.append(cand)
    for cand in ordered:
        key = f"out/{cand}"
        if key not in names:
            continue
        member = tf.getmember(key)
        if member.isfile() and not cand.endswith(_HARNESS_JUNK):
            return cand, member
    if not want_binary:
        return None
    bins = []
    for n in names:
        if not n.startswith("out/") or n.endswith("/"):
            continue
        base = Path(n).name
        if base.endswith(_HARNESS_JUNK) or base.startswith("afl-"):
            continue
        member = tf.getmember(n)
        if member.isfile() and member.mode & 0o111:
            bins.append((n, member))
    if not bins:
        return None
    n, member = max(bins, key=lambda item: item[1].size)
    return Path(n).name, member


def _extract_once(oss_id: int, dest: Path, want_binary: bool,
                  scan_layers: int, max_bytes: int,
                  max_layer_bytes: int, harness: str | None) -> dict:
    img = open_image("n132/arvo", f"{oss_id}-vul")
    out: dict = {
        "oss_id": oss_id,
        "vuln_commit": img.vuln_commit(),
        "image_size": img.total_size,
        "poc": None,
        "binary": None,
        "fetched_bytes": 0,
        "skipped_large_layers": 0,
    }
    dest.mkdir(parents=True, exist_ok=True)

    for layer in reversed(img.layers[-scan_layers:]):
        size = int(layer.get("size") or 0)
        if size > max_layer_bytes:
            # Newest-first: the PoC lives in this fat layer or not at all.
            # Do not walk older ≤1GB layers after a skip (ImageMagick was
            # burning ~800MB/ID and 6–8 min on those leftovers).
            out["skipped_large_layers"] += 1
            break
        if out["fetched_bytes"] + size > max_bytes:
            continue
        out["fetched_bytes"] += size
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
        out["out_names"] = sorted(
            Path(n).name for n in names
            if n.startswith("out/") and not n.endswith("/")
            and "fuzz" in Path(n).name.lower())

        picked = _pick_out_binary(tf, names, harness, want_binary)
        if picked is not None:
            bin_name, bin_member = picked
            data = tf.extractfile(bin_member)
            if data is not None:
                ref = dest / "harness"
                ref.write_bytes(data.read())
                ref.chmod(0o755)
                out["binary"] = {"path": str(ref), "name": bin_name,
                                 "size": bin_member.size}
        break

    if out["poc"] is None:
        extra = ""
        if out["skipped_large_layers"]:
            extra = (f" (stopped after {out['skipped_large_layers']} layers "
                     f"> {max_layer_bytes} bytes; older layers not fetched)")
        raise FetchError(f"tmp/poc not found in last {scan_layers} layers "
                         f"of n132/arvo:{oss_id}-vul{extra}")
    return out


def _stream(url: str, headers: dict[str, str], dest: Path,
            timeout: int = 90, retries: int = 4,
            deadline_s: int | None = None,
            expected_size: int | None = None) -> int:
    """Download a blob to disk. Same proxy path as PoC extract; not dockerd."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    wall = deadline_s if deadline_s is not None else max(timeout * 3, 180)
    if expected_size and expected_size > 50_000_000:
        # A 700MB layer at 2MB/s is ~6 min; the old 270s cap aborted it
        # and the retry loop paid for the same bytes again.
        retries = 1
        wall = max(wall, expected_size // 1_000_000 + 180)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            n = 0
            deadline = time.monotonic() + wall
            with urllib.request.urlopen(req, timeout=timeout) as src, dest.open("wb") as out:
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"response deadline exceeded: {url}")
                    chunk = src.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    n += len(chunk)
            return n
        except urllib.error.HTTPError as e:
            if dest.exists():
                dest.unlink()
            if e.code in (401, 403):
                raise
            last = e
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
        except Exception as e:  # noqa: BLE001
            last = e
            if dest.exists():
                dest.unlink()
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise last if last else FetchError(f"download failed: {url}")


def _resolve_manifest(repo: str, tag: str, token: str) -> dict:
    auth = {"Authorization": f"Bearer {token}"}
    manifest = _get(f"{REGISTRY}/{repo}/manifests/{tag}",
                    auth | {"Accept": MANIFEST_ACCEPT +
                            ",application/vnd.docker.distribution.manifest.list.v2+json,"
                            "application/vnd.oci.image.index.v1+json"})
    if "manifests" in manifest:
        pick = next((m for m in manifest["manifests"]
                     if m.get("platform", {}).get("architecture") in ("amd64", "x86_64")
                     and m.get("platform", {}).get("os", "linux") == "linux"),
                    manifest["manifests"][0])
        manifest = _get(f"{REGISTRY}/{repo}/manifests/{pick['digest']}",
                        auth | {"Accept": MANIFEST_ACCEPT})
    if "layers" not in manifest:
        raise FetchError(f"no layers in manifest for {repo}:{tag}")
    return manifest


def _cached_blob(repo: str, digest: str, token: str,
                 expected_size: int | None = None) -> tuple[Path, int, str]:
    """Download a registry blob once; reuse ``/tmp/memvul/blobs`` across retries."""
    BLOB_CACHE.mkdir(parents=True, exist_ok=True)
    path = BLOB_CACHE / digest.replace(":", "_")
    if path.exists():
        have = path.stat().st_size
        if expected_size is None:
            if have > 0:
                return path, 0, token
        elif have == expected_size:
            return path, 0, token
        path.unlink()
    url = f"{REGISTRY}/{repo}/blobs/{digest}"
    last: Exception | None = None
    for attempt in range(5):
        try:
            auth = {"Authorization": f"Bearer {token}"}
            n = _stream(url, auth, path, expected_size=expected_size)
            if expected_size and n != expected_size:
                path.unlink(missing_ok=True)
                raise FetchError(f"size mismatch {digest[7:19]}: {n} != {expected_size}")
            return path, n, token
        except urllib.error.HTTPError as e:
            last = e
            path.unlink(missing_ok=True)
            if e.code in (401, 403):
                token = _token(repo)
            elif attempt + 1 < 5:
                time.sleep(min(2 ** attempt, 16))
            else:
                raise
        except TimeoutError:
            path.unlink(missing_ok=True)
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            path.unlink(missing_ok=True)
            if attempt + 1 < 5:
                time.sleep(min(2 ** attempt, 16))
            else:
                raise
    raise last if last else FetchError(f"blob {digest} failed")


def store_tar(tag: str) -> Path:
    """``n132/arvo:42516204-vul`` or ``42516204-vul`` → ``…/42516204-vul.tar``."""
    name = tag.rsplit(":", 1)[-1]
    if not name.endswith(".tar"):
        name = f"{name}.tar"
    return IMAGE_STORE / name


def persist_image(repo: str, tag: str) -> Path:
    """``docker save`` onto the Data disk. Skip if the tarball is already there."""
    dest = store_tar(tag)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    IMAGE_STORE.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    tmp.unlink(missing_ok=True)
    print(f"    saving {repo}:{tag} -> {dest}", flush=True)
    save = subprocess.run(
        ["docker", "save", "-o", str(tmp), f"{repo}:{tag}"],
        capture_output=True, text=True, timeout=600)
    if save.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise FetchError(f"docker save failed: {save.stderr[-400:]}")
    tmp.replace(dest)
    return dest


def load_into_docker(repo: str, tag: str,
                     work: Path | None = None) -> dict:
    """Fetch an image through the working urllib/proxy path and ``docker load``.

    Avoids dockerd's HTTP/2 CONNECT to the local proxy, which EOFs on
    ``auth.docker.io``. Layer blobs are cached so a mid-image TLS drop
    does not restart from layer 1. Tokens are refreshed (Hub expires ~5 min).
    A successful load is immediately archived to ``IMAGE_STORE`` so the
    image can be ``rmi``'d off the system disk after the project finishes.
    """
    if work is None:
        work = CACHE_ROOT / "images"
    inspect = subprocess.run(
        ["docker", "image", "inspect", f"{repo}:{tag}"],
        capture_output=True, text=True)
    if inspect.returncode == 0:
        try:
            persist_image(repo, tag)
        except Exception as e:  # noqa: BLE001
            print(f"    WARN persist failed: {e}", flush=True)
        return {"tag": f"{repo}:{tag}", "cached": True, "bytes": 0, "source": "docker"}

    archived = store_tar(tag)
    if archived.exists() and archived.stat().st_size > 0:
        print(f"    load-from-store {archived.name} "
              f"({archived.stat().st_size / 1e6:.0f}MB)", flush=True)
        load = subprocess.run(
            ["docker", "load", "-i", str(archived)],
            capture_output=True, text=True, timeout=600)
        if load.returncode != 0:
            raise FetchError(f"docker load from store failed: {load.stderr[-400:]}")
        return {"tag": f"{repo}:{tag}", "cached": True, "bytes": 0,
                "source": "store", "load": load.stdout.strip()}

    token = _token(repo)
    manifest = _resolve_manifest(repo, tag, token)
    layers = manifest["layers"]
    cfg = manifest["config"]
    dest = work / f"{repo.replace('/', '_')}__{tag}"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    cfg_name = cfg["digest"].replace(":", "_") + ".json"
    cfg_path, cfg_n, token = _cached_blob(
        repo, cfg["digest"], token, cfg.get("size"))
    shutil.copy2(cfg_path, dest / cfg_name)
    layer_names: list[str] = []
    fetched = cfg_n
    token_at = time.time()
    for i, layer in enumerate(layers, 1):
        digest = layer["digest"]
        size = layer.get("size")
        cached = (BLOB_CACHE / digest.replace(":", "_"))
        hit = cached.exists() and (
            size is None or cached.stat().st_size == size)
        print(f"    layer {i}/{len(layers)} "
              f"{(size or 0) / 1e6:.0f}MB {digest[7:19]}"
              f"{' cached' if hit else ''}", flush=True)
        if time.time() - token_at > TOKEN_REFRESH_S:
            token = _token(repo)
            token_at = time.time()
        raw, n, token = _cached_blob(repo, digest, token, size)
        fetched += n
        media = layer.get("mediaType", "")
        layer_rel = f"{digest.replace(':', '_')}/layer.tar"
        layer_path = dest / layer_rel
        layer_path.parent.mkdir(parents=True, exist_ok=True)
        head = raw.open("rb").read(2)
        if "gzip" in media or head == b"\x1f\x8b":
            with gzip.open(raw, "rb") as src, layer_path.open("wb") as out:
                shutil.copyfileobj(src, out, 8 * 1024 * 1024)
        else:
            try:
                os.link(raw, layer_path)
            except OSError:
                shutil.copy2(raw, layer_path)
        layer_names.append(layer_rel)

    (dest / "manifest.json").write_text(json.dumps([{
        "Config": cfg_name,
        "RepoTags": [f"{repo}:{tag}"],
        "Layers": layer_names,
    }]))
    archive = dest.with_suffix(".tar")
    if archive.exists():
        archive.unlink()
    subprocess.run(
        ["tar", "-C", str(dest), "-cf", str(archive),
         "manifest.json", cfg_name, *[p.split("/")[0] for p in layer_names]],
        check=True, timeout=600)
    shutil.rmtree(dest, ignore_errors=True)
    load = subprocess.run(
        ["docker", "load", "-i", str(archive)],
        capture_output=True, text=True, timeout=600)
    archive.unlink(missing_ok=True)
    if load.returncode != 0:
        raise FetchError(f"docker load failed: {load.stderr[-400:]}")
    try:
        persist_image(repo, tag)
    except Exception as e:  # noqa: BLE001
        print(f"    WARN persist failed: {e}", flush=True)
    return {"tag": f"{repo}:{tag}", "cached": False, "bytes": fetched,
            "source": "registry", "load": load.stdout.strip()}

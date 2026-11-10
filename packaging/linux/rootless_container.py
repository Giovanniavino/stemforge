"""Container senza Docker: immagine OCI -> cartella -> unshare + chroot.

    python3 packaging/linux/rootless_container.py pull IMAGE ROOTFS
    python3 packaging/linux/rootless_container.py run ROOTFS [--bind HOST:GUEST]... -- CMD...

Serve a riprodurre sul dev-box (Windows + WSL2, niente Docker) la build e
il collaudo che la CI fa con `container:` (BUILD_SPEC §9.6, §9.8): stessa
immagine, stessi comandi. Non installa nulla nel sistema: scarica i
layer dal registry, verifica lo SHA-256 di ognuno e li estrae; poi entra
con un namespace utente (`unshare -r`), dove si è root solo per finta.

Solo libreria standard e `unshare`/`chroot` di util-linux/coreutils.
Il digest dell'immagine usata finisce in ROOTFS/.image-digest, così una
build dice sempre da che immagine è nata.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

_ARCH = "amd64"
_TIMEOUT_S = 120
_CHUNK = 1 << 20
_ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))
_WHITEOUT = ".wh."
_OPAQUE = ".wh..wh..opq"
# fuori da una sessione di login l'ambiente è vuoto: questo basta a tutti
_GUEST_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _split_image(image: str) -> tuple[str, str, str]:
    """'quay.io/pypa/x:tag' -> (registry, repository, tag-o-digest)."""
    if "/" not in image or "." not in image.split("/")[0]:
        image = "docker.io/" + (image if "/" in image else "library/" + image)
    registry, _, rest = image.partition("/")
    if "@" in rest:
        repo, _, ref = rest.partition("@")
    else:
        repo, _, ref = rest.rpartition(":") if ":" in rest else (rest, "", "latest")
    return registry, repo, ref


def _token(registry: str, repo: str) -> str | None:
    if registry == "docker.io":
        url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
    else:
        url = f"https://{registry}/v2/auth?service={registry}&scope=repository:{repo}:pull"
    with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as response:
        return json.load(response).get("token")


def _api(registry: str) -> str:
    return "registry-1.docker.io" if registry == "docker.io" else registry


def _get(url: str, token: str | None, accept: str = _ACCEPT):
    request = urllib.request.Request(url, headers={"Accept": accept})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(request, timeout=_TIMEOUT_S)


def _fetch_manifest(base: str, ref: str, token: str | None) -> tuple[dict, str]:
    """Un manifest; se chiesto per digest, verificato byte per byte.

    I layer si verificano contro il manifest: senza questo controllo un
    digest fissato in CI proteggerebbe solo i layer di un manifest falso.
    """
    with _get(base + ref, token) as response:
        raw = response.read()
        digest = response.headers.get("Docker-Content-Digest", ref)
    if ref.startswith("sha256:"):
        actual = "sha256:" + hashlib.sha256(raw).hexdigest()
        if actual != ref:
            raise SystemExit(f"manifest corrotto: chiesto {ref}, ricevuto {actual}")
        digest = ref
    return json.loads(raw), digest


def _manifest(registry: str, repo: str, ref: str, token: str | None) -> tuple[dict, str]:
    """Manifest della piattaforma linux/amd64 e il suo digest."""
    base = f"https://{_api(registry)}/v2/{repo}/manifests/"
    data, digest = _fetch_manifest(base, ref, token)
    if "manifests" in data:
        wanted = [
            m for m in data["manifests"]
            if m.get("platform", {}).get("architecture") == _ARCH
            and m.get("platform", {}).get("os") == "linux"
        ]
        if not wanted:
            raise SystemExit(f"nessuna variante linux/{_ARCH} per {repo}:{ref}")
        data, digest = _fetch_manifest(base, wanted[0]["digest"], token)
    return data, digest


def _download_blob(registry: str, repo: str, digest: str, token: str | None, target: Path) -> None:
    algo, _, expected = digest.partition(":")
    if algo != "sha256":
        raise SystemExit(f"digest non supportato: {digest}")
    hasher = hashlib.sha256()
    url = f"https://{_api(registry)}/v2/{repo}/blobs/{digest}"
    with _get(url, token, accept="*/*") as response, target.open("wb") as out:
        while chunk := response.read(_CHUNK):
            hasher.update(chunk)
            out.write(chunk)
    if hasher.hexdigest() != expected:
        raise SystemExit(f"layer corrotto: {digest} (sha256 {hasher.hexdigest()})")


def _inside(root: Path, name: str) -> Path:
    normalized = Path(os.path.normpath(root / name.lstrip("/")))
    if normalized != root and root not in normalized.parents:
        raise SystemExit(f"il layer esce dalla radice: {name}")
    return normalized


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _apply_whiteouts(root: Path, members: list[tarfile.TarInfo]) -> list[tarfile.TarInfo]:
    """Cancellazioni dei layer OCI; restituisce i membri da estrarre."""
    keep: list[tarfile.TarInfo] = []
    for member in members:
        name = os.path.basename(member.name)
        parent = _inside(root, os.path.dirname(member.name))
        if name == _OPAQUE:
            for child in parent.iterdir() if parent.is_dir() else ():
                _remove(child)
        elif name.startswith(_WHITEOUT):
            _remove(parent / name[len(_WHITEOUT):])
        elif not (member.ischr() or member.isblk() or member.isfifo()):
            _inside(root, member.name)
            keep.append(member)
    return keep


def _extract_layer(layer: Path, root: Path) -> None:
    with tarfile.open(layer) as archive:
        members = _apply_whiteouts(root, archive.getmembers())
        for member in members:
            target = root / member.name.lstrip("/")
            if (target.exists() or target.is_symlink()) and not (target.is_dir() and member.isdir()):
                _remove(target)
        archive.extractall(root, members=members, filter="fully_trusted")


def _make_writable(root: Path) -> None:
    """Directory 0555 (es. /usr/bin su RHEL) fermerebbero il layer dopo."""
    for current, dirs, _files in os.walk(root):
        for name in dirs:
            path = Path(current) / name
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o700)


def pull(image: str, rootfs: Path) -> None:
    registry, repo, ref = _split_image(image)
    token = _token(registry, repo)
    manifest, digest = _manifest(registry, repo, ref, token)
    if rootfs.exists():
        shutil.rmtree(rootfs)
    rootfs.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        for index, layer in enumerate(manifest["layers"]):
            blob = Path(tmp) / f"layer{index}"
            print(f"layer {index + 1}/{len(manifest['layers'])}: {layer['digest']}", flush=True)
            _download_blob(registry, repo, layer["digest"], token, blob)
            _extract_layer(blob, rootfs)
            _make_writable(rootfs)
            blob.unlink()
    # immagine come chiesta + digest del manifest linux/amd64 usato davvero
    (rootfs / ".image-digest").write_text(f"{image} {digest}\n", encoding="utf-8")
    print(f"{image} -> {rootfs} ({digest})")


def _mount_script(rootfs: Path, binds: list[tuple[str, str]], command: list[str]) -> str:
    root = shlex.quote(str(rootfs))
    lines = [
        "set -eu",
        f"mount --rbind /dev {root}/dev",
        f"mount -t proc proc {root}/proc",
        f"mount --rbind /sys {root}/sys",
        f"mount -t tmpfs tmpfs {root}/tmp",
        f"cp -L /etc/resolv.conf {root}/etc/resolv.conf",
    ]
    for host, guest in binds:
        lines.append(f"mkdir -p {root}{shlex.quote(guest)}")
        lines.append(f"mount --rbind {shlex.quote(host)} {root}{shlex.quote(guest)}")
    passthrough = " ".join(
        shlex.quote(f"{key}={os.environ[key]}")
        for key in sorted(os.environ)
        if key.startswith(("STEMFORGE_", "QT_", "APPIMAGE_"))
    )
    env = f"env -i HOME=/root PATH={_GUEST_PATH} LANG=C.UTF-8 {passthrough}"
    lines.append(f"exec chroot {root} {env} {shlex.join(command)}")
    return "\n".join(lines)


def run(rootfs: Path, binds: list[tuple[str, str]], command: list[str]) -> int:
    for sub in ("dev", "proc", "sys", "tmp", "etc"):
        (rootfs / sub).mkdir(exist_ok=True)
    script = _mount_script(rootfs.resolve(), binds, command)
    unshare = ["unshare", "--user", "--map-root-user", "--mount", "--pid", "--fork"]
    return subprocess.run([*unshare, "sh", "-c", script], check=False).returncode


def _parse_run(args: list[str]) -> tuple[Path, list[tuple[str, str]], list[str]]:
    if "--" not in args:
        raise SystemExit("uso: run ROOTFS [--bind HOST:GUEST]... -- CMD...")
    split = args.index("--")
    head, command = args[:split], args[split + 1:]
    binds: list[tuple[str, str]] = []
    while len(head) > 1 and head[1] == "--bind":
        host, _, guest = head[2].partition(":")
        binds.append((str(Path(host).resolve()), guest or host))
        head = [head[0], *head[3:]]
    if len(head) != 1 or not command:
        raise SystemExit("uso: run ROOTFS [--bind HOST:GUEST]... -- CMD...")
    return Path(head[0]), binds, command


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "pull":
        pull(argv[1], Path(argv[2]))
        return 0
    if argv and argv[0] == "run":
        rootfs, binds, command = _parse_run(argv[1:])
        return run(rootfs, binds, command)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

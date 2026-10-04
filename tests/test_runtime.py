"""GPU detection, pinned runtime install, activation and the CPU fallback explanation."""

import hashlib
import io
import json
import os
import sys
import threading
import zipfile

import pytest

from mywhisper.download import DownloadCancelled, DownloadError, download_file
from mywhisper.runtime import gpu_detect, install, startup, store
from mywhisper.runtime.gpu_detect import AMD, CPU, NVIDIA, Adapter, classify, parse_adapters
from mywhisper.runtime.packages import Download, RuntimePackage, package_for

# ---- detection -------------------------------------------------------------

POWERSHELL_OUTPUT = json.dumps([
    {"Name": "AMD Radeon RX 7800 XT", "PNPDeviceID": r"PCI\VEN_1002&DEV_747E&SUBSYS_", "DriverVersion": "32.0.21"},
    {"Name": "Intel(R) UHD Graphics 770", "PNPDeviceID": r"PCI\VEN_8086&DEV_4680", "DriverVersion": "31.0"},
])


def test_parse_adapters_reads_vendor_ids():
    adapters = parse_adapters(POWERSHELL_OUTPUT)
    assert [(a.name, a.vendor) for a in adapters] == [
        ("AMD Radeon RX 7800 XT", AMD),
        ("Intel(R) UHD Graphics 770", "intel"),
    ]
    single = parse_adapters(json.dumps({"Name": "Microsoft Basic Display Adapter", "PNPDeviceID": r"ROOT\BasicDisplay"}))
    assert single == [Adapter("Microsoft Basic Display Adapter", "other", "")]
    assert parse_adapters("") == []


@pytest.mark.parametrize(
    ("adapters", "variant"),
    [
        ([Adapter("NVIDIA GeForce RTX 4070", NVIDIA)], NVIDIA),
        ([Adapter("NVIDIA GeForce RTX 5090", NVIDIA)], NVIDIA),
        ([Adapter("NVIDIA GeForce GTX 1060 6GB", NVIDIA)], NVIDIA),
        ([Adapter("NVIDIA GeForce GTX 680", NVIDIA)], CPU),  # Kepler: no CUDA 12
        ([Adapter("AMD Radeon RX 7800 XT", AMD)], AMD),
        ([Adapter("AMD Radeon RX 6800", AMD)], AMD),
        ([Adapter("AMD Radeon RX 9070 XT", AMD)], AMD),
        ([Adapter("AMD Radeon 780M Graphics", AMD)], AMD),
        ([Adapter("AMD Radeon RX 6600", AMD)], CPU),  # gfx1032: not in the ROCm wheels
        ([Adapter("AMD Radeon(TM) Graphics", AMD)], CPU),
        ([Adapter("Intel(R) Arc(TM) A770", "intel")], CPU),
        ([], CPU),
        # an AMD iGPU next to an NVIDIA card: the NVIDIA card wins
        ([Adapter("AMD Radeon 780M Graphics", AMD), Adapter("NVIDIA GeForce RTX 4060 Laptop GPU", NVIDIA)], NVIDIA),
    ],
)
def test_classify(adapters, variant):
    detection = classify(adapters)
    assert detection.variant == variant
    assert detection.reason


def test_cpu_reason_names_the_card():
    assert "RX 6600" in classify([Adapter("AMD Radeon RX 6600", AMD)]).reason
    assert "Aucune carte" in classify([]).reason


def test_pinned_packages_exist_for_the_shipped_python():
    for variant in (NVIDIA, AMD):
        package = package_for(variant, "cp313")
        assert package is not None and package.download_size > 1_000_000_000
        assert all(len(d.sha256) == 64 and d.url.startswith("https://") for d in package.downloads)
    assert package_for(CPU, "cp313") is None
    assert package_for(NVIDIA, "cp39") is None


# ---- downloads ---------------------------------------------------------------


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, status: int = 200):
        super().__init__(data)
        self.status = status


class CutResponse(FakeResponse):
    def read(self, size=-1):
        block = super().read(size)
        if not block:
            raise OSError("connexion perdue")
        return block


def serving(files, cut_after=None):
    """An opener(url, offset) that serves bytes, honours Range, and can cut a transfer."""
    calls = []

    def opener(url, offset=0):
        calls.append((url, offset))
        data = files[url]
        if cut_after and url in cut_after and not offset:
            return CutResponse(data[: cut_after[url]])
        if offset:
            return FakeResponse(data[offset:], 206)
        return FakeResponse(data)

    opener.calls = calls
    return opener


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_download_checks_sha_and_reports_progress(tmp_path):
    data = b"x" * 3_000_000
    seen = []
    opener = serving({"https://h/f.bin": data})
    path = download_file("https://h/f.bin", tmp_path / "f.bin", sha(data), seen.append, opener=opener)
    assert path.read_bytes() == data and sum(seen) == len(data)
    # already there and valid: no new request
    download_file("https://h/f.bin", tmp_path / "f.bin", sha(data), opener=opener)
    assert len(opener.calls) == 1


def test_download_rejects_a_tampered_file(tmp_path):
    opener = serving({"https://h/f.bin": b"evil"})
    with pytest.raises(DownloadError, match="SHA-256"):
        download_file("https://h/f.bin", tmp_path / "f.bin", sha(b"good"), opener=opener)
    assert not (tmp_path / "f.bin").exists() and not (tmp_path / "f.bin.part").exists()


def test_download_resumes_after_a_cut(tmp_path):
    data = bytes(range(256)) * 20_000
    opener = serving({"https://h/f.bin": data}, cut_after={"https://h/f.bin": 1_500_000})
    with pytest.raises(DownloadError):
        download_file("https://h/f.bin", tmp_path / "f.bin", sha(data), opener=opener)
    assert (tmp_path / "f.bin.part").stat().st_size > 0
    download_file("https://h/f.bin", tmp_path / "f.bin", sha(data), opener=opener)
    assert (tmp_path / "f.bin").read_bytes() == data
    assert opener.calls[-1][1] > 0  # the second request used a Range


def test_download_restarts_when_the_part_is_already_whole(tmp_path):
    # Crash between the last byte and the rename: the server answers the Range with 416.
    import urllib.error

    data = b"x" * 1000
    (tmp_path / "f.bin.part").write_bytes(data)
    calls = []

    def opener(url, offset=0):
        calls.append(offset)
        if offset:
            raise urllib.error.HTTPError(url, 416, "Range Not Satisfiable", {}, None)
        return FakeResponse(data)

    download_file("https://h/f.bin", tmp_path / "f.bin", sha(data), opener=opener)
    assert (tmp_path / "f.bin").read_bytes() == data and calls == [1000, 0]


def test_download_reports_a_truncated_response(tmp_path):
    import http.client

    class Truncated(FakeResponse):
        def read(self, size=-1):
            raise http.client.IncompleteRead(b"", 10)

    with pytest.raises(DownloadError, match="interrompu"):
        download_file("https://h/f", tmp_path / "f", None, opener=lambda url, offset=0: Truncated(b""))


def test_download_can_be_cancelled(tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DownloadCancelled):
        download_file("https://h/f", tmp_path / "f", None, cancel=cancel, opener=serving({"https://h/f": b"abc"}))


# ---- runtime install ---------------------------------------------------------


def make_zip(files) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def fake_amd_package():
    ct2 = make_zip({"ctranslate2/__init__.py": b"ROCM = True\n", "ctranslate2/ctranslate2.dll": b"dll"})
    release_zip = make_zip({"temp-windows/ctranslate2-x-cp313.whl": ct2, "temp-windows/other.whl": b"zz"})
    core = make_zip({"_rocm_sdk_core/bin/amdhip64.dll": b"hip"})
    files = {"https://h/rocm.zip": release_zip, "https://h/core.whl": core}
    package = RuntimePackage(
        "amd",
        "AMD test",
        "test-1",
        (
            Download("https://h/rocm.zip", sha(release_zip), len(release_zip), member="temp-windows/ctranslate2-x-cp313.whl"),
            Download("https://h/core.whl", sha(core), len(core)),
        ),
        disk_needed=1,
    )
    return package, serving(files)


def test_install_unpacks_wheels_side_by_side(tmp_path):
    package, opener = fake_amd_package()
    stages = []
    target = install.install(package, tmp_path, lambda stage, done, total: stages.append(stage), opener=opener)
    assert (target / "ctranslate2" / "__init__.py").read_text() == "ROCM = True\n"
    assert (target / "_rocm_sdk_core" / "bin" / "amdhip64.dll").exists()
    assert not list(target.glob("*.whl"))
    assert not (tmp_path / "downloads").exists()
    assert store.is_installed(package, tmp_path)
    assert {"download", "extract"} <= set(stages)


def test_install_refuses_without_disk_space(tmp_path):
    package, opener = fake_amd_package()
    huge = RuntimePackage(package.variant, package.label, package.version, package.downloads, disk_needed=10**18)
    with pytest.raises(DownloadError, match="Espace disque"):
        install.install(huge, tmp_path, opener=opener)


def test_manifest_version_change_means_reinstall(tmp_path):
    package, opener = fake_amd_package()
    install.install(package, tmp_path, opener=opener)
    newer = RuntimePackage(package.variant, package.label, "test-2", package.downloads, 1)
    assert not store.is_installed(newer, tmp_path)


def test_activate_puts_amd_ct2_first_and_nvidia_dlls_on_path(tmp_path, monkeypatch):
    package, opener = fake_amd_package()
    install.install(package, tmp_path, opener=opener)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "app"), raising=False)
    store.activate(package, tmp_path)
    assert sys.path[0] == str(store.install_dir(package, tmp_path))
    assert sys.path[-1] == str(tmp_path / "app" / "ct2_cpu")

    nvidia = RuntimePackage("nvidia", "NVIDIA test", "n-1", (), 1)
    bin_dir = store.install_dir(nvidia, tmp_path) / "nvidia" / "cublas" / "bin"
    bin_dir.mkdir(parents=True)
    monkeypatch.setenv("PATH", r"C:\Windows")
    store.activate(nvidia, tmp_path)
    assert os.environ["PATH"].startswith(str(bin_dir))


# ---- startup choice and CPU notice ----------------------------------------------


def test_prepare_uses_an_installed_runtime(tmp_path, monkeypatch):
    package, opener = fake_amd_package()
    monkeypatch.setenv("MYWHISPER_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(startup, "package_for", lambda variant, tag=None: package if variant == AMD else None)
    assert startup.prepare("auto").variant == "dev"  # nothing installed, source checkout
    install.install(package, tmp_path, opener=opener)
    assert startup.prepare("auto").variant == AMD
    assert startup.prepare("cpu").forced_cpu


def test_cpu_notice_cases():
    gpu = gpu_detect.Detection(NVIDIA, Adapter("NVIDIA GeForce RTX 4070", NVIDIA), "Carte NVIDIA détectée : RTX 4070")
    notice = startup.cpu_notice(startup.RuntimeChoice(None), gpu)
    assert notice.install_variant == NVIDIA and "Go à télécharger" in notice.detail
    assert notice.title == startup.SLOW_TITLE

    intel = classify([Adapter("Intel(R) UHD Graphics 770", "intel")])
    notice = startup.cpu_notice(startup.RuntimeChoice(None), intel)
    assert notice.install_variant is None and "UHD Graphics 770" in notice.detail

    failed = startup.cpu_notice(startup.RuntimeChoice(AMD))
    assert "pilote AMD" in failed.detail and failed.install_variant is None

    assert startup.cpu_notice(startup.RuntimeChoice(None, forced_cpu=True)) is None

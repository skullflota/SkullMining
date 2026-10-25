"""v0.8.0: actualización desde las releases de GitHub."""
import io, logging, os, sys, tempfile, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "SkullMining"))
import skull_updater as U

LOG = logging.getLogger("t")


def mkzip(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, c in files.items():
            z.writestr(n, c)
    return b.getvalue()


GOOD = {"SkullMining/load.py": "X = 2\n", "SkullMining/skull_tracker.py": "PLUGIN_VERSION = '0.9.0'\n",
        "SkullMining/LEEME.md": "hola", "SkullMining/pending.json": "[]", "SkullMining/__pycache__/a.pyc": "x"}


class R:
    def __init__(self, status=200, js=None, content=b"", url=""):
        self.status_code, self._js, self.content, self.url = status, js, content, url
    def json(self):
        return self._js


def api(tag, name="SkullMining-v0.9.0.zip", url="https://github.com/skullflota/SkullMining/releases/download/v0.9.0/SkullMining-v0.9.0.zip"):
    return {"tag_name": tag, "assets": [{"name": name, "browser_download_url": url}]}


def test_versions():
    assert U.parse_version("v0.10.0") > U.parse_version("0.9.9") > U.parse_version("0.8.0")
    assert U.latest_from_api(api("v0.9.0"))["version"] == "0.9.0"
    assert U.latest_from_api(api("v0.9.0", url="https://evil.example/x.zip")) is None
    assert U.latest_from_api(api("v0.9.0", name="otra-cosa.zip")) is None
    assert U.latest_from_api(dict(api("v0.9.0"), draft=True)) is None


def test_check_and_install():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "load.py"), "w").write("X = 1\n")
    open(os.path.join(d, "pending.json"), "w").write('[{"kind":"mark"}]')
    zipdata = mkzip(GOOD)
    def get(url, **kw):
        if url == U.API_LATEST:
            return R(js=api("v0.9.0"))
        return R(content=zipdata, url="https://objects.githubusercontent.com/abc")
    u = U.Updater(d, "0.8.0", LOG, http_get=get)
    u.check(); assert u.state == U.AVAILABLE and u.latest["version"] == "0.9.0"
    u.install(); assert u.state == U.DONE, u.error
    assert open(os.path.join(d, "load.py")).read() == "X = 2\n"
    assert open(os.path.join(d, "_anterior", "load.py")).read() == "X = 1\n"
    assert open(os.path.join(d, "pending.json")).read() == '[{"kind":"mark"}]'   # la cola no se toca
    assert not os.path.exists(os.path.join(d, "__pycache__"))
    # misma versión: no ofrece nada
    u2 = U.Updater(d, "0.9.0", LOG, http_get=get); u2.check(); assert u2.state == U.IDLE


def test_bad_zips():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "load.py"), "w").write("X = 1\n")
    for bad in ({"SkullMining/../evil.py": "x=1"},                       # ruta peligrosa
                {"SkullMining/load.py": "def (:", "SkullMining/skull_tracker.py": "a=1"},   # no compila
                {"SkullMining/otro.py": "a=1"}):                         # no es el plugin
        try:
            U.install_zip(mkzip(bad), d); assert False, bad
        except (ValueError, SyntaxError):
            pass
    assert open(os.path.join(d, "load.py")).read() == "X = 1\n"           # no se ha tocado nada
    def get(url, **kw):
        return R(js=api("v0.9.0")) if url == U.API_LATEST else R(content=mkzip(GOOD), url="https://evil.example/x")
    u = U.Updater(d, "0.8.0", LOG, http_get=get); u.check(); u.install()
    assert u.state == U.ERROR and open(os.path.join(d, "load.py")).read() == "X = 1\n"


if __name__ == "__main__":
    test_versions(); test_check_and_install(); test_bad_zips(); print("OK test_updater")

"""The engine (#176, pipeline v3 spike S11): one long-lived process that runs a lesson's tools and rebuilds only
what changed. Opt-in: nothing in the paint-lesson skill uses it, and `tools.py <tool>` works exactly as before
whether or not an engine is running.

    python spike/tools.py engine serve                      # start it (leave it running in the background)
    python spike/tools.py engine call <tool> <arguments>    # any tool, as `tools.py <tool> <arguments>` would run it
    python spike/tools.py engine chain --lesson <lesson>    # the skill's tools in order, from what changed
    python spike/tools.py engine status                     # what it holds
    python spike/tools.py engine stop

`call` prints the tool's one JSON line and exits with its code, so a caller swaps `tools.py <tool>` for
`tools.py engine call <tool>` and reads the same answer. What a tool writes is the same, byte for byte, as when it
runs as its own process (docs/spikes/v3-one-engine.md, checked by spike/experiments/v3_one_engine.py). What the
engine keeps between calls, each by exactly what went into it:

- the Python modules, the stroke cards and element files (spike/yaml_files.py), and the outline model, loaded once;
- every step picture build (build_steps._built), so step-aids, draft-text, check, and publish don't build again;
- what's behind the objects and each part's prepared paint (build_steps.remember_parts), so a change to one stage
  rebuilds only the parts its steps paint;
- the outline model's reading of each picture (the embedding, about 8 seconds), in memory and on disk in
  output/.embed-cache/ by the picture's bytes and the model file, so `outline` reads a finish once however many
  times its parts change.

`chain` knows what each tool reads (INPUTS: plan.json's parts, paints, stages and the rest of it, the finish, the
outlines, the background picture, canvas.json, the lesson's elements, text.json, notes.json, and techniques/ and
palettes/) and remembers, for each lesson, what each tool read when it last succeeded. It starts at the first tool
in the skill's order (rule 9) that hasn't succeeded yet or whose inputs changed since, and runs every tool after it:
a parts edit runs from `outline`, a stages edit from `build-steps`, a new canvas.json from `step-aids`, text alone
just `check`. A tool that refuses or fails doesn't count as run. `--from` says where to start instead. It stops at
the first tool that refuses.

One engine serves one caller at a time; calls wait their turn. It listens on 127.0.0.1 with a random token, both
written to its state file (output/.engine/engine.json unless --state), which `call` reads.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import secrets
import socket
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
STATE = ROOT / "output" / ".engine" / "engine.json"
READINGS = ROOT / "output" / ".embed-cache"
ORDER = ["outline", "paints", "build-steps", "step-aids", "mix", "draft-text", "card-adapt", "check"]  # rule 9
TOOLS_ONLY = ("engine",)  # what `call` won't run inside the engine


# What each tool of the chain reads, by group (its own outputs left out: outline's outlines, paints' paints,
# draft-text's and card-adapt's text.json). A tool is run again when any of its groups changed since it last
# succeeded on the lesson, and so is every tool after it.
INPUTS = {
    "outline": ("parts", "rest", "finish"),
    "paints": ("parts", "rest", "finish", "owner", "library"),
    "build-steps": ("parts", "paints", "stages", "rest", "finish", "owner", "background"),
    "step-aids": ("parts", "paints", "stages", "rest", "finish", "owner", "background", "canvas"),
    "mix": ("paints", "rest", "finish", "library"),
    "draft-text": ("parts", "paints", "stages", "rest", "finish", "owner", "background", "canvas", "elements",
                   "library"),
    "card-adapt": ("stages", "rest", "library"),
    "check": ("parts", "paints", "stages", "rest", "finish", "owner", "background", "canvas", "elements", "library",
              "text", "notes"),
}
FILES = {"finish": "99_finish.png", "owner": "parts/owner.png", "background": "98_background.png",
         "canvas": "canvas.json", "text": "text.json", "notes": "notes.json"}


def _digest_files(paths) -> str:
    h = hashlib.sha1()
    for path in paths:
        h.update(f"{path}\n".encode())
        try:
            h.update(Path(path).read_bytes())
        except OSError:
            h.update(b"(missing)")
    return h.hexdigest()


def _inputs(lesson: Path) -> dict[str, str]:
    """A digest of every group of inputs the chain's tools read: plan.json's parts, paints, stages, and everything
    else in it (technique, palette, ...), the finish, the outlines, the background picture, canvas.json, the
    lesson's drafted elements, text.json, notes.json, and the library (techniques/ and palettes/, every byte)."""
    digest = lambda v: hashlib.sha1(json.dumps(v, sort_keys=True).encode()).hexdigest()  # noqa: E731
    try:
        plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as e:
        plan = {"unreadable": str(e)}
    out = {k: digest(plan.get(k)) for k in ("parts", "paints", "stages")}
    out["rest"] = digest({k: v for k, v in plan.items() if k not in ("parts", "paints", "stages")})
    for group, name in FILES.items():
        out[group] = _digest_files([lesson / name])
    out["elements"] = _digest_files(sorted(f for f in (lesson / "elements").rglob("*") if f.is_file()))
    out["library"] = _library_stamp(plan.get("palette"))
    return out


def _library_stamp(palette=None) -> str:
    """techniques/ and palettes/, plus a palette the plan names by path outside palettes/ (tools.load_palette takes
    "<path>.yaml" relative to the repo root)."""
    files = sorted(p for folder in (ROOT / "techniques", ROOT / "palettes") if folder.exists()
                   for p in folder.rglob("*.yaml"))
    if isinstance(palette, str) and palette.endswith(".yaml") and (ROOT / palette) not in files:
        files.append(ROOT / palette)
    return _digest_files(files)


def _lesson_of(argv: list[str], cwd: str) -> Path | None:
    for i, a in enumerate(argv):
        if a == "--lesson" and i + 1 < len(argv):
            return (Path(cwd) / argv[i + 1]).resolve()
        if a.startswith("--lesson="):
            return (Path(cwd) / a.split("=", 1)[1]).resolve()
    return None


class Engine:
    def __init__(self, readings: Path = READINGS) -> None:
        import build_steps
        import tools

        self.tools, self.bs = tools, build_steps
        self.started = time.time()
        self.calls = 0
        # lesson -> tool -> the digests of that tool's inputs right after it last succeeded on the lesson
        self.ran: dict[str, dict[str, dict[str, str]]] = {}
        self.sam, self.readings = None, Path(readings)
        self.memos, self._undo = install_memos()  # first: if it fails, nothing else has been changed
        try:
            build_steps.remember_parts(True)
            tools._outline_model = self.outline_model
        except Exception:
            self.close()
            raise
        self.base_env = dict(os.environ)

    def close(self) -> None:
        """Put back everything the engine changed in this process (for tests that make one in their own)."""
        for module, name, was in reversed(self._undo):
            setattr(module, name, was)
        self._undo = []
        self.bs.remember_parts(False)
        self.tools._outline_model = None

    def outline_model(self):
        """The outline model, loaded on the first outline and kept, with every picture's reading kept on disk."""
        import outline

        if self.sam is None:
            self.sam = outline.Sam(keep=self.readings)
        self.sam.emb = None  # outline reads the picture (from what's kept, when it's there)
        return self.sam

    def _fresh_state(self) -> None:
        """Put back what a new process would start with, where a tool leaves something behind that isn't keyed by
        its inputs: a painter's palette registered for the mixer, and the mixer's memos made with it."""
        import mixing

        if mixing.CUSTOM:
            mixing.CUSTOM.clear()
            for f in vars(mixing).values():
                if hasattr(f, "cache_clear"):
                    f.cache_clear()

    def _env(self, env: dict[str, str]) -> None:
        """The caller's environment, plus .env's values it doesn't set (as run.py's load_dotenv does at import)."""
        from dotenv import dotenv_values

        os.environ.clear()
        os.environ.update(env)
        for k, v in dotenv_values(ROOT / ".env").items():
            if v is not None and k not in os.environ:
                os.environ[k] = v

    def call(self, argv: list[str], cwd: str, env: dict[str, str]) -> dict:
        """One tool, in this process, as `tools.py <argv>` would run it: (exit code, stdout, stderr)."""
        if argv[:1] and argv[0] in TOOLS_ONLY:
            return {"code": 2, "stdout": json.dumps({"refused": "engine call runs a tool, not the engine"}) + "\n",
                    "stderr": ""}
        self.calls += 1
        lesson = _lesson_of(argv, cwd)
        # what the tool reads, taken before it runs: an edit made while it runs must still send the chain back to it
        before = _inputs(lesson) if lesson is not None and argv[:1] and argv[0] in INPUTS else None
        out, err = io.StringIO(), io.StringIO()
        here = os.getcwd()
        try:
            os.chdir(cwd)
            self._env(env)
            self._fresh_state()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = self.tools.main(list(argv))
                except SystemExit as e:  # argparse: --help, or arguments it can't read
                    code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
                except Exception:  # what a crashing tool prints: its traceback, exit code 1
                    traceback.print_exc()
                    code = 1
        finally:
            os.environ.clear()
            os.environ.update(self.base_env)
            os.chdir(here)
        if code == 0 and before is not None:
            self.record(lesson, argv[0], before)
        return {"code": code, "stdout": out.getvalue(), "stderr": err.getvalue()}

    def record(self, lesson: Path, tool: str, now: dict[str, str] | None = None) -> None:
        """`tool` succeeded on the lesson: what it read, as it was when it started (now, from call) or as it is now.
        A tool that failed or refused leaves its last success in place, so the chain still runs it after an edit."""
        now = now if now is not None else _inputs(Path(lesson))
        self.ran.setdefault(str(Path(lesson).resolve()), {})[tool] = {g: now[g] for g in INPUTS[tool]}

    def start_of(self, lesson: Path) -> tuple[str, str]:
        """Where the chain starts for this lesson, and why: the first tool in the skill's order that hasn't
        succeeded on the lesson in this engine, or whose inputs changed since it last did."""
        ran, now = self.ran.get(str(Path(lesson).resolve()), {}), _inputs(Path(lesson))
        for tool in ORDER:
            if tool not in ran:
                return tool, f"{tool} hasn't succeeded on this lesson in this engine yet"
            changed = [g for g in INPUTS[tool] if ran[tool][g] != now[g]]
            if changed:
                return tool, f"{', '.join(changed)} changed since {tool} last succeeded"
        return "check", "nothing any tool reads changed since it last succeeded: only check runs"

    def chain(self, lesson: str, cwd: str, env: dict[str, str], first: str | None, last: str) -> dict:
        path = (Path(cwd) / lesson).resolve()
        start, why = (first, "--from") if first else self.start_of(path)
        if start not in ORDER or last not in ORDER or ORDER.index(start) > ORDER.index(last):
            return {"code": 2, "stdout": json.dumps({"refused": f"the chain is {', '.join(ORDER)}: --from {start} "
                                                                  f"--to {last} isn't a stretch of it"}) + "\n",
                    "stderr": ""}
        began, ran, errs, code = time.time(), [], [], 0
        for tool in ORDER[ORDER.index(start):ORDER.index(last) + 1]:
            r = self.call([tool, "--lesson", lesson], cwd, env)
            errs.append(r["stderr"])
            lines = r["stdout"].strip().splitlines()
            result = json.loads(lines[-1]) if lines else {}
            ran.append({"tool": tool, "code": r["code"], "result": result})
            if r["code"] != 0:
                code = r["code"]
                break
        problems = [f"{x['tool']}: {p}" for x in ran for p in (x["result"].get("problems") or [])]
        out = {"from": start, "why": why, "ran": ran, "problems": problems, "ok": code == 0 and not problems,
               "seconds": round(time.time() - began, 2), "cost_usd": 0.0}
        return {"code": code, "stdout": json.dumps(out) + "\n", "stderr": "".join(errs)}

    def status(self) -> dict:
        sam = self.sam
        try:
            import resource  # not on Windows

            peak = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)  # KB on Linux
        except ImportError:
            peak = None
        return {"up_seconds": round(time.time() - self.started, 1), "calls": self.calls, "pid": os.getpid(),
                "peak_memory_mb": peak,
                "builds_kept": len(self.bs._built), "parts_kept": len(self.bs._parts_memo or {}),
                "memos": {name: dict(m.counts, held=len(m.kept)) for name, m in self.memos.items()},
                "lessons": sorted(self.ran), "outline_model": "loaded" if sam else "not loaded yet",
                "readings": dict(sam.reads) if sam else {}, "readings_folder": str(self.readings)}


# ---------------------------------------------------------------------------
# What the tools work out again and again from the same files, kept by those files' bytes
# ---------------------------------------------------------------------------


def _file_digest(path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def _arrays_digest(h, arrays) -> None:
    import numpy as np

    for a in arrays:
        h.update(f"{a.shape}{a.dtype}".encode() + np.ascontiguousarray(a).tobytes())


class Memo:
    """A function's answers by a key made from everything it reads, the newest `size` of them. Each caller gets
    its own copy, so changing an answer can't change the next one."""

    def __init__(self, fn, key, size: int, copy_out=None):
        import copy

        self.fn, self.key, self.size = fn, key, size
        self.copy_out = copy_out or copy.deepcopy
        self.kept: dict[str, object] = {}
        self.counts = {"made": 0, "reused": 0}

    def __call__(self, *args, **kwargs):
        key = self.key(*args, **kwargs)
        if key is None:  # a call this memo doesn't cover: as it was
            return self.fn(*args, **kwargs)
        if key in self.kept:
            self.counts["reused"] += 1
            self.kept[key] = self.kept.pop(key)  # newest last
        else:
            self.counts["made"] += 1
            self.kept[key] = self.fn(*args, **kwargs)
            while len(self.kept) > self.size:
                self.kept.pop(next(iter(self.kept)))
        return self.copy_out(self.kept[key])


def _yaml_stamp(*folders: Path) -> str:
    """Every stroke card, basics card, element, technique, and palette file's path and bytes: what draft-text reads
    besides its arguments. A changed card changes the key."""
    return _digest_files(sorted(p for folder in folders if folder.exists() for p in folder.rglob("*.yaml")))


def install_memos() -> tuple[dict[str, Memo], list[tuple[object, str, object]]]:
    """Memos for the slowest repeated work the build memo doesn't cover, each a pure function of the files or
    arrays it's keyed on: decoding a step picture, a page's inlined pictures, the embed's pictures, the texture
    check, and the drafted text check and publish draft again to compare. Only the engine installs them. Returns
    the memos, and (module, name, what it was) for each function replaced, to put back."""
    import draft_text
    import filters
    import lesson_embed
    import lesson_page
    import tools

    memos: dict[str, Memo] = {}
    undo: list[tuple[object, str, object]] = []

    def patch(module, name: str, new) -> None:
        undo.append((module, name, getattr(module, name)))
        setattr(module, name, new)

    def load_key(path, max_side=filters.MAX_SIDE):
        return f"{_file_digest(path)} {max_side}"

    memos["load"] = Memo(filters.load, load_key, 64, copy_out=lambda a: a.copy())
    patch(filters, "load", memos["load"])

    def src_key(folder, name, embed, max_side=900):
        return f"{_file_digest(Path(folder) / name)} {max_side}" if embed else None

    memos["image_src"] = Memo(lesson_page.image_src, src_key, 256, copy_out=lambda s: s)
    patch(lesson_page, "image_src", memos["image_src"])

    webp = lesson_embed.webp

    def webp_bytes(src, out, max_side):  # the file's bytes and the size webp returns
        size = webp(src, out, max_side)
        return Path(out).read_bytes(), size

    def webp_key(src, out, max_side):
        return f"{_file_digest(src)} {max_side}"

    kept_webp = Memo(webp_bytes, webp_key, 256, copy_out=lambda x: x)

    def webp_memo(src, out, max_side):
        data, size = kept_webp(src, out, max_side)
        if not Path(out).exists() or Path(out).read_bytes() != data:
            Path(out).write_bytes(data)  # what webp would have written
        return list(size)

    memos["webp"] = kept_webp
    patch(lesson_embed, "webp", webp_memo)

    def jumps_key(lesson, paths):
        return " ".join(f"{Path(p).name}:{_file_digest(p)}" for p in paths) if all(Path(p).exists() for p in paths) else None

    memos["texture_jumps"] = Memo(tools.texture_jumps, jumps_key, 16)
    patch(tools, "texture_jumps", memos["texture_jumps"])

    def draft_key(plan, pictures, masks, canvas_box=None, canvas=None, known=None, lesson=None, *, owner):
        h = hashlib.sha1(json.dumps([plan, canvas_box, canvas, known, str(lesson)], sort_keys=True,
                                    default=str).encode())
        _arrays_digest(h, list(pictures) + list(masks) + [owner])
        folders = [ROOT / "techniques", ROOT / "palettes"] + ([Path(lesson) / "elements"] if lesson else [])
        h.update(_yaml_stamp(*folders).encode())
        return h.hexdigest()

    memos["draft"] = Memo(draft_text.draft, draft_key, 8)
    patch(draft_text, "draft", memos["draft"])

    def png_bytes(rgb):
        from PIL import Image

        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="PNG")  # what Image.save writes for a path ending in .png
        return buf.getvalue()

    def png_key(rgb):
        h = hashlib.sha1()
        _arrays_digest(h, [rgb])
        return h.hexdigest()

    memos["png"] = Memo(png_bytes, png_key, 128, copy_out=lambda b: b)
    patch(tools, "save_png", lambda rgb, path: Path(path).write_bytes(memos["png"](rgb)))
    return memos, undo


# ---------------------------------------------------------------------------
# The server and the client: one JSON line each way, over 127.0.0.1
# ---------------------------------------------------------------------------


def _send(conn: socket.socket, msg: dict) -> None:
    conn.sendall(json.dumps(msg).encode("utf-8") + b"\n")


def _recv(conn: socket.socket) -> dict:
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = conn.recv(1 << 20)
        if not chunk:
            break
        buf += chunk
    return json.loads(buf.decode("utf-8")) if buf.strip() else {}


def serve(state: Path, readings: Path = READINGS) -> int:
    engine = Engine(readings)
    token = secrets.token_hex(16)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    state.parent.mkdir(parents=True, exist_ok=True)
    tmp = state.with_suffix(".tmp")
    tmp.write_text(json.dumps({"port": srv.getsockname()[1], "token": token, "pid": os.getpid()}), encoding="utf-8")
    os.replace(tmp, state)  # written whole: a caller never reads half of it
    print(f"engine: listening on 127.0.0.1:{srv.getsockname()[1]} (state {state})", file=sys.stderr, flush=True)
    try:
        while True:
            conn, _ = srv.accept()
            with conn:
                try:
                    conn.settimeout(30)  # a caller that connects and sends nothing doesn't hold up the others
                    req = _recv(conn)
                    conn.settimeout(None)
                except (OSError, ValueError):
                    continue
                if not secrets.compare_digest(str(req.get("token", "")), token):
                    _send(conn, {"code": 2, "stdout": json.dumps({"refused": "wrong engine token"}) + "\n", "stderr": ""})
                    continue
                op = req.get("op")
                try:
                    if op == "call":
                        reply = engine.call(req["argv"], req["cwd"], req["env"])
                    elif op == "chain":
                        reply = engine.chain(req["lesson"], req["cwd"], req["env"], req.get("first"), req["last"])
                    elif op == "status":
                        reply = {"code": 0, "stdout": json.dumps(engine.status()) + "\n", "stderr": ""}
                    elif op == "stop":
                        _send(conn, {"code": 0, "stdout": json.dumps({"stopped": True, **engine.status()}) + "\n",
                                     "stderr": ""})
                        return 0
                    else:
                        reply = {"code": 2, "stdout": json.dumps({"refused": f"unknown op {op!r}"}) + "\n", "stderr": ""}
                except Exception:
                    reply = {"code": 1, "stdout": "", "stderr": traceback.format_exc()}
                try:
                    _send(conn, reply)
                except OSError:
                    pass  # the caller went away; the work is done either way
    finally:
        srv.close()
        with contextlib.suppress(OSError):
            if json.loads(state.read_text(encoding="utf-8")).get("token") == token:
                state.unlink()


def request(state: Path, msg: dict) -> dict:
    """Send one request to the running engine. Raises ConnectionError when there's none."""
    try:
        info = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ConnectionError(f"no engine is running (no {state})") from e
    try:
        conn = socket.create_connection(("127.0.0.1", int(info["port"])), timeout=10)
    except OSError as e:
        raise ConnectionError(f"no engine answers at 127.0.0.1:{info['port']} ({e})") from e
    with conn:
        conn.settimeout(None)  # a tool can take minutes; the engine answers when it's done
        _send(conn, {**msg, "token": info["token"]})
        reply = _recv(conn)
    if not reply:
        raise ConnectionError("the engine closed the connection without an answer")
    return reply


def _relay(reply: dict) -> int:
    sys.stderr.write(reply.get("stderr", ""))
    sys.stdout.write(reply.get("stdout", ""))
    sys.stdout.flush()
    return int(reply.get("code", 1))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="tools.py engine", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["serve", "call", "chain", "status", "stop"],
                    help="call takes the tool and its arguments after it (and --state, if any, before the tool)")
    ap.add_argument("--state", type=Path, default=STATE, help=f"the engine's state file (default {STATE})")
    ap.add_argument("--readings", type=Path, default=READINGS,
                    help=f"serve: where the outline model's reading of each picture is kept (default {READINGS})")
    ap.add_argument("--lesson", help="chain: the lesson folder")
    ap.add_argument("--from", dest="first", choices=ORDER, help="chain: start here instead of from what changed")
    ap.add_argument("--to", dest="last", choices=ORDER, default="check", help="chain: stop after this tool (default check)")
    msg: dict = {"cwd": os.getcwd(), "env": dict(os.environ)}
    if argv[:1] == ["call"]:  # everything after the tool's name is the tool's, word for word
        rest, state = list(argv[1:]), STATE
        if rest[:1] == ["--state"] and len(rest) > 1:
            state, rest = Path(rest[1]), rest[2:]
        elif rest[:1] and rest[0].startswith("--state="):
            state, rest = Path(rest[0].split("=", 1)[1]), rest[1:]
        if not rest or rest[0].startswith("-"):
            ap.error("call needs a tool and its arguments, as for tools.py: engine call build-steps --lesson <lesson>")
        msg.update(op="call", argv=rest)
        try:
            return _relay(request(state, msg))
        except ConnectionError as e:
            return _not_running(e)
    a = ap.parse_args(argv)
    if a.action == "serve":
        return serve(a.state, a.readings)
    if a.action == "chain":
        if not a.lesson:
            ap.error("chain needs --lesson")
        msg.update(op="chain", lesson=a.lesson, first=a.first, last=a.last)
    else:
        msg["op"] = a.action
    try:
        reply = request(a.state, msg)
    except ConnectionError as e:
        return _not_running(e)
    return _relay(reply)


def _not_running(e: Exception) -> int:
    print(json.dumps({"refused": f"{e}. Start one with: python spike/tools.py engine serve (in the background), "
                                 "or run the tool without the engine: python spike/tools.py <tool> ..."}))
    return 2

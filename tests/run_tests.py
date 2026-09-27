#!/usr/bin/env python3
"""Runs the download script against stub yt-dlp/ffmpeg/ffprobe and checks the argv yt-dlp receives.

Uses bulk-youtube-download.bat on Windows (with both LF and CRLF line endings) and bulk-youtube-download.sh elsewhere.
Nothing is downloaded: the stub yt-dlp only records its arguments.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WINDOWS = os.name == "nt"

LINKS = [
    "[",
    '  "https://youtu.be/7ssVNgOK_MM",',
    '  "--update-to=evil/repo@tag",',
    '  "-o/tmp/pwned",',
    '  "file:///etc/passwd",',
    '  "https://example.invalid/c/!USERNAME!/x!y^z%PATH%",',
    '  "HTTPS://www.youtube.com/watch?v=-m1EzV-i3WI&list=abc",',
    "]",
]

EXPECTED_URLS = [
    "https://youtu.be/7ssVNgOK_MM",
    "https://example.invalid/c/!USERNAME!/x!y^z%PATH%",
    "HTTPS://www.youtube.com/watch?v=-m1EzV-i3WI&list=abc",
]

STUB_YTDLP = """import json, os, sys
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "argv.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
"""


def make_stubs(bin_dir):
    with open(os.path.join(bin_dir, "yt_dlp_stub.py"), "w", encoding="utf-8") as f:
        f.write(STUB_YTDLP)
    if IS_WINDOWS:
        with open(os.path.join(bin_dir, "yt-dlp.cmd"), "w") as f:
            f.write('@echo off\r\nsetlocal DisableDelayedExpansion\r\n"%s" "%%~dp0yt_dlp_stub.py" %%*\r\n' % sys.executable)
        for name in ("ffmpeg", "ffprobe"):
            with open(os.path.join(bin_dir, name + ".cmd"), "w") as f:
                f.write("@exit /b 0\r\n")
    else:
        path = os.path.join(bin_dir, "yt-dlp")
        with open(path, "w") as f:
            f.write('#!/bin/sh\nexec "%s" "$(dirname "$0")/yt_dlp_stub.py" "$@"\n' % sys.executable)
        os.chmod(path, 0o755)
        for name in ("ffmpeg", "ffprobe"):
            path = os.path.join(bin_dir, name)
            with open(path, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(path, 0o755)


def run_case(label, script_name, newline):
    work = tempfile.mkdtemp(prefix="byd-test-")
    try:
        bin_dir = os.path.join(work, "bin")
        run_dir = os.path.join(work, "run")
        os.makedirs(bin_dir)
        os.makedirs(run_dir)
        make_stubs(bin_dir)

        with open(os.path.join(ROOT, script_name), "rb") as f:
            script = f.read().replace(b"\r\n", b"\n")
        with open(os.path.join(run_dir, script_name), "wb") as f:
            f.write(script.replace(b"\n", newline))
        with open(os.path.join(run_dir, "links.txt"), "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(LINKS) + "\n")

        env = dict(os.environ)
        env["PATH"] = bin_dir + os.pathsep + env["PATH"]
        if IS_WINDOWS:
            # The script's emoji lines only parse under the UTF-8 code page
            cmd = ["cmd", "/d", "/c", "chcp 65001 >nul & " + script_name + " --no-mtime"]
        else:
            cmd = ["bash", script_name, "--no-mtime"]
        proc = subprocess.run(cmd, cwd=run_dir, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        output = proc.stdout.decode("utf-8", errors="replace")

        log_path = os.path.join(bin_dir, "argv.jsonl")
        calls = []
        if os.path.exists(log_path):
            with open(log_path, encoding="utf-8") as f:
                calls = [json.loads(line) for line in f if line.strip()]

        errors = []
        if proc.returncode != 0:
            errors.append("exit code %d" % proc.returncode)
        urls = []
        for argv in calls:
            if len(argv) < 2 or argv[-2] != "--":
                errors.append("URL not preceded by '--': %r" % argv[-2:])
            if "--no-mtime" not in argv[:-2]:
                errors.append("extra args not passed before '--': %r" % argv)
            urls.append(argv[-1])
        if urls != EXPECTED_URLS:
            errors.append("URLs passed to yt-dlp:\n    %s\n  expected:\n    %s" % ("\n    ".join(map(repr, urls)), "\n    ".join(map(repr, EXPECTED_URLS))))

        if errors:
            print("FAIL %s" % label)
            for e in errors:
                print("  " + e)
            print("  --- script output ---")
            print("  " + output.replace("\n", "\n  "))
            return False
        print("PASS %s" % label)
        return True
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if IS_WINDOWS:
        cases = [("bat (LF)", "bulk-youtube-download.bat", b"\n"),
                 ("bat (CRLF)", "bulk-youtube-download.bat", b"\r\n")]
    else:
        cases = [("sh", "bulk-youtube-download.sh", b"\n")]
    results = [run_case(*case) for case in cases]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()

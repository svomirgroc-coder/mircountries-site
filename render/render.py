#!/usr/bin/env python3
"""Бесплатный рендерер MirCountries (замена Creatomate): FFmpeg в GitHub Actions.
Вход: переменная окружения JOB (JSON) с полями:
  tag, width, height, flag_url,
  jobs: [{name, videos:[{url,start}], audios:[{url,start,trim}], flags:[start,...], duration}]
Результат: файлы <name>.mp4 + result.json в папке out/."""
import json, os, subprocess, sys, urllib.request, hashlib, pathlib

spec = json.loads(os.environ["JOB"])
W, H = int(spec.get("width", 720)), int(spec.get("height", 1280))
FPS = 24
work = pathlib.Path("work"); work.mkdir(exist_ok=True)
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
cache = {}

def fetch(url):
    if url in cache:
        return cache[url]
    p = work / (hashlib.md5(url.encode()).hexdigest() + pathlib.Path(url.split("?")[0]).suffix[:6])
    subprocess.run(["curl", "-sSL", "--fail", "--retry", "3", "-o", str(p), url], check=True)
    cache[url] = str(p)
    return str(p)

flag = fetch(spec["flag_url"]) if spec.get("flag_url") else None
fw, fh = round(W * 0.27), round(H * 0.10)
fx, fy = round(W * 0.04), round(H * 0.03)
results = []

for j in spec["jobs"]:
    cmd = ["ffmpeg", "-loglevel", "error", "-y"]
    fc = []
    n = 0
    vlabels = []
    for v in j["videos"]:
        cmd += ["-i", fetch(v["url"])]
        fc.append(f"[{n}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
                  f"trim=duration=25,setpts=PTS-STARTPTS[v{n}]")
        vlabels.append(f"[v{n}]"); n += 1
    fc.append("".join(vlabels) + f"concat=n={len(vlabels)}:v=1:a=0[base]")
    last = "base"
    for k, t in enumerate(j.get("flags", [])):
        if not flag:
            break
        cmd += ["-stream_loop", "-1", "-i", flag]
        fc.append(f"[{n}:v]scale={fw}:{fh}:force_original_aspect_ratio=increase,crop={fw}:{fh},format=yuva420p,"
                  f"fade=t=in:st=0:d=0.6:alpha=1,fade=t=out:st=5.2:d=0.8:alpha=1,trim=duration=6,setpts=PTS-STARTPTS+{t}/TB[f{k}]")
        fc.append(f"[{last}][f{k}]overlay=x={fx}:y={fy}:enable='between(t,{t},{t + 6})':eof_action=pass[o{k}]")
        last = f"o{k}"; n += 1
    alabels = []
    for k, a in enumerate(j.get("audios", [])):
        cmd += ["-i", fetch(a["url"])]
        tr = a.get("trim", 25); st = int(a.get("start", 0) * 1000)
        fc.append(f"[{n}:a]atrim=duration={tr},afade=t=in:st=0:d=0.3,afade=t=out:st={tr - 0.6}:d=0.6,asetpts=PTS-STARTPTS,"
                  f"adelay={st}|{st}[a{k}]")
        alabels.append(f"[a{k}]"); n += 1
    maps = ["-map", f"[{last}]"]
    if alabels:
        fc.append("".join(alabels) + f"amix=inputs={len(alabels)}:duration=longest:normalize=0[aout]")
        maps += ["-map", "[aout]"]
    fname = j["name"] + ".mp4"
    cmd += ["-filter_complex", ";".join(fc)] + maps + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-t", str(j["duration"]), "-movflags", "+faststart", str(out / fname)]
    subprocess.run(cmd, check=True)
    results.append({"name": j["name"], "file": fname, "lang": j.get("lang"), "product": j.get("product"),
                    "duration": j["duration"], "bytes": (out / fname).stat().st_size})
    print("OK", fname, flush=True)

(out / "result.json").write_text(json.dumps({"tag": spec["tag"], "results": results}, ensure_ascii=False))

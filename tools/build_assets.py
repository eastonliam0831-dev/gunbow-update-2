#!/usr/bin/env python3
"""
Gun Bow asset generator.

Turns the Quaternius "Ultimate Gun Pack" OBJ models into Minecraft item models
(voxelised into cuboid elements, because vanilla item models can only be boxes),
builds the shared colour palette texture, item definitions, synthesised gun
sounds, the lang file and the generated Guns.java list.

Usage:  python3 tools/build_assets.py /path/to/Ultimate_Gun_Pack/OBJ [/path/to/sound/sources]
Needs:  numpy, scipy, pillow, ffmpeg (for .ogg)
"""
import json, math, os, subprocess, sys, tempfile
from collections import OrderedDict
import numpy as np
from scipy import ndimage
from scipy.io import wavfile
from scipy.signal import fftconvolve, butter, lfilter
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "src/main/resources/assets/gunbow")
JAVA_OUT = os.path.join(ROOT, "src/main/java/com/gunbow/Guns.java")

K = 5.5          # model units per mesh unit (keeps relative gun sizes)
VS = 0.5         # voxel size in model units
LO, HI = -16.0, 32.0
N = int((HI - LO) / VS)

# (file stem, id, display name, category)
CATS = ["Pistol", "Revolver", "SMG", "Rifle", "Bullpup", "Shotgun", "Sniper"]


def gun_list():
    g = []
    for i in range(1, 7): g.append((f"Pistol_{i}", f"pistol_{i}", f"Pistol {i}", "Pistol"))
    for i in range(1, 6): g.append((f"Revolver_{i}", f"revolver_{i}", f"Revolver {i}", "Revolver"))
    for i in range(1, 6): g.append((f"SubmachineGun_{i}", f"smg_{i}", f"Submachine Gun {i}", "SMG"))
    for i in range(1, 6): g.append((f"AssaultRifle_{i}", f"assault_rifle_{i}", f"Assault Rifle {i}", "Rifle"))
    for i in range(1, 5): g.append((f"AssaultRifle2_{i}", f"assault_rifle_2_{i}", f"Assault Rifle 2-{i}", "Rifle"))
    for i in range(1, 4): g.append((f"Bullpup_{i}", f"bullpup_{i}", f"Bullpup Rifle {i}", "Bullpup"))
    for i in range(1, 5): g.append((f"Shotgun_{i}", f"shotgun_{i}", f"Shotgun {i}", "Shotgun"))
    g.append(("Shotgun_ShortStock", "shotgun_short_stock", "Short-Stock Shotgun", "Shotgun"))
    g.append(("Shotgun_SawedOff", "shotgun_sawed_off", "Sawed-Off Shotgun", "Shotgun"))
    for i in range(1, 7): g.append((f"SniperRifle_{i}", f"sniper_rifle_{i}", f"Sniper Rifle {i}", "Sniper"))
    return g


# ---------------------------------------------------------------- OBJ / MTL
def lin2srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def load_mtl(path):
    mats, cur = {}, None
    for line in open(path):
        p = line.split()
        if not p: continue
        if p[0] == "newmtl": cur = p[1]
        elif p[0] == "Kd" and cur:
            rgb = np.clip(lin2srgb(np.array([float(x) for x in p[1:4]])) * 1.45 + 0.03, 0, 1)  # lift: MC shading darkens items
            mats[cur] = tuple(int(round(v * 255)) for v in rgb)
    return mats


def load_obj(path):
    mats = load_mtl(path[:-4] + ".mtl")
    verts, tris, cur = [], [], None
    for line in open(path):
        if line.startswith("v "): verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("usemtl"): cur = line.split()[1]
        elif line.startswith("f "):
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            col = mats.get(cur, (90, 90, 90))
            for i in range(1, len(idx) - 1): tris.append((idx[0], idx[i], idx[i + 1], col))
    return np.array(verts), tris


# ---------------------------------------------------------------- voxelise
def voxelise(verts, tris, palette):
    # mesh origin (the grip) -> model pivot (8,8,8)
    mv = 8.0 + K * verts
    occ = np.zeros((N, N, N), bool)
    col = -np.ones((N, N, N), int)
    for a, b, c, rgb in tris:
        A, B, C = mv[a], mv[b], mv[c]
        L = max(np.linalg.norm(B - A), np.linalg.norm(C - B), np.linalg.norm(A - C))
        n = max(2, int(math.ceil(L / (VS * 0.4))))
        ci = palette.setdefault(rgb, len(palette))
        uu, vv = np.meshgrid(np.arange(n + 1) / n, np.arange(n + 1) / n)
        m = (uu + vv) <= 1.0001
        u, v = uu[m][:, None], vv[m][:, None]
        pts = A + u * (B - A) + v * (C - A)
        idx = np.floor((pts - LO) / VS).astype(int)
        idx = np.clip(idx, 0, N - 1)
        occ[idx[:, 0], idx[:, 1], idx[:, 2]] = True
        col[idx[:, 0], idx[:, 1], idx[:, 2]] = ci
    lab, _ = ndimage.label(~occ)
    solid = lab != lab[0, 0, 0]
    _, (ix, iy, iz) = ndimage.distance_transform_edt(~occ, return_indices=True)
    full = np.where(solid, col[ix, iy, iz], -1)
    return full, solid


def greedy(col):
    used = np.zeros(col.shape, bool)
    boxes = []
    for x, y, z in np.argwhere(col >= 0):
        if used[x, y, z]: continue
        c = col[x, y, z]
        x2 = x
        while x2 + 1 < N and col[x2 + 1, y, z] == c and not used[x2 + 1, y, z]: x2 += 1
        y2 = y
        while y2 + 1 < N and np.all((col[x:x2 + 1, y2 + 1, z] == c) & ~used[x:x2 + 1, y2 + 1, z]): y2 += 1
        z2 = z
        while z2 + 1 < N and np.all((col[x:x2 + 1, y:y2 + 1, z2 + 1] == c) & ~used[x:x2 + 1, y:y2 + 1, z2 + 1]): z2 += 1
        used[x:x2 + 1, y:y2 + 1, z:z2 + 1] = True
        boxes.append((x, y, z, x2, y2, z2, int(c)))
    return boxes


def covered(solid, sl):
    return bool(np.all(solid[sl]))


def build_elements(col, solid):
    els = []
    for x, y, z, x2, y2, z2, c in greedy(col):
        cx, cy = c % 16, c // 16
        uv = [cx + 0.25, cy + 0.25, cx + 0.75, cy + 0.75]
        faces = {}
        def add(name, hidden):
            if not hidden: faces[name] = {"uv": uv, "texture": "#0"}
        add("east",  x2 + 1 < N and covered(solid, (x2 + 1, slice(y, y2 + 1), slice(z, z2 + 1))))
        add("west",  x - 1 >= 0 and covered(solid, (x - 1, slice(y, y2 + 1), slice(z, z2 + 1))))
        add("up",    y2 + 1 < N and covered(solid, (slice(x, x2 + 1), y2 + 1, slice(z, z2 + 1))))
        add("down",  y - 1 >= 0 and covered(solid, (slice(x, x2 + 1), y - 1, slice(z, z2 + 1))))
        add("south", z2 + 1 < N and covered(solid, (slice(x, x2 + 1), slice(y, y2 + 1), z2 + 1)))
        add("north", z - 1 >= 0 and covered(solid, (slice(x, x2 + 1), slice(y, y2 + 1), z - 1)))
        if not faces: continue
        f = lambda i: round(i * VS + LO, 3)
        els.append({"from": [f(x), f(y), f(z)], "to": [f(x2 + 1), f(y2 + 1), f(z2 + 1)], "faces": faces})
    return els


# ---------------------------------------------------------------- display
# Hold positions live here. Barrel points along model +X, top along +Y, pivot = grip.
# Rotations were derived from vanilla's item-in-hand frames (see README, "Tuning").
def display(cat, solid):
    idx = np.argwhere(solid)
    mn, mx = idx.min(0) * VS + LO, (idx.max(0) + 1) * VS + LO
    ctr = (mn + mx) / 2.0
    size = mx - mn
    gs = min(1.0, 15.0 / max(size[0], size[1]))           # gui scale
    gui_t = [round(-(ctr[0] - 8) * gs, 2), round(-(ctr[1] - 8) * gs, 2), 0]
    FP, TP = 0.5, 0.55
    def mirror(r): return [r[0], -r[1], -r[2]]
    fp_r, fp_t = [0, -90, 0], [1.0, 0.0, 1.5]
    tp_r, tp_t = [0, 90, 90], [0, 1.0, 0.5]
    d = OrderedDict()
    d["thirdperson_righthand"] = {"rotation": tp_r, "translation": tp_t, "scale": [TP] * 3}
    d["thirdperson_lefthand"] = {"rotation": mirror(tp_r), "translation": tp_t, "scale": [TP] * 3}
    d["firstperson_righthand"] = {"rotation": fp_r, "translation": fp_t, "scale": [FP] * 3}
    d["firstperson_lefthand"] = {"rotation": mirror(fp_r), "translation": fp_t, "scale": [FP] * 3}
    d["gui"] = {"rotation": [0, 0, 0], "translation": gui_t, "scale": [round(gs, 3)] * 3}
    d["ground"] = {"rotation": [0, 0, 0], "translation": [0, 2, 0], "scale": [0.3] * 3}
    d["fixed"] = {"rotation": [0, 180, 0], "translation": [round(-(ctr[0] - 8) * 0.5, 2), round(-(ctr[1] - 8) * 0.5, 2), 0],
                  "scale": [round(min(0.5, 12.0 / max(size[0], size[1])), 3)] * 3}
    d["head"] = {"rotation": [0, 180, 0], "translation": [0, 13, 7], "scale": [0.5] * 3}
    return d


# ---------------------------------------------------------------- sounds
# Real recordings supplied by the user (Freesound). Spec: category -> fire/reload source id prefix + cut window (s).
SOUND_SPEC = {
    "pistol":  {"fire": ("703342", 6.10, 8.00), "reload": ("702603", None, None)},   # S&W M&P9 Shield / pistol reload
    "revolver": {"fire": ("231248", 1.98, 3.60), "reload": ("475421", None, None)},  # S&W 686 / revolver reload
    "smg":     {"fire": ("658566", 0.07, 0.33), "reload": ("677160", None, None)},   # SMG burst (~4 rounds) / Uzi reload
    "rifle":   {"fire": ("404562", 0.00, 1.80), "reload": ("445111", None, None)},   # assault rifle / rifle mag change
    "shotgun": {"fire": ("266105", 0.50, None), "reload": ("773872", None, None)},   # shotgun / pump cock
    "sniper":  {"fire": ("855607", 0.00, None), "reload": ("855599", None, None)},   # M2010 ESR / Barrett charging handle
}
CYCLE_KINDS = {"shotgun", "sniper"}   # pump / bolt cycles automatically after each shot
CAT_TO_SOUND = {"Pistol": "pistol", "Revolver": "revolver", "SMG": "smg", "Rifle": "rifle",
                "Bullpup": "rifle", "Shotgun": "shotgun", "Sniper": "sniper"}
SR = 44100


def find_source(sound_dir, prefix):
    for fn in os.listdir(sound_dir):
        if fn.startswith(prefix):
            return os.path.join(sound_dir, fn)
    raise FileNotFoundError(f"no sound file starting with {prefix} in {sound_dir}")


def load_mono(path):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        pass
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(SR),
                    "-c:a", "pcm_s16le", tmp.name], check=True)
    sr, x = wavfile.read(tmp.name)
    os.unlink(tmp.name)
    return x.astype(np.float64) / 32768.0


def trim_quiet(x, thresh_db=-42.0, pad=0.25):
    peak = np.max(np.abs(x)) + 1e-9
    loud = np.where(np.abs(x) > peak * 10 ** (thresh_db / 20))[0]
    a = max(0, loud[0] - int(0.01 * SR))
    b = min(len(x), loud[-1] + int(pad * SR))
    return x[a:b]


def finish(x, peak):
    x = x - np.mean(x)
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
    fi, fo = int(0.003 * SR), int(0.04 * SR)
    x[:fi] *= np.linspace(0, 1, fi)
    x[-fo:] *= np.linspace(1, 0, fo)
    return (x * 32767).astype(np.int16)


def write_ogg(samples, path):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        pass
    wavfile.write(tmp.name, SR, samples)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp.name, "-c:a", "libvorbis", "-q:a", "4", path], check=True)
    os.unlink(tmp.name)


def build_sounds(sound_dir):
    for kind, spec in SOUND_SPEC.items():
        for role, (prefix, a, b) in spec.items():
            x = load_mono(find_source(sound_dir, prefix))
            if a is not None or b is not None:
                x = x[int((a or 0) * SR): int(b * SR) if b else len(x)]
                x = trim_quiet(x, pad=0.4) if b is None else x
            else:
                x = trim_quiet(x, thresh_db=-40.0, pad=0.3)
            out = finish(x, 0.95 if role == "fire" else 0.75)
            write_ogg(out, os.path.join(ASSETS, f"sounds/{role}_{kind}.ogg"))
            print(f"sound {role}_{kind}: {len(out) / SR:.2f}s")


# ---------------------------------------------------------------- preview
def render_preview(col, pal, path):
    """Isometric-ish render of the voxel gun into a 160x80 PNG for the menu."""
    solid = col >= 0
    idx = np.argwhere(solid)
    def empty(shift_axis, d):
        return ~np.roll(solid, -d, axis=shift_axis)
    up, front, side = empty(1, 1), empty(2, 1), empty(0, 1)
    P = (idx + 0.5) * VS
    P = P - (P.min(0) + P.max(0)) / 2
    yaw, pitch = math.radians(-32), math.radians(24)
    x1 = math.cos(yaw) * P[:, 0] + math.sin(yaw) * P[:, 2]
    z1 = -math.sin(yaw) * P[:, 0] + math.cos(yaw) * P[:, 2]
    y2 = math.cos(pitch) * P[:, 1] - math.sin(pitch) * z1
    z2 = math.sin(pitch) * P[:, 1] + math.cos(pitch) * z1
    ex, ey = x1.max() - x1.min() + VS, y2.max() - y2.min() + VS
    s = min(148 / ex, 72 / ey)
    img = Image.new("RGBA", (160, 80), (0, 0, 0, 0))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    size = max(1.0, s * VS * 1.45)
    cx, cy = 80 - (x1.max() + x1.min()) / 2 * s, 40 + (y2.max() + y2.min()) / 2 * s
    for i in np.argsort(z2):
        gx, gy, gz = idx[i]
        b = 0.58 + 0.27 * up[gx, gy, gz] + 0.10 * front[gx, gy, gz] + 0.05 * side[gx, gy, gz]
        r, g, bl = pal[col[gx, gy, gz]]
        c = (min(255, int(r * b)), min(255, int(g * b)), min(255, int(bl * b)), 255)
        px, py = cx + x1[i] * s, cy - y2[i] * s
        d.rectangle([px - size / 2, py - size / 2, px + size / 2, py + size / 2], fill=c)
    img.save(path)


# ---------------------------------------------------------------- main
def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    obj_dir = sys.argv[1]
    guns = gun_list()
    for sub in ("models/item", "items", "textures/item", "textures/preview", "lang"):
        os.makedirs(os.path.join(ASSETS, sub), exist_ok=True)
    os.makedirs(os.path.join(ASSETS, "sounds"), exist_ok=True)
    palette = OrderedDict()
    previews = {}
    pending_previews = []
    for stem, gid, name, cat in guns:
        verts, tris = load_obj(os.path.join(obj_dir, stem + ".obj"))
        col, solid = voxelise(verts, tris, palette)
        els = build_elements(col, solid)
        model = OrderedDict()
        model["textures"] = {"0": "gunbow:item/palette", "particle": "gunbow:item/palette"}
        model["gui_light"] = "front"
        model["elements"] = els
        model["display"] = display(cat, solid)
        with open(os.path.join(ASSETS, f"models/item/{gid}.json"), "w") as fh:
            json.dump(model, fh, separators=(",", ":"))
        with open(os.path.join(ASSETS, f"items/{gid}.json"), "w") as fh:
            json.dump({"model": {"type": "minecraft:model", "model": f"gunbow:item/{gid}"}}, fh)
        previews[gid] = (col, name)
        pending_previews.append((gid, col))
        print(f"{gid:24s} elements={len(els)}")
    assert len(palette) <= 256
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
    for rgb, i in palette.items():
        cx, cy = (i % 16) * 4, (i // 16) * 4
        img.paste(Image.new("RGBA", (4, 4), rgb + (255,)), (cx, cy))
    img.save(os.path.join(ASSETS, "textures/item/palette.png"))
    # previews (need the finished palette)
    pal = {i: rgb for rgb, i in palette.items()}
    for gid, col in pending_previews:
        render_preview(col, pal, os.path.join(ASSETS, f"textures/preview/{gid}.png"))
    # sounds
    if len(sys.argv) > 2:
        build_sounds(sys.argv[2])
    sounds = OrderedDict()
    counts = {}
    for stem, gid, name, cat in guns:
        kind = CAT_TO_SOUND[cat]
        i = counts.get(kind, 0); counts[kind] = i + 1
        pitch = round(1.0 + 0.02 * ((i % 5) - 2), 3)       # tiny per-gun variation (+-4%)
        sounds[f"shot.{gid}"] = {"sounds": [{"name": f"gunbow:fire_{kind}", "pitch": pitch}], "subtitle": "gunbow.subtitle.shot"}
        sounds[f"reload.{gid}"] = {"sounds": [{"name": f"gunbow:reload_{kind}", "pitch": pitch}], "subtitle": "gunbow.subtitle.reload"}
    with open(os.path.join(ASSETS, "sounds.json"), "w") as fh:
        json.dump(sounds, fh, indent=1)
    # lang
    lang = OrderedDict()
    lang["key.gunbow.menu"] = "Open Gun Menu"
    lang["key.category.gunbow.main"] = "Gun Bow"
    lang["gunbow.subtitle.shot"] = "Gunshot"
    lang["gunbow.subtitle.reload"] = "Reloading"
    lang["key.gunbow.reload"] = "Reload (sound)"
    lang["gunbow.menu.title"] = "Choose Your Gun"
    lang["gunbow.menu.default"] = "Vanilla Bow"
    lang["gunbow.menu.done"] = "Done"
    with open(os.path.join(ASSETS, "lang/en_us.json"), "w") as fh:
        json.dump(lang, fh, indent=1)
    # Guns.java
    rows = ",\n".join(f'        new Gun("{gid}", "{name}", "{cat}", {str(CAT_TO_SOUND[cat] in CYCLE_KINDS).lower()})' for _, gid, name, cat in guns)
    cats = ", ".join(f'"{c}"' for c in CATS)
    with open(JAVA_OUT, "w") as fh:
        fh.write(f"""package com.gunbow;

/** GENERATED by tools/build_assets.py - do not edit by hand. */
public final class Guns {{
    public record Gun(String id, String name, String category, boolean cycles) {{}}

    public static final String[] CATEGORIES = {{ {cats} }};

    public static final Gun[] ALL = {{
{rows}
    }};

    public static Gun byId(String id) {{
        for (Gun g : ALL) if (g.id().equals(id)) return g;
        return null;
    }}

    private Guns() {{}}
}}
""")
    # preview sheet
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        pal = {i: rgb for rgb, i in palette.items()}
        cols = 8; rws = math.ceil(len(previews) / cols)
        fig, axs = plt.subplots(rws, cols, figsize=(cols * 2.6, rws * 1.5))
        for ax in axs.flat: ax.axis("off")
        for ax, (gid, (col, name)) in zip(axs.flat, previews.items()):
            im = np.full((N, N, 3), 255, np.uint8)
            for z in range(N):
                lay = col[:, :, z]
                for x, y in np.argwhere(lay >= 0): im[N - 1 - y, x] = pal[lay[x, y]]
            ys, xs = np.where((im != 255).any(2))
            ax.imshow(im[ys.min():ys.max() + 1, xs.min():xs.max() + 1], interpolation="nearest")
            ax.set_title(name, fontsize=7)
        plt.tight_layout(); plt.savefig(os.path.join(ROOT, "tools/preview.png"), dpi=80)
    except Exception as e:
        print("preview skipped:", e)


if __name__ == "__main__":
    main()

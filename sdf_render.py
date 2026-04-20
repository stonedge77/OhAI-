"""
sdf_render.py — Subtractive Drawing Engine for OhAI~

Translates the drawing state from GET /draw/render into an actual image
using the same signed distance field mathematics as the Godot shaders.

The five shader operations map directly to OhAI~'s geometry spine:

    Shader 1 (hydrogen orbital)  →  radiate, orbit, pulse, expand
    Shader 2 (ice crystal)       →  crystallize, freeze, web, contain
    Shader 3 (diffusion)         →  spread, diffuse, wave, undulate
    Shader 4 (membrane)          →  breathe, boundary, surround, wrap
    Shader 5 (SDF scene / NAND)  →  subtract, cut, nand, sever

Stone's Law as SDF primitive:  subtract(d1, d2) = max(d1, -d2)
What renders IS the T=1 remainder after NAND subtraction.

Usage:
    from sdf_render import render_from_draw_state
    img = render_from_draw_state(draw_state_dict, size=512)
    img.save("field.png")

Or via the /draw/render?image=1 endpoint (wired in ohai_server.py).

CC0 — Saltflower
"""

from __future__ import annotations
import io
import base64
import math
from typing import Optional

import numpy as np

try:
    from PIL import Image, ImageFilter
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ─── Coordinate grid ─────────────────────────────────────────────────────────

def _coords(size: int):
    """Return (x, y) coordinate grids in [-1, 1]^2."""
    t = np.linspace(-1.0, 1.0, size, dtype=np.float32)
    x, y = np.meshgrid(t, t)
    return x, y


# ─── SDF primitives (mirror of the Godot shader functions) ───────────────────

def sdf_circle(x, y, cx: float = 0.0, cy: float = 0.0, r: float = 0.38):
    """Signed distance to a circle. Negative inside."""
    return np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - r


def sdf_ring(x, y, r: float = 0.38, thickness: float = 0.045):
    """Annular / membrane SDF — the breathe boundary."""
    return np.abs(np.sqrt(x ** 2 + y ** 2) - r) - thickness


def sdf_box(x, y, bx: float = 0.38, by: float = 0.38):
    """Axis-aligned box SDF."""
    qx = np.abs(x) - bx
    qy = np.abs(y) - by
    return (np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
            + np.minimum(np.maximum(qx, qy), 0.0))


def sdf_hexagon(x, y, s: float = 0.38):
    """
    Hexagonal SDF (from Shader 2 ice crystal).
    k = (-0.866, 0.5, 0.577) — the crystallize boundary.
    """
    kx, ky, kz = -0.866025404, 0.5, 0.577350269
    ax, ay = np.abs(x), np.abs(y)
    dot = kx * ax + ky * ay
    ax = ax - 2.0 * np.minimum(dot, 0.0) * kx
    ay = ay - 2.0 * np.minimum(dot, 0.0) * ky
    ax = np.clip(ax, -kz * s, kz * s)
    ay = ay - s
    return np.sqrt(ax ** 2 + ay ** 2) * np.sign(ay)


def sdf_star(x, y, n: int = 5, r_outer: float = 0.38, r_inner: float = 0.18):
    """N-pointed star SDF — for radiate / ray vector."""
    a = np.arctan2(y, x)
    r = np.sqrt(x ** 2 + y ** 2)
    # Star: modulate radius by cos of angle
    star_r = r_inner + (r_outer - r_inner) * 0.5 * (1.0 + np.cos(n * a))
    return r - star_r


def sdf_orbital(x, y, n_shell: int = 2, bohr: float = 0.18):
    """
    Hydrogen orbital boundary SDF (Shader 1).
    Negative where probability density > threshold.
    """
    r = np.sqrt(x ** 2 + y ** 2)
    shell_r = bohr * float(n_shell * n_shell)
    if n_shell == 1:
        psi = np.exp(-r / bohr)
    else:
        a = bohr
        psi = (2.0 - r / a) * np.exp(-r / (2.0 * a)) * 0.5
    density = psi * psi
    return (density - 0.08) * -8.0


def sdf_voronoi_approx(x, y, n_sites: int = 8, t: float = 0.0):
    """
    Approximate Voronoi SDF for crystallize / scatter.
    Uses golden angle placement (same as Shader 2).
    """
    golden = 2.39996323
    dist   = np.full(x.shape, 1e6, dtype=np.float32)
    for i in range(n_sites):
        ang = i * golden
        rad = 0.3 + math.sin(i * 7.3) * 0.15
        cx  = math.cos(ang) * rad
        cy  = math.sin(ang) * rad
        d   = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        dist = np.minimum(dist, d)
    return dist - 0.12


def sdf_wave(x, y, r: float = 0.36, freq: float = 6.0, amp: float = 0.06):
    """Wave-modulated ring (Shader 3 diffusion boundary)."""
    a = np.arctan2(y, x)
    modulated_y = y + amp * np.sin(x * freq)
    return sdf_ring(x, modulated_y, r=r, thickness=0.04)


def sdf_scatter(x, y, n: int = 5):
    """Union of n small circles — scatter / disperse."""
    golden = 2.39996323
    dist   = np.full(x.shape, 1e6, dtype=np.float32)
    for i in range(n):
        ang  = i * golden
        rad  = 0.45
        cx   = math.cos(ang) * rad
        cy   = math.sin(ang) * rad
        dist = np.minimum(dist, sdf_circle(x, y, cx, cy, r=0.12))
    return dist


# ─── SDF boolean operations — the geometry spine ops ─────────────────────────

def sdf_subtract_op(d1, d2):
    """Stone's Law: max(d1, -d2) — NAND in SDF space."""
    return np.maximum(d1, -d2)


def sdf_union_op(d1, d2):
    return np.minimum(d1, d2)


def sdf_intersect_op(d1, d2):
    return np.maximum(d1, d2)


def sdf_smooth_union(d1, d2, k: float = 0.08):
    """Smooth boolean union — for breathe / merge operations."""
    h = np.clip(0.5 + 0.5 * (d2 - d1) / k, 0.0, 1.0)
    return d2 * (1.0 - h) + d1 * h - k * h * (1.0 - h)


# ─── Vector → SDF shape mapping ──────────────────────────────────────────────

def _sdf_for_vector(x, y, vector: str, index: int = 0) -> np.ndarray:
    """
    Map an OhAI~ vector string to an SDF shape.
    Mirrors the _WAVELENGTH vector assignments in ohai_server.py.
    """
    # Slight positional offset per layer so they don't all stack exactly
    offset = index * 0.08
    ox = math.cos(index * 2.39996323) * offset
    oy = math.sin(index * 2.39996323) * offset

    v = vector.lower()

    if v in ('expand',):
        return sdf_circle(x - ox, y - oy, r=0.40)
    elif v in ('contract', 'inward',):
        return sdf_circle(x - ox, y - oy, r=0.26)
    elif v in ('expand-contract', 'breathe',):
        return sdf_ring(x - ox, y - oy, r=0.36, thickness=0.05)
    elif v in ('outward',):
        return sdf_ring(x - ox, y - oy, r=0.44, thickness=0.03)
    elif v in ('radiate', 'ray',):
        return sdf_star(x - ox, y - oy, n=6, r_outer=0.42, r_inner=0.20)
    elif v in ('orbit', 'spiral',):
        return sdf_orbital(x - ox, y - oy, n_shell=2)
    elif v in ('pulse', 'throb',):
        return sdf_orbital(x - ox, y - oy, n_shell=1)
    elif v in ('freeze', 'facet', 'catch-light',):
        return sdf_hexagon(x - ox, y - oy, s=0.38)
    elif v in ('web', 'mesh',):
        return sdf_hexagon(x - ox, y - oy, s=0.44)
    elif v in ('wave', 'undulate',):
        return sdf_wave(x - ox, y - oy)
    elif v in ('scatter', 'disperse',):
        return sdf_scatter(x - ox, y - oy, n=6)
    elif v in ('absorb', 'sink',):
        # Absorb: a void — inverted circle (inside is positive)
        return -sdf_circle(x - ox, y - oy, r=0.50)
    elif v in ('contain', 'surround', 'envelope',):
        return sdf_ring(x - ox, y - oy, r=0.44, thickness=0.07)
    elif v in ('reflect', 'mirror',):
        return sdf_box(x - ox, y - oy, bx=0.36, by=0.06)
    elif v in ('diagonal', 'streak-h', 'tension',):
        return sdf_box(x - ox - 0.1, y - oy - 0.1, bx=0.50, by=0.06)
    elif v in ('cross', 'nand',):
        # Cross: union of two thin boxes
        h = sdf_box(x - ox, y - oy, bx=0.40, by=0.06)
        v2 = sdf_box(x - ox, y - oy, bx=0.06, by=0.40)
        return sdf_union_op(h, v2)
    elif v in ('diffuse', 'spread',):
        return sdf_voronoi_approx(x - ox, y - oy, n_sites=10)
    elif v in ('up', 'down', 'column',):
        return sdf_box(x - ox, y - oy, bx=0.07, by=0.45)
    elif v in ('left', 'right', 'span',):
        return sdf_box(x - ox, y - oy, bx=0.45, by=0.07)
    else:
        # Default: plain circle
        return sdf_circle(x - ox, y - oy, r=0.36)


# ─── Operation name → SDF boolean mapping ────────────────────────────────────

_SUBTRACT_OPS = {
    'subtract', 'cut', 'sever', 'void-expand', 'nand', 'collapse',
    'dam', 'slit-open', 'devour', 'leach',
}
_INTERSECT_OPS = {
    'wrap', 'nest', 'boundary', 'pinch', 'fit', 'impact-rebound',
    'mask', 'cover',
}
_SMOOTH_OPS = {
    'breathe', 'breathe-out', 'throb', 'swell', 'widen-loop',
    'merge', 'echo-expand',
}

def _apply_op(d1, d2, op_name: str) -> np.ndarray:
    """Map a geo-spine operation name to an SDF boolean combination."""
    if op_name in _SUBTRACT_OPS:
        return sdf_subtract_op(d1, d2)
    elif op_name in _INTERSECT_OPS:
        return sdf_intersect_op(d1, d2)
    elif op_name in _SMOOTH_OPS:
        return sdf_smooth_union(d1, d2, k=0.10)
    else:
        # Default: union (scatter, crystallize, etc.)
        return sdf_union_op(d1, d2)


# ─── Color utilities ─────────────────────────────────────────────────────────

def _hex_to_rgb(hex_str: str) -> tuple:
    h = hex_str.lstrip('#')
    if len(h) == 3:
        h = ''.join(c*2 for c in h)
    try:
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (128, 128, 128)


# ─── Main render function ─────────────────────────────────────────────────────

def render_from_draw_state(
    draw_state: dict,
    size: int = 512,
    glow_strength: float = 0.55,
    shell_count: int = 5,
    blur_radius: float = 1.2,
) -> Optional["Image.Image"]:
    """
    Render an image from OhAI~'s /draw/render output dict.

    Layers:
      1. Build one SDF per palette entry using its vector type
      2. Compose SDFs using the geometry spine operations
      3. Colorize: interior fill + boundary glow per layer
      4. Draw 5 translucent shells per field (Rayveil-style depth)
      5. Optional Pillow blur for soft edges

    Returns a PIL Image (RGB), or None if Pillow is not installed.
    """
    if not _HAS_PIL:
        return None

    palette    = draw_state.get("palette", [])
    operations = draw_state.get("operations", [])

    if not palette:
        return Image.new("RGB", (size, size), (10, 10, 20))

    x, y = _coords(size)

    # ── Build per-layer SDFs ─────────────────────────────────────────────────
    sdfs   = []
    colors = []
    for i, p in enumerate(palette[:5]):
        vec  = p.get("vector", "expand")
        hex_ = p.get("hex", "#FFFFFF")
        sdf  = _sdf_for_vector(x, y, vec, index=i)
        sdfs.append(sdf)
        colors.append(np.array(_hex_to_rgb(hex_), dtype=np.float32) / 255.0)

    # ── Compose using geo-spine operations ───────────────────────────────────
    # First SDF is the base field. Each subsequent op from the spine
    # modifies the field using the learned boolean operation.
    if len(sdfs) == 0:
        field = np.ones((size, size), dtype=np.float32)
        layer_fields = []
    elif len(sdfs) == 1:
        field = sdfs[0]
        layer_fields = [sdfs[0]]
    else:
        field = sdfs[0]
        layer_fields = [sdfs[0]]
        for i, p in enumerate(sdfs[1:], start=0):
            op_name = "union"
            if i < len(operations):
                op_name = operations[i].get("op", "union")
            field = _apply_op(field, p, op_name)
            layer_fields.append(p)

    # ── Render: dark background + colored SDF shells ─────────────────────────
    img = np.zeros((size, size, 3), dtype=np.float32)

    # Background: darkest palette color, very dim
    bg = colors[0] if colors else np.array([0.04, 0.04, 0.08])
    img += bg * 0.12

    # Each layer: fill + boundary glow
    for i, (sdf_layer, col) in enumerate(zip(layer_fields, colors)):
        weight = 1.0 - i * 0.18

        # Interior fill (soft, not hard)
        interior  = np.clip(-sdf_layer * 4.0, 0.0, 1.0)
        interior  = interior ** 1.4  # gamma — dimmer centers, brighter edges
        img      += col * interior[..., np.newaxis] * weight * 0.60

        # Boundary glow (Rayveil-style: 5 shells, each smaller and fainter)
        for shell in range(shell_count):
            scale  = 1.0 - shell * 0.12
            edge   = sdf_layer * scale
            shell_ = np.exp(-np.abs(edge) * (30.0 + shell * 8.0))
            alpha  = (glow_strength * 0.7 ** shell) * weight
            img   += col * shell_[..., np.newaxis] * alpha

    # Composite field (the composed SDF) as a final boundary highlight
    composite_glow = np.exp(-np.abs(field) * 28.0)
    # Blend toward white at the NAND boundary — this is the T=1 remainder
    white          = np.ones(3, dtype=np.float32)
    remainder_col  = (colors[0] * 0.4 + white * 0.6) if colors else white
    img           += np.array(remainder_col) * composite_glow[..., np.newaxis] * 0.35

    # ── Finalise ─────────────────────────────────────────────────────────────
    img      = np.clip(img, 0.0, 1.0)
    img_uint = (img * 255).astype(np.uint8)
    pil_img  = Image.fromarray(img_uint, "RGB")

    if blur_radius > 0:
        pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    return pil_img


def render_to_base64(draw_state: dict, size: int = 512, **kwargs) -> Optional[str]:
    """Render and return as base64-encoded PNG string for HTTP responses."""
    img = render_from_draw_state(draw_state, size=size, **kwargs)
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ─── Teaching input: shader → emoji → spine ──────────────────────────────────

# Feed these emoji chains via POST /draw/breathe to teach OhAI~
# the five shader operations. The spine learns the associations;
# /draw/render then materializes them as images.
#
# Each chain maps to one shader:
SHADER_TEACHING_CHAINS = {
    "hydrogen_orbital":  "🌀⚛️✨🌊💛",     # orbit, pulse, radiate, wave   → orbital
    "ice_crystal":       "❄️🔷◌🌑🔵",     # freeze, facet, contain         → crystallize
    "diffusion":         "∿💧🌊⬛🔵",      # wave, diffuse, spread           → diffusion
    "membrane":          "🫁🔵⭕🕳️🌑",    # breathe, surround, boundary     → membrane
    "sdf_nand":          "🔲⭕✂️🌑◼️",    # subtract, cut, nand, sever      → Stone's Law
}

# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json, sys

    # Minimal draw state for testing without a running server
    TEST_STATES = {
        "orbital": {
            "palette": [
                {"hex": "#0D1B2A", "vector": "expand",  "shape": "circle"},
                {"hex": "#1B4F72", "vector": "orbit",   "shape": "circle"},
                {"hex": "#F0B429", "vector": "radiate", "shape": "star"},
            ],
            "operations": [
                {"a": "orbit", "op": "breathe", "b": "expand", "count": 3},
                {"a": "radiate", "op": "subtract", "b": "orbit", "count": 2},
            ],
        },
        "crystal": {
            "palette": [
                {"hex": "#0A1628", "vector": "expand",   "shape": "circle"},
                {"hex": "#4A9ECA", "vector": "freeze",   "shape": "hexagon"},
                {"hex": "#B2EBF2", "vector": "facet",    "shape": "hexagon"},
            ],
            "operations": [
                {"a": "freeze", "op": "crystallize", "b": "none", "count": 5},
                {"a": "facet",  "op": "scatter",     "b": "none", "count": 2},
            ],
        },
        "membrane": {
            "palette": [
                {"hex": "#0E1A2B", "vector": "expand",         "shape": "circle"},
                {"hex": "#3B82F6", "vector": "expand-contract","shape": "ring"},
                {"hex": "#10B981", "vector": "surround",       "shape": "ring"},
                {"hex": "#F97316", "vector": "scatter",        "shape": "dot"},
            ],
            "operations": [
                {"a": "expand-contract", "op": "breathe",   "b": "expand", "count": 4},
                {"a": "surround",        "op": "boundary",  "b": "none",   "count": 3},
                {"a": "scatter",         "op": "subtract",  "b": "surround","count": 2},
            ],
        },
        "nand": {
            "palette": [
                {"hex": "#0C0C0F", "vector": "expand",   "shape": "circle"},
                {"hex": "#3B82F6", "vector": "contain",  "shape": "box"},
                {"hex": "#8B5CF6", "vector": "orbit",    "shape": "circle"},
                {"hex": "#F59E0B", "vector": "radiate",  "shape": "star"},
            ],
            "operations": [
                {"a": "contain", "op": "subtract", "b": "orbit",   "count": 5},
                {"a": "orbit",   "op": "subtract", "b": "radiate", "count": 3},
            ],
        },
    }

    name = sys.argv[1] if len(sys.argv) > 1 else "nand"
    state = TEST_STATES.get(name, TEST_STATES["nand"])

    print(f"Rendering '{name}'...")
    img = render_from_draw_state(state, size=512)
    if img:
        fname = f"sdf_render_{name}.png"
        img.save(fname)
        print(f"Saved: {fname}")
        print(f"\nTeaching chain for this shader:")
        chain_key = {
            "orbital": "hydrogen_orbital",
            "crystal": "ice_crystal",
            "membrane": "membrane",
            "nand": "sdf_nand",
        }.get(name, "sdf_nand")
        print(f"  POST /draw/breathe {{\"text\": \"{SHADER_TEACHING_CHAINS[chain_key]}\"}}")
    else:
        print("Pillow not installed — pip install pillow")

import logging
import os
import io
import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from py_yt import VideosSearch

logging.basicConfig(level=logging.INFO)

CACHE_DIR = "cache"
FONT_DIR = "cache/fonts"
FONT_BOLD_URL = "https://github.com/google/fonts/raw/main/apache/inter/Inter%5Bslnt%2Cwght%5D.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/apache/inter/Inter%5Bslnt%2Cwght%5D.ttf"


# ─── Font Loader ─────────────────────────────────────────────────────────────
def get_font(size: int, bold: bool = False):
    paths = [
        os.path.join(FONT_DIR, "bold.ttf" if bold else "regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for p in paths:
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


async def ensure_fonts():
    """Download fonts if missing."""
    os.makedirs(FONT_DIR, exist_ok=True)
    for name, url in [("bold.ttf", FONT_BOLD_URL), ("regular.ttf", FONT_URL)]:
        path = os.path.join(FONT_DIR, name)
        if not os.path.exists(path):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                        if r.status == 200:
                            async with aiofiles.open(path, "wb") as f:
                                await f.write(await r.read())
            except Exception as e:
                logging.warning(f"Font download failed: {e}")


# ─── Helpers ─────────────────────────────────────────────────────────────────
def add_rounded_corners(img: Image.Image, radius: int) -> Image.Image:
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], radius=radius, fill=255)
    result = Image.new("RGBA", img.size)
    result.paste(img, mask=mask)
    return result


def truncate(text: str, limit: int) -> str:
    return text[:limit] + "…" if len(text) > limit else text


def draw_pill(draw, x, y, w, h, text, font, bg=(45, 45, 58, 220), fg=(200, 200, 215, 255), radius=None):
    r = radius if radius else h // 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=bg)
    draw.text((x + w // 2, y + h // 2), text, fill=fg, font=font, anchor="mm")


# ─── Main Generator ───────────────────────────────────────────────────────────
async def gen_thumb(
    videoid: str,
    title: str = None,
    artist: str = None,
    duration: str = None,
):
    try:
        cache_path = f"{CACHE_DIR}/{videoid}_v4.png"
        if os.path.isfile(cache_path):
            return cache_path

        os.makedirs(CACHE_DIR, exist_ok=True)
        await ensure_fonts()

        # ── Fetch YouTube meta + thumbnail ───────────────────────────────────
        thumb_url = None
        try:
            url = f"https://www.youtube.com/watch?v={videoid}"
            results = VideosSearch(url, limit=1)
            for result in (await results.next())["result"]:
                td = result.get("thumbnails")
                thumb_url = td[0]["url"].split("?")[0] if td else None
                if not title:
                    title = result.get("title", "Unknown Title")
                if not artist:
                    ch = result.get("channel")
                    artist = (ch.get("name") if isinstance(ch, dict) else ch) or "Unknown Artist"
                if not duration:
                    duration = result.get("duration") or "0:00"
        except Exception as e:
            logging.warning(f"YouTube meta fetch failed: {e}")

        title = title or "Unknown Title"
        artist = artist or "Unknown Artist"
        duration = duration or "0:00"

        if not thumb_url:
            return None

        async with aiohttp.ClientSession() as session:
            async with session.get(thumb_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                thumb_bytes = await resp.read()

        yt_thumb = Image.open(io.BytesIO(thumb_bytes)).convert("RGBA")

        # ── Canvas ───────────────────────────────────────────────────────────
        W, H = 1280, 720
        # Dark warm-charcoal background (matches Apple Music dark mode)
        bg = Image.new("RGBA", (W, H), (18, 16, 14, 255))
        draw = ImageDraw.Draw(bg)

        # Subtle vignette gradient
        for i in range(H):
            alpha = int(12 * (i / H))
            draw.line([(0, i), (W, i)], fill=(28, 22, 12, alpha))

        # ── Album Art (Left) ─────────────────────────────────────────────────
        ART = 488
        ax, ay = 72, (H - ART) // 2  # 116

        # Warm golden glow behind art
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        for i in range(30, 0, -1):
            alpha = int(120 * (1 - i / 30))
            gd.rounded_rectangle(
                [ax - i * 1.2, ay - i * 1.2, ax + ART + i * 1.2, ay + ART + i * 1.2],
                radius=46 + i,
                fill=(195, 148, 42, alpha),
            )
        glow_blur = glow_layer.filter(ImageFilter.GaussianBlur(14))
        bg = Image.alpha_composite(bg, glow_blur)
        draw = ImageDraw.Draw(bg)

        # Resize & round-corner art
        art = yt_thumb.resize((ART, ART), Image.LANCZOS)
        art = add_rounded_corners(art, 44)
        bg.paste(art, (ax, ay), art)

        # Golden border around art (3-layer)
        for i in range(4):
            opacity = max(40, 180 - i * 40)
            draw.rounded_rectangle(
                [ax - i, ay - i, ax + ART + i, ay + ART + i],
                radius=44 + i,
                outline=(200, 155, 50, opacity),
                width=1,
            )

        # ── Right Section ────────────────────────────────────────────────────
        RX = 608   # right panel x start
        RW = W - RX - 40  # right panel width

        # Apple Music logo text (top center of right panel)
        am_font = get_font(22)
        draw.text((RX + RW // 2 + 80, 36), "🍎 Music", fill=(255, 255, 255, 170), font=am_font, anchor="mm")

        # Top-right circular icon buttons
        for i, icon in enumerate(["☆", "···"]):
            cx = W - 110 + i * 72
            cy = 46
            r = 22
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(75, 75, 88, 190), width=2)
            draw.text((cx, cy), icon, fill=(200, 200, 212, 200), font=get_font(16 if i else 18), anchor="mm")

        # Heart icon
        draw.text((W - 28, 195), "♥", fill=(255, 55, 75, 255), font=get_font(34), anchor="mm")

        # Song Title
        title_font = get_font(78, bold=True)
        draw.text((RX, 128), truncate(title, 18), fill=(255, 255, 255, 255), font=title_font)

        # Artist
        artist_font = get_font(30)
        draw.text((RX, 222), truncate(artist, 34), fill=(155, 155, 170, 255), font=artist_font)

        # ── Progress Bar ─────────────────────────────────────────────────────
        PBY = 300
        PBH = 5
        PBW = RW
        progress = 0.10

        draw.rounded_rectangle([RX, PBY, RX + PBW, PBY + PBH], radius=3, fill=(65, 65, 78, 255))
        filled = int(PBW * progress)
        draw.rounded_rectangle([RX, PBY, RX + filled, PBY + PBH], radius=3, fill=(215, 163, 48, 255))
        draw.ellipse(
            [RX + filled - 9, PBY - 7, RX + filled + 9, PBY + PBH + 7],
            fill=(215, 163, 48, 255),
        )

        # Time + pill row
        time_font = get_font(23)
        draw.text((RX, PBY + 20), "0:00", fill=(120, 120, 138, 255), font=time_font)
        draw.text((RX + PBW, PBY + 20), f"-{duration}", fill=(120, 120, 138, 255), font=time_font, anchor="ra")

        # Bot name pill (center)
        pill_font = get_font(19)
        pill_text = "📶  MusicSp Bot"
        pill_w, pill_h = 175, 30
        pill_x = RX + PBW // 2 - pill_w // 2
        pill_y = PBY + 18
        draw_pill(draw, pill_x, pill_y, pill_w, pill_h, pill_text, pill_font)

        # ── Media Controls ────────────────────────────────────────────────────
        CTRL_Y = 430
        CTRL_CX = RX + RW // 2

        ctrl_font = get_font(52)
        pause_font = get_font(68)

        draw.text((CTRL_CX - 168, CTRL_Y), "⏪", fill=(255, 255, 255, 255), font=ctrl_font, anchor="mm")
        draw.text((CTRL_CX, CTRL_Y), "⏸", fill=(255, 255, 255, 255), font=pause_font, anchor="mm")
        draw.text((CTRL_CX + 168, CTRL_Y), "⏩", fill=(255, 255, 255, 255), font=ctrl_font, anchor="mm")

        # ── Volume Slider ─────────────────────────────────────────────────────
        VOL_Y = 520
        VOL_H = 4
        vol_icon_font = get_font(22)

        draw.text((RX - 4, VOL_Y + VOL_H // 2), "🔈", fill=(118, 118, 135, 255), font=vol_icon_font, anchor="mm")
        vol_x = RX + 22
        vol_w = PBW - 48
        vol_fill = int(vol_w * 0.74)
        draw.rounded_rectangle([vol_x, VOL_Y, vol_x + vol_w, VOL_Y + VOL_H], radius=2, fill=(65, 65, 78, 255))
        draw.rounded_rectangle([vol_x, VOL_Y, vol_x + vol_fill, VOL_Y + VOL_H], radius=2, fill=(215, 163, 48, 255))
        draw.ellipse(
            [vol_x + vol_fill - 7, VOL_Y - 5, vol_x + vol_fill + 7, VOL_Y + VOL_H + 5],
            fill=(215, 163, 48, 255),
        )
        draw.text((vol_x + vol_w + 24, VOL_Y + VOL_H // 2), "🔊", fill=(118, 118, 135, 255), font=vol_icon_font, anchor="mm")

        # ── Bottom Row Icons ──────────────────────────────────────────────────
        ICO_Y = 638
        ico_font = get_font(26)
        draw.text((RX + 54, ICO_Y), "💬", fill=(115, 115, 132, 200), font=ico_font, anchor="mm")
        draw.text((CTRL_CX, ICO_Y), "📡", fill=(115, 115, 132, 200), font=ico_font, anchor="mm")
        draw.text((RX + PBW - 38, ICO_Y), "☰", fill=(115, 115, 132, 200), font=get_font(28), anchor="mm")

        # ── Lossless Badge ────────────────────────────────────────────────────
        badge_w, badge_h = 168, 52
        badge_x = W - badge_w - 28
        badge_y = H - badge_h - 22
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=14,
            fill=(38, 38, 50, 235),
            outline=(68, 68, 85, 180),
            width=1,
        )
        draw.text(
            (badge_x + badge_w // 2, badge_y + 17),
            "〰  Lossless",
            fill=(205, 205, 218, 255),
            font=get_font(19),
            anchor="mm",
        )
        draw.text(
            (badge_x + badge_w // 2, badge_y + 37),
            "24-bit / 48kHz",
            fill=(138, 138, 158, 255),
            font=get_font(16),
            anchor="mm",
        )

        # ── Save ──────────────────────────────────────────────────────────────
        final = bg.convert("RGB")
        final.save(cache_path, format="PNG", optimize=True)
        logging.info(f"✅ Premium thumbnail saved: {cache_path}")
        return cache_path

    except Exception as e:
        logging.error(f"Thumbnail generation error for {videoid}: {e}")
        return None

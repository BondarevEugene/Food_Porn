import os
import sys
import asyncio
import aiohttp
from io import BytesIO

import replicate
import requests
from PIL import Image, ImageDraw, ImageFilter

# 1. Токен авторизації Replicate беспечно підтягується з середовища
replicate_token = os.getenv("REPLICATE_API_TOKEN")

# Посилання на референс обличчя через змінні середовища або дефолтний публічний приклад
FACE_REFERENCE_URL = os.getenv("FACE_REFERENCE_URL", "https://images.unsplash.com/photo-1534528741775-53994a69daeb")

config = {
    "project": "Seamless Luxury Vision Board Collage",
    "canvas": {
        "base_resolution": {"width": 1080, "height": 1920},
        "style": "photorealistic seamless double-exposure composite, soft ethereal blending, light leaks, warm bokeh particles, gold aura glow",
        "color_palette": {"tone": "warm golden amber, luxury aesthetic"}
    },
    "character_profile": {
        "hair": "Long dark brown straight hair",
        "style": "Elegant, luxury, polished look"
    },
    "central_element": {
        "id": "central_portrait",
        "layout": {"x_center": 540, "y_center": 900, "width": 640, "height": 850, "feather_radius": 100},
        "prompt": "Close-up front-facing portrait, warm inviting smile, white sparkling top, thin gold necklace, soft golden lighting"
    },
    "theme_sections": [
        {"id": "love_and_care",
         "layout": {"x_center": 270, "y_center": 240, "width": 560, "height": 500, "feather_radius": 80},
         "prompt": "in a romantic embrace with her partner, receiving a large bouquet of white roses, orange luxury gift boxes"},
        {"id": "health_and_fitness",
         "layout": {"x_center": 810, "y_center": 240, "width": 560, "height": 500, "feather_radius": 80},
         "prompt": "taking a gym mirror selfie in beige matching workout wear, showing fit body figure"},
        {"id": "maldives_travel",
         "layout": {"x_center": 240, "y_center": 680, "width": 500, "height": 520, "feather_radius": 95},
         "prompt": "walking hand-in-hand with her husband on a tropical Maldives resort beach with overwater bungalows"},
        {"id": "business_goal",
         "layout": {"x_center": 810, "y_center": 1200, "width": 560, "height": 500, "feather_radius": 80},
         "prompt": "in a beige elegant suit jacket working on a laptop at a modern desk, background shows subtle financial chart"}
    ]
}


async def wait_with_progress(seconds):
    """Асинхронне очікування без блокування event loop"""
    for i in range(seconds, 0, -1):
        sys.stdout.write(f"\r   [БЛОКУВАННЯ] Очікування лімітів сервера ШІ... Залишилось: {i} сек. ")
        sys.stdout.flush()
        await asyncio.sleep(1)
    sys.stdout.write("\r   [СИСТЕМА] Сервер готовий до наступного запиту!                      \n")
    sys.stdout.flush()


def create_feather_mask(width, height, feather_radius):
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    pad = max(10, feather_radius // 2)
    draw.ellipse([pad, pad, width - pad, height - pad], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(feather_radius))


def generate_ai_image(prompt_text, width, height):
    """Генерація з первинною обробкою помилок без падіння скрипту."""
    try:
        output = replicate.run(
            "bytedance/flux-pulid",
            input={
                "prompt": prompt_text,
                "main_face_image": FACE_REFERENCE_URL,
                "width": width,
                "height": height,
                "num_steps": 20,
                "guidance_scale": 4.0
            }
        )
        img_url = output[0] if isinstance(output, list) else output
        response = requests.get(img_url)
        return Image.open(BytesIO(response.content)).convert("RGBA")
    except Exception as e:
        print(f"\n   ⚠️ [Увага!] Не вдалося отримати ШІ-картинку. Причина: {e}")
        print("   [Зшивання] Застосовано резервний золотий luxury-градієнт для збереження структури колажу.")
        return Image.new("RGBA", (width, height), "#D4AF37")


async def build_final_vision_board():
    w = config["canvas"]["base_resolution"]["width"]
    h = config["canvas"]["base_resolution"]["height"]
    canvas_img = Image.new("RGBA", (w, h), "#2C1E14")

    style_suffix = f", {config['canvas']['style']}, {config['canvas']['color_palette']['tone']}"
    char_desc = f"A gorgeous woman with {config['character_profile']['hair']}, {config['character_profile']['style']}"

    print("=" * 70)
    print("📢 УВАГА КЛІЄНТУ: Запущено процес генерації преміум-коллажу.")
    print("⏳ Кожен блок потребує близько 1 хвилини на обробку.")
    print("=" * 70)
    print("🚀 Старт генерації...")

    for i, node in enumerate(config["theme_sections"]):
        if i > 0:
            await wait_with_progress(45)

        print(f"📸 [AI] Генерація фото для блоку: '{node['id']}'...")
        lay = node["layout"]
        full_prompt = f"{char_desc} {node['prompt']}{style_suffix}"

        layer_img = await asyncio.to_thread(generate_ai_image, full_prompt, lay["width"], lay["height"])
        mask = create_feather_mask(lay["width"], lay["height"], lay["feather_radius"])

        x = lay["x_center"] - (lay["width"] // 2)
        y = lay["y_center"] - (lay["height"] // 2)

        temp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        temp.paste(layer_img, (x, y), mask)
        canvas_img = Image.alpha_composite(canvas_img, temp)
        print(f"   [+] Блок {node['id']} успішно інтегровано в макет.\n")

    await wait_with_progress(45)

    print("👑 [AI] Генерація Головного Центрального Портрета...")
    c_element = config["central_element"]
    c_lay = c_element["layout"]
    central_prompt = f"{c_element['prompt']}. Featuring {char_desc}{style_suffix}"

    central_img = await asyncio.to_thread(generate_ai_image, central_prompt, c_lay["width"], c_lay["height"])
    c_mask = create_feather_mask(c_lay["width"], c_lay["height"], c_lay["feather_radius"])

    cx = c_lay["x_center"] - (c_lay["width"] // 2)
    cy = c_lay["y_center"] - (c_lay["height"] // 2)

    temp_c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    temp_c.paste(central_img, (cx, cy), c_mask)
    canvas_img = Image.alpha_composite(canvas_img, temp_c)
    print("   [+] Центральний портрет успішно накладено поверх шарів.")

    output_filename = "final_luxury_vision_board.png"
    canvas_img.convert("RGB").save(output_filename, "PNG")
    print("=" * 70)
    print("🎉 [УСПІХ] Процес завершено!")
    print(f"💾 Результат збережено за шляхом: {os.path.abspath(output_filename)}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(build_final_vision_board())
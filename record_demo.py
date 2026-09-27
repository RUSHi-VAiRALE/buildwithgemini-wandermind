import asyncio
import os
import shutil
import subprocess
from playwright.async_api import async_playwright

ARTIFACT_DIR = "/config/.gemini/antigravity/brain/85fe71a8-c892-40c9-a956-39bfb3218b7f"
VIDEO_TEMP_DIR = "/config/Desktop/Session1/wandermind/temp_video"

async def record_demo():
    os.makedirs(VIDEO_TEMP_DIR, exist_ok=True)
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=VIDEO_TEMP_DIR,
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        print("1. Navigating to Wandermind Frontend...")
        await page.goto("http://localhost:8080", wait_until="networkidle")
        await asyncio.sleep(3.0)

        # Prompt 1: Show main feature (Firestore travel destination search)
        prompt1 = "What are the top travel destinations in Kyoto for nature and culture?"
        print(f"2. Typing Prompt 1: '{prompt1}'...")
        input_el = page.locator("#input")
        await input_el.focus()
        await page.keyboard.type(prompt1, delay=40)
        await asyncio.sleep(1.0)
        
        print("Sending Prompt 1...")
        await page.locator("#form button[type='submit']").click()
        
        # Wait for agent response 1
        print("Waiting for Prompt 1 response...")
        await page.wait_for_selector(".typing-indicator", state="detached", timeout=60000)
        await asyncio.sleep(4.0)

        # Smooth scroll down to view results
        await page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
        await asyncio.sleep(3.0)

        # Prompt 2: Richer prompt (Live Weather + Postcard Image Generation)
        prompt2 = "Can you check the live weather in Kyoto and generate a scenic postcard of Kyoto Bamboo Forest?"
        print(f"3. Typing Prompt 2: '{prompt2}'...")
        await input_el.focus()
        await page.keyboard.type(prompt2, delay=40)
        await asyncio.sleep(1.0)
        
        print("Sending Prompt 2...")
        await page.locator("#form button[type='submit']").click()

        # Wait for agent response 2 (weather + image generation)
        print("Waiting for Prompt 2 response (weather & postcard generation)...")
        await page.wait_for_selector(".typing-indicator", state="detached", timeout=90000)
        await asyncio.sleep(6.0)

        # Scroll down smoothly to show the generated postcard image and weather card
        await page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
        await asyncio.sleep(6.0)

        print("Closing browser context to finalize video recording...")
        video_path = await page.video.path()
        await context.close()
        await browser.close()

        print(f"Raw recorded video saved to: {video_path}")

        # Copy raw video to artifact directory
        target_webm = os.path.join(ARTIFACT_DIR, "wandermind_demo.webm")
        target_mp4 = os.path.join(ARTIFACT_DIR, "wandermind_demo.mp4")
        shutil.copy(video_path, target_webm)
        print(f"Copied webm demo video to artifact directory: {target_webm}")

        # Convert to mp4 using ffmpeg if available
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            try:
                cmd = [ffmpeg_bin, "-y", "-i", target_webm, "-c:v", "libx264", "-pix_fmt", "yuv420p", target_mp4]
                subprocess.run(cmd, check=True)
                print(f"Converted demo video to mp4: {target_mp4}")
            except Exception as e:
                print(f"ffmpeg conversion note: {e}")
        else:
            shutil.copy(target_webm, target_mp4)

if __name__ == "__main__":
    asyncio.run(record_demo())

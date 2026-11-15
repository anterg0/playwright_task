import random
import time
import os
import json
from playwright.sync_api import sync_playwright

PATH_TO_VIDEO_FOLDER = "./video"

def move_and_click(page, locator, steps=60, duration=0.7):
    box = locator.bounding_box()

    target_x = box["x"] + box["width"] / 2
    target_y = box["y"] + box["height"] / 2

    start_x, start_y = page.evaluate(
        "() => [window.mouseX, window.mouseY]"
    )

    for i in range(1, steps + 1):
        t = i / steps
        progress = 1 - (1 - t) ** 3

        x = start_x + (target_x - start_x) * progress
        y = start_y + (target_y - start_y) * progress

        page.mouse.move(x, y)
        time.sleep(duration / steps)

    page.mouse.click(target_x, target_y)

def inject_cursor(page):
    page.add_init_script("""
        (() => {
            let zoomActive = false;

            window.mouseX = 0;
            window.mouseY = 0;

            function showZoomRing(x, y, type) {
                if (!document.body) return;

                const ring = document.createElement('div');
                ring.id = 'custom-ring';
                const color = type === 'in' ? '#00d26a' : '#ff4d4d';

                ring.style.cssText = `
                    position: fixed;
                    left: ${x}px;
                    top: ${y}px;
                    width: 54px;
                    height: 54px;
                    border: 3px solid ${color};
                    border-radius: 50%;
                    transform: translate(-50%, -50%) scale(0.7);
                    opacity: 1;
                    pointer-events: none;
                    z-index: 1000000;
                    box-shadow: 0 0 12px ${color};
                    transition: transform 0.5s ease-out, opacity 0.5s ease-out;
                `;

                document.body.appendChild(ring);

                requestAnimationFrame(() => {
                    ring.style.transform = 'translate(-50%, -50%) scale(1.4)';
                    ring.style.opacity = '0';
                });

                setTimeout(() => ring.remove(), 550);
            }

            window.__zoomAt = async (x, y) => {
                x = Number.isFinite(x) ? x : window.mouseX;
                y = Number.isFinite(y) ? y : window.mouseY;

                const type = zoomActive ? 'out' : 'in';
                zoomActive = !zoomActive;

                if (window.__recordZoomEvent) {
                    await window.__recordZoomEvent({ x, y, type });
                }

                if (document.body) {
                    showZoomRing(x, y, type);
                } else {
                    document.addEventListener('DOMContentLoaded', () => {
                        showZoomRing(x, y, type);
                    }, { once: true });
                }

                return type;
            };

            document.addEventListener("keydown", async (event) => {
                if (event.key === "F5") {
                    event.preventDefault();
                    event.stopPropagation();

                    await window.__zoomAt(window.mouseX, window.mouseY);
                }
            }, true);

            document.addEventListener('mousemove', (event) => {
                window.mouseX = event.clientX;
                window.mouseY = event.clientY;

                const cursor = document.getElementById('custom-cursor');
                const ring = document.getElementById('custom-ring');

                if (cursor) {
                    cursor.style.left = event.clientX + 'px';
                    cursor.style.top = event.clientY + 'px';
                }
                if (ring) {
                    ring.style.left = event.clientX + 'px';
                    ring.style.top = event.clientY + 'px';
                }
            });

            document.addEventListener('DOMContentLoaded', () => {
                const cursor = document.createElement('div');
                cursor.id = 'custom-cursor';

                cursor.innerHTML = `
                    <div class="cursor-halo"></div>
                    <svg width="32" height="40" viewBox="0 0 32 40"
                        xmlns="http://www.w3.org/2000/svg">
                        <path
                            d="M4 2 L4 30 L11 23 L17 36 L23 33 L17 20 L27 20 Z"
                            fill="white"
                            stroke="#222"
                            stroke-width="2"
                            stroke-linejoin="round"
                        />
                    </svg>
                `;

                const style = document.createElement('style');
                style.textContent = `
                    #custom-cursor {
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 0;
                        height: 0;
                        pointer-events: none;
                        z-index: 999999;
                    }

                    .cursor-halo {
                        position: absolute;
                        width: 40px;
                        height: 40px;
                        left: 0;
                        top: 0;
                        transform: translate(-50%, -50%);
                        background: rgba(255, 204, 0, 0.35);
                        border: 1px solid rgba(255, 204, 0, 0.8);
                        border-radius: 50%;
                    }

                    #custom-cursor svg {
                        position: absolute;
                        width: 32px;
                        height: 32px;
                        left: 0;
                        top: 0;
                        transform: translate(-7px, -3px);
                    }
                `;

                document.head.appendChild(style);
                document.body.appendChild(cursor);

                document.addEventListener('mousedown', (event) => {
                    const ripple = document.createElement('div');

                    ripple.style.cssText = `
                        position: fixed;
                        left: ${event.clientX}px;
                        top: ${event.clientY}px;
                        width: 20px;
                        height: 20px;
                        border: 2px solid #ffcc00;
                        border-radius: 50%;
                        pointer-events: none;
                        z-index: 999998;
                        transform: translate(-50%, -50%);
                    `;

                    document.body.appendChild(ripple);

                    const animation = ripple.animate([
                        {
                            transform: 'translate(-50%, -50%) scale(0.5)',
                            opacity: 1
                        },
                        {
                            transform: 'translate(-50%, -50%) scale(3)',
                            opacity: 0
                        }
                    ], {
                        duration: 500,
                        easing: 'ease-out'
                    });

                    animation.onfinish = () => ripple.remove();
                });

                document.addEventListener('submit', () => {
                    const target = document.elementFromPoint(
                        window.mouseX,
                        window.mouseY
                    );

                    const button = target?.closest('button');

                    if (button) {
                        document.dispatchEvent(new MouseEvent('mousedown', {
                            bubbles: true,
                            clientX: window.mouseX,
                            clientY: window.mouseY
                        }));
                    }
                }, true);
            });
        })();
    """)

def ShowCallout(page, text, bgColor="#FFFF00", textColor="#000000", fade=True):
    page.evaluate("""({text, bgColor, textColor, fade}) => {
        const box = document.createElement("div");
        box.id = "playwright-callout";
        box.textContent = text;

        Object.assign(box.style, {
            position: "fixed",
            top: "30px",
            left: "50%",
            transform: "translateX(-50%)",
            padding: "12px 20px",
            background: bgColor,
            color: textColor,
            font: "16pt Arial",
            width: "fit-content",
            zIndex: "999999",
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
            opacity: fade ? "0" : "1",
            transition: fade ? "opacity 2s" : "none"
        });

        document.body.appendChild(box);

        if (fade) requestAnimationFrame(() => box.style.opacity = "1");

        setTimeout(() => {
            if (fade) box.style.opacity = "0";
            setTimeout(() => box.remove(), fade ? 2000 : 0);
        }, 3000);
    }""", {
        "text": text,
        "bgColor": bgColor,
        "textColor": textColor,
        "fade": fade
    })

    page.wait_for_function(
        "() => !document.getElementById('playwright-callout')"
    )

def CaptureVideo_Magento(url, company_name, language, country, postcode, city, street, house_no):
    browser = None
    context = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)

            os.makedirs(PATH_TO_VIDEO_FOLDER, exist_ok=True)

            output_path = os.path.abspath(
                f"{PATH_TO_VIDEO_FOLDER}/{company_name}.webm"
            )
            sidecar_path = f"{output_path}.zoom.json"

            if os.path.exists(sidecar_path):
                os.remove(sidecar_path)

            recording_started_at = time.monotonic()
            zoom_events = []

            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                record_video_dir=PATH_TO_VIDEO_FOLDER,
                record_video_size={"width": 1280, "height": 720}
            )

            page = context.new_page()
            video = page.video

            def record_zoom_event(source, event):
                zoom_events.append({
                    "t": round(time.monotonic() - recording_started_at, 3),
                    "x": round(float(event["x"]), 2),
                    "y": round(float(event["y"]), 2),
                    "type": event["type"]
                })

            page.expose_binding("__recordZoomEvent", record_zoom_event)
            inject_cursor(page)

            page.goto(url)

            ShowCallout(page, "Hello World!")

            move_and_click(page, page.locator('textarea[name="q"]'), steps=100)

            # page.evaluate("window.__zoomAt(window.mouseX, window.mouseY)")

            text = "Magento developer in " + city

            for char in text:
                page.keyboard.type(char)
                time.sleep(random.uniform(0.1, 0.25))

            # page.evaluate("window.__zoomAt(window.mouseX, window.mouseY)")

            move_and_click(
                page,
                page.locator('form button[type="submit"]:visible'),
                steps=60
            )

            page.locator('a[data-testid="result-title-a"]').first.wait_for(
                state="visible",
                timeout=15000
            )

            move_and_click(
                page,
                page.locator('a[data-testid="result-title-a"]').first,
                steps=60
            )

            time.sleep(3)

            context.close()
            context = None

            output_path = os.path.abspath(
                f"{PATH_TO_VIDEO_FOLDER}/{company_name}.webm"
            )

            video.save_as(output_path)
            video.delete()

            if zoom_events:
                sidecar_path = f"{output_path}.zoom.json"

                with open(sidecar_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "viewport": {
                            "width": 1280,
                            "height": 720
                        },
                        "fps": 25,
                        "zoom_factor": 2.0,
                        "ramp_sec": 0.5,
                        "events": zoom_events
                    }, f, indent=4)

            browser.close()
            browser = None

            return output_path

    except Exception as e:
        print(f"Recording failed: {e}")
        return None

    finally:
        if context is not None:
            context.close()

        if browser is not None:
            browser.close()

import random
import time
from playwright.sync_api import Page

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
        document.addEventListener('DOMContentLoaded', () => {
            const cursor = document.createElement('div');
            cursor.id = 'custom-cursor';

            let enterPressed = false;
            window.mouseX = 0;
            window.mouseY = 0;

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

            document.addEventListener('mousemove', (event) => {
                window.mouseX = event.clientX;
                window.mouseY = event.clientY;

                cursor.style.left = event.clientX + 'px';
                cursor.style.top = event.clientY + 'px';
            });

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
            document.addEventListener('submit', (event) => {
                const target = document.elementFromPoint(window.mouseX, window.mouseY);
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
    """)

def CaptureVideo_Magento(url, company_name, language, country, postcode, city, street, house_no):
    pass

def sample_test(page: Page):
    inject_cursor(page)
    page.goto("https://duckduckgo.com")
    
    move_and_click(page, page.locator('textarea[name="q"]'), steps=100)

    text = "Playwright"

    for char in text:
        page.keyboard.type(char)
        time.sleep(random.uniform(0.1, 0.25))

    move_and_click(page, page.locator('form button[type="submit"]:visible'), steps=60)

    page.wait_for_load_state("domcontentloaded")

    page.locator('a[data-testid="result-title-a"]').first.wait_for(state="visible",timeout=15000)

    move_and_click(page, page.locator('a[data-testid="result-title-a"]').first, steps=60)

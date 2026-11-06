from playwright.sync_api import sync_playwright
from qscript import sample_test

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    sample_test(page)
    input("Press Enter to close the browser...")
    browser.close()
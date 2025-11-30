from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.firefox.launch()
    page = browser.new_page()
    page.goto('https://www.peopleperhour.com/freelance-jobs')
    print(page.content())
    browser.close()

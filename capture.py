import time
import os
from playwright.sync_api import sync_playwright

artifacts_dir = r"C:\Users\admin\.gemini\antigravity\brain\7c6ed8bd-73a8-4179-8606-b1c0a2acde26\artifacts"
os.makedirs(artifacts_dir, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
    
    # Login
    page.goto("http://127.0.0.1:8000/login")
    page.wait_for_timeout(1000)
    page.fill("input[name='username'], input#username, input[type='text']", "admin")
    page.fill("input[name='password'], input#password, input[type='password']", "admin123")
    page.click("button[type='submit']")
    page.wait_for_timeout(2000)
    
    # 1. Dashboard
    page.goto("http://127.0.0.1:8000/")
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(artifacts_dir, "01_dashboard.png"), full_page=True)
    
    # 2. AI Prediction
    page.goto("http://127.0.0.1:8000/ai-prediction")
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(artifacts_dir, "02_ai_prediction.png"), full_page=True)
    
    # 3. Module Predictions
    page.goto("http://127.0.0.1:8000/module-predictions")
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(artifacts_dir, "03_module_predictions.png"), full_page=True)
    
    # 4. Analytics
    page.goto("http://127.0.0.1:8000/analytics")
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(artifacts_dir, "04_analytics.png"), full_page=True)
    
    # 5. Admin / Vehicles
    page.goto("http://127.0.0.1:8000/vehicles")
    page.wait_for_timeout(3000)
    page.screenshot(path=os.path.join(artifacts_dir, "05_vehicles.png"), full_page=True)
    
    browser.close()
    print("Screenshots captured successfully.")

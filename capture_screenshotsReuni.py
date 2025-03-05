#!/usr/bin/env python3
import subprocess
import tkinter as tk
from Screenshot import Screenshot
from tkinter import ttk
from PIL import Image
import io
import threading
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import time

# CSS intégré
CSS_CONTENT = """
transition: all 0s!important;
html, body {
    overflow-x: hidden !important;
    width: 100% !important;
    max-width: 100% !important;
}

#wrappersite {
    overflow: hidden!important;
}

.sectionsbloc img,body .vegas-container,#content img {
    transform: initial!important;
}

#tarteaucitronAlertSmall, #tarteaucitronAlertBig,.fixedParent,.fixed-header,.animationDirection::before,.to-top,#popup,#banner,#ckbp_popup,#ckbp_banner,
#loader-wrapper,.loader,#ckbp_popup,#ckbp_banner,#AVcontentBox,#AVoverlay,#event_animation_container {
    display: none!important;
}

.fixe-bg,.baseBefore::before,#reassurances,#prestations {
    background-attachment: initial!important;
}

.animClass, .animClassChild, .animClassToogle, .animClassChildToogle {
    overflow: inherit!important;
}

.animClass, .animClassChild>*, .animClassToogle, .animClassChildToogle>* {
    transform: translate(0,0)!important;
    opacity: 1!important;
}
"""

def sanitize_url(url):
    return re.sub(r'\W+', '-', url)

def get_filename_from_url(url):
    url = re.sub(r'^https://', '', url)
    url = re.sub(r'^www\.', '', url)
    domain = url.split('/')[0]
    return re.sub(r'\..*$', '', domain)

def capture_screenshot_small(url, headless, time_value):
    mobile_emulation = {
        "deviceMetrics": {"width": 360, "height": 640, "pixelRatio": 3.0},
        "userAgent": "Mozilla/5.0 (Linux; Android 4.2.1; en-us; Nexus 5 Build/JOP40D) AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.166 Mobile Safari/535.19"
    }
    
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)
    
    driver = webdriver.Chrome(options=chrome_options)
    filename = get_filename_from_url(url)
    
    try:
        driver.get(url + "/?force")
        driver.execute_script('var style = document.createElement("style"); style.type = "text/css"; style.innerHTML = arguments[0]; document.head.appendChild(style);', CSS_CONTENT)
        
        time.sleep(time_value)
        
        WebDriverWait(driver, 10).until(lambda driver: driver.execute_script("return document.readyState") == "complete")
        
        driver.set_window_size(360, 640)
        # Capture d'écran en PNG
        png_data = driver.get_screenshot_as_png()
        
        # Conversion en JPG
        img = Image.open(io.BytesIO(png_data))
        rgb_img = img.convert('RGB')
        
        # Sauvegarde en JPG
        jpg_filename = f"{filename}-mobile.jpg"
        rgb_img.save(jpg_filename, 'JPEG', quality=85)
        
        print(f"Capture d'écran mobile sauvegardée : {jpg_filename}")
    except Exception as e:
        print(f"Une erreur s'est produite : {e}")
    finally:
        driver.quit()

def capture_screenshot_full(url, headless, time_value):
    ob = Screenshot.Screenshot()
    filename = get_filename_from_url(url)
    
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get(url + "/?force")
        
        driver.execute_script('var style = document.createElement("style"); style.type = "text/css"; style.innerHTML = arguments[0]; document.head.appendChild(style);', CSS_CONTENT)
        
        driver.set_window_size(1920, 1080)
        
        time.sleep(time_value)
        
        sanitized_url = sanitize_url(url)
        png_path = ob.full_screenshot(driver, save_path='.', image_name=f'{filename}.png', is_load_at_runtime=True, load_wait_time=3)
        
        # Conversion PNG en JPG
        with Image.open(png_path) as img:
            rgb_img = img.convert('RGB')
            jpg_filename = f'{filename}.jpg'
            rgb_img.save(jpg_filename, 'JPEG', quality=85)
        
        # Suppression du fichier PNG
        os.remove(png_path)
        
        print(f"Capture d'écran sauvegardée : {jpg_filename}")
    
    except Exception as e:
        print(f"Une erreur s'est produite : {e}")
    finally:
        driver.quit()

def execute_scripts(urls, script1_checked, script2_checked, headless, time_value):
    executed_sites = []
    
    def execute_script(script_func, script_name, url):
        script_func(url, headless, time_value)
        executed_sites.append(url.strip())
        status_text.insert(tk.END, f"{script_name} terminé sur {url.strip()}\n")
        root.update()
    
    for url in urls:
        if script1_checked:
            t1 = threading.Thread(target=execute_script, args=(capture_screenshot_small, "capture_screenshots_small", url.strip()))
            t1.start()
        
        if script2_checked:
            t2 = threading.Thread(target=execute_script, args=(capture_screenshot_full, "capture_screenshotsFull", url.strip()))
            t2.start()
    
    return executed_sites

def execute_button_clicked():
    status_text.delete("1.0", tk.END)
    urls = url_entry.get("1.0", tk.END).splitlines()
    script1_checked = script1_var.get()
    script2_checked = script2_var.get()
    headless = headless_var.get()
    time_value = int(time_entry.get())
    
    if not script1_checked and not script2_checked:
        status_label.config(text="Veuillez sélectionner au moins un script à exécuter.", foreground="red")
        return
    
    tasks = []
    if script1_checked:
        tasks.append("Script 1 (capture_screenshots_small)")
    if script2_checked:
        tasks.append("Script 2 (capture_screenshotsFull)")
    
    task_str = ", ".join(tasks)
    status_label.config(text=f"Exécution en cours de {task_str} sur les sites suivants:")
    
    executed_sites = execute_scripts(urls, script1_checked, script2_checked, headless, time_value)
    status_label.config(text=f"{task_str} en exécution sur les sites suivants: {', '.join(executed_sites)}")

# Interface graphique
root = tk.Tk()
root.title("Exécution des scripts")

url_label = ttk.Label(root, text="URLs (une par ligne):")
url_entry = tk.Text(root, width=50, height=10)
execute_button = ttk.Button(root, text="Exécuter les scripts", command=execute_button_clicked)
status_label = ttk.Label(root, text="")
status_text = tk.Text(root, width=60, height=10)
script1_var = tk.BooleanVar(value=True)
script2_var = tk.BooleanVar(value=True)
script1_checkbox = ttk.Checkbutton(root, text="Version mobile (capture_screenshots_small)", variable=script1_var)
script2_checkbox = ttk.Checkbutton(root, text="Version Full (capture_screenshotsFull)", variable=script2_var)
headless_var = tk.BooleanVar(value=True)
headless_checkbox = ttk.Checkbutton(root, text="Mode headless", variable=headless_var)
time_label = ttk.Label(root, text="Temps (en secondes):")
time_entry = ttk.Entry(root)
time_entry.insert(tk.END, "3")

url_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
url_entry.grid(row=0, column=1, padx=5, pady=5, rowspan=6, sticky="nsew")
script1_checkbox.grid(row=1, column=0, padx=5, pady=5, sticky="w")
script2_checkbox.grid(row=2, column=0, padx=5, pady=5, sticky="w")
headless_checkbox.grid(row=3, column=0, padx=5, pady=5, sticky="w")
time_label.grid(row=4, column=0, padx=5, pady=5, sticky="w")
time_entry.grid(row=5, column=0, padx=5, pady=5, sticky="w")
execute_button.grid(row=6, column=0, columnspan=2, padx=5, pady=5)
status_label.grid(row=7, column=0, columnspan=2, padx=5, pady=5)
status_text.grid(row=8, column=0, columnspan=2, padx=5, pady=5)

if __name__ == "__main__":
    root.mainloop()
import sys
import os
from Screenshot import Screenshot
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import time

def sanitize_url(url):
    # Remplace les caractères non alphanumériques par des tirets "-"
    sanitized_url = re.sub(r'\W+', '-', url)
    return sanitized_url

def get_filename_from_url(url):
    # Supprimer le protocole "https://"
    url = re.sub(r'^https://', '', url)
    # Supprimer "www."
    url = re.sub(r'^www\.', '', url)
    # Extraire le domaine principal
    domain = url.split('/')[0]
    # Supprimer l'extension de fichier
    filename = re.sub(r'\..*$', '', domain)
    return filename

# Récupération de l'URL depuis les arguments de ligne de commande
if len(sys.argv) < 2:
    print("Veuillez fournir l'URL en argument.")
    sys.exit(1)

url = sys.argv[1]

# Chemin vers le fichier CSS à appliquer
css_file_path = "style_custom.css"

# Configuration pour les captures d'écran
mobile_emulation = {
    "deviceMetrics": {"width": 360, "height": 640, "pixelRatio": 3.0},
    "userAgent": "Mozilla/5.0 (Linux; Android 4.2.1; en-us; Nexus 5 Build/JOP40D) AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.166 Mobile Safari/535.19",
}

chrome_options = Options()

# Vérifie si le mode headless est activé
if "--headless" in sys.argv:
    chrome_options.add_argument("--headless")

chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)

# Initialisation du pilote Selenium
driver = webdriver.Chrome(options=chrome_options)

sanitized_url = sanitize_url(url)
filename = get_filename_from_url(url)

try:
    driver.get(url + "/?force")

    # Applique le CSS spécifié
    with open(css_file_path, "r") as css_file:
        css = css_file.read()
        driver.execute_script('var style = document.createElement("style"); style.type = "text/css"; style.innerHTML = arguments[0]; document.head.appendChild(style);', css)

    # Attends le temps spécifié (si donné)
    if "--time" in sys.argv and sys.argv.index("--time") + 1 < len(sys.argv):
        time_index = sys.argv.index("--time")
        if time_index + 1 < len(sys.argv):
            try:
                wait_time = int(sys.argv[time_index + 1])
                time.sleep(wait_time)
            except ValueError:
                print("La valeur du temps n'est pas valide. Utilisation du temps par défaut.")
    else:
        # Attend 2 secondes au tout début
        time.sleep(5)

    # Attends que la page soit complètement chargée
    WebDriverWait(driver, 10).until(lambda driver: driver.execute_script("return document.readyState") == "complete")

    # Prend une capture d'écran en format mobile
    driver.set_window_size(360, 640)
    driver.save_screenshot(f"{filename}-mobile.png")

except NoSuchElementException as e:
    print(f"Élément non trouvé : {e}")
except TimeoutException as e:
    print(f"Temps d'attente dépassé : {e}")
except Exception as e:
    print(f"Une erreur s'est produite : {e}")

# Ferme le navigateur
driver.quit()

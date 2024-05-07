import subprocess
import tkinter as tk
from tkinter import ttk
import threading

def execute_scripts(urls, script1_checked, script2_checked, headless, time_value):
    # Chemin vers les scripts Python
    script1_path = "capture_screenshots_small.py"
    script2_path = "capture_screenshotsFull.py"

    executed_sites = []

    if script1_checked:
        t1 = threading.Thread(target=execute_script, args=(script1_path, "capture_screenshots_small.py", urls, executed_sites, headless, time_value))
        t1.start()

    if script2_checked:
        t2 = threading.Thread(target=execute_script, args=(script2_path, "capture_screenshotsFull.py", urls, executed_sites, headless, time_value))
        t2.start()

    return executed_sites

def execute_script(script_path, script_name, urls, executed_sites, headless, time_value):
    for url in urls:
        subprocess.run(["python", script_path, url.strip(), "--headless" if headless else "", "--time", str(time_value)])
        executed_sites.append(url.strip())
        status_text.insert(tk.END, f"{script_name} terminé sur {url.strip()}\n")
        root.update()  # Rafraîchir l'interface

def execute_button_clicked():
    status_text.delete("1.0", tk.END)
    urls = url_entry.get("1.0", tk.END).splitlines()  # Récupère tout le texte depuis le début jusqu'à la fin
    script1_checked = script1_var.get()
    script2_checked = script2_var.get()
    headless = headless_var.get()
    time_value = time_entry.get()
    
    if not script1_checked and not script2_checked:
        status_label.config(text="Veuillez sélectionner au moins un script à exécuter.", foreground="red")
        return
    
    tasks = []
    if script1_checked:
        tasks.append("Script 1 (capture_screenshots_small.py)")
    if script2_checked:
        tasks.append("Script 2 (capture_screenshotsFull.py)")
    
    task_str = ", ".join(tasks)
    status_label.config(text=f"Exécution en cours de {task_str} sur les sites suivants:")
    executed_sites = execute_scripts(urls, script1_checked, script2_checked, headless, time_value)
    status_label.config(text=f"{task_str} en exécution sur les sites suivants: {', '.join(executed_sites)}")

# Création de la fenêtre principale
root = tk.Tk()
root.title("Exécution des scripts")

# Création des widgets
url_label = ttk.Label(root, text="URLs (une par ligne):")
url_entry = tk.Text(root, width=50, height=10)  # Champ de texte multiligne
execute_button = ttk.Button(root, text="Exécuter les scripts", command=execute_button_clicked)
status_label = ttk.Label(root, text="")
status_text = tk.Text(root, width=60, height=10)

script1_var = tk.BooleanVar(value=True)
script2_var = tk.BooleanVar(value=True)
script1_checkbox = ttk.Checkbutton(root, text="Version mobile (capture_screenshots_small.py)", variable=script1_var)
script2_checkbox = ttk.Checkbutton(root, text="Version Full (capture_screenshotsFull.py)", variable=script2_var)

headless_var = tk.BooleanVar(value=True)
headless_checkbox = ttk.Checkbutton(root, text="Mode headless", variable=headless_var)

time_label = ttk.Label(root, text="Temps (en secondes):")
time_entry = ttk.Entry(root)
time_entry.insert(tk.END, "3")  # Insère la valeur par défaut

# Placement des widgets dans la fenêtre
url_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
url_entry.grid(row=0, column=1, padx=5, pady=5, rowspan=6, sticky="nsew")  # Utilise rowspan pour s'étendre sur plusieurs lignes
script1_checkbox.grid(row=1, column=0, padx=5, pady=5, sticky="w")
script2_checkbox.grid(row=2, column=0, padx=5, pady=5, sticky="w")
headless_checkbox.grid(row=3, column=0, padx=5, pady=5, sticky="w")
time_label.grid(row=4, column=0, padx=5, pady=5, sticky="w")
time_entry.grid(row=5, column=0, padx=5, pady=5, sticky="w")
execute_button.grid(row=6, column=0, columnspan=2, padx=5, pady=5)
status_label.grid(row=7, column=0, columnspan=2, padx=5, pady=5)
status_text.grid(row=8, column=0, columnspan=2, padx=5, pady=5)

# Lancement de la boucle principale
root.mainloop()

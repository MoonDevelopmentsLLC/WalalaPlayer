import tkinter as tk
from tkinter import filedialog, scrolledtext
import threading
import ctypes
import time
import os
import sys
import cv2
import pystray
from PIL import Image, ImageDraw, ImageTk
import win32gui
import win32con
import win32api
import win32com.client
from screeninfo import get_monitors

def get_workerws():
    progman = win32gui.FindWindow("Progman", None)
    result = ctypes.c_ulong()
    win32gui.SendMessageTimeout(progman, 0x052C, 0, 0, win32con.SMTO_NORMAL, 1000, ctypes.byref(result))
    workerws = []

    def enum_windows_callback(hwnd, lparam):
        if win32gui.GetClassName(hwnd) == "WorkerW":
            shell = win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None)
            if shell == 0:
                lparam.append(hwnd)
        return True

    win32gui.EnumWindows(enum_windows_callback, workerws)
    return workerws

class LiveWallpaper:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Walala Player")
        self.root.geometry("400x420")
        self.video_path = None
        self.running = False
        self.tray_icon = None
        self.player_thread = None
        self.stopped_manually = False
        self.behind_mode = tk.BooleanVar(value=False)
        self.auto_load_last_video = tk.BooleanVar(value=True)
        self.auto_start_wallpaper = tk.BooleanVar(value=False)
        self.launch_on_startup = tk.BooleanVar(value=False)
        self.use_toggle_theme = False  

        if getattr(sys, 'frozen', False):
            self.base_dir = sys._MEIPASS
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.last_video_file = os.path.join(self.base_dir, "last_video.txt")
        icon_path = os.path.join(self.base_dir, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception as e:
                print(f"Could not set window icon: {e}")

        self.root.configure(bg='black')
        button_style = {'bg': 'gray', 'fg': 'white', 'activebackground': '#505050', 'activeforeground': 'white'}
        check_style = {'bg': 'black', 'fg': 'white', 'selectcolor': 'gray'}

        tk.Button(self.root, text="Theme", command=self.toggle_theme, **button_style).place(x=10, y=10)

        tk.Button(self.root, text="Load Video", command=self.load_video, **button_style).pack(pady=(50, 10))
        tk.Button(self.root, text="Start Wallpaper", command=self.start_wallpaper, **button_style).pack(pady=5)

        self.toggle_frame = tk.Frame(self.root, bg='black')
        self.toggle_frame.pack(pady=5)

        self.check_widgets = []
        self.toggle_widgets = []

        self.create_checkboxes(check_style)
        self.create_toggle_buttons(button_style)

        self.log_box = scrolledtext.ScrolledText(self.root, height=10, state='disabled', bg='black', fg='#00ffff', insertbackground='white')
        self.log_box.pack(fill='both', expand=True, padx=10, pady=10)

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.try_load_last_video()

        if self.auto_start_wallpaper.get() and self.video_path and not self.stopped_manually:
            self.start_wallpaper()

    def toggle_theme(self):
        self.use_toggle_theme = not self.use_toggle_theme
        for widget in self.check_widgets:
            widget.pack_forget()
        for widget in self.toggle_widgets:
            widget.pack_forget()
        if self.use_toggle_theme:
            for widget in self.toggle_widgets:
                widget.pack(pady=2)
        else:
            for widget in self.check_widgets:
                widget.pack(pady=2)

    def create_checkboxes(self, style):
        self.check_widgets = [
            tk.Checkbutton(self.toggle_frame, text="Load Last Video on Startup", variable=self.auto_load_last_video, **style),
            tk.Checkbutton(self.toggle_frame, text="Auto-Start on Windows Startup", variable=self.launch_on_startup, command=self.toggle_startup, **style),
            tk.Checkbutton(self.toggle_frame, text="Auto-Start Wallpaper on Launch", variable=self.auto_start_wallpaper, **style)
        ]
        for widget in self.check_widgets:
            widget.pack(pady=2)

    def create_toggle_buttons(self, style):
        def make_toggle(var, text, cmd=None):
            def toggle():
                var.set(not var.get())
                btn.config(text=f"{text}: {'ON' if var.get() else 'OFF'}")
                if cmd:
                    cmd()
            btn = tk.Button(self.toggle_frame, text=f"{text}: {'ON' if var.get() else 'OFF'}", command=toggle, **style)
            return btn

        self.toggle_widgets = [
            make_toggle(self.auto_load_last_video, "Load Last Video"),
            make_toggle(self.launch_on_startup, "Auto-Start on Startup", self.toggle_startup),
            make_toggle(self.auto_start_wallpaper, "Auto-Start Wallpaper")
        ]

    def toggle_startup(self):
        startup_path = os.path.join(os.getenv("APPDATA"), "Microsoft\\Windows\\Start Menu\\Programs\\Startup")
        shortcut_path = os.path.join(startup_path, "WalalaPlayer.lnk")
        target = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
        working_dir = os.path.dirname(target)

        if self.launch_on_startup.get():
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = working_dir
            shortcut.IconLocation = target
            shortcut.save()
            self.log("Added to Windows Startup.")
        else:
            try:
                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)
                    self.log("Removed from Windows Startup.")
            except Exception as e:
                self.log(f"Error removing startup shortcut: {e}")

    def try_load_last_video(self):
        if os.path.exists(self.last_video_file):
            try:
                with open(self.last_video_file, 'r', encoding='utf-8') as f:
                    lines = f.read().splitlines()
                    if lines:
                        self.video_path = lines[0] if os.path.exists(lines[0]) else None
                        for line in lines[1:]:
                            if "auto_load_last_video=" in line:
                                self.auto_load_last_video.set(line.endswith("1"))
                            elif "auto_start_wallpaper=" in line:
                                self.auto_start_wallpaper.set(line.endswith("1"))
                            elif "behind_mode=" in line:
                                self.behind_mode.set(line.endswith("1"))
                            elif "launch_on_startup=" in line:
                                self.launch_on_startup.set(line.endswith("1"))
                        if self.video_path:
                            self.log(f"Loaded last video: {self.video_path}")
            except Exception as e:
                self.log(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            with open(self.last_video_file, 'w', encoding='utf-8') as f:
                f.write(f"{self.video_path or ''}\n")
                f.write(f"auto_load_last_video={int(self.auto_load_last_video.get())}\n")
                f.write(f"auto_start_wallpaper={int(self.auto_start_wallpaper.get())}\n")
                f.write(f"behind_mode={int(self.behind_mode.get())}\n")
                f.write(f"launch_on_startup={int(self.launch_on_startup.get())}\n")
        except Exception as e:
            self.log(f"Failed to save settings: {e}")

    def log(self, message):
        self.log_box.config(state='normal')
        self.log_box.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_box.see(tk.END)
        self.log_box.config(state='disabled')

    def load_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv")])
        if path:
            self.video_path = path
            self.log(f"Video loaded: {path}")
            self.stopped_manually = False
            self.save_settings()

    def start_wallpaper(self):
        if not self.video_path:
            self.log("Error: no video selected.")
            return
        if self.running:
            self.log("Already running.")
            return
        self.running = True
        self.stopped_manually = False
        self.log("Starting wallpaper...")
        self.save_settings()
        self.hide_to_tray()
        self.player_thread = threading.Thread(target=self.play_video, daemon=True)
        self.player_thread.start()

    def hide_to_tray(self):
        self.root.withdraw()
        if not self.tray_icon:
            self.create_tray()

    def create_tray(self):
        icon_path = os.path.join(self.base_dir, "icon.ico")
        try:
            tray_image = Image.open(icon_path)
        except Exception as e:
            self.log(f"Failed to load tray icon: {e}")
            tray_image = Image.new('RGB', (64, 64), color=(30, 30, 30))

        menu = pystray.Menu(
            pystray.MenuItem('Stop', self.stop_wallpaper),
            pystray.MenuItem('Exit', self.exit_app)
        )
        self.tray_icon = pystray.Icon('LiveWallpaper', tray_image, 'Live Wallpaper', menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
            #Free Software is so freaking awesome!!!!!! 
    def stop_wallpaper(self, icon=None, item=None):
        self.log("Stopping wallpaper...")
        self.running = False
        self.stopped_manually = True
        time.sleep(0.5)
        try:
            cv2.destroyAllWindows()
            cv2.waitKey(1)
        except Exception as e:
            self.log(f"Error closing video windows: {e}")
        win32api.ShowCursor(True)
        self.root.after(0, self.root.deiconify)
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.log("Stopped.")

    def exit_app(self, icon=None, item=None):
        self.log("Exiting...")
        self.running = False
        time.sleep(0.5)
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()
        os._exit(0)

    def _prepare_window(self, name, x, y, w, h, behind=False, parent=None):
        cv2.namedWindow(name, cv2.WINDOW_NORMAL)
        hwnd = None
        for _ in range(20):
            hwnd = win32gui.FindWindow(None, name)
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            self.log(f"Could not find window {name}.")
            return None
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style &= ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME | win32con.WS_BORDER)
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        exstyle |= win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOOLWINDOW
        exstyle &= ~win32con.WS_EX_APPWINDOW
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, exstyle)
        win32gui.SetWindowPos(hwnd, win32con.HWND_BOTTOM if behind else win32con.HWND_TOP,
                              x, y, w, h, win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED)
        if parent:
            win32gui.SetParent(hwnd, parent)
        return name

    def play_video(self):
        monitors = get_monitors()
        workerws = get_workerws() if self.behind_mode.get() else None
        names = []
        for i, mon in enumerate(monitors):
            name = f"LV_{i}"
            win = self._prepare_window(name, mon.x, mon.y, mon.width, mon.height,
                                       behind=True, parent=workerws)
            if win:
                names.append(win)

        self.log(f"Windows on {len(names)} monitor(s).")
        while self.running:
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                self.log("Error opening video.")
                break
            while cap.isOpened() and self.running:
                ret, frame = cap.read()
                if not ret:
                    break
                for name in names:
                    cv2.imshow(name, frame)
                if cv2.waitKey(30) & 0xFF == 27:
                    self.running = False
                    break
            cap.release()
            cv2.waitKey(1)

        if not self.stopped_manually:
            self.stop_wallpaper()

if __name__ == '__main__':
    LiveWallpaper().root.mainloop()

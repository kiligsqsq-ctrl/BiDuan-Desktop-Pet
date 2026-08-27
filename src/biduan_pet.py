from __future__ import annotations

import copy
import ctypes
import datetime as dt
import json
import math
import os
import random
from queue import Empty, Queue
import sys
import uuid
import winreg
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import pystray


APP_NAME = "彼端"
APP_FULL_NAME = "彼端桌宠"
APP_VERSION = "0.4.2"
APP_USER_MODEL_ID = "BiDuan.CoupleDesktopPet"
APP_MUTEX_NAME = "Local\\BiDuanCoupleDesktopPet"
TRANSPARENT_COLOR = "#ff00ff"
SYNC_INTERVAL_MS = 8_000
SYNC_FILE_PREFIX = "biduan_sync_"
ANIMATION_TICK_MS = 30
ANIMATION_INTERVAL_OPTIONS = {
    "10 秒": 10,
    "30 秒": 30,
    "60 秒": 60,
    "5 分钟": 300,
}
ANIMATION_INTERVAL_LABELS = {
    seconds: label for label, seconds in ANIMATION_INTERVAL_OPTIONS.items()
}
STATUS_SOURCE_OPTIONS = {
    "me": "我的状态",
    "partner": "TA 的状态",
}


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base.joinpath(*parts)


ANIMATION_ASSETS_DIR = resource_path("assets", "animations")
APP_ICON_PNG = resource_path("assets", "branding", "biduan_icon.png")
TRAY_ICON_PNG = resource_path("assets", "branding", "biduan_tray.png")

STATUSES = {
    "打招呼": {"color": "#4b9b91", "line": "嗨，我一直都在这里。"},
    "工作": {"color": "#4b8fe8", "line": "我在忙，但没有消失。"},
    "吃饭": {"color": "#f6a340", "line": "要按时吃饭呀。"},
    "睡觉": {"color": "#7c79d8", "line": "晚安，梦里也见。"},
    "开心": {"color": "#ffbf3d", "line": "今天心情亮晶晶。"},
    "难过": {"color": "#7d8da8", "line": "抱一下会好一点。"},
    "生气": {"color": "#e75b50", "line": "我有一点生气，需要哄一哄。"},
    "无聊": {"color": "#77a66f", "line": "有一点无聊，来陪陪我吧。"},
    "洗澡": {"color": "#48b6c7", "line": "我去洗个香香的澡。"},
    "上厕所": {"color": "#9b8067", "line": "稍等一下，我马上回来。"},
    "甜蜜": {"color": "#ff6b8a", "line": "今天也想和你贴贴。"},
}

STATUS_ALIASES = {
    "想你": "甜蜜",
    "学习": "工作",
    "游戏": "开心",
    "路上": "打招呼",
    "自定义": "无聊",
}

REACTIONS = {
    "轻轻碰你": ("你轻轻碰了碰 TA。", 8, -2, 8),
    "抱抱": ("一个很轻很久的抱抱。", 14, -1, 12),
    "喂糖": ("甜度上升，心情也软下来。", 12, 10, -4),
    "休息": ("陪 TA 安静休息一小会儿。", 4, 18, -2),
}

REMOTE_REACTIONS = {
    "轻轻碰你": "TA 轻轻碰了碰你。",
    "抱抱": "TA 给了你一个很轻很久的抱抱。",
    "喂糖": "TA 给你送来了一颗糖。",
    "休息": "TA 想陪你安静休息一会儿。",
}

DEFAULT_STATE = {
    "app": {"onboarding_complete": False},
    "me": {"name": "我", "status": "甜蜜", "custom_status": ""},
    "partner": {"name": "TA", "status": "工作", "custom_status": ""},
    "pet": {
        "name": "小彼端",
        "x": 80,
        "y": 120,
        "opacity": 0.96,
        "always_on_top": True,
        "animation_interval_seconds": 60,
        "status_source": "partner",
        "appearance": {"mode": "animated"},
    },
    "couple": {
        "together_date": dt.date.today().isoformat(),
        "anniversary_date": dt.date.today().isoformat(),
    },
    "care": {"mood": 82, "energy": 76, "longing": 64, "last_tick": dt.datetime.now().isoformat()},
    "notes": [],
    "interactions": [],
    "diary": [],
    "sync": {
        "enabled": False,
        "folder": "",
        "device_id": "",
        "last_sync_at": "",
        "last_partner_exported_at": "",
        "last_error": "",
    },
    "last_message": "双击我，打开你们的小窝。",
}


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "BiDuanPet"
    return Path.home() / ".biduan_pet"


def load_brand_image(path: Path, size: int = 256) -> Image.Image:
    try:
        image = Image.open(path).convert("RGBA")
    except OSError:
        image = Image.new("RGBA", (size, size), "#ff6b72")
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    return image


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else python
    return f'"{launcher}" "{Path(__file__).resolve()}"'


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "BiDuan")
            return bool(value)
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, "BiDuan", 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, "BiDuan")
            except FileNotFoundError:
                pass


def configure_windows_identity() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


def acquire_single_instance() -> int | None:
    if os.name != "nt":
        return 1
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, APP_MUTEX_NAME)
    if not handle:
        return None
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        return None
    return int(handle)


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def deep_merge(default: dict, saved: dict) -> dict:
    merged = copy.deepcopy(default)
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def parse_date(value: str, fallback: dt.date | None = None) -> dt.date:
    if fallback is None:
        fallback = dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def days_between(start_date: str) -> int:
    start = parse_date(start_date)
    return max(0, (dt.date.today() - start).days + 1)


def days_until_anniversary(value: str) -> int:
    date = parse_date(value)
    today = dt.date.today()
    try:
        target = dt.date(today.year, date.month, date.day)
    except ValueError:
        target = dt.date(today.year, 2, 28)
    if target < today:
        try:
            target = dt.date(today.year + 1, date.month, date.day)
        except ValueError:
            target = dt.date(today.year + 1, 2, 28)
    return (target - today).days


def short_time(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(value)
        return parsed.strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return "--"


def wrap_text(text: str, width: int = 14) -> str:
    text = text.strip()
    if len(text) <= width:
        return text
    lines = []
    current = ""
    for char in text:
        current += char
        if len(current) >= width:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return "\n".join(lines[:3])


@dataclass
class AnimationClip:
    path: Path
    name: str
    frames: list[Image.Image]
    durations: list[int]


def load_animation_manifest() -> dict:
    path = ANIMATION_ASSETS_DIR / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "states": [], "drag": {}}
    if not isinstance(manifest.get("states"), list):
        manifest["states"] = []
    return manifest


def find_animation_state(manifest: dict, status: str) -> dict | None:
    for state in manifest.get("states", []):
        if state.get("status") == status:
            return state
    return None


def animation_file(relative_path: str) -> Path:
    return ANIMATION_ASSETS_DIR / relative_path


def load_gif_clip(path: Path, name: str = "", size: int = 228) -> AnimationClip:
    frames: list[Image.Image] = []
    durations: list[int] = []
    with Image.open(path) as image:
        frame_count = int(getattr(image, "n_frames", 1))
        for index in range(frame_count):
            image.seek(index)
            frame = image.convert("RGBA").convert("RGBa")
            frame = frame.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
            alpha = frame.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
            frame.putalpha(alpha)
            frames.append(frame.copy())
            duration = int(image.info.get("duration", 40) or 40)
            durations.append(max(20, min(250, duration)))
    if not frames:
        raise ValueError(f"GIF has no frames: {path}")
    return AnimationClip(path=path, name=name or path.stem, frames=frames, durations=durations)


def load_gif_preview(path: Path, size: int = 220) -> Image.Image:
    with Image.open(path) as image:
        frame = image.convert("RGBA")
        frame.thumbnail((size, size), Image.Resampling.LANCZOS)
        return frame.copy()


class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "state.json")
        self.is_new = not self.path.exists()
        self.data = self.load()
        if self.ensure_runtime_defaults():
            self.save()

    def load(self) -> dict:
        if not self.path.exists():
            return copy.deepcopy(DEFAULT_STATE)
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            return deep_merge(DEFAULT_STATE, saved)
        except (OSError, json.JSONDecodeError):
            backup = self.path.with_suffix(".broken.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            return copy.deepcopy(DEFAULT_STATE)

    def ensure_runtime_defaults(self) -> bool:
        changed = False
        sync = self.data.setdefault("sync", {})
        if not sync.get("device_id"):
            sync["device_id"] = uuid.uuid4().hex
            changed = True
        for key, value in DEFAULT_STATE["sync"].items():
            if key not in sync:
                sync[key] = copy.deepcopy(value)
                changed = True
        for profile_name, fallback in (("me", "甜蜜"), ("partner", "工作")):
            profile = self.data.setdefault(profile_name, {})
            current = profile.get("status", fallback)
            migrated = STATUS_ALIASES.get(current, current)
            if migrated not in STATUSES:
                migrated = fallback
            if current != migrated:
                profile["status"] = migrated
                changed = True
        pet = self.data.setdefault("pet", {})
        interval = pet.get("animation_interval_seconds", 60)
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = 60
        if interval not in ANIMATION_INTERVAL_LABELS:
            interval = 60
        if pet.get("animation_interval_seconds") != interval:
            pet["animation_interval_seconds"] = interval
            changed = True
        status_source = pet.get("status_source", "partner")
        if status_source not in STATUS_SOURCE_OPTIONS:
            status_source = "partner"
        if pet.get("status_source") != status_source:
            pet["status_source"] = status_source
            changed = True
        appearance = pet.setdefault("appearance", {})
        if appearance.get("mode") != "animated":
            appearance["mode"] = "animated"
            changed = True
        return changed

    def save(self) -> None:
        write_json_atomic(self.path, self.data)

    @property
    def device_id(self) -> str:
        return self.data["sync"]["device_id"]

    def set_message(self, message: str) -> None:
        self.data["last_message"] = message
        self.save()

    def add_note(self, author: str, text: str) -> dict:
        note = {
            "id": uuid.uuid4().hex,
            "sender_id": self.device_id,
            "author": author,
            "text": text[:2000],
            "created_at": now_iso(),
        }
        self.data.setdefault("notes", []).append(note)
        self.data["notes"] = self.data["notes"][-200:]
        self.save()
        return note

    def add_interaction(self, author: str, action: str, message: str) -> dict:
        interaction = {
            "id": uuid.uuid4().hex,
            "sender_id": self.device_id,
            "author": author,
            "action": action,
            "message": message,
            "created_at": now_iso(),
        }
        self.data.setdefault("interactions", []).append(interaction)
        self.data["interactions"] = self.data["interactions"][-100:]
        self.save()
        return interaction

    def apply_care_delta(self, mood: int = 0, energy: int = 0, longing: int = 0) -> None:
        care = self.data["care"]
        care["mood"] = clamp(care.get("mood", 70) + mood)
        care["energy"] = clamp(care.get("energy", 70) + energy)
        care["longing"] = clamp(care.get("longing", 50) + longing)
        care["last_tick"] = now_iso()
        self.save()

    def care_tick(self) -> bool:
        care = self.data["care"]
        try:
            last = dt.datetime.fromisoformat(care.get("last_tick", now_iso()))
        except ValueError:
            last = dt.datetime.now()
        minutes = (dt.datetime.now() - last).total_seconds() / 60
        steps = int(minutes // 30)
        if steps <= 0:
            return False
        care["mood"] = clamp(care.get("mood", 70) - steps)
        care["energy"] = clamp(care.get("energy", 70) - steps)
        care["longing"] = clamp(care.get("longing", 50) + steps * 2)
        care["last_tick"] = now_iso()
        self.save()
        return True

    def make_sync_packet(self) -> dict:
        me = self.data["me"]

        def sent_here(item: dict) -> bool:
            sender_id = item.get("sender_id")
            return sender_id == self.device_id or (not sender_id and item.get("author") == me["name"])

        recent_notes = [copy.deepcopy(note) for note in self.data.get("notes", []) if sent_here(note)]
        recent_interactions = [
            copy.deepcopy(interaction)
            for interaction in self.data.get("interactions", [])
            if sent_here(interaction)
        ]
        return {
            "app": "BiDuanPet",
            "schema": 2,
            "version": APP_VERSION,
            "sender_id": self.device_id,
            "exported_at": now_iso(),
            "profile": {
                "name": me["name"],
                "status": me["status"],
                "custom_status": me.get("custom_status", ""),
            },
            "notes": recent_notes[-50:],
            "interactions": recent_interactions[-30:],
        }

    def import_sync_packet(self, packet: dict) -> dict:
        if not isinstance(packet, dict) or packet.get("app") != "BiDuanPet":
            raise ValueError("这不是彼端同步文件。")
        sender_id = str(packet.get("sender_id", ""))
        result = {
            "notes": 0,
            "interactions": 0,
            "status_changed": False,
            "latest_message": "",
            "partner_exported_at": packet.get("exported_at", ""),
        }
        if sender_id and sender_id == self.device_id:
            return result

        profile = packet.get("profile", {})
        partner = self.data["partner"]
        previous_profile = (partner.get("name"), partner.get("status"), partner.get("custom_status", ""))
        partner["name"] = str(profile.get("name") or partner["name"])[:30]
        incoming_status = profile.get("status")
        if incoming_status in STATUSES:
            partner["status"] = incoming_status
        partner["custom_status"] = str(profile.get("custom_status", ""))[:80]
        result["status_changed"] = previous_profile != (
            partner.get("name"),
            partner.get("status"),
            partner.get("custom_status", ""),
        )

        known_note_ids = {note.get("id") for note in self.data.get("notes", [])}
        for note in packet.get("notes", [])[-50:]:
            if not isinstance(note, dict):
                continue
            note_id = str(note.get("id") or uuid.uuid4().hex)
            text = str(note.get("text", "")).strip()[:2000]
            if note_id in known_note_ids or not text:
                continue
            self.data.setdefault("notes", []).append(
                {
                    "id": note_id,
                    "sender_id": sender_id or note.get("sender_id", ""),
                    "author": partner["name"],
                    "text": text,
                    "created_at": note.get("created_at", now_iso()),
                }
            )
            known_note_ids.add(note_id)
            result["notes"] += 1
            result["latest_message"] = f"{partner['name']}：{text}"

        known_interaction_ids = {
            interaction.get("id") for interaction in self.data.get("interactions", [])
        }
        for interaction in packet.get("interactions", [])[-30:]:
            if not isinstance(interaction, dict):
                continue
            interaction_id = str(interaction.get("id") or uuid.uuid4().hex)
            if interaction_id in known_interaction_ids:
                continue
            action = str(interaction.get("action", ""))[:30]
            message = REMOTE_REACTIONS.get(
                action,
                str(interaction.get("message", "TA 给你送来了一点陪伴。"))[:200],
            )
            self.data.setdefault("interactions", []).append(
                {
                    "id": interaction_id,
                    "sender_id": sender_id or interaction.get("sender_id", ""),
                    "author": partner["name"],
                    "action": action,
                    "message": message,
                    "created_at": interaction.get("created_at", now_iso()),
                }
            )
            known_interaction_ids.add(interaction_id)
            if action in REACTIONS:
                _, mood, energy, longing = REACTIONS[action]
                care = self.data["care"]
                care["mood"] = clamp(care.get("mood", 70) + mood)
                care["energy"] = clamp(care.get("energy", 70) + energy)
                care["longing"] = clamp(care.get("longing", 50) + longing)
                care["last_tick"] = now_iso()
            result["interactions"] += 1
            result["latest_message"] = message

        self.data["notes"] = self.data.get("notes", [])[-200:]
        self.data["interactions"] = self.data.get("interactions", [])[-100:]
        self.save()
        return result

    def configure_sync_folder(self, folder: Path, enabled: bool = True) -> None:
        sync = self.data["sync"]
        sync["folder"] = str(folder)
        sync["enabled"] = enabled
        sync["last_error"] = ""
        self.save()

    def sync_folder_once(self) -> dict:
        result = {
            "notes": 0,
            "interactions": 0,
            "status_changed": False,
            "latest_message": "",
            "error": "",
        }
        sync = self.data["sync"]
        folder_value = str(sync.get("folder", "")).strip()
        if not sync.get("enabled") or not folder_value:
            return result

        folder = Path(folder_value)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            own_file = folder / f"{SYNC_FILE_PREFIX}{self.device_id}.json"
            write_json_atomic(own_file, self.make_sync_packet())

            candidates = []
            for path in folder.glob(f"{SYNC_FILE_PREFIX}*.json"):
                if path == own_file:
                    continue
                try:
                    candidates.append((path.stat().st_mtime_ns, path))
                except OSError:
                    continue
            for _, path in sorted(candidates)[-8:]:
                packet = json.loads(path.read_text(encoding="utf-8"))
                imported = self.import_sync_packet(packet)
                result["notes"] += imported["notes"]
                result["interactions"] += imported["interactions"]
                result["status_changed"] = result["status_changed"] or imported["status_changed"]
                if imported["latest_message"]:
                    result["latest_message"] = imported["latest_message"]
                if imported["partner_exported_at"]:
                    sync["last_partner_exported_at"] = imported["partner_exported_at"]

            sync["last_sync_at"] = now_iso()
            sync["last_error"] = ""
            self.save()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            result["error"] = str(exc)
            sync["last_error"] = str(exc)
            self.save()
        return result


class DesktopPetApp:
    def __init__(self) -> None:
        self.store = StateStore()
        self.root = tk.Tk()
        self.root.title(APP_FULL_NAME)
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT_COLOR)
        self.root.option_add("*Font", "{Microsoft YaHei} 10")
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.apply_window_icon(self.root)

        pet = self.store.data["pet"]
        self.width = 300
        self.height = 300
        self.root.geometry(f"{self.width}x{self.height}+{pet.get('x', 80)}+{pet.get('y', 120)}")
        self.set_window_attributes()

        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.phase = 0
        self.blink_countdown = random.randint(35, 70)
        self.drag_offset = (0, 0)
        self.drag_start_pointer = (0, 0)
        self.dragging = False
        self.message = self.store.data.get("last_message", "")
        self.message_until = 0
        self.animation_manifest = load_animation_manifest()
        self.animation_clip: AnimationClip | None = None
        self.animation_mode = "status"
        self.animation_status = self.displayed_status()
        self.animation_variant_file = ""
        self.animation_frame_index = 0
        self.animation_elapsed_ms = 0
        self.animation_variant_elapsed_ms = 0
        self.animation_loops_remaining = 1
        self.animation_photo_index = -1
        self.pet_photo: ImageTk.PhotoImage | None = None
        self.panel: ControlPanel | None = None
        self.pet_visible = True
        self.tray_icon: pystray.Icon | None = None
        self.ui_queue: Queue[Callable[[], None]] = Queue()
        self.sync_request_id: str | None = None
        self.quitting = False

        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label="打开小窝", command=self.open_panel)
        self.menu.add_command(label="轻轻碰你", command=lambda: self.react("轻轻碰你"))
        self.menu.add_command(label="隐藏桌宠（从右下角恢复）", command=self.hide_pet)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.quit_app)

        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag_window)
        self.canvas.bind("<ButtonRelease-1>", self.end_drag)
        self.canvas.bind("<Double-Button-1>", lambda event: self.open_panel())
        self.canvas.bind("<Button-3>", self.show_menu)
        self.play_startup_animation()

    def apply_window_icon(self, window: tk.Misc) -> None:
        try:
            photo = ImageTk.PhotoImage(load_brand_image(APP_ICON_PNG, 64), master=window)
            window.iconphoto(True, photo)
            setattr(window, "_biduan_icon_photo", photo)
        except (OSError, tk.TclError):
            pass

    def set_window_attributes(self) -> None:
        pet = self.store.data["pet"]
        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)
        except tk.TclError:
            pass
        try:
            self.root.wm_attributes("-topmost", bool(pet.get("always_on_top", True)))
            self.root.wm_attributes("-alpha", float(pet.get("opacity", 0.96)))
        except tk.TclError:
            pass

    def displayed_status(self) -> str:
        source = self.store.data.get("pet", {}).get("status_source", "partner")
        profile_name = "me" if source == "me" else "partner"
        fallback = "甜蜜" if profile_name == "me" else "工作"
        status = self.store.data.get(profile_name, {}).get("status", fallback)
        return status if status in STATUSES else fallback

    def status_source(self) -> str:
        source = self.store.data.get("pet", {}).get("status_source", "partner")
        return source if source in STATUS_SOURCE_OPTIONS else "partner"

    def animation_interval_ms(self) -> int:
        seconds = self.store.data.get("pet", {}).get("animation_interval_seconds", 60)
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            seconds = 60
        if seconds not in ANIMATION_INTERVAL_LABELS:
            seconds = 60
        return seconds * 1000

    def start(self) -> None:
        self.start_tray()
        self.process_ui_queue()
        self.animate()
        self.schedule_care_tick()
        self.schedule_sync_tick()
        if self.store.is_new:
            self.root.after(600, self.open_panel)
            self.root.after(1300, lambda: self.notify("欢迎来到彼端。先在小窝里写下你们的名字和纪念日。"))
        self.root.mainloop()

    def start_tray(self) -> None:
        def status_action(value: str) -> Callable:
            def action(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
                self.post_to_ui(lambda: self.set_my_status(value))

            return action

        def status_checked(value: str) -> Callable:
            def checked(_item: pystray.MenuItem) -> bool:
                return self.store.data["me"].get("status") == value

            return checked

        status_menu = pystray.Menu(
            *[
                pystray.MenuItem(
                    status,
                    status_action(status),
                    radio=True,
                    checked=status_checked(status),
                )
                for status in STATUSES
            ]
        )
        menu = pystray.Menu(
            pystray.MenuItem(
                "打开彼端小窝",
                lambda _icon, _item: self.post_to_ui(self.open_panel),
                default=True,
            ),
            pystray.MenuItem(
                lambda _item: "隐藏桌宠" if self.pet_visible else "显示桌宠",
                lambda _icon, _item: self.post_to_ui(self.toggle_pet),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("我的状态", status_menu),
            pystray.MenuItem(
                "给 TA 一个抱抱",
                lambda _icon, _item: self.post_to_ui(lambda: self.react("抱抱")),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "开机自动启动",
                lambda _icon, _item: self.post_to_ui(self.toggle_startup),
                checked=lambda _item: is_startup_enabled(),
            ),
            pystray.MenuItem(
                "退出彼端",
                lambda _icon, _item: self.post_to_ui(self.quit_app),
            ),
        )
        self.tray_icon = pystray.Icon(
            "BiDuan",
            icon=load_brand_image(TRAY_ICON_PNG, 64),
            title=APP_FULL_NAME,
            menu=menu,
        )
        self.tray_icon.run_detached()

    def post_to_ui(self, callback: Callable[[], None]) -> None:
        self.ui_queue.put(callback)

    def process_ui_queue(self) -> None:
        try:
            while True:
                callback = self.ui_queue.get_nowait()
                callback()
        except Empty:
            pass
        if not self.quitting:
            self.root.after(80, self.process_ui_queue)

    def notify(self, message: str, title: str = APP_NAME) -> None:
        if not self.tray_icon:
            return
        try:
            self.tray_icon.notify(message, title)
        except (NotImplementedError, OSError):
            pass

    def refresh_tray(self) -> None:
        if not self.tray_icon:
            return
        partner = self.store.data["partner"]
        self.tray_icon.title = f"{APP_NAME} · {partner['name']}：{partner.get('status', '工作')}"
        self.tray_icon.update_menu()

    def start_drag(self, event: tk.Event) -> None:
        self.drag_offset = (event.x, event.y)
        self.drag_start_pointer = (event.x_root, event.y_root)
        self.dragging = False

    def drag_window(self, event: tk.Event) -> None:
        if not self.dragging:
            distance = abs(event.x_root - self.drag_start_pointer[0]) + abs(
                event.y_root - self.drag_start_pointer[1]
            )
            if distance >= 6:
                self.dragging = True
                self.play_drag_animation()
        x = self.root.winfo_pointerx() - self.drag_offset[0]
        y = self.root.winfo_pointery() - self.drag_offset[1]
        self.root.geometry(f"+{x}+{y}")

    def end_drag(self, _event: tk.Event) -> None:
        pet = self.store.data["pet"]
        pet["x"] = self.root.winfo_x()
        pet["y"] = self.root.winfo_y()
        self.store.save()
        if self.dragging:
            self.dragging = False
            self.set_status_animation(self.displayed_status(), force_variant=True)

    def show_menu(self, event: tk.Event) -> None:
        self.menu.tk_popup(event.x_root, event.y_root)

    def show_pet(self) -> None:
        self.pet_visible = True
        self.root.deiconify()
        self.set_window_attributes()
        self.refresh_tray()

    def hide_pet(self) -> None:
        self.pet_visible = False
        self.root.withdraw()
        self.refresh_tray()
        self.notify("桌宠已隐藏，点击右下角“彼端”图标可以恢复。")

    def toggle_pet(self) -> None:
        if self.pet_visible:
            self.hide_pet()
        else:
            self.show_pet()

    def toggle_startup(self) -> None:
        try:
            enabled = not is_startup_enabled()
            set_startup_enabled(enabled)
            self.notify("已开启开机自动启动。" if enabled else "已关闭开机自动启动。")
            if self.panel and self.panel.exists():
                self.panel.startup_enabled.set(enabled)
            self.refresh_tray()
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"开机启动设置失败：{exc}")

    def quit_app(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        self.store.save()
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.destroy()

    def open_panel(self) -> None:
        if self.panel and self.panel.exists():
            self.panel.focus()
            return
        self.panel = ControlPanel(self)
        if not self.store.data["app"].get("onboarding_complete"):
            self.store.data["app"]["onboarding_complete"] = True
            self.store.save()

    def react(self, action: str) -> None:
        message, mood, energy, longing = REACTIONS.get(action, ("我收到啦。", 3, 0, 2))
        self.store.apply_care_delta(mood, energy, longing)
        self.store.add_interaction(self.store.data["me"]["name"], action, message)
        self.say(message, seconds=4)
        self.request_sync()
        if self.panel and self.panel.exists():
            self.panel.refresh_all()

    def set_my_status(self, status: str) -> None:
        if status not in STATUSES:
            return
        self.store.data["me"]["status"] = status
        if self.status_source() == "me":
            self.set_status_animation(status, force_variant=True)
        partner_name = self.store.data["partner"]["name"]
        self.say(f"我的状态已设为“{status}”，会同步给 {partner_name}。")
        self.request_sync()
        if self.panel and self.panel.exists():
            self.panel.me_status.set(status)
            self.panel.refresh_all()
        self.refresh_tray()

    def say(self, message: str, seconds: int = 5) -> None:
        self.message = message
        self.message_until = self.phase + seconds * round(1000 / ANIMATION_TICK_MS)
        self.store.set_message(message)

    def request_sync(self) -> None:
        if not self.store.data["sync"].get("enabled"):
            return
        if self.sync_request_id:
            try:
                self.root.after_cancel(self.sync_request_id)
            except tk.TclError:
                pass
        self.sync_request_id = self.root.after(450, self.sync_now)

    def sync_now(self, user_initiated: bool = False) -> dict:
        self.sync_request_id = None
        result = self.store.sync_folder_once()
        self.handle_sync_result(result, user_initiated)
        return result

    def handle_sync_result(self, result: dict, user_initiated: bool = False) -> None:
        if result.get("status_changed") and self.status_source() == "partner":
            self.set_status_animation(self.displayed_status(), force_variant=True)
        if self.panel and self.panel.exists():
            self.panel.partner_name.set(self.store.data["partner"]["name"])
            self.panel.refresh_all()
        self.refresh_tray()
        if result.get("latest_message"):
            message = result["latest_message"]
            self.say(message, seconds=7)
            self.notify(message, f"{APP_NAME} · 收到 TA 的消息")
        elif result.get("status_changed"):
            partner = self.store.data["partner"]
            message = f"{partner['name']}现在：{partner.get('status', '工作')}"
            self.say(message, seconds=5)
            self.notify(message)
        elif user_initiated and not result.get("error"):
            self.notify("同步完成，已经和共享文件夹保持一致。")
        if result.get("error") and user_initiated:
            messagebox.showerror("同步失败", result["error"])

    def schedule_sync_tick(self) -> None:
        if self.store.data["sync"].get("enabled"):
            self.sync_now()
        self.root.after(SYNC_INTERVAL_MS, self.schedule_sync_tick)

    def schedule_care_tick(self) -> None:
        changed = self.store.care_tick()
        if changed and self.panel and self.panel.exists():
            self.panel.refresh_all()
        self.root.after(60_000, self.schedule_care_tick)

    def animate(self) -> None:
        self.phase += 1
        self.advance_animation(ANIMATION_TICK_MS)
        self.draw()
        self.root.after(ANIMATION_TICK_MS, self.animate)

    def draw_round_rect(self, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> None:
        c = self.canvas
        c.create_arc(x1, y1, x1 + radius, y1 + radius, start=90, extent=90, **kwargs)
        c.create_arc(x2 - radius, y1, x2, y1 + radius, start=0, extent=90, **kwargs)
        c.create_arc(x2 - radius, y2 - radius, x2, y2, start=270, extent=90, **kwargs)
        c.create_arc(x1, y2 - radius, x1 + radius, y2, start=180, extent=90, **kwargs)
        c.create_rectangle(x1 + radius // 2, y1, x2 - radius // 2, y2, **kwargs)
        c.create_rectangle(x1, y1 + radius // 2, x2, y2 - radius // 2, **kwargs)

    def invalidate_pet_image(self) -> None:
        self.set_status_animation(self.displayed_status(), force_variant=True)

    def animation_variants(self, status: str) -> list[dict]:
        state = find_animation_state(self.animation_manifest, status)
        if not state:
            return []
        return [variant for variant in state.get("variants", []) if variant.get("file")]

    def load_animation_variant(self, variant: dict, mode: str, loops: int) -> bool:
        relative_path = str(variant.get("file", ""))
        if not relative_path:
            return False
        path = animation_file(relative_path)
        try:
            clip = load_gif_clip(path, str(variant.get("name", path.stem)))
        except (OSError, ValueError):
            return False
        self.animation_clip = clip
        self.animation_mode = mode
        self.animation_variant_file = relative_path
        self.animation_frame_index = 0
        self.animation_elapsed_ms = 0
        self.animation_variant_elapsed_ms = 0
        self.animation_loops_remaining = max(1, loops)
        self.animation_photo_index = -1
        self.pet_photo = None
        return True

    def set_status_animation(self, status: str, force_variant: bool = False) -> bool:
        if status not in STATUSES:
            status = "甜蜜"
        self.animation_status = status
        variants = self.animation_variants(status)
        if not variants:
            self.animation_clip = None
            return False
        candidates = list(variants)
        if len(candidates) > 1 and (force_variant or self.animation_mode == "status"):
            alternatives = [
                variant for variant in candidates if variant.get("file") != self.animation_variant_file
            ]
            if alternatives:
                candidates = alternatives
        random.shuffle(candidates)
        for variant in candidates:
            if self.load_animation_variant(variant, mode="status", loops=random.randint(2, 4)):
                return True
        self.animation_clip = None
        return False

    def play_startup_animation(self) -> None:
        variants = self.animation_variants("打招呼")
        random.shuffle(variants)
        for variant in variants:
            if self.load_animation_variant(variant, mode="startup", loops=1):
                return
        self.set_status_animation(self.displayed_status(), force_variant=True)

    def play_drag_animation(self) -> None:
        drag = self.animation_manifest.get("drag", {})
        if not self.load_animation_variant(drag, mode="drag", loops=1):
            self.set_status_animation(self.displayed_status(), force_variant=True)

    def advance_animation(self, elapsed_ms: int) -> None:
        clip = self.animation_clip
        if not clip or not clip.frames:
            return
        previous_index = self.animation_frame_index
        self.animation_elapsed_ms += elapsed_ms
        if self.animation_mode == "status":
            self.animation_variant_elapsed_ms += elapsed_ms
        while self.animation_elapsed_ms >= clip.durations[self.animation_frame_index]:
            self.animation_elapsed_ms -= clip.durations[self.animation_frame_index]
            self.animation_frame_index += 1
            if self.animation_frame_index < len(clip.frames):
                continue

            self.animation_frame_index = 0
            if self.animation_mode == "startup":
                self.set_status_animation(self.displayed_status(), force_variant=True)
                return
            if self.animation_mode == "status":
                if self.animation_variant_elapsed_ms >= self.animation_interval_ms():
                    self.set_status_animation(self.animation_status, force_variant=True)
                    return
            if self.animation_mode == "drag" and not self.dragging:
                self.set_status_animation(self.displayed_status(), force_variant=True)
                return

        if previous_index != self.animation_frame_index:
            self.animation_photo_index = -1

    def draw_animation_pet(self, x: int, y: int) -> bool:
        clip = self.animation_clip
        if not clip or not clip.frames:
            return False
        if self.animation_photo_index != self.animation_frame_index or self.pet_photo is None:
            self.pet_photo = ImageTk.PhotoImage(
                clip.frames[self.animation_frame_index],
                master=self.root,
            )
            self.animation_photo_index = self.animation_frame_index
        self.canvas.create_image(x, y, image=self.pet_photo, anchor="center")
        return True

    def draw_default_pet(self, x: int, y: float, status: dict, partner_status: dict, care: dict, pulse: float) -> None:
        c = self.canvas
        c.create_oval(x - 70, y + 62, x + 70, y + 82, fill="#000000", outline="", stipple="gray50")
        c.create_oval(x - 75, y - 72, x + 75, y + 72, fill=status["color"], outline="#ffffff", width=3)
        c.create_oval(x - 48, y - 82, x - 6, y - 38, fill="#ffd7df", outline="#ffffff", width=2)
        c.create_oval(x + 6, y - 82, x + 48, y - 38, fill="#ffd7df", outline="#ffffff", width=2)
        c.create_oval(x - 58, y - 44, x + 58, y + 58, fill="#fff7f1", outline="")

        self.blink_countdown -= 1
        blinking = self.blink_countdown in (1, 2, 3)
        if self.blink_countdown <= 0:
            self.blink_countdown = random.randint(35, 80)
        if blinking:
            c.create_line(x - 32, y - 8, x - 12, y - 8, fill="#594b57", width=3, capstyle="round")
            c.create_line(x + 12, y - 8, x + 32, y - 8, fill="#594b57", width=3, capstyle="round")
        else:
            c.create_oval(x - 34, y - 18, x - 16, y + 4, fill="#3f3342", outline="")
            c.create_oval(x + 16, y - 18, x + 34, y + 4, fill="#3f3342", outline="")
            c.create_oval(x - 28, y - 14, x - 23, y - 8, fill="#ffffff", outline="")
            c.create_oval(x + 22, y - 14, x + 27, y - 8, fill="#ffffff", outline="")

        c.create_oval(x - 48, y + 4, x - 24, y + 18, fill="#ffbcc8", outline="")
        c.create_oval(x + 24, y + 4, x + 48, y + 18, fill="#ffbcc8", outline="")
        c.create_arc(x - 24, y + 6, x + 24, y + 34, start=200, extent=140, style="arc", outline="#594b57", width=3)
        c.create_text(x, y + 38 + pulse, text="\u2665", fill=partner_status["color"], font=("Microsoft YaHei", 24, "bold"))
        c.create_text(
            x,
            y + 66,
            text=f"{self.store.data['pet']['name']} · {care.get('mood', 0)}%",
            fill="#ffffff",
            font=("Microsoft YaHei", 9, "bold"),
        )

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")

        me = self.store.data["me"]
        partner = self.store.data["partner"]
        care = self.store.data["care"]
        showing_me = self.status_source() == "me"
        display_profile = me if showing_me else partner
        display_status = self.displayed_status()
        status = STATUSES[display_status]
        display_name = me["name"] if showing_me else partner["name"]
        pulse = math.sin(self.phase / 10) * 2
        x = self.width // 2
        y = 180

        if not self.draw_animation_pet(x, y):
            self.draw_default_pet(x, y, status, status, care, pulse)

        if self.message_until and self.phase > self.message_until:
            self.message = status["line"]
            self.message_until = 0
        bubble = self.message or status["line"]
        if self.phase % 320 == 0 and not self.message_until:
            bubble = random.choice(
                [
                    f"{display_name}现在：{display_status}",
                    status["line"],
                    f"在一起第 {days_between(self.store.data['couple']['together_date'])} 天",
                    "想念不是打扰，是安静陪着。",
                ]
            )
            self.message = bubble

        text_id = c.create_text(
            x,
            34,
            text=wrap_text(bubble, 15),
            fill="#5a3342",
            font=("Microsoft YaHei", 10, "bold"),
            justify="center",
            width=220,
        )
        bbox = c.bbox(text_id)
        if bbox:
            x1, y1, x2, y2 = bbox
            pad = 10
            self.draw_round_rect(
                x1 - pad,
                y1 - pad,
                x2 + pad,
                y2 + pad,
                18,
                fill="#fff5f7",
                outline="#ffc1cf",
                width=2,
            )
            c.tag_raise(text_id)


class ControlPanel:
    def __init__(self, app: DesktopPetApp) -> None:
        self.app = app
        self.store = app.store
        self.window = tk.Toplevel(app.root)
        self.window.title("彼端 · 情侣小窝")
        self.window.geometry("660x720")
        self.window.minsize(600, 660)
        self.window.configure(bg="#fffaf7")
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        self.window.option_add("*Font", "{Microsoft YaHei} 10")
        self.app.apply_window_icon(self.window)

        self.style = ttk.Style(self.window)
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#fffaf7")
        self.style.configure("TLabelframe", background="#fffaf7")
        self.style.configure("TLabelframe.Label", background="#fffaf7", foreground="#5a3342", font=("Microsoft YaHei", 10, "bold"))
        self.style.configure("TLabel", background="#fffaf7", foreground="#3f3342")
        self.style.configure("TButton", padding=(10, 6))
        self.style.configure("Accent.TButton", background="#ff6b8a", foreground="#ffffff")
        self.style.map("Accent.TButton", background=[("active", "#f05275")])

        data = self.store.data
        self.me_name = tk.StringVar(value=data["me"]["name"])
        self.partner_name = tk.StringVar(value=data["partner"]["name"])
        self.pet_name = tk.StringVar(value=data["pet"]["name"])
        self.me_status = tk.StringVar(value=data["me"]["status"])
        self.together_date = tk.StringVar(value=data["couple"]["together_date"])
        self.anniversary_date = tk.StringVar(value=data["couple"]["anniversary_date"])
        self.opacity = tk.DoubleVar(value=float(data["pet"].get("opacity", 0.96)))
        self.always_on_top = tk.BooleanVar(value=bool(data["pet"].get("always_on_top", True)))
        interval_seconds = int(data["pet"].get("animation_interval_seconds", 60))
        self.animation_interval_label = tk.StringVar(
            value=ANIMATION_INTERVAL_LABELS.get(interval_seconds, "60 秒")
        )
        self.desktop_status_source = tk.StringVar(
            value=data["pet"].get("status_source", "partner")
        )
        self.startup_enabled = tk.BooleanVar(value=is_startup_enabled())
        self.auto_sync_enabled = tk.BooleanVar(value=bool(data["sync"].get("enabled", False)))
        self.sync_status_text = tk.StringVar(value="")
        self.mood_value = tk.IntVar(value=data["care"]["mood"])
        self.energy_value = tk.IntVar(value=data["care"]["energy"])
        self.longing_value = tk.IntVar(value=data["care"]["longing"])
        self.animation_states = list(self.app.animation_manifest.get("states", []))
        self.selected_animation_status = tk.StringVar(value=data["me"]["status"])
        self.preview_variant_indices: dict[str, int] = {}
        self.appearance_preview_photo: ImageTk.PhotoImage | None = None
        self.tab_scroll_canvases: dict[str, tk.Canvas] = {}

        self.build()
        self.refresh_all()

    def exists(self) -> bool:
        return bool(self.window.winfo_exists())

    def focus(self) -> None:
        self.window.deiconify()
        self.window.focus_force()

    def build(self) -> None:
        outer = ttk.Frame(self.window, padding=18)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        title_group = ttk.Frame(header)
        title_group.pack(side="left")
        ttk.Label(title_group, text=APP_NAME, font=("Microsoft YaHei", 20, "bold"), foreground="#ff5f78").pack(anchor="w")
        ttk.Label(
            title_group,
            text=f"情侣小窝 · MVP {APP_VERSION}",
            font=("Microsoft YaHei", 9),
            foreground="#4b8588",
        ).pack(anchor="w")
        ttk.Button(header, text="保存", style="Accent.TButton", command=self.save_profile).pack(side="right")

        self.summary = ttk.Label(outer, text="", font=("Microsoft YaHei", 10), foreground="#6f5962")
        self.summary.pack(fill="x", pady=(0, 12))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)

        today_container, self.today_tab = self.create_scrollable_tab()
        appearance_container, self.appearance_tab = self.create_scrollable_tab()
        interact_container, self.interact_tab = self.create_scrollable_tab()
        notes_container, self.notes_tab = self.create_scrollable_tab()
        settings_container, self.settings_tab = self.create_scrollable_tab()
        self.notebook.add(today_container, text="陪伴")
        self.notebook.add(appearance_container, text="动作")
        self.notebook.add(interact_container, text="互动")
        self.notebook.add(notes_container, text="留言")
        self.notebook.add(settings_container, text="设置")
        self.window.bind("<MouseWheel>", self.scroll_selected_tab)

        self.build_today_tab()
        self.build_appearance_tab()
        self.build_interact_tab()
        self.build_notes_tab()
        self.build_settings_tab()

    def create_scrollable_tab(self) -> tuple[ttk.Frame, ttk.Frame]:
        container = ttk.Frame(self.notebook)
        canvas = tk.Canvas(
            container,
            bg="#fffaf7",
            highlightthickness=0,
            borderwidth=0,
            yscrollincrement=24,
        )
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        content = ttk.Frame(canvas, padding=12)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window_id, width=event.width),
        )
        self.tab_scroll_canvases[str(container)] = canvas
        return container, content

    def scroll_selected_tab(self, event: tk.Event) -> str | None:
        if isinstance(event.widget, (tk.Listbox, tk.Text)):
            return None
        canvas = self.tab_scroll_canvases.get(self.notebook.select())
        if not canvas or not event.delta:
            return None
        canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")
        return "break"

    def build_today_tab(self) -> None:
        status_frame = ttk.LabelFrame(self.today_tab, text="我的近况")
        status_frame.pack(fill="x", pady=(0, 12))
        status_frame.columnconfigure(1, weight=1)

        ttk.Label(status_frame, text="我的状态").grid(row=0, column=0, sticky="w", padx=12, pady=10)
        my_combo = ttk.Combobox(status_frame, values=list(STATUSES.keys()), textvariable=self.me_status, state="readonly")
        my_combo.grid(row=0, column=1, sticky="ew", padx=12, pady=10)
        my_combo.bind("<<ComboboxSelected>>", lambda _event: self.save_status())

        ttk.Label(status_frame, text="动作轮换").grid(row=1, column=0, sticky="w", padx=12, pady=10)
        interval_combo = ttk.Combobox(
            status_frame,
            values=list(ANIMATION_INTERVAL_OPTIONS),
            textvariable=self.animation_interval_label,
            state="readonly",
        )
        interval_combo.grid(row=1, column=1, sticky="ew", padx=12, pady=10)
        interval_combo.bind("<<ComboboxSelected>>", lambda _event: self.save_animation_interval())

        care_frame = ttk.LabelFrame(self.today_tab, text="照顾值")
        care_frame.pack(fill="x", pady=(0, 12))
        self.add_meter(care_frame, "心情", self.mood_value, 0)
        self.add_meter(care_frame, "能量", self.energy_value, 1)
        self.add_meter(care_frame, "想念", self.longing_value, 2)

        action_frame = ttk.LabelFrame(self.today_tab, text="一点点陪伴")
        action_frame.pack(fill="x", pady=(0, 12))
        for index, action in enumerate(REACTIONS):
            ttk.Button(action_frame, text=action, command=lambda item=action: self.app.react(item)).grid(
                row=index // 2,
                column=index % 2,
                padx=10,
                pady=10,
                sticky="ew",
            )
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        self.anniversary_label = ttk.LabelFrame(self.today_tab, text="纪念日")
        self.anniversary_label.pack(fill="x")
        self.anniversary_text = ttk.Label(self.anniversary_label, text="", font=("Microsoft YaHei", 12, "bold"))
        self.anniversary_text.pack(anchor="w", padx=12, pady=12)

    def build_appearance_tab(self) -> None:
        source_frame = ttk.LabelFrame(self.appearance_tab, text="桌面状态来源")
        source_frame.pack(fill="x", pady=(0, 12))
        source_frame.columnconfigure(0, weight=1)
        source_frame.columnconfigure(1, weight=1)
        ttk.Radiobutton(
            source_frame,
            text="显示我的状态",
            variable=self.desktop_status_source,
            value="me",
            command=self.save_status_source,
        ).grid(row=0, column=0, sticky="w", padx=14, pady=10)
        ttk.Radiobutton(
            source_frame,
            text="显示 TA 的状态",
            variable=self.desktop_status_source,
            value="partner",
            command=self.save_status_source,
        ).grid(row=0, column=1, sticky="w", padx=14, pady=10)

        body = ttk.Frame(self.appearance_tab)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        state_frame = ttk.LabelFrame(body, text="状态动作")
        state_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        state_frame.rowconfigure(0, weight=1)
        state_frame.columnconfigure(0, weight=1)

        self.appearance_list = tk.Listbox(
            state_frame,
            height=12,
            relief="flat",
            bg="#fffdfb",
            fg="#3f3342",
            activestyle="dotbox",
        )
        self.appearance_list.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.appearance_list.bind("<<ListboxSelect>>", lambda _event: self.refresh_appearance_preview())
        state_scroll = ttk.Scrollbar(state_frame, orient="vertical", command=self.appearance_list.yview)
        state_scroll.grid(row=0, column=1, sticky="ns", pady=12)
        self.appearance_list.configure(yscrollcommand=state_scroll.set)

        current_status = self.store.data["me"]["status"]
        for index, state in enumerate(self.animation_states):
            variants = state.get("variants", [])
            status = state.get("status", "")
            self.appearance_list.insert("end", f"{status}  ·  {len(variants)} 种动作")
            if status == current_status:
                self.appearance_list.selection_set(index)
                self.appearance_list.see(index)

        preview_frame = ttk.LabelFrame(body, text="预览")
        preview_frame.grid(row=0, column=1, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)

        self.appearance_preview = ttk.Label(preview_frame, text="")
        self.appearance_preview.grid(row=0, column=0, pady=(18, 8))
        self.appearance_status = ttk.Label(preview_frame, text="", foreground="#6f5962", wraplength=240, justify="center")
        self.appearance_status.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))

        ttk.Button(
            preview_frame,
            text="把这个状态告诉 TA",
            style="Accent.TButton",
            command=self.use_selected_animation,
        ).grid(
            row=2, column=0, sticky="ew", padx=14, pady=(0, 10)
        )
        ttk.Button(preview_frame, text="换一个预览动作", command=self.next_selected_animation).grid(
            row=3, column=0, sticky="ew", padx=14, pady=(0, 10)
        )

    def selected_animation_state(self) -> dict | None:
        if not self.animation_states or not hasattr(self, "appearance_list"):
            return None
        selection = self.appearance_list.curselection()
        if selection:
            return self.animation_states[selection[0]]
        return None

    def refresh_appearance_preview(self) -> None:
        if not hasattr(self, "appearance_preview"):
            return
        state = self.selected_animation_state()
        if not state:
            self.appearance_preview.configure(image="", text="请选择状态")
            self.appearance_status.configure(text="")
            return
        status = str(state.get("status", ""))
        variants = list(state.get("variants", []))
        if not variants:
            self.appearance_preview.configure(image="", text="暂无动作")
            self.appearance_status.configure(text=f"{status} · 0 个动作")
            return
        selected_index = self.preview_variant_indices.get(status)
        if selected_index is None and status == self.app.animation_status and self.app.animation_clip:
            current = next(
                (
                    (index, item)
                    for index, item in enumerate(variants)
                    if animation_file(str(item.get("file", ""))) == self.app.animation_clip.path
                ),
                None,
            )
            if current:
                selected_index = current[0]
        if selected_index is None:
            selected_index = 0
        selected_index %= len(variants)
        self.preview_variant_indices[status] = selected_index
        variant = variants[selected_index]
        path = animation_file(str(variant.get("file", "")))
        try:
            image = load_gif_preview(path)
        except (OSError, ValueError):
            self.appearance_preview.configure(image="", text="动作不可用")
            self.appearance_status.configure(text=f"{status} · {len(variants)} 个动作")
            return
        self.appearance_preview_photo = ImageTk.PhotoImage(image)
        self.appearance_preview.configure(image=self.appearance_preview_photo, text="")
        self.appearance_status.configure(
            text=f"{status} · {len(variants)} 个动作\n当前：{variant.get('name', path.stem)}"
        )

    def use_selected_animation(self) -> None:
        state = self.selected_animation_state()
        if not state:
            messagebox.showwarning("请选择状态", "先在左侧选择一种状态。")
            return
        status = str(state.get("status", "甜蜜"))
        self.selected_animation_status.set(status)
        self.me_status.set(status)
        self.app.set_my_status(status)
        self.refresh_appearance_preview()

    def next_selected_animation(self) -> None:
        state = self.selected_animation_state()
        if not state:
            return
        status = str(state.get("status", "甜蜜"))
        variants = list(state.get("variants", []))
        if not variants:
            return
        current = self.preview_variant_indices.get(status, 0)
        self.preview_variant_indices[status] = (current + 1) % len(variants)
        self.refresh_appearance_preview()

    def add_meter(self, parent: ttk.Frame, label: str, variable: tk.IntVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=8)
        bar = ttk.Progressbar(parent, maximum=100, variable=variable)
        bar.grid(row=row, column=1, sticky="ew", padx=8, pady=8)
        ttk.Label(parent, textvariable=variable, width=4).grid(row=row, column=2, sticky="e", padx=12, pady=8)
        parent.columnconfigure(1, weight=1)

    def build_interact_tab(self) -> None:
        sync_frame = ttk.LabelFrame(self.interact_tab, text="自动同步")
        sync_frame.pack(fill="x", pady=(0, 12))
        sync_frame.columnconfigure(0, weight=1)
        sync_frame.columnconfigure(1, weight=1)
        ttk.Label(sync_frame, textvariable=self.sync_status_text, foreground="#4b8588").grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=12,
            pady=(10, 4),
        )
        ttk.Checkbutton(
            sync_frame,
            text="开启共享文件夹自动同步",
            variable=self.auto_sync_enabled,
            command=self.toggle_auto_sync,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=4)
        ttk.Button(sync_frame, text="选择两人共享文件夹", command=self.choose_sync_folder).grid(
            row=2,
            column=0,
            sticky="ew",
            padx=(12, 6),
            pady=(6, 12),
        )
        ttk.Button(sync_frame, text="立即同步", style="Accent.TButton", command=self.manual_folder_sync).grid(
            row=2,
            column=1,
            sticky="ew",
            padx=(6, 12),
            pady=(6, 12),
        )

        manual_frame = ttk.LabelFrame(self.interact_tab, text="同步文件")
        manual_frame.pack(fill="x", pady=(0, 12))
        manual_frame.columnconfigure(0, weight=1)
        manual_frame.columnconfigure(1, weight=1)
        ttk.Button(manual_frame, text="导出给 TA", command=self.export_sync).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(12, 6),
            pady=12,
        )
        ttk.Button(manual_frame, text="导入 TA 的文件", command=self.import_sync).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(6, 12),
            pady=12,
        )

        quick_frame = ttk.LabelFrame(self.interact_tab, text="快速留言")
        quick_frame.pack(fill="x", pady=(0, 12))
        quick_messages = ["我想你啦", "记得喝水", "忙完抱抱", "今天也辛苦了", "晚安，梦里见", "到家告诉我"]
        for index, message in enumerate(quick_messages):
            ttk.Button(quick_frame, text=message, command=lambda text=message: self.add_quick_note(text)).grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=10,
                pady=8,
            )
        quick_frame.columnconfigure(0, weight=1)
        quick_frame.columnconfigure(1, weight=1)

    def choose_sync_folder(self) -> None:
        current = self.store.data["sync"].get("folder", "")
        initial = current if current and Path(current).exists() else str(Path.home())
        folder = filedialog.askdirectory(
            parent=self.window,
            title="选择你和 TA 共用的云盘文件夹",
            initialdir=initial,
        )
        if not folder:
            return
        self.store.configure_sync_folder(Path(folder), enabled=True)
        self.auto_sync_enabled.set(True)
        self.app.sync_now(user_initiated=True)
        self.refresh_sync_status()

    def toggle_auto_sync(self) -> None:
        enabled = bool(self.auto_sync_enabled.get())
        sync = self.store.data["sync"]
        if enabled and not sync.get("folder"):
            self.choose_sync_folder()
            if not self.store.data["sync"].get("folder"):
                self.auto_sync_enabled.set(False)
            return
        sync["enabled"] = enabled
        sync["last_error"] = ""
        self.store.save()
        if enabled:
            self.app.sync_now(user_initiated=True)
        self.refresh_sync_status()

    def manual_folder_sync(self) -> None:
        sync = self.store.data["sync"]
        if not sync.get("folder"):
            self.choose_sync_folder()
            return
        if not sync.get("enabled"):
            sync["enabled"] = True
            self.auto_sync_enabled.set(True)
            self.store.save()
        self.app.sync_now(user_initiated=True)
        self.refresh_sync_status()

    def refresh_sync_status(self) -> None:
        sync = self.store.data["sync"]
        folder = str(sync.get("folder", "")).strip()
        if not folder:
            text = "尚未连接共享文件夹"
        elif sync.get("last_error"):
            text = f"同步异常 · {Path(folder).name}"
        elif not sync.get("enabled"):
            text = f"已暂停 · {Path(folder).name}"
        elif sync.get("last_sync_at"):
            text = f"已连接 · 上次同步 {short_time(sync['last_sync_at'])}"
        else:
            text = f"已连接 · {Path(folder).name}"
        self.sync_status_text.set(text)

    def build_notes_tab(self) -> None:
        editor_frame = ttk.LabelFrame(self.notes_tab, text="写给 TA")
        editor_frame.pack(fill="x", pady=(0, 12))
        self.note_text = tk.Text(editor_frame, height=4, wrap="word", relief="flat", bg="#fff5f7", fg="#3f3342")
        self.note_text.pack(fill="x", padx=12, pady=(12, 8))
        ttk.Button(editor_frame, text="放进信箱", style="Accent.TButton", command=self.add_note).pack(anchor="e", padx=12, pady=(0, 12))

        list_frame = ttk.LabelFrame(self.notes_tab, text="信箱")
        list_frame.pack(fill="both", expand=True)
        list_body = ttk.Frame(list_frame)
        list_body.pack(fill="both", expand=True, padx=12, pady=12)
        list_body.columnconfigure(0, weight=1)
        list_body.rowconfigure(0, weight=1)

        self.notes_list = tk.Listbox(list_body, height=8, relief="flat", bg="#fffdfb", fg="#3f3342", activestyle="dotbox")
        self.notes_list.grid(row=0, column=0, sticky="nsew")
        self.notes_list.bind("<<ListboxSelect>>", lambda _event: self.show_selected_note())
        scrollbar = ttk.Scrollbar(list_body, orient="vertical", command=self.notes_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.notes_list.configure(yscrollcommand=scrollbar.set)

        self.note_preview = tk.Text(list_frame, height=5, wrap="word", relief="flat", bg="#fff5f7", fg="#3f3342", state="disabled")
        self.note_preview.pack(fill="x", padx=12, pady=(0, 12))

    def build_settings_tab(self) -> None:
        profile = ttk.LabelFrame(self.settings_tab, text="名字")
        profile.pack(fill="x", pady=(0, 12))
        profile.columnconfigure(1, weight=1)
        self.add_entry(profile, "我的昵称", self.me_name, 0)
        self.add_entry(profile, "TA 的昵称", self.partner_name, 1)
        self.add_entry(profile, "宠物名字", self.pet_name, 2)

        dates = ttk.LabelFrame(self.settings_tab, text="日期")
        dates.pack(fill="x", pady=(0, 12))
        dates.columnconfigure(1, weight=1)
        self.add_entry(dates, "在一起日期", self.together_date, 0)
        self.add_entry(dates, "纪念日日期", self.anniversary_date, 1)
        ttk.Label(dates, text="格式：2026-07-05", foreground="#6f5962").grid(row=2, column=1, sticky="w", padx=12, pady=(0, 10))

        window = ttk.LabelFrame(self.settings_tab, text="窗口")
        window.pack(fill="x")
        ttk.Checkbutton(
            window,
            text="保持在最上方",
            variable=self.always_on_top,
            command=self.save_window_settings,
        ).pack(anchor="w", padx=12, pady=(10, 4))
        ttk.Checkbutton(
            window,
            text="开机自动启动彼端",
            variable=self.startup_enabled,
            command=self.save_startup_setting,
        ).pack(anchor="w", padx=12, pady=4)
        ttk.Label(window, text="透明度").pack(anchor="w", padx=12, pady=(8, 0))
        opacity_scale = ttk.Scale(
            window,
            from_=0.45,
            to=1.0,
            variable=self.opacity,
            command=lambda _value: self.save_window_settings(),
        )
        opacity_scale.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(window, text="把桌宠放回左上角", command=self.reset_position).pack(fill="x", padx=12, pady=(0, 12))

    def add_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=10)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=12, pady=10)

    def save_status(self) -> None:
        self.app.set_my_status(self.me_status.get())
        self.store.save()
        self.refresh_all()

    def save_animation_interval(self) -> None:
        label = self.animation_interval_label.get()
        seconds = ANIMATION_INTERVAL_OPTIONS.get(label, 60)
        self.store.data["pet"]["animation_interval_seconds"] = seconds
        self.store.save()
        self.app.animation_variant_elapsed_ms = 0
        self.app.say(f"动作轮换已设为 {label}。")

    def save_status_source(self) -> None:
        source = self.desktop_status_source.get()
        if source not in STATUS_SOURCE_OPTIONS:
            source = "partner"
            self.desktop_status_source.set(source)
        self.store.data["pet"]["status_source"] = source
        self.store.save()
        self.app.set_status_animation(self.app.displayed_status(), force_variant=True)
        self.app.say(f"桌面现在显示{STATUS_SOURCE_OPTIONS[source]}。")
        self.refresh_appearance_preview()

    def save_profile(self, silent: bool = False) -> None:
        if parse_date(self.together_date.get()).isoformat() != self.together_date.get():
            messagebox.showwarning("日期格式", "在一起日期请使用 2026-07-05 这样的格式。")
            return
        if parse_date(self.anniversary_date.get()).isoformat() != self.anniversary_date.get():
            messagebox.showwarning("日期格式", "纪念日日期请使用 2026-07-05 这样的格式。")
            return
        data = self.store.data
        data["me"]["name"] = self.me_name.get().strip() or "我"
        data["partner"]["name"] = self.partner_name.get().strip() or "TA"
        data["pet"]["name"] = self.pet_name.get().strip() or "小彼端"
        data["me"]["status"] = self.me_status.get()
        data["couple"]["together_date"] = self.together_date.get()
        data["couple"]["anniversary_date"] = self.anniversary_date.get()
        data["pet"]["opacity"] = round(float(self.opacity.get()), 2)
        data["pet"]["always_on_top"] = bool(self.always_on_top.get())
        data["pet"]["status_source"] = self.desktop_status_source.get()
        self.store.save()
        self.app.set_window_attributes()
        self.app.refresh_tray()
        self.app.request_sync()
        self.refresh_all()
        if not silent:
            self.app.say("我记住啦。")

    def save_window_settings(self) -> None:
        data = self.store.data
        data["pet"]["opacity"] = round(float(self.opacity.get()), 2)
        data["pet"]["always_on_top"] = bool(self.always_on_top.get())
        self.store.save()
        self.app.set_window_attributes()

    def save_startup_setting(self) -> None:
        try:
            set_startup_enabled(bool(self.startup_enabled.get()))
            self.app.refresh_tray()
        except OSError as exc:
            self.startup_enabled.set(is_startup_enabled())
            messagebox.showerror("设置失败", f"开机启动设置失败：{exc}")

    def refresh_all(self) -> None:
        data = self.store.data
        self.mood_value.set(data["care"]["mood"])
        self.energy_value.set(data["care"]["energy"])
        self.longing_value.set(data["care"]["longing"])
        interval_seconds = int(data["pet"].get("animation_interval_seconds", 60))
        self.animation_interval_label.set(
            ANIMATION_INTERVAL_LABELS.get(interval_seconds, "60 秒")
        )
        self.desktop_status_source.set(data["pet"].get("status_source", "partner"))
        together_days = days_between(data["couple"]["together_date"])
        anniversary_days = days_until_anniversary(data["couple"]["anniversary_date"])
        self.summary.configure(
            text=f"{data['me']['name']} 和 {data['partner']['name']}，在一起第 {together_days} 天。"
        )
        if anniversary_days == 0:
            anniversary = "今天就是纪念日。"
        else:
            anniversary = f"距离下一次纪念日还有 {anniversary_days} 天。"
        self.anniversary_text.configure(text=f"在一起第 {together_days} 天 · {anniversary}")
        self.auto_sync_enabled.set(bool(data["sync"].get("enabled", False)))
        self.startup_enabled.set(is_startup_enabled())
        self.refresh_sync_status()
        self.refresh_notes()
        self.refresh_appearance_preview()

    def add_note(self) -> None:
        text = self.note_text.get("1.0", "end").strip()
        if not text:
            return
        author = self.store.data["me"]["name"]
        self.store.add_note(author, text)
        self.note_text.delete("1.0", "end")
        self.refresh_notes()
        self.app.say("这句话我先替你收好。")
        self.app.request_sync()

    def add_quick_note(self, text: str) -> None:
        author = self.store.data["me"]["name"]
        self.store.add_note(author, text)
        self.refresh_notes()
        self.app.say(text)
        self.app.request_sync()

    def refresh_notes(self) -> None:
        if not hasattr(self, "notes_list"):
            return
        self.notes_list.delete(0, "end")
        for note in reversed(self.store.data.get("notes", [])[-60:]):
            text = note.get("text", "").replace("\n", " ")
            if len(text) > 24:
                text = text[:24] + "..."
            self.notes_list.insert("end", f"{short_time(note.get('created_at'))}  {note.get('author', '')}: {text}")
        self.show_selected_note()

    def show_selected_note(self) -> None:
        if not hasattr(self, "note_preview"):
            return
        selection = self.notes_list.curselection()
        notes = list(reversed(self.store.data.get("notes", [])[-60:]))
        text = ""
        if selection:
            note = notes[selection[0]]
            text = f"{note.get('author', '')} · {short_time(note.get('created_at'))}\n\n{note.get('text', '')}"
        self.note_preview.configure(state="normal")
        self.note_preview.delete("1.0", "end")
        self.note_preview.insert("1.0", text)
        self.note_preview.configure(state="disabled")

    def export_sync(self) -> None:
        packet = self.store.make_sync_packet()
        filename = filedialog.asksaveasfilename(
            parent=self.window,
            title="导出同步文件",
            defaultextension=".json",
            filetypes=[("彼端同步文件", "*.json")],
            initialfile=f"彼端同步_{dt.date.today().isoformat()}.json",
        )
        if not filename:
            return
        Path(filename).write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        self.app.say("同步文件已经准备好啦。")
        messagebox.showinfo("导出完成", "把这个同步文件发给 TA，TA 导入后就能看到你的状态和留言。")

    def import_sync(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self.window,
            title="导入同步文件",
            filetypes=[("彼端同步文件", "*.json"), ("JSON 文件", "*.json")],
        )
        if not filename:
            return
        try:
            packet = json.loads(Path(filename).read_text(encoding="utf-8"))
            imported = self.store.import_sync_packet(packet)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        self.partner_name.set(self.store.data["partner"]["name"])
        self.refresh_all()
        self.app.handle_sync_result(imported)
        messagebox.showinfo(
            "导入完成",
            f"已更新 TA 的状态，收到 {imported['notes']} 条留言和 {imported['interactions']} 次互动。",
        )

    def reset_position(self) -> None:
        self.store.data["pet"]["x"] = 80
        self.store.data["pet"]["y"] = 120
        self.store.save()
        self.app.root.geometry("+80+120")
        self.app.say("我回到这里啦。")


def main() -> int:
    configure_windows_identity()
    mutex_handle = acquire_single_instance()
    if mutex_handle is None:
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(
                None,
                "彼端已经在运行了，请查看桌面或右下角托盘图标。",
                APP_NAME,
                0x40,
            )
        return 0
    try:
        app = DesktopPetApp()
        app.start()
        return 0
    except Exception as exc:
        messagebox.showerror(APP_NAME, f"启动失败：{exc}")
        return 1
    finally:
        if os.name == "nt" and mutex_handle:
            ctypes.windll.kernel32.CloseHandle(mutex_handle)


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import biduan_pet


class CoreStateTests(unittest.TestCase):
    def test_deep_merge_does_not_mutate_defaults(self) -> None:
        defaults = {"profile": {"name": "我"}, "notes": []}
        saved = {"profile": {"name": "小夏"}}
        merged = biduan_pet.deep_merge(defaults, saved)
        merged["notes"].append("hello")
        self.assertEqual(defaults["notes"], [])
        self.assertEqual(merged["profile"]["name"], "小夏")

    def test_new_store_gets_stable_device_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            first = biduan_pet.StateStore(path)
            first_id = first.device_id
            second = biduan_pet.StateStore(path)
            self.assertEqual(first_id, second.device_id)
            self.assertEqual(len(first_id), 32)

    def test_two_devices_exchange_status_notes_and_interactions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = root / "shared"
            alice = biduan_pet.StateStore(root / "alice.json")
            bob = biduan_pet.StateStore(root / "bob.json")

            alice.data["me"].update({"name": "小夏", "status": "甜蜜"})
            bob.data["me"].update({"name": "阿远", "status": "工作"})
            alice.configure_sync_folder(shared)
            bob.configure_sync_folder(shared)

            alice.add_note("小夏", "今晚忙完一起看电影")
            alice.add_interaction("小夏", "抱抱", "一个很轻很久的抱抱。")
            alice.sync_folder_once()
            imported = bob.sync_folder_once()

            self.assertEqual(imported["notes"], 1)
            self.assertEqual(imported["interactions"], 1)
            self.assertEqual(bob.data["partner"]["name"], "小夏")
            self.assertEqual(bob.data["partner"]["status"], "甜蜜")
            self.assertIn("抱抱", imported["latest_message"])
            self.assertEqual(bob.data["notes"][-1]["text"], "今晚忙完一起看电影")

            repeated = bob.sync_folder_once()
            self.assertEqual(repeated["notes"], 0)
            self.assertEqual(repeated["interactions"], 0)

            alice.sync_folder_once()
            self.assertEqual(alice.data["partner"]["name"], "阿远")
            self.assertEqual(alice.data["partner"]["status"], "工作")

    def test_invalid_sync_packet_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = biduan_pet.StateStore(Path(directory) / "state.json")
            with self.assertRaises(ValueError):
                store.import_sync_packet({"app": "OtherApp"})

    def test_leap_day_anniversary_is_supported(self) -> None:
        days = biduan_pet.days_until_anniversary("2024-02-29")
        self.assertGreaterEqual(days, 0)
        self.assertLessEqual(days, 366)

    def test_default_state_is_not_modified_by_store_changes(self) -> None:
        snapshot = copy.deepcopy(biduan_pet.DEFAULT_STATE)
        with tempfile.TemporaryDirectory() as directory:
            store = biduan_pet.StateStore(Path(directory) / "state.json")
            store.data["notes"].append({"text": "local"})
        self.assertEqual(snapshot, biduan_pet.DEFAULT_STATE)

    def test_legacy_status_and_appearance_are_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            legacy = biduan_pet.StateStore(path)
            legacy.data["me"]["status"] = "想你"
            legacy.data["partner"]["status"] = "学习"
            legacy.data["pet"]["appearance"]["mode"] = "preset"
            legacy.data["pet"]["animation_interval_seconds"] = 999
            legacy.data["pet"]["status_source"] = "unknown"
            legacy.save()

            migrated = biduan_pet.StateStore(path)
            self.assertEqual(migrated.data["me"]["status"], "甜蜜")
            self.assertEqual(migrated.data["partner"]["status"], "工作")
            self.assertEqual(migrated.data["pet"]["appearance"]["mode"], "animated")
            self.assertEqual(migrated.data["pet"]["animation_interval_seconds"], 60)
            self.assertEqual(migrated.data["pet"]["status_source"], "partner")

    def test_displayed_status_uses_selected_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = biduan_pet.StateStore(Path(directory) / "state.json")
            store.data["me"]["status"] = "开心"
            store.data["partner"]["status"] = "工作"
            app = object.__new__(biduan_pet.DesktopPetApp)
            app.store = store

            store.data["pet"]["status_source"] = "partner"
            self.assertEqual(app.displayed_status(), "工作")
            store.data["pet"]["status_source"] = "me"
            self.assertEqual(app.displayed_status(), "开心")


class AnimationAssetTests(unittest.TestCase):
    def test_manifest_contains_all_supplied_actions(self) -> None:
        manifest = biduan_pet.load_animation_manifest()
        states = manifest["states"]
        self.assertEqual(len(states), 11)
        self.assertEqual({state["status"] for state in states}, set(biduan_pet.STATUSES))
        self.assertEqual(sum(len(state["variants"]) for state in states), 61)

        files = [
            biduan_pet.animation_file(variant["file"])
            for state in states
            for variant in state["variants"]
        ]
        files.append(biduan_pet.animation_file(manifest["drag"]["file"]))
        self.assertTrue(all(path.is_file() for path in files))

    def test_gif_clip_loads_frames_and_durations(self) -> None:
        manifest = biduan_pet.load_animation_manifest()
        variant = manifest["states"][0]["variants"][0]
        clip = biduan_pet.load_gif_clip(
            biduan_pet.animation_file(variant["file"]),
            name=variant["name"],
            size=64,
        )
        self.assertEqual(len(clip.frames), variant["frames"])
        self.assertEqual(len(clip.frames), len(clip.durations))
        self.assertEqual(clip.frames[0].size, (64, 64))
        self.assertTrue(all(20 <= duration <= 250 for duration in clip.durations))
        used_alpha_values = {
            value
            for value, count in enumerate(clip.frames[0].getchannel("A").histogram())
            if count
        }
        self.assertTrue(used_alpha_values <= {0, 255})

    def test_animation_interval_has_four_supported_choices(self) -> None:
        self.assertEqual(
            set(biduan_pet.ANIMATION_INTERVAL_OPTIONS.values()),
            {10, 30, 60, 300},
        )


if __name__ == "__main__":
    unittest.main()

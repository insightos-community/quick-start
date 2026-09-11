# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "mesa_launch", Path(__file__).resolve().parents[1] / "artifacts/mesa/launch.py")
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class MesaProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prefix = Path(self.temp.name)
        (self.prefix / "lib").mkdir()
        (self.prefix / "lib/libEGL.so.1").touch()

    def report(self, software=False, foreign=False):
        prefix = Path("/foreign") if foreign else self.prefix
        return {"renderer": "llvmpipe" if software else "AMD Radeon",
                "software": software,
                "libraries": [str(prefix / "lib/libEGL.so.1"),
                              str(prefix / "lib/libgallium-25.2.7.so")]}

    def test_auto_tries_other_devices_before_software_fallback(self):
        def probe(env, listing=False):
            if listing:
                return {"devices": 2}
            return self.report(software=env["MUJOCO_EGL_DEVICE_ID"] == "0")
        env, report = launch.select("auto", {}, self.prefix, libc="musl", probe=probe)
        self.assertEqual((report["selected"], report["device"]), ("mesa-gpu", 1))
        self.assertEqual(env["MUJOCO_EGL_DEVICE_ID"], "1")
        self.assertIn("error", report["attempts"][0])

    def test_auto_reports_software_fallback(self):
        def probe(env, listing=False):
            return {"devices": 1} if listing else self.report(software=True)
        env, report = launch.select("auto", {}, self.prefix, libc="musl", probe=probe)
        self.assertEqual(report["selected"], "software")
        self.assertTrue(report["opengl"]["software"])
        self.assertEqual(env["LIBGL_ALWAYS_SOFTWARE"], "1")

    def test_explicit_gpu_or_device_never_accepts_software(self):
        def probe(env, listing=False):
            return {"devices": 1} if listing else self.report(software=True)
        for profile, device in (("mesa-gpu", None), ("auto", 0)):
            with self.subTest(profile=profile), self.assertRaisesRegex(RuntimeError, "GPU acceleration is required"):
                launch.select(profile, {}, self.prefix, device=device, libc="musl", probe=probe)

    def test_glibc_cannot_load_bundled_musl_mesa(self):
        with self.assertRaisesRegex(ValueError, "musl Python"):
            launch.select("software", {}, self.prefix, libc="glibc")

    def test_bundled_profile_clears_conflicting_driver_overrides(self):
        base = {key: "old" for key in launch.DRIVER_ENV}
        base.update(LD_LIBRARY_PATH="/pinocchio/lib", MUJOCO_EGL_DEVICE_ID="5")
        env = launch.environment(base, "mesa-gpu", self.prefix, None, "musl")
        self.assertTrue(all(key not in env for key in launch.DRIVER_ENV))
        self.assertNotIn("MUJOCO_EGL_DEVICE_ID", env)
        self.assertEqual(env["LD_LIBRARY_PATH"], str(self.prefix / "lib") + ":/pinocchio/lib")
        self.assertEqual(base["GALLIUM_DRIVER"], "old")

    def test_wrong_library_origin_is_rejected(self):
        def probe(env, listing=False):
            return {"devices": 1} if listing else self.report(foreign=True)
        with self.assertRaisesRegex(RuntimeError, "Unexpected lib"):
            launch.select("mesa-gpu", {}, self.prefix, libc="musl", probe=probe)

    def test_application_shared_dependencies_precede_mesa_runtime_fallback(self):
        runtime = self.prefix / "runtime"
        (runtime / "lib").mkdir(parents=True)
        env = launch.environment({"LD_LIBRARY_PATH": "/released-deps/lib"},
                                 "mesa-gpu", self.prefix, runtime, "musl")
        self.assertEqual(env["LD_LIBRARY_PATH"].split(":"),
                         [str(self.prefix / "lib"), "/released-deps/lib", str(runtime / "lib")])

    def test_system_uses_host_vendor_configuration_and_reports_software(self):
        base = {"__EGL_VENDOR_LIBRARY_FILENAMES": "/host/nvidia.json"}
        def probe(env, listing=False):
            self.assertEqual(env["__EGL_VENDOR_LIBRARY_FILENAMES"], base["__EGL_VENDOR_LIBRARY_FILENAMES"])
            self.assertNotIn("LD_LIBRARY_PATH", env)
            return {"devices": 1} if listing else self.report(software=True, foreign=True)
        _, report = launch.select("auto", base, libc="glibc", probe=probe)
        self.assertEqual(report["selected"], "system")
        self.assertTrue(report["opengl"]["software"])

    def test_failed_driver_can_fall_back_in_fresh_process_environment(self):
        def probe(env, listing=False):
            if env.get("GALLIUM_DRIVER") != "llvmpipe":
                return {"error": "Driver crashed or timed out"}
            return {"devices": 1} if listing else self.report(software=True)
        _, report = launch.select("auto", {}, self.prefix, libc="musl", probe=probe)
        self.assertEqual(report["selected"], "software")
        self.assertEqual(report["attempts"][0]["error"], "Driver crashed or timed out")


if __name__ == "__main__":
    unittest.main()

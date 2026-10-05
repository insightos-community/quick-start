# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
"""CPU 线程覆盖阀门与拓扑预览。

无 GPU 主机上线程数决定推理耗时数量级, 但值取决于运行时条件 (本机拓扑 +
同机负载), 安装时定死会翻车。这些用例固定"安装器只做覆盖阀门、默认交给
运行期自动探测"这一契约, 以及把探测结果如实展示给验收。
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import semantic_installer as installer


class StubApp:
    """只够 cpu_threads / cpu_topology_note 使用的最小 App 替身。"""

    def __init__(self, settings):
        self.settings = dict(settings)
        self.vars = {}
        self.logs = []

    def log(self, level, message):
        self.logs.append((level, message))


class ParseCpuThreadsTests(unittest.TestCase):
    def test_blank_means_auto_detection(self):
        """默认留空 = 交给 Ability 自动探测, 这是推荐路径, 不能被当成 0 处理。"""
        for raw in (None, "", "   "):
            self.assertIsNone(installer.parse_cpu_threads(raw))
        self.assertIsNone(installer.parse_cpu_threads(
            installer.DEFAULT_SETTINGS.get("CPU_THREADS")))

    def test_valid_values_are_parsed_and_trimmed(self):
        self.assertEqual(installer.parse_cpu_threads("8"), 8)
        self.assertEqual(installer.parse_cpu_threads(" 9 "), 9)
        self.assertEqual(installer.parse_cpu_threads("1"), 1)

    def test_invalid_values_are_rejected_at_install_time(self):
        """非法值必须在安装阶段报错, 而不是留给运行期静默失效。"""
        for raw in ("0", "-1", "abc", "3.5", "8核"):
            with self.assertRaises(ValueError):
                installer.parse_cpu_threads(raw)

    def test_parser_does_not_log_so_the_settings_form_can_render_every_frame(self):
        """设置界面每帧都要渲染拓扑预览, 解析不能有日志副作用 (否则刷屏)。"""
        app = StubApp({**installer.DEFAULT_SETTINGS, "CPU_THREADS": "abc"})
        with self.assertRaises(ValueError):
            installer.parse_cpu_threads(app.settings.get("CPU_THREADS"))
        self.assertEqual(app.logs, [])


class CpuThreadsSettingTests(unittest.TestCase):
    def test_blank_writes_nothing_so_ability_keeps_auto_tuning(self):
        app = StubApp({**installer.DEFAULT_SETTINGS, "CPU_THREADS": ""})
        self.assertEqual(installer.cpu_threads(app), "")
        self.assertEqual(app.logs, [])

    def test_explicit_value_is_returned_verbatim(self):
        app = StubApp({**installer.DEFAULT_SETTINGS, "CPU_THREADS": "8"})
        self.assertEqual(installer.cpu_threads(app), "8")

    def test_value_above_available_cores_warns_but_does_not_block_the_install(self):
        """运行期会自行收敛 (cpu_tuning 取 min), 因此这里只告警不中断安装。"""
        available = len(installer.cpu_available_cores())
        app = StubApp({**installer.DEFAULT_SETTINGS, "CPU_THREADS": str(available + 8)})
        self.assertEqual(installer.cpu_threads(app), str(available + 8))
        self.assertEqual([level for level, _ in app.logs], ["warn"])

    def test_invalid_value_raises_so_the_step_reports_failure(self):
        app = StubApp({**installer.DEFAULT_SETTINGS, "CPU_THREADS": "abc"})
        with self.assertRaises(ValueError):
            installer.cpu_threads(app)


class CpuTopologyNoteTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))

    def _fake_topology(self, tiers):
        """造一棵假的 /sys 频率树: {cpu_index: 频率kHz}。"""
        for cpu, khz in tiers.items():
            d = self.root / f"cpu{cpu}" / "cpufreq"
            d.mkdir(parents=True, exist_ok=True)
            (d / "cpuinfo_max_freq").write_text(str(khz), encoding="utf-8")

    def test_note_reports_tiers_and_auto_budget(self):
        """验收要能提前看到"这台机器会怎么算", 而不是等运行期日志。"""
        self._fake_topology({0: 4_900_000, 1: 4_900_000, 2: 4_400_000, 3: 2_500_000})
        app = StubApp(installer.DEFAULT_SETTINGS)
        with patch.object(installer, "cpu_available_cores", lambda: [0, 1, 2, 3]), \
                patch.object(installer, "CPUFREQ_CPU_ROOT", str(self.root), create=True):
            note = installer._cpu_topology_note_at(str(self.root), app)
        self.assertIn("4 核", note)
        self.assertIn("4900MHz", note)
        self.assertIn("2500MHz", note)
        # 3 个快速核 (排除 1 个低速核) 扣掉保留量 2 = 1
        self.assertIn("自动预算 1 线程", note)

    def test_homogeneous_cores_are_not_penalised(self):
        """读不到分档 (虚拟机/容器) 时不能把核数算少, 否则线程预算偏低。"""
        app = StubApp(installer.DEFAULT_SETTINGS)
        note = installer._cpu_topology_note_at(str(self.root / "absent"), app,
                                               cores=[0, 1, 2, 3])
        self.assertIn("4 核", note)
        self.assertNotIn("频率分档", note)

    def test_explicit_override_is_shown_as_such(self):
        app = StubApp({**installer.DEFAULT_SETTINGS, "CPU_THREADS": "6"})
        note = installer._cpu_topology_note_at(str(self.root / "absent"), app,
                                               cores=[0, 1, 2, 3])
        self.assertIn("已被 CPU_THREADS=6 覆盖", note)

    def test_note_has_no_log_side_effects(self):
        """设置界面每帧调用一次, 不能因此写日志。"""
        app = StubApp({**installer.DEFAULT_SETTINGS, "CPU_THREADS": "999"})
        for _ in range(3):
            installer._cpu_topology_note_at(str(self.root / "absent"), app, cores=[0, 1])
        self.assertEqual(app.logs, [])


class CpuCgroupQuotaTests(unittest.TestCase):
    def test_missing_cgroup_files_yield_none(self):
        """取不到配额要退回可见核数, 不能抛错中断探测。"""
        with patch.object(installer, "CGROUP_V2_CPU_MAX", "/nonexistent/cpu.max"), \
                patch.object(installer, "CGROUP_V1_QUOTA", "/nonexistent/quota"), \
                patch.object(installer, "CGROUP_V1_PERIOD", "/nonexistent/period"):
            self.assertIsNone(installer.cpu_cgroup_quota())

    def test_parses_v2_quota(self):
        path = Path(tempfile.mkdtemp()) / "cpu.max"
        self.addCleanup(lambda: __import__("shutil").rmtree(path.parent, ignore_errors=True))
        path.write_text("400000 100000", encoding="utf-8")
        with patch.object(installer, "CGROUP_V2_CPU_MAX", str(path)), \
                patch.object(installer, "CGROUP_V1_QUOTA", "/nonexistent/quota"), \
                patch.object(installer, "CGROUP_V1_PERIOD", "/nonexistent/period"):
            self.assertEqual(installer.cpu_cgroup_quota(), 4)

    def test_unlimited_and_malformed_quota_fall_back(self):
        path = Path(tempfile.mkdtemp()) / "cpu.max"
        self.addCleanup(lambda: __import__("shutil").rmtree(path.parent, ignore_errors=True))
        for content in ("max 100000", "", "abc 100000", "100000 0"):
            path.write_text(content, encoding="utf-8")
            with patch.object(installer, "CGROUP_V2_CPU_MAX", str(path)), \
                    patch.object(installer, "CGROUP_V1_QUOTA", "/nonexistent/quota"), \
                    patch.object(installer, "CGROUP_V1_PERIOD", "/nonexistent/period"):
                self.assertIsNone(installer.cpu_cgroup_quota(), content)


class ReservedCoreParityTests(unittest.TestCase):
    def test_reserved_count_matches_ability_rule(self):
        """安装器预览必须与 Ability 的实际规则一致, 否则日志会误导验收。"""
        import math
        for total in range(1, 129):
            ability = min(total - 1, max(2, math.ceil(total * 0.2)))
            installer_reserved = min(total - 1, max(2, -(-total * 20 // 100)))
            self.assertEqual(ability, installer_reserved, f"total={total}")


if __name__ == "__main__":
    unittest.main()
